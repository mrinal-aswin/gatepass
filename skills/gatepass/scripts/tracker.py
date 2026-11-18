"""Local SQLite store for edits made on the dashboard, applied to the Markdown sources.

Every edit (a status click, a funnel week) is recorded as an event in people/<slug>/tracker.sqlite,
then applied to the readable sources (actions.md, resume/ASSUMPTIONS.md, funnel.md). The Markdown
stays the record every other stage reads; the database is the write-ahead log and audit trail.
`sync` applies anything still pending, which is why every pipeline run starts with it.

Used by actions.py (set / funnel / sync / serve). Stdlib only.
"""
import datetime, http.server, json, re, secrets, sqlite3, sys, threading
from pathlib import Path

DB_NAME = "tracker.sqlite"
SCHEMA_VERSION = "1"
SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,
  source     TEXT NOT NULL CHECK (source IN ('page', 'cli')),
  kind       TEXT NOT NULL CHECK (kind IN ('status', 'funnel')),
  target     TEXT NOT NULL,          -- action or ledger ID, or the funnel week
  payload    TEXT NOT NULL,          -- JSON
  base       TEXT,                   -- status the editor saw; NULL means "apply regardless"
  state      TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('pending', 'applied', 'conflict', 'rejected')),
  detail     TEXT,
  applied_at TEXT
);
CREATE INDEX IF NOT EXISTS events_by_state ON events (state, id);
"""
STATUSES = ("open", "resolved", "ignored")
# "sourced" = taken from the person's own documents, not yet confirmed by them. It is not a guess,
# so it shows as resolved; choosing a status on the page always writes the explicit mapping below.
LEDGER_TO_PAGE = {"assumed": "open", "sourced": "resolved", "verified": "resolved", "removed": "ignored"}
PAGE_TO_LEDGER = {"open": "assumed", "resolved": "verified", "ignored": "removed"}
ACTIONS_MD, LEDGER_MD, FUNNEL_MD = "outputs/actions.md", "outputs/resume/ASSUMPTIONS.md", "outputs/funnel.md"
FRAMEWORK = Path(__file__).resolve().parent.parent / "assets" / "framework.json"
MAX_BODY = 64 * 1024
WRITE_LOCK = threading.Lock()  # one writer at a time: events apply in order and Markdown writes never interleave


def now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def connect(pdir: Path) -> sqlite3.Connection:
    db = sqlite3.connect(pdir / DB_NAME, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    db.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    db.commit()
    return db


def funnel_keys() -> list:
    return [c["key"] for c in json.loads(FRAMEWORK.read_text())["funnel"]["columns"]]


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


# ---------- validation (before anything is recorded) ----------
def validate(kind: str, target: str, payload: dict) -> str:
    """Return an error message, or "" when the edit is well formed."""
    if kind == "status":
        if not re.fullmatch(r"[A-Z]+\d+", target or ""):
            return f"'{target}' is not an action or ledger ID"
        if payload.get("status") not in STATUSES:
            return f"status must be one of {', '.join(STATUSES)}"
        return ""
    if kind == "funnel":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", target or ""):
            return "week must be YYYY-MM-DD (the Monday of the week)"
        keys = funnel_keys()
        counts = payload.get("counts", {})
        bad = [k for k, v in counts.items() if k not in keys or not (isinstance(v, int) and 0 <= v <= 100000)]
        return f"counts must be whole numbers for {', '.join(keys)} (bad: {', '.join(bad)})" if bad else ""
    return f"unknown kind '{kind}'"


def record(pdir: Path, kind: str, target: str, payload: dict, base: str = None, source: str = "cli") -> int:
    err = validate(kind, target, payload)
    if err:
        raise ValueError(err)
    with connect(pdir) as db:
        cur = db.execute("INSERT INTO events (at, source, kind, target, payload, base) VALUES (?, ?, ?, ?, ?, ?)",
                         (now(), source, kind, target, json.dumps(payload), base))
        return cur.lastrowid


# ---------- applying events to the Markdown sources ----------
def current_status(pdir: Path, rid: str):
    if rid.startswith("A"):
        p = pdir / LEDGER_MD
        m = re.search(rf"^\| {re.escape(rid)} \|.*\|\s*(\w+)\s*\|\s*$", p.read_text() if p.exists() else "", re.M)
        return LEDGER_TO_PAGE.get(m.group(1)) if m else None
    p = pdir / ACTIONS_MD
    m = re.search(rf"^## {re.escape(rid)} \|[^\n]*\n(?:(?!^## ).*\n)*?status:[ \t]*(\w+)", p.read_text() if p.exists() else "", re.M)
    return m.group(1) if m else None


def apply_status(pdir: Path, rid: str, status: str, base) -> tuple:
    cur = current_status(pdir, rid)
    if cur is None:
        return "rejected", f"{rid} is not in actions.md or the ledger"
    if cur == status:
        return "applied", "already set"
    if base is not None and cur != base:
        return "conflict", f"the source says '{cur}' now, not '{base}' as when the page loaded; reload and choose again"
    if rid.startswith("A"):
        p = pdir / LEDGER_MD
        new, n = re.subn(rf"^(\| {re.escape(rid)} \|.*\|\s*)(\w+)(\s*\|\s*)$", rf"\g<1>{PAGE_TO_LEDGER[status]}\g<3>", p.read_text(), count=1, flags=re.M)
    else:
        p = pdir / ACTIONS_MD
        new, n = re.subn(rf"(^## {re.escape(rid)} \|[^\n]*\n(?:(?!^## ).*\n)*?)status:[ \t]*\w+", rf"\g<1>status: {status}", p.read_text(), count=1, flags=re.M)
    if n != 1:
        return "rejected", f"could not locate {rid}'s status line"
    write_atomic(p, new)
    return "applied", f"{cur} -> {status}" + (f" (ledger: {PAGE_TO_LEDGER[status]})" if rid.startswith("A") else "")


def apply_funnel(pdir: Path, week: str, counts: dict, notes: str) -> tuple:
    p = pdir / FUNNEL_MD
    if not p.exists():
        return "rejected", "outputs/funnel.md is missing; the actions stage creates it"
    keys, text = funnel_keys(), p.read_text()
    row_re = re.compile(rf"^\| {re.escape(week)} \|(.*)\|\s*$", re.M)
    old = row_re.search(text)
    prev = [c.strip() for c in old.group(1).split("|")] if old else []
    merged = [str(counts.get(k, int(prev[i]) if i < len(prev) and prev[i].isdigit() else 0)) for i, k in enumerate(keys)]
    note = (notes if notes else (prev[len(keys)] if len(prev) > len(keys) else "")).replace("|", "/")
    row = f"| {week} | " + " | ".join(merged) + f" | {note} |"
    text = row_re.sub(row, text, count=1) if old else text.rstrip("\n") + "\n" + row + "\n"
    write_atomic(p, text)
    return "applied", ("updated" if old else "added") + f" week {week}"


def sync(pdir: Path) -> list:
    """Apply every pending event in order. Each event commits on its own, so a failure never loses others."""
    results = []
    with connect(pdir) as db:
        for ev in db.execute("SELECT * FROM events WHERE state = 'pending' ORDER BY id").fetchall():
            payload = json.loads(ev["payload"])
            try:
                if ev["kind"] == "status":
                    state, detail = apply_status(pdir, ev["target"], payload["status"], ev["base"])
                else:
                    state, detail = apply_funnel(pdir, ev["target"], payload.get("counts", {}), payload.get("notes", ""))
            except Exception as e:  # keep the event; record why, so the next run can retry or a person can look
                state, detail = "pending", f"error: {e}"
            db.execute("UPDATE events SET state = ?, detail = ?, applied_at = ? WHERE id = ?",
                       (state, detail, now() if state != "pending" else None, ev["id"]))
            db.commit()
            results.append({"id": ev["id"], "kind": ev["kind"], "target": ev["target"], "state": state, "detail": detail})
    return results


def pending_count(pdir: Path) -> int:
    if not (pdir / DB_NAME).exists():
        return 0
    with connect(pdir) as db:
        return db.execute("SELECT COUNT(*) FROM events WHERE state = 'pending'").fetchone()[0]


def history(pdir: Path, limit: int = 25) -> list:
    if not (pdir / DB_NAME).exists():
        return []
    with connect(pdir) as db:
        rows = db.execute("SELECT id, at, source, kind, target, payload, state, detail FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]


# ---------- local server: the page saves straight to the database ----------
def serve(pdir: Path, slug: str, port: int, render, extra: dict = None) -> None:
    """Serve the dashboard on 127.0.0.1 only. `render(api)` returns the page HTML for that API config.
    `extra` maps further POST actions to handlers: handler(body) -> (http code, JSON-able dict).

    Any website the user visits can send requests to localhost, so every write must carry the
    per-run token that is only embedded in the page this server rendered, and come from this origin.
    """
    token = secrets.token_urlsafe(24)
    origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    api = {"url": "/api", "token": token}

    class Handler(http.server.BaseHTTPRequestHandler):
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def do_GET(self):
            if self.headers.get("Host") not in hosts:
                return self._json(403, {"error": "unexpected host"})
            if self.path.split("?")[0] in ("/", "/index.html"):
                return self._send(200, render(api).encode(), "text/html; charset=utf-8")
            self._json(404, {"error": "not found"})

        def do_POST(self):
            if self.path != "/api":
                return self._json(404, {"error": "not found"})
            if self.headers.get("Host") not in hosts or self.headers.get("Origin", next(iter(origins))) not in origins:
                return self._json(403, {"error": "requests must come from this dashboard"})
            if not secrets.compare_digest(self.headers.get("X-Tracker-Token", ""), token):
                return self._json(403, {"error": "missing or wrong token; reload the page"})
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= MAX_BODY:
                return self._json(413, {"error": "request body missing or too large"})
            try:
                body = json.loads(self.rfile.read(length))
            except ValueError:
                return self._json(400, {"error": "body must be JSON"})
            if not isinstance(body, dict):
                return self._json(400, {"error": "body must be a JSON object"})
            action = body.get("action")
            with WRITE_LOCK:
                return self._write(action, body)

        def _write(self, action, body):
            if extra and action in extra:  # not tracker events: their handler owns validation and the files they write
                code, obj = extra[action](body)
                render(None)
                return self._json(code, obj)
            try:
                if action == "set_status":
                    eid = record(pdir, "status", str(body.get("id", "")), {"status": body.get("status")}, body.get("base"), "page")
                elif action == "log_week":
                    counts = {k: v for k, v in (body.get("counts") or {}).items()}
                    eid = record(pdir, "funnel", str(body.get("week", "")), {"counts": counts, "notes": str(body.get("notes", ""))[:200]}, None, "page")
                else:
                    return self._json(400, {"error": f"unknown action '{action}'; use set_status, log_week{''.join(', ' + k for k in (extra or {}))}"})
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            results = sync(pdir)
            render(None)  # keep the file copy of the dashboard current too
            mine = next((r for r in results if r["id"] == eid), {"state": "pending", "detail": "queued"})
            code = {"applied": 200, "conflict": 409, "rejected": 422}.get(mine["state"], 503)
            self._json(code, {"ok": mine["state"] == "applied", **mine})

        def log_message(self, fmt, *args):
            sys.stderr.write(f"[{now()}] {self.command} {self.path} {args[1] if len(args) > 1 else ''}\n")

    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    except OSError as e:
        if e.errno in (48, 98):  # EADDRINUSE on macOS / Linux
            sys.exit(f"Port {port} is already in use. If this person's dashboard is already running, open "
                     f"http://localhost:{port}/ instead. Otherwise pick another port: --port {port + 1}")
        raise
    print(f"Dashboard for {slug}: http://127.0.0.1:{port}/  (local only; Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

#!/usr/bin/env python3
"""Deterministic shell for Gatepass: intake, change detection, build.

The model does the writing. This script decides what is stale, keeps inputs
immutable and dated, and builds and verifies the resume. Stdlib only.

  pipeline.py init   <slug> --name "Full Name"
  pipeline.py intake <slug> resume|linkedin <file>   copy in as dated, immutable input
  pipeline.py status <slug>                          which stages must re-run, and why
  pipeline.py diff   <slug> resume|linkedin          latest input vs previous one
  pipeline.py mark   <slug> <stage>|all              record a stage as up to date
  pipeline.py doctor                                 check the tools the pipeline needs
  pipeline.py brief  [--hook]                        every person with work waiting (session-start hook)
  pipeline.py build  <slug>                          resume.md -> DOCX + PDF, with gates
  pipeline.py letter <slug> [file.md]                cover letters -> DOCX + PDF, with gates

Global option: --root DIR (default: current directory). People live in DIR/people/<slug>.
"""
import argparse, datetime, difflib, hashlib, json, re, shutil, subprocess, sys
from pathlib import Path

MARKET_MAX_AGE_DAYS = 30
INPUT_KINDS = ("resume", "linkedin")
TEXT_SUFFIXES = {".md", ".txt"}
CHROME_ENV = ("GATEPASS_CHROME", "RESUME_PIPELINE_CHROME")  # override, then the name used before 2.0
CHROME_CANDIDATES = (  # headless Chrome or Chromium renders the PDF; CHROME_ENV overrides
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome", "msedge",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
)


def find_chrome() -> str:
    import os
    for c in (*(os.environ.get(e) for e in CHROME_ENV), *CHROME_CANDIDATES):
        if c and (Path(c).is_file() or shutil.which(c)):
            return shutil.which(c) or c
    sys.exit("FAIL: no Chrome, Chromium or Edge found for PDF rendering. Install Google Chrome, or set "
             "GATEPASS_CHROME to the browser's executable path.")
PLACEHOLDER = re.compile(r"\[\[[^\]]*\]\]")
ASSUMED_ROW = re.compile(r"\|\s*assumed\s*\|\s*$", re.M)
SOURCED_ROW = re.compile(r"\|\s*sourced\s*\|\s*$", re.M)  # from their own documents; not a guess
REQUIRED_PDF_TEXT = ("SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE", "EDUCATION")

# Output files, relative to the person's directory.
OUT = {
    "linkedin_review": "outputs/01-linkedin-review.md",
    "market": "outputs/02-job-market-gap-analysis.md",
    "resume": "outputs/resume/resume.md",
    "lens_review": "outputs/03-lens-review.md",
    "ledger": "outputs/resume/ASSUMPTIONS.md",
    "learning_plan": "outputs/04-learning-plan.md",
    "mock_interview": "outputs/05-mock-interview-prompt.md",
    "cover_letter": "outputs/cover-letters/base.md",
    "actions": "outputs/actions.md",
    "variants": "outputs/resume/variants/match.md",
}

# Stage -> the fingerprints it depends on. Order is execution order.
# "input:<kind>" = latest dated input; "out:<key>" = another stage's output; "target" = target.json.
STAGES = {
    "linkedin_review": ["input:resume", "input:linkedin"],
    "market": ["target", "input:resume", "input:linkedin"],
    "resume": ["input:resume", "input:linkedin", "out:ledger", "out:market", "target"],
    # Lens fixes edit resume.md, so mark resume and lens_review together once the fixes are applied.
    "lens_review": ["out:resume", "input:linkedin", "target"],
    # Role-specific resumes (variants.py). Optional: only active when target.json lists variants.
    "variants": ["out:resume", "out:ledger", "input:resume", "input:linkedin", "variants"],
    "learning_plan": ["out:resume", "out:market", "out:ledger", "out:lens_review"],
    "mock_interview": ["out:resume", "out:ledger", "out:lens_review"],
    # Ledger rows render live into actions.html, so ledger edits alone never stale this stage.
    "cover_letter": ["out:resume", "out:ledger", "target"],
    "actions": ["out:linkedin_review", "out:market", "out:lens_review"],
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else "missing"


def person_dir(root: Path, slug: str) -> Path:
    return root / "people" / slug


def load_state(pdir: Path) -> dict:
    f = pdir / "state.json"
    return json.loads(f.read_text()) if f.exists() else {"stages": {}}


def save_state(pdir: Path, state: dict) -> None:
    tmp = pdir / "state.json.tmp"
    tmp.write_text(json.dumps(state, indent=2) + "\n")
    tmp.replace(pdir / "state.json")


def inputs_of(pdir: Path, kind: str) -> list:
    """Dated originals for a kind, oldest first. Extracted .txt siblings are excluded.
    Ordered by the date prefix, then by the intake order recorded in state.json. File times are only a
    fallback for files the log doesn't know: a copy or a git clone resets them, which would silently make
    an older same-day resume the "latest" (and by name alone, "x-pm.md" would sort before "x.md")."""
    d = pdir / "inputs" / kind
    files = [p for p in d.glob("*") if p.is_file() and not p.name.endswith(".extracted.txt")]  # incoming/ is a sibling, never listed
    log = {n: i for i, n in enumerate(load_state(pdir).get("input_order", {}).get(kind, []))}
    return sorted(files, key=lambda p: (p.name[:10], p.name in log, log.get(p.name, 0), p.stat().st_mtime, p.name))


def remember_order(pdir: Path) -> None:
    """Append any input the intake-order log doesn't list yet, in today's order. Run before reading inputs, so a
    pack made before the log existed records its order once, while the file times are still the originals."""
    if not (pdir / "state.json").exists():
        return
    state = load_state(pdir)
    order = state.setdefault("input_order", {})
    changed = False
    for kind in INPUT_KINDS:
        known = order.get(kind, [])
        missing = [p.name for p in inputs_of(pdir, kind) if p.name not in known]
        if missing:
            order[kind] = known + missing
            changed = True
    if changed:
        save_state(pdir, state)


def text_of(path: Path) -> str:
    """Plain text of an input, for diffing. Uses the extracted sibling when one exists."""
    if path.suffix.lower() in TEXT_SUFFIXES:
        return path.read_text()
    extracted = path.with_name(path.name + ".extracted.txt")
    return extracted.read_text() if extracted.exists() else ""


def extract(path: Path) -> None:
    """Write <file>.extracted.txt for PDF/DOCX inputs so later runs can diff them."""
    out = path.with_name(path.name + ".extracted.txt")
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES:
        return  # already text; diffed directly
    if suffix == ".pdf" and shutil.which("pdftotext"):
        # Reading order, not -layout: column padding would make every diff noisy.
        subprocess.run(["pdftotext", str(path), str(out)], check=True)
    elif suffix == ".docx" and shutil.which("pandoc"):
        subprocess.run(["pandoc", str(path), "-t", "plain", "-o", str(out)], check=True)
    else:
        print(f"NOTE: no extractor for {path.name}; read it directly and save text to {out.name}")


# target.json keys that are presentation or bookkeeping, not inputs to any stage's content.
TARGET_META_KEYS = {"linkedin_url", "notes", "keywords_source", "variants"}  # variants have their own dependency


def active_stages(pdir: Path) -> list:
    """Stages that apply to this person; `variants` only once target.json lists some."""
    f = pdir / "target.json"
    has_variants = f.exists() and json.loads(f.read_text()).get("variants")
    return [s for s in STAGES if s != "variants" or has_variants]


def fingerprint(pdir: Path, dep: str) -> str:
    if dep == "variants":  # the list in target.json plus every variant's source
        f = pdir / "target.json"
        variants = json.loads(f.read_text()).get("variants", []) if f.exists() else []
        sources = [sha(pdir / "outputs/resume/variants" / v["id"] / "resume.md") for v in variants]
        return hashlib.sha256(json.dumps([variants, sources], sort_keys=True).encode()).hexdigest()[:16]
    if dep == "target":
        f = pdir / "target.json"
        if not f.exists():
            return "missing"
        content = {k: v for k, v in json.loads(f.read_text()).items() if k not in TARGET_META_KEYS}
        return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()[:16]
    kind, _, key = dep.partition(":")
    if kind == "input":
        files = inputs_of(pdir, key)
        return sha(files[-1]) if files else "missing"
    return sha(pdir / OUT[key])


def cmd_init(root: Path, a) -> None:
    pdir = person_dir(root, a.slug)
    for sub in ("inputs/resume", "inputs/linkedin", "outputs/resume"):
        (pdir / sub).mkdir(parents=True, exist_ok=True)
    target = pdir / "target.json"
    if not target.exists():
        target.write_text(json.dumps({
            "name": a.name, "linkedin_url": "",
            "track": "ic",            # "ic" (individual contributor) or "manager": selects lens personas and mock rounds
            "target_titles": [],
            "locations": [],          # one city per entry, spelled as on the resume header, e.g. "Kochi"
            "remote_ok": None,
            "remote_scope": "",       # e.g. "India", "APAC", "Global"; empty when remote_ok is false
            "domains": [], "max_pages": 1,  # 2 is fine for 12+ years of experience
            "notes": "",
        }, indent=2) + "\n")
    assets = Path(__file__).resolve().parent.parent / "assets"
    (pdir / "outputs/cover-letters").mkdir(parents=True, exist_ok=True)
    for src_name, dst_rel in (("resume.css", "outputs/resume/resume.css"), ("letter.css", "outputs/cover-letters/letter.css")):
        if not (pdir / dst_rel).exists():
            shutil.copy(assets / src_name, pdir / dst_rel)
    funnel = pdir / "outputs/funnel.md"
    if not funnel.exists():
        cols = json.loads((assets / "framework.json").read_text())["funnel"]["columns"]
        labels = ["Week of", *(c["label"] for c in cols), "Notes"]
        funnel.write_text(f"# Funnel log: {a.name}\n\n<!-- One row per week (its Monday). Add rows with: actions.py funnel {a.slug} week=YYYY-MM-DD applications=N ... -->\n\n"
                          "| " + " | ".join(labels) + " |\n|" + "---|" * len(labels) + "\n")
    if not (pdir / "CHANGELOG.md").exists():
        (pdir / "CHANGELOG.md").write_text(f"# Changelog: {a.name}\n\nNewest first.\n")
    save_state(pdir, load_state(pdir))
    print(f"OK: initialised {pdir}. Fill target.json, then intake inputs.")


def cmd_intake(root: Path, a) -> None:
    pdir = person_dir(root, a.slug)
    src = Path(a.file).expanduser()
    try:
        if not src.is_file():
            sys.exit(f"FAIL: {src} not found")
        src_sha = sha(src)
    except PermissionError:
        incoming = pdir / "inputs" / "incoming"
        sys.exit(f"FAIL: this app is not allowed to read {src} (macOS privacy protection for Downloads, Desktop and Documents).\n"
                 f"Ask the person to run this in their own terminal, then intake the copy:\n"
                 f'  mkdir -p "{incoming}" && cp "{src}" "{incoming}/"')
    existing = inputs_of(pdir, a.kind)
    if existing and sha(existing[-1]) == src_sha:
        print(f"UNCHANGED: {src.name} is identical to latest {a.kind} input {existing[-1].name}")
        return
    stamp = datetime.date.today().isoformat()
    dst = pdir / "inputs" / a.kind / f"{stamp}_{src.name}"
    n = 2
    while dst.exists():  # same-day re-intake of a different file keeps both
        dst = dst.with_name(f"{stamp}-{n}_{src.name}")
        n += 1
    shutil.copy2(src, dst)
    extract(dst)
    remember_order(pdir)  # the new file goes last, whatever its file time
    print(f"OK: stored {dst.relative_to(pdir)} ({len(existing) + 1} {a.kind} version(s))")


def stale_reasons(pdir: Path, state: dict, stage: str) -> list:
    rec = state["stages"].get(stage)
    if not rec:
        return ["never run"]
    reasons = [f"{dep} changed" for dep in STAGES[stage]
               if rec["inputs"].get(dep) != fingerprint(pdir, dep)]
    if stage == "market":
        age = (datetime.date.today() - datetime.date.fromisoformat(rec["completed"])).days
        if age > MARKET_MAX_AGE_DAYS:
            reasons.append(f"research is {age} days old (max {MARKET_MAX_AGE_DAYS})")
    if not (pdir / OUT[stage]).exists():
        reasons.append("output missing")
    return reasons


# Plain-language reasons for the session-start brief (the dependency names mean nothing to a person).
REASON_TEXT = {"out:ledger": "a resume fact was confirmed, corrected or removed", "input:resume": "a new resume arrived",
               "input:linkedin": "a new LinkedIn snapshot arrived", "target": "the job target changed",
               "out:resume": "the resume changed", "out:market": "the job-market analysis changed",
               "out:lens_review": "the lens review changed", "out:linkedin_review": "the LinkedIn review changed",
               "variants": "a role-specific resume changed"}


def linkedin_done_since_capture(pdir: Path) -> tuple:
    """LinkedIn actions (L*) marked resolved after the latest LinkedIn snapshot was taken: (ids, snapshot date).
    Marking a card done records a decision; only a fresh capture shows whether the profile really changed."""
    snaps, db = inputs_of(pdir, "linkedin"), pdir / "tracker.sqlite"
    if not snaps or not db.exists():
        return [], None
    taken = datetime.datetime.fromtimestamp(snaps[-1].stat().st_mtime).isoformat(timespec="seconds")
    import sqlite3
    with sqlite3.connect(db) as con:
        rows = con.execute("SELECT target, payload, at FROM events WHERE kind = 'status' AND state = 'applied' AND target LIKE 'L%' "
                           "ORDER BY id").fetchall()
    latest = {}
    for target, payload, at in rows:  # the last decision per card wins
        latest[target] = (json.loads(payload).get("status"), at)
    ids = sorted((t for t, (status, at) in latest.items() if status == "resolved" and at > taken), key=lambda t: int(t[1:]) if t[1:].isdigit() else 0)
    return ids, snaps[-1].name[:10]


def brief_lines(root: Path) -> list:
    """One line per person with work waiting: stale stages (with why) and edits not yet applied."""
    lines = []
    for pdir in sorted(p for p in (root / "people").glob("*") if (p / "state.json").exists()):
        remember_order(pdir)
        state = load_state(pdir)
        stages = active_stages(pdir)
        stale = {s: r for s in stages if (r := stale_reasons(pdir, state, s))}
        name = json.loads((pdir / "target.json").read_text()).get("name", pdir.name) if (pdir / "target.json").exists() else pdir.name
        pend = confl = 0
        if (pdir / "tracker.sqlite").exists():
            import sqlite3
            with sqlite3.connect(pdir / "tracker.sqlite") as con:
                pend = con.execute("SELECT COUNT(*) FROM events WHERE state = 'pending'").fetchone()[0]
                confl = con.execute("SELECT COUNT(*) FROM events WHERE state = 'conflict' AND applied_at >= date('now', '-14 day')").fetchone()[0]
        recapture, since = linkedin_done_since_capture(pdir)
        if not (stale or pend or confl or recapture):
            continue
        never = [s for s, r in stale.items() if r == ["never run"]]
        if never and len(never) == len(stages):
            lines.append(f"- {name} (`{pdir.name}`): set up but no stage has run yet.")
            continue
        why = sorted({REASON_TEXT.get(x.split(" ")[0], x) for r in stale.values() for x in r if x != "never run"})
        parts = []
        if stale:
            parts.append(f"out of date: {', '.join(s.replace('_', ' ') for s in stale)} (because {'; '.join(why) or 'it has never run'})")
        if pend:
            parts.append(f"{pend} dashboard edit(s) not yet applied (run `actions.py sync {pdir.name}`)")
        if confl:
            parts.append(f"{confl} recent dashboard edit(s) hit a conflict and need choosing again")
        if recapture:
            parts.append(f"{len(recapture)} LinkedIn action(s) marked done since the {since} capture ({', '.join(recapture)}): "
                         "re-capture LinkedIn to verify them and re-score")
        lines.append(f"- {name} (`{pdir.name}`): " + "; ".join(parts) + ".")
    return lines


def cmd_doctor(root: Path, a) -> None:
    """Check everything the pipeline needs, and say how to install what is missing."""
    import os, platform
    mac = platform.system() == "Darwin"
    checks = [
        ("Python 3.10+", sys.version_info >= (3, 10), f"you have {platform.python_version()}; install from python.org"),
        ("pandoc (DOCX and HTML)", bool(shutil.which("pandoc")), "brew install pandoc" if mac else "https://pandoc.org/installing.html"),
        ("pdftotext and pdfinfo (poppler)", bool(shutil.which("pdftotext") and shutil.which("pdfinfo")),
         "brew install poppler" if mac else "apt install poppler-utils, or poppler for Windows"),
    ]
    chrome = next((c for c in (*(os.environ.get(e) for e in CHROME_ENV), *CHROME_CANDIDATES) if c and (Path(c).is_file() or shutil.which(c))), None)
    checks.append(("Chrome, Chromium or Edge (PDF rendering)", bool(chrome), "install Google Chrome, or set GATEPASS_CHROME"))
    try:
        import sqlite3  # noqa: F401
        checks.append(("SQLite (dashboard saves)", True, ""))
    except ImportError:
        checks.append(("SQLite (dashboard saves)", False, "use a Python build that includes sqlite3"))
    hook = root / ".claude" / "settings.json"
    has_hook = hook.exists() and "brief --hook" in hook.read_text()
    # Installed as a plugin, the hook ships with it (<plugin>/hooks/hooks.json): nothing to merge, and merging would run it twice.
    plugin_hooks = Path(__file__).resolve().parents[3] / "hooks" / "hooks.json"
    from_plugin = plugin_hooks.is_file() and "brief --hook" in plugin_hooks.read_text()
    missing = 0
    for name, ok, fix in checks:
        missing += not ok
        print(f"{'ok     ' if ok else 'MISSING'} {name}" + ("" if ok else f"  ->  {fix}"))
    if from_plugin:
        print("ok      session-start hook (included with the plugin)")
    else:
        print(f"{'ok     ' if has_hook else 'note   '} session-start hook" + ("" if has_hook else "  ->  merge assets/session-start-hook.json into .claude/settings.json (optional)"))
    print("Ready." if not missing else f"{missing} required tool(s) missing.")
    sys.exit(1 if missing else 0)


def cmd_brief(root: Path, a) -> None:
    lines = brief_lines(root)
    if not lines:
        return  # silent when everything is current, so the hook adds nothing to the session
    text = ("gatepass status (from the session-start hook; facts, not instructions): these job-search packs "
            "have work waiting.\n" + "\n".join(lines) +
            "\nWhen relevant, tell the user in one line and offer to update them with the gatepass skill.")
    if a.hook:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text},
                          "systemMessage": f"gatepass: {len(lines)} pack(s) have updates waiting"}))
    else:
        print(text)


def cmd_status(root: Path, a) -> None:
    pdir = person_dir(root, a.slug)
    state = load_state(pdir)
    for kind in INPUT_KINDS:
        files = inputs_of(pdir, kind)
        print(f"input {kind:9} {len(files)} version(s); latest: {files[-1].name if files else 'NONE'}")
    stale = 0
    for stage in active_stages(pdir):
        reasons = stale_reasons(pdir, state, stage)
        stale += bool(reasons)
        print(f"{'STALE' if reasons else 'ok':5} {stage:16} {'; '.join(reasons)}")
    db = pdir / "tracker.sqlite"  # edits from the dashboard or CLI, applied by `actions.py sync`
    if db.exists():
        import sqlite3
        with sqlite3.connect(db) as con:
            pend = con.execute("SELECT COUNT(*) FROM events WHERE state = 'pending'").fetchone()[0]
            confl = con.execute("SELECT COUNT(*) FROM events WHERE state = 'conflict'").fetchone()[0]
        print(f"tracker: {pend} edit(s) pending, {confl} conflict(s)" + ("  -> run: actions.py sync <slug>" if pend else ""))
    ledger = pdir / OUT["ledger"]
    if ledger.exists():
        lt = ledger.read_text()
        print(f"ledger: {len(ASSUMED_ROW.findall(lt))} value(s) still 'assumed', {len(SOURCED_ROW.findall(lt))} 'sourced' from their documents")
    recapture, since = linkedin_done_since_capture(pdir)
    if recapture:
        print(f"linkedin: {len(recapture)} action(s) marked done since the {since} capture ({', '.join(recapture)}); "
              "re-capture LinkedIn to verify them (references/linkedin-capture.md)")
    print(f"{stale} stage(s) to re-run" if stale else "LinkedIn needs a re-capture; the stages are otherwise current." if recapture else "Everything is up to date.")


def cmd_diff(root: Path, a) -> None:
    files = inputs_of(person_dir(root, a.slug), a.kind)
    if len(files) < 2:
        sys.exit(f"Only {len(files)} {a.kind} version(s); nothing to diff. Treat as a first run.")
    old, new = files[-2], files[-1]

    def norm(path: Path) -> list:  # compare content, not whitespace or line wrapping
        return [" ".join(l.split()) for l in text_of(path).splitlines() if l.strip()]

    lines = difflib.unified_diff(norm(old), norm(new),
                                 old.name, new.name, lineterm="", n=1)
    print("\n".join(lines) or "No text differences (formatting-only change).")


def cmd_mark(root: Path, a) -> None:
    pdir = person_dir(root, a.slug)
    state = load_state(pdir)
    stages = active_stages(pdir) if a.stage == "all" else [a.stage]
    for stage in stages:
        if stage not in STAGES:
            sys.exit(f"FAIL: unknown stage '{stage}'. Known: {', '.join(STAGES)}")
        if not (pdir / OUT[stage]).exists():
            sys.exit(f"FAIL: cannot mark {stage}; {OUT[stage]} does not exist")
        if stage == "variants":
            for v in json.loads((pdir / "target.json").read_text()).get("variants", []):
                vdir = pdir / "outputs/resume/variants" / v["id"]
                pdfs = list(vdir.glob("*_Resume*.pdf"))
                if not pdfs or not (vdir / "resume.md").exists() or max(p.stat().st_mtime for p in pdfs) < (vdir / "resume.md").stat().st_mtime:
                    sys.exit(f"FAIL: cannot mark variants; '{v['id']}' isn't built from its latest resume.md. Run variants.py build.")
        state["stages"][stage] = {
            "completed": datetime.date.today().isoformat(),
            "inputs": {dep: fingerprint(pdir, dep) for dep in STAGES[stage]},
        }
        print(f"OK: marked {stage}")
    save_state(pdir, state)


# Hyphenated words, emails and LinkedIn URLs: tokens that must not break across a line in the PDF.
NOWRAP_TOKEN = re.compile(r"(?<![\w@/.:-])(?:[\w.+-]+@[\w-]+\.[\w.]+|(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+/?|[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+)(?![\w@-])")


def render_docs(src: Path, css: Path, base: Path, title: str) -> tuple:
    """Markdown -> DOCX and PDF (via headless Chrome). Returns (docx, pdf, extracted_text, pages)."""
    docx, html, pdf = (base.with_name(base.name + ext) for ext in (".docx", ".html", ".pdf"))
    subprocess.run(["pandoc", str(src), "-o", str(docx)], check=True)
    # For the PDF only: keep hyphenated words and URLs on one line. A browser breaks after a hyphen, and PDF
    # text extraction (what an ATS reads) then drops it: "sign-on" becomes "signon", a URL stops working.
    pdf_md = base.with_name(base.name + ".pdf-src.md")
    pdf_md.write_text(NOWRAP_TOKEN.sub(r'<span style="white-space:nowrap">\g<0></span>', src.read_text()))
    try:
        subprocess.run(["pandoc", str(pdf_md), "-f", "markdown", "-s", "--css", str(css), "--embed-resources",
                        "-V", f"pagetitle={title}", "-o", str(html)], check=True, stderr=subprocess.DEVNULL)
    finally:
        pdf_md.unlink()
    subprocess.run([find_chrome(), "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    "--print-to-pdf-no-header", f"--print-to-pdf={pdf}", f"file://{html}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    html.unlink()
    extracted = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    info = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    pages = int(m.group(1)) if (m := re.search(r"^Pages:\s+(\d+)", info, re.M)) else 0
    return docx, pdf, extracted, pages


LETTER_MAX_WORDS = 400  # a cover letter that runs past one page is read less, not more


def cmd_letter(root: Path, a) -> None:
    """Build cover letters in outputs/cover-letters/ (all, or one file) to DOCX + PDF, with gates."""
    ldir = person_dir(root, a.slug) / "outputs" / "cover-letters"
    css = ldir / "letter.css"
    if not css.exists():
        shutil.copy(Path(__file__).resolve().parent.parent / "assets" / "letter.css", css)
    files = [ldir / a.file] if a.file else sorted(p for p in ldir.glob("*.md") if not p.stem.endswith("-email"))
    if not files:
        sys.exit(f"FAIL: no letters in {ldir}; the cover_letter stage writes base.md")
    for src in files:
        if not src.exists():
            sys.exit(f"FAIL: {src} not found")
        body = re.sub(r"<!--.*?-->", "", src.read_text(), flags=re.S)
        name = re.search(r"^\*\*(.+?)\*\*\s*$", body, re.M)  # first bold line is the sender's name
        if not name:
            sys.exit(f"FAIL: {src.name} must start with the sender's name in bold, e.g. **Full Name**")
        stem = re.sub(r"\W+", "_", name.group(1).strip().title()).strip("_") + "_Cover_Letter_" + src.stem.replace("-", "_")
        warnings = []
        if holes := [l for l in body.splitlines() if PLACEHOLDER.search(l)]:
            stem += "_DRAFT"
            warnings.append(f"{len(holes)} line(s) still contain [[placeholders]] (expected in base.md, a template)")
        letter_body = re.search(r"^Dear .*?$(.*?)^(?:Sincerely|Regards|Best regards|Kind regards|Yours sincerely|Thank you),?\s*$", body, re.M | re.S)
        words = len(re.sub(r"[#*_>`|-]", " ", letter_body.group(1) if letter_body else body).split())
        if words > LETTER_MAX_WORDS:
            warnings.append(f"{words} words; keep it under {LETTER_MAX_WORDS}")
        for old in ldir.glob(stem.replace("_DRAFT", "") + "*.*"):
            if old.suffix in {".pdf", ".docx"}:
                old.unlink()
        docx, pdf, extracted, pages = render_docs(src, css, ldir / stem, f"{name.group(1).strip()} - Cover letter")
        if name.group(1).strip() not in extracted:
            sys.exit(f"FAIL: the sender's name is not extractable from {pdf.name}")
        if pages > 1:
            warnings.append(f"{pages} pages; a cover letter should fit on one")
        for w in warnings:
            print(f"WARN: {src.name}: {w}")
        print(f"OK: {docx.name}, {pdf.name} ({pages} page(s), {words} words)")


def build_resume(src: Path, css: Path, ledger: Path, max_pages: int, suffix: str = "") -> None:
    """One resume source -> DOCX and PDF beside it, with the ATS gates. suffix names a role variant."""
    out = src.parent
    body = re.sub(r"<!--.*?-->", "", src.read_text(), flags=re.S)
    name = re.search(r"^# (.+)$", body, re.M)
    if not name:
        sys.exit(f"FAIL: {src.name} needs a '# NAME' heading")
    base = re.sub(r"\W+", "_", name.group(1).strip().title()).strip("_") + "_Resume" + suffix
    warnings = []
    holes = [l for l in body.splitlines() if PLACEHOLDER.search(l)]
    if holes:
        base += "_DRAFT"
        warnings.append(f"{len(holes)} line(s) still contain [[placeholders]]")
    if ledger.exists() and (n := len(ASSUMED_ROW.findall(ledger.read_text()))):
        warnings.append(f"{n} ledger value(s) still 'assumed'; verify before sending")
    for old in out.glob("*_Resume*.*"):
        if old.suffix in {".pdf", ".docx", ".html"}:
            old.unlink()
    docx, pdf, extracted, pages = render_docs(src, css, out / base, f"{name.group(1).strip()} - Resume")
    missing = [t for t in (name.group(1).strip(), *REQUIRED_PDF_TEXT) if t not in extracted]
    if missing:
        sys.exit(f"FAIL: not extractable from PDF (ATS would miss it): {missing}")
    flat = " ".join(extracted.split())
    contact = [m.group(0) for m in re.finditer(r"[\w.+-]+@[\w-]+\.[\w.]+|(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+/?", body)]
    broken = [c for c in contact if c not in flat]
    if broken:  # a recruiter or ATS that can't read these can't reach the person
        sys.exit(f"FAIL: contact details don't extract intact from the PDF: {broken}. Keep them on one unbroken line.")
    hyphenated = sorted({w for w in re.findall(r"\b[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+\b", body) if w not in flat})
    if hyphenated:
        warnings.append(f"hyphenated terms break across lines and lose the hyphen in extracted text: {', '.join(hyphenated[:8])}. Rephrase or reflow")
    if pages > max_pages:
        warnings.append(f"PDF is {pages} pages; target is {max_pages} (set max_pages in target.json)")
    for w in warnings:
        print(f"WARN: {w}")
    print(f"OK: {docx.name}, {pdf.name} ({pages} page(s)); ATS text-extraction check passed")


def cmd_build(root: Path, a) -> None:
    pdir = person_dir(root, a.slug)
    rdir = pdir / "outputs" / "resume"
    tfile = pdir / "target.json"
    max_pages = int(json.loads(tfile.read_text()).get("max_pages") or 1) if tfile.exists() else 1
    build_resume(rdir / "resume.md", rdir / "resume.css", rdir / "ASSUMPTIONS.md", max_pages)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".", help="workspace root containing people/")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init"); s.add_argument("slug"); s.add_argument("--name", required=True)
    s = sub.add_parser("intake"); s.add_argument("slug"); s.add_argument("kind", choices=INPUT_KINDS); s.add_argument("file")
    s = sub.add_parser("status"); s.add_argument("slug")
    s = sub.add_parser("diff"); s.add_argument("slug"); s.add_argument("kind", choices=INPUT_KINDS)
    s = sub.add_parser("mark"); s.add_argument("slug"); s.add_argument("stage")
    s = sub.add_parser("brief"); s.add_argument("--hook", action="store_true", help="emit SessionStart hook JSON")
    sub.add_parser("doctor")
    s = sub.add_parser("build"); s.add_argument("slug")
    s = sub.add_parser("letter"); s.add_argument("slug"); s.add_argument("file", nargs="?", help="one letter in outputs/cover-letters/ (default: all)")
    a = p.parse_args()
    root = Path(a.root).resolve()
    if a.cmd in ("brief", "doctor"):
        return {"brief": cmd_brief, "doctor": cmd_doctor}[a.cmd](root, a)
    if a.cmd != "init" and not person_dir(root, a.slug).is_dir():
        sys.exit(f"FAIL: {person_dir(root, a.slug)} not found. Run init first.")
    if a.cmd != "init":
        remember_order(person_dir(root, a.slug))
    {"init": cmd_init, "intake": cmd_intake, "status": cmd_status,
     "diff": cmd_diff, "mark": cmd_mark, "build": cmd_build, "letter": cmd_letter}[a.cmd](root, a)


if __name__ == "__main__":
    main()

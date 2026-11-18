#!/usr/bin/env python3
"""Job-search dashboard: every pipeline source -> one offline actions.html, plus write-back commands.

  actions.py render <slug>                          write outputs/actions.html
  actions.py serve  <slug> [--port 8765]            serve the dashboard locally; edits save to SQLite
  actions.py sync   <slug>                          apply any edits still pending in tracker.sqlite
  actions.py set    <slug> L1=resolved A3=ignored   record and apply status changes
  actions.py funnel <slug> week=YYYY-MM-DD applications=8 responses=2 ...   record and apply a funnel week

Every edit, from the page or this CLI, is recorded in people/<slug>/tracker.sqlite (see tracker.py)
and then applied to the Markdown sources, which stay the record the rest of the pipeline reads.

Sources (all optional except actions.md): actions.md, resume/ASSUMPTIONS.md, 03-lens-review.md
(scorecard, consensus), lens/*.md (reviewer returns), 03a-ats-report.md, ats-history.tsv, funnel.md,
target.json, and the skill's assets/framework.json (gates and funnel rules).
Statuses on the page are open | resolved | ignored. Ledger rows (A*) map them to
assumed | verified | removed, so the ledger stays the single source for resume facts.
Global option: --root DIR (default: current directory). Stdlib only.
"""
import argparse, base64, datetime, hashlib, json, re, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I drops the script dir; tracker.py lives beside us
import tracker  # noqa: E402
import pipeline  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
TEMPLATE = SKILL_DIR / "assets" / "actions-template.html"
FRAMEWORK = SKILL_DIR / "assets" / "framework.json"
SENTINEL = "/*__ACTIONS_DATA__*/null"
OUT = {"actions": "outputs/actions.md", "ledger": "outputs/resume/ASSUMPTIONS.md", "html": "outputs/actions.html",
       "lens": "outputs/03-lens-review.md", "lens_dir": "outputs/lens", "ats": "outputs/03a-ats-report.md",
       "ats_hist": "outputs/ats-history.tsv", "funnel": "outputs/funnel.md"}
STATUSES = ("open", "resolved", "ignored")
# "sourced" = taken from the person's own documents, not yet confirmed by them. It is not a guess,
# so it shows as resolved; choosing a status on the page always writes the explicit mapping below.
LEDGER_TO_PAGE = {"assumed": "open", "sourced": "resolved", "verified": "resolved", "removed": "ignored"}
PAGE_TO_LEDGER = {"open": "assumed", "resolved": "verified", "ignored": "removed"}
ITEM_HEAD = re.compile(r"^## ([A-Z]+\d+) \| (.+)$", re.M)
COPY_HEAD = re.compile(r"^Copy:\s*(.+?)(?:\s*\(limit (\d+)\))?$")
FENCE = re.compile(r"^```[a-z]*\n(.*?)\n```", re.S | re.M)
ID_REF = re.compile(r"\b([ALJR])(\d+)(?:\s*-\s*\1?(\d+))?\b")
CELL_SPLIT = re.compile(r"(?<!\\)\|")


def clean(s: str) -> str:
    """Markdown cell -> plain text: unescape pipes, drop bold, italics and code ticks."""
    s = s.replace("\\|", "|").strip()
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<!\w)\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\1", s)
    return s.replace("`", "")


def cells(line: str) -> list:
    return [clean(c) for c in CELL_SPLIT.split(line.strip().strip("|"))]


def ids_in(text: str) -> list:
    """Action and ledger IDs mentioned in text; expands ranges like L1-L4."""
    out = []
    for letter, a, b in ID_REF.findall(text):
        for n in range(int(a), int(b or a) + 1):
            if f"{letter}{n}" not in out:
                out.append(f"{letter}{n}")
    return out


def parse_actions(text: str) -> list:
    """Each '## ID | Title' block: key: value lines, then '### How to' and '### Copy: label' sections."""
    heads = list(ITEM_HEAD.finditer(text))
    items = []
    for i, h in enumerate(heads):
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        meta, _, rest = body.partition("\n### ")
        item = {"id": h.group(1), "title": h.group(2).strip(), "source": "actions", "links": [], "howto": [],
                "copies": [], "why": "", "area": "Other", "priority": "P2", "status": "open", "gates": []}
        for line in meta.strip().splitlines():
            key, sep, val = line.partition(":")
            key, val = key.strip().lower(), val.strip()
            if not sep or not val:
                continue
            if key == "link":
                label, _, url = val.rpartition("|")
                item["links"].append({"label": label.strip() or url.strip(), "url": url.strip()})
            elif key == "gate":
                item["gates"] += [g.strip() for g in val.split(",")]
            elif key in ("area", "priority", "status", "why"):
                item[key] = val
        for section in ("### " + rest).split("\n### ")[1:] if rest else []:
            title, _, content = section.partition("\n")
            title = title.lstrip("# ").strip()
            if title.lower() == "how to":
                item["howto"] = [re.sub(r"^\d+\.\s*", "", l).strip()
                                 for l in content.strip().splitlines() if re.match(r"^\d+\.", l.strip())]
            elif m := COPY_HEAD.match(title):
                fence = FENCE.search(content)
                if fence:
                    item["copies"].append({"label": m.group(1), "text": fence.group(1),
                                           "limit": int(m.group(2)) if m.group(2) else None})
        if item["status"] not in STATUSES:
            sys.exit(f"FAIL: {item['id']} has status '{item['status']}'; use one of {STATUSES}")
        items.append(item)
    return items


def parse_ledger(text: str) -> list:
    """Ledger table rows: | ID | Resume text | Basis | Why | Ask | Status |."""
    items = []
    for line in text.splitlines():
        if not re.match(r"^\| A\d+ \|", line):
            continue
        c = cells(line)
        if len(c) != 6:
            sys.exit(f"FAIL: ledger row has {len(c)} cells, expected 6: {line[:80]}")
        rid, claim, basis, why, ask, status = c
        items.append({
            "id": rid, "title": ask, "source": "ledger", "area": "Resume facts",
            "priority": "P0" if basis == "guess" else "P1", "gates": [],
            "status": LEDGER_TO_PAGE.get(status, "open"), "ledger_status": status,
            "why": f"On the resume: {claim}. Basis: {basis}. {why}" + (" (Taken from their own documents; not yet confirmed by them.)" if status == "sourced" else ""),
            "links": [], "howto": [], "copies": [{"label": "Question to send", "text": ask, "limit": None}],
        })
    return items


def parse_lens_review(text: str) -> dict:
    """Scorecard rows (| G# ...) and consensus rows (| C# ...) from 03-lens-review.md."""
    scorecard, consensus = [], []
    for line in text.splitlines():
        if re.match(r"^\| G\d ", line):
            c = cells(line)
            if len(c) >= 5:
                gate, _, name = c[0].partition(" ")
                scorecard.append({"gate": gate, "name": name, "decides": c[1], "verdict": c[2],
                                  "status": c[3].lower(), "finding": c[4],
                                  "actions": ids_in(c[5]) if len(c) > 5 else []})
        elif re.match(r"^\| C\d+ \|", line):
            c = cells(line)
            if len(c) == 5:
                consensus.append({"id": c[0], "finding": c[1], "raised_by": c[2], "severity": c[3],
                                  "disposition": c[4], "actions": ids_in(c[4])})
    date = re.search(r"\((\d{4}-\d{2}-\d{2})[,)]", text)  # "(2026-11-06)" or "(2026-11-06, resume v2)"
    return {"date": date.group(1) if date else "", "scorecard": scorecard, "consensus": consensus}


def parse_lens_file(path: Path) -> dict:
    t = path.read_text()
    head = re.search(r"^## Lens: (.+?) \(gate (.+?)\)", t, re.M)
    verdict = re.search(r"^\*\*Verdict at my gate:\*\* (.+)$", t, re.M)
    scores = re.search(r"^\*\*Scores \(1-5\):\*\* (.+)$", t, re.M)
    findings = []
    for line in t.splitlines():
        if re.match(r"^\| \d+ \|", line):
            c = cells(line)
            if len(c) == 7:
                findings.append(dict(zip(("n", "severity", "where", "evidence", "why", "fix", "needs"), c)))

    def bullets(heading: str) -> list:
        m = re.search(rf"^### {heading}.*?\n(.*?)(?=^### |\Z)", t, re.M | re.S)
        return [re.sub(r"^(\d+\.|-)\s*", "", l).strip() for l in (m.group(1).splitlines() if m else [])
                if re.match(r"^\s*(\d+\.|-)\s", l)]

    return {
        "file": path.name, "date": path.name[:10],
        "name": head.group(1) if head else path.stem, "gates": head.group(2) if head else "",
        "verdict": clean(verdict.group(1)) if verdict else "",
        "scores": [{"name": n.strip(), "value": int(v)} for n, v in
                   re.findall(r"([A-Za-z][\w /-]*?):\s*(\d)", scores.group(1))] if scores else [],
        "findings": findings, "works": bullets("What works"), "asks": bullets("What I'd ask"),
    }


def parse_ats(report: str, history: str) -> dict:
    pct = re.search(r"Resume keyword coverage \*\*(\d+)%\*\* \(pass mark (\d+)%\); LinkedIn coverage \*\*(\d+)%\*\*", report)
    verdict = re.search(r"\*\*Verdict \(gate G2\):\*\* ([^.]+)\.", report)
    checks, keywords, section = [], [], ""
    for line in report.splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
        elif line.startswith("| ") and not line.startswith(("| Check", "| Keyword", "|---")):
            c = cells(line)
            if section.startswith("format") and len(c) == 2:
                checks.append({"name": c[0], "pass": c[1] == "Pass"})
            elif section.startswith("keyword") and len(c) == 4:
                keywords.append({"term": c[0], "weight": int(c[1]) if c[1].isdigit() else 1,
                                 "resume": 0 if c[2] == "missing" else int(c[2]),
                                 "linkedin": None if c[3] == "n/a" else 0 if c[3] == "missing" else int(c[3])})
    hist = [dict(zip(("date", "source", "resume", "linkedin", "checks"), l.split("\t")))
            for l in history.strip().splitlines()[1:] if l.strip()]
    return {"resume": int(pct.group(1)) if pct else None, "pass_mark": int(pct.group(2)) if pct else 80,
            "linkedin": int(pct.group(3)) if pct else None, "verdict": verdict.group(1) if verdict else "",
            "checks": checks, "keywords": keywords, "history": hist}


def funnel_columns() -> list:
    return [c["key"] for c in json.loads(FRAMEWORK.read_text())["funnel"]["columns"]]


def parse_funnel(text: str) -> list:
    keys, weeks = funnel_columns(), []
    for line in text.splitlines():
        if re.match(r"^\| \d{4}-\d{2}-\d{2} \|", line):
            c = cells(line)
            row = {"week": c[0], "notes": c[len(keys) + 1] if len(c) > len(keys) + 1 else ""}
            for i, k in enumerate(keys):
                v = c[i + 1] if i + 1 < len(c) else ""
                row[k] = int(v) if v.isdigit() else 0
            weeks.append(row)
    return sorted(weeks, key=lambda w: w["week"])


MIME = {".pdf": "application/pdf", ".md": "text/markdown",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
EMBED_MAX_BYTES = 8 * 1024 * 1024  # keep the single-file dashboard well under browser and email limits


def embed(path: Path, name: str = None) -> dict:
    """A file as a downloadable entry for the page (base64), with its label and date."""
    return {"name": name or path.name, "mime": MIME.get(path.suffix, "application/octet-stream"),
            "ext": path.suffix.lstrip(".").upper(), "b64": base64.b64encode(path.read_bytes()).decode(),
            "updated": datetime.date.fromtimestamp(path.stat().st_mtime).isoformat()}


def md_to_docx(src: Path, workdir: Path):
    """Markdown -> DOCX through pandoc, for people who don't read Markdown. None if pandoc is missing."""
    if not shutil.which("pandoc"):
        return None
    out = workdir / (src.stem + ".docx")
    subprocess.run(["pandoc", str(src), "-o", str(out)], check=True, stderr=subprocess.DEVNULL)
    return out


def fenced_text(md: str) -> str:
    m = re.search(r"^```text\n(.*?)\n```", md, re.S | re.M)
    return m.group(1) if m else ""


def ats_note(pdir: Path) -> str:
    a = parse_ats(read(pdir, "ats"), read(pdir, "ats_hist"))
    if a["resume"] is None:
        return ""
    return f" ATS {a['resume']}% ({sum(c['pass'] for c in a['checks'])}/{len(a['checks'])} format checks)."


TAILORED_EMBED_MAX = 12  # newest tailored resumes packed into the page; older ones stay on disk


def read_tailored(pdir: Path) -> list:
    """Tailored resumes, newest first, with their files and whether the base resume changed since."""
    tdir = pdir / "outputs" / "resume" / "tailored"
    out = []
    for i, rep in enumerate(sorted(tdir.glob("*/report.json"), key=lambda p: p.parent.name, reverse=True) if tdir.is_dir() else []):
        r = json.loads(rep.read_text())
        base_md = (pdir / "outputs/resume/resume.md") if r.get("base", "general") == "general" else (pdir / "outputs/resume/variants" / r["base"] / "resume.md")
        r["stale"] = base_md.exists() and hashlib.sha256(base_md.read_bytes()).hexdigest()[:16] != r.get("base_sha")
        r["files"] = [embed(rep.parent / f) for f in r.get("files", []) if (rep.parent / f).exists()] if i < TAILORED_EMBED_MAX else []
        out.append(r)
    return out


def tailor_action(pdir: Path):
    import tailor as tailor_mod

    def handle(body: dict):
        try:
            r = tailor_mod.tailor(pdir, str(body.get("company", "")), str(body.get("role", "")), str(body.get("jd", "")),
                                  str(body.get("url", "")), str(body.get("base", "general")))
        except ValueError as e:
            return 422, {"ok": False, "error": str(e)}
        return 200, {"ok": True, "folder": r["folder"]}
    return handle


def read_variants(pdir: Path) -> list:
    f = pdir / "outputs" / "resume" / "variants" / "match.json"
    return json.loads(f.read_text()) if f.exists() else []


def collect_documents(pdir: Path, slug: str) -> list:
    """Everything the person downloads or copies, embedded so the dashboard works as one shared file."""
    out, o = [], pdir / "outputs"
    name = slug.replace("-", " ").title().replace(" ", "_")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        rdir = o / "resume"
        resume = [p for p in sorted(rdir.glob("*_Resume*.*")) if p.suffix in (".pdf", ".docx")] if rdir.is_dir() else []
        if resume:
            draft = any("DRAFT" in p.name for p in resume)
            has_variants = (rdir / "variants" / "match.json").exists() and any(v["in_use"] for v in json.loads((rdir / "variants" / "match.json").read_text()))
            out.append({"id": "resume", "group": "Apply with", "title": "Resume (general)" if has_variants else "Resume",
                        "desc": "One page, ATS-safe. PDF to upload; DOCX when a portal asks for Word." + ats_note(pdir),
                        "warn": "Contains [[placeholders]]: fill them before sending." if draft else "",
                        "files": [embed(p) for p in sorted(resume, key=lambda p: p.suffix != ".pdf")], "copy": None})
        for v in read_variants(pdir):
            if not v["in_use"]:
                continue
            built = [p for p in sorted((rdir / "variants" / v["id"]).glob("*_Resume*.*")) if p.suffix in (".pdf", ".docx")]
            if built:
                ats = f", ATS {v['ats']['pct']}% ({v['ats']['checks_passed']}/{v['ats']['checks_total']} format checks)" if v.get("ats") else ""
                out.append({"id": "resume-" + v["id"], "group": "Apply with", "title": f"Resume: {v['title']}",
                            "desc": f"For {v['title']} roles. Same facts, ordered for this role. Profile fit {v['fit']}%{ats}.",
                            "warn": {"stretch": f"Stretch role: the documents show little of {', '.join(v['weak'][:4])}. Be ready to explain.",
                                     "no-fit": f"Built by override: {v.get('override', '')}"}.get(v["verdict"], ""),
                            "files": [embed(p) for p in sorted(built, key=lambda p: p.suffix != ".pdf")], "copy": None})
        ldir = o / "cover-letters"
        if ldir.is_dir():
            for src in sorted(ldir.glob("*.md")):
                if src.stem.endswith("-email"):
                    text = re.sub(r"<!--.*?-->\s*", "", src.read_text(), flags=re.S).strip().replace("**Subject:**", "Subject:")
                    out.append({"id": "letter-" + src.stem, "group": "Apply with", "title": "Cover letter: short email version",
                                "desc": "Under 120 words, for referral requests, recruiter replies and LinkedIn messages. Fill the [[placeholders]] and paste.",
                                "warn": "", "files": [embed(src)], "copy": {"label": "Copy email text", "text": text}})
                    continue
                built = [p for p in sorted(ldir.glob(f"*_Cover_Letter_{src.stem.replace('-', '_')}*.*")) if p.suffix in (".pdf", ".docx")]
                is_base = src.stem == "base"
                out.append({"id": "letter-" + src.stem, "group": "Apply with",
                            "title": "Cover letter: base template" if is_base else f"Cover letter: {src.stem[11:].replace('-', ' ').title() or src.stem}",
                            "desc": ("The template for tailored letters. Ask Claude for a letter per job (action J6); this one has [[placeholders]]."
                                     if is_base else f"Tailored letter, written {src.stem[:10]}."),
                            "warn": "Template: fill the [[placeholders]] or ask for a tailored letter." if any("DRAFT" in p.name for p in built) else "",
                            "files": [embed(p) for p in sorted(built, key=lambda p: p.suffix != ".pdf")] + [embed(src)], "copy": None})
        for key, title, desc, copy_label in (
            ("04-learning-plan.md", "Learning plan", "Six-week interview preparation, the story bank, predicted questions and the application system.", None),
            ("05-mock-interview-prompt.md", "Mock interview prompt", "Paste into a new ChatGPT chat, fill the three <<...>> blocks, and answer out loud.", "Copy prompt for ChatGPT"),
        ):
            src = o / key
            if not src.exists():
                continue
            files = [f for f in (md_to_docx(src, tmp),) if f]
            entry = {"id": src.stem, "group": "Prepare with", "title": title, "desc": desc, "warn": "",
                     "files": [embed(f, f"{name}_{src.stem[3:].replace('-', '_').title()}.docx") for f in files] + [embed(src)],
                     "copy": {"label": copy_label, "text": fenced_text(src.read_text())} if copy_label else None}
            out.append(entry)
        for key, title in (("01-linkedin-review.md", "LinkedIn review"), ("02-job-market-gap-analysis.md", "Job market and gap analysis"),
                           ("03-lens-review.md", "Lens review"), ("03a-ats-report.md", "ATS report")):
            if (o / key).exists():
                out.append({"id": key[:-3], "group": "Reference reports", "title": title, "desc": "", "warn": "",
                            "files": [embed(o / key)], "copy": None})
    total = sum(len(f["b64"]) for d in out for f in d["files"])
    if total > EMBED_MAX_BYTES:
        sys.exit(f"FAIL: embedded documents are {total // 1024} KB; over the {EMBED_MAX_BYTES // 1024} KB cap")
    return out


def read(pdir: Path, key: str) -> str:
    p = pdir / OUT[key]
    return p.read_text() if p.exists() else ""


def scripts_ref(root: Path) -> str:
    """How the dashboard's copy-paste commands name this skill's scripts: relative to the workspace when the
    skill sits inside it (a project install), otherwise the absolute path (a plugin install elsewhere)."""
    scripts = SKILL_DIR / "scripts"
    try:
        return str(scripts.relative_to(root.resolve()))
    except ValueError:
        return str(scripts)


def cmd_render(pdir: Path, slug: str, api: dict = None, quiet: bool = False) -> str:
    items = parse_actions(read(pdir, "actions")) + parse_ledger(read(pdir, "ledger"))
    review = parse_lens_review(read(pdir, "lens"))
    by_id = {i["id"]: i for i in items}
    for row in review["scorecard"]:  # the scorecard is the source of gate <-> action links
        for rid in row["actions"]:
            if rid in by_id and row["gate"] not in by_id[rid]["gates"]:
                by_id[rid]["gates"].append(row["gate"])
    floor = {"Critical": "P0", "High": "P1"}  # reviewer severity outranks a guessed priority
    for row in review["consensus"]:
        p = floor.get(row["severity"])
        for rid in row["actions"]:
            if rid not in by_id:
                continue
            by_id[rid]["consensus"] = by_id[rid].get("consensus", 0) + 1  # tie-break: fixes more agreed findings
            if p and by_id[rid]["priority"] > p:
                by_id[rid]["priority"] = p
    lens_dir = pdir / OUT["lens_dir"]
    lenses = [parse_lens_file(p) for p in sorted(lens_dir.glob("*.md"))] if lens_dir.is_dir() else []
    target = json.loads((pdir / "target.json").read_text()) if (pdir / "target.json").exists() else {}
    data = {
        "slug": slug, "name": target.get("name", slug), "generated": datetime.date.today().isoformat(),
        "linkedin_url": target.get("linkedin_url", ""), "target": {k: target.get(k) for k in ("target_titles", "locations", "domains")},
        "framework": json.loads(FRAMEWORK.read_text()), "items": items, "review": review, "lenses": lenses,
        "ats": parse_ats(read(pdir, "ats"), read(pdir, "ats_hist")), "funnel": parse_funnel(read(pdir, "funnel")),
        "api": api, "scripts": scripts_ref(pdir.parent.parent), "history": tracker.history(pdir), "pending": tracker.pending_count(pdir),
        "recapture": dict(zip(("ids", "since"), pipeline.linkedin_done_since_capture(pdir))),
        "documents": collect_documents(pdir, slug), "variants": read_variants(pdir), "tailored": read_tailored(pdir),
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")  # never close the <script> early
    html = TEMPLATE.read_text()
    if html.count(SENTINEL) != 1:
        sys.exit(f"FAIL: template must contain the sentinel {SENTINEL} exactly once")
    html = html.replace(SENTINEL, payload)
    if api:  # the served variant carries the per-run token, so it is never written to disk
        return html
    out = pdir / OUT["html"]
    tmp = out.with_suffix(".tmp")
    tmp.write_text(html)
    tmp.replace(out)
    if quiet:
        return html
    counts = {s: sum(i["status"] == s for i in items) for s in STATUSES}
    print(f"OK: {out.relative_to(pdir.parent.parent)}: {len(items)} actions ({counts['open']} open, "
          f"{counts['resolved']} resolved, {counts['ignored']} ignored), {len(review['scorecard'])} gates, "
          f"{len(lenses)} lens returns, {len(data['ats']['keywords'])} keywords, {len(data['funnel'])} funnel weeks, "
          f"{sum(len(d['files']) for d in data['documents'])} downloads ({len(payload) // 1024} KB page)")
    return html


def report(results: list) -> int:
    for r in results:
        print(f"{r['state'].upper():9} #{r['id']} {r['kind']} {r['target']}: {r['detail']}")
    return sum(r["state"] in ("conflict", "rejected") for r in results)


def cmd_set(pdir: Path, slug: str, pairs: list) -> None:
    edits = []
    for pair in pairs:  # validate everything before recording anything
        rid, _, status = pair.partition("=")
        err = tracker.validate("status", rid, {"status": status})
        if not err and tracker.current_status(pdir, rid) is None:
            err = f"{rid} is not in actions.md or the ledger"
        if err:
            sys.exit(f"FAIL: '{pair}': {err} (nothing was recorded)")
        edits.append((rid, status))
    for rid, status in edits:  # CLI edits carry no base: the person is stating the outcome directly
        tracker.record(pdir, "status", rid, {"status": status}, None, "cli")
    bad = report(tracker.sync(pdir))
    cmd_render(pdir, slug)
    sys.exit(1 if bad else 0)


def cmd_funnel(pdir: Path, slug: str, pairs: list) -> None:
    vals = dict(p.partition("=")[::2] for p in pairs)
    week, notes = vals.pop("week", ""), vals.pop("notes", "")
    if any(not v.isdigit() for v in vals.values()):
        sys.exit(f"FAIL: counts must be whole numbers for: {', '.join(tracker.funnel_keys())} (nothing was recorded)")
    payload = {"counts": {k: int(v) for k, v in vals.items()}, "notes": notes}
    err = tracker.validate("funnel", week, payload)
    if err:
        sys.exit(f"FAIL: {err} (nothing was recorded)")
    tracker.record(pdir, "funnel", week, payload, None, "cli")
    bad = report(tracker.sync(pdir))
    cmd_render(pdir, slug)
    sys.exit(1 if bad else 0)


def cmd_sync(pdir: Path, slug: str) -> None:
    results = tracker.sync(pdir)
    if not results:
        print("OK: nothing pending")
    bad = report(results)
    if (pdir / OUT["actions"]).exists():  # a brand-new person has nothing to show yet
        cmd_render(pdir, slug)
    sys.exit(1 if bad else 0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("render"); s.add_argument("slug")
    s = sub.add_parser("set"); s.add_argument("slug"); s.add_argument("pairs", nargs="+")
    s = sub.add_parser("funnel"); s.add_argument("slug"); s.add_argument("pairs", nargs="+")
    s = sub.add_parser("sync"); s.add_argument("slug")
    s = sub.add_parser("serve"); s.add_argument("slug"); s.add_argument("--port", type=int, default=8765)
    a = p.parse_args()
    pdir = Path(a.root).resolve() / "people" / a.slug
    if not pdir.is_dir():
        sys.exit(f"FAIL: {pdir} not found")
    {"render": lambda: cmd_render(pdir, a.slug), "set": lambda: cmd_set(pdir, a.slug, a.pairs),
     "funnel": lambda: cmd_funnel(pdir, a.slug, a.pairs), "sync": lambda: cmd_sync(pdir, a.slug),
     "serve": lambda: (tracker.sync(pdir), tracker.serve(pdir, a.slug, a.port,
                                                         lambda api: cmd_render(pdir, a.slug, api, quiet=True),
                                                         {"tailor": tailor_action(pdir)}))}[a.cmd]()


if __name__ == "__main__":
    main()

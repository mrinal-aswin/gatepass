#!/usr/bin/env python3
"""A resume tailored to one job description, built from the pipeline's own resume as the base.

  tailor.py tailor <slug> --company "Acme" --role "Senior Frontend Engineer" --jd-file jd.txt [--url URL] [--base general|<variant id>]

Deterministic, no model call, so it runs in seconds from the dashboard's Tailor tab. It never writes new
claims: it reorders skills and bullets by what the job ad asks for, adds job-ad terms that the person's own
documents prove but the base resume leaves out, and lists the rest as gaps. The same fact gate as role
variants checks the result before it is built. Output: outputs/resume/tailored/<date>-<company>-<role>/.
"""
import argparse, contextlib, datetime, hashlib, io, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I drops the script directory
import lens, pipeline, variants

MAX_ADDED = 8          # job-ad terms added to the skills section at most; more reads as stuffing
JD_MIN_CHARS = 200     # shorter than this is a title, not a job description
REQUIRED = re.compile(r"\b(must|required|requirements?|mandatory|essential|need to have|you have|you bring)\b", re.I)
ADDED_LABEL = "Also relevant"


def slug(text: str, limit: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-") or "job"


def vocabulary(pdir: Path, base_text: str) -> list:
    """Every skill term the pipeline knows: target and role keywords, the role-family catalog, and the base resume's own skills."""
    target = variants.load_target(pdir)
    entries = [*target.get("keywords", []), *(k for v in target.get("variants", []) for k in v.get("keywords", [])),
               *(k for f in variants.catalog().values() for k in f["keywords"])]
    for line in variants.section(base_text, "SKILLS").splitlines():
        if line.strip().startswith("-"):
            for item in re.split(r"[,;]", re.sub(r"^\s*-\s*\*\*[^*]+\*\*\s*", "", line)):
                item = re.sub(r"\s*\(.*?\)\s*", " ", item).strip(" .")
                if 2 <= len(item) <= 40:
                    entries.append({"term": item, "aliases": []})
    seen, out = set(), []
    for e in entries:
        key = e["term"].lower()
        if key not in seen:
            seen.add(key)
            out.append(e)
    return out


def surface_forms(k: dict) -> list:
    return k.get("aliases", []) if k.get("label") else [k["term"], *k.get("aliases", [])]


def found_form(text: str, k: dict):
    """The first wording of a keyword that occurs in the text, or None."""
    return next((t for t in surface_forms(k) if lens.term_regex(t).search(text)), None)


def jd_keywords(jd: str, vocab: list) -> list:
    """Known skills the job ad mentions, named the way the ad names them. One entry per wording, so a
    category (Frontend framework) and its member (React) don't count the same mention twice."""
    required_text = " ".join(l for l in jd.splitlines() if REQUIRED.search(l))
    out, seen = [], set()
    for k in vocab:
        forms = [t for t in surface_forms(k) if lens.term_regex(t).search(jd)]
        forms = [t for t in forms if t.lower() not in seen]
        if not forms:
            continue
        seen.update(t.lower() for t in forms)
        n = sum(len(lens.term_regex(t).findall(jd)) for t in forms)
        weight = 3 if n >= 3 or any(lens.term_regex(t).search(required_text) for t in forms) else 2 if n == 2 else 1
        out.append({"term": forms[0], "aliases": forms[1:], "weight": weight, "jd_mentions": n})
    return sorted(out, key=lambda k: (-k["weight"], -k["jd_mentions"], k["term"].lower()))


def relevance(text: str, keywords: list) -> int:
    return sum(k["weight"] for k in keywords if found_form(text, k))


def tailor_text(base: str, keywords: list, added: list) -> str:
    """Reorder skills and each role's bullets by job-ad relevance (stable), and add proven job-ad terms."""
    lines = base.splitlines()
    m = re.search(r"^## SKILLS\s*$", base, re.M)
    if m:
        start = base[:m.end()].count("\n") + 1
        end = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
        skills = []
        for line in (l for l in lines[start:end] if l.strip().startswith("- ")):
            head = re.match(r"^(\s*-\s*\*\*[^*]+\*\*\s*)(.*)$", line)
            if head:
                items = sorted((x.strip() for x in head.group(2).split(",")), key=lambda it: -relevance(it, keywords))
                line = head.group(1) + ", ".join(items)
            skills.append(line)
        skills.sort(key=lambda l: -relevance(l, keywords))
        if added:  # second line: close to the top, after the most relevant group
            skills.insert(min(1, len(skills)), f"- **{ADDED_LABEL}:** " + ", ".join(added))
        lines[start:end] = ["", *skills, ""]
    # Bullets: reorder within each run of consecutive "- " lines under PROFESSIONAL EXPERIENCE.
    out, run, in_exp = [], [], False
    def flush():
        out.extend(sorted(run, key=lambda l: -relevance(l, keywords)))
        run.clear()
    for line in lines:
        if line.startswith("## "):
            flush()
            in_exp = line.strip() == "## PROFESSIONAL EXPERIENCE"
        if in_exp and line.startswith("- "):
            run.append(line)
            continue
        flush()
        out.append(line)
    flush()
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n") + "\n"


def text_of_pdf(pdf: Path) -> str:
    return subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout


def base_source(pdir: Path, base: str) -> Path:
    if base in (None, "", "general"):
        return pdir / pipeline.OUT["resume"]
    if base not in {v["id"] for v in variants.load_target(pdir).get("variants", [])}:  # also blocks path tricks like ../
        raise ValueError(f"'{base}' isn't one of this person's role resumes")
    src = variants.variant_dir(pdir, base) / "resume.md"
    if not src.exists():
        raise ValueError(f"no role resume '{base}'; build it first or use the general resume")
    return src


def tailor(pdir: Path, company: str, role: str, jd: str, url: str = "", base: str = "general") -> dict:
    """Build the tailored resume. Returns the report; raises ValueError with a plain message on bad input or a failed gate."""
    company, role, url = company.strip()[:80], role.strip()[:120], (url or "").strip()[:500]
    if not company or not role:
        raise ValueError("company and role are required")
    if len(jd.strip()) < JD_MIN_CHARS:
        raise ValueError(f"paste the full job description (at least {JD_MIN_CHARS} characters)")
    if url and not re.match(r"^https?://", url):
        raise ValueError("the job link must start with http:// or https://")
    src = base_source(pdir, base)
    base_text = variants.strip_comments(src.read_text())
    keywords = jd_keywords(jd, vocabulary(pdir, base_text))
    if not keywords:
        raise ValueError("no known skills found in this job description; is it the full text?")
    evidence = variants.profile_evidence(pdir)
    # Rows the ledger holds back pending the person's answer: their documents mention it, but it isn't claimed yet.
    held = " ".join(t for t, st in variants.ledger_rows(pdir) if st == "assumed" and re.match(r"^\(\s*(not claimed|dropped)", t, re.I))
    added, rows = [], []
    for k in keywords:
        if found_form(base_text, k):
            status = "on resume"
        elif (form := found_form(evidence, k)) and not lens.term_regex(form).search(held) and len(added) < MAX_ADDED:
            status = "added from your documents"
            added.append(form)
        else:
            status = "gap"
        rows.append({"term": " / ".join([k["term"], *k["aliases"]]), "weight": k["weight"], "jd_mentions": k["jd_mentions"], "status": status})

    today = datetime.date.today().isoformat()
    out = pdir / "outputs" / "resume" / "tailored" / f"{today}-{slug(company, 30)}-{slug(role, 40)}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "jd.md").write_text(f"# {role} at {company}\n\nSaved {today}." + (f" Link: {url}" if url else "") + "\n\n" + jd.strip() + "\n")
    tailored = tailor_text(base_text, keywords, added)
    md = out / "resume.md"
    md.write_text(f"<!-- Tailored {today} for {role} at {company}, from {src.relative_to(pdir)}. Generated by tailor.py: "
                  "edit the base resume, not this file. -->\n" + tailored)

    gate = variants.check_variant(pdir, {"id": "tailored", "keywords": keywords}, md)
    if gate:
        raise ValueError("the tailored resume failed the fact check: " + "; ".join(gate[:5]))
    target = variants.load_target(pdir)
    log = io.StringIO()
    try:
        with contextlib.redirect_stdout(log):
            pipeline.build_resume(md, pdir / "outputs/resume/resume.css", pdir / pipeline.OUT["ledger"],
                                  int(target.get("max_pages") or 1), "_" + re.sub(r"\W+", "_", company.title()).strip("_")[:30])
    except SystemExit as e:
        raise ValueError(f"build failed: {e}") from None
    pdf = sorted(out.glob("*_Resume*.pdf"))[-1]
    text = text_of_pdf(pdf)
    base_pdfs = sorted(src.parent.glob("*_Resume*.pdf"))
    before = lens.coverage(text_of_pdf(base_pdfs[-1]), keywords)[0] if base_pdfs else None
    after, missing = lens.coverage(text, keywords)
    checks = lens.format_checks(text, [*target.get("target_titles", []), role], target.get("locations", []))
    report = {
        "company": company, "role": role, "url": url, "date": today, "base": base or "general", "folder": out.name,
        "base_sha": pipeline.sha(src), "before": before, "after": after, "pass_mark": lens.PASS_SCORE,
        "checks": [{"name": n, "pass": ok} for n, ok in checks], "keywords": rows, "added": added,
        "gaps": [r["term"] for r in rows if r["status"] == "gap"],
        "base_label": "General resume" if (base or "general") == "general" else f"Role resume: {base}",
        "warnings": [l[6:] for l in log.getvalue().splitlines() if l.startswith("WARN: ")],
        "files": [p.name for p in sorted(out.glob("*_Resume*.*"), key=lambda p: p.suffix != ".pdf") if p.suffix in (".pdf", ".docx")],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("tailor"); s.add_argument("slug")
    s.add_argument("--company", required=True); s.add_argument("--role", required=True)
    s.add_argument("--jd-file", required=True); s.add_argument("--url", default=""); s.add_argument("--base", default="general")
    a = p.parse_args()
    pdir = pipeline.person_dir(Path(a.root).resolve(), a.slug)
    if not pdir.is_dir():
        sys.exit(f"FAIL: {pdir} not found")
    try:
        r = tailor(pdir, a.company, a.role, Path(a.jd_file).expanduser().read_text(), a.url, a.base)
    except ValueError as e:
        sys.exit(f"FAIL: {e}")
    for w in r["warnings"]:
        print(f"WARN: {w}")
    print(f"OK: outputs/resume/tailored/{r['folder']}/ ({', '.join(r['files'])})")
    print(f"ATS against this job: {r['before']}% with the base resume -> {r['after']}% tailored (pass mark {r['pass_mark']}%); "
          f"format checks {sum(c['pass'] for c in r['checks'])}/{len(r['checks'])}")
    print(f"  added from the person's documents: {', '.join(r['added']) or 'none'}")
    print(f"  gaps (not claimed): {', '.join(r['gaps']) or 'none'}")


if __name__ == "__main__":
    main()

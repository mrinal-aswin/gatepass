#!/usr/bin/env python3
"""ATS lens (gate G2, plus LinkedIn findability for G1): a deterministic, repeatable score.

  lens.py ats <slug>     score the built resume PDF and latest LinkedIn snapshot against target.json

Keywords live in target.json as {"term", "aliases", "weight"} (weight 3 = must-have, 2 = strong,
1 = nice). Matching is case-insensitive on whole terms, so "React" does not match "Reactive".
The resume is read from the built PDF's extracted text, which is what an ATS actually sees.
Writes outputs/03a-ats-report.md and appends a row to outputs/ats-history.tsv.
"""
import argparse, datetime, json, re, subprocess, sys
from re import split as re_split
from pathlib import Path

HEADINGS = ("SUMMARY", "SKILLS", "PROFESSIONAL EXPERIENCE", "EDUCATION")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE = re.compile(r"\+?\d[\d\s-]{8,}\d")
PASS_SCORE = 80  # weighted keyword coverage, percent


def term_regex(term: str) -> re.Pattern:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", re.I)


def city_parts(entry: str) -> list:
    """'Kochi / Ernakulam, Kerala, India' -> ['Kochi', 'Ernakulam', 'Kerala', 'India']; 'Remote (India)' -> []."""
    if entry.strip().lower().startswith("remote"):
        return []  # remote is a preference, not a place the header should name
    work_styles = {"hybrid", "onsite", "on-site", "remote", "wfh"}
    return [p for p in (s.strip() for s in re_split(r"[/,()]", entry)) if len(p) > 2 and p.lower() not in work_styles]


def hits(text: str, kw: dict) -> int:
    return sum(len(term_regex(t).findall(text)) for t in [kw["term"], *kw.get("aliases", [])])


def coverage(text: str, keywords: list) -> tuple:
    total = sum(k.get("weight", 1) for k in keywords) or 1
    got = sum(k.get("weight", 1) for k in keywords if hits(text, k))
    return round(100 * got / total), [k for k in keywords if not hits(text, k)]


def resume_text(pdir: Path) -> tuple:
    pdfs = sorted((pdir / "outputs/resume").glob("*_Resume*.pdf"))
    if pdfs:
        out = subprocess.run(["pdftotext", str(pdfs[-1]), "-"], capture_output=True, text=True, check=True)
        return out.stdout, pdfs[-1].name
    md = (pdir / "outputs/resume/resume.md").read_text()
    return re.sub(r"<!--.*?-->", "", md, flags=re.S), "resume.md (no built PDF found)"


def format_checks(resume: str, titles: list, locations: list) -> list:
    """What an ATS needs from any resume's extracted text: (check, passed)."""
    head = "\n".join(resume.splitlines()[:6])
    return [
        ("All standard section headings extract", all(h in resume for h in HEADINGS)),
        ("A target title appears in the header", any(term_regex(t).search(head) for t in titles)),
        ("Email present", bool(EMAIL.search(resume))),
        ("Phone present", bool(PHONE.search(resume))),
        ("A target city appears in the header", any(term_regex(part).search(head) for c in locations for part in city_parts(c))),
    ]


def cmd_ats(pdir: Path) -> None:
    target = json.loads((pdir / "target.json").read_text())
    keywords = target.get("keywords") or sys.exit("FAIL: target.json has no 'keywords'; the market stage writes them")
    resume, resume_src = resume_text(pdir)
    sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I drops the script directory
    import pipeline  # same folder; shares the intake-order rule so ATS reads the snapshot the pipeline calls latest
    snaps = [s for s in pipeline.inputs_of(pdir, "linkedin") if s.suffix == ".md"]
    linkedin = snaps[-1].read_text() if snaps else ""

    r_score, r_missing = coverage(resume, keywords)
    l_score, l_missing = coverage(linkedin, keywords) if linkedin else (0, keywords)
    checks = format_checks(resume, target.get("target_titles", []), target.get("locations", []))

    rows = []
    for k in sorted(keywords, key=lambda k: (-k.get("weight", 1), k["term"].lower())):
        rows.append(f"| {k['term']} | {k.get('weight', 1)} | {hits(resume, k) or '**missing**'} | "
                    f"{hits(linkedin, k) or '**missing**' if linkedin else 'n/a'} |")
    verdict = "Pass" if r_score >= PASS_SCORE and all(ok for _, ok in checks) else "Needs work"
    today = datetime.date.today().isoformat()
    report = [
        f"# 03a - ATS report: {target.get('name', pdir.name)} ({today})", "",
        f"Resume source: `{resume_src}` (extracted text, as an ATS reads it). "
        f"LinkedIn source: `{snaps[-1].name if snaps else 'none'}`.", "",
        f"**Verdict (gate G2):** {verdict}. Resume keyword coverage **{r_score}%** (pass mark {PASS_SCORE}%); "
        f"LinkedIn coverage **{l_score}%** (gate G1 findability).", "",
        "## Format checks", "", "| Check | Result |", "|---|---|",
        *[f"| {name} | {'Pass' if ok else '**Fail**'} |" for name, ok in checks], "",
        "## Keyword coverage", "",
        "Weight 3 = must-have, 2 = strong, 1 = nice to have. Counts are whole-term matches, aliases included.", "",
        "| Keyword | Weight | Resume | LinkedIn |", "|---|---|---|---|", *rows, "",
        "## Missing, by weight", "",
        f"- Resume: {', '.join(k['term'] for k in sorted(r_missing, key=lambda k: -k.get('weight', 1))) or 'none'}",
        f"- LinkedIn: {', '.join(k['term'] for k in sorted(l_missing, key=lambda k: -k.get('weight', 1))) or 'none'}", "",
        "Add a missing keyword only where the person genuinely has the skill. Coverage bought with untrue "
        "keywords fails at the technical round (G5) instead.", "",
    ]
    (pdir / "outputs/03a-ats-report.md").write_text("\n".join(report))
    hist = pdir / "outputs/ats-history.tsv"
    if not hist.exists():
        hist.write_text("date\tresume_source\tresume_pct\tlinkedin_pct\tchecks_passed\n")
    with hist.open("a") as f:
        f.write(f"{today}\t{resume_src}\t{r_score}\t{l_score}\t{sum(ok for _, ok in checks)}/{len(checks)}\n")
    print(f"ATS {verdict}: resume {r_score}%, LinkedIn {l_score}%, checks {sum(ok for _, ok in checks)}/{len(checks)}")
    print(f"  missing on resume (by weight): {', '.join(k['term'] for k in sorted(r_missing, key=lambda k: -k.get('weight', 1))) or 'none'}")
    print(f"  missing on LinkedIn (by weight): {', '.join(k['term'] for k in sorted(l_missing, key=lambda k: -k.get('weight', 1))) or 'none'}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ats").add_argument("slug")
    a = p.parse_args()
    pdir = Path(a.root).resolve() / "people" / a.slug
    if not pdir.is_dir():
        sys.exit(f"FAIL: {pdir} not found")
    cmd_ats(pdir)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Role-specific resumes (frontend, backend, full stack...), only where the person's profile supports them.

  variants.py match <slug>        score every role family against what the person's documents prove
  variants.py check <slug> [id]   fact gate: a variant may reorder and reword, never add
  variants.py build <slug> [id]   fit gate + fact gate + DOCX/PDF + ATS score for each variant

Families come from assets/role-families.json; target.json "variants" lists those in use, each
{"id", "title", "titles", "keywords" (from job ads, optional), "override" (why, for a no-fit role)}.
Sources are outputs/resume/variants/<id>/resume.md; the report is variants/match.md and match.json.
The base resume stays the single record of facts: it, the inputs and the ledger are the evidence.
"""
import argparse, json, re, subprocess, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I drops the script directory
import lens, pipeline

FAMILIES = Path(__file__).resolve().parent.parent / "assets" / "role-families.json"
FIT_MIN, MUST_MIN = 60, 66        # percent coverage, overall and of weight-3 keywords, to call a role a fit
STRETCH_MIN, STRETCH_MUST = 40, 33  # below these, the documents don't support the role
SOLID_MENTIONS = 2                # fewer mentions across the person's documents is a passing reference
NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def load_target(pdir: Path) -> dict:
    return json.loads((pdir / "target.json").read_text())


def catalog() -> dict:
    return {k: v for k, v in json.loads(FAMILIES.read_text()).items() if not k.startswith("_")}


def ledger_rows(pdir: Path) -> list:
    """(resume text, status) per ledger row; the status is the last cell."""
    f = pdir / pipeline.OUT["ledger"]
    rows = []
    for line in f.read_text().splitlines() if f.exists() else []:
        if re.match(r"^\|\s*A\d+\s*\|", line):
            c = [x.strip() for x in line.strip().strip("|").split("|")]
            rows.append((c[1], c[-1]))
    return rows


def removed_claims(pdir: Path) -> list:
    """What the ledger took back: quoted text or ~~struck~~ items in `removed` rows."""
    claims = []
    for text, status in ledger_rows(pdir):
        if status == "removed":
            claims += re.findall(r'"([^"]{3,})"', text)
            claims += [c.strip() for struck in re.findall(r"~~(.+?)~~", text) for c in struck.split(",") if len(c.strip()) >= 3]
    return claims


def without_removed(text: str, pdir: Path) -> str:
    for claim in removed_claims(pdir):
        text = lens.term_regex(claim).sub(" ", text)
    return text


def profile_evidence(pdir: Path) -> str:
    """What the person's own documents prove: latest resume, latest LinkedIn, facts they confirmed.
    Never the generated resumes: scoring those would measure the pipeline's own writing. Claims the
    ledger removed don't count, even though the old documents still contain them."""
    parts = [pipeline.text_of(files[-1]) for kind in pipeline.INPUT_KINDS if (files := pipeline.inputs_of(pdir, kind))]
    parts += [text for text, status in ledger_rows(pdir) if status == "verified"]
    return without_removed("\n".join(parts), pdir)


def check_evidence(pdir: Path) -> str:
    """Anything a variant may state: the profile, the base resume, and any claim tracked in the ledger."""
    base = strip_comments((pdir / pipeline.OUT["resume"]).read_text())
    return "\n".join([profile_evidence(pdir), base, *(t for t, s in ledger_rows(pdir) if s != "removed")])


def mentions(evidence: str, k: dict) -> int:
    terms = k.get("aliases", []) if k.get("label") else [k["term"], *k.get("aliases", [])]
    return sum(len(lens.term_regex(t).findall(evidence)) for t in terms)


def score(evidence: str, keywords: list) -> dict:
    """Depth, not presence: one passing mention earns half credit and never satisfies a must-have,
    so a frontend engineer who once listed PostgreSQL doesn't read as a backend engineer."""
    total = sum(k.get("weight", 1) for k in keywords) or 1
    count = {k["term"]: mentions(evidence, k) for k in keywords}
    earned = sum(k.get("weight", 1) * (1 if count[k["term"]] >= SOLID_MENTIONS else 0.5 if count[k["term"]] else 0) for k in keywords)
    must = [k for k in keywords if k.get("weight", 1) == 3]
    must_pct = round(100 * sum(count[k["term"]] >= SOLID_MENTIONS for k in must) / len(must)) if must else 100
    pct = round(100 * earned / total)
    verdict = ("fit" if pct >= FIT_MIN and must_pct >= MUST_MIN
               else "stretch" if pct >= STRETCH_MIN and must_pct >= STRETCH_MUST else "no-fit")
    return {"fit": pct, "must": must_pct, "verdict": verdict, "missing": [k["term"] for k in keywords if not count[k["term"]]],
            "thin": [k["term"] for k in keywords if count[k["term"]] == 1],
            "weak": [k["term"] for k in sorted(keywords, key=lambda k: -k.get("weight", 1)) if count[k["term"]] < SOLID_MENTIONS]}


def definition(variant: dict, families: dict) -> dict:
    family = families.get(variant["id"], {})
    d = {"id": variant["id"], "title": variant.get("title") or family.get("title"), "titles": variant.get("titles") or family.get("titles") or [],
         "keywords": variant.get("keywords") or family.get("keywords"), "keywords_from": "job ads" if variant.get("keywords") else "generic list"}
    if not d["title"] or not d["keywords"]:
        sys.exit(f"FAIL: variant '{variant['id']}' isn't in role-families.json, so target.json must give its title and keywords")
    return d


def variant_dir(pdir: Path, vid: str) -> Path:
    return pdir / "outputs" / "resume" / "variants" / vid


def built_pdf(pdir: Path, vid: str):
    pdfs = sorted(variant_dir(pdir, vid).glob("*_Resume*.pdf"))
    return pdfs[-1] if pdfs else None


def ats_of(pdir: Path, d: dict):
    pdf = built_pdf(pdir, d["id"])
    if not pdf:
        return None
    text = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True, check=True).stdout
    pct, missing = lens.coverage(text, d["keywords"])
    checks = lens.format_checks(text, d["titles"], load_target(pdir).get("locations", []))
    snapshots = pipeline.inputs_of(pdir, "linkedin")
    linkedin = pipeline.text_of(snapshots[-1]) if snapshots else ""
    return {"pct": pct, "missing": [k["term"] for k in missing], "file": pdf.name, "checks_passed": sum(ok for _, ok in checks),
            "checks_total": len(checks), "checks_failed": [name for name, ok in checks if not ok],
            "pass": pct >= lens.PASS_SCORE and all(ok for _, ok in checks),
            "linkedin": lens.coverage(linkedin, d["keywords"])[0] if linkedin else None,
            "checks": [{"name": name, "pass": ok} for name, ok in checks],  # same shape as the dashboard's general ATS data
            "keywords": [{"term": k["term"], "weight": k.get("weight", 1), "resume": lens.hits(text, k),
                          "linkedin": lens.hits(linkedin, k) if linkedin else None} for k in d["keywords"]]}


def write_report(pdir: Path) -> list:
    target, families = load_target(pdir), catalog()
    evidence = profile_evidence(pdir)
    used = {v["id"]: v for v in target.get("variants", [])}
    rows = []
    for vid in [*used, *(f for f in families if f not in used)]:
        d = definition(used.get(vid, {"id": vid}), families)
        rows.append({**d, **score(evidence, d["keywords"]), "in_use": vid in used, "override": used.get(vid, {}).get("override", ""),
                     "ats": ats_of(pdir, d) if vid in used else None})
    rows.sort(key=lambda r: (not r["in_use"], -r["fit"]))
    out = pdir / "outputs" / "resume" / "variants"
    out.mkdir(parents=True, exist_ok=True)
    md = [f"# Role-specific resumes: {target.get('name', pdir.name)}", "",
          f"Fit is keyword depth in what the person's own documents prove (latest resume, LinkedIn, confirmed facts), never the "
          f"generated resumes. A keyword mentioned only once earns half credit and doesn't count as a must-have. It shows what the documents "
          f"support, not how recent the experience is, so read the single mentions below. **fit**: at least {FIT_MIN}% overall and {MUST_MIN}% of must-haves. **stretch**: at least {STRETCH_MIN}% and "
          f"{STRETCH_MUST}%. Below that, the documents don't support the role, and `build` refuses it without a written `override`.", "",
          "| Role | Fit | Must-haves | Verdict | In use | Keywords from | ATS | Missing from the profile |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        ats = f"{r['ats']['pct']}%, checks {r['ats']['checks_passed']}/{r['ats']['checks_total']}" if r["ats"] else "-"
        md.append(f"| {r['title']} (`{r['id']}`) | {r['fit']}% | {r['must']}% | {r['verdict']} | {'yes' if r['in_use'] else 'no'} | "
                  f"{r['keywords_from']} | {ats} | {', '.join(r['missing']) or 'none'} |")
    thin = [f"- {r['title']}: {', '.join(r['thin'])}" for r in rows if r["verdict"] != "no-fit" and r["thin"]]
    if thin:
        md += ["", "## Single mentions in the profile (real experience, or a passing reference?)", "", *thin]
    (out / "match.md").write_text("\n".join(md) + "\n")
    (out / "match.json").write_text(json.dumps(rows, indent=2) + "\n")
    return rows


def section(body: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    return m.group(1) if m else ""


def check_variant(pdir: Path, d: dict, src: Path = None) -> list:
    """Reasons this variant (or any resume derived from the base) states something the person's records don't.
    Empty means it passes."""
    src = src or variant_dir(pdir, d["id"]) / "resume.md"
    if not src.exists():
        return [f"{src.relative_to(pdir)} doesn't exist yet; write it from the base resume"]
    body, base = strip_comments(src.read_text()), strip_comments((pdir / pipeline.OUT["resume"]).read_text())
    problems = []

    def job_lines(text: str) -> list:  # titles, employers and dates must stay word for word: background checks compare them
        return [" ".join(l.split()) for l in text.splitlines() if l.startswith("### ") or re.match(r"^\*\*.*\d{4}", l)]
    want, got = job_lines(base), job_lines(body)
    problems += [f"job title or date differs from the base resume, or is missing: '{l}'" for l in want if l not in got]
    problems += [f"job title or date isn't in the base resume: '{l}'" for l in got if l not in want]
    if [l for l in got if l in want] != [l for l in want if l in got]:
        problems.append("jobs are in a different order from the base resume")
    if section(body, "EDUCATION").split() != section(base, "EDUCATION").split():
        problems.append("the EDUCATION section differs from the base resume")
    head = lambda t: t.split("## ", 1)[0]
    for contact in re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+|linkedin\.com/in/[\w-]+", head(base)):
        if contact not in body:
            problems.append(f"contact detail missing: {contact}")

    evidence = check_evidence(pdir)
    known = set(NUMBER.findall(evidence))
    for n in sorted(set(NUMBER.findall(body)) - known):
        problems.append(f"number '{n}' appears in no document or ledger row")
    # Term by term, across every family: Vite in the evidence doesn't license a Webpack claim on any resume.
    known_keywords = [*d["keywords"], *(k for f in catalog().values() for k in f["keywords"])]
    terms = {t for k in known_keywords for t in (k.get("aliases", []) if k.get("label") else [k["term"], *k.get("aliases", [])])}
    for term in sorted(terms):
        if lens.term_regex(term).search(body) and not lens.term_regex(term).search(evidence):
            problems.append(f"'{term}' is claimed but appears in no document or ledger row")
    for line in (l.strip() for l in section(body, "SKILLS").splitlines() if l.strip().startswith("-")):
        for item in re.split(r"[,;]", re.sub(r"^-\s*\*\*[^*]+\*\*\s*", "", line)):
            item = item.strip(" .")
            if item and not lens.term_regex(item).search(evidence):
                problems.append(f"skill '{item}' appears in no document or ledger row")
    for claim in removed_claims(pdir):
        if lens.term_regex(claim).search(body):
            problems.append(f"'{claim}' was removed in the ledger and must stay out")
    return problems


def selected(pdir: Path, vid: str = None) -> list:
    target, families = load_target(pdir), catalog()
    variants = target.get("variants") or sys.exit("FAIL: target.json has no 'variants'. Run `match`, pick the roles, then list them there.")
    if vid and vid not in {v["id"] for v in variants}:
        sys.exit(f"FAIL: '{vid}' isn't in target.json variants")
    return [(v, definition(v, families)) for v in variants if not vid or v["id"] == vid]


def cmd_match(pdir: Path, a) -> None:
    for r in write_report(pdir):
        print(f"{r['verdict']:8} {r['title']:26} fit {r['fit']:3}%  must-haves {r['must']:3}%" + ("  [in use]" if r["in_use"] else ""))
    print(f"Report: outputs/resume/variants/match.md (fit needs {FIT_MIN}% overall and {MUST_MIN}% of must-haves)")


def report_problems(vid: str, problems: list) -> None:
    for p in problems:
        print(f"FAIL: {vid}: {p}")


def cmd_check(pdir: Path, a) -> None:
    failed = False
    for _, d in selected(pdir, a.id):
        problems = check_variant(pdir, d)
        report_problems(d["id"], problems)
        failed |= bool(problems)
        if not problems:
            print(f"OK: {d['id']}: every fact traces to the person's records")
    sys.exit(1 if failed else 0)


def cmd_build(pdir: Path, a) -> None:
    target = load_target(pdir)
    evidence, failed = profile_evidence(pdir), False
    for v, d in selected(pdir, a.id):
        s = score(evidence, d["keywords"])
        if s["verdict"] == "no-fit" and not v.get("override"):
            print(f"FAIL: {d['id']}: the profile doesn't support this role (fit {s['fit']}%, must-haves {s['must']}%; missing {', '.join(s['missing'][:6])}). "
                  "Build it only if the person has experience their documents leave out: confirm it in the ledger, or set \"override\" with the reason.")
            failed = True
            continue
        if problems := check_variant(pdir, d):
            report_problems(d["id"], problems)
            failed = True
            continue
        if s["verdict"] == "stretch":
            print(f"WARN: {d['id']}: stretch role (fit {s['fit']}%); little evidence of {', '.join(s['weak'][:4])}")
        vdir = variant_dir(pdir, d["id"])
        if not (css := pdir / "outputs/resume/resume.css").exists():
            sys.exit("FAIL: outputs/resume/resume.css is missing; run init")
        suffix = "_" + re.sub(r"\W+", "_", d["id"].title())
        pipeline.build_resume(vdir / "resume.md", css, pdir / pipeline.OUT["ledger"], int(target.get("max_pages") or 1), suffix)
        ats = ats_of(pdir, d)
        print(f"ATS {'Pass' if ats['pass'] else 'Needs work'}: {d['id']} {ats['pct']}% against {d['keywords_from']} keywords, "
              f"checks {ats['checks_passed']}/{ats['checks_total']}" + (f"; missing {', '.join(ats['missing'])}" if ats["missing"] else ""))
        for name in ats["checks_failed"]:
            print(f"WARN: {d['id']}: format check failed: {name}")
    write_report(pdir)
    sys.exit(1 if failed else 0)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--root", default=".")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("match").add_argument("slug")
    for name in ("check", "build"):
        s = sub.add_parser(name); s.add_argument("slug"); s.add_argument("id", nargs="?")
    a = p.parse_args()
    pdir = pipeline.person_dir(Path(a.root).resolve(), a.slug)
    if not pdir.is_dir():
        sys.exit(f"FAIL: {pdir} not found")
    {"match": cmd_match, "check": cmd_check, "build": cmd_build}[a.cmd](pdir, a)


if __name__ == "__main__":
    main()

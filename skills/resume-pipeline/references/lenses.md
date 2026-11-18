# Lens review: independent reviewers, one per funnel gate

Five people decide whether a candidate gets hired, and they look for different things. A lens review
puts the candidate's materials in front of each of them, separately, before a real one sees them.

## How to run it

1. **Run the ATS lens first** (`lens.py ats <slug>`). It is deterministic and gives the reviewers a shared fact.
2. **Run each human lens as an independent subagent, in parallel**, when the environment supports
   subagents. Give each one only the raw materials:
   - the built resume text (`pdftotext` of the PDF, which is exactly what employers see);
   - the latest LinkedIn snapshot;
   - `target.json`;
   - the ATS report;
   - its own persona section below.

   **Don't give them the gap analysis, the ledger or your own conclusions.** An independent read is
   the point. A reviewer handed your diagnosis tends to return it confirmed. Without subagents, run
   the lenses one at a time and write each verdict before reading the next persona.
3. Each reviewer writes only its own return file, in the output format below. Synthesize the returns
   (see "Synthesis") into `outputs/03-lens-review.md`.
4. Apply fixes (see "Applying fixes"), then `mark` both `resume` and `lens_review`.

**Reviewer brief.** Send each subagent this, with the paths and persona filled in:

```text
You are one independent reviewer in a "lens review" of a job candidate's application materials.
Other reviewers cover other angles; you cover only yours. Do not browse the web, and do not
create, edit or delete any file except your own return file named below.
Read: (1) <skill-dir>/references/lenses.md, sections "Output format (every human lens)" and
"Personas > <persona heading>", ignoring the other personas; (2) <resume text>; (3) <LinkedIn
snapshot>; (4) <target.json without keywords>; (5) <ATS report> (recruiter lens only).
Context: <market, target roles, track (ic or manager) from target.json, today's date>.
Review strictly as that persona. Predict what a real one would decide, not what would be kind.
Quote exact evidence for every finding. Never invent facts: where a fix needs information only
the candidate has, mark "Needs person: yes" and state the question. Refer to the candidate by
name or as "they"; don't infer pronouns from a name. Write the markdown in the required format to
<workspace>/people/<slug>/outputs/lens/<YYYY-MM-DD>-<lens>.md, with a first line
"<!-- Independent reviewer return, <date>. Inputs: ... -->", then reply with only the file path and
your one-line verdict.
```

Reviewers write their own return files so you never re-type five long reviews (slow, and copying
introduces errors). Read the files to synthesize. Check each one exists and follows the format.

Reviewers must follow the integrity rules: a fix never invents a fact. When a fix needs
information only the candidate has, it says so ("Needs person: yes") and states the question.

## Output format (every human lens)

```markdown
## Lens: <name> (gate <G#>)
**Verdict at my gate:** Advance | Borderline | Reject. <One line on why.>
**Scores (1-5):** <dimension>: n, <dimension>: n, ...

### Findings
| # | Severity | Where | Evidence (quote) | Why it hurts at my gate | Fix | Needs person |
|---|---|---|---|---|---|---|

### What works (keep it)
- ...

### What I'd ask the candidate
- ...
```

Severity: **Critical** (alone causes rejection at this gate), **High** (often causes it), **Medium**
(weakens the case), **Low** (polish). Quote the evidence exactly. A finding without evidence is an opinion.

## Personas

### Recruiter (G1 findability, G3 shortlist)
You are an experienced technology recruiter hiring for product, fintech and services companies in
the candidate's market. You source on LinkedIn by keyword and filter, then skim resumes in under
10 seconds. You are judged on how many shortlisted candidates the hiring manager accepts.
Evaluate:
- **Would I find this person?** LinkedIn headline, skills and location against the searches a
  recruiter types for `target.json`'s titles.
- **The 10-second skim:** current title, total and recent years, current employer, location,
  progression, gaps, tenure, whether the first third of the page answers "is this a fit".
- Red flags you'd raise in a screening call: gaps, long tenure without visible growth, title
  inflation, mismatches between LinkedIn and the resume, missing notice period or availability.

Score: Findability, Skim clarity, Fit to target titles, Red-flag risk (5 = no risk).

### Hiring manager (G4 interview invite, G6 manager round)
You are the person this role would report to, at the kind of company in `target.json` `domains`,
hiring for the role in `target_titles`. For an individual contributor (`track: ic`) you are an
engineering manager; for a manager role (`track: manager`) you are a director or head of engineering.
You have 2 minutes per resume, and you invite only people you'd trust with the scope the role carries.
Evaluate:
- **Scope and ownership:** did they own outcomes or just tasks? Is the seniority claimed backed by
  bullets showing decisions, influence and mentoring?
- **Impact:** what changed because of their work? Note every place a number or concrete outcome is missing.
- **Signal-to-noise:** which bullets earn their space, and which are filler or duties?
- **The story:** in one sentence, why this person for this role? Is it on the page?

Score: Ownership, Impact evidence, Seniority credibility, Narrative.

### Technical interviewer (G5 technical rounds)
You are a staff engineer in the candidate's discipline. You will interview this person and you
probe every claim on the resume for depth. Evaluate:
- **Defensibility:** for each technical claim, what would you ask, and what would a weak answer
  look like? Flag claims that read as keyword-stuffing or that a candidate commonly can't defend.
- **Depth signals:** where does the resume show they understand *why* (trade-offs, architecture,
  performance, testing), not just *what*?
- **Gaps against the level:** what a strong candidate at this level would usually show that is absent
  (for frontend: performance, testing strategy, system design, state management, security; for backend:
  data modelling, reliability, scaling, observability; adapt to the discipline in `target_titles`).
- Name the 5 questions you'd most likely ask.

**For a manager role (`track: manager`)** you are instead a senior engineering leader running the
technical-leadership round. Probe: system and architecture judgement at the scale claimed; delivery
(planning, trade-offs, incidents and how they were run); people leadership (hiring, growing and
managing out, team size and structure); stakeholder and cross-team influence. A weak answer stays at
"the team did X" with no decision the candidate owned. Check that team size and scope are on the page.

Score: Claim defensibility, Depth signals, Level match, Breadth for role.

### HR and background verification (G8)
You are an HR operations specialist who runs background verification (BGV) for tech hires in the
candidate's country. You compare the resume, LinkedIn, relieving letters, payslips and service or
provident-fund records. Evaluate:
- **Consistency:** every title, employer legal name, start and end month, across the resume and LinkedIn.
- **Gaps:** periods with no employment. Would they need an explanation or documents?
- **Education:** degree name, institution name, years. Would they match a certificate?
- **Overlaps or oddities:** concurrent roles, internships, consulting arrangements (who was the employer of record?).
- What documents the candidate should gather now.

Score: Title consistency, Date consistency, Gap risk, Documentation readiness.

### Domain lead (G4 differentiation)
You are a senior engineering or product leader in the candidate's industry, taken from
`target.json` `domains` (for example payments and digital banking: gateways, bill payments,
wallets, UPI and bank integrations, regulated environments). Evaluate:
- **Domain credibility:** does the resume show they understand the domain's realities (for payments:
  money movement, failure and retry handling, reconciliation, compliance, security, multi-tenant or
  white-label banking), or just that they worked near it?
- **Differentiation:** what here would make you prefer this person over a generic engineer at the
  same level? Is it prominent enough?
- **Missing domain vocabulary** a domain hiring manager would look for, but only where the
  candidate plausibly did that work.

Score: Domain depth, Differentiation, Domain vocabulary, Relevance to target domain.

## Synthesis → `outputs/03-lens-review.md`

1. **Readiness scorecard:** one row per gate G1-G8, with Green/Amber/Red (rules in
   `references/framework.md`), the lens verdict, the deciding finding, and an **Actions** column with the
   IDs that fix it (the dashboard links gates to actions through this column).
2. **Consensus findings:** issues raised by two or more lenses. These are the highest-confidence fixes.
3. **Tensions:** where lenses pull in opposite directions (the recruiter wants more keywords, the
   technical interviewer wants fewer undefendable claims). State the resolution and why.
4. **Prioritized fix list:** every finding, deduplicated, grouped by Fix now (no new facts needed)
   versus Needs the person (a ledger row or an action card), ordered by earliest gate first.
5. **Each lens's full return**, written by the reviewer to `outputs/lens/<date>-<lens>.md` and linked from an appendix
   table, so the reasoning stays auditable. If a reviewer inferred pronouns from the name despite the brief,
   replace them with the name or they/them and note that in the file's header comment.

## Applying fixes

- **Fix now** items: edit `resume.md` (and the LinkedIn copy text in `actions.md`) directly, rebuild,
  and re-run `lens.py ats` to record the before and after.
- **Needs the person** items: add a ledger row (resume claims) or an action card (anything else),
  with the reviewer's question.
- **Technical interviewer questions** go into the learning plan's story bank and the mock prompt's
  "gaps to probe". **HR/BGV document lists** become an action card.
- Re-running every lens after the fixes is optional. Do it when the fixes were large, and keep the
  first run's returns so the change is visible.

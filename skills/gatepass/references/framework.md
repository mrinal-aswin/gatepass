# The job-search funnel framework

A job search is a funnel, and it fails at a specific gate. Polishing the resume does nothing for
someone who is never found, and interview prep does nothing for someone whose resume is filtered
out. This framework names every gate, the evaluator who controls it, how the pipeline tests it,
and what to fix when it's the gate that leaks.

## The gates

| # | Gate | Who decides | What they decide in | Tested by | Pipeline output |
|---|---|---|---|---|---|
| G0 | **Positioning** | The candidate | Target titles, level, cities, domain | market stage | `target.json`, `02-…` |
| G1 | **Findable** | Recruiter search on LinkedIn and job boards | Keyword search, filters (title, city, Open to Work) | Recruiter lens + ATS script (LinkedIn side) | LinkedIn actions |
| G2 | **Parseable** | ATS software | Text extraction, keyword match, knockout questions | `lens.py ats` (deterministic) | `03a-ats-report.md` |
| G3 | **Shortlisted** | Recruiter, in seconds | Title, years, location, employer, gaps, obvious fit | Recruiter lens | resume, LinkedIn |
| G4 | **Interview invite** | Hiring manager | Scope, impact, seniority, domain relevance | Hiring-manager lens + domain lens | resume |
| G5 | **Technical pass** | Senior engineers | Depth behind every claim | Technical-interviewer lens | learning plan, mock prompt |
| G6 | **Manager / behavioural pass** | Hiring manager | Ownership, judgement, collaboration, motivation | Hiring-manager lens | story bank, mock prompt |
| G7 | **Offer** | Manager + HR | Level, compensation, notice period | Market data | learning plan (negotiation) |
| G8 | **Background check clear** | HR / BGV vendor | Titles, dates, employers, education match records | HR/BGV lens | ledger, LinkedIn actions |

A gate is only as strong as the evidence for it. Each lens gives its gate a verdict, and the
**readiness scorecard** in `03-lens-review.md` shows every gate as Green, Amber or Red:

- **Green:** the lens would advance the candidate, with no Critical or High findings open.
- **Amber:** a Borderline verdict, or High findings that are fixable without new facts.
- **Red:** a Reject verdict, or a Critical finding. Fix this gate before spending effort downstream.

Work the earliest Red gate first. A Red G8 is the exception: fix it before the first offer, because
a failed background check costs the offer itself.

The gate list and the funnel diagnosis rules are also kept in machine-readable form in
`assets/framework.json`, which the dashboard reads. Change a gate or threshold there.

## The measurement loop (once applications start)

The scorecard predicts; the funnel measures. Every week, count from the application tracker:

| Metric | Gate it measures |
|---|---|
| Recruiter InMails or profile views (LinkedIn shows these) | G1 |
| Applications sent → any response | G2-G3 |
| Responses → first interview | G3-G4 |
| First interview → technical rounds passed | G5 |
| Final rounds → offers | G6-G7 |
| Offers → joined | G7-G8 |

**Diagnose the first stage where conversion drops**, and go back to that gate's lens:

- Applications get no responses → G1-G3. Re-run the recruiter lens and the ATS score against the
  actual JDs being applied to. Tailor harder, and lean on referrals.
- Screens happen but no technical interviews follow → G4. The resume or recruiter call promises a
  level the evidence doesn't support, or the domain story is weak.
- Technical rounds fail → G5. Pull the mock-interview reports. Shift study time to the lowest-scoring
  dimension, and drop claims the candidate can't defend.
- Finals don't become offers → G6-G7. Rehearse the story bank, and check level calibration and pay expectations.

These are diagnostic rules, not benchmarks. Conversion rates vary widely by market, seniority and
season, so compare the candidate against their own previous weeks, not against a quoted industry
number. After roughly 20 targeted applications there is enough signal to tell which gate leaks.
Each stage in `assets/framework.json` also has a `floor`, a warning line (for example 8% of applications
getting a response). It lets the dashboard name a leak early, when only the first stage has enough volume.

## Order of work for a new person

1. G0 positioning (market stage), then G8 facts (the ledger). Everything else builds on true facts
   and a clear target.
2. G2 and G1 (cheap, mechanical, high leverage): ATS score, LinkedIn findability.
3. G3 and G4: resume rewrite, informed by the lens review.
4. G5 and G6: the learning plan and mock interviews, started in parallel with applications.
5. G7: negotiation prep before the first final round, not after the offer.

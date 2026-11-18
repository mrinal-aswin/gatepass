# Stage specifications

Each section covers what a stage reads, what it must produce, and the quality bar.
Paths are relative to `people/<slug>/`. On an update, apply the input diff to the existing
document. Use the structure below only when writing a document for the first time.

## Contents
1. linkedin_review
2. market
3. resume (+ ledger, build)
4. learning_plan
5. mock_interview
6. actions
7. lens_review (see `references/lenses.md`)
8. cover_letter
9. variants (role-specific resumes)
10. tailored resumes (per job description)

---

## 1. linkedin_review → `outputs/01-linkedin-review.md`

**Reads:** latest resume text, latest LinkedIn snapshot.

**Sections, in this order:**
1. **Current state:** a table of Section, What is there, Verdict, covering Headline, Location, About,
   Experience, Skills, Education, Certifications, Recommendations, Activity, Featured.
2. **Resume vs LinkedIn conflicts:** a table of Field, Resume, LinkedIn, Action. Check every
   title, every start and end date, employers, roles missing on either side, projects, degree name and
   certifications. Explain why it matters: Indian background verification (and most others)
   compares titles and dates with relieving letters and service records. Mismatches can end an offer.
3. **Prioritised fixes:**
   - P0 (this week): reconcile the timeline, set the exact city, Open to Work (recruiters only) with
     titles and locations from `target.json`, an About draft.
   - P1 (two weeks): headline (220 characters max, keyword-dense), experience bullets copied from
     the final resume, skills (pin the top 3, add modern keywords, push legacy tools down).
   - P2 (a month): recommendations (who to ask, with a one-line prompt for each), Featured
     proof-of-work, a cadence of posts, a custom URL and photo.
4. **Order of operations:** finalise facts → resume → copy to LinkedIn.

**Quality bar:** the About and headline drafts follow the ledger rules. Any value not in the
person's documents is either qualitative or in the ledger. Name clients and banks only with a
note to check what the employment contract allows.

---

## 2. market → `outputs/02-job-market-gap-analysis.md`

**Reads:** `target.json`, latest resume.

**Research (only when the target changed or the research is over 30 days old):** run several web
searches in parallel:
- titles × locations from `target.json`;
- the person's strongest differentiators (domain plus specialist skill, e.g. "React micro-frontend
  payments");
- local tech-park and company boards for their home city.

Open 3-5 of the best-fitting postings to pull real requirement keywords, if fetching is permitted.
If you only had search snippets, say so in a "Limitation" line at the top.

**Sections:**
1. **Positioning:** target titles, experience band (compute years from dates, minus gaps), the
   strongest differentiator, the main weakness.
2. **Listings:** grouped as home city / domain-matched in other cities / remote. Each with a link
   and fit notes, plus a recommended application mix (e.g. 40/40/20).
3. **JD keyword matrix:** Requirement, Frequency, On resume?, Action. Distinguish "add the
   evidence if it's true" from "learn it first". Never recommend claiming a skill the person hasn't used.
4. **Resume issues by severity:** Critical / High / Medium.
5. **Inputs needed from the person:** timeline, impact numbers, a stack truth-check, preferences.
6. **Sources:** every URL used, as markdown links.

**Also write `keywords` into `target.json`** from the keyword matrix: `{"term", "aliases", "weight"}`,
where weight 3 = required by most target JDs, 2 = common, 1 = occasional. Include keywords the
person lacks, because the ATS score has to show real gaps. Add aliases for the spellings employers
use ("React.js", "ReactJS"). Record where the list came from in `keywords_source`. Write the keywords
**before** marking `market`: they are part of `target.json`, so marking first would flag every stage that
reads the target as stale.

**Update without new research:** re-score sections 1, 3, 4 and 5 against the new resume, and
keep the listings section with its original date.

---

## 3. resume → `outputs/resume/resume.md`, `outputs/resume/ASSUMPTIONS.md`, then `build`

**Reads:** resume, LinkedIn, ledger, market keyword matrix, `target.json`.

**ATS format (the build relies on this):**
- First line `# FULL NAME`. Then a bold one-line positioning headline, then one contact line
  (city | phone | email | LinkedIn).
- Sections with exactly these headings: `## SUMMARY`, `## SKILLS`, `## PROFESSIONAL EXPERIENCE`,
  `## EDUCATION` (optionally `## CERTIFICATIONS`, `## PROJECTS`).
- Each role as `### Title | Company, City`, then `**Mon YYYY - Mon YYYY**`, then bullets.
  Promotions at one employer: one `###` entry with the latest title and the full tenure, then a plain
  progression line ("Senior SE (Oct 2025 - Present); SDE 3 (Oct 2023 - Oct 2025); ...") before the bullets.
  That keeps one page and shows the growth. Genuinely different roles (another team or function) get
  separate entries.
- Single column. No tables, images, icons, text boxes or columns.
- Skills as labelled bullet lines (`- **Frameworks:** ...`), keyword-dense, mirroring the
  matrix's top requirements the person actually has.
- One page for under about 12 years of experience. With 12 or more, two pages are acceptable: set
  `max_pages: 2` in `target.json`, and put the strongest material on page one. `build` warns above `max_pages`.

**Writing:**
- Bullets: action verb + what + scope or impact. Replace duty statements ("Responsible for…",
  "Contribute to…") with outcomes. Put the most senior-signalling items first in each role.
- Summary: 3-4 sentences covering years, domain, the two or three differentiators and earlier
  notable employers.
- Cut or compress stale technologies and old certificates that don't help the target role.
- Leave career gaps off the resume unless the reason strengthens it. Prepare the spoken answer
  in the learning plan instead.

**Ledger (`ASSUMPTIONS.md`):** a table of ID, Resume text, Basis (`derived`/`standard`/`guess`),
Why this default, What to ask the person, Status (`assumed`/`sourced`/`verified`/`removed`). Use `sourced`
for a value taken from the person's own documents (a metric on their resume, years computed from their
dates): it isn't a guess, so it doesn't count toward the build's warning, but it isn't confirmed either.
`verified` means the person confirmed it. The Status
cell must be the **last** column. The script counts `| assumed |` at the end of a row. Add a
"Deliberately not claimed" list. Story-bank defaults from the learning plan get rows too.

**Build:** copy `assets/resume.css` into `outputs/resume/` if it's missing (`init` does this), run
`build`, and resolve FAIL lines. Keep WARN lines in the report to the user.

---

## 4. learning_plan → `outputs/04-learning-plan.md`

**Reads:** final resume, market gaps, ledger.

**Sections:**
1. **What the loop looks like:** a table of the target company type's rounds, what each tests,
   where the person stands, and the weight in the plan. For senior roles, system design is
   usually the deciding round.
2. **Six-week plan** sized to a full-time job (about 1.5 h on weekdays, 4 h on weekend days).
   Order: fundamentals → framework internals → hands-on practice problems themed on the person's
   domain → system design (with a named framework, and prompts drawn from the person's real
   projects) → testing, performance and a public proof-of-work project → stories and mocks.
   Every week ends with a concrete output.
3. **Story bank:** a table of Likely question, Story to use (from their real projects), Points to hit.
   Plus rehearsed answers for "why leaving", gaps, "why senior", and salary (anchored on market
   data, with sources).
4. **Application system:** tracker columns, weekly cadence, referrals first, 5-minute tailoring.
5. **Resources:** stable, well-known sources only.
6. **Weekly checkpoint:** three questions, plus a rule for shifting time when one area keeps scoring low.

Adapt the technical content to the person's actual field. The structure holds for any
engineering role, and most of it holds for non-engineering roles too.

---

## 5. mock_interview → `outputs/05-mock-interview-prompt.md`

**Reads:** final resume, ledger, market gaps.

Start from `assets/mock-interview-template.md` and fill in:
- `{{CANDIDATE_BLOCK}}`: name, target role, years, current role with products and stack, earlier
  roles. Write it in compact prose.
- `{{GAPS_TO_PROBE}}`: the weaknesses from the gap analysis, plus `assumed` ledger rows an
  interviewer would test, plus career gaps and job tenure questions.
- `{{ROUNDS}}`: round definitions adapted to the role. Keep the five-round shape, and set the
  practice problems and design prompts in the person's domain. For `track: manager`, the hands-on round
  becomes a written exercise (review a design doc, plan an incident response, or decide a staffing
  trade-off), the deep-dive round covers delivery and people leadership, and system design stays at
  architecture level. For `track: ic`, keep live coding.
- `{{INTERVIEWER_PERSONA}}`: the kind of company in `target.json`.

Keep the interview rules, commands, rubric and final report format from the template unchanged.
They are what make sessions comparable over time.

---

## 6. actions → `outputs/actions.md`, then `actions.py render <slug>` → `outputs/actions.html`

**Reads:** LinkedIn review, market analysis (for job-search actions), latest LinkedIn snapshot.

**Format (the renderer parses this exactly):**

````markdown
## L1 | Write the LinkedIn About section
area: LinkedIn
priority: P0
status: open
why: One or two sentences on the payoff, specific to this person.
link: Open profile | https://www.linkedin.com/in/<id>/

### How to
1. Numbered, concrete UI steps ("click the pencil on ...").
2. ...

### Copy: About text (limit 2600)
```text
Ready-to-paste text.
```
````

- IDs: `L<n>` LinkedIn, `J<n>` job search, `R<n>` resume formatting. Never reuse an ID (see the update rules).
- `status`: `open` | `resolved` | `ignored`. Items the person has already done go in as `resolved`, so the page shows progress.
- Several `link:` and `### Copy:` entries are allowed. Put the limit on any copy text that goes into a length-limited field: headline 220, About 2600, experience description 2000.
- Links must be `https://` pages that exist for everyone. Use the profile URL, its `details/experience|skills|education|recommendations/` pages, `recent-activity/all/`, and `https://www.linkedin.com/public-profile/settings`. Don't guess at edit-modal URLs; tell the user which pencil to click instead.
- Don't link local files from a card (the page drops non-https links). Point to the dashboard's
  **Documents** tab instead ("Download the letter from the Documents tab"), where every built file is.
- Copy text follows the integrity rules. No invented metrics, and suggested posts or comments must be templates the person completes from real experience, never ready-made claims.
- Don't recommend retired features. LinkedIn retired skill assessments in 2024.
- Resume-fact (A*) cards come from `ASSUMPTIONS.md` automatically. Don't duplicate them here.

**The page** (`assets/actions-template.html`) is offline and self-contained. Statuses clicked there persist in the viewer's browser, and a bar offers `actions.py set ...` to write them back. A `set` on an A* row edits the ledger (resolved = verified, ignored = removed), which correctly stales the resume stage.

---

## 7. lens_review → `outputs/03-lens-review.md` (+ `03a-ats-report.md`)

The full method is in `references/lenses.md`, and the gate model in `references/framework.md`. Runs
after `resume`. Its fixes edit the resume, so `resume` and `lens_review` are marked together at the end.

**Document sections:**
1. **Readiness scorecard:** G1-G8 with Green/Amber/Red, the deciding lens and its finding, and the ATS
   before and after percentages.
2. **Consensus findings** (two or more lenses).
3. **Tensions and how they were resolved.**
4. **Fixes applied** (with the resume diff in words) and **fixes needing the person** (each mapped to a ledger row or action ID).
5. **Predicted interview questions** from the technical and hiring-manager lenses (these also feed the
   learning plan and mock prompt).
6. **Appendix:** each lens's return, verbatim, with its date.

**On updates:** re-run only the lenses whose gate the change touches. A LinkedIn-only change needs
the recruiter and HR/BGV lenses. A resume rewrite needs all of them. Carry earlier returns forward in the appendix.

**Dashboard inputs the actions stage must keep valid:**
- `03-lens-review.md` scorecard rows `| G# Name | decides | verdict | **Status** | finding | Actions |`:
  the last column lists the action and ledger IDs (ranges like `L1-L4` are fine). This is what links gates
  to actions on the page. Consensus rows `| C# | finding | raised by | severity | disposition |`: IDs in the
  disposition become links. A Critical consensus finding raises its linked items to P0, and a High one to at least P1.
- `outputs/funnel.md`: `init` creates it with the header `| Week of | <funnel.columns labels> | Notes |`
  from `assets/framework.json`. Rows are added by `actions.py funnel`, never by hand-editing totals.
- `target.json` `linkedin_url`: used for the ATS tab's "Open LinkedIn skills" link.

**Tracker database (`tracker.sqlite`, created on first use).** Table `events`: one row per edit, with
`source` (page or cli), `kind` (status or funnel), `target`, a JSON `payload`, `base` (the status the editor
saw), and `state`: pending, applied, conflict (the source changed since the page loaded) or rejected
(unknown ID). Applying is ordered and idempotent: an already-set status is recorded as applied, and a
failed apply stays pending for the next `sync`. The Markdown files remain the record every stage reads.
Never edit the database by hand; to undo a decision, record a new status.

---

## 8. cover_letter → `outputs/cover-letters/base.md`, `base-email.md`; tailored letters on request

**Reads:** final resume, ledger, target, lens review (for the strongest proof points). Runs after
`mock_interview`. Build with `pipeline.py letter <slug> [file]`. The build labels a letter `_DRAFT` while it
has `[[placeholders]]`, and warns over 400 words or one page.

**Why it matters:** many screens skip cover letters, but the ones that read them, and every referral or
recruiter email, use them to decide whether the resume gets a careful read. The letter's job is to connect
this person's strongest two proofs to this employer's top two requirements, in under a minute's reading.

**Format (the build parses the first lines; the 400-word check counts only the body, from "Dear" to the sign-off):**

```markdown
**Full Name**

City | phone | email | linkedin.com/in/...

<Date, e.g. 6 November 2026>

Hiring Manager, [[Company]]

Dear [[Hiring manager's name, or "Hiring Manager"]],

<4 paragraphs, 250-350 words>

Sincerely,

Full Name
```

**Four paragraphs:**
1. **The role and the thesis** (2-3 sentences): the exact role title; one specific, true reason for
   this company ([[placeholder]] in the base); a one-line thesis of who the person is for this role.
2. **Proof 1:** the resume achievement that best matches the JD's top requirement. Name the problem,
   what the person did, and the outcome, in words that match the resume and ledger exactly.
3. **Proof 2:** the second requirement, with a different achievement. Where the JD stresses something
   the person lacks, don't paper over it. Show the nearest true strength, or leave it out.
4. **Close:** level and progression, availability, and a plain request for a conversation. If the notice
   period is unknown, leave it out of the base letter rather than adding a placeholder or a guessed default.
   Placeholders in `base.md` are only for per-job fields (company, role, the company reason, the hiring
   manager's name), so filling those is all a tailored letter needs. No flattery, no "I believe I would be a great fit".

**Rules:**
- Same integrity rules as the resume: nothing absent from the resume or ledger; no invented metrics. A claim
  resting on an `assumed` ledger row is fine, but list those rows in the file's header comment, so that
  verifying or removing a row flags which letters need a change.
- Mirror 3-5 of the JD's own terms where they are true for the person. An ATS sometimes ingests the letter too.
- Indian market: address "Hiring Manager" when no name is known. Don't put expected CTC in a letter.
- **`base-email.md`:** under 120 words, with a subject line, for referral requests and recruiter replies.
  Not built to PDF; it is copied into an email or LinkedIn message.

**Tailoring a letter for a job:** read the JD (pasted, attached or fetched). Pick its top two
requirements that the person genuinely meets, swap them into paragraphs 2-3, fill the company reason from
the JD or the company's own site (never invented), set the date, and build. Then add the letter to the
dashboard's application tracker card (J1) notes, so a reply can be traced back to the letter sent.

---

## 9. variants → `outputs/resume/variants/<id>/resume.md`, then `variants.py build`

**Reads:** base resume, ledger, inputs, `target.json`. Optional: active only once `target.json` lists `variants`. Runs after
`lens_review`, so variants inherit the reviewed base.

**1. Match.** `variants.py match <slug>` scores each family in `assets/role-families.json` against the latest resume, LinkedIn
and `verified` ledger rows. A keyword mentioned once earns half credit and never satisfies a must-have. The verdict is `fit`,
`stretch` or `no-fit`. The score shows what the documents support, not how recent it is: read the single mentions in `match.md`, and
ask about a skill that may be years old before relying on it. New family: add it to the JSON. Keep aliases free of common English
words, and set `"label": true` on a term that names a category (Databases, Delivery).

**2. Choose and research.** The person picks from the fits (a stretch only if they ask, with its gaps stated). In `target.json`:

```json
"variants": [{"id": "frontend", "title": "Senior Frontend Engineer", "titles": ["Senior Frontend Engineer", "SDE III Frontend"],
              "keywords": [{"term": "React", "aliases": ["React.js"], "weight": 3}]}]
```

`title` and `titles` override the family's. `keywords` come from real job ads for that role (the market stage's method; add a
"Per-role keywords" section to `02-job-market-gap-analysis.md`). Without them the ATS score uses the generic list and says so.
Editing this list stales only the `variants` stage. A person with experience the documents leave out should confirm it in the ledger
(`verified` rows count as evidence). `"override": "<why>"` is the last resort for a `no-fit` role; the dashboard shows the reason.

**3. Write `variants/<id>/resume.md`** in the same ATS format, copied from the base resume and then edited:
- **May change:** headline, summary, skills order and grouping, bullet order, bullet emphasis, and which minor bullets stay.
- **Must not change:** name, contact details, job titles, employers, dates, education. The `build` compares these with the base.
- **No new facts:** every number, skill and role keyword must appear in the person's documents, the base resume or a ledger row.
  To add a true fact that isn't there yet, add a ledger row first. Any wording of a `removed` ledger claim fails the build.
- Keep every job, compressed if needed. Dropping one creates a gap that doesn't exist.

**4. Build.** `variants.py build <slug> [id]` applies the fit gate and the fact gate, builds `Name_Resume_<Id>.docx/.pdf`, scores ATS
(keyword coverage against that role's keywords, plus the same five format checks as the base resume) and refreshes `match.md` and `match.json`. Fix FAIL lines by editing the variant, never by weakening the
base. Then `mark <slug> variants` and `actions.py render <slug>`. The dashboard lists each resume under Documents and the role table under ATS.

**Reviews:** the gates catch invented facts, not weak writing. On a variant's first build, run the technical interviewer and hiring
manager lenses on it (the role changes their reading), saving returns as `lens/<date>-<id>-<lens>.md`. Re-run them only after a large
rewrite. The recruiter and HR/BGV lenses read the base; their findings carry over.

**On updates:** a change to the base resume or ledger stales this stage. Apply the same edit to each variant; don't regenerate it.

**Rest of the pack:** the learning plan gets a short "By role" section with each variant's gaps from `match.md`. The application tracker (J1)
gets a "Resume version" column, so a reply can be traced to the version sent. A tailored cover letter starts from the variant used for that job.

---

## 10. Tailored resumes → `outputs/resume/tailored/<date>-<company>-<role>/` (not a stage)

**Reads:** the chosen base (general resume or a built role resume), the person's documents, the ledger, the keyword
vocabulary (target and role keywords, `assets/role-families.json`, the base's own skills). Made on request, from the dashboard's
Tailor tab or `tailor.py`, so it has no fingerprint and never stales other stages.

**What it does:** finds the known skills the job ad mentions, named the way the ad names them, and weights them (3 = mentioned 3+ times
or in a requirements line). Then: skills groups and items sorted by relevance; bullets sorted within each role; an "Also relevant" line
with the ad's wording for skills the documents prove but the base omits. Titles, dates, education, summary and contacts stay word for word.
Blocked from the added line: `removed` ledger claims, and anything in an `assumed` row that starts "(not claimed)" or "(dropped)".

**Gates:** the variants fact gate, then the normal build gates, then ATS against the ad's keywords (before with the base, after tailored)
and the five format checks with the role added as a title. **report.json** keeps the keyword table, gaps, warnings and the base's fingerprint;
the dashboard marks the resume out of date when that fingerprint no longer matches.

**Limits to say plainly:** the keyword list only knows skills already in the vocabulary, so an unusual requirement may not show as a gap; read the ad.
Reordering moves nothing past an ATS (coverage is about presence); the score only rises when a proven skill is added.


---
name: resume-pipeline
description: Job-search framework for one person, built on the hiring funnel (findable, ATS, recruiter shortlist, hiring manager, technical rounds, offer, background check). Reviews LinkedIn against the resume, researches live jobs and JD keywords, writes an ATS-safe one-page resume (DOCX + PDF), plus role-specific versions (frontend, backend, full stack) where the profile supports them, scores it, runs a lens review where independent reviewers (recruiter, hiring manager, technical interviewer, HR/background check, domain lead) each judge their gate, then builds a learning plan, a ChatGPT mock-interview prompt, cover letters and an action tracker. Updates re-run only what changed. Use whenever someone shares a resume, CV or LinkedIn profile, or says "update the resume", "X sent a new CV", "their LinkedIn changed", "refresh the job search", "review this like a recruiter", "prepare X for interviews", "make this ATS friendly", "write a cover letter for this job" or "help my teammate land a job", even for one piece.
---

# Resume pipeline

Eight stages turn a person's resume and LinkedIn profile into a job-search pack. A small script
(`scripts/pipeline.py`) handles everything deterministic: storing inputs, deciding which stages
are stale, and building and checking the resume. You do the reading, research and writing.

The pipeline exists so that the **second and tenth runs are cheap and safe**. When a new resume
or LinkedIn snapshot arrives, only the stages that depend on it re-run. Facts the person has
already confirmed survive every update.

## Workspace layout

Everything lives under `people/<slug>/` in the working directory (slug = `firstname-lastname`):

```
people/<slug>/
  target.json            target titles, locations, remote, domains (drives job research)
  state.json             written by the script; never edit by hand
  tracker.sqlite         every edit made on the dashboard or with set/funnel, as an event log; never edit by hand
  CHANGELOG.md           one entry per run, newest first
  inputs/resume/         YYYY-MM-DD_<original name>, immutable, plus .extracted.txt
  inputs/linkedin/       YYYY-MM-DD_linkedin.md, immutable text snapshots
  outputs/
    01-linkedin-review.md
    02-job-market-gap-analysis.md
    03-lens-review.md    readiness scorecard per funnel gate, consensus fixes, each reviewer's return
    03a-ats-report.md    deterministic keyword coverage and format checks (lens.py ats)
    ats-history.tsv      one row per ATS run, for before/after
    resume/resume.md     single source for the resume; DOCX and PDF are built from it
    resume/ASSUMPTIONS.md  ledger of every value not taken straight from the person's documents
    resume/resume.css
    resume/variants/     optional role-specific resumes: <id>/resume.md (+ DOCX, PDF), match.md, match.json
    resume/tailored/     one folder per job: jd.md, resume.md, DOCX, PDF, report.json (tailor.py)
    04-learning-plan.md
    05-mock-interview-prompt.md
    cover-letters/       base.md (+ base-email.md), one tailored letter per job, DOCX + PDF built by `letter`
    actions.md           every improvement as a trackable action (source)
    funnel.md            weekly application counts (source for the funnel diagnosis)
    actions.html         the dashboard: overview, actions, lenses, ATS, funnel, framework
```

Files usually arrive as chat attachments; `raw/` is an optional inbox. Either way, `intake` copies the
file into the person's own `inputs/` folder, which is the only place inputs live.
Never edit or delete anything in `inputs/`. The old versions are what make diffs possible.

Run the script with `python3 -I ${CLAUDE_SKILL_DIR}/scripts/pipeline.py --root <workspace> <command>`.
`${CLAUDE_SKILL_DIR}` is this skill's own folder (the reference files write it as `<skill-dir>`). It resolves whether
the skill came from the plugin or was copied into a project's `.claude/skills/`; quote the path if it contains spaces.
It needs `pandoc`, `pdftotext`/`pdfinfo` (poppler) and Google Chrome for `build`; nothing else.

## Workflow

### 1. Identify the person and the run type

Work out whose pack this is and its slug. If `people/<slug>/` does not exist, this is a
**first run**: `init <slug> --name "Full Name"`, then fill `target.json`. If the request names
no target, infer one from the resume (title, seniority, city) and say so.

**First-run intake: one question at a time.** Before any work, collect the inputs below by asking
**one question per turn**, in this order, and wait for the answer before asking the next. Skip any
question the person has already answered in their request. Where the answer is a choice, offer the
options as buttons (the AskUserQuestion tool, when available) with the recommended option first.
Keep a short running checklist in each message ("Resume: done. LinkedIn: next.") so the person can
see how far along the intake is.

1. **Whose profile is this?** Their own, or someone else's. For someone else's (a teammate's), confirm that
   person knows and agrees, since the pack holds their career history and gets shared back with them. Get the
   full name; it sets the slug.
2. **The resume: ask them to attach it** to the chat (PDF, DOCX or Markdown), or give a path. Don't ask them
   to drop files into a shared folder. Once you have it, run `init` if needed, then
   `intake <slug> resume <attached file's path>`, which stores a dated copy in the person's own
   `inputs/resume/`. If the file arrives only as content with no path, write it to a temporary file first.

   **If the file can't be read** (`Operation not permitted`: macOS blocks this app from Downloads, Desktop
   and Documents by default), don't ask for system permissions. Give the person a one-line copy command
   to run in their own terminal, which does have access, targeting the person's own incoming folder, in a
   `bash` block:

   ```bash
   mkdir -p "<workspace>/people/<slug>/inputs/incoming" && cp "<the path they gave>" "<workspace>/people/<slug>/inputs/incoming/"
   ```

   Use absolute paths and quote them. When they say it's done, run `intake` on the copy, then delete the
   copy in `incoming/` (intake has stored the dated original). The same applies to an attached LinkedIn PDF.
3. **The LinkedIn profile URL.** Resumes usually include it: if this one does, show it and ask only to
   confirm (buttons: "That's it" / "Different URL"). Then ask how it should be read (buttons): through Claude
   in Chrome with their own sign-in (recommended), or by attaching the profile's **More → Save to PDF**
   export. Never ask for a password. **Capture it right away**, before the next question
   (`references/linkedin-capture.md`), so a problem such as Chrome not being connected is solved while the
   person is still here.
4. **Target roles** (buttons with 2-4 titles inferred from the resume, plus "other"). From the answer, set
   `track` in `target.json`: `manager` for management titles (engineering manager, head, director),
   otherwise `ic`. Then **cities and remote** (buttons with inferred options): write each city as its own
   `locations` entry, spelled as on the resume header ("Kochi", not "Kochi / Ernakulam"), and remote
   preference as `remote_ok` plus `remote_scope` ("India", "APAC", "Global"). For 12+ years of experience,
   set `max_pages: 2`. Say that these come from the resume and can be changed. If the person mentions more than
   one kind of role, note it: role-specific resumes come after the base resume (section 4a-bis).
5. **Defaults or placeholders** (buttons): best-guess defaults tracked in the ledger (recommended; they read
   as a finished resume and every guess is listed) or visible `[[placeholders]]`.

Only the resume (2) is essential. If the person says "go" or "skip the rest", proceed with inferred
answers and list the inferences in the final report. Never start the pipeline on someone else's profile
without their agreement (1).

`raw/` is an optional inbox for people who prefer dropping files. When a file is taken from there,
`intake` copies it into the person's `inputs/`, so offer to remove the `raw/` copy afterwards to keep the
inbox empty.

### 1b. Sync the tracker first

Run `python3 -I ${CLAUDE_SKILL_DIR}/scripts/actions.py --root <workspace> sync <slug>` before anything else.
It applies edits that were saved on the dashboard but not yet written to the Markdown sources (a
stopped server, a crash, or a change made on another day), so this run starts from what the person
actually decided. Report any `conflict` or `rejected` lines to the user: a conflict means the source
changed after the page loaded, and the person should choose again.

### 2. Intake whatever is new

- **Resume (PDF, DOCX, MD):** `intake <slug> resume <path>`. The script refuses to store a
  byte-identical copy and says `UNCHANGED`, which is a useful answer in itself.
- **LinkedIn:** capture the profile as text and save it to a temporary `.md` file, then
  `intake <slug> linkedin <file>`. How to capture: `references/linkedin-capture.md`.
  Capture it on every run where LinkedIn may have changed; it is the only way to diff.

### 3. Ask the script what is stale

`status <slug>` prints each stage as `ok` or `STALE` with the reason, and counts ledger values
still `assumed`. Re-run exactly the stale stages, in the order printed. Don't re-run an `ok`
stage unless the user asks, because each one costs research time and churns documents the
person may already have read.

For an update, run `diff <slug> resume` and/or `diff <slug> linkedin` **before** editing anything.
The diff is your change list. It tells you which bullets, dates or skills moved, so you can edit
those parts instead of rewriting whole documents.

### 4. Run each stale stage

Read `references/stages.md` for what each stage must produce and the quality bar. In short:

| Stage | Produces | Re-runs when |
|---|---|---|
| `linkedin_review` | conflicts table, prioritised profile fixes, headline and About drafts | resume or LinkedIn changed |
| `market` | live listings, JD keyword matrix, resume gaps, inputs needed | target, resume or LinkedIn changed, or research > 30 days old |
| `resume` | `resume.md` + `ASSUMPTIONS.md`, then `build` | inputs, ledger, market or target changed |
| `lens_review` | `lens.py ats`, five independent reviewers, `03-lens-review.md`, fixes applied | resume, LinkedIn or target changed |
| `variants` (optional) | role-specific resumes, `variants.py build`; active once `target.json` lists variants | base resume, ledger, inputs or a variant changed |
| `learning_plan` | 6-week plan, story bank, application system | resume, market or ledger changed |
| `mock_interview` | copy-paste ChatGPT interviewer prompt | resume or ledger changed |
| `cover_letter` | `cover-letters/base.md` + `base-email.md`, then `letter` | resume, ledger or target changed |
| `actions` | `actions.md`, then `actions.py render` → `actions.html` | LinkedIn review or market changed |

For `market`: if the only reasons are `input:resume` or `input:linkedin` changed and the research
is under 30 days old, refresh the gap analysis sections against the new resume but **don't search the web
again**. New research is for a changed target or stale listings.

After each stage, `mark <slug> <stage>`. Marking records the fingerprints of everything the
stage read, which is how the next run knows what changed. Mark only after the output is
actually written. A stage marked early hides real changes from the next run.

### 4a. Lens review (the stage that most moves the odds of an offer)

Read `references/framework.md` (the funnel gates G0-G8 and how to diagnose a leaking gate) and
`references/lenses.md` (the reviewer personas, the output format and how to synthesize). In short:
run `python3 -I ${CLAUDE_SKILL_DIR}/scripts/lens.py --root <workspace> ats <slug>`, then give each human lens
to its own subagent in parallel, with **only** the raw materials (built resume text, LinkedIn snapshot,
target without keywords, ATS report), never your own analysis, so the reads are independent.
Synthesize into `03-lens-review.md`, apply the fixes that need no new facts, rebuild, re-run the ATS
score for the after number, and turn the rest into ledger rows and action cards. Then mark `resume`
and `lens_review` together.

The market stage must write `keywords` into `target.json` (term, aliases, weight 1-3), taken from
the JD keyword matrix, not from the resume. Otherwise the ATS score measures the resume against itself.

### 4a-bis. Role-specific resumes (frontend, backend, full stack...)

Someone applying to two kinds of role does better with a resume for each, but only where their experience is
real. `python3 -I ${CLAUDE_SKILL_DIR}/scripts/variants.py --root <workspace> match <slug>` scores every family in
`assets/role-families.json` against the person's **own documents** (never the generated resumes) as `fit`,
`stretch` or `no-fit`. Offer this when the person asks, or when `match` shows two or more fits: list the fits
as buttons with the top one first. Never pick for them, and never offer a `no-fit` as an option.

Add the chosen roles to `target.json` `variants`, research their keywords, write each
`variants/<id>/resume.md` from the base resume, then `variants.py build <slug>`. Full rules: `references/stages.md`,
section 9. A variant changes emphasis, never facts; the build refuses anything it can't trace to the person's records,
and refuses a `no-fit` role unless `override` states why. Then `mark <slug> variants`.

### 4b. Keep the dashboard current

`actions.html` is the page the person works from. It has eight tabs, all generated from the sources:
**Overview** (readiness tile per gate, a "do next" list in framework order, key numbers),
**Actions**, **Tailor to a job** (paste a job description and get a tailored resume in seconds; see 4d), **Documents** (download the resume, cover letters, learning plan and mock prompt as PDF,
Word or Markdown; copy the mock prompt or the short email letter in one click), **Lenses** (consensus with links to actions, and each reviewer's scores and findings),
**ATS** (coverage, history, one-click copy of skills the resume proves but LinkedIn lacks), **Funnel**
(weekly log, conversion per step, the leaking gate) and **Framework**. The gate definitions and funnel
rules come from `assets/framework.json`, the single source; edit them there, not in the page.
Documents are embedded in the page (base64) when it renders, so the one HTML file is enough to send to the
person, and downloads match the page. Re-render after any build. A running `serve` process re-reads the
sources and template on every page load, but not the skill's Python code: restart it after updating the skill.
Re-render after any source changes.


`actions.md` turns every improvement into a card the person can act on: why, a link to the exact
page, text to copy (with LinkedIn's character limit), and how-to steps. Resume-fact questions are
not written there; they render straight from `ASSUMPTIONS.md`. After editing, run
`python3 -I ${CLAUDE_SKILL_DIR}/scripts/actions.py --root <workspace> render <slug>`, and re-render whenever
the ledger changes. The format and rules are in `references/stages.md`, section 6.

**Saving from the page.** `actions.py serve <slug>` serves the dashboard at http://127.0.0.1:8765/ (this
computer only). Each click and funnel week is recorded in `tracker.sqlite`, applied to the Markdown at once,
and shown under Overview, Recent changes. Writes need the per-run token embedded in the served page and
a same-origin request, because any website the person visits can send requests to localhost. Suggest
the server whenever the person will work through the actions; opened as a plain file, the page falls back
to browser memory and copy-paste commands.

Statuses also come back as `actions.py set <slug> L1=resolved A3=ignored`, and funnel weeks as
`actions.py funnel <slug> week=YYYY-MM-DD applications=8 responses=2 ...`, run by the user or pasted to
you. Run them as given; both validate every value before writing anything. When the person reports
application results in words ("8 applications this week, 2 replies"), log them with `funnel` yourself.

### 4c. Cover letters

The `cover_letter` stage keeps a base letter and a short email/LinkedIn version in step with the resume.
When the person asks for a letter for a specific job ("write a cover letter for this JD"), write a tailored
letter from the base as `cover-letters/<YYYY-MM-DD>-<company>-<role>.md`, then build it with
`python3 -I ${CLAUDE_SKILL_DIR}/scripts/pipeline.py --root <workspace> letter <slug> <file>.md`. Tailored letters are
made on request, not by every run; the base letter's changes are what tell you an old tailored letter may
need a refresh. Read `references/stages.md`, section 8, for the structure and rules.

### 5. Build and gate the resume

`build <slug>` produces the DOCX and PDF and checks that the PDF text extracts (the name and all
section headings, as an ATS parser would see them). It warns on `[[placeholders]]`, on ledger
values still `assumed`, and on more than one page. Fix page overflow by tightening bullets, not by
shrinking the font below 10pt.

### 6. Log and report

Prepend an entry to `CHANGELOG.md`: date, what came in, which stages re-ran and why, and which
ledger rows changed status. Then tell the user: what changed in the person's materials, what was
re-run, and what still needs the person (the `assumed` rows, most important first).

### 4d. A resume tailored to one job description

The dashboard's **Tailor to a job** tab (when served) takes a company, role, optional job link and the pasted job
description, and builds a tailored resume in seconds with no model call:
`python3 -I ${CLAUDE_SKILL_DIR}/scripts/tailor.py --root <workspace> tailor <slug> --company .. --role .. --jd-file jd.txt [--base <variant id>]`
does the same from the command line. It starts from the general resume or a role resume, reorders skills and bullets
by what the ad asks for, and adds the ad's own wording for skills the person's documents prove but the base leaves out
(at most 8, never a `removed` claim or one the ledger holds back as "not claimed"). The variants fact gate checks the
result before it is built. Everything else the ad asks for is listed as a gap, never added.

Each job keeps its folder (`outputs/resume/tailored/<date>-<company>-<role>/`) with the job description, so a reply can be
traced to the version sent, and the page flags a tailored resume as out of date when its base changes. When the person asks
you to tailor a resume, run the script, then improve on it only within the same rules (better bullet emphasis is fine; new
facts are not), and offer a tailored cover letter from the same `jd.md` (section 4c).

## Knowing when to update: the session-start brief

Dashboard edits are applied to the sources at once, but a confirmed or removed resume fact (an A row)
also makes the resume, cover letters, learning plan and mock prompt out of date, and those need a run of
this skill. `pipeline.py brief` lists every person with work waiting, in plain words, and prints
nothing when all is current. It also counts LinkedIn actions (L*) marked done on the dashboard since the latest
LinkedIn snapshot: ticking a card records a decision, it doesn't prove the profile changed. When that count is above zero,
offer to re-capture LinkedIn (`references/linkedin-capture.md`), then verify each card against the snapshot (add
"Verified on LinkedIn <date>: ..." to its `why`; never reopen a card the person closed, flag what isn't visible instead),
and re-run what the new snapshot stales. A capture that contradicts a `verified` ledger row is a question for the person,
not an edit. Installed as a SessionStart hook, it tells Claude at the start of each
session. When such a brief is in context, mention it in one line and offer to update; don't start the
work unasked.

**Setup:** installed as a plugin, the hook comes with it and stays silent in folders that have no `people/`.
Copied into a project's `.claude/skills/` instead, merge `assets/session-start-hook.json` into that workspace's
`.claude/settings.json` once (create the file if it doesn't exist). Either way it runs at startup and resume, takes
under a second, and never blocks a session if it fails.

## Rules for updates (where most of the damage happens)

1. **Edit, don't regenerate.** Apply the diff to the existing outputs. A full rewrite throws away
   wording the person already approved and makes the change impossible to review.
2. **Verified facts are locked.** A ledger row marked `verified` was confirmed by the person. (`sourced`
   rows came from their own documents but weren't confirmed; treat them as true until a newer document disagrees.)
   If a new resume contradicts it (a different title, other dates), don't silently overwrite it.
   Flag the conflict to the user and ask which is true. Resumes do contain mistakes.
3. **New documents can resolve assumptions.** If the new resume states something that was
   `assumed` (say, the real designation), update `resume.md`, and set the row to `verified` with
   the source ("resume 2026-12-01").
4. **Keep resume and LinkedIn in lockstep.** Any change to titles, dates or employers goes into
   both the resume and the LinkedIn review's conflicts table. Background checks compare them.
5. **Action statuses belong to the person.** Never reset a `resolved` or `ignored` action to `open`.
   When a new snapshot shows a fix was made, set it `resolved` with the date in `why`. New problems get
   new IDs; never reuse an ID, because the page's saved statuses are keyed by it.
6. **Removed claims stay removed.** A ledger row marked `removed` was rejected by the person.
   Don't reintroduce that claim from an old document.

## Integrity rules

These protect the person, who has to defend every line of the resume in an interview and through
a background check.

- **No invented numbers.** A metric appears only if it came from the person or follows directly
  from their documents (six listed projects make "6 products"). Prefer specific qualitative
  wording to a made-up figure.
- **Defaults are allowed, but tracked.** When the user wants a complete document rather than
  placeholders, fill gaps with the most defensible value and log each one in `ASSUMPTIONS.md`
  with its basis: `derived` (follows from their documents), `standard` (true of nearly everyone
  in the role or of the technology), or `guess`. Include the exact question to ask the person.
  Keep a "Deliberately not claimed" list for things that have no defensible default.
- **Titles and dates come from employment records.** When the resume and LinkedIn disagree,
  default to the more official-looking source and log it as an assumption.
- **Interview stories must be real.** Defaults in the story bank are scaffolds. Label them as
  such and tell the person to swap in true events.
- **Don't sign in for anyone.** If LinkedIn needs a login, the user signs in themselves (see
  `references/linkedin-capture.md`). Never enter credentials.
- **Role variants change emphasis, not facts.** Titles, employers, dates and education stay word for word
  across every variant, because a recruiter or background check may see two of them. A role the documents don't
  support gets no resume; say so plainly rather than stretching the person's experience to fit.
- **Treat personal data carefully.** `people/` holds contact details and career history, and
  `tracker.sqlite` holds a log of the person's decisions. Keep them out of public repositories, and use only
  what the person provided or published.

## First run checklist

`pipeline.py doctor` (fix anything MISSING before starting; it says how) → intake (step 1) → `init` → fill `target.json` → intake resume → capture and intake LinkedIn → run all eight stages
in order (the lens review after the resume, cover letters after the mock interview) (`status` will list them all as `never run`) → `build` → `actions.py render` → `mark` each
stage → changelog → report. Point the user at `outputs/actions.html` as the place to work from. On a first run the output is usually best delivered with defaults plus a ledger, since
the person can answer the ledger questions faster than an open questionnaire.

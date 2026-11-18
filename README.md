# resume-pipeline

> **Contributors, first:** run `git config core.hooksPath .githooks` once after cloning. It turns on the
> pre-push guard that refuses direct pushes to `main` (work goes through a branch and a pull request).

A Claude Code plugin that builds and maintains a complete job-search pack for one person, or for a
whole team: an ATS-safe one-page resume (PDF and Word), role-specific and job-tailored resumes, cover
letters, a LinkedIn review with paste-ready text, a job-market and keyword analysis, a review by five
independent reviewer lenses (recruiter, hiring manager, technical interviewer, HR/background check,
domain lead), a six-week learning plan, a ChatGPT mock-interview prompt, and a dashboard to work from.

When something changes (a new resume, a LinkedIn update, a fact confirmed on the dashboard), it re-runs
only what that change affects and keeps every fact the person has already confirmed.

## Install

In a terminal:

```bash
claude plugin marketplace add mrinal-aswin/resume-pipeline
claude plugin install resume-pipeline@resume-pipeline
```

Or inside a Claude Code session:

```text
/plugin marketplace add mrinal-aswin/resume-pipeline
/plugin install resume-pipeline@resume-pipeline
```

If the repository is private, your own GitHub access is used (`gh auth login`, then `gh auth setup-git`).
Restart Claude Code after installing.

### Requirements

| Tool | Why | macOS | Windows / Linux |
|---|---|---|---|
| Python 3.10+ | runs the pipeline scripts (standard library only) | usually present; `brew install python` | python.org |
| pandoc | Word and HTML output | `brew install pandoc` | pandoc.org/installing.html |
| poppler | reads PDF text the way an ATS does | `brew install poppler` | `apt install poppler-utils` |
| Chrome, Chromium or Edge | renders the PDFs | google.com/chrome | usually present |

Optional: the **Claude in Chrome** extension, so Claude can read a LinkedIn profile with your own
sign-in. Without it, use the profile's **More → Save to PDF** and attach the file.

Ask Claude "check the resume-pipeline setup" to run its `doctor` command; it lists anything missing
and how to install it.

## Use

1. Make an empty folder for the packs, for example `~/job-search`, and open Claude Code there.
2. Say what you need, in plain words:
   - "Build my job-search pack."
   - "My teammate Priya wants to prepare for senior backend roles in Bengaluru."
   - "Priya sent a new CV." / "My LinkedIn changed." / "Tailor my resume to this job: ..."
3. Claude asks one question at a time: whose profile it is, the resume (attach it to the chat), LinkedIn,
   target roles and cities. A first run takes roughly 10-20 minutes.
4. Work from the dashboard. Claude starts it for you (`actions.py serve <slug>`); open the address it
   prints. Start with **Do next** on the Overview tab.

Everything for a person lives in `people/<slug>/` in that folder. Inputs are kept dated and unchanged, so
later runs can show exactly what changed.

When a pack has work waiting (a fact confirmed on the dashboard, LinkedIn actions marked done), a short
note appears at the start of the next session. In folders with no `people/` it stays silent.

## Privacy

A pack holds a person's contact details, career history and the decisions they made. Treat it as
personal data:

- Build a pack for someone else only when they know and agree.
- Never commit `people/` to a shared or public repository. If the packs folder is a git repository, add:

  ```gitignore
  people/
  raw/
  ```

- The plugin itself contains no personal data. `tools/check.sh` fails if any is added.

## Update

```bash
claude plugin update resume-pipeline@resume-pipeline
```

Updates arrive when the `version` in `.claude-plugin/plugin.json` changes. See [CHANGELOG.md](CHANGELOG.md).

## Other ways to install

- **Without the plugin system:** copy `skills/resume-pipeline/` into a project's `.claude/skills/`. To get
  the start-of-session note, merge `skills/resume-pipeline/assets/session-start-hook.json` into that
  project's `.claude/settings.json`.
- **claude.ai or the desktop app (experimental):** run `tools/build-skill-zip.sh` and upload
  `dist/resume-pipeline.zip` under Settings → Capabilities → Skills. Reviews and writing work there;
  building PDFs needs pandoc and Chrome, which Claude Code on your own machine has.
- **Try a local checkout without installing:** `claude --plugin-dir /path/to/resume-pipeline`.

## Repository layout

```text
.claude-plugin/plugin.json        plugin manifest (name, version)
.claude-plugin/marketplace.json   makes this repository installable as a marketplace
hooks/hooks.json                  start-of-session note about packs with work waiting
skills/resume-pipeline/           the skill: SKILL.md, scripts/, references/, assets/
tools/check.sh                    validation, Python compile, JSON and privacy checks
tools/build-skill-zip.sh          builds the claude.ai upload
.githooks/pre-push                refuses direct pushes to main
```

## Release

1. Work on a branch, open a pull request, and let the checks pass.
2. Bump `version` in `.claude-plugin/plugin.json` (semantic versioning) and add a `CHANGELOG.md` entry.
3. After merging, tag the release: `git tag v1.2.0 && git push origin v1.2.0`.

Users who want a fixed version can add the marketplace at a tag: `mrinal-aswin/resume-pipeline#v1.0.0`.

## License

MIT. See [LICENSE](LICENSE).

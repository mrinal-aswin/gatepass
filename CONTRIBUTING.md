# Contributing

## First, once per clone

```bash
git config core.hooksPath .githooks
```

This turns on the pre-push guard that refuses direct pushes to `main`. Git doesn't copy this setting
when you clone, so without the command the guard does nothing. It's a guardrail, not a security control:
`git push --no-verify` gets past it for a genuine hotfix.

## How changes land

1. Open an issue that describes the change.
2. Make a branch named `<issue number>-<short-slug>`, for example `12-funnel-floor`, linked to the issue.
3. Commit and push to that branch only.
4. Open a pull request whose description says `Closes #<issue number>`.
5. The `checks` workflow runs `tools/check.sh` (plugin validation, Python compile, JSON syntax and the
   privacy guard). Merge once it passes and the change is reviewed.

Run the same checks locally before pushing:

```bash
bash tools/check.sh
```

## Releasing

1. In the pull request, bump `version` in `.claude-plugin/plugin.json` (semantic versioning) and add a
   `CHANGELOG.md` entry. Installed copies only update when this version changes.
2. After merging, tag the release from `main`:

   ```bash
   git tag -a v1.2.0 -m "resume-pipeline 1.2.0" && git push origin v1.2.0
   ```

Users who want a fixed version can add the marketplace at a tag: `mrinal-aswin/resume-pipeline#v1.0.0`.

## Repository layout

```text
.claude-plugin/plugin.json        plugin manifest (name, version, license)
.claude-plugin/marketplace.json   makes this repository installable as a marketplace
hooks/hooks.json                  start-of-session note about packs with work waiting
skills/resume-pipeline/           the skill: SKILL.md, scripts/, references/, assets/
tools/check.sh                    validation, Python compile, JSON and privacy checks
tools/build-skill-zip.sh          builds the claude.ai upload
.githooks/pre-push                refuses direct pushes to main
.github/workflows/checks.yml      runs tools/check.sh on pull requests, main and tags
```

## Ground rules

- **No personal data, ever.** No real resumes, names, emails or packs in this repository, including in
  tests and examples. Use invented people.
- **Edit the skill here, not in a workspace copy.** A workspace uses the installed plugin.

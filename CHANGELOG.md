# Changelog

All notable changes to this plugin. Versions follow `.claude-plugin/plugin.json`.

## 1.0.0 (2026-11-18)

First release as a Claude Code plugin.

- **Pipeline:** eight stages (LinkedIn review, job market, resume, lens review, learning plan, mock interview,
  cover letter, actions) with fingerprinted staleness, so updates re-run only what changed.
- **Resumes:** ATS-safe resume builds (PDF and Word) with a text-extraction gate; role-specific resumes with a fact
  gate; job-tailored resumes from a pasted job description.
- **Reviews:** deterministic ATS scoring; five independent reviewer lenses.
- **Dashboard:** Overview, Actions, Documents, Tailor, Lenses, ATS, Funnel and Framework tabs; saves through a local
  server to an event log.
- **Funnel diagnosis:** a per-stage warning line, so a weak first step is flagged before later steps have data.
- **Hooks:** a start-of-session note for packs with work waiting, silent in folders without `people/`.
- **Input order:** the order files arrive is recorded in `state.json`, so moving, copying or cloning a packs folder
  can't make an older same-day resume or LinkedIn capture count as the latest.
- **Portability:** copy-paste commands on the dashboard name the skill's real location, so they work from a plugin
  install as well as a project copy.

#!/usr/bin/env bash
# Checks run before every release and in CI: plugin validation, Python compile, JSON syntax,
# and a privacy guard that keeps personal data out of the repository.
set -euo pipefail
cd "$(dirname "$0")/.."

SKILL=skills/resume-pipeline
fail=0
say() { printf '%s\n' "$*"; }

say "== Python compiles"
python3 -I -m py_compile "$SKILL"/scripts/*.py
find "$SKILL" -name __pycache__ -type d -prune -exec rm -rf {} +

say "== JSON parses"
for f in .claude-plugin/*.json hooks/hooks.json "$SKILL"/assets/*.json; do
  python3 -I -c 'import json, sys; json.load(open(sys.argv[1]))' "$f" || { say "bad JSON: $f"; fail=1; }
done

say "== Skill name matches its folder"
name=$(sed -n 's/^name: *//p' "$SKILL/SKILL.md" | head -1)
[ "$name" = "resume-pipeline" ] || { say "SKILL.md name is '$name', expected resume-pipeline"; fail=1; }

say "== Privacy guard"
# No pack folders, trackers, documents or email addresses anywhere in the shipped files.
if find . -path ./.git -prune -o \( -name people -o -name raw \) -type d -print | grep -q .; then
  say "a people/ or raw/ folder is present"; fail=1
fi
if find . -path ./.git -prune -o -path ./dist -prune -o -type f \( -name '*.sqlite' -o -name '*.pdf' -o -name '*.docx' \) -print | grep -q .; then
  say "a tracker, PDF or Word file is present"; fail=1
fi
if grep -rIEn '[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.[A-Za-z.]{2,}' --exclude-dir=.git --exclude-dir=dist . \
   | grep -vE 'noreply@|@example\.(com|org)|gh auth' ; then
  say "an email address is present (above)"; fail=1
fi

say "== Plugin and marketplace validate"
if command -v claude >/dev/null 2>&1; then
  claude plugin validate . || fail=1
else
  say "claude CLI not found; skipped (CI installs it)"
fi

[ "$fail" -eq 0 ] && say "All checks passed." || { say "Checks failed."; exit 1; }

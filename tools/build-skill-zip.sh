#!/usr/bin/env bash
# Builds dist/resume-pipeline.zip for upload to claude.ai or the desktop app.
# The archive's top level must be the skill folder (resume-pipeline/SKILL.md), not SKILL.md itself.
set -euo pipefail
cd "$(dirname "$0")/.."
tools/check.sh >/dev/null
mkdir -p dist
rm -f dist/resume-pipeline.zip
(cd skills && zip -qr ../dist/resume-pipeline.zip resume-pipeline -x '*__pycache__*' '*.DS_Store')
unzip -Z1 dist/resume-pipeline.zip | grep -qv '^resume-pipeline/' && { echo "unexpected top-level entry"; exit 1; }
echo "Built dist/resume-pipeline.zip ($(unzip -Z1 dist/resume-pipeline.zip | grep -vc '/$') files)"

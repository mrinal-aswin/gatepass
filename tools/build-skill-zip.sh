#!/usr/bin/env bash
# Builds dist/gatepass.zip for upload to claude.ai or the desktop app.
# The archive's top level must be the skill folder (gatepass/SKILL.md), not SKILL.md itself.
set -euo pipefail
cd "$(dirname "$0")/.."
tools/check.sh >/dev/null
mkdir -p dist
rm -f dist/gatepass.zip
(cd skills && zip -qr ../dist/gatepass.zip gatepass -x '*__pycache__*' '*.DS_Store')
unzip -Z1 dist/gatepass.zip | grep -qv '^gatepass/' && { echo "unexpected top-level entry"; exit 1; }
echo "Built dist/gatepass.zip ($(unzip -Z1 dist/gatepass.zip | grep -vc '/$') files)"

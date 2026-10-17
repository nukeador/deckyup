#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/check-version.py
pnpm build
python3 scripts/package.py
python3 scripts/validate-package.py dist-release/Decky-Direct-Updater.zip

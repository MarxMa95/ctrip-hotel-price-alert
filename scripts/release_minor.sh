#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LEGACY_APP_PATH="$APP_DIR/hotel_price_alert/legacy_app.py"
README_PATH="$APP_DIR/README.md"

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

cd "$APP_DIR"

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    echo "Missing required command: $name"
    exit 1
  fi
}

require_command git
require_command gh
require_command python3

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo 'This script must be run inside a Git repository.'
  exit 1
fi

if [[ "$DRY_RUN" -eq 0 ]] && [[ -n "$(git status --short)" ]]; then
  echo 'Working tree is not clean. Commit or stash your changes before releasing.'
  git status --short
  exit 1
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  gh auth status >/dev/null
fi

latest_tag="$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | sort -V | tail -1)"
if [[ -z "$latest_tag" ]]; then
  latest_tag='v0.0.0'
fi

if [[ ! "$latest_tag" =~ ^v([0-9]+)\.([0-9]+)\.([0-9]+)$ ]]; then
  echo "Latest tag does not look like semver: $latest_tag"
  exit 1
fi

major="${match[1]}"
minor="${match[2]}"
next_tag="v${major}.$((minor + 1)).0"

echo "Current tag: $latest_tag"
echo "Next minor release: $next_tag"

if git rev-parse "$next_tag" >/dev/null 2>&1; then
  echo "Tag already exists: $next_tag"
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo ''
  echo '[Dry run] No files were changed.'
  echo "[Dry run] Would update: $LEGACY_APP_PATH"
  echo "[Dry run] Would update: $README_PATH"
  echo '[Dry run] Would run: ./scripts/run_core_checks.sh'
  echo '[Dry run] Would run: ./scripts/prepublish_check.sh'
  echo "[Dry run] Would commit: Release $next_tag"
  echo "[Dry run] Would push branch and tag, then create GitHub release $next_tag"
  exit 0
fi

python3 - "$LEGACY_APP_PATH" "$README_PATH" "$next_tag" <<'PY'
from pathlib import Path
import re
import sys

legacy_app = Path(sys.argv[1])
readme = Path(sys.argv[2])
next_tag = sys.argv[3]

legacy_text = legacy_app.read_text(encoding='utf-8')
legacy_text, legacy_count = re.subn(
    r"APP_BUILD_VERSION = 'v\d+\.\d+\.\d+'",
    f"APP_BUILD_VERSION = '{next_tag}'",
    legacy_text,
    count=1,
)
if legacy_count != 1:
    raise SystemExit('Failed to update APP_BUILD_VERSION in legacy_app.py')
legacy_app.write_text(legacy_text, encoding='utf-8')

readme_text = readme.read_text(encoding='utf-8')
readme_text, readme_count = re.subn(
    r"The current release is `v\d+\.\d+\.\d+`",
    f"The current release is `{next_tag}`",
    readme_text,
    count=1,
)
if readme_count != 1:
    raise SystemExit('Failed to update the current release line in README.md')
readme.write_text(readme_text, encoding='utf-8')
PY

./scripts/run_core_checks.sh
./scripts/prepublish_check.sh

git add "$LEGACY_APP_PATH" "$README_PATH"
git commit -m "Release $next_tag"
git push origin main
git tag -a "$next_tag" -m "Release $next_tag"
git push origin "$next_tag"
gh release create "$next_tag" --title "$next_tag" --generate-notes

echo ''
echo "Release completed: $next_tag"

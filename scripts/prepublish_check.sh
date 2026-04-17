#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

cd "$APP_DIR"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo 'No usable python3 interpreter was found. Cannot run the pre-publish check.'
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import re
import subprocess
import sys
from pathlib import Path

repo = Path.cwd()
inside_git = subprocess.run(
    ['git', 'rev-parse', '--is-inside-work-tree'],
    cwd=repo,
    capture_output=True,
    text=True,
).returncode == 0

print('==> Starting pre-publish check')
print(f'Working directory: {repo}')
print(f"Git repository: {'yes' if inside_git else 'no'}")

if inside_git:
    tracked = subprocess.run(
        ['git', 'ls-files', '-z'],
        cwd=repo,
        capture_output=True,
        check=True,
    ).stdout.decode('utf-8', errors='ignore').split('\0')
    scan_files = [item for item in tracked if item]
    scan_mode_label = 'Git-tracked files'
else:
    scan_files = []
    for path in repo.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        if rel.startswith('.git/'):
            continue
        scan_files.append(rel)
    scan_mode_label = 'Current project files (non-Git preview mode)'

sensitive_prefixes = ('logs/', 'session_profiles/', 'debug_screens/')

print('1/3 Check sensitive runtime data')
sensitive_hits = []
for path in scan_files:
    if path == 'data.db' or path.startswith(sensitive_prefixes):
        sensitive_hits.append(path)

if inside_git:
    if sensitive_hits:
        print('Found runtime files/directories that should not be committed but are already tracked by Git:')
        for item in sensitive_hits[:50]:
            print(f'  - {item}')
        if len(sensitive_hits) > 50:
            print(f'  ... remaining {len(sensitive_hits) - 50} items omitted')
    else:
        print('  OK: data.db, session_profiles/, logs/, and debug_screens/ are not tracked')
else:
    if sensitive_hits:
        print('  Note: local runtime data exists in this directory; as long as it remains ignored, it will not be committed.')
        print(f'  Found {len(sensitive_hits)} local runtime files; detailed listing was skipped.')
    else:
        print('  OK: no local data.db, session_profiles/, logs/, or debug_screens/ entries were found here')

print('2/3 Check that .gitignore covers the key runtime directories')
ignore_expect = ['data.db', 'logs/', 'session_profiles/', 'debug_screens/']
missing_ignore = []
try:
    gitignore_text = (repo / '.gitignore').read_text(encoding='utf-8')
except FileNotFoundError:
    gitignore_text = ''
for item in ignore_expect:
    if item not in gitignore_text:
        missing_ignore.append(item)
if missing_ignore:
    print('Missing recommended .gitignore entries:')
    for item in missing_ignore:
        print(f'  - {item}')
else:
    print('  OK: .gitignore already covers the key runtime directories')

print(f'3/3 Scan {scan_mode_label} for suspicious real webhook URLs')
patterns = [
    ('Feishu', re.compile(r'https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9_-]{20,}')),
    ('WeCom', re.compile(r'https://qyapi\.weixin\.qq\.com/cgi-bin/webhook/send\?key=[A-Za-z0-9_-]{16,}')),
    ('Slack', re.compile(r'https://hooks\.slack\.com/services/[A-Za-z0-9/_-]{20,}')),
]
allow_markers = {
    'example', 'examples', 'sample', 'samples', 'test', 'tests', 'dummy',
    'placeholder', 'your-', 'your_', 'replace-me', 'replace_with', 'xxxx',
    'token-here', 'webhook-here',
}
webhook_hits = []
for rel_path in scan_files:
    if rel_path == 'data.db' or rel_path.startswith(sensitive_prefixes) or rel_path.startswith('.git/'):
        continue
    path = repo / rel_path
    if not path.is_file():
        continue
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except Exception:
        continue
    for source, pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group(0)
            lowered = value.lower()
            if any(marker in lowered for marker in allow_markers):
                continue
            webhook_hits.append((rel_path, source, value))

if webhook_hits:
    print('Found suspicious real webhook URLs. Please confirm they are not committed:')
    for rel_path, source, value in webhook_hits[:20]:
        masked = value[:48] + '...' if len(value) > 48 else value
        print(f'  - [{source}] {rel_path}: {masked}')
    if len(webhook_hits) > 20:
        print(f'  ... remaining {len(webhook_hits) - 20} items omitted')
else:
    print('  OK: no suspicious real webhook URLs were found')

issues = bool(missing_ignore or webhook_hits or (inside_git and sensitive_hits))
print('')
if inside_git:
    if issues:
        print('Result: failed. Please clean up the repository before publishing to GitHub.')
        print('Recommendation: run `git status` and `git diff --cached` to confirm that local runtime data and real webhooks are not included.')
        sys.exit(1)
    print('Result: passed. You can continue with `git status`, `git add`, and `git commit`.')
else:
    if issues:
        print('Result: preview check failed. This is not a Git repository yet, but there are still source or ignore-rule risks to resolve.')
        print('Recommendation: fix the issues first, then run `git init` and `git add`.')
        sys.exit(1)
    print('Result: preview check passed. This is not a Git repository yet; run this script again after Git is initialized for the final check.')
PY

#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

cd "$APP_DIR"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo '未找到可用的 python3，无法执行上传前自检。'
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

print('==> 上传前自检开始')
print(f'工作目录: {repo}')
print(f"Git 仓库: {'是' if inside_git else '否'}")

if inside_git:
    tracked = subprocess.run(
        ['git', 'ls-files', '-z'],
        cwd=repo,
        capture_output=True,
        check=True,
    ).stdout.decode('utf-8', errors='ignore').split('\0')
    scan_files = [item for item in tracked if item]
    scan_mode_label = 'Git 已跟踪文件'
else:
    scan_files = []
    for path in repo.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        if rel.startswith('.git/'):
            continue
        scan_files.append(rel)
    scan_mode_label = '当前项目源码文件（非 Git 模式预检）'

sensitive_prefixes = ('logs/', 'session_profiles/', 'debug_screens/')

print('1/3 检查敏感运行数据')
sensitive_hits = []
for path in scan_files:
    if path == 'data.db' or path.startswith(sensitive_prefixes):
        sensitive_hits.append(path)

if inside_git:
    if sensitive_hits:
        print('发现不应提交但已经被 Git 跟踪的运行时文件/目录：')
        for item in sensitive_hits[:50]:
            print(f'  - {item}')
        if len(sensitive_hits) > 50:
            print(f'  ... 其余 {len(sensitive_hits) - 50} 项未展开')
    else:
        print('  OK：未发现 data.db、session_profiles/、logs/、debug_screens/ 被跟踪')
else:
    if sensitive_hits:
        print('  提示：当前目录存在本地运行数据；只要保持忽略，不会随 Git 上传。')
        print(f'  共发现 {len(sensitive_hits)} 个本地运行文件，已跳过逐项展开。')
    else:
        print('  OK：当前目录未发现 data.db、session_profiles/、logs/、debug_screens/')

print('2/3 检查 .gitignore 是否覆盖关键运行目录')
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
    print('缺少建议的 .gitignore 项：')
    for item in missing_ignore:
        print(f'  - {item}')
else:
    print('  OK：.gitignore 已覆盖关键运行目录')

print(f'3/3 扫描{scan_mode_label}中的疑似真实 webhook')
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
    print('发现疑似真实 webhook，请确认不要提交：')
    for rel_path, source, value in webhook_hits[:20]:
        masked = value[:48] + '...' if len(value) > 48 else value
        print(f'  - [{source}] {rel_path}: {masked}')
    if len(webhook_hits) > 20:
        print(f'  ... 其余 {len(webhook_hits) - 20} 项未展开')
else:
    print('  OK：未发现疑似真实 webhook')

issues = bool(missing_ignore or webhook_hits or (inside_git and sensitive_hits))
print('')
if inside_git:
    if issues:
        print('结果：未通过，请先清理后再上传到 GitHub。')
        print('建议：执行 `git status`、`git diff --cached`，确认没有把本地运行数据或真实 webhook 带进去。')
        sys.exit(1)
    print('结果：通过，可以继续执行 `git status` / `git add` / `git commit`。')
else:
    if issues:
        print('结果：预检未通过。当前还不是 Git 仓库，但源码或忽略规则里仍有风险。')
        print('建议：先修复，再 `git init` / `git add`。')
        sys.exit(1)
    print('结果：预检通过。当前还不是 Git 仓库；后续初始化 Git 后可再次运行本脚本做正式检查。')
PY

#!/bin/zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"

cd "$APP_DIR"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo '未找到可用 Python，请先安装 Python 3。'
  exit 1
fi

echo ''
echo '==> Playwright 初始化与浏览器冒烟检查'
"$PYTHON_BIN" - <<'PY'
from hotel_price_alert.legacy_app import resolve_chromium_executable
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    executable_path = resolve_chromium_executable()
    browser = playwright.chromium.launch(executable_path=executable_path, headless=True)
    page = browser.new_page()
    page.goto('about:blank')
    print(f'OK executable={executable_path}')
    browser.close()
PY

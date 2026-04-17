from pathlib import Path
import importlib.util
import sys

CACHE_DIR = Path.home() / 'Library' / 'Caches' / 'ms-playwright'
CANDIDATE_PATTERNS = [
    'chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium',
    'chromium-*/chrome-mac-arm64/Chromium.app/Contents/MacOS/Chromium',
    'chromium-*/chrome-mac/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
    'chromium-*/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing',
]
SYSTEM_CANDIDATES = [
    Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
    Path('/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing'),
    Path('/Applications/Chromium.app/Contents/MacOS/Chromium'),
    Path('/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'),
]


def list_browsers() -> list[Path]:
    results: list[Path] = []
    for pattern in CANDIDATE_PATTERNS:
        results.extend(sorted(CACHE_DIR.glob(pattern)))
    results.extend(SYSTEM_CANDIDATES)
    seen = set()
    ordered = []
    for path in results:
        if path.exists() and str(path) not in seen:
            seen.add(str(path))
            ordered.append(path)
    return ordered


def main() -> int:
    print('开始自检...')
    print(f'Python: {sys.executable}')
    print(f'Python 版本: {sys.version.split()[0]}')

    if not importlib.util.find_spec('playwright'):
        print('❌ 缺少 playwright Python 包')
        print('建议：运行 `python3 -m pip install playwright`')
        return 1
    print('✅ 已找到 playwright Python 包')

    if CACHE_DIR.exists():
        print(f'✅ 缓存目录存在: {CACHE_DIR}')
    else:
        print(f'⚠️ 未找到 Playwright 浏览器缓存目录: {CACHE_DIR}')
        print('将尝试使用系统已安装的浏览器')

    browsers = list_browsers()
    if not browsers:
        print('❌ 未找到可用的 Chromium/Chrome/Edge 可执行文件')
        print('建议：安装 Google Chrome，或运行 `python3 -m playwright install chromium`')
        return 1

    print('✅ 找到这些可尝试的浏览器：')
    for browser in browsers:
        print(f'  - {browser}')

    from playwright.sync_api import sync_playwright
    errors: list[str] = []
    with sync_playwright() as p:
        for browser_path in browsers:
            print(f'尝试启动: {browser_path}')
            try:
                browser_obj = p.chromium.launch(executable_path=str(browser_path), headless=True)
                page = browser_obj.new_page()
                page.set_content('<html><body>ok</body></html>')
                text = page.locator('body').inner_text()
                browser_obj.close()
                if text.strip() != 'ok':
                    raise RuntimeError('浏览器启动了，但页面渲染异常')
                print(f'✅ 浏览器启动测试通过: {browser_path}')
                print('✅ 自检通过，可以启动价格提醒服务')
                return 0
            except Exception as exc:
                errors.append(f'{browser_path}: {exc}')
                print(f'❌ 启动失败: {browser_path}')

    print('❌ 所有候选浏览器都启动失败')
    print('建议：先关闭所有 Chrome 窗口后重试；如果还失败，把这段报错发我。')
    for item in errors:
        print(f'  - {item}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

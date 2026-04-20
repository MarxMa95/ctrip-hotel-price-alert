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
    print('Starting environment check...')
    print(f'Python: {sys.executable}')
    print(f'Python version: {sys.version.split()[0]}')

    if not importlib.util.find_spec('playwright'):
        print('❌ Missing the playwright Python package')
        print('Suggested fix: run `python3 -m pip install playwright`')
        return 1
    print('✅ Found the playwright Python package')

    if CACHE_DIR.exists():
        print(f'✅ Browser cache directory exists: {CACHE_DIR}')
    else:
        print(f'⚠️ Playwright browser cache directory not found: {CACHE_DIR}')
        print('Will try to use a system-installed browser instead')

    browsers = list_browsers()
    if not browsers:
        print('❌ No usable Chromium/Chrome/Edge executable was found')
        print('Suggested fix: install Google Chrome, or run `python3 -m playwright install chromium`')
        return 1

    print('✅ Found these browser candidates:')
    for browser in browsers:
        print(f'  - {browser}')

    from playwright.sync_api import sync_playwright
    errors: list[str] = []
    with sync_playwright() as p:
        for browser_path in browsers:
            print(f'Trying to launch: {browser_path}')
            try:
                browser_obj = p.chromium.launch(executable_path=str(browser_path), headless=True)
                page = browser_obj.new_page()
                page.set_content('<html><body>ok</body></html>')
                text = page.locator('body').inner_text()
                browser_obj.close()
                if text.strip() != 'ok':
                    raise RuntimeError('The browser launched, but page rendering failed')
                print(f'✅ Browser launch test passed: {browser_path}')
                print('✅ Environment check passed. The app should be able to start')
                return 0
            except Exception as exc:
                errors.append(f'{browser_path}: {exc}')
                print(f'❌ Launch failed: {browser_path}')

    print('❌ All browser candidates failed to launch')
    print('Suggested fix: close all Chrome windows and try again. If it still fails, share the errors below.')
    for item in errors:
        print(f'  - {item}')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())

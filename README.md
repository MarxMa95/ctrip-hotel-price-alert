# Ctrip Hotel Price Alert

[![Release](https://img.shields.io/github/v/release/MarxMa95/ctrip-hotel-price-alert)](https://github.com/MarxMa95/ctrip-hotel-price-alert/releases)
[![License](https://img.shields.io/github/license/MarxMa95/ctrip-hotel-price-alert)](https://github.com/MarxMa95/ctrip-hotel-price-alert/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](https://www.apple.com/macos/)

Local hotel price monitoring for `Ctrip` with browser-assisted page access and IM webhook notifications.

## Features
- Monitor a hotel or a specific room type by keyword
- Notify on price drop or target price hit
- Support `Feishu` and `WeCom` robot webhooks
- Show recent trend, all-time low, and latest low occurrence time
- Keep full price history from now on
- Run locally on your own machine

## Screenshots / UI Summary
Each watcher card shows:
- current price
- target price
- minimum expected price
- recent trend chart
- all-time low price
- latest occurrence time of that low price
- last check time and next scheduled check

## Requirements
- macOS
- Python 3.11+
- `playwright`
- A local Chrome / Chromium / Edge installation, or Playwright-managed Chromium

Install dependencies if needed:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

## Quick Start

### Start the app

```bash
python3 app.py
```

Then open:

```text
http://127.0.0.1:8766
```

### Or use the included launcher

- `携程酒店提醒-启动.command`

This launcher will:
- stop the old local process if needed
- check port conflicts
- start the service
- open the browser

### Desktop shortcuts

If you use the provided desktop shortcuts, note the difference:
- repository root `.command` files are the real project entry scripts
- desktop `.command` files are lightweight wrappers that jump back into the project directory

Recommended desktop entries:
- `携程酒店提醒-启动.command`
- `核心回归检查.command`
- `环境自检.command`

## Installation

Clone the repository and run:

```bash
python3 app.py
```

Optional launchd background mode on macOS:

```bash
./scripts/install_launchd.sh
```

Useful commands:

```bash
./scripts/status_launchd.sh
./scripts/uninstall_launchd.sh
```

## Usage

Create a watcher with these core fields:
- hotel URL
- watcher name
- hotel name
- notification type
- notification webhook

Optional but commonly useful:
- room type keyword
- target price
- minimum expected price
- poll interval in minutes

### Notification behavior
- send a notification if current price is below target price
- send a notification if current price is lower than last check
- do not repeat for the same or higher already-notified price
- for Feishu:
  - target hit sends a stronger card
  - target hit also sends `@all`
  - non-target drop sends a normal card

### Login / session flow
Access to Ctrip pages may depend on your own login state.

Recommended flow:
1. open the app page
2. click `登录并保存会话`
3. finish login in the opened browser window
4. click `我已登录完成`
5. run `立即检查`

## Configuration

### IM webhook
The UI supports:
- `Feishu`
- `WeCom`

Select the IM type and paste the matching robot webhook URL.

### Advanced settings
Advanced settings are mainly for troubleshooting:
- custom request headers JSON
- custom price regex

Example:

```json
{
  "Cookie": "your-cookie-here"
}
```

## FAQ

### Why didn’t I receive a notification?
Most commonly because the notification condition was not met yet:
- current price is still above target price
- current price is not lower than the last notified price

### Why is login required?
Ctrip may show different content depending on session, device, region, or other access conditions.

### Why does the trend chart not show all history?
The chart is intentionally limited for UI readability, but the underlying price history is now kept in full.

### Why can historical low time be inaccurate for old data?
Older versions only kept a rolling slice of price history. For newly collected data, the low-price timestamp now persists correctly.

## Regression Checks

### Core checks

```bash
./scripts/run_core_checks.sh
```

Covers:
- Python syntax
- repository CRUD
- notification logic
- watcher services
- session API services
- browser path resolution logic

### Smoke checks

```bash
./scripts/run_smoke_checks.sh
```

Note:
- this is closer to a real browser environment
- it may fail in restricted environments
- local machine results are the most meaningful

## Git / Open Source Notes

Before publishing this repository, make sure you do **not** commit local runtime data.

Ignored by default now:
- `data.db`
- `logs/`
- `session_profiles/`
- `debug_screens/`
- `__pycache__/`

Why these should stay local:
- `data.db` may contain your personal watcher data
- `session_profiles/` may contain browser session and login material
- `logs/` may include local paths, runtime errors, and debugging details
- `debug_screens/` may contain captured page content

Recommended open-source workflow:
1. keep source code, templates, static assets, tests, and scripts in git
2. keep runtime data local only
3. if needed, publish a clean sample config or sample screenshots separately

Run the pre-publish self-check before pushing:

```bash
./scripts/prepublish_check.sh
```

## Project Structure

```text
hotel_price_alert/
  api.py
  server.py
  repository.py
  notifications.py
  utils.py
  fetchers.py
  extractors.py
  session.py
  services/
templates/
static/
scripts/
tests/
```

## Development Notes
- current repository only targets `Ctrip`
- notification layer is already abstracted enough for more IM integrations later
- browser/session logic remains the most environment-sensitive part

## Legal / Responsible Use

This project is intended for personal, local use only.

Please keep these boundaries in mind:
- use it only with websites and accounts you are authorized to access
- review and follow the target website’s terms, policies, and applicable laws before using automation
- keep request frequency low and avoid behavior that may burden, interfere with, or bypass a website’s normal controls
- do not use this project to resell data, build a commercial data service, or run large-scale collection jobs
- do not commit personal session data, cookies, logs, screenshots, or webhook secrets into Git

This repository does not provide anti-bot bypass tooling, CAPTCHA solving, proxy rotation, or bulk collection features, and it should not be used for those purposes.

## Disclaimer
Use this project responsibly and only in ways that comply with the target website’s terms and your local laws.

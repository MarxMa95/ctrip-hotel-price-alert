# Ctrip Hotel Price Alert

[![Release](https://img.shields.io/github/v/release/MarxMa95/ctrip-hotel-price-alert)](https://github.com/MarxMa95/ctrip-hotel-price-alert/releases)
[![License](https://img.shields.io/github/license/MarxMa95/ctrip-hotel-price-alert)](https://github.com/MarxMa95/ctrip-hotel-price-alert/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](https://www.apple.com/macos/)

A local-first hotel price monitoring app for `Ctrip`, built for room-specific tracking, flexible IM notifications, and quick setup on your own machine.

Release policy: each shipped update gets a new GitHub release tag. The current release is `v1.1.0`, and subsequent feature updates continue as `v1.2.0`, `v1.3.0`, and so on.

## Why this project

Most hotel price trackers only watch a listing at the hotel level. This project is built for the more practical case:

- track a specific room type instead of the whole hotel
- keep monitoring from your own machine and browser session
- send alerts to the IM tool you already use
- review recent price trend, all-time low, and latest low occurrence time

## Key Features

- Room-specific monitoring by room name keyword
- Multiple notification channels:
  - `Feishu`
  - `WeCom`
  - `Slack`
  - `Discord`
  - `Telegram`
- Separate alert behavior for:
  - target price reached
  - normal price drop
- Trend chart with:
  - recent 7-day / 30-day / full-history view
  - all-time low price
  - latest timestamp when that low price appeared
- Full local history retention for newly collected data
- Browser-session-assisted access for pages that require a valid signed-in session
- Local-only runtime data: watchers, logs, and session material stay on your machine

## Product Positioning

This project is designed to be:

- `Room-aware`: track the exact room you care about
- `IM-flexible`: use the notification provider that fits your workflow
- `Local-first`: keep your session and runtime data on your own device
- `Practical`: start quickly without building a cloud service

## Requirements

- macOS
- Python `3.11+`
- `playwright`
- A local Chrome / Chromium / Edge installation, or Playwright-managed Chromium

Install the required browser dependency if needed:

```bash
python3 -m pip install playwright
python3 -m playwright install chromium
```

## Quick Start

### Option 1: Run directly

```bash
python3 app.py
```

Then open:

```text
http://127.0.0.1:8766
```

### Option 2: Use the launcher

- `Launch Ctrip Hotel Alert.command`

This launcher will:

- stop an older local process if needed
- detect port conflicts
- start the service
- open the app in your browser

## Included Helper Entrypoints

- `Launch Ctrip Hotel Alert.command`
- `Run Core Checks.command`
- `Environment Check.command`
- `Pre-Publish Check.command`

You can also refresh desktop wrappers:

```bash
./scripts/refresh_desktop_shortcuts.sh
```

## Installation

Clone the repository and start the app:

```bash
python3 app.py
```

Optional background mode with `launchd`:

```bash
./scripts/install_launchd.sh
```

Useful service commands:

```bash
./scripts/status_launchd.sh
./scripts/uninstall_launchd.sh
```

## Usage

Create a watcher with these core fields:

- hotel URL
- watcher name
- hotel name
- room type name
- notification provider
- notification target

Common optional fields:

- target price
- minimum reasonable price
- polling interval in minutes
- quiet hours
- daily notification limit
- minimum price-drop threshold

## Notification Providers

The UI currently supports:

- `Feishu` robot webhook
- `WeCom` robot webhook
- `Slack` incoming webhook
- `Discord` channel webhook
- `Telegram` bot token + chat ID

Behavior highlights:

- target price hit is visually stronger than a normal drop
- `Feishu` target-hit alerts also send `@all`
- price-drop notifications can be limited by threshold, quiet hours, and daily caps

## Session / Login Flow

Some Ctrip pages depend on your own login/session state.

Recommended flow:

1. Open the app
2. Open the session panel
3. Start the dedicated Ctrip login flow
4. Finish login in the opened browser window
5. Save and verify the session
6. Run a check or let the watcher continue polling

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

Notes:

- this is closer to a real browser environment
- it may fail in restricted or headless-hostile environments
- local machine results are the most meaningful

## Privacy & Runtime Data

This app is intentionally local-first.

Runtime files should stay local and should not be committed:

- `data.db`
- `logs/`
- `session_profiles/`
- `debug_screens/`

These may contain:

- your watcher data
- your session artifacts
- local logs and debugging output
- captured page content

## Publishing Safety

Run the built-in pre-publish check before pushing:

```bash
./scripts/prepublish_check.sh
```

It checks for:

- tracked runtime data
- missing `.gitignore` coverage
- likely real webhook secrets

## FAQ

### Why did I not receive a notification?

Common reasons:

- current price has not reached the target
- current price did not beat the last notified price
- the watcher is inside quiet hours
- the daily notification limit was reached
- the price drop did not meet the minimum drop threshold

### Why does a watcher show room not found?

This project now favors stricter room matching over loose fuzzy matches.

That reduces false positives, but it also means you should prefer the full room name shown on the page.

### Why does the chart window sometimes look the same for 7 days and 30 days?

Because your local history may currently only contain data from the last several days. Once more data accumulates, the windows will diverge naturally.

### Why is login/session handling needed?

Ctrip may render different content depending on session state, region, device context, and other access conditions.

## Responsible Use

This project is intended for personal monitoring, research, and workflow automation on pages you are already able to access in your own browser.

Please use it responsibly:

- respect the target platform's terms and operational limits
- avoid abusive traffic patterns
- do not use it to bypass access controls
- do not publish personal session data, cookies, or webhook secrets

This repository is provided as a local automation utility, not as a hosted scraping service.

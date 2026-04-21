# 携程酒店降价提醒工具 / Ctrip Hotel Price Alert

[![Release](https://img.shields.io/github/v/release/MarxMa95/ctrip-hotel-price-alert)](https://github.com/MarxMa95/ctrip-hotel-price-alert/releases)
[![License](https://img.shields.io/github/license/MarxMa95/ctrip-hotel-price-alert)](https://github.com/MarxMa95/ctrip-hotel-price-alert/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/platform-macOS-lightgrey)](https://www.apple.com/macos/)

一个 `local-first` 的携程酒店价格监控工具。
它不是只盯“酒店均价”，而是可以精确监控你关心的具体房型，并在价格下降或达到目标价时，通过你常用的 IM 工具推送提醒。

> 适合已经选定酒店和房型、只想蹲一个更合适价格的人。

Release policy: each shipped update gets a new GitHub release tag. The current release is `v1.1.0`, and subsequent feature updates continue as `v1.2.0`, `v1.3.0`, and so on.

## 为什么做这个项目 / Why this project

很多酒店价格提醒工具只能按“酒店级”监控。
但真实场景里，大家真正关心的通常是：

- 我想住的那个房型有没有降价
- 价格是不是已经到我的心理价位
- 订完之后有没有更低价值得重新下单
- 能不能直接把提醒发到我已经在用的消息工具里

这个项目就是为这个场景做的：

- 按房型监控，而不是只看整家酒店
- 本地运行，账号会话和运行数据保留在自己机器上
- 支持飞书、企微、Slack、Discord、Telegram 等通知方式
- 可以查看最近价格趋势、历史最低价和最低价最近出现时间

## 核心特性 / Key features

- 房型级监控
  - 支持按房型名称关键词监控指定房型
- 多通知渠道
  - `Feishu`
  - `WeCom`
  - `Slack`
  - `Discord`
  - `Telegram`
- 更实用的提醒策略
  - 到达目标价提醒
  - 普通降价提醒
- 价格趋势可视化
  - 最近 7 天 / 30 天 / 全历史价格趋势
  - 历史最低价
  - 最低价最近出现时间
- 本地优先
  - watcher、日志、session 等运行数据默认只保存在本机
- 支持登录态页面
  - 可通过本地浏览器登录流程保存并复用携程会话

## 项目定位 / Product positioning

这个项目不是云端 SaaS，也不是“酒店全网比价平台”。
它更像一个为个人使用设计的本地工具：

- `Room-aware`: 盯你真正想住的那个房型
- `Local-first`: 会话和数据掌握在自己手里
- `IM-flexible`: 提醒发到你已有的工作流里
- `Practical`: 不需要先搭一整套云服务

## 运行环境 / Requirements

- macOS
- Python `3.11+`
- `playwright`
- 本地 Chrome / Chromium / Edge，或 Playwright 安装的 Chromium

如需安装浏览器依赖：

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
- `scripts/release_minor.sh`

You can also refresh desktop wrappers:

```bash
./scripts/refresh_desktop_shortcuts.sh
```

Create the next minor release automatically:

```bash
./scripts/release_minor.sh
```

Preview the next version without changing anything:

```bash
./scripts/release_minor.sh --dry-run
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

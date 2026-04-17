# Contributing

Thanks for your interest in improving `Ctrip Hotel Price Alert`.

## Before You Start
- Please keep the project focused on local, personal-use monitoring
- Avoid changes that increase scraping aggressiveness, bulk collection, anti-bot bypass, proxy rotation, or CAPTCHA-solving behavior
- Prefer small, focused pull requests over large mixed changes

## Development Setup
1. Clone the repository
2. Install Python dependencies you need locally
3. Install Playwright if required:
   - `python3 -m pip install playwright`
   - `python3 -m playwright install chromium`
4. Start the app locally:
   - `python3 app.py`

## Recommended Checks
Run these before opening a pull request:
- `./scripts/run_core_checks.sh`
- `./scripts/prepublish_check.sh`

If browser-based smoke checks are not stable in your environment, mention that clearly in the PR.

## Pull Request Guidelines
- Keep behavior changes minimal and well explained
- Update `README.md` when user-facing behavior changes
- Add or update tests when logic changes
- Do not commit local runtime data such as:
  - `data.db`
  - `logs/`
  - `session_profiles/`
  - `debug_screens/`
- Do not commit real webhook URLs, cookies, sessions, or personal account data

## Scope Boundaries
Pull requests are less likely to be accepted if they add:
- large-scale crawling features
- anti-bot bypass tooling
- CAPTCHA solving
- proxy pools or account rotation
- commercial data extraction workflows

## Bug Reports
When reporting a bug, please include:
- what you expected
- what happened instead
- your macOS and Python version
- whether the failure is UI-only, session-related, or browser-related
- relevant logs or screenshots with secrets removed

## Security Issues
Please do not open a public issue for sensitive security problems.
See `SECURITY.md` for the reporting process.

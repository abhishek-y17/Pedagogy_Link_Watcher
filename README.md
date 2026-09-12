# KEA Link Watch

Watches KEA counselling pages for newly-added links and posts them to a
Telegram group. Replaces manually refreshing the page to check for a new
notice or result.

See **CLAUDE.md** for the detailed working agreement, and `README_OFFICE.txt`
for the non-technical operator walkthrough.

## Quick start

```bash
pip install -r requirements.txt
python -m playwright install chromium

# first run: record the current links on each watched page without alerting
PYTHONPATH=src python -m neet_pipeline.run_monitor --baseline

# one-shot scan, or a loop (what the office-box launcher runs)
PYTHONPATH=src python -m neet_pipeline.run_monitor --once
PYTHONPATH=src python -m neet_pipeline.run_monitor --loop
```

Add or remove a watched page by editing `config/link_watch_pages.txt` (one
URL per line) — no code changes needed.

**Production runs on an office computer** (residential Indian ISP, stays on
24/7) via a one-click Windows launcher, because KEA geo-blocks non-Indian
IPs (cloud runners can't reach it). Setup: double-click `SETUP.bat` once,
then `START_MONITOR.bat` (visible window) or `INSTALL_AUTOSTART.bat`
(background, Task Scheduler, recommended).

## Running the test suite

```bash
pip install -r requirements.txt
PYTHONPATH=src pytest
```

The same suite runs automatically on pushes and pull requests via
`.github/workflows/tests.yml`.

## Security note

Tokens live in `config/.env` (gitignored) — never commit them. Runtime
`*.log`/`*.logs` files are also ignored because request tracebacks can
contain sensitive URLs.

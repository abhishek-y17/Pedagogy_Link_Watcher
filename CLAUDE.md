# CLAUDE.md — KEA Link Watch

Context and working agreement for Claude Code. Read this fully before editing.

## What this project is

A small always-on monitor for an education consultancy. It watches a
hand-edited list of KEA counselling pages for **newly-added links** and posts
them to a Telegram group. That's the entire scope — there is no PDF scraping,
no student roster, no rank matching, and no parent notification here anymore
(an earlier, much larger version of this repo did all of that; it was
deliberately stripped down to just this).

```
config/link_watch_pages.txt  -->  monitor/link_watch.py  -->  notifier/link_alerts.py
   (which pages to watch)          (diff links, detect new)      (post to Telegram)
```

## The one thing to keep working

Every ~1 minute (configurable), for each page in `config/link_watch_pages.txt`:
1. Render the page with a headless browser (KEA pages are JS-rendered and
   robots-block plain `requests` fetches).
2. Extract every `<a href>` link on the page.
3. Compare against the last-known set of links for that page
   (`data/cache/links_<page_key>.json`).
4. Post any newly-added links to the Telegram alerts chat; append them to
   `data/cache/recent_links_<page_key>.log` for a human-skimmable feed.
5. Post a ✅/❌ heartbeat line to a separate Telegram health chat.

**Auto-baseline:** a page with no existing manifest is silently baselined on
its first scan — every current link is recorded, nothing is alerted. Only
links added *after* that first scan trigger an alert. This is what makes
adding a new page to `link_watch_pages.txt` safe: it never floods the chat
with everything already on the page.

**Safer polling (jitter + rate-limit backoff):** at a 1-minute cadence,
polling at an exact, fixed interval risks the office's residential IP
getting rate-limited or blocked by KEA — with no cloud fallback (see
convention 4 below), that would take the whole tool down.
`run_monitor.py::JITTER_SECONDS` (±30s) adds a small random delay to every
poll — an inter-cycle sleep offset for `--loop`, and a pre-scan delay for
`--once`/Task Scheduler (which owns its own fixed cadence and has no
inter-cycle sleep to jitter). `monitor/headless.py::RateLimitedError` is
raised specifically for HTTP 429/503 (distinct from any other failure,
e.g. the 403 seen live against mcc.nic.in's WAF); when
`monitor/link_watch.py::LinkWatchResult.rate_limited` comes back `True`,
`run_monitor.py::_record_backoff` persists a `backoff_until` deadline
(`BACKOFF_SECONDS` = 5 min) into `data/cache/monitor_state.json`, and every
`_execute_monitor_run` call checks `_active_backoff()` first and skips
scanning entirely (no network call at all) until that deadline passes —
this works across process restarts since Task Scheduler runs `--once` as a
fresh process each time. A skipped run still posts a heartbeat (`⏸ ...
SKIPPED ... backing off ...`) so the health chat is never silently quiet.
`--no-jitter` disables the pre-scan/inter-cycle delay (used by tests and
available for manual runs).

## Adding or removing a watched page

Edit `config/link_watch_pages.txt` directly — one URL per line, `#` comments
and blank lines ignored. No code change needed. A newly-added page baselines
itself on the next scan (see above); a removed line just stops being checked
(its old manifest file under `data/cache/` is harmless and can be deleted).

There is no separate yaml config — `config/link_watch_pages.txt` is the only
config file this tool reads. Link *identity* (used to detect "is this link
new") is normalized URL + link text; see `monitor/link_watch.py`'s module
docstring for why ambiguous query params like `?id=` are kept by default
rather than stripped (government portals often use `?id=` as the real
document key). `normalize_url_for_identity`/`extract_all_links` accept
optional `volatile_params`/`keep_params` overrides in code for a page whose
query params misbehave, but nothing wires those up from config today — add
that only if a real page actually needs it.

## Non-negotiable conventions

1. **`config/link_watch_pages.txt` is the source of truth for what's
   watched.** Don't hardcode page URLs anywhere in code.
2. **A new link is informational only.** It never triggers scraping, parsing,
   or any downstream action beyond a Telegram post — there is nothing
   downstream to trigger.
3. **No secrets in code.** All tokens go in `config/.env` (gitignored),
   loaded at runtime. Never commit real credentials.
4. **KEA geo-blocks non-Indian IPs.** Confirmed: fails from a GitHub-hosted
   runner and from a France VPN, works from India. This is why the monitor
   runs on an office PC (residential Indian connection, stays on 24/7) via
   `START_MONITOR.bat` / Task Scheduler, not GitHub Actions or any other
   cloud host.

## Repo layout

```
kea-link-watch/
├── CLAUDE.md
├── README.md
├── README_OFFICE.txt      # plain-English operator guide (office PC)
├── SETUP.bat              # run once: venv, deps, playwright, config/.env
├── START_MONITOR.bat      # everyday visible run (--loop --interval 60)
├── INSTALL_AUTOSTART.bat  # register Task Scheduler job (--once every 1 min, no window)
├── UNINSTALL_AUTOSTART.bat# remove that task
├── setup.sh / start_monitor.sh   # Linux/macOS bonus parity
├── config/
│   ├── link_watch_pages.txt    # the watched pages (hand-edited) -- the only config file
│   └── .env                    # tokens (gitignored)
├── data/                   # all gitignored; plain local folders on disk
│   └── cache/              # link manifests, recent_links_<page>.log,
│                           # monitor_state.json, health_state.json
├── logs/                   # gitignored; autostart.log from scripts/run_once_task.bat
├── .github/workflows/
│   └── tests.yml           # pytest on push/PR
├── src/neet_pipeline/
│   ├── monitor/            # config, watched_pages, headless, link_watch,
│   │                       # recent_links, manifest
│   ├── notifier/           # link_alerts, health, telegram_api
│   └── run_monitor.py      # orchestrator: check pages -> post alerts -> heartbeat
├── scripts/                # preflight_check.py, run_once_task.bat
└── tests/
```

(The package is still importable as `neet_pipeline` — renaming it wasn't
worth the churn for what is now a much smaller tool.)

## Running it

```bash
pip install -r requirements.txt
python -m playwright install chromium

PYTHONPATH=src python -m neet_pipeline.run_monitor --baseline   # first run only, or to deliberately reset
PYTHONPATH=src python -m neet_pipeline.run_monitor --once       # single scan (cron/Task Scheduler)
PYTHONPATH=src python -m neet_pipeline.run_monitor --loop [--interval 60]
```

`--pages` overrides which `link_watch_pages.txt` to read (default:
`config/link_watch_pages.txt`) — mainly useful for tests.

`--no-notify` scans and records links without posting to Telegram;
`--no-health` skips the heartbeat post; `--no-jitter` polls at the exact
interval with no random delay. All three are mainly for dry runs / tests.

## Telegram setup

Two separate bots/chats, both in `config/.env`:
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` — the alerts chat (new links only).
- `HEALTH_BOT_TOKEN` / `HEALTH_CHAT_ID` — the heartbeat chat (a ✅/❌ line after
  every run). Kept separate so a heartbeat never buries a real alert.

A missing/invalid token fails loudly (`notifier/telegram_api.py` raises
`TelegramConfigError`) rather than silently doing nothing.

## History

This repo used to be a full NEET counselling pipeline: scrape KEA/MCC result
PDFs, match tracked students by rank, and post a Telegram bundle for staff to
forward to parents by hand. That scope was dropped by request — the link-watch
piece (originally an add-on to the PDF monitor) is now the whole project.

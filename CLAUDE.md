# CLAUDE.md — KEA Link Watch

Context and working agreement for Claude Code. Read this fully before editing.

## What this project is

A small always-on monitor for an education consultancy. It watches a
hand-edited list of KEA (Karnataka) and MCC (national) counselling pages for
**newly-added links** and posts them to a Telegram group. See **LINK.md**
for what's watched and why those specific URLs were chosen over the
alternatives. That's the entire scope — there is no PDF scraping,
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
5. Record this run's outcome for the health chat -- see "Batched health
   heartbeat" below; a failed run posts immediately, a healthy/skipped one
   is buffered into the next batch summary.

**Auto-baseline:** a page with no existing manifest is silently baselined on
its first scan — every current link is recorded, nothing is alerted. Only
links added *after* that first scan trigger an alert. This is what makes
adding a new page to `link_watch_pages.txt` safe: it never floods the chat
with everything already on the page.

**Batched health heartbeat:** `notifier/health.py::record_run` buffers each
run's outcome (ok/failed/skipped) instead of posting a heartbeat every ~1
minute -- that was too noisy at this cadence. Once
`health.py::BATCH_SIZE` (10) runs have piled up, `pop_batch` hands them
back for `format_batch_summary` to render as one Telegram message (OK/
FAILED/SKIPPED counts, total new links, and any failure/skip/warning text
deduplicated with an "(xN)" count rather than repeated per run) -- roughly
one heartbeat every 10 minutes at the normal cadence. A **failed** run is
the exception: `run_monitor.py::_record_health_outcome` posts it
immediately via `health.py::format_failure` rather than buffering it, so
a real problem is never sitting unreported for up to 10 cycles. Tests
shrink `BATCH_SIZE` via `monkeypatch.setattr(health_mod, "BATCH_SIZE",
...)` (read from module globals at call time, not bound as a default arg,
so this works) instead of running 10 real cycles per test.

**Safer polling (jitter + rate-limit backoff):** at a 1-minute cadence,
polling at an exact, fixed interval risks the office's residential IP
getting rate-limited or blocked by KEA — with no cloud fallback (see
convention 4 below), that would take the whole tool down.
`--loop` randomizes its inter-cycle sleep between
`run_monitor.py::LOOP_SLEEP_MIN`/`LOOP_SLEEP_MAX` (50-90s, so cadence is
never faster than 50s) instead of sleeping a fixed `--interval`; the first
scan after start still runs immediately (no pre-scan delay), since the
inter-cycle sleep already provides the randomness. `--once`/Task Scheduler
(which owns its own fixed external cadence and has no inter-cycle sleep to
jitter) instead gets a `run_monitor.py::JITTER_SECONDS` (±30s) pre-scan
delay. `monitor/headless.py::RateLimitedError` is
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

See **LINK.md** for the reasoning behind the current URL list -- e.g. why
MCC is watched via its full-list pages (`current-events-*`,
`eservices-schedule-*`) rather than the landing pages, and why only those
two sections and not all of MCC's "View More" targets. Update LINK.md
alongside the `.txt` file when the reasoning changes, not just the URLs.

There is no separate yaml config — `config/link_watch_pages.txt` is the only
config file this tool reads. Link *identity* (used to detect "is this link
new") is normalized URL + link text; see `monitor/link_watch.py`'s module
docstring for why ambiguous query params like `?id=` are kept by default
rather than stripped (government portals often use `?id=` as the real
document key). `normalize_url_for_identity`/`extract_all_links` accept
optional `volatile_params`/`keep_params` overrides in code for a page whose
query params misbehave, but nothing wires those up from config today — add
that only if a real page actually needs it.

`extract_all_links` also accepts a `content_selector` (a CSS selector, e.g.
`"main"`) that scopes extraction to that element instead of the whole
document. This exists because a site's nav/header/footer chrome is
byte-identical across every page it hosts; without scoping, two watched
pages on the same site pick up each other's shared chrome links, and any
edit to that chrome fires a duplicate, unrelated alert on every page on
that site at once. `monitor/config.py::_CONTENT_SELECTOR_BY_HOST` wires
this in per-hostname (not exposed in `link_watch_pages.txt` — same
code-level-override pattern as `volatile_params`/`keep_params` above).
Both watched hosts are confirmed and wired against their live DOM
(2026-09-19, re-confirmed 2026-10-27): `mcc.nic.in` -> `"main"`, and
`cetonline.karnataka.gov.in` (KEA) -> `".card-deck"` (every KEA page shares
an identical template — a 235-link sidebar `<nav>`, a 4-link banner, and a
15-link `<footer>` around one page-specific `div.card-deck`; the sidebar
is exactly where PGCET/PG-Dental/PBBSc/BPT/AHS-lateral links were leaking
into UGCET/UGNEET's manifests — see LINK.md's "Why these KEA pages"
section for the live incident that surfaced this).

**Flood guards — a broken render fails the page, never alerts it.** Two
failure modes would otherwise alert a page's *entire* link list as "new",
so both now fail that page's scan instead (a warning in the health chat;
the page retries next cycle; its manifest is untouched):
- `link_watch.py::check_link_page` raises `ContentSelectorMissingError` when
  a page's configured `content_selector` matches nothing (maintenance page,
  half-loaded render, redesign). `extract_all_links` itself still falls back
  to the whole document for direct callers, but a watched page with a
  selector never takes that path — on KEA it would alert ~250 sidebar links.
- `headless.py::fetch_rendered_html` raises when a KEA page comes back in
  Kannada (`is_non_english_kea_render`). Link identity includes link text,
  and a Kannada render changes every identity on the page (12/12 on
  `pgetmed2026`, confirmed live 2026-10-27), so a silently failed English
  switch would otherwise alert every notice on every KEA page at once.

**One alert line per document.** mcc.nic.in renders each document as three
`<a>` tags to the same PDF (icon / title / "View(484 KB)").
`link_watch.py::collapse_by_url` folds those into one entry (keeping the
real title) for the alert message, the recent-links log and the new-link
counts. Identity — and so every manifest — stays (url, text).

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
5. **mcc.nic.in needs specific headers, not just an Indian IP.** Its Akamai
   WAF returns HTTP 403 to headless Chromium whenever the request is
   missing Chromium's `Sec-Ch-Ua` client-hint headers, regardless of IP
   location (confirmed live from an Indian IP too -- this is bot detection,
   not geo-blocking). `monitor/headless.py::_HEADLESS_EXTRA_HEADERS` sends
   those headers alongside the UA string; don't drop them when touching
   that function.

## Repo layout

```
kea-link-watch/
├── CLAUDE.md
├── LINK.md                # why these specific pages/URLs are watched
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

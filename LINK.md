# Watched pages — what and why

This file explains *why* `config/link_watch_pages.txt` watches the specific
URLs it does, not just what they are. Edit the `.txt` file to actually
change what's watched (see CLAUDE.md) — this file is the reasoning behind
those choices, kept separate so it doesn't get lost in a config comment.

## Currently watched

| URL | Site | Why this one |
|---|---|---|
| `https://cetonline.karnataka.gov.in/kea/ugneet2026` | KEA (Karnataka) | Karnataka NEET-UG counselling notices/results |
| `https://cetonline.karnataka.gov.in/kea/ugcet2026` | KEA (Karnataka) | Karnataka UGCET counselling notices/results |
| `https://cetonline.karnataka.gov.in/kea/pgcet2026` | KEA (Karnataka) | Karnataka PGCET (MBA/MCA/M.Tech/M.Arch) counselling notices/results |
| `https://cetonline.karnataka.gov.in/kea/pgden2026` | KEA (Karnataka) | Karnataka PG-Dental counselling notices/results |
| `https://mcc.nic.in/current-events-pg/` | MCC (national) | Full list of PG counselling notices/results (see below — not the landing page) |
| `https://mcc.nic.in/eservices-schedule-pg/` | MCC (national) | Full list of PG round schedules |
| `https://mcc.nic.in/current-events-ug/` | MCC (national) | Full list of UG counselling notices/results |
| `https://mcc.nic.in/eservices-schedule-ug/` | MCC (national) | Full list of UG round schedules |

## Why the MCC *full-list* pages, not the landing pages

`https://mcc.nic.in/pg-medical-counselling/` and
`https://mcc.nic.in/ug-medical-counselling/` (the landing pages) were the
first two MCC URLs considered, and are **not** watched. Each landing page
only shows the latest few items per section (e.g. "Current Events") in a
box, with a "View More" link to a separate full-list page. Two problems
with watching the landing page directly:

1. **Truncation risk.** If more items get added to a box than the box
   shows before the next scan (most likely during a rate-limit backoff or
   the office PC being off), the pushed-off item is never seen at all —
   not delayed, just missed. Watching the full-list page instead removes
   this failure mode entirely.
2. **Duplicate alerts if watched alongside the full-list page.** The same
   PDF link appears on both the landing page and its full-list page. If we
   watched both, one new document would fire two separate Telegram alerts
   under two different page keys. Since the full-list page is strictly a
   superset, the landing page is redundant once the full-list page is
   watched.

## Why only these 4 KEA pages, not any other KEA sub-page

`cetonline.karnataka.gov.in` runs a single shared sidebar/nav menu across
every program it hosts (UGNEET, UGCET, PGCET, PG-Dental, PG-AYUSH, PG
Nursing, etc.) — the same menu markup is present on every page. Only
UGNEET-2026, UGCET-2026, PGCET-2026, and PG-Dental-2026 are watched
deliberately; no other KEA sub-page (PG-AYUSH, PG-Nursing, PGET-Medical,
older-year pages like `pgcet2025.aspx`, etc.) should be added without a
specific reason, since each addition is another page whose own content
plus that same shared sidebar gets diffed.

**Known issue this caused, now fixed:** because `extract_all_links`
originally scanned the whole rendered page with no scoping, the shared
sidebar's links (e.g. `pgcet2026.aspx`, `pget2025.aspx`,
`Pgcollegeportal2026`) were being recorded as part of *every* watched
page's manifest, not just the page that page is actually about. Confirmed
live 2026-09-18/19: a single sidebar change (a new "PGCET - 2026 College
Portal link" entry) fired a duplicate alert on both the UGCET and UGNEET
pages simultaneously, and separately, PBBSc/BPT-lateral/BSc-lateral/AHS
lateral links (more sidebar entries, unrelated to UGNEET) were alerted
the same way. `monitor/config.py::_CONTENT_SELECTOR_BY_HOST` now scopes
extraction on both sites: `main` for mcc.nic.in, `.card-deck` for
`cetonline.karnataka.gov.in` — both confirmed against each site's live DOM
(2026-09-19). On KEA specifically, every one of the 4 watched pages uses
an identical template: a 235-link `<nav>` (the full KEA program sidebar --
this is exactly where PGCET/PG-Dental/PBBSc/BPT/AHS-lateral links were
leaking from), a 4-link `<section class="pu-text">` banner ("Home"/
"Admissions", also shared), and a 15-link shared `<footer>`, all wrapped
around one page-specific `div.card-deck` holding just that page's own
notices. Scoping to `.card-deck` drops the shared chrome on all 4 pages
without touching real content. The alert message now shows a single
`Source page:` line (no separate `Page:` line — they were identical
anyway, since `page.name` is just the raw URL) so it's unambiguous which
of the 4 KEA pages actually changed.

## Why only 4 MCC full-list pages, not all 7

MCC's landing pages surface up to 7 "View More" targets each. Only the
**Current Events** and **Schedule** full-list pages are watched. The other
sections found during investigation:

- `https://mcc.nic.in/news-events-pg/`, `https://mcc.nic.in/news-events-ug-medical/`
  ("News & Events") — mostly press-style announcements, not counselling
  actions.
- `https://mcc.nic.in/important-link-ug/` ("Important Link") — static
  external portal/institute links, rarely changes.

These were left out to keep the alert chat high-signal. Add any of them to
`config/link_watch_pages.txt` later if something important turns out to
live there — no code change needed, see CLAUDE.md's "Adding or removing a
watched page" section.

## Why mcc.nic.in needed a code change to work at all

mcc.nic.in's Akamai WAF returned HTTP 403 to this tool's headless-Chromium
fetcher even with a spoofed desktop Chrome user-agent — confirmed from an
Indian IP, so it wasn't a geo-block. The cause: Playwright doesn't send
Chromium's `Sec-Ch-Ua` client-hint headers by default, and their absence
(while the UA string claimed a real Chrome build) was enough on its own to
get flagged. Fixed in `src/neet_pipeline/monitor/headless.py` by sending
those headers alongside the UA — see `_HEADLESS_EXTRA_HEADERS` in that file.
No automation-flag tricks or `navigator.webdriver` patching were needed.

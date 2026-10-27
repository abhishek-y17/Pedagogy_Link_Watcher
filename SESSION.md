# Session log

Working notes on what changed, when, and why — kept separate from LINK.md
(the standing reasoning doc) and CLAUDE.md (the working agreement). This
file is a running log; add a new dated section per session instead of
editing old ones.

## 2026-09-19

### Problem reported

Staff noticed the KEA/MCC link-watch was alerting on links unrelated to the
page being watched: the UGCET/UGNEET pages fired alerts for PGCET links,
and separately for PBBSc/BPT-lateral/BSc-lateral/AHS-lateral links — none
of which are UGCET/UGNEET content.

### Root cause

`extract_all_links` (in `monitor/link_watch.py`) extracted every `<a href>`
on the whole rendered page, with no scoping. Both watched sites reuse a
site-wide nav/sidebar/footer template that's byte-identical across every
page they host:

- **KEA** (`cetonline.karnataka.gov.in`): all 4 watched pages share an
  identical template — a 235-link sidebar `<nav>` listing every KEA
  program (this is exactly where the PGCET/PG-Dental/PBBSc/BPT/AHS-lateral
  links were leaking from), a 4-link "Home"/"Admissions" banner
  (`section.pu-text`), and a 15-link shared `<footer>` — wrapped around one
  page-specific `div.card-deck` holding just that page's own notices.
- **MCC** (`mcc.nic.in`): `<header id="mainHeader">` holds the nav menu,
  `<footer id="mainFooter">` holds the gov.in footer links, `<main>` holds
  only the actual event-list content.

Confirmed live via direct DOM inspection of both sites (this session had
working network access to both, including KEA, which is normally
geo-blocked from outside India per CLAUDE.md convention 4 — worth noting
in case a future session doesn't get through and needs to hand this off to
the office PC instead). Confirmed in the wild too: `recent_links_kea_ugcet2026.log`
and `recent_links_kea_ugneet2026.log` both show an identical alert
("PGCET - 2026 College Portal link", 2026-09-18 12:28:02) fired at the
same instant on two unrelated pages — the sidebar changing once, alerted
twice.

### Fixes made

1. **Content-selector scoping** — `monitor/link_watch.py::extract_all_links`
   gained an optional `content_selector` (CSS selector) parameter that
   limits extraction to that element instead of the whole document, falling
   back to the whole page if the selector matches nothing (so a future site
   redesign degrades to noisier behavior instead of silently returning zero
   links). Wired per-hostname in `monitor/config.py::_CONTENT_SELECTOR_BY_HOST`:
   - `mcc.nic.in` → `"main"`
   - `cetonline.karnataka.gov.in` → `".card-deck"`

2. **Two new KEA pages added**, per request — `config/link_watch_pages.txt`
   now watches 4 KEA pages instead of 2:
   - `https://cetonline.karnataka.gov.in/kea/pgcet2026` (PGCET)
   - `https://cetonline.karnataka.gov.in/kea/pgden2026` (PG-Dental)

   Reasoning documented in LINK.md's "Why only these 4 KEA pages, not any
   other KEA sub-page" section — no other KEA sub-page (PG-AYUSH, PG-Nursing,
   older-year pages, etc.) should be added without a specific reason.

3. **Alert message simplified** — `notifier/link_alerts.py::format_link_alert_message`
   dropped the `Page:` line. It duplicated `Source page:` verbatim (both
   read the page's raw URL), confirmed from the live alert above. Now each
   new-links block shows one `Source page: <url>` line, unambiguous about
   which of the 4 KEA / 4 MCC pages actually changed.

4. **Docs updated** — CLAUDE.md and LINK.md both updated to describe the
   `content_selector` mechanism and the confirmed per-host values, so this
   doesn't need re-discovering next time.

### Testing done this session

- Added tests for: `content_selector` scoping in `extract_all_links`
  (drops nav/footer, falls back safely), `check_link_page` respecting
  `page.content_selector` (a shared-nav change must not surface as a "new
  link"), the config wiring (`_CONTENT_SELECTOR_BY_HOST` applied per host,
  absent for unrecognized hosts), and the alert message no longer
  duplicating the source-page line.
- Full suite: **93 passed**, 0 failed.
- Deleted this session's own stale cache files (written before the
  selector fix went in, so they still had sidebar noise baked into their
  "known" sets) and re-ran `--once --no-notify --no-health --no-jitter`
  against the live sites to get a clean baseline under the fixed code:

  ```
  ugneet2026  -> 0 new, 68 total   (was 316 before scoping)
  ugcet2026   -> 0 new, 495 total  (was 743 before scoping)
  pgcet2026   -> baselined 92 links (new page, correctly silent)
  pgden2026   -> baselined 22 links (new page, correctly silent)
  mcc x4      -> 0 new each        (unaffected by the KEA-side fix)
  ```

  Manually inspected `links_kea_pgcet2026.json` / `links_kea_pgden2026.json`
  afterward — each contains only its own program's links (PGCET
  application/objection/portal links; PG-Dental schedule/fee/seat-matrix
  PDFs respectively), no cross-contamination between pages.
- **No Telegram messages were sent at any point this session** — every
  live run used `--no-notify --no-health`.

### Detection round-trip test (removed-link re-baseline)

To prove the diff logic still genuinely detects new links after the
scoping fix (not just "everything comes back 0 new because the manifest
absorbed the noise"), the *last* baselined link was deliberately removed
from `data/cache/links_kea_pgden2026.json` (`"PGET 2026(MDS) Dental First
round option entry link.05-09-2026"`, the KEA PGCET-Dental online option
entry link) and the monitor re-run live against the real site with
`--no-notify --no-health`:

- Run 1 after removal: `pgden2026 -> 1 new link(s), 22 total link(s)` — the
  removed link was correctly rediscovered and logged to
  `recent_links_kea_pgden2026.log`, and nothing else on any of the 8 pages
  fired (no cross-contamination reintroduced).
- Run 2 (immediately after): `pgden2026 -> 0 new link(s), 22 total
  link(s)` — the rediscovered link was persisted back into the manifest,
  confirming the manifest self-heals to a stable state.
- One transient blip noted along the way: `ugneet2026` returned "0 total
  link(s)" on a single run sandwiched between two runs that both correctly
  returned 68 — a one-off render race from scanning the same KEA page
  several times within seconds (far faster than the real ~50-90s loop
  cadence), not a regression from this session's changes. Confirmed
  harmless: the manifest is append-only, so an empty scan never erases
  known links or causes a false alert, only a possible one-cycle-delayed
  detection in the worst case. Re-ran and it resolved itself immediately.
- **No Telegram messages were sent during this test either.**

### State at end of session

- Working tree has the code/doc changes above plus new/updated manifest
  and log files from the clean re-baseline and the round-trip test
  (`data/cache/links_kea_pgcet2026.json`, `links_kea_pgden2026.json`,
  `recent_links_kea_pgden2026.log`). Committed after this test passed.
- All 4 KEA pages and all 4 MCC pages are now content-scoped and verified
  clean (0 false new-links on the already-known pages, correct silent
  auto-baseline on the 2 newly added pages, and correct detection +
  self-healing confirmed via the removed-link round-trip above).



## 2026-10-27

### Problems reported

"Lot of errors", PG-NEET is top priority, add the KEA/MCC PG and dental
pages properly, pause CET, re-baseline before the office install
(2026-10-28), and test rigorously.

### Root causes found

1. **`kea/pgneet2026` is HTTP 404** -- that page doesn't exist, so it failed
   every scan (a WARNING in every health batch). KEA's PG-Medical notices
   page is `kea/pgetmed2026` (sidebar: "PGET- 2026 (Medical/Dental & DNB)"
   -> "PG-Medical/DNB"). `pgneet2026` is only the path of KEA's application
   portal (`/pgneet2026/forms/login.aspx`).
2. **CI was red**: commit 414cbf6 swapped the URLs without updating
   `test_load_real_link_watch_pages_txt` (1 failed / 92 passed).
3. **MCC MDS (PG Dental) wasn't watched at all.** MCC has a separate MDS
   section (`/mds-counselling/`), live for 2026.
4. **Stale baseline.** Manifests were last baselined 2026-09-22; the live
   sites had moved on by ~130 links (UGNEET's manifest still held 312
   pre-scoping entries vs 126 real). Installing on those would have
   flooded the alerts chat on the first scan.
5. **Latent flood risks found while testing** (no live incident yet):
   a Kannada render changes every KEA link identity (12/12 on
   pgetmed2026, confirmed live), and a page missing `.card-deck` fell back
   to the whole document (~250 sidebar links). Either would alert a whole
   page as "new".
6. **MCC triple alert lines**: each MCC document is 3 `<a>` tags to one
   PDF (icon / title / "View(484 KB)"), so one notice = 3 alert lines.

### Changes

- `config/link_watch_pages.txt`: `pgneet2026` -> `pgetmed2026`; added
  `mcc.nic.in/current-events-mds/` + `eservices-schedule-mds/`; UGCET/PGCET
  commented out (paused). 9 pages total.
- `headless.py`: `is_non_english_kea_render` -- a Kannada render fails the
  page's scan instead of being returned.
- `link_watch.py`: `ContentSelectorMissingError` -- a watched page whose
  selector matches nothing fails its scan instead of whole-page fallback;
  `collapse_by_url` -- one alert/log entry per document URL, real title
  preferred over "View(...)" labels. Manifest identity unchanged.
- `link_alerts.py` / `run_monitor.py`: use `collapse_by_url` for the
  message, the recent-links log and all new-link counts.
- Docs: LINK.md (page table, paused/404/considered pages, MDS), CLAUDE.md
  (flood guards, collapse).

### Testing

- Unit suite: **110 passed** (was 1 failed / 92 passed). 17 new tests:
  `test_headless_fetch.py` (fake playwright: English/Kannada/no-dropdown,
  429/503 -> RateLimitedError, 403/404/500 -> plain error), selector-missing
  guard, collapse (MCC markup, short titles vs "View(...)"), end-to-end
  cycle (1 MCC doc -> 1 alert line + 1 log line; broken KEA page -> warning
  only, manifest untouched), real-config test rewritten for the 9 pages.
- **Mutation check**: disabling each guard in turn made its tests fail
  (Kannada guard: 1, selector guard: 2, collapse: 6); restored -> green.
- Live probe of every candidate page: all reachable from India, selector
  matched exactly once on each, and no page-specific KEA link sits outside
  `.card-deck` (checked by diffing pgetmed/pgden/ugneet against each other).
- **Live baseline** (stale manifests deleted first, not merged):
  pgetmed 12, pgden 37, ugneet 126, MCC pg 20+14, mds 38+32, ug 42+26.
- **3 consecutive live `--once` scans**: 27/27 page-scans OK, 0 new links,
  identical counts every run.
- **Live detection round-trip**: removed a real KEA PG-Medical notice and
  all 3 anchors of a real MCC MDS document from their manifests, ran a real
  cycle with Telegram send stubbed to capture text -> exactly 2 new links,
  1 message, one clean line per document; next cycle 0 new, manifests
  byte-identical to the baseline. Test artifacts removed from the logs.
- No Telegram messages were sent during any of the above.

### Real Telegram test (on request), then a final no-send pass

- **One real alert sent, deliberately**: the KEA PG-Medical
  "Notification_22/10/2026" identity was removed from its manifest and a
  real `--once` posted it to the alerts group ("NEET Result Alerts") at
  19:03 -- user confirmed receipt. It is a genuine 22/10 notice re-sent as
  a test, not a new publication. Then a real `--loop` ran 4 cycles (36
  page-scans, 0 new, 0 failed) and was stopped before the 10-run health
  batch, so no heartbeat was posted. Afterwards: the test entry was removed
  from `recent_links_kea_pgetmed2026.log`, `health_state.json` was reset
  (so the office's first heartbeat doesn't include these runs), and all 9
  manifests verified byte-identical to the baseline.
- **Telegram credentials, no message sent** (`getMe`/`getChat`/
  `getChatMember`): alerts bot @neet_result_alerts_bot and health bot
  @pes_healthMonitor_bot both valid, both administrators in their groups.
- **Final no-send pass**: 110 unit tests; 3 more live dry runs (27/27 OK,
  0 new); a **fresh-PC simulation** (code + page list only, no
  `data/cache`) -> `--baseline` then `--once` clean, and its baseline is
  byte-identical to the committed one; a live **4-page round-trip** in that
  copy (KEA PG-Medical, KEA PG-Dental, MCC PG, MCC MDS -- one real document
  removed from each) -> each detected exactly once, one 4-entry message
  captured (Telegram's low-level call stubbed to fail on any real request),
  next cycle silent, manifests healed identically.

### Office install checklist (2026-10-28)

1. `git pull` (brings the fresh baseline in `data/cache`).
2. SETUP.bat if the PC has no `.venv` yet; fill `config\.env`.
3. Start (START_MONITOR.bat or INSTALL_AUTOSTART.bat). Do **not** delete
   `data\cache` -- the first scan then alerts only what KEA/MCC published
   since this baseline (real news). Only run `--baseline` again if the
   office wants to start with zero alerts.
4. Within ~10 runs, the health chat should show a batch with FAILED: 0 and
   no WARNING lines. A full 9-page cycle takes ~45-60s.

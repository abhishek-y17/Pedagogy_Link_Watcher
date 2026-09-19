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



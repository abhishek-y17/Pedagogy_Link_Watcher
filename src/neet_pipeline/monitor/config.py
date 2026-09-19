"""
Load the pages the link-watch monitor watches.

config/link_watch_pages.txt (hand-edited, one URL per line) is the single
source of truth for what's watched -- no page list should be hardcoded in
monitor code.
"""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from . import watched_pages as wp

DEFAULT_LOOP_INTERVAL = 60

# Per-host CSS-selector override limiting link extraction to a page's actual
# content area, dropping the site-wide nav/header/footer chrome that's
# identical across every page on the same site -- without this, watching two
# pages on the same site (e.g. MCC's UG and PG full-list pages) means any
# edit to that shared chrome (a nav item added, a footer link changed) fires
# a duplicate false alert on every watched page on that site simultaneously.
# See link_watch.py::extract_all_links's content_selector param.
#
# mcc.nic.in confirmed live 2026-09-19: <header id="mainHeader"> holds the
# nav menu, <footer id="mainFooter"> holds the govt footer links, and
# <main> holds only the actual event-list content -- scoping to "main" drops
# the shared chrome cleanly.
#
# cetonline.karnataka.gov.in (KEA) confirmed live 2026-09-19 across all 4
# watched pages (ugneet2026/ugcet2026/pgcet2026/pgden2026): every page uses
# the identical template -- a 235-link <nav> (the full program sidebar,
# source of the PGCET/PG-Dental/PG-AYUSH links leaking into UGCET/UGNEET
# alerts), a 4-link <section class="pu-text"> banner (just "Home"/
# "Admissions"), and a 15-link shared <footer> -- around a single
# `div.card-deck` that holds only that page's own notices. ".card-deck"
# scopes to that div.
_CONTENT_SELECTOR_BY_HOST = {
    "mcc.nic.in": "main",
    "cetonline.karnataka.gov.in": ".card-deck",
}


@dataclass
class LinkWatchPage:
    key: str
    name: str
    url: str
    content_selector: str | None = None


@dataclass
class MonitorConfig:
    link_watch: list[LinkWatchPage] = field(default_factory=list)


def load_config(path: str = wp.DEFAULT_LINK_WATCH_PAGES_TXT) -> MonitorConfig:
    link_watch: list[LinkWatchPage] = []
    seen_keys: set[str] = set()
    for url in wp.load_pages(path):
        key = wp.derive_key(url)
        while key in seen_keys:  # slug collision -> disambiguate deterministically
            key = f"{key}_{hashlib.sha1(url.encode()).hexdigest()[:6]}"
        seen_keys.add(key)
        host = (urlsplit(url).hostname or "").lower()
        content_selector = _CONTENT_SELECTOR_BY_HOST.get(host)
        link_watch.append(LinkWatchPage(
            key=key, name=wp.derive_name(url), url=url,
            content_selector=content_selector,
        ))
    return MonitorConfig(link_watch=link_watch)

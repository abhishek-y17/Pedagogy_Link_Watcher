"""
Load the pages the link-watch monitor watches.

config/link_watch_pages.txt (hand-edited, one URL per line) is the single
source of truth for what's watched -- no page list should be hardcoded in
monitor code.
"""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field

from . import watched_pages as wp

DEFAULT_LOOP_INTERVAL = 600


@dataclass
class LinkWatchPage:
    key: str
    name: str
    url: str


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
        link_watch.append(LinkWatchPage(key=key, name=wp.derive_name(url), url=url))
    return MonitorConfig(link_watch=link_watch)

"""
Hand-edited list of counselling pages watched for NEW links.

`config/link_watch_pages.txt` is the one place staff edit to change which
pages the all-link watch covers: one URL per line, blank lines and `#`
comments ignored. `monitor/config.py::load_config` reads this file directly.

This module is a tiny read-only loader: missing-file tolerant, no network,
stdlib only. It must NOT import `config` or `link_watch` -- `config` imports
this, so importing back would be a cycle.
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlsplit

DEFAULT_LINK_WATCH_PAGES_TXT = os.path.join("config", "link_watch_pages.txt")


def is_valid_page_url(url: str) -> bool:
    parts = urlsplit((url or "").strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def normalize_for_dedupe(url: str) -> str:
    """
    Page-list identity only: fold trailing slash and case so the same page
    listed twice collapses to one entry. This is deliberately NOT
    link_watch.normalize_url_for_identity -- that one is for the links
    found ON a page and keeps meaningful query params.
    """
    return (url or "").strip().rstrip("/").lower()


def _strip_inline_comment(line: str) -> str:
    # a trailing " # comment" is a comment; a "#" with no leading space is
    # only a comment when it starts the line (handled by the caller).
    idx = line.find(" #")
    return line[:idx].strip() if idx != -1 else line.strip()


def load_pages(path: str = DEFAULT_LINK_WATCH_PAGES_TXT) -> list[str]:
    if not os.path.exists(path):
        return []

    out: list[str] = []
    seen: set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            line = _strip_inline_comment(line)
            if not line:
                continue
            if not is_valid_page_url(line):
                print(f"WARNING: skipping invalid link-watch page URL in {path}: {line!r}")
                continue
            norm = normalize_for_dedupe(line)
            if norm in seen:
                continue
            seen.add(norm)
            out.append(line)
    return out


def derive_key(url: str) -> str:
    path = urlsplit((url or "").strip()).path
    slug = re.sub(r"[^a-z0-9]+", "_", path.strip("/").lower()).strip("_")
    if slug:
        return slug
    host_slug = re.sub(r"[^a-z0-9]+", "_", urlsplit((url or "").strip()).netloc.lower()).strip("_")
    return host_slug or "page"


def derive_name(url: str) -> str:
    # alerts render "Page: <name>" + "Source page: <url>"; the raw URL is
    # the clearest name for a hand-listed page.
    return url

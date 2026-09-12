"""
Human-readable "recent links" feed for the KEA link watch — one file per page.

`data/cache/links_<page_key>.json` is the full dedup set the diff runs against
(hundreds of entries, unordered — a government portal legitimately links to
years of archives). That file answers "have we seen this link before"; it is
not meant for a human to skim.

This module keeps a small companion log **per watched page**:

    data/cache/recent_links_<page_key>.log

e.g. `recent_links_kea_ugneet2026.log` and `recent_links_kea_ugcet2026.log`.
Each holds the last `MAX_RECENT` links the monitor flagged as new on that
page, **newest on top**. Every scan prepends any freshly detected links; the
file never grows past `MAX_RECENT` entries.

Paths are built from `manifest.CACHE_DIR`, so anything that isolates the
manifest directory in a test isolates these logs too.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

from . import manifest as manifest_mod

MAX_RECENT = 20


def _safe_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", key or "page")


def recent_links_path(page_key: str) -> str:
    return os.path.join(manifest_mod.CACHE_DIR, f"recent_links_{_safe_key(page_key)}.log")


def _header(page_name: str) -> str:
    return (
        f"# {page_name} — recent links, newest on top, last {MAX_RECENT} the monitor flagged as new.\n"
        f"# Auto-updated every scan. Format:  <detected-at>  |  <link text>  |  <url>\n"
        f"# The full set the diff runs against lives alongside this file as links_<page>.json.\n"
    )


_SEP = "  |  "


def _format_entry(detected_at: str, text: str, url: str) -> str:
    label = (text or "(no link text)").replace("\n", " ").strip()
    return f"{detected_at}{_SEP}{label}{_SEP}{url}"


def _entry_url(entry: str) -> str:
    return entry.rsplit(_SEP, 1)[-1].strip()


def _read_entries(path: str) -> list[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [ln.rstrip("\n") for ln in f if ln.strip() and not ln.lstrip().startswith("#")]


def _write(path: str, page_name: str, entries: list[str]) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(_header(page_name))
        f.write("\n")
        f.write("\n".join(entries[:MAX_RECENT]))
        if entries:
            f.write("\n")
    os.replace(tmp, path)


def record_new_links(page_key: str, page_name: str, links,
                     detected_at: str | None = None) -> int:
    """Prepend freshly-detected links for one page to its own recent-links log.

    `links` is any iterable of objects with `.text` and `.url` (PageLink), or
    `(text, url)` tuples. Order within the batch is preserved (first stays on
    top). Best-effort: never raises — a logging failure must not break a scan.
    Returns the number of entries added.
    """
    items = list(links or [])
    if not items:
        return 0
    detected_at = detected_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = recent_links_path(page_key)
    try:
        new_entries, new_urls = [], set()
        for item in items:
            text = getattr(item, "text", None)
            url = getattr(item, "url", None)
            if url is None and isinstance(item, (tuple, list)) and len(item) == 2:
                text, url = item
            new_entries.append(_format_entry(detected_at, text or "", url or ""))
            new_urls.add((url or "").strip())
        # keep this feed to one line per URL: an existing line for a URL we are
        # re-recording now is dropped so the fresh (top) line wins.
        kept = [e for e in _read_entries(path) if _entry_url(e) not in new_urls]
        _write(path, page_name, new_entries + kept)
        return len(new_entries)
    except OSError as e:  # pragma: no cover - disk-full / permissions
        print(f"WARNING: could not update {path}: {type(e).__name__}: {e}")
        return 0


def seed(page_key: str, page_name: str, entries) -> int:
    """One-time initialisation for one page's log.

    `entries` is an iterable of `(detected_at, text, url)` tuples, already
    ordered newest-first. Overwrites any existing file for that page.
    """
    lines = [_format_entry(*e) for e in entries]
    _write(recent_links_path(page_key), page_name, lines)
    return min(len(lines), MAX_RECENT)


def read_recent(page_key: str) -> list[str]:
    return _read_entries(recent_links_path(page_key))

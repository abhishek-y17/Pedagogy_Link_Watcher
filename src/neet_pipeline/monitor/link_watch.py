"""
Headless all-link watch for KEA pages.

This is intentionally separate from the result-PDF detector in core.py:
a new link here only means "something changed, go look". It never triggers
scraping, matching, or the confirmed-result review flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from . import manifest as manifest_mod
from .config import LinkWatchPage
from .headless import fetch_rendered_html, RateLimitedError
from ..state import load_json, save_json_atomic


# Query params that are session / cache-buster / ad-tracking noise on
# essentially every site. This set is deliberately conservative: it does
# NOT contain ambiguous keys like `id`, `t` or `token`. On government
# portals `?id=` is routinely the real document key, and folding
# `?id=101` and `?id=102` into one identity would silently hide the
# second published notice -- the exact failure this watch exists to
# prevent. Ambiguous keys are handled two other ways: by the shape of
# their value (`_looks_like_session_token`) and by an explicit
# `volatile_params` / `keep_params` override passed in code (see
# normalize_url_for_identity below).
VOLATILE_QUERY_PARAMS = {
    "_",
    "cache",
    "cachebuster",
    "cb",
    "fbclid",
    "gclid",
    "jsessionid",
    "msclkid",
    "phpsessid",
    "session",
    "sessionid",
    "sid",
    "time",
    "timestamp",
    "ts",
}

# Keys that are sometimes a real document key and sometimes a session
# nonce. Treated as volatile ONLY when the value looks like a token
# (see _looks_like_session_token) -- a caller can also pass extra
# volatile_params/keep_params to normalize_url_for_identity/extract_all_links
# for a page with unusual query-param behavior.
_AMBIGUOUS_QUERY_PARAMS = {"id", "t", "tok", "token", "nonce", "auth"}

# Value shapes that are never a human-meaningful document id: long hex
# digests, long opaque alnum tokens, and 10+ digit epoch-style stamps.
_HEX_TOKEN_RE = re.compile(r"\A[0-9a-f]{16,}\Z", re.IGNORECASE)
_OPAQUE_TOKEN_RE = re.compile(r"\A(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9_-]{20,}\Z")
_EPOCH_LIKE_RE = re.compile(r"\A\d{10,}\Z")


def _looks_like_session_token(value: str) -> bool:
    v = (value or "").strip()
    return bool(
        _HEX_TOKEN_RE.match(v)
        or _OPAQUE_TOKEN_RE.match(v)
        or _EPOCH_LIKE_RE.match(v)
    )


@dataclass(frozen=True)
class LinkIdentity:
    normalized_url: str
    text: str


@dataclass
class PageLink:
    url: str
    normalized_url: str
    text: str

    @property
    def identity(self) -> LinkIdentity:
        return LinkIdentity(self.normalized_url, self.text)


@dataclass
class LinkWatchResult:
    page: LinkWatchPage
    ok: bool
    links: list[PageLink] = field(default_factory=list)
    new_links: list[PageLink] = field(default_factory=list)
    known_identities: set[LinkIdentity] = field(default_factory=set)
    current_identities: set[LinkIdentity] = field(default_factory=set)
    error: str | None = None
    # True only on a page's first ever scan: every link is recorded as
    # "known" and NOTHING is alerted on. Adding a page never floods the
    # chat; you are only alerted for links added after this scan.
    baselined: bool = False
    # True when `error` was caused by a 429/503 response -- run_monitor.py
    # uses this to trigger a backoff period rather than retrying next cycle
    # like an ordinary transient failure.
    rate_limited: bool = False


def _safe_key(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", key)


def link_manifest_path(page_key: str) -> str:
    return os.path.join(manifest_mod.CACHE_DIR, f"links_{_safe_key(page_key)}.json")


def link_manifest_exists(page_key: str) -> bool:
    """Whether this page has ever been scanned. `False` -> next scan
    baselines (records all links, alerts on none). Note: a present but
    empty ([] on disk) manifest returns True -- "never scanned" and "no
    links last scan" are different states."""
    return os.path.exists(link_manifest_path(page_key))


def read_link_manifest(page_key: str) -> set[LinkIdentity]:
    path = link_manifest_path(page_key)
    raw = load_json(path, [])

    identities: set[LinkIdentity] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        normalized_url = item.get("normalized_url")
        text = item.get("text")
        if isinstance(normalized_url, str) and isinstance(text, str):
            identities.add(LinkIdentity(normalized_url, text))
    return identities


def write_link_manifest(page_key: str, identities: set[LinkIdentity]) -> None:
    path = link_manifest_path(page_key)
    payload = [
        {"normalized_url": ident.normalized_url, "text": ident.text}
        for ident in sorted(identities, key=lambda i: (i.normalized_url, i.text))
    ]
    save_json_atomic(path, payload)


def _is_volatile_param(name: str, value: str = "",
                       extra_volatile: frozenset = frozenset(),
                       keep: frozenset = frozenset()) -> bool:
    lower = (name or "").lower()
    if lower in keep:
        return False
    if lower in VOLATILE_QUERY_PARAMS or lower in extra_volatile or lower.startswith("utm_"):
        return True
    if lower in _AMBIGUOUS_QUERY_PARAMS and _looks_like_session_token(value):
        return True
    return False


def _netloc_lower_host(parts) -> str:
    host = (parts.hostname or "").lower()
    if not host:
        return parts.netloc.lower()
    if parts.port:
        default_port = (parts.scheme.lower() == "http" and parts.port == 80) or (
            parts.scheme.lower() == "https" and parts.port == 443
        )
        if not default_port:
            host = f"{host}:{parts.port}"
    return host


def normalize_url_for_identity(url: str, volatile_params: frozenset = frozenset(),
                               keep_params: frozenset = frozenset()) -> str:
    """
    Stable link identity URL: lowercase scheme/host, remove volatile query
    tokens, keep path plus meaningful query params, and drop fragments.

    `volatile_params` / `keep_params` let a caller declare a verified session
    key to strip, or force-keep a key the value heuristic would otherwise
    treat as a token. No config source sets these today -- they exist for a
    page whose query params misbehave, should one show up.
    """
    parts = urlsplit((url or "").strip())
    kept_params = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_volatile_param(name, value, volatile_params, keep_params)
    ]
    kept_params.sort(key=lambda item: (item[0].lower(), item[1]))
    return urlunsplit((
        parts.scheme.lower(),
        _netloc_lower_host(parts),
        parts.path or "/",
        urlencode(kept_params, doseq=True),
        "",
    ))


def normalize_link_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_all_links(html: str, base_url: str, volatile_params: frozenset = frozenset(),
                      keep_params: frozenset = frozenset()) -> list[PageLink]:
    """Extract every HTTP(S) <a href> link, not just PDFs."""
    soup = BeautifulSoup(html or "", "html.parser")
    seen: dict[LinkIdentity, PageLink] = {}
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href:
            continue
        url = urljoin(base_url, href)
        scheme = urlsplit(url).scheme.lower()
        if scheme not in ("http", "https"):
            continue
        text = normalize_link_text(a.get_text(separator=" ", strip=True))
        normalized_url = normalize_url_for_identity(url, volatile_params, keep_params)
        link = PageLink(url=url, normalized_url=normalized_url, text=text)
        seen.setdefault(link.identity, link)
    return sorted(seen.values(), key=lambda link: (link.normalized_url, link.text, link.url))


def check_link_page(page: LinkWatchPage) -> LinkWatchResult:
    try:
        html = fetch_rendered_html(page.url)
        links = extract_all_links(html, page.url)
        manifest_present = link_manifest_exists(page.key)
        known = read_link_manifest(page.key)
        current = {link.identity for link in links}
        if not manifest_present:
            # first ever scan: record every current link, alert on none
            new_links, baselined = [], True
        else:
            new_links = [link for link in links if link.identity not in known]
            baselined = False
        return LinkWatchResult(
            page=page,
            ok=True,
            links=links,
            new_links=new_links,
            known_identities=known,
            current_identities=current,
            baselined=baselined,
        )
    except Exception as e:
        return LinkWatchResult(
            page=page,
            ok=False,
            error=f"{type(e).__name__}: {e}",
            rate_limited=isinstance(e, RateLimitedError),
        )


def persist_link_result(result: LinkWatchResult) -> None:
    if not result.ok:
        return
    write_link_manifest(
        result.page.key,
        set(result.known_identities) | set(result.current_identities),
    )

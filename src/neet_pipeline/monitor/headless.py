"""
Stage 5 — headless-browser rendering. For result-PDF detection this remains
an optional fallback for a site whose PDF links are injected client-side
(requests+bs4 can't see them; see detect.py::likely_js_rendered). The
separate KEA link-watch path uses this renderer first because those pages
robots-block plain fetches and render link lists through JavaScript.

If playwright or Chromium is not installed, this fails LOUDLY with a clear,
actionable message rather than silently reporting nothing.
"""

from __future__ import annotations

_HEADLESS_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")

# Playwright doesn't send Chromium's Sec-Ch-Ua client-hint headers by
# default. Their absence -- while the UA string claims a real Chrome build --
# was enough on its own for mcc.nic.in's Akamai Bot Manager to flag the
# request and return HTTP 403, confirmed live; adding these (matching the
# UA's Chrome version) alongside the UA is sufficient, no automation-flag
# tricks or navigator.webdriver patching required.
_HEADLESS_EXTRA_HEADERS = {
    "Accept-Language": "en-IN,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="122", "Google Chrome";v="122", "Not?A_Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}


class HeadlessUnavailableError(RuntimeError):
    """playwright itself isn't installed/usable -- distinct from the
    target site blocking the headless browser (see fetch_rendered_html)."""


class RateLimitedError(RuntimeError):
    """The site responded 429 (Too Many Requests) or 503 (Service
    Unavailable) -- back off for a while rather than retrying immediately,
    since retrying at the same cadence risks a longer/harder block."""

    def __init__(self, status_code: int, url: str):
        self.status_code = status_code
        super().__init__(f"Rate-limited fetching {url}: HTTP {status_code}")


def fetch_rendered_html(url: str, timeout_ms: int = 30000) -> str:
    """
    Renders `url` in headless Chromium and returns the fully-loaded HTML.

    Raises HeadlessUnavailableError if playwright/Chromium isn't installed.
    Raises RuntimeError if the site's own defenses block the headless
    browser despite `_HEADLESS_EXTRA_HEADERS` -- mcc.nic.in's WAF (Akamai
    Bot Manager) is known to 403 headless Chromium missing those headers
    (see `_HEADLESS_EXTRA_HEADERS`'s comment). That is a materially
    different failure than "playwright missing" and is reported as such.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise HeadlessUnavailableError(
            "playwright is not installed -- headless fallback unavailable. "
            "Install with: pip install playwright && playwright install chromium"
        ) from e

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as e:
            raise HeadlessUnavailableError(
                "playwright Chromium is not installed or could not launch. "
                "Install with: pip install playwright && playwright install chromium"
            ) from e
        try:
            page = browser.new_page(
                user_agent=_HEADLESS_UA,
                extra_http_headers=_HEADLESS_EXTRA_HEADERS,
            )
            resp = page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            if resp is not None and resp.status in (429, 503):
                raise RateLimitedError(resp.status, url)
            if resp is not None and resp.status >= 400:
                raise RuntimeError(
                    f"Headless browser was blocked fetching {url}: HTTP {resp.status}. "
                    f"Some sites (e.g. mcc.nic.in's Akamai Bot Manager) block headless "
                    f"Chromium outright, not just requests+bs4."
                )
            _try_switch_to_english(page, timeout_ms)
            try:
                html = page.content()
            except Exception:
                # a postback triggered by the language switch may still be
                # settling -- give it a moment and read once more.
                page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(500)
                html = page.content()
            if is_non_english_kea_render(html):
                raise RuntimeError(
                    f"{url} rendered in Kannada -- the English language switch did not "
                    f"take. Skipping this scan rather than alerting every link on the "
                    f"page under its Kannada text; the next scan retries."
                )
            return html
        finally:
            browser.close()


def is_non_english_kea_render(html: str) -> bool:
    """
    True when `html` carries KEA's `#ddlLanguage` dropdown with an English
    option, but the server-selected option is not English.

    Link identity is (url, link text), and KEA renders every link's text in
    the selected language -- confirmed live 2026-10-27: a Kannada render of
    kea/pgetmed2026 changed 12 of 12 identities. So if
    `_try_switch_to_english` silently fails on one run, every link on every
    KEA page would alert as "new". Failing that page's scan instead keeps
    the problem in the health chat, not the alerts chat.

    Checks the returned HTML (ASP.NET marks the active option with
    `selected="selected"` after the postback), not the live browser state.
    """
    from bs4 import BeautifulSoup

    select = BeautifulSoup(html or "", "html.parser").select_one("#ddlLanguage")
    if select is None or select.select_one("option[value='E']") is None:
        return False
    selected = select.select_one("option[selected]")
    return selected is None or selected.get("value") != "E"


def _try_switch_to_english(page, timeout_ms: int) -> None:
    """
    KEA's cetonline pages carry an ASP.NET language dropdown
    (`#ddlLanguage`, options `K` / `E`) and render every link's visible text
    in the selected language. Default is Kannada; switch to English so link
    identities and the recent-links feed are readable.

    Best-effort: any site without that exact control, or any failure here,
    is silently ignored -- the language switch is a nicety, never fatal.
    """
    try:
        if not page.query_selector("#ddlLanguage option[value='E']"):
            return
        if page.eval_on_selector("#ddlLanguage", "el => el.value") == "E":
            return
        page.select_option("#ddlLanguage", "E")
        # the switch fires an ASP.NET __doPostBack (full page reload). Poll in
        # the browser until the reload is done and the dropdown reads "E";
        # wait_for_function survives the navigation that wait_for_load_state
        # can race against.
        page.wait_for_function(
            "() => document.readyState === 'complete'"
            " && document.querySelector('#ddlLanguage')"
            " && document.querySelector('#ddlLanguage').value === 'E'",
            timeout=timeout_ms,
        )
        page.wait_for_timeout(300)
    except Exception:
        pass

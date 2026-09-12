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


class HeadlessUnavailableError(RuntimeError):
    """playwright itself isn't installed/usable -- distinct from the
    target site blocking the headless browser (see fetch_rendered_html)."""


def fetch_rendered_html(url: str, timeout_ms: int = 30000) -> str:
    """
    Renders `url` in headless Chromium and returns the fully-loaded HTML.

    Raises HeadlessUnavailableError if playwright/Chromium isn't installed.
    Raises RuntimeError if the site's own defenses block the headless
    browser -- confirmed live against mcc.nic.in, whose WAF (Akamai Bot
    Manager) returns HTTP 403 to headless Chromium even with basic
    UA-spoofing and navigator.webdriver patched out. That is a materially
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
            page = browser.new_page(user_agent=_HEADLESS_UA)
            resp = page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            if resp is not None and resp.status >= 400:
                raise RuntimeError(
                    f"Headless browser was blocked fetching {url}: HTTP {resp.status}. "
                    f"Some sites (e.g. mcc.nic.in's Akamai Bot Manager) block headless "
                    f"Chromium outright, not just requests+bs4."
                )
            _try_switch_to_english(page, timeout_ms)
            try:
                return page.content()
            except Exception:
                # a postback triggered by the language switch may still be
                # settling -- give it a moment and read once more.
                page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(500)
                return page.content()
        finally:
            browser.close()


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

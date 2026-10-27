"""fetch_rendered_html with a fake playwright: status handling and the
Kannada-render guard (see headless.py::is_non_english_kea_render)."""

import sys
import types

import pytest

from neet_pipeline.monitor import headless
from neet_pipeline.monitor.headless import RateLimitedError, is_non_english_kea_render

_KANNADA = ('<select id="ddlLanguage"><option selected="selected" value="K">Kannada</option>'
            '<option value="E">English</option></select><div class="card-deck">x</div>')
_ENGLISH = ('<select id="ddlLanguage"><option value="K">Kannada</option>'
            '<option selected="selected" value="E">English</option></select>'
            '<div class="card-deck">x</div>')


class _Resp:
    def __init__(self, status):
        self.status = status


class _Page:
    def __init__(self, html, status):
        self._html, self._status = html, status

    def goto(self, url, timeout=None, wait_until=None):
        return _Resp(self._status)

    def content(self):
        return self._html


class _Browser:
    def __init__(self, page):
        self._page = page
        self.closed = False

    def new_page(self, **kwargs):
        assert "Sec-Ch-Ua" in kwargs["extra_http_headers"]  # mcc.nic.in WAF needs these
        return self._page

    def close(self):
        self.closed = True


def _install_fake_playwright(monkeypatch, html, status=200):
    browser = _Browser(_Page(html, status))

    class _Ctx:
        def __enter__(self):
            return types.SimpleNamespace(
                chromium=types.SimpleNamespace(launch=lambda: browser))

        def __exit__(self, *exc):
            return False

    sync_api = types.ModuleType("playwright.sync_api")
    sync_api.sync_playwright = _Ctx
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    monkeypatch.setattr(headless, "_try_switch_to_english", lambda page, timeout_ms: None)
    return browser


def test_english_render_is_returned(monkeypatch):
    browser = _install_fake_playwright(monkeypatch, _ENGLISH)
    assert headless.fetch_rendered_html("https://kea.example/p") == _ENGLISH
    assert browser.closed


def test_kannada_render_fails_the_fetch_instead_of_returning(monkeypatch):
    browser = _install_fake_playwright(monkeypatch, _KANNADA)
    with pytest.raises(RuntimeError, match="Kannada"):
        headless.fetch_rendered_html("https://kea.example/p")
    assert browser.closed


def test_page_without_language_dropdown_is_returned(monkeypatch):
    _install_fake_playwright(monkeypatch, "<main><a href='/x.pdf'>X</a></main>")
    assert "x.pdf" in headless.fetch_rendered_html("https://mcc.example/p")


@pytest.mark.parametrize("status", [429, 503])
def test_rate_limit_statuses_raise_rate_limited(monkeypatch, status):
    _install_fake_playwright(monkeypatch, _ENGLISH, status=status)
    with pytest.raises(RateLimitedError):
        headless.fetch_rendered_html("https://kea.example/p")


@pytest.mark.parametrize("status", [403, 404, 500])
def test_other_error_statuses_raise_plain_runtime_error(monkeypatch, status):
    _install_fake_playwright(monkeypatch, _ENGLISH, status=status)
    with pytest.raises(RuntimeError, match=f"HTTP {status}") as exc:
        headless.fetch_rendered_html("https://kea.example/p")
    assert not isinstance(exc.value, RateLimitedError)


def test_is_non_english_kea_render_cases():
    assert is_non_english_kea_render(_KANNADA) is True
    assert is_non_english_kea_render(_ENGLISH) is False
    assert is_non_english_kea_render("<main>no dropdown</main>") is False
    assert is_non_english_kea_render("") is False
    # dropdown present but nothing marked selected: browser defaults to the
    # first option (Kannada), so treat as not-English
    assert is_non_english_kea_render(
        '<select id="ddlLanguage"><option value="K">K</option><option value="E">E</option></select>'
    ) is True
    # a dropdown with no English option at all isn't KEA's -- leave it alone
    assert is_non_english_kea_render(
        '<select id="ddlLanguage"><option selected value="K">K</option></select>') is False

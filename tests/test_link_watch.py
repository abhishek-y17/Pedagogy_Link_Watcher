from neet_pipeline.monitor import link_watch as lw
from neet_pipeline.monitor import manifest as manifest_mod
from neet_pipeline.monitor.config import LinkWatchPage
from neet_pipeline.monitor.headless import RateLimitedError


def _page(**kw):
    return LinkWatchPage(
        key="kea_ugneet2026",
        name="KEA UG NEET 2026",
        url="https://cetonline.karnataka.gov.in/kea/ugneet2026",
        **kw,
    )


def test_normalization_strips_session_noise_but_keeps_meaningful_id():
    # `?id=` is a real document key on government portals -- two notices that
    # differ only by id must stay DISTINCT, while session/cache params drop.
    first = lw.normalize_url_for_identity(
        "https://EXAMPLE.com/view?id=101&sid=AAA&_=1700000000&round=2")
    second = lw.normalize_url_for_identity(
        "https://example.com/view?id=102&sid=BBB&_=1800000000&round=2")
    assert first == "https://example.com/view?id=101&round=2"
    assert second == "https://example.com/view?id=102&round=2"
    assert first != second


def test_normalization_strips_token_shaped_values_and_utm():
    first = lw.normalize_url_for_identity(
        "https://x.gov.in/doc?token=9f8e7d6c5b4a39281706abcd&utm_source=wa&round=1")
    second = lw.normalize_url_for_identity(
        "https://x.gov.in/doc?token=0011223344556677aabbccdd&round=1")
    assert first == second == "https://x.gov.in/doc?round=1"


def test_per_page_volatile_and_keep_overrides():
    stripped = lw.normalize_url_for_identity(
        "https://x.gov.in/l?pagesid=1&doc=5", volatile_params=frozenset({"pagesid"}))
    stripped2 = lw.normalize_url_for_identity(
        "https://x.gov.in/l?pagesid=2&doc=5", volatile_params=frozenset({"pagesid"}))
    assert stripped == stripped2 == "https://x.gov.in/l?doc=5"

    # keep_params forces retention of a value the heuristic would strip
    kept = lw.normalize_url_for_identity(
        "https://x.gov.in/l?token=9f8e7d6c5b4a39281706abcd", keep_params=frozenset({"token"}))
    assert "token=9f8e7d6c5b4a39281706abcd" in kept


def test_same_link_with_session_params_not_new_second_run(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    # page already baselined (empty manifest on disk) so the first scan
    # below diffs normally instead of silently recording everything.
    lw.write_link_manifest(page.key, set())
    html_1 = '<a href="/kea/doc.pdf?id=111&sid=1700000000&round=1">Round 1 Result</a>'
    html_2 = '<a href="/kea/doc.pdf?id=111&sid=1800000000&round=1">Round 1 Result</a>'

    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_1)
    first = lw.check_link_page(page)
    assert len(first.new_links) == 1
    lw.persist_link_result(first)

    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_2)
    second = lw.check_link_page(page)
    assert second.ok
    assert second.new_links == []


def test_distinct_document_ids_alert_separately(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    html_1 = '<a href="/kea/doc.pdf?id=111&round=1">Round 1 Result</a>'
    html_2 = (
        '<a href="/kea/doc.pdf?id=111&round=1">Round 1 Result</a>'
        '<a href="/kea/doc.pdf?id=222&round=2">Round 2 Result</a>'
    )

    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_1)
    lw.persist_link_result(lw.check_link_page(page))

    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_2)
    second = lw.check_link_page(page)
    assert [link.text for link in second.new_links] == ["Round 2 Result"]


def test_genuinely_new_link_is_detected_once(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    html_1 = '<a href="/kea/doc.pdf?id=111&round=1">Round 1 Result</a>'
    html_2 = (
        '<a href="/kea/doc.pdf?id=111&round=1">Round 1 Result</a>'
        '<a href="/kea/new-notice.pdf?sid=abc">New Notice</a>'
    )

    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_1)
    lw.persist_link_result(lw.check_link_page(page))

    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_2)
    second = lw.check_link_page(page)
    assert [link.text for link in second.new_links] == ["New Notice"]
    lw.persist_link_result(second)

    third = lw.check_link_page(page)
    assert third.new_links == []


def test_first_scan_of_new_page_baselines_and_alerts_on_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    html = (
        '<a href="/kea/a.pdf?id=1">Notice A</a>'
        '<a href="/kea/b.pdf?id=2">Notice B</a>'
        '<a href="/kea/c.pdf?id=3">Notice C</a>'
    )
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html)

    assert not lw.link_manifest_exists(page.key)
    first = lw.check_link_page(page)
    assert first.ok and first.baselined is True
    assert first.new_links == [] and len(first.links) == 3

    lw.persist_link_result(first)
    assert lw.link_manifest_exists(page.key)

    # one genuinely new link on the next scan is reported normally
    monkeypatch.setattr(
        lw, "fetch_rendered_html",
        lambda url: html + '<a href="/kea/d.pdf?id=4">Notice D</a>',
    )
    second = lw.check_link_page(page)
    assert second.baselined is False
    assert [link.text for link in second.new_links] == ["Notice D"]


def test_present_but_empty_manifest_is_not_a_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    lw.write_link_manifest(page.key, set())  # scanned before, saw nothing
    monkeypatch.setattr(
        lw, "fetch_rendered_html",
        lambda url: '<a href="/kea/x.pdf?id=9">New notice</a>',
    )
    result = lw.check_link_page(page)
    assert result.baselined is False
    assert [link.text for link in result.new_links] == ["New notice"]


def test_rate_limited_response_sets_flag_distinct_from_other_failures(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()

    def raise_429(url):
        raise RateLimitedError(429, url)

    monkeypatch.setattr(lw, "fetch_rendered_html", raise_429)
    result = lw.check_link_page(page)

    assert result.ok is False
    assert result.rate_limited is True
    assert "429" in result.error


def test_ordinary_failure_does_not_set_rate_limited_flag(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: (_ for _ in ()).throw(RuntimeError("blocked (403)")))
    result = lw.check_link_page(page)

    assert result.ok is False
    assert result.rate_limited is False


def test_link_manifest_survives_simulated_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    page = _page()
    html = '<a href="/kea/doc.pdf?id=111">Round 1 Result</a>'
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html)

    first = lw.check_link_page(page)
    lw.persist_link_result(first)

    # No process memory is reused here; check_link_page reads the on-disk
    # manifest again, which is what a fresh cron invocation depends on.
    second = lw.check_link_page(page)
    assert second.new_links == []
    assert lw.link_manifest_path(page.key).endswith("links_kea_ugneet2026.json")

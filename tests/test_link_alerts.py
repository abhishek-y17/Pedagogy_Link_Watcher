import pytest

from neet_pipeline.monitor.config import LinkWatchPage
from neet_pipeline.monitor.link_watch import LinkWatchResult, PageLink
from neet_pipeline.notifier import link_alerts
from neet_pipeline.notifier.link_alerts import (
    MAX_ALERT_CHARS, _split_for_telegram, format_link_alert_message, post_link_alerts,
)


def _result(page_key="kea", n_new=1):
    page = LinkWatchPage(key=page_key, name=f"Page {page_key}", url=f"https://kea.example/{page_key}")
    new_links = [
        PageLink(
            url=f"https://kea.example/{page_key}/doc{i}.pdf?id={i}",
            normalized_url=f"https://kea.example/{page_key}/doc{i}.pdf?id={i}",
            text=f"Notice number {i} for round something",
        )
        for i in range(n_new)
    ]
    return LinkWatchResult(page=page, ok=True, links=list(new_links), new_links=new_links)


def test_message_shows_source_page_once_not_a_duplicate_page_line():
    # page.name is the raw URL (see watched_pages.py::derive_name), so a
    # separate "Page:" line duplicated "Source page:" verbatim -- confirmed
    # live 2026-09-18, e.g. both read
    # "https://cetonline.karnataka.gov.in/kea/ugneet2026". Keep just one line.
    text = format_link_alert_message([_result(page_key="kea_ugneet2026")])
    assert text.count("Source page:") == 1
    assert "Page:" not in text
    assert "https://kea.example/kea_ugneet2026" in text


def test_split_short_text_is_one_chunk():
    chunks = _split_for_telegram("line one\nline two\nline three")
    assert chunks == ["line one\nline two\nline three"]


def test_split_long_text_packs_whole_lines_under_limit_and_rejoins():
    lines = [f"- Notice {i} https://kea.example/very/long/path/doc{i}.pdf?id={i}" for i in range(400)]
    text = "\n".join(lines)
    chunks = _split_for_telegram(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= MAX_ALERT_CHARS
    # no line was split; rejoining the chunks reproduces the original
    assert "\n".join(chunks) == text


def test_split_hard_slices_a_single_overlong_line():
    long_line = "x" * (MAX_ALERT_CHARS * 2 + 50)
    chunks = _split_for_telegram(long_line)
    assert len(chunks) == 3
    assert all(len(c) <= MAX_ALERT_CHARS for c in chunks)
    assert "".join(chunks) == long_line


def test_post_link_alerts_chunks_and_prefixes(monkeypatch):
    sent = []
    monkeypatch.setattr(link_alerts.tg, "send_message",
                        lambda token, chat_id, text: sent.append(text) or {"message_id": len(sent)})

    n = post_link_alerts("TOKEN", "-100", [_result(n_new=60)])

    assert n == len(sent) > 1
    for i, text in enumerate(sent, 1):
        assert text.startswith(f"(part {i}/{len(sent)})\n")
        assert len(text) <= 4096


def test_post_link_alerts_no_new_links_sends_nothing(monkeypatch):
    sent = []
    monkeypatch.setattr(link_alerts.tg, "send_message",
                        lambda *a, **k: sent.append(a))
    assert post_link_alerts("TOKEN", "-100", [_result(n_new=0)]) == 0
    assert sent == []


def test_post_link_alerts_propagates_send_failure(monkeypatch):
    calls = {"n": 0}

    def flaky(token, chat_id, text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("Telegram API request failed on sendMessage: HTTPError")
        return {"message_id": calls["n"]}

    monkeypatch.setattr(link_alerts.tg, "send_message", flaky)
    with pytest.raises(RuntimeError):
        post_link_alerts("TOKEN", "-100", [_result(n_new=60)])


def test_single_chunk_has_no_part_prefix(monkeypatch):
    sent = []
    monkeypatch.setattr(link_alerts.tg, "send_message",
                        lambda token, chat_id, text: sent.append(text))
    post_link_alerts("TOKEN", "-100", [_result(n_new=1)])
    assert len(sent) == 1
    assert not sent[0].startswith("(part ")


def test_message_lists_each_mcc_document_once_with_its_title():
    # mcc.nic.in: icon link, title link and "View(size)" link all point at
    # the same PDF -- one new document must be one alert entry, not three.
    page = LinkWatchPage(key="current_events_mds", name="mds",
                         url="https://mcc.nic.in/current-events-mds/")
    pdf = "https://cdnbbsr.s3waas.gov.in/uploads/2026/10/doc.pdf"
    new_links = [PageLink(pdf, pdf, ""), PageLink(pdf, pdf, "Round 2 Result MDS"),
                 PageLink(pdf, pdf, "View(484 KB)")]
    result = LinkWatchResult(page=page, ok=True, links=new_links, new_links=new_links)

    text = format_link_alert_message([result], timestamp="T")

    assert "Total new links: 1" in text
    assert text.count(pdf) == 1
    assert "- Round 2 Result MDS" in text
    assert "View(484 KB)" not in text and "(no link text)" not in text

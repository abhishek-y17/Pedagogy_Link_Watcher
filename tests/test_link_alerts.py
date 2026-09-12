import pytest

from neet_pipeline.monitor.config import LinkWatchPage
from neet_pipeline.monitor.link_watch import LinkWatchResult, PageLink
from neet_pipeline.notifier import link_alerts
from neet_pipeline.notifier.link_alerts import MAX_ALERT_CHARS, _split_for_telegram, post_link_alerts


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

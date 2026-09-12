import os
import pytest

from neet_pipeline.notifier import telegram_api as tg


def test_get_bot_token_raises_when_missing(tmp_path):
    env_path = str(tmp_path / "nope.env")
    with pytest.raises(tg.TelegramConfigError):
        tg.get_bot_token(env_path)


def test_get_chat_id_raises_when_missing(tmp_path):
    env_path = str(tmp_path / "nope.env")
    with pytest.raises(tg.TelegramConfigError):
        tg.get_chat_id(env_path)


def test_get_bot_token_reads_from_env_file(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("TELEGRAM_BOT_TOKEN=123:abc\nTELEGRAM_CHAT_ID=-999\n", encoding="utf-8")
    assert tg.get_bot_token(str(env_path)) == "123:abc"
    assert tg.get_chat_id(str(env_path)) == "-999"


def test_get_credentials_can_read_health_bot_vars(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("HEALTH_BOT_TOKEN=health:token\nHEALTH_CHAT_ID=-200\n", encoding="utf-8")
    assert tg.get_credentials(
        str(env_path),
        token_var="HEALTH_BOT_TOKEN",
        chat_id_var="HEALTH_CHAT_ID",
    ) == ("health:token", "-200")


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def test_send_message_posts_plain_text(monkeypatch):
    captured = {}

    def fake_post(url, data=None, files=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        return _FakeResponse({"ok": True, "result": {"message_id": 42}})

    monkeypatch.setattr(tg.requests, "post", fake_post)
    result = tg.send_message("TOKEN", "-100", "hello")

    assert result == {"message_id": 42}
    assert "TOKEN" in captured["url"]
    assert "sendMessage" in captured["url"]
    assert captured["data"]["text"] == "hello"
    # the button flow is gone: no inline-keyboard plumbing left
    assert "reply_markup" not in captured["data"]


def test_bot_only_helpers_are_removed():
    for gone in ("answer_callback_query", "edit_message_reply_markup", "get_updates"):
        assert not hasattr(tg, gone)


def test_send_document_opens_and_posts_file(monkeypatch, tmp_path):
    doc_path = tmp_path / "doc.pdf"
    doc_path.write_bytes(b"%PDF-1.4 fake content")
    captured = {}

    def fake_post(url, data=None, files=None, timeout=None):
        captured["files"] = files
        captured["data"] = data
        captured["timeout"] = timeout
        return _FakeResponse({"ok": True, "result": {"message_id": 7}})

    monkeypatch.setattr(tg.requests, "post", fake_post)
    result = tg.send_document("TOKEN", "-100", str(doc_path), caption="hi")

    assert result == {"message_id": 7}
    assert "document" in captured["files"]
    assert captured["data"]["caption"] == "hi"


def test_send_document_uses_a_longer_timeout_than_send_message(monkeypatch, tmp_path):
    """
    Regression test: a live post of a real ~9.5MB KEA result PDF timed out
    with the original 30s timeout shared by every call. send_document now
    gets its own, much longer timeout for the multipart upload.
    """
    doc_path = tmp_path / "doc.pdf"
    doc_path.write_bytes(b"%PDF-1.4 fake content")
    timeouts = {}

    def fake_post(url, data=None, files=None, timeout=None):
        timeouts[url.rsplit("/", 1)[-1]] = timeout
        return _FakeResponse({"ok": True, "result": {"message_id": 1}})

    monkeypatch.setattr(tg.requests, "post", fake_post)
    tg.send_message("TOKEN", "-100", "hi")
    tg.send_document("TOKEN", "-100", str(doc_path))

    assert timeouts["sendDocument"] > timeouts["sendMessage"]


def test_api_error_raises_runtime_error(monkeypatch):
    def fake_post(url, data=None, files=None, timeout=None):
        return _FakeResponse({"ok": False, "error_code": 400, "description": "Bad Request"})

    monkeypatch.setattr(tg.requests, "post", fake_post)
    with pytest.raises(RuntimeError):
        tg.send_message("TOKEN", "-100", "hello")


def test_transport_error_does_not_leak_token(monkeypatch):
    secret = "123456789:SUPER_SECRET_TOKEN_VALUE"

    def fake_post(url, data=None, files=None, timeout=None):
        raise tg.requests.ConnectTimeout(f"timed out calling {url}")

    monkeypatch.setattr(tg.requests, "post", fake_post)
    with pytest.raises(RuntimeError) as exc_info:
        tg.send_message(secret, "-100", "hello")

    assert secret not in str(exc_info.value)
    assert "sendMessage" in str(exc_info.value)

import json

import pytest

from neet_pipeline import run_monitor as rm
from neet_pipeline.monitor import link_watch as lw
from neet_pipeline.monitor import manifest as manifest_mod
from neet_pipeline.monitor.config import LinkWatchPage, MonitorConfig
from neet_pipeline.notifier import health as health_mod


def _page(key="kea_ugneet2026", name="KEA UG NEET 2026", url="https://kea.example/ugneet2026"):
    return LinkWatchPage(key=key, name=name, url=url)


def _cfg(*pages):
    return MonitorConfig(link_watch=list(pages))


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(rm, "STATE_PATH", str(tmp_path / "cache" / "monitor_state.json"))
    monkeypatch.setattr(health_mod, "HEALTH_STATE_PATH", str(tmp_path / "cache" / "health_state.json"))


def _mock_credentials_and_messages(monkeypatch):
    calls = []

    def fake_get_credentials(env_path, token_var="TELEGRAM_BOT_TOKEN", chat_id_var="TELEGRAM_CHAT_ID"):
        if token_var == "HEALTH_BOT_TOKEN":
            return "HEALTH_TOKEN", "-200"
        return "ALERT_TOKEN", "-100"

    def fake_send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
        calls.append({"token": token, "chat_id": chat_id, "text": text})
        return {"message_id": len(calls)}

    monkeypatch.setattr(rm.tg, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(rm.tg, "send_message", fake_send_message)
    return calls


def test_new_link_is_forwarded_once_and_manifest_persists(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    cfg = _cfg(_page())
    # page already baselined -> the first run below diffs normally instead
    # of silently recording every link (see auto-baseline in link_watch).
    lw.write_link_manifest("kea_ugneet2026", set())
    # same notice (id unchanged), only a cache-buster timestamp differs ->
    # must NOT re-alert on the second run.
    html_by_run = [
        '<a href="/notice.pdf?id=1&t=1700000000">Round 1 notice</a>',
        '<a href="/notice.pdf?id=1&t=1800000000">Round 1 notice</a>',
    ]
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: html_by_run.pop(0))

    first = rm.run_cycle(cfg, notify=True)
    second = rm.run_cycle(cfg, notify=True)

    alert_messages = [call for call in calls if call["token"] == "ALERT_TOKEN"]
    assert first.new_links_count == 1
    assert second.new_links_count == 0
    assert len(alert_messages) == 1
    assert "Round 1 notice" in alert_messages[0]["text"]
    assert "https://kea.example/notice.pdf?id=1&t=1700000000" in alert_messages[0]["text"]

    manifest_path = lw.link_manifest_path("kea_ugneet2026")
    with open(manifest_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved == [{"normalized_url": "https://kea.example/notice.pdf?id=1", "text": "Round 1 notice"}]


def test_health_success_posts_counts(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    cfg = _cfg(_page())
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)
    lw.write_link_manifest("kea_ugneet2026", set())  # already baselined
    monkeypatch.setattr(
        lw,
        "fetch_rendered_html",
        lambda url: '<a href="/one.pdf?id=1">One</a><a href="/two.html?round=2">Two</a>',
    )

    code = rm._execute_monitor_run("unused.yaml", notify=False, health_enabled=True)

    assert code == 0
    health_messages = [call["text"] for call in calls if call["token"] == "HEALTH_TOKEN"]
    assert len(health_messages) == 1
    assert "Run #1 OK" in health_messages[0]
    assert "pages checked: 1" in health_messages[0]
    assert "new links: 2" in health_messages[0]


def test_thrown_error_still_posts_failure_health(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    monkeypatch.setattr(rm, "load_config", lambda path: _cfg())

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(rm, "run_cycle", boom)

    code = rm._execute_monitor_run("unused.yaml", notify=False, health_enabled=True)

    assert code == 1
    health_messages = [call["text"] for call in calls if call["token"] == "HEALTH_TOKEN"]
    assert len(health_messages) == 1
    assert "Run #1 FAILED" in health_messages[0]
    assert "RuntimeError: simulated crash" in health_messages[0]


def test_missing_alerts_config_for_needed_post_reports_failed_health(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = []
    cfg = _cfg(_page())
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)
    lw.write_link_manifest("kea_ugneet2026", set())  # already baselined
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: '<a href="/new.pdf?id=1">New notice</a>')

    def fake_get_credentials(env_path, token_var="TELEGRAM_BOT_TOKEN", chat_id_var="TELEGRAM_CHAT_ID"):
        if token_var == "HEALTH_BOT_TOKEN":
            return "HEALTH_TOKEN", "-200"
        raise rm.tg.TelegramConfigError("TELEGRAM_BOT_TOKEN is not set")

    def fake_send_message(token, chat_id, text, reply_markup=None, parse_mode=None):
        calls.append({"token": token, "chat_id": chat_id, "text": text})
        return {"message_id": len(calls)}

    monkeypatch.setattr(rm.tg, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(rm.tg, "send_message", fake_send_message)

    code = rm._execute_monitor_run("unused.yaml", notify=True, health_enabled=True)

    assert code == 1
    health_messages = [call["text"] for call in calls if call["token"] == "HEALTH_TOKEN"]
    assert len(health_messages) == 1
    assert "Run #1 FAILED" in health_messages[0]
    assert "TELEGRAM_BOT_TOKEN is not set" in health_messages[0]


def test_one_of_two_link_pages_down_is_success_with_warning(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    ok_page = _page(key="ok", name="KEA OK", url="https://kea.example/ok")
    down_page = _page(key="down", name="KEA Down", url="https://kea.example/down")
    cfg = _cfg(ok_page, down_page)
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)

    def fake_fetch(url):
        if url.endswith("/down"):
            raise RuntimeError("blocked")
        return '<a href="/ok.pdf">OK</a>'

    monkeypatch.setattr(lw, "fetch_rendered_html", fake_fetch)

    code = rm._execute_monitor_run("unused.yaml", notify=False, health_enabled=True)

    assert code == 0
    health_messages = [call["text"] for call in calls if call["token"] == "HEALTH_TOKEN"]
    assert len(health_messages) == 1
    assert "Run #1 OK" in health_messages[0]
    assert "WARNING: link-watch page failed: KEA Down: RuntimeError: blocked" in health_messages[0]


def test_all_link_pages_down_is_failed_health(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    cfg = _cfg(
        _page(key="ugneet", name="KEA UG NEET", url="https://kea.example/ugneet"),
        _page(key="ugcet", name="KEA UGCET", url="https://kea.example/ugcet"),
    )
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: (_ for _ in ()).throw(RuntimeError("blocked")))

    code = rm._execute_monitor_run("unused.yaml", notify=False, health_enabled=True)

    assert code == 1
    health_messages = [call["text"] for call in calls if call["token"] == "HEALTH_TOKEN"]
    assert len(health_messages) == 1
    assert "Run #1 FAILED" in health_messages[0]
    assert "all configured link-watch page(s) failed" in health_messages[0]


def test_new_links_are_appended_to_that_pages_recent_links_log(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)  # also points recent_links at the temp cache dir
    _mock_credentials_and_messages(monkeypatch)
    cfg = _cfg(_page())
    lw.write_link_manifest("kea_ugneet2026", set())  # already baselined
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: '<a href="/r2-medical.pdf?id=7">Round 2 Medical Allotment</a>')

    rm.run_cycle(cfg, notify=True)

    entries = rm.recent_links.read_recent("kea_ugneet2026")
    assert len(entries) == 1
    assert "Round 2 Medical Allotment" in entries[0]
    assert rm.recent_links.recent_links_path("kea_ugneet2026").endswith("recent_links_kea_ugneet2026.log")


def test_newly_added_page_baselines_without_alert(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    cfg = _cfg(_page())
    monkeypatch.setattr(
        lw, "fetch_rendered_html",
        lambda url: '<a href="/a.pdf?id=1">A</a><a href="/b.pdf?id=2">B</a>',
    )

    summary = rm.run_cycle(cfg, notify=True)

    assert summary.new_links_count == 0
    alert_messages = [c for c in calls if c["token"] == "ALERT_TOKEN"]
    assert alert_messages == []
    assert lw.link_manifest_exists("kea_ugneet2026")

    # next cycle: a genuinely new link now alerts
    monkeypatch.setattr(
        lw, "fetch_rendered_html",
        lambda url: '<a href="/a.pdf?id=1">A</a><a href="/b.pdf?id=2">B</a><a href="/c.pdf?id=3">C</a>',
    )
    summary2 = rm.run_cycle(cfg, notify=True)
    assert summary2.new_links_count == 1
    assert [c for c in calls if c["token"] == "ALERT_TOKEN"]


def test_link_alert_send_failure_defers_all_persistence(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    p1 = _page(key="p1", name="P1", url="https://kea.example/p1")
    p2 = _page(key="p2", name="P2", url="https://kea.example/p2")
    cfg = _cfg(p1, p2)
    lw.write_link_manifest("p1", set())
    lw.write_link_manifest("p2", set())
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: '<a href="/new.pdf?id=9">Fresh notice</a>')

    def failing_send(token, chat_id, text, reply_markup=None, parse_mode=None):
        raise RuntimeError("Telegram API request failed on sendMessage")

    monkeypatch.setattr(rm.tg, "send_message", failing_send)

    with pytest.raises(RuntimeError):
        rm.run_cycle(cfg, notify=True)

    # neither page's manifest gained the new link -> next run retries
    assert lw.read_link_manifest("p1") == set()
    assert lw.read_link_manifest("p2") == set()


def test_run_status_goes_only_to_health_chat_never_to_alerts_chat(tmp_path, monkeypatch):
    """The per-run ✅/❌ heartbeat is health-chat only. The main alerts chat
    must never receive a run-status line (only real alerts land there)."""
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    cfg = _cfg()
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)

    assert rm._execute_monitor_run("unused.yaml", notify=True, health_enabled=True) == 0

    assert [c for c in calls if c["chat_id"] == "-100"] == []  # alerts chat: silent
    health = [c for c in calls if c["chat_id"] == "-200"]
    assert len(health) == 1 and "Run #1 OK" in health[0]["text"]


def test_crash_run_status_goes_only_to_health_chat(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    monkeypatch.setattr(rm, "load_config", lambda path: _cfg())
    monkeypatch.setattr(rm, "run_cycle", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    assert rm._execute_monitor_run("unused.yaml", notify=True, health_enabled=True) == 1

    assert [c for c in calls if c["chat_id"] == "-100"] == []
    health = [c for c in calls if c["chat_id"] == "-200"]
    assert len(health) == 1 and "FAILED" in health[0]["text"]


def test_run_counter_increments_and_persists(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    calls = _mock_credentials_and_messages(monkeypatch)
    monkeypatch.setattr(rm, "load_config", lambda path: _cfg())

    assert rm._execute_monitor_run("unused.yaml", notify=False, health_enabled=True) == 0
    assert rm._execute_monitor_run("unused.yaml", notify=False, health_enabled=True) == 0

    health_messages = [call["text"] for call in calls if call["token"] == "HEALTH_TOKEN"]
    assert "Run #1 OK" in health_messages[0]
    assert "Run #2 OK" in health_messages[1]
    with open(health_mod.HEALTH_STATE_PATH, "r", encoding="utf-8") as f:
        assert json.load(f)["run"] == 2

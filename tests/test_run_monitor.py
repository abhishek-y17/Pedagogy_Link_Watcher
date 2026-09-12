import os

from neet_pipeline import run_monitor as rm
from neet_pipeline.monitor import link_watch as lw
from neet_pipeline.monitor import manifest as manifest_mod
from neet_pipeline.monitor.config import LinkWatchPage, MonitorConfig


def _page(key="kea_ugneet2026", name="KEA UG NEET 2026", url="https://kea.example/ugneet2026"):
    return LinkWatchPage(key=key, name=name, url=url)


def _cfg(*pages):
    return MonitorConfig(link_watch=list(pages) or [_page()])


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(rm, "STATE_PATH", str(tmp_path / "cache" / "monitor_state.json"))


def test_cycle_counter_increments_each_scan(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg()
    lw.write_link_manifest("kea_ugneet2026", set())
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: "<html></html>")

    rm.run_cycle(cfg, notify=False)
    rm.run_cycle(cfg, notify=False)

    state = rm.load_json(str(tmp_path / "cache" / "monitor_state.json"), {})
    assert state["cycle"] == 2


def test_get_last_scan_status_records_timestamp(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg()
    lw.write_link_manifest("kea_ugneet2026", set())
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: "<html></html>")

    rm.run_cycle(cfg, notify=False)

    status = rm.get_last_scan_status(str(tmp_path / "cache" / "monitor_state.json"))
    assert status["cycle"] == 1
    assert status["last_scan_at"] is not None
    assert status["unreachable_pages"] == []


def test_get_last_scan_status_tracks_unreachable_pages(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(_page(name="Karnataka - KEA"))
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: (_ for _ in ()).throw(RuntimeError("blocked")))

    rm.run_cycle(cfg, notify=False)

    status = rm.get_last_scan_status(str(tmp_path / "cache" / "monitor_state.json"))
    assert status["unreachable_pages"] == ["Karnataka - KEA"]


def test_get_last_scan_status_before_any_scan(tmp_path):
    status = rm.get_last_scan_status(str(tmp_path / "nope.json"))
    assert status["cycle"] == 0
    assert status["last_scan_at"] is None


# --- --once exit code ---

def test_main_once_returns_0_on_clean_scan(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg()
    lw.write_link_manifest("kea_ugneet2026", set())
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)
    monkeypatch.setattr(lw, "fetch_rendered_html", lambda url: "<html></html>")

    assert rm.main(["--once", "--no-notify", "--no-health"]) == 0


def test_main_baseline_seeds_manifest_without_alerting(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg()
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: '<a href="/notice.pdf?id=1">Historical notice</a>')

    def _boom(*args, **kwargs):
        raise AssertionError("baseline must not post any alert")

    monkeypatch.setattr(rm.tg, "get_credentials", _boom)

    assert rm.main(["--baseline"]) == 0
    assert lw.link_manifest_exists("kea_ugneet2026")
    manifest = lw.read_link_manifest("kea_ugneet2026")
    assert {(i.normalized_url, i.text) for i in manifest} == {
        ("https://kea.example/notice.pdf?id=1", "Historical notice")
    }


def test_main_once_returns_1_when_all_pages_unreachable(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg()
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)
    monkeypatch.setattr(lw, "fetch_rendered_html",
                        lambda url: (_ for _ in ()).throw(RuntimeError("blocked")))

    assert rm.main(["--once", "--no-notify", "--no-health"]) == 1


def test_main_once_returns_0_when_some_but_not_all_pages_unreachable(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    cfg = _cfg(
        _page(key="ugneet", name="KEA UG NEET", url="https://kea.example/ugneet"),
        _page(key="ugcet", name="KEA UGCET", url="https://kea.example/ugcet"),
    )
    lw.write_link_manifest("ugneet", set())
    lw.write_link_manifest("ugcet", set())
    monkeypatch.setattr(rm, "load_config", lambda path: cfg)

    def _fetch(url):
        if "ugneet" in url:
            raise RuntimeError("blocked")
        return "<html></html>"

    monkeypatch.setattr(lw, "fetch_rendered_html", _fetch)

    assert rm.main(["--once", "--no-notify", "--no-health"]) == 0


def test_main_once_returns_1_on_unhandled_exception(tmp_path, monkeypatch):
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setattr(rm, "load_config", lambda path: _cfg())

    def _boom(*args, **kwargs):
        raise RuntimeError("simulated crash mid-scan")

    monkeypatch.setattr(rm, "run_cycle", _boom)

    assert rm.main(["--once", "--no-notify", "--no-health"]) == 1

from neet_pipeline.monitor.config import load_config


def test_load_real_link_watch_pages_txt():
    # relies on tests being run from the repo root (config/link_watch_pages.txt).
    cfg = load_config()
    assert len(cfg.link_watch) >= 2
    watch_urls = {p.url for p in cfg.link_watch}
    assert "https://cetonline.karnataka.gov.in/kea/ugneet2026" in watch_urls
    assert "https://cetonline.karnataka.gov.in/kea/ugcet2026" in watch_urls
    assert {"kea_ugneet2026", "kea_ugcet2026"} <= {p.key for p in cfg.link_watch}


def test_load_missing_file_returns_empty_link_watch(tmp_path):
    cfg = load_config(str(tmp_path / "nope.txt"))
    assert cfg.link_watch == []


def test_load_config_from_custom_txt(tmp_path):
    p = tmp_path / "pages.txt"
    p.write_text(
        "# watched pages\n"
        "https://cetonline.karnataka.gov.in/kea/ugneet2026\n"
        "https://kea.example.gov.in/notices\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    assert [pg.url for pg in cfg.link_watch] == [
        "https://cetonline.karnataka.gov.in/kea/ugneet2026",
        "https://kea.example.gov.in/notices",
    ]
    assert [pg.key for pg in cfg.link_watch] == ["kea_ugneet2026", "notices"]


def test_empty_txt_has_empty_link_watch(tmp_path):
    p = tmp_path / "pages.txt"
    p.write_text("", encoding="utf-8")
    cfg = load_config(str(p))
    assert cfg.link_watch == []


def test_duplicate_derived_keys_are_disambiguated(tmp_path):
    p = tmp_path / "pages.txt"
    p.write_text(
        "https://a.example.gov.in/notices\n"
        "https://b.example.gov.in/notices\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    keys = [pg.key for pg in cfg.link_watch]
    assert keys[0] == "notices"
    assert keys[1] != "notices"
    assert len(set(keys)) == 2

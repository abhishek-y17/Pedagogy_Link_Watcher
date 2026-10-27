from neet_pipeline.monitor.config import load_config


def test_load_real_link_watch_pages_txt():
    # relies on tests being run from the repo root (config/link_watch_pages.txt).
    cfg = load_config()
    watch_urls = {p.url for p in cfg.link_watch}
    expected = {
        # KEA PGET-2026 (PG-NEET) Medical/DNB + Dental, and UGNEET-2026
        "https://cetonline.karnataka.gov.in/kea/pgetmed2026",
        "https://cetonline.karnataka.gov.in/kea/pgden2026",
        "https://cetonline.karnataka.gov.in/kea/ugneet2026",
        # MCC PG, MDS (PG Dental) and UG full-list pages
        "https://mcc.nic.in/current-events-pg/",
        "https://mcc.nic.in/eservices-schedule-pg/",
        "https://mcc.nic.in/current-events-mds/",
        "https://mcc.nic.in/eservices-schedule-mds/",
        "https://mcc.nic.in/current-events-ug/",
        "https://mcc.nic.in/eservices-schedule-ug/",
    }
    assert watch_urls == expected
    # kea/pgneet2026 is a 404 on KEA (confirmed live 2026-10-27) -- the
    # PG-Medical page is kea/pgetmed2026. CET pages are paused (commented out).
    assert "https://cetonline.karnataka.gov.in/kea/pgneet2026" not in watch_urls
    assert {"kea_pgetmed2026", "kea_pgden2026", "kea_ugneet2026",
            "current_events_mds", "eservices_schedule_mds"} <= {p.key for p in cfg.link_watch}
    # every page must be scoped to its own content, not the shared
    # sidebar/nav/footer -- see CLAUDE.md.
    for p in cfg.link_watch:
        if "cetonline.karnataka.gov.in" in p.url:
            assert p.content_selector == ".card-deck", p.url
        else:
            assert p.content_selector == "main", p.url


def test_content_selector_wired_per_host(tmp_path):
    p = tmp_path / "pages.txt"
    p.write_text(
        "https://cetonline.karnataka.gov.in/kea/ugneet2026\n"
        "https://mcc.nic.in/current-events-pg/\n"
        "https://kea.example.gov.in/notices\n",
        encoding="utf-8",
    )
    cfg = load_config(str(p))
    by_url = {pg.url: pg for pg in cfg.link_watch}
    assert by_url["https://cetonline.karnataka.gov.in/kea/ugneet2026"].content_selector == ".card-deck"
    assert by_url["https://mcc.nic.in/current-events-pg/"].content_selector == "main"
    # a host with no confirmed selector isn't scoped -- falling back to the
    # old whole-page behavior rather than guessing.
    assert by_url["https://kea.example.gov.in/notices"].content_selector is None


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

import os

import pytest

from neet_pipeline.monitor import manifest as manifest_mod
from neet_pipeline.monitor import recent_links as rl
from neet_pipeline.monitor.link_watch import PageLink


@pytest.fixture(autouse=True)
def _cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))


def _link(text, url):
    return PageLink(url=url, normalized_url=url, text=text)


def test_missing_file_reads_empty():
    assert rl.read_recent("kea_ugneet2026") == []


def test_path_is_named_after_the_page(tmp_path):
    assert rl.recent_links_path("kea_ugneet2026") == str(tmp_path / "recent_links_kea_ugneet2026.log")
    assert rl.recent_links_path("kea_ugcet2026") == str(tmp_path / "recent_links_kea_ugcet2026.log")


def test_two_pages_write_separate_files():
    rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026", [_link("neet notice", "https://k/n.pdf")])
    rl.record_new_links("kea_ugcet2026", "KEA UGCET 2026", [_link("cet notice", "https://k/c.pdf")])

    neet = rl.read_recent("kea_ugneet2026")
    cet = rl.read_recent("kea_ugcet2026")
    assert len(neet) == 1 and "neet notice" in neet[0]
    assert len(cet) == 1 and "cet notice" in cet[0]
    assert "cet notice" not in "\n".join(neet)


def test_record_prepends_newest_on_top_and_caps_at_max():
    for i in range(rl.MAX_RECENT + 8):
        rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026",
                            [_link(f"notice {i}", f"https://k/{i}.pdf")],
                            detected_at=f"2026-09-08 10:{i:02d}:00")
    entries = rl.read_recent("kea_ugneet2026")
    assert len(entries) == rl.MAX_RECENT
    assert "notice 27" in entries[0]
    assert "notice 26" in entries[1]
    assert not any(e.endswith("/0.pdf") for e in entries)


def test_batch_keeps_given_order_on_top():
    rl.record_new_links("kea_ugcet2026", "KEA UGCET 2026", [_link("old", "https://k/old.pdf")],
                        detected_at="2026-09-01 09:00:00")
    rl.record_new_links("kea_ugcet2026", "KEA UGCET 2026",
                        [_link("first", "https://k/a.pdf"), _link("second", "https://k/b.pdf")],
                        detected_at="2026-09-08 09:00:00")
    entries = rl.read_recent("kea_ugcet2026")
    assert "first" in entries[0]
    assert "second" in entries[1]
    assert "old" in entries[2]


def test_header_names_the_page_and_is_not_counted():
    rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026", [_link("x", "https://k/x.pdf")])
    raw = open(rl.recent_links_path("kea_ugneet2026"), encoding="utf-8").read()
    assert raw.startswith("# KEA UG NEET 2026 —")
    assert len(rl.read_recent("kea_ugneet2026")) == 1


def test_empty_links_is_noop():
    assert rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026", []) == 0
    assert not os.path.exists(rl.recent_links_path("kea_ugneet2026"))


def test_seed_writes_newest_first():
    n = rl.seed("kea_ugcet2026", "KEA UGCET 2026", [
        ("2026-09-08 00:00:00", "newest", "https://k/n.pdf"),
        ("2026-09-01 00:00:00", "older", "https://k/o.pdf"),
    ])
    assert n == 2
    entries = rl.read_recent("kea_ugcet2026")
    assert "newest" in entries[0] and "older" in entries[1]


def test_re_recording_same_url_moves_it_to_top_no_duplicate():
    rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026",
                        [_link("Round 2 seat matrix", "https://k/r2.pdf")],
                        detected_at="2026-09-07 08:00:00")
    rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026",
                        [_link("other", "https://k/other.pdf")],
                        detected_at="2026-09-07 09:00:00")
    rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026",
                        [_link("Round 2 seat matrix", "https://k/r2.pdf")],
                        detected_at="2026-09-08 10:00:00")

    entries = rl.read_recent("kea_ugneet2026")
    assert sum(1 for e in entries if "https://k/r2.pdf" in e) == 1
    assert "2026-09-08 10:00:00" in entries[0] and "https://k/r2.pdf" in entries[0]


def test_tuple_items_accepted():
    rl.record_new_links("kea_ugneet2026", "KEA UG NEET 2026", [("hello", "https://k/h.pdf")],
                        detected_at="2026-09-08 09:00:00")
    top = rl.read_recent("kea_ugneet2026")[0]
    assert "hello" in top and "https://k/h.pdf" in top

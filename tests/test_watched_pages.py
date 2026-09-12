from neet_pipeline.monitor import watched_pages as wp


def test_missing_file_returns_empty(tmp_path):
    assert wp.load_pages(str(tmp_path / "nope.txt")) == []


def test_comments_blank_lines_and_inline_comments_are_stripped(tmp_path):
    p = tmp_path / "pages.txt"
    p.write_text(
        "# a heading comment\n"
        "\n"
        "   \n"
        "https://a.gov.in/one   # inline comment\n"
        "https://b.gov.in/two\n",
        encoding="utf-8",
    )
    assert wp.load_pages(str(p)) == ["https://a.gov.in/one", "https://b.gov.in/two"]


def test_trailing_slash_and_case_dedupe_preserving_order(tmp_path):
    p = tmp_path / "pages.txt"
    p.write_text(
        "https://Example.gov.in/kea/\n"
        "https://example.gov.in/kea\n"
        "https://example.gov.in/other\n",
        encoding="utf-8",
    )
    assert wp.load_pages(str(p)) == [
        "https://Example.gov.in/kea/",
        "https://example.gov.in/other",
    ]


def test_invalid_lines_skipped_with_warning(tmp_path, capsys):
    p = tmp_path / "pages.txt"
    p.write_text(
        "ftp://x.gov.in/f\n"
        "not a url at all\n"
        "https://ok.gov.in/page\n",
        encoding="utf-8",
    )
    assert wp.load_pages(str(p)) == ["https://ok.gov.in/page"]
    err = capsys.readouterr().out
    assert "ftp://x.gov.in/f" in err
    assert "not a url at all" in err


def test_is_valid_page_url():
    assert wp.is_valid_page_url("https://x.gov.in/a")
    assert wp.is_valid_page_url("http://x.gov.in")
    assert not wp.is_valid_page_url("ftp://x.gov.in/a")
    assert not wp.is_valid_page_url("https://")
    assert not wp.is_valid_page_url("")


def test_derive_key():
    assert wp.derive_key("https://cetonline.karnataka.gov.in/kea/ugneet2026") == "kea_ugneet2026"
    assert wp.derive_key("https://cetonline.karnataka.gov.in/kea/ugneet2026/") == "kea_ugneet2026"
    # root URL -> host slug
    assert wp.derive_key("https://kea.example.com/") == "kea_example_com"
    # deterministic
    u = "https://x.gov.in/a/b-c"
    assert wp.derive_key(u) == wp.derive_key(u) == "a_b_c"


def test_derive_name_is_the_url():
    u = "https://x.gov.in/a"
    assert wp.derive_name(u) == u

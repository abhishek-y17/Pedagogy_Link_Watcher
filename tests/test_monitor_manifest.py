import os
import json

from neet_pipeline.monitor import manifest as manifest_mod
from neet_pipeline.monitor.manifest import read_manifest, write_manifest


def test_read_missing_manifest_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    assert read_manifest("nosuchsite") == []


def test_write_then_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    write_manifest("kea", ["https://x/b.pdf", "https://x/a.pdf", "https://x/a.pdf"])
    result = read_manifest("kea")
    # sorted and deduped
    assert result == ["https://x/a.pdf", "https://x/b.pdf"]


def test_corrupt_manifest_file_returns_empty_list(tmp_path, monkeypatch):
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(tmp_path))
    path = manifest_mod.manifest_path("broken")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("{not valid json")
    assert read_manifest("broken") == []


def test_write_manifest_creates_cache_dir(tmp_path, monkeypatch):
    target = tmp_path / "nested" / "cache"
    monkeypatch.setattr(manifest_mod, "CACHE_DIR", str(target))
    write_manifest("mcc", ["https://x/a.pdf"])
    assert os.path.exists(manifest_mod.manifest_path("mcc"))

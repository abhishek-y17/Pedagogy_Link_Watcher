"""
Per-site JSON manifest of known PDF URLs — the diff baseline.

data/cache/<key>.pdfs.json holds the flat sorted list of every PDF URL seen
on that site so far. Each poll compares the freshly extracted URL set
against this manifest; anything not in it is new.
"""

from __future__ import annotations
import os

from ..state import load_json, save_json_atomic

CACHE_DIR = os.path.join("data", "cache")


def manifest_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.pdfs.json")


def read_manifest(key: str) -> list[str]:
    p = manifest_path(key)
    data = load_json(p, [])
    return data if isinstance(data, list) else []


def write_manifest(key: str, urls: list[str]) -> None:
    save_json_atomic(manifest_path(key), sorted(set(urls)))

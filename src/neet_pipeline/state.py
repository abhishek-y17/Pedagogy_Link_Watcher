"""Small, crash-safe helpers for JSON-backed runtime state.

The monitor and Telegram bot keep lightweight local state in ``data/cache``.
Writing through a temporary file and ``os.replace`` prevents a killed process
from leaving a half-written JSON document behind.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from typing import Any


def load_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return copy.deepcopy(default)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return copy.deepcopy(default)


def save_json_atomic(path: str, data: Any) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".json-", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise

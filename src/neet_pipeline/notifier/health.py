"""
Health / heartbeat reporting for monitor runs.

If the Python process itself is killed before this code runs, it cannot
self-report. A dead-man's-switch that alerts on missing heartbeats is a
separate production task documented in HOSTING.md.
"""

from __future__ import annotations

import os

from . import telegram_api as tg
from ..state import load_json, save_json_atomic


HEALTH_STATE_PATH = os.path.join("data", "cache", "health_state.json")
HEALTH_TOKEN_VAR = "HEALTH_BOT_TOKEN"
HEALTH_CHAT_ID_VAR = "HEALTH_CHAT_ID"


def _load(path: str | None = None) -> dict:
    path = path or HEALTH_STATE_PATH
    data = load_json(path, {"run": 0})
    return data if isinstance(data, dict) else {"run": 0}


def _save(data: dict, path: str | None = None) -> None:
    path = path or HEALTH_STATE_PATH
    save_json_atomic(path, data)


def next_run_number(path: str | None = None) -> int:
    state = _load(path)
    state["run"] = int(state.get("run", 0)) + 1
    _save(state, path)
    return state["run"]


def format_success(run_number: int, timestamp: str, pages_checked: int,
                   new_links: int, duration_seconds: float,
                   warnings: list[str] | None = None) -> str:
    duration = int(round(duration_seconds))
    text = (
        f"✅ Run #{run_number} OK — {timestamp} — pages checked: {pages_checked}, "
        f"new links: {new_links}, duration: {duration}s"
    )
    if warnings:
        text += "\nWARNING: " + "\nWARNING: ".join(warnings)
    return text


def format_failure(run_number: int, timestamp: str, failure: str) -> str:
    return f"❌ Run #{run_number} FAILED — {timestamp} — {failure}"


def format_skipped(run_number: int, timestamp: str, until: str) -> str:
    return (
        f"⏸ Run #{run_number} SKIPPED — {timestamp} — "
        f"backing off until {until} after a 429/503 from KEA"
    )


def post_health(text: str, env_path: str = tg.DEFAULT_ENV_PATH) -> dict:
    token, chat_id = tg.get_credentials(
        env_path,
        token_var=HEALTH_TOKEN_VAR,
        chat_id_var=HEALTH_CHAT_ID_VAR,
    )
    return tg.send_message(token, chat_id, text)

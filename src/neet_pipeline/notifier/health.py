"""
Health / heartbeat reporting for monitor runs.

Heartbeats are batched: each run's outcome is buffered via `record_run`
rather than posted immediately, and only once `BATCH_SIZE` runs have piled
up does `pop_batch` hand back the batch for `format_batch_summary` to
render as a single Telegram message (one post per ~BATCH_SIZE runs instead
of one per run). This exists because the scan cadence (~1 min) made a
per-run heartbeat noisy; batching trades a little detection latency for a
much quieter health chat. The scan cadence itself (run_monitor.py's
LOOP_SLEEP_MIN/MAX) is unaffected -- only how often a heartbeat is posted.

If the Python process itself is killed before this code runs, it cannot
self-report. A dead-man's-switch that alerts on missing heartbeats is a
separate production task documented in HOSTING.md.
"""

from __future__ import annotations

import os
from collections import Counter

from . import telegram_api as tg
from ..state import load_json, save_json_atomic


HEALTH_STATE_PATH = os.path.join("data", "cache", "health_state.json")
HEALTH_TOKEN_VAR = "HEALTH_BOT_TOKEN"
HEALTH_CHAT_ID_VAR = "HEALTH_CHAT_ID"

# Runs are buffered and posted as one summary message every this many runs
# (~10 runs at the ~1 min cadence is roughly a 10-minute heartbeat).
BATCH_SIZE = 10


def _load(path: str | None = None) -> dict:
    path = path or HEALTH_STATE_PATH
    data = load_json(path, {"run": 0, "pending": []})
    return data if isinstance(data, dict) else {"run": 0, "pending": []}


def _save(data: dict, path: str | None = None) -> None:
    path = path or HEALTH_STATE_PATH
    save_json_atomic(path, data)


def next_run_number(path: str | None = None) -> int:
    state = _load(path)
    state["run"] = int(state.get("run", 0)) + 1
    _save(state, path)
    return state["run"]


def record_run(record: dict, path: str | None = None) -> list[dict]:
    """Buffer one run's outcome. Does not post anything -- see `pop_batch`."""
    state = _load(path)
    pending = state.get("pending", [])
    pending.append(record)
    state["pending"] = pending
    _save(state, path)
    return pending


def pop_batch(path: str | None = None) -> list[dict] | None:
    """
    Once `BATCH_SIZE` runs have accumulated, clears the buffer and returns
    them for the caller to post as one summary; otherwise leaves the
    buffer alone and returns None. `BATCH_SIZE` is read from this module's
    globals at call time (not bound as a default arg), so tests can
    `monkeypatch.setattr(health_mod, "BATCH_SIZE", ...)` to shrink it.
    """
    state = _load(path)
    pending = state.get("pending", [])
    if len(pending) < BATCH_SIZE:
        return None
    state["pending"] = []
    _save(state, path)
    return pending


def format_failure(run_number: int, timestamp: str, failure: str) -> str:
    """
    A failed run is reported immediately rather than buffered into the
    next batch -- see run_monitor.py::_record_health_outcome. Waiting up
    to BATCH_SIZE runs to report a real problem would delay noticing it
    by up to ~BATCH_SIZE scan cycles, which defeats the point of a health
    heartbeat.
    """
    return f"❌ Run #{run_number} FAILED — {timestamp} — {failure}"


def format_batch_summary(records: list[dict]) -> str:
    """
    One line per distinct failure/skip/warning message (with an "(xN)"
    count if it repeated), rather than one line per run -- a page that's
    been down for the whole batch shouldn't produce 10 near-identical
    lines.
    """
    ok = sum(1 for r in records if r["status"] == "ok")
    failed = [r for r in records if r["status"] == "failed"]
    skipped = [r for r in records if r["status"] == "skipped"]
    total_new_links = sum(r.get("new_links", 0) for r in records if r["status"] == "ok")

    first, last = records[0], records[-1]
    icon = "✅" if not failed else "❌"
    if first["run_number"] == last["run_number"]:
        header = f"{icon} Run #{first['run_number']} ({first['timestamp']})"
    else:
        header = (f"{icon} Runs #{first['run_number']}-#{last['run_number']} "
                   f"({first['timestamp']} → {last['timestamp']})")

    lines = [
        header,
        f"OK: {ok}/{len(records)}  FAILED: {len(failed)}  SKIPPED: {len(skipped)}  "
        f"new links: {total_new_links}",
    ]

    for text, n in Counter(r.get("failure", "?") for r in failed).items():
        lines.append(f"  FAILED: {text}" + (f" (x{n})" if n > 1 else ""))
    for until, n in Counter(r.get("until", "?") for r in skipped).items():
        lines.append(f"  SKIPPED: backing off until {until}" + (f" (x{n})" if n > 1 else ""))
    for text, n in Counter(w for r in records for w in (r.get("warnings") or [])).items():
        lines.append(f"  WARNING: {text}" + (f" (x{n})" if n > 1 else ""))

    return "\n".join(lines)


def post_health(text: str, env_path: str = tg.DEFAULT_ENV_PATH) -> dict:
    token, chat_id = tg.get_credentials(
        env_path,
        token_var=HEALTH_TOKEN_VAR,
        chat_id_var=HEALTH_CHAT_ID_VAR,
    )
    return tg.send_message(token, chat_id, text)

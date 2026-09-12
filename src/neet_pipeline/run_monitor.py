"""
KEA link-watch monitor (see CLAUDE.md).

Usage:
    PYTHONPATH=src python -m neet_pipeline.run_monitor --once
    PYTHONPATH=src python -m neet_pipeline.run_monitor --loop [--interval 60]
    PYTHONPATH=src python -m neet_pipeline.run_monitor --baseline

Watches the pages listed in config/link_watch_pages.txt for newly-added
links and posts them to the Telegram alerts chat. A never-before-seen page
is silently baselined on its first scan (every current link recorded,
nothing alerted) -- only links added after that first scan trigger an alert.

--once does a single scan (for cron/Task Scheduler); --loop repeats every
--interval seconds (default 60 = 1 min) until killed; --baseline records
the current link state without alerting, for a fresh deployment or a
deliberate reset.
"""

from __future__ import annotations
import argparse
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime

from .monitor.config import load_config, DEFAULT_LOOP_INTERVAL
from .monitor.watched_pages import DEFAULT_LINK_WATCH_PAGES_TXT
from .monitor.link_watch import LinkWatchResult, check_link_page, persist_link_result
from .monitor import recent_links
from .notifier import telegram_api as tg
from .notifier import health as health_mod
from .notifier.link_alerts import post_link_alerts
from .state import load_json, save_json_atomic

STATE_PATH = os.path.join("data", "cache", "monitor_state.json")

# Safer-polling protections (KEA geo-blocks non-Indian IPs, so this office
# connection is the only way to reach it -- getting it rate-limited/blocked
# takes the whole tool down):
BACKOFF_SECONDS = 300   # after a 429/503, stop scanning entirely for 5 min
JITTER_SECONDS = 30     # +/- randomness on every poll so cadence isn't exact


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


@dataclass
class MonitorRunSummary:
    link_results: list[LinkWatchResult] = field(default_factory=list)
    link_alert_messages: int = 0

    @property
    def pages_checked(self) -> int:
        return sum(1 for result in self.link_results if result.ok)

    @property
    def new_links_count(self) -> int:
        return sum(len(result.new_links) for result in self.link_results if result.ok)


def _next_cycle() -> int:
    state = load_json(STATE_PATH, {"cycle": 0})
    state["cycle"] = state.get("cycle", 0) + 1
    save_json_atomic(STATE_PATH, state)
    return state["cycle"]


def _record_scan_result(unreachable_pages: list) -> None:
    state = load_json(STATE_PATH, {"cycle": 0})
    state["last_scan_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    state["unreachable_pages"] = unreachable_pages
    save_json_atomic(STATE_PATH, state)


def get_last_scan_status(state_path: str = None) -> dict:
    return load_json(state_path or STATE_PATH, {
        "cycle": 0, "last_scan_at": None, "unreachable_pages": [],
    })


def _record_backoff() -> float:
    """Persist a backoff deadline after a 429/503. Survives process
    restarts (Task Scheduler runs --once as a fresh process every cycle),
    so the deadline lives in STATE_PATH rather than in memory."""
    until = time.time() + BACKOFF_SECONDS
    state = load_json(STATE_PATH, {"cycle": 0})
    state["backoff_until"] = until
    save_json_atomic(STATE_PATH, state)
    return until


def _active_backoff() -> float | None:
    """Returns the backoff deadline (epoch seconds) if still in the future,
    else None. A past/absent deadline needs no explicit clearing -- it's
    simply ignored from here on."""
    until = load_json(STATE_PATH, {}).get("backoff_until")
    if isinstance(until, (int, float)) and until > time.time():
        return until
    return None


def _check_link_watch_pages(cfg) -> list[LinkWatchResult]:
    results = []
    for page in cfg.link_watch:
        log(f"[link-watch] Checking {page.name} -> {page.url}")
        result = check_link_page(page)
        if result.ok and result.baselined:
            log(f"[link-watch] {page.name} - baselined {len(result.links)} link(s) "
                f"(new page, no alerts this scan)")
        elif result.ok:
            log(f"[link-watch] {page.name} - {len(result.new_links)} new link(s), "
                f"{len(result.links)} total link(s)")
        else:
            log(f"[link-watch] {page.name} - FAILED: {result.error}")
        results.append(result)
    return results


def _post_link_alerts_and_persist(results: list[LinkWatchResult], notify: bool,
                                  env_path: str) -> int:
    new_links_count = sum(len(result.new_links) for result in results if result.ok)
    messages_sent = 0
    if new_links_count and notify:
        token, chat_id = tg.get_credentials(env_path)
        messages_sent = post_link_alerts(token, chat_id, results)
        log(f"[link-watch] Posted {new_links_count} new link(s) in {messages_sent} message(s).")
    elif new_links_count:
        log(f"[link-watch] {new_links_count} new link(s) found; --no-notify set, so no alerts posted.")

    # Persist only after any required alert post succeeds. If the Telegram
    # post fails, the identities are left unrecorded so the next run retries
    # instead of silently losing the change.
    for result in results:
        persist_link_result(result)
        if result.ok and result.new_links:
            recent_links.record_new_links(result.page.key, result.page.name, result.new_links)
    return messages_sent


def run_cycle(cfg, notify: bool = True, env_path: str = tg.DEFAULT_ENV_PATH) -> MonitorRunSummary:
    cycle = _next_cycle()
    log(f"=== scan cycle {cycle} ===")
    link_results = _check_link_watch_pages(cfg)
    _record_scan_result([r.page.name for r in link_results if not r.ok])
    if any(r.rate_limited for r in link_results):
        until = _record_backoff()
        until_ts = datetime.fromtimestamp(until).strftime("%Y-%m-%d %H:%M:%S")
        log(f"WARNING: rate-limited (429/503) -- backing off until {until_ts}")
    link_alert_messages = _post_link_alerts_and_persist(link_results, notify, env_path)
    return MonitorRunSummary(link_results=link_results, link_alert_messages=link_alert_messages)


def _summary_warnings(summary: MonitorRunSummary) -> list[str]:
    warnings = []
    for result in summary.link_results:
        if not result.ok:
            warnings.append(f"link-watch page failed: {result.page.name}: {result.error}")
    return warnings


def _summary_failure(summary: MonitorRunSummary) -> str | None:
    if summary.link_results and not any(result.ok for result in summary.link_results):
        details = "; ".join(f"{result.page.name}: {result.error}" for result in summary.link_results)
        return f"all configured link-watch page(s) failed: {details}"
    return None


def _post_health_message(text: str, env_path: str) -> bool:
    try:
        health_mod.post_health(text, env_path=env_path)
        return True
    except Exception as e:
        log(f"[health] ERROR: could not post heartbeat: {type(e).__name__}: {e}")
        return False


def _execute_monitor_run(config_path: str, notify: bool = True, health_enabled: bool = True,
                         env_path: str = tg.DEFAULT_ENV_PATH, jitter: bool = True) -> int:
    backoff_until = _active_backoff()
    if backoff_until is not None:
        run_number = health_mod.next_run_number() if health_enabled else None
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        until_ts = datetime.fromtimestamp(backoff_until).strftime("%Y-%m-%d %H:%M:%S")
        log(f"[link-watch] Backing off until {until_ts} after a 429/503 -- skipping this scan.")
        if health_enabled:
            _post_health_message(health_mod.format_skipped(run_number, timestamp, until_ts), env_path)
        return 0

    if jitter:
        # A small random pre-scan delay so requests don't land at the exact
        # top of every interval -- meaningful for --once/Task Scheduler,
        # which owns the fixed cadence itself and has no inter-cycle sleep
        # to jitter (that happens in main()'s --loop branch instead).
        time.sleep(random.uniform(0, JITTER_SECONDS))

    run_number = health_mod.next_run_number() if health_enabled else None
    started = time.monotonic()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        cfg = load_config(config_path)
        log(f"Loaded {len(cfg.link_watch)} link-watch page(s)")
        summary = run_cycle(cfg, notify=notify, env_path=env_path)
        duration = time.monotonic() - started
        failure = _summary_failure(summary)
        warnings = _summary_warnings(summary)

        if failure:
            log(f"ERROR: {failure}")
            if health_enabled:
                text = health_mod.format_failure(run_number, timestamp, failure)
                if not _post_health_message(text, env_path):
                    return 1
            return 1

        if warnings:
            for warning in warnings:
                log(f"WARNING: {warning}")

        if health_enabled:
            text = health_mod.format_success(
                run_number,
                timestamp,
                pages_checked=summary.pages_checked,
                new_links=summary.new_links_count,
                duration_seconds=duration,
                warnings=warnings,
            )
            if not _post_health_message(text, env_path):
                return 1
        return 0
    except Exception as e:
        failure = f"{type(e).__name__}: {e}"
        log(f"FATAL: scan cycle raised an unhandled exception: {failure}")
        if health_enabled:
            text = health_mod.format_failure(run_number, timestamp, failure)
            _post_health_message(text, env_path)
        return 1


def _execute_baseline(config_path: str) -> int:
    """Record the current link state without alerting.

    Use this once on a fresh deployment, or deliberately to reset the
    watch, so existing links are not treated as newly published.
    """
    try:
        cfg = load_config(config_path)
        link_results = _check_link_watch_pages(cfg)
        for result in link_results:
            persist_link_result(result)

        all_link_pages_failed = bool(link_results) and not any(result.ok for result in link_results)
        if all_link_pages_failed:
            log("ERROR: baseline could not reach any configured link-watch page")
            return 1
        log("Baseline saved. Future cycles will alert only on newly discovered links.")
        return 0
    except Exception as e:
        log(f"FATAL: baseline failed: {type(e).__name__}: {e}")
        return 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="neet_pipeline.run_monitor")
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true", help="single scan, then exit (cron/Task Scheduler)")
    mode.add_argument("--loop", action="store_true", help="repeat every --interval seconds until killed")
    mode.add_argument("--baseline", action="store_true",
                      help="seed current links without alerting")
    p.add_argument("--interval", type=int, default=DEFAULT_LOOP_INTERVAL,
                   help=f"seconds between loop cycles (default {DEFAULT_LOOP_INTERVAL})")
    p.add_argument("--pages", default=DEFAULT_LINK_WATCH_PAGES_TXT,
                   help="path to link_watch_pages.txt")
    p.add_argument("--no-notify", action="store_true",
                   help="scan and record links, skip posting to Telegram")
    p.add_argument("--no-health", action="store_true",
                   help="skip the health heartbeat post for this run")
    p.add_argument("--no-jitter", action="store_true",
                   help="poll at the exact interval with no random delay (mainly for tests)")
    args = p.parse_args(argv)

    if args.baseline:
        return _execute_baseline(args.pages)

    if args.once:
        return _execute_monitor_run(
            args.pages,
            notify=not args.no_notify,
            health_enabled=not args.no_health,
            jitter=not args.no_jitter,
        )

    while True:
        _execute_monitor_run(
            args.pages,
            notify=not args.no_notify,
            health_enabled=not args.no_health,
            jitter=not args.no_jitter,
        )
        if args.no_jitter:
            sleep_for = args.interval
        else:
            sleep_for = max(1, args.interval + random.uniform(-JITTER_SECONDS, JITTER_SECONDS))
        log(f"Sleeping {sleep_for:.0f}s...")
        time.sleep(sleep_for)


if __name__ == "__main__":
    sys.exit(main())

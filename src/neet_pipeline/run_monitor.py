"""
KEA link-watch monitor (see CLAUDE.md).

Usage:
    PYTHONPATH=src python -m neet_pipeline.run_monitor --once
    PYTHONPATH=src python -m neet_pipeline.run_monitor --loop [--interval 600]
    PYTHONPATH=src python -m neet_pipeline.run_monitor --baseline

Watches the pages listed in config/link_watch_pages.txt for newly-added
links and posts them to the Telegram alerts chat. A never-before-seen page
is silently baselined on its first scan (every current link recorded,
nothing alerted) -- only links added after that first scan trigger an alert.

--once does a single scan (for cron/Task Scheduler); --loop repeats every
--interval seconds (default 600 = 10 min) until killed; --baseline records
the current link state without alerting, for a fresh deployment or a
deliberate reset.
"""

from __future__ import annotations
import argparse
import os
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
                         env_path: str = tg.DEFAULT_ENV_PATH) -> int:
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
    args = p.parse_args(argv)

    if args.baseline:
        return _execute_baseline(args.pages)

    if args.once:
        return _execute_monitor_run(
            args.pages,
            notify=not args.no_notify,
            health_enabled=not args.no_health,
        )

    while True:
        _execute_monitor_run(
            args.pages,
            notify=not args.no_notify,
            health_enabled=not args.no_health,
        )
        log(f"Sleeping {args.interval}s...")
        time.sleep(args.interval)


if __name__ == "__main__":
    sys.exit(main())

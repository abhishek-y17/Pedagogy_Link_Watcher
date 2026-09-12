"""
Telegram alerts for generic page-link changes.

These alerts go to the existing staff alerts group. They are deliberately
informational only: a new link does not imply a real result PDF and never
starts scraping or matching.

A large burst of new links can exceed Telegram's 4096-char message limit,
so the formatted alert is split into "(part i/N)" messages, each packed
whole-line and kept under the limit.
"""

from __future__ import annotations

from datetime import datetime

from ..monitor.link_watch import LinkWatchResult
from . import telegram_api as tg

# Telegram's hard limit is 4096 chars. Leave room for the "(part 12/34)\n"
# prefix we prepend when there is more than one chunk.
MAX_ALERT_CHARS = 3800


def format_link_alert_message(results: list[LinkWatchResult], timestamp: str | None = None) -> str:
    timestamp = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_results = [result for result in results if result.ok and result.new_links]
    total_new = sum(len(result.new_links) for result in new_results)

    lines = [f"New KEA page link(s) detected — {timestamp}", f"Total new links: {total_new}"]
    for result in new_results:
        lines.append("")
        lines.append(f"Page: {result.page.name}")
        lines.append(f"Source page: {result.page.url}")
        for link in result.new_links:
            label = link.text or "(no link text)"
            lines.append(f"- {label}")
            lines.append(f"  {link.url}")
    return "\n".join(lines)


def _split_for_telegram(text: str, limit: int = MAX_ALERT_CHARS) -> list[str]:
    """
    Greedy-pack whole lines into chunks <= limit. A link line is never split
    across messages; a single line longer than the limit is hard-sliced (only
    that line). Always returns at least one chunk.
    """
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush():
        nonlocal current, current_len
        if current:
            chunks.append("\n".join(current))
            current = []
            current_len = 0

    for line in text.split("\n"):
        while len(line) > limit:
            flush()
            chunks.append(line[:limit])
            line = line[limit:]
        # +1 for the newline that will join this line to the previous one
        addition = len(line) + (1 if current else 0)
        if current and current_len + addition > limit:
            flush()
            addition = len(line)
        current.append(line)
        current_len += addition

    flush()
    return chunks or [""]


def post_link_alerts(token: str, chat_id: str, results: list[LinkWatchResult],
                     timestamp: str | None = None) -> int:
    total_new = sum(len(result.new_links) for result in results if result.ok)
    if total_new == 0:
        return 0
    chunks = _split_for_telegram(format_link_alert_message(results, timestamp=timestamp))
    n = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        prefix = f"(part {i}/{n})\n" if n > 1 else ""
        tg.send_message(token, chat_id, prefix + chunk)
    return n  # messages sent

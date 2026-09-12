"""
Plain-English config check used by START_MONITOR.bat (and anyone else) before
the monitor starts. Never raises a Python traceback at a non-technical user --
prints a short, specific message and exits 1 instead.

Checks:
  - config/.env exists
  - the 4 required Telegram values are present and non-blank
    (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, HEALTH_BOT_TOKEN, HEALTH_CHAT_ID)

Does NOT validate the values are correct tokens -- only that something was
typed in. A bad token still fails loudly later, from telegram_api.py, with
its own clear message.
"""

from __future__ import annotations
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO_ROOT, "config", ".env")
ENV_EXAMPLE = os.path.join(REPO_ROOT, "config", ".env.example")

REQUIRED = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "HEALTH_BOT_TOKEN", "HEALTH_CHAT_ID"]


def main() -> int:
    if not os.path.exists(ENV_PATH):
        print()
        print("=" * 64)
        print(" PROBLEM: config\\.env is missing.")
        print()
        print(" This file holds your Telegram tokens. To fix it:")
        print("   1. Double-click SETUP.bat first (it creates config\\.env")
        print("      from the template), OR")
        print("   2. Copy config\\.env.example to config\\.env yourself")
        print("   3. Open config\\.env in Notepad and fill in your tokens")
        print("=" * 64)
        print()
        return 1

    try:
        from dotenv import dotenv_values
        values = {**dotenv_values(ENV_PATH), **os.environ}
    except Exception as e:
        print(f"PROBLEM: could not read config\\.env ({type(e).__name__}: {e})")
        return 1

    missing = [k for k in REQUIRED if not (values.get(k) or "").strip()]
    if missing:
        print()
        print("=" * 64)
        print(" PROBLEM: config\\.env is missing some values.")
        print()
        print(" These are blank or not set:")
        for k in missing:
            print(f"   - {k}")
        print()
        print(" Open config\\.env in Notepad and fill them in, then try again.")
        print(" (HEALTHCHECKS_URL is optional and can stay blank.)")
        print("=" * 64)
        print()
        return 1

    print("[OK] config\\.env looks complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Linux/macOS equivalent of START_MONITOR.bat (bonus -- see setup.sh).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
export PYTHONPATH=src

VENV_PY=".venv/bin/python"
if [ ! -x "$VENV_PY" ]; then
    echo "[PROBLEM] setup has not been run yet. Run ./setup.sh first."
    exit 1
fi

echo "============================================================"
echo " KEA Link Watch -- running (checks every 1 minute)"
echo " Press Ctrl+C to stop. Status heartbeat goes to the HEALTH"
echo " Telegram group; real alerts go to the MAIN Telegram group."
echo "============================================================"

"$VENV_PY" scripts/preflight_check.py || exit 1
echo

# First run on this machine: seed a starting point before scanning for real,
# so a fresh checkout doesn't treat every existing link as brand new and
# alert on all of it at once. Only runs once (until data/cache exists).
if [ ! -d "data/cache" ]; then
    echo "First run -- setting the starting point (no alerts sent this step)..."
    "$VENV_PY" -m neet_pipeline.run_monitor --baseline || {
        echo "[PROBLEM] Could not set the starting point -- check your internet connection and try again."
        exit 1
    }
    echo "[OK] Starting point set. Starting normal monitoring now..."
    echo
fi

exec "$VENV_PY" -m neet_pipeline.run_monitor --loop --interval 60

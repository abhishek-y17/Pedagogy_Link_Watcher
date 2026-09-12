#!/usr/bin/env bash
# Linux/macOS equivalent of SETUP.bat (bonus -- the office deployment is
# Windows-first; see SETUP.bat / README_OFFICE.txt for the primary path).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "============================================================"
echo " KEA Link Watch -- one-time setup"
echo "============================================================"

PYEXE=""
for cand in python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PYEXE="$cand"; break; fi
done
if [ -z "$PYEXE" ]; then
    echo "[PROBLEM] Python 3 was not found. Install it from https://www.python.org/downloads/"
    echo "          (or your distro's package manager) and re-run this script."
    exit 1
fi
echo "[OK] Found $($PYEXE --version)"

if [ -x ".venv/bin/python" ]; then
    echo "[OK] .venv already exists -- skipping creation."
else
    echo "Creating .venv ..."
    "$PYEXE" -m venv .venv || { echo "[PROBLEM] venv creation failed."; exit 1; }
fi

VENV_PY=".venv/bin/python"
echo "Installing required packages..."
"$VENV_PY" -m pip install --upgrade pip || { echo "[PROBLEM] pip upgrade failed."; exit 1; }
"$VENV_PY" -m pip install -r requirements.txt || { echo "[PROBLEM] package install failed."; exit 1; }

echo "Installing the Chromium browser component..."
"$VENV_PY" -m playwright install --with-deps chromium || {
    echo "[PROBLEM] browser install failed (on Linux this may need extra system"
    echo "          libraries -- see the error above and Playwright's docs)."
    exit 1
}

if [ -f "config/.env" ]; then
    echo "[OK] config/.env already exists -- leaving it alone."
elif [ -f "config/.env.example" ]; then
    cp "config/.env.example" "config/.env"
    echo "[ACTION NEEDED] Created config/.env from the template."
    echo "                Edit it with your tokens before starting."
else
    echo "[PROBLEM] config/.env.example is missing."
    exit 1
fi

echo
echo "Setup complete! Next: fill in config/.env, then run ./start_monitor.sh"

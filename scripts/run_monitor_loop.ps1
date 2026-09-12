# Local standing link-watch loop -- checks every page listed in
# config/link_watch_pages.txt on an interval and posts newly-added links to
# the Telegram alerts group, plus a ✅/❌ heartbeat to the health group.
#
# Production runs on an office PC via START_MONITOR.bat / INSTALL_AUTOSTART.bat
# (see CLAUDE.md -- KEA geo-blocks non-Indian IPs, so this can't run on a
# cloud host). This script is a plain PowerShell equivalent for a laptop watch.
#
# --- HOW TO RUN -------------------------------------------------------
# From the repo root, in PowerShell (no venv activation needed):
#
#       .\scripts\run_monitor_loop.ps1
#
# Ctrl+C stops it. Requires config/.env with TELEGRAM_BOT_TOKEN /
# TELEGRAM_CHAT_ID for alerts and HEALTH_BOT_TOKEN / HEALTH_CHAT_ID for the
# separate heartbeat group (see config/.env.example). Use
# `python -m neet_pipeline.run_monitor --loop --no-health` for a dry run
# without health reporting.
# ------------------------------------------------------------------------

$root = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = "src"
& (Join-Path $root ".venv\Scripts\python.exe") -m neet_pipeline.run_monitor --loop

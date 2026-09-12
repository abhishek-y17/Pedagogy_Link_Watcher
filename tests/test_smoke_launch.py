"""
Smoke test for the one-click launcher path: proves that after a plain
`pip install -r requirements.txt` (no monkeypatching, no mocks), the package
actually imports and `run_monitor --once --no-notify --no-health` runs to
completion without crashing. This is what SETUP.bat + START_MONITOR.bat /
scripts/run_once_task.bat ultimately invoke -- if this test fails, a
non-technical user's install is broken (missing dependency, import error,
syntax error, etc.), which is exactly the failure class the launcher can't
self-diagnose.

Runs as a real subprocess (not an in-process call) so it also exercises the
`python -m neet_pipeline.run_monitor` entry point itself, not just the
importability of the module. Uses an empty site/link-watch config so it never
touches the network -- this is an install/import smoke test, not a network
integration test (that's covered elsewhere with mocks).
"""

from __future__ import annotations
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")


def test_run_monitor_once_runs_cleanly_with_empty_config(tmp_path):
    pages_txt = tmp_path / "link_watch_pages.txt"
    pages_txt.write_text("", encoding="utf-8")  # no pages -> link_watch stays empty

    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR

    proc = subprocess.run(
        [sys.executable, "-m", "neet_pipeline.run_monitor",
         "--once", "--no-notify", "--no-health", "--no-jitter", "--pages", str(pages_txt)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, f"unexpected crash:\n{combined}"
    assert proc.returncode == 0, (
        f"expected a clean exit (0 link-watch pages configured is a trivially clean scan), "
        f"got {proc.returncode}:\n{combined}"
    )
    assert "Loaded 0 link-watch page(s)" in combined


def test_neet_pipeline_package_imports_cleanly():
    """Catches a missing/incompatible dependency before it reaches a user --
    this is the #1 way "just install and run" breaks for a non-coder."""
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC_DIR
    modules = [
        "neet_pipeline.run_monitor",
        "neet_pipeline.monitor.link_watch",
        "neet_pipeline.monitor.headless",
        "neet_pipeline.notifier.link_alerts",
        "neet_pipeline.notifier.telegram_api",
    ]
    proc = subprocess.run(
        [sys.executable, "-c", "import " + ", ".join(modules)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert proc.returncode == 0, f"import failed:\n{proc.stdout}{proc.stderr}"

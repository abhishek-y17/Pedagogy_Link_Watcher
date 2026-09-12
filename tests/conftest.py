import os
import sys
import time

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)


@pytest.fixture(autouse=True)
def _no_real_sleeps(monkeypatch):
    """run_monitor.py sleeps for jitter (up to 30s) and --loop's inter-cycle
    delay. Tests exercise these code paths often; a real sleep would make
    the suite take minutes without testing anything meaningful. Individual
    tests that care about the sleep duration itself should monkeypatch
    time.sleep locally, which overrides this."""
    monkeypatch.setattr(time, "sleep", lambda *_a, **_k: None)

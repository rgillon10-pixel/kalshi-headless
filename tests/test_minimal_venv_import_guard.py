"""Minimal-venv import guard for the hourly pass (2026-08-24 outage post-mortem).

`pyproject.toml` keeps `cryptography` and `websocket-client` in the `dev` extra so tests and
cloud passes run in a minimal venv. That contract is only real if every module the hourly
orchestrator imports at module level survives those packages being ABSENT. It was silently
broken on 2026-07-28: `collection/polymarket_us_live.py` gained a module-level
`from cryptography...import ed25519`, `hourly_pass` imports that module, and every VPS hourly
pass died at import time for 27 days — 15 collectors down, zero tape, while the cron kept
reporting "no new tape lines".

An in-process import test proves nothing here (this venv may have the dev extras installed),
so per the L232 pattern the import runs in a REAL subprocess with a meta_path blocker that
makes the dev-extra distributions unimportable, simulating the minimal venv exactly.
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Top-level import names of every `dev` extra in pyproject.toml. If an extra is added there,
# add its import name here — that is the whole maintenance burden of this guard.
DEV_EXTRA_IMPORT_NAMES = ("cryptography", "websocket")

_BLOCKER_PROLOGUE = """
import importlib.abc
import sys

BLOCKED = {blocked!r}

class _MinimalVenvBlocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split(".")[0]
        if root in BLOCKED:
            raise ModuleNotFoundError(f"No module named {{fullname!r}} (blocked: minimal venv)")
        return None

sys.meta_path.insert(0, _MinimalVenvBlocker())
"""


def _import_with_blocked_extras(module: str) -> subprocess.CompletedProcess:
    code = _BLOCKER_PROLOGUE.format(blocked=DEV_EXTRA_IMPORT_NAMES) + (
        f"import importlib\nimportlib.import_module({module!r})\nprint('ok')\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_hourly_pass_imports_without_dev_extras() -> None:
    proc = _import_with_blocked_extras("collection.hourly_pass")
    assert proc.returncode == 0, (
        "collection.hourly_pass failed to import with dev extras blocked — this is the exact "
        "failure mode that killed every VPS hourly pass 2026-07-28 → 2026-08-24. A module it "
        "imports at module level must be importing a dev-extra package eagerly; make that "
        f"import lazy (as ws_depth.py does).\nstderr:\n{proc.stderr}"
    )


def test_blocker_can_fire() -> None:
    """L189/L192: the guard must be shown ABLE to fail — a blocker that blocks nothing would
    make the test above a permanent false pass."""
    proc = _import_with_blocked_extras("cryptography")
    assert proc.returncode != 0 and "blocked: minimal venv" in proc.stderr

"""Hourly collector entry point (READ-ONLY) — Q3, the single command the hourly
Haiku routine runs.

One pass = one `collection.sports_pairs` pass + one `collection.crypto_hourly` pass;
during the 09 UTC hour, also run `scripts/anomaly_sweep.py` if it exists (Q6, not yet
built — this entry point checks for it every run so no further wiring is needed once
Q6 lands; its absence is not a failure).

Never fakes success: a sub-pass that raises degrades to an honest `ok: False` entry
(same discipline as each collector's own per-leg error handling) rather than crashing
the whole hourly pass, and `completeness_ok` reflects the worst of what actually
happened — a hard sub-pass failure, any series-enumeration error inside a sub-pass, or
(during the 09 UTC hour) the anomaly sweep existing but failing — never silently True.

Run:
    python -m collection.hourly_pass
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

from collection import crypto_hourly, sports_pairs
from core.io import REPO_ROOT

ANOMALY_SWEEP_HOUR_UTC = 9
ANOMALY_SWEEP_SCRIPT = REPO_ROOT / "scripts" / "anomaly_sweep.py"


def _run_pass(fn: Callable[[], Dict], label: str) -> Dict:
    """Run one sub-pass; a hard exception degrades to an honest failure entry rather
    than crashing the whole hourly pass."""
    try:
        return {"ok": True, **fn()}
    except Exception as exc:
        print(f"[hourly_pass] ERROR {label} pass failed: {exc}", file=sys.stderr)
        return {"ok": False, "error": str(exc)}


def _default_anomaly_runner() -> bool:
    """Run scripts/anomaly_sweep.py as a subprocess if it exists. Its absence (Q6 not
    yet built) is NOT a failure; a nonzero exit once it exists IS."""
    if not ANOMALY_SWEEP_SCRIPT.exists():
        return True
    result = subprocess.run([sys.executable, str(ANOMALY_SWEEP_SCRIPT)],
                            cwd=REPO_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"[hourly_pass] ERROR anomaly_sweep.py failed (rc={result.returncode}): "
              f"{result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def run(sports_fn: Optional[Callable[[], Dict]] = None,
        crypto_fn: Optional[Callable[[], Dict]] = None,
        anomaly_runner: Optional[Callable[[], bool]] = None,
        now: Optional[datetime] = None) -> Dict:
    """One hourly pass. `sports_fn`/`crypto_fn`/`anomaly_runner`/`now` are injectable
    for offline testing; production defaults to the real collectors (each builds its
    own live Kalshi client), the real anomaly-sweep subprocess check, and the real
    wall-clock hour."""
    now = now if now is not None else datetime.now(timezone.utc)
    sports_fn = sports_fn or sports_pairs.run
    crypto_fn = crypto_fn or crypto_hourly.run
    anomaly_runner = anomaly_runner or _default_anomaly_runner

    sports = _run_pass(sports_fn, "sports_pairs")
    crypto = _run_pass(crypto_fn, "crypto_hourly")

    ran_anomaly_sweep = now.hour == ANOMALY_SWEEP_HOUR_UTC
    anomaly_ok = anomaly_runner() if ran_anomaly_sweep else True

    n_markets = sports.get("total_outcomes", 0) + crypto.get("total_outcomes", 0)
    n_lines = sports.get("n_events", 0) + crypto.get("n_captured", 0)
    completeness_ok = (
        sports.get("ok", False) and crypto.get("ok", False)
        and sports.get("n_series_errors", 0) == 0
        and crypto.get("n_series_errors", 0) == 0
        and anomaly_ok
    )

    summary = {
        "captured_at": now.isoformat(),
        "n_markets": n_markets, "n_lines": n_lines,
        "completeness_ok": completeness_ok,
        "ran_anomaly_sweep": ran_anomaly_sweep, "anomaly_sweep_ok": anomaly_ok,
        "sports": sports, "crypto": crypto,
    }
    print(f"[hourly_pass] {n_markets} markets, {n_lines} lines, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}")
    return summary


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Hourly collector entry point (sports pairs + crypto hourly "
                    "+ 09 UTC anomaly sweep if built)")
    ap.parse_args(argv)
    summary = run()
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

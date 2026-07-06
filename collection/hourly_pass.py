"""Hourly collector entry point (READ-ONLY) — the single command the hourly routine runs.

LOOP-QUEUE.md Q3: one `collection.sports_pairs` pass + one `collection.crypto_hourly` pass
every hour; during the 09 UTC hour also runs `scripts/anomaly_sweep.py` as a subprocess if
that script exists yet (Q6, not built as of this module's authorship — its absence is
recorded as `not_built`, never silently skipped without a trace).

LOOP-QUEUE.md Q8 (2026-07-05): also runs one `collection.polymarket_pairs` pass every hour
(World Cup ends Jul 19 — repeated snapshots are the prerequisite for S9's lead-lag
cross-correlation, and every skipped hour is a snapshot lost for good).

LOOP-QUEUE.md Q10 (2026-07-05): also runs one `collection.econ_prints` pass during the
09 UTC hour (CPI/payrolls/GDP ladders release infrequently — a daily cadence is enough,
per that item's own spec — and Kalshi purges settled markets ~60 days after close, so
every un-collected release is data lost forever).

LOOP-QUEUE.md Q12 (2026-07-06): also runs one `collection.polymarket_pairs.run_fed_decision`
pass every hour — a second Kalshi<->Polymarket cross-venue family (Fed rate-decision
meetings) that outlives the World Cup, serving S17 the same way the WC-round pass serves S9.

Never fakes success: each sub-pass is invoked independently and its exception (if any) is
caught and recorded rather than allowed to take the other sub-pass down with it. Overall
`completeness_ok` is the AND of each sub-pass's own honest completeness signal (already
computed by that sub-pass per Hard Rule discipline) — a partial failure here always shows up
as `completeness_ok: False`, it is never absorbed into a false "ok".

`n_markets` counts underlying Kalshi market contracts captured this pass (summed from each
freshly-written tape record's own `expected_outcomes`, e.g. a sports game's 2-3 markets or a
crypto symbol's full bracket ladder); `n_lines` counts the JSONL tape records written (one
per game / one per symbol) — the two numbers are usually different because one crypto-hourly
"line" can represent 100+ markets.

Run one pass:
    python -m collection.hourly_pass
    python -m collection.hourly_pass --sports-limit 3 --crypto-symbols BTC   # offline/dev use
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from collection import crypto_hourly, econ_prints, polymarket_pairs, sports_pairs
from core.io import REPO_ROOT

ANOMALY_SWEEP_UTC_HOUR = 9
ANOMALY_SWEEP_SCRIPT = REPO_ROOT / "scripts" / "anomaly_sweep.py"
ECON_PRINTS_UTC_HOUR = 9


# --------------------------------------------------------------------------- #
# sub-pass wiring (real by default, injectable for offline testing)
# --------------------------------------------------------------------------- #
def _default_sports_pass() -> Dict[str, Any]:
    return sports_pairs.run(odds_api_key=os.environ.get("ODDS_API_KEY"))


def _default_crypto_pass() -> Dict[str, Any]:
    return crypto_hourly.run()


def _default_polymarket_pass() -> Dict[str, Any]:
    return polymarket_pairs.run()


def _default_polymarket_macro_pass() -> Dict[str, Any]:
    return polymarket_pairs.run_fed_decision()


def _default_econ_prints_pass() -> Dict[str, Any]:
    return econ_prints.run()


def _run_anomaly_sweep_subprocess() -> Dict[str, Any]:
    """Run scripts/anomaly_sweep.py as a subprocess (Q6 not built yet -> `not_built`,
    recorded honestly rather than pretending the slot ran)."""
    if not ANOMALY_SWEEP_SCRIPT.exists():
        return {"status": "not_built"}
    proc = subprocess.run(
        [sys.executable, str(ANOMALY_SWEEP_SCRIPT)],
        capture_output=True, text=True, timeout=300)
    result: Dict[str, Any] = {
        "status": "ok" if proc.returncode == 0 else "error",
        "returncode": proc.returncode,
    }
    if proc.returncode != 0:
        result["stderr_tail"] = proc.stderr[-2000:]
    return result


def _safe_call(fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    """Never let one sub-pass's exception take the others down with it."""
    try:
        return {"status": "ok", "result": fn()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


# --------------------------------------------------------------------------- #
# n_markets accounting — read back only the lines this pass just wrote
# --------------------------------------------------------------------------- #
def _sum_expected_markets_from_tape(
        path: Optional[str], capture_id: str,
        expected_outcomes: Callable[[Dict[str, Any]], int]) -> int:
    """Sum `expected_outcomes` over tape records matching `capture_id` in `path` (an
    append-mode JSONL file may hold prior passes' lines too — filter to just this one)."""
    if not path:
        return 0
    total = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("capture_id") != capture_id:
                continue
            total += expected_outcomes(rec)
    return total


def _sports_expected_outcomes(rec: Dict[str, Any]) -> int:
    return rec.get("expected_outcomes", 0) or 0


def _crypto_expected_outcomes(rec: Dict[str, Any]) -> int:
    return (rec.get("current") or {}).get("expected_outcomes", 0) or 0


# --------------------------------------------------------------------------- #
# one hourly pass
# --------------------------------------------------------------------------- #
def run(sports_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        crypto_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        polymarket_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        polymarket_macro_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        anomaly_sweep_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        econ_prints_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        now: Optional[datetime] = None) -> Dict[str, Any]:
    """One hourly pass: sports_pairs + crypto_hourly + polymarket_pairs (WC round) +
    polymarket_pairs.run_fed_decision (Fed meetings), plus anomaly_sweep and econ_prints
    during the 09 UTC hour. `sports_fn`/`crypto_fn`/`polymarket_fn`/`polymarket_macro_fn`/
    `anomaly_sweep_fn`/`econ_prints_fn`/`now` are injectable for offline testing; each
    defaults to the real, network-touching implementation."""
    ts = now if now is not None else datetime.now(timezone.utc)
    sports_fn = sports_fn or _default_sports_pass
    crypto_fn = crypto_fn or _default_crypto_pass
    polymarket_fn = polymarket_fn or _default_polymarket_pass
    polymarket_macro_fn = polymarket_macro_fn or _default_polymarket_macro_pass

    sports = _safe_call(sports_fn)
    crypto = _safe_call(crypto_fn)
    polymarket = _safe_call(polymarket_fn)
    polymarket_macro = _safe_call(polymarket_macro_fn)

    completeness_ok = True
    n_markets = 0
    n_lines = 0

    if sports["status"] == "ok":
        r = sports["result"]
        n_games, n_complete = r.get("n_games", 0), r.get("n_complete", 0)
        n_lines += n_games
        n_markets += _sum_expected_markets_from_tape(
            r.get("path"), r.get("capture_id", ""), _sports_expected_outcomes)
        completeness_ok = completeness_ok and (n_games == n_complete)
    else:
        completeness_ok = False

    if crypto["status"] == "ok":
        r = crypto["result"]
        n_symbols, n_complete = r.get("n_symbols", 0), r.get("n_complete", 0)
        n_lines += n_symbols
        n_markets += _sum_expected_markets_from_tape(
            r.get("path"), r.get("capture_id", ""), _crypto_expected_outcomes)
        completeness_ok = completeness_ok and (n_symbols == n_complete)
    else:
        completeness_ok = False

    if polymarket["status"] == "ok":
        r = polymarket["result"]
        n_matched = r.get("n_matched", 0)
        n_lines += n_matched
        n_markets += n_matched
        completeness_ok = completeness_ok and bool(r.get("completeness_ok", False))
    else:
        completeness_ok = False

    if polymarket_macro["status"] == "ok":
        r = polymarket_macro["result"]
        n_matched = r.get("n_matched", 0)
        n_lines += n_matched
        n_markets += n_matched
        completeness_ok = completeness_ok and bool(r.get("completeness_ok", False))
    else:
        completeness_ok = False

    anomaly: Optional[Dict[str, Any]] = None
    if ts.hour == ANOMALY_SWEEP_UTC_HOUR:
        sweep_fn = anomaly_sweep_fn or _run_anomaly_sweep_subprocess
        anomaly = _safe_call(sweep_fn)
        sweep_status = anomaly["result"]["status"] if anomaly["status"] == "ok" else "error"
        if sweep_status == "error":
            completeness_ok = False

    econ: Optional[Dict[str, Any]] = None
    if ts.hour == ECON_PRINTS_UTC_HOUR:
        e_fn = econ_prints_fn or _default_econ_prints_pass
        econ = _safe_call(e_fn)
        if econ["status"] == "error":
            completeness_ok = False
        else:
            n_series, n_complete_econ = econ["result"].get("n_series", 0), econ["result"].get("n_complete", 0)
            if n_series != n_complete_econ:
                completeness_ok = False

    summary = {
        "captured_at": ts.isoformat(),
        "sports_pairs": sports,
        "crypto_hourly": crypto,
        "polymarket_pairs": polymarket,
        "polymarket_macro_pairs": polymarket_macro,
        "anomaly_sweep": anomaly,
        "econ_prints": econ,
        "n_markets": n_markets,
        "n_lines": n_lines,
        "completeness_ok": completeness_ok,
    }
    print(f"[hourly_pass] {n_markets} markets, {n_lines} lines, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Hourly collector entry point (read-only)")
    ap.add_argument("--sports-limit", type=int, default=None,
                    help="cap sports candidate series per pass (offline/dev use)")
    ap.add_argument("--crypto-symbols", nargs="*", default=None,
                    help="cap crypto symbols per pass, e.g. --crypto-symbols BTC (offline/dev use)")
    args = ap.parse_args(argv)

    sports_fn = None
    if args.sports_limit is not None:
        sports_fn = lambda: sports_pairs.run(  # noqa: E731
            limit=args.sports_limit, odds_api_key=os.environ.get("ODDS_API_KEY"))

    crypto_fn = None
    if args.crypto_symbols is not None:
        symbols = {s: crypto_hourly.SYMBOLS[s] for s in args.crypto_symbols}
        crypto_fn = lambda: crypto_hourly.run(symbols=symbols)  # noqa: E731

    summary = run(sports_fn=sports_fn, crypto_fn=crypto_fn)
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

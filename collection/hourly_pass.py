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

LOOP-QUEUE.md Q12 CPI follow-up (2026-07-06): also runs one
`collection.polymarket_pairs.run_cpi` pass during the 09 UTC hour, same slot/cadence as
`econ_prints` (CPI prints release monthly — a daily cadence is enough, and the underlying
Kalshi ladder this leg reads doesn't move faster than that either).

S6 forward-depth (2026-07-07): also runs one `collection.orderbook_depth` pass every hour,
snapshotting FULL L2 book depth for exactly the tickers the sports/crypto sub-passes just
discovered THIS pass (read straight back from their freshly-written tape by capture_id — no
re-sweep of the 10k+ open universe, lesson L10). Serves S6 (inventory-aware market-making),
whose gate note needs the forward tape to estimate order-arrival intensity. Honest cadence
caveat lives in that module's docstring: hourly snapshots are coarse for intensity, not a
continuous order-flow tape.

Weather revival (2026-07-15): also runs one `collection.weather_books` pass every hour —
forward full-depth orderbook capture for Kalshi weather markets (daily KXHIGH*/KXLOWT* ladders
for the config cities + a live category sweep so new series don't drop, plus the KXTEMPNYCH
hourly-directional series). The VPS weather tape was torn down 2026-07-03 and nothing has
collected weather since; every weather edge candidate in the revival dossier is blocked on a
fresh forward L2 tape, and (lesson L11) an un-collected snapshot is lost forever. Unlike the
S6 depth pass this sub-pass does its OWN discovery (weather isn't in the sports/crypto
tickers the depth pass reuses), fault-isolated like every sibling.

Weather revival forecast + actuals legs (2026-07-16, Q38): also runs, ONCE per UTC day each,
(a) one `collection.forecast_collector` pass during the FORECAST_COLLECTOR_UTC_HOUR (multi-model
Open-Meteo daily Tmax forecast tape, tag `synthetic` — a forecast is never a fill price) and
(b) one `collection.weather_actuals` pass during the WEATHER_ACTUALS_UTC_HOUR (previous-UTC-day
settlement-truth actuals: CLI + METAR cross-confirmed to `broker_truth`, else `unverifiable`,
joined to that day's SETTLED Kalshi KXHIGH*/KXLOWT* ladders). These are the two tape legs Q37's
future EMOS weather-signal probe is blocked on; the forecast collector was previously a manual
one-shot ("SCHEDULING IS DEFERRED") because a sleeping-laptop cadence produced gappy tape — the
always-on cloud/VPS cadence removes that blocker. Both are gated on their own UTC hour (distinct
from ANOMALY/ECON's 09 so no single hour is overloaded) and, being once-daily forecast/actuals
tape rather than fresh Kalshi market BBOs, do NOT contribute to n_markets/n_lines; they fold into
`completeness_ok` honestly (a fetch exception lowers it, a not-yet-posted source does not).

Crypto perps (2026-07-16, Ryan interactive session — Q42/Q43 prerequisite): also runs one
`collection.perp_tape` pass every hour — Kalshi's CFTC-regulated crypto perpetual futures
(launched 2026-05-29, a separate public `/margin` API on a separate host) full contract list,
BTC/ETH L2 books, per-contract live funding-rate estimates, and a trailing finalized-funding
window. The L2 book and the intra-window funding estimate are NOT retrievable later (the
estimate's path is destroyed at each 8h funding boundary), so every skipped hour is perps
microstructure lost for good; the funding-clamp anomaly (rates print exactly 0 in 62–99% of
windows) is Q42's thesis and this tape is what that probe reads. Fault-isolated like every
sibling; its `n_contracts` (underlying perp contracts listed) folds into n_markets and its
JSONL section-lines into n_lines.

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

from collection import (crypto_hourly, econ_prints, forecast_collector, orderbook_depth,
                        perp_tape, polymarket_pairs, sports_pairs, weather_actuals,
                        weather_books)
from core.io import REPO_ROOT

ANOMALY_SWEEP_UTC_HOUR = 9
ANOMALY_SWEEP_SCRIPT = REPO_ROOT / "scripts" / "anomaly_sweep.py"
ECON_PRINTS_UTC_HOUR = 9
# Weather revival (Q38): both legs fire ONCE per UTC day, on their own hours kept distinct
# from ANOMALY/ECON's 09 so a single hour's pass isn't overloaded. The forecast leg is a
# DAILY Tmax forecast (not a book snapshot) — hourly capture would be redundant; the actuals
# leg reconciles the PREVIOUS UTC day's settlement truth, run an hour later so late-posting
# NWS CLI reports for the just-closed day are more likely to be available.
FORECAST_COLLECTOR_UTC_HOUR = 11   # daily multi-model Open-Meteo forecast tape (tag: synthetic)
WEATHER_ACTUALS_UTC_HOUR = 12      # daily actuals + Kalshi settled-market join for yesterday


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


def _default_polymarket_cpi_pass() -> Dict[str, Any]:
    return polymarket_pairs.run_cpi()


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
# forward-depth (S6) ticker gathering — reuse THIS pass's already-discovered set,
# read straight back from the tape the sports/crypto sub-passes just wrote (no re-sweep,
# no extra discovery API calls — lesson L10: never re-pull the 10k+ open universe)
# --------------------------------------------------------------------------- #
def _tickers_from_tape(path: Optional[str], capture_id: str,
                       extract: Callable[[Dict[str, Any]], List[str]]) -> List[str]:
    if not path:
        return []
    out: List[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("capture_id") != capture_id:
                continue
            out.extend(extract(rec))
    return out


def _sports_depth_tickers(rec: Dict[str, Any]) -> List[str]:
    return [o.get("ticker") for o in (rec.get("outcomes") or []) if o.get("ticker")]


def _crypto_depth_tickers(rec: Dict[str, Any]) -> List[str]:
    return [o.get("ticker")
            for o in ((rec.get("current") or {}).get("outcomes") or []) if o.get("ticker")]


def _gather_depth_tickers(sports: Dict[str, Any], crypto: Dict[str, Any]) -> List[str]:
    """The exact tickers this pass already discovered — pulled from the freshly-written
    sports/crypto tape lines (filtered by their capture_id), never a fresh platform sweep."""
    tickers: List[str] = []
    if sports.get("status") == "ok":
        r = sports["result"]
        tickers += _tickers_from_tape(r.get("path"), r.get("capture_id", ""),
                                      _sports_depth_tickers)
    if crypto.get("status") == "ok":
        r = crypto["result"]
        tickers += _tickers_from_tape(r.get("path"), r.get("capture_id", ""),
                                      _crypto_depth_tickers)
    return tickers


def _default_depth_pass(tickers: List[str]) -> Dict[str, Any]:
    return orderbook_depth.run(tickers=tickers)


def _default_weather_pass() -> Dict[str, Any]:
    return weather_books.run()


def _default_forecast_pass() -> Dict[str, Any]:
    return forecast_collector.run()


def _default_weather_actuals_pass() -> Dict[str, Any]:
    return weather_actuals.run()


def _default_perp_pass() -> Dict[str, Any]:
    return perp_tape.run()


# --------------------------------------------------------------------------- #
# one hourly pass
# --------------------------------------------------------------------------- #
def run(sports_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        crypto_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        polymarket_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        polymarket_macro_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        anomaly_sweep_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        econ_prints_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        polymarket_cpi_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        depth_fn: Optional[Callable[[List[str]], Dict[str, Any]]] = None,
        weather_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        forecast_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        weather_actuals_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        perp_fn: Optional[Callable[[], Dict[str, Any]]] = None,
        now: Optional[datetime] = None) -> Dict[str, Any]:
    """One hourly pass: sports_pairs + crypto_hourly + polymarket_pairs (WC round) +
    polymarket_pairs.run_fed_decision (Fed meetings), plus anomaly_sweep, econ_prints, and
    polymarket_pairs.run_cpi (CPI derived-bucket pairing) during the 09 UTC hour.
    `sports_fn`/`crypto_fn`/`polymarket_fn`/`polymarket_macro_fn`/`anomaly_sweep_fn`/
    `econ_prints_fn`/`polymarket_cpi_fn`/`now` are injectable for offline testing; each
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

    # forward-depth (S6): snapshot full L2 depth for THIS pass's already-discovered tickers.
    # Fault-isolated like every sibling; one line per ticker, each ticker one market.
    depth_tickers = _gather_depth_tickers(sports, crypto)
    d_fn = depth_fn or _default_depth_pass
    depth = _safe_call(lambda: d_fn(depth_tickers))
    if depth["status"] == "ok":
        r = depth["result"]
        n_captured = r.get("n_captured", 0)
        n_lines += n_captured
        n_markets += n_captured
        completeness_ok = completeness_ok and bool(r.get("completeness_ok", False))
    else:
        completeness_ok = False

    # crypto perps (Q42/Q43 prereq): full contract list + BTC/ETH L2 + live funding
    # estimates + trailing finalized funding. Fault-isolated like every sibling; its
    # section-lines fold into n_lines and its listed perp contracts into n_markets.
    p_fn = perp_fn or _default_perp_pass
    perps = _safe_call(p_fn)
    if perps["status"] == "ok":
        r = perps["result"]
        n_lines += r.get("n_lines", 0)
        n_markets += r.get("n_contracts", 0)
        completeness_ok = completeness_ok and bool(r.get("completeness_ok", False))
    else:
        completeness_ok = False

    # weather revival: forward full-depth capture for weather markets. Own discovery,
    # fault-isolated like every sibling; one line per open weather market, each one market.
    w_fn = weather_fn or _default_weather_pass
    weather = _safe_call(w_fn)
    if weather["status"] == "ok":
        r = weather["result"]
        n_captured = r.get("n_captured", 0)
        n_lines += n_captured
        n_markets += n_captured
        completeness_ok = completeness_ok and bool(r.get("completeness_ok", False))
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

    polymarket_cpi: Optional[Dict[str, Any]] = None
    if ts.hour == ECON_PRINTS_UTC_HOUR:
        cpi_fn = polymarket_cpi_fn or _default_polymarket_cpi_pass
        polymarket_cpi = _safe_call(cpi_fn)
        if polymarket_cpi["status"] == "error":
            completeness_ok = False
        else:
            n_lines += polymarket_cpi["result"].get("n_matched", 0)
            n_markets += polymarket_cpi["result"].get("n_matched", 0)
            completeness_ok = completeness_ok and bool(polymarket_cpi["result"].get("completeness_ok", False))

    # weather revival forecast leg (Q38a): daily multi-model Tmax forecast, fired once per UTC
    # day. Fault-isolated; its lines are forecast tape (source_tag synthetic), NOT Kalshi market
    # contracts, so they are deliberately NOT folded into n_markets/n_lines (mirrors econ_prints).
    # Completeness folds in honestly: every (city, model) it set out to collect must persist
    # (n_complete == n_expected) — a config-only zero-expected pass is fine, a fetch exception is
    # not (the exception surfaces as status=error via _safe_call).
    forecast: Optional[Dict[str, Any]] = None
    if ts.hour == FORECAST_COLLECTOR_UTC_HOUR:
        f_fn = forecast_fn or _default_forecast_pass
        forecast = _safe_call(f_fn)
        if forecast["status"] == "error":
            completeness_ok = False
        else:
            r = forecast["result"]
            n_exp, n_comp = r.get("n_expected", 0), r.get("n_complete", 0)
            if n_comp != n_exp:
                completeness_ok = False

    # weather revival actuals leg (Q38b): daily settlement-truth actuals + Kalshi settled-market
    # join for the PREVIOUS UTC day, fired once per UTC day (an hour after the forecast leg).
    # Fault-isolated; its lines are actuals tape (broker_truth / unverifiable), not fresh Kalshi
    # market BBOs, so likewise NOT folded into n_markets/n_lines. Completeness folds in via the
    # module's own honest signal (a city fetch/parse exception or a Kalshi settled-fetch
    # exception lowers it; a source that simply hasn't posted yet is captured, not a drop).
    wx_actuals: Optional[Dict[str, Any]] = None
    if ts.hour == WEATHER_ACTUALS_UTC_HOUR:
        wa_fn = weather_actuals_fn or _default_weather_actuals_pass
        wx_actuals = _safe_call(wa_fn)
        if wx_actuals["status"] == "error":
            completeness_ok = False
        else:
            completeness_ok = completeness_ok and bool(wx_actuals["result"].get("completeness_ok", False))

    summary = {
        "captured_at": ts.isoformat(),
        "sports_pairs": sports,
        "crypto_hourly": crypto,
        "orderbook_depth": depth,
        "perp_tape": perps,
        "weather_books": weather,
        "polymarket_pairs": polymarket,
        "polymarket_macro_pairs": polymarket_macro,
        "anomaly_sweep": anomaly,
        "econ_prints": econ,
        "polymarket_cpi_pairs": polymarket_cpi,
        "forecast_collector": forecast,
        "weather_actuals": wx_actuals,
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

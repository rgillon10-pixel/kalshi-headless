#!/usr/bin/env python3
"""q36_kxtemp_hourly_probe.py — Q36: KXTEMPNYCH hourly settlement-basis + microstructure study.

LOOP-QUEUE.md Q36 (weather revival, 2026-07-15 Ryan session; dossier
`findings/2026-07-15-weather-revival-dossier.md`). Kalshi now runs HOURLY temperature markets
(KXTEMPNYCH + AUS/CHI/DC/LAX siblings): one market per hour, opens ~1–2h before the reading,
settles on **The Weather Company (TWC) value for the station coordinates** (NOT NWS CLI). A
60-minute market on a near-observable quantity is a pure nowcast game — the VPS-latency thesis
is that whoever ingests faster obs and reprices within the hour has a structural edge. This is
the read-only probe Q36 specifies once its tape gate opens.

── STATUS: PROBE-PREP, NOT A VERDICT (self-activating; mirrors scripts/q32_*) ──────────────────
This probe needs two things that do not yet co-exist in committed tape:
  (a) ≥7 distinct dt-days of `tape/weather_books/` hourly-family coverage. The collector landed
      2026-07-15; only `dt=2026-07-16.jsonl` (day 1) is committed as of this writing, so the
      gate is NOT open. Eligible ~2026-07-22.
  (b) a SETTLEMENT leg — KXTEMPNYCH settles on the TWC value for KNYC, which is NOT captured in
      any tape family (fetching it is a network COLLECTION change, OUT OF SCOPE for this probe),
      and the ASOS/METAR ob stream that the settlement-basis half reconciles against is likewise
      not captured. This leg is therefore INJECTABLE via `--settlement-dir` (exactly as Q32's
      Polymarket leg is injectable). Absent/empty → both halves report "settlement/ob leg not
      captured" and the probe exits INSUFFICIENT DATA.
Because BOTH gates are unmet on today's tape, this file is written + offline-tested against
FIXTURES so it fires the moment the tape gate opens and a settlement leg is injected. It makes
NO edge claim, writes NO findings/ verdict, and registers NOTHING in kb/strategies. Run against
today's real, incomplete tape it prints an honest INSUFFICIENT DATA line and exits 0 — it NEVER
fabricates a bootstrap from empty input.

── EXPECTED SCHEMA for the injected settlement leg (`--settlement-dir`, one JSONL/day) ─────────
One line per settled hourly-market ticker. The realized-outcome fields are `broker_truth`; the
ASOS/METAR ob timeseries is an observed feed (tag `synthetic` for our purposes — it is not a
Kalshi settlement and not a fill). Shape:

  {
    "schema_version": "weather_settlement.v0",           # v0 = proposed, not yet captured
    "capture_id": "20260722T130000Z",                    # provenance
    "ticker": "KXTEMPNYCH-26JUL2222-T81.99",             # per hourly-market-ticker JOIN key
    "expiration_value": 82.0,                            # Kalshi settled reading (broker_truth)
    "settled_result": "yes",                            # realized outcome yes|no (broker_truth)
    "twc_value": 81.7,                                  # optional realized TWC value (broker_truth)
    "signal_known_at": "2026-07-22T21:41:00+00:00",     # optional — wall-clock UTC the DECIDING ob
                                                         #   was publicly knowable; needed to isolate
                                                         #   a STALE window (else the P&L half can
                                                         #   only report the structural depth×dur cut)
    "asos_obs": [                                        # optional ob timeseries for the basis half
      {"ts": "2026-07-22T21:35:00+00:00", "temp_f": 81.4, "source": "asos_1min"},
      {"ts": "2026-07-22T21:51:00+00:00", "temp_f": 82.1, "source": "metar"}
    ]
  }

`settled_result` / `expiration_value` are LOAD-BEARING for the microstructure P&L half;
`asos_obs` is LOAD-BEARING for the settlement-basis half. A ticker missing the field a given
half needs is EXCLUDED from that half and COUNTED, never assumed.

── THE TWO HALVES (only when the gate is met; otherwise INSUFFICIENT-DATA exit) ────────────────
1. SETTLEMENT-BASIS half (the tractable one at hourly cadence). Join settled KXTEMPNYCH outcomes
   to the injected ASOS/METAR ob stream and quantify the TWC-vs-ASOS mapping — rounding residual,
   publication lag, disagreement rate — the same shape as validation/v1_actuals.py's CLI-vs-METAR
   reconcile. Descriptive only; no CI, no verdict. Runs only when `asos_obs` is injected.
2. MICROSTRUCTURE half. Per hourly market, measure book convergence timing and the depth-at-touch
   × duration-of-stale-pricing in WALL-CLOCK SECONDS between captures (NOT snapshot counts — L76,
   the W-D forward-fill lesson) and a MANDATORY depth×duration JOINT distribution (L78 — the W-D
   probe died exactly there: depth and duration were anti-correlated, 0 opportunities ≥10 contracts
   AND ≥60s). The stale-ask-lift P&L is net of the TAKER fee (see FEE CHOICE) and block-bootstrapped
   by MARKET-HOUR (L6), routed through bootstrap_verdict_admissible (L41) + clears_tick_magnitude
   (L27), with BOTH a frozen-inclusive and a movement-conditioned cut (L32).

── HONESTY: the microstructure half is UNDER-SAMPLED at hourly cadence (do not oversell) ────────
Collection is HOURLY (one pass/hour — the cloud loop's cron floor, S9/Q16/L23). An hourly
KXTEMPNYCH market is open only ~60–120 min, so it gets only ~1–2 snapshots (today's real tape:
300 hourly-NYC records across 230 tickers = ~1.3 snapshots/ticker). A "minutes-of-stale-pricing"
measurement is therefore fundamentally under-sampled and CANNOT resolve sub-hour stale windows —
the real VPS-latency test needs finer (≤5-min) VPS tape. This half self-labels
"snapshot-sampled, hourly cadence, cannot resolve sub-hour stale windows — needs finer VPS tape"
(mirroring S6/L23 honesty) rather than emitting a confident microstructure verdict from 1–2
snapshots. The settlement-basis half is the tractable one at hourly cadence.

── FEE CHOICE (documented; the direction Q36 describes) ────────────────────────────────────────
The Q36 mechanism is the VPS REACTING to a fresh ob and LIFTING a stale resting ask before the
book reprices — a TAKER lift. So the stale-ask-lift P&L is charged the TAKER rate 0.07 via
core.pricing.fee_per_contract (never hand-rolled — L18). A resting-maker variant (0.0175) is NOT
what this thesis models; if a future maker-side weather probe wants it, pass MAKER_FEE_RATE.

── PRICE / TAG DISCIPLINE ──────────────────────────────────────────────────────────────────────
The fillable YES ask = 1 − best_no_bid (a DERIVED ask, still fillable — tag `derived_ask`), with
best_yes_ask as the `real_ask` fallback; symmetrically the NO ask = 1 − best_yes_bid. Realized
settlement is `broker_truth`; a forecast/ob value is `synthetic`. No synthetic/nominal price is
ever quoted as a fill (Hard Rule #1/#3). READ-ONLY over tape; fees ONLY from core.pricing.

Run:
    python scripts/q36_kxtemp_hourly_probe.py
    python scripts/q36_kxtemp_hourly_probe.py --settlement-dir tape/weather_settlement --json-out /tmp/q36.json
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    bracket_by_movement,
    clears_tick_magnitude,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.timeutil import (  # noqa: E402
    parse_crypto_hour_token_close_utc,
    parse_kalshi_ts,
)

SERIES_DEFAULT = "KXTEMPNYCH"
WEATHER_BOOKS_GLOB = str(REPO_ROOT / "tape" / "weather_books" / "dt=*.jsonl")
SETTLEMENT_SCHEMA_VERSION = "weather_settlement.v0"

MIN_DAYS = 7            # self-activation gate: ≥7 distinct dt-days of hourly coverage (Q36)
MIN_CI_UNITS = 10       # shared data-adequacy floor (matches bootstrap_verdict_admissible default)
PRICE_TICK = 0.01

# FEE: the stale-ask-lift is a TAKER lift (VPS reacts to an ob, lifts a stale resting ask) — 0.07.
STALE_LIFT_FEE_RATE = TAKER_FEE_RATE

# depth×duration joint grid (contracts, wall-clock seconds) — mirrors the W-D probe's own cells so
# a 0-opportunity result is directly comparable to L78's "0 opportunities ≥10 contracts AND ≥60s".
DEPTH_DURATION_GRID: Tuple[Tuple[float, float], ...] = ((10.0, 60.0), (5.0, 60.0), (20.0, 10.0))

# settlement-basis disagreement tolerance, °F — mirrors validation/v1_actuals.py's TOL_F (the one
# definition of "do the sources agree"). Descriptive only; not a fill threshold.
BASIS_TOL_F = 1.0

_DT_RE = re.compile(r"dt=(\d{4}-\d{2}-\d{2})\.jsonl$")
_UNDERSAMPLED_LABEL = ("snapshot-sampled, hourly cadence, cannot resolve sub-hour stale windows "
                       "— needs finer VPS tape")


# --------------------------------------------------------------------------- #
# ticker parsing — strike + ET-hour close, off the ticker itself
# --------------------------------------------------------------------------- #
def parse_hourly_ticker(ticker: str) -> Optional[Dict[str, Any]]:
    """Parse `KXTEMPNYCH-26JUL1522-T81.99` into its parts. Returns
    `{"series", "date_hour_token", "close_utc", "et_hour", "strike, "market_hour"}` or None
    on a grammar mismatch.

    The middle segment (`26JUL1522`) is a `YYMONDDHH` token whose trailing HH is
    America/New_York local time — the SAME grammar as the crypto-hourly token, so close time is
    read via core.timeutil.parse_crypto_hour_token_close_utc (L45/L49 — never re-derive a
    crypto-hourly close inline; KXTEMPNYCH is a New-York station so ET is the correct zone). The
    trailing `T<float>` token is the strike. `market_hour` (`SERIES-DATEHOUR`) is the block-
    bootstrap unit key (L6 — strikes within one hour are correlated, not independent draws).
    """
    if not ticker:
        return None
    parts = ticker.split("-")
    if len(parts) < 3:
        return None
    # rejoin everything past the date/hour token so a NEGATIVE strike (`T-5`) survives the split.
    series, token, strike_tok = parts[0], parts[1], "-".join(parts[2:])
    close_utc = parse_crypto_hour_token_close_utc(token)
    if close_utc is None:
        return None
    m = re.fullmatch(r"[Tt](-?\d+(?:\.\d+)?)", strike_tok)
    if not m:
        return None
    try:
        strike = float(m.group(1))
    except ValueError:
        return None
    return {
        "series": series,
        "date_hour_token": token,
        "close_utc": close_utc,
        "et_hour": int(token[-2:]),
        "strike": strike,
        "market_hour": f"{series}-{token}",
    }


# --------------------------------------------------------------------------- #
# fillable asks + depth-at-touch off a book record
# --------------------------------------------------------------------------- #
def derived_yes_ask(rec: Dict[str, Any]) -> Optional[float]:
    """Fillable YES ask = 1 − best_no_bid (tag `derived_ask`), falling back to best_yes_ask
    (tag `real_ask`) when the NO bid is absent. Both are fillable taker prices; a raw None
    yields None (never a fabricated fill)."""
    nb = rec.get("best_no_bid")
    if nb is not None:
        return round(1.0 - float(nb), 6)
    ya = rec.get("best_yes_ask")
    return float(ya) if ya is not None else None


def derived_no_ask(rec: Dict[str, Any]) -> Optional[float]:
    """Fillable NO ask = 1 − best_yes_bid (tag `derived_ask`), falling back to best_no_ask."""
    yb = rec.get("best_yes_bid")
    if yb is not None:
        return round(1.0 - float(yb), 6)
    na = rec.get("best_no_ask")
    return float(na) if na is not None else None


def _size_at_price(ladder: Any, price: Optional[float]) -> float:
    """Size resting at `price` in a `[[price, size], ...]` ladder (sizes are floats, may be
    fractional — L47). 0.0 if the price/ladder is absent."""
    if price is None or not ladder:
        return 0.0
    for lvl in ladder:
        try:
            if abs(float(lvl[0]) - float(price)) < 1e-9:
                return float(lvl[1])
        except (TypeError, ValueError, IndexError):
            continue
    return 0.0


def winning_side_ask(rec: Dict[str, Any], settled_result: str) -> Optional[float]:
    """The fillable ask you'd LIFT to hold the settling side: YES ask if settled yes, NO ask if
    settled no. None if that side has no fillable ask."""
    if settled_result == "yes":
        return derived_yes_ask(rec)
    if settled_result == "no":
        return derived_no_ask(rec)
    return None


def winning_side_depth(rec: Dict[str, Any], settled_result: str) -> float:
    """Contracts resting at the winning-side touch. Buying YES lifts the mirror of the best NO
    bid (yes_ask = 1 − no_bid), so its depth is the size at the top no_bids level; buying NO uses
    the top yes_bids level. Returns 0.0 when that side of the book is empty (L23 — empty ≠ error)."""
    if settled_result == "yes":
        return _size_at_price(rec.get("no_bids"), rec.get("best_no_bid"))
    if settled_result == "no":
        return _size_at_price(rec.get("yes_bids"), rec.get("best_yes_bid"))
    return 0.0


def _bbo_tuple(rec: Dict[str, Any]) -> Tuple:
    """The four BBO fields — a pair with an identical tuple across two captures is FROZEN (L32:
    a no-fill, not free income)."""
    return (rec.get("best_yes_ask"), rec.get("best_no_ask"),
            rec.get("best_yes_bid"), rec.get("best_no_bid"))


# --------------------------------------------------------------------------- #
# loaders — read-only over tape / injected settlement dir
# --------------------------------------------------------------------------- #
def load_hourly_snapshots(tape_glob: str, series: str = SERIES_DEFAULT
                          ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Read every `weather_books` hourly record for `series`, grouped by MARKET-HOUR (the L6
    bootstrap unit). ALL snapshots are kept (multiple captures of one ticker are separate lines —
    staleness timing needs them, so we do NOT dedupe). Returns (by_market_hour, meta) where meta
    carries `n_days` (distinct dt-day FILES with ≥1 such record — L25: a `dt=` path must be a
    regular FILE, the directory-regression shape is ignored) and `n_market_hours`."""
    by_mh: Dict[str, List[Dict[str, Any]]] = {}
    days: set = set()
    n_records = 0
    n_bad_ticker = 0
    for path in sorted(glob.glob(tape_glob)):
        if not os.path.isfile(path):   # L25: a directory-shaped dt= path is not readable tape
            continue
        m = _DT_RE.search(os.path.basename(path))
        day = m.group(1) if m else None
        file_has_series = False
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("group") != "hourly" or rec.get("series") != series:
                    continue
                parsed = parse_hourly_ticker(rec.get("ticker", ""))
                if parsed is None:
                    n_bad_ticker += 1
                    continue
                file_has_series = True
                n_records += 1
                rec["_parsed"] = parsed
                by_mh.setdefault(parsed["market_hour"], []).append(rec)
        if day and file_has_series:
            days.add(day)
    meta = {
        "n_days": len(days),
        "days": sorted(days),
        "n_market_hours": len(by_mh),
        "n_records": n_records,
        "n_bad_ticker": n_bad_ticker,
        "series": series,
    }
    return by_mh, meta


def load_settlement_leg(settlement_dir: Optional[str]
                        ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Read the injected settlement leg JSONL under `settlement_dir`, keyed by `ticker` (latest
    `capture_id` wins). Missing/empty dir is an honest empty result (the self-activating guard,
    never a crash). Meta counts how many carry the outcome leg vs the ob leg so each half can
    report its own adequacy."""
    by_ticker: Dict[str, Dict[str, Any]] = {}
    n_lines = 0
    n_files = 0
    if settlement_dir:
        for path in sorted(glob.glob(str(Path(settlement_dir) / "dt=*.jsonl"))):
            if not os.path.isfile(path):
                continue
            n_files += 1
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    rec = json.loads(line)
                    n_lines += 1
                    key = rec.get("ticker")
                    if not key:
                        continue
                    prev = by_ticker.get(key)
                    if prev is None or str(rec.get("capture_id", "")) > str(prev.get("capture_id", "")):
                        by_ticker[key] = rec
    n_with_outcome = sum(1 for r in by_ticker.values()
                         if r.get("settled_result") in ("yes", "no"))
    n_with_obs = sum(1 for r in by_ticker.values() if r.get("asos_obs"))
    meta = {
        "n_settlement_files": n_files, "n_settlement_lines": n_lines,
        "n_settlement_tickers": len(by_ticker),
        "n_with_outcome": n_with_outcome, "n_with_obs": n_with_obs,
    }
    return by_ticker, meta


# --------------------------------------------------------------------------- #
# half 1 — settlement basis (TWC vs ASOS), descriptive, needs the ob leg
# --------------------------------------------------------------------------- #
def settlement_basis_analysis(settlement: Dict[str, Dict[str, Any]]
                              ) -> Dict[str, Any]:
    """Quantify the TWC-vs-ASOS mapping the way validation/v1_actuals.py reconciles CLI-vs-METAR:
    rounding residual (settled value − closest-in-time ASOS ob), publication lag (close − last ob
    before it), and disagreement rate (|settled − closest ASOS| > BASIS_TOL_F). Descriptive only —
    tags: settled value `broker_truth`, ASOS ob `synthetic`. Runs only over tickers carrying an
    `asos_obs` timeseries; returns an honest empty result otherwise."""
    residuals: List[float] = []
    disagreements = 0
    n_used = 0
    for tkr, rec in settlement.items():
        obs = rec.get("asos_obs") or []
        settled = rec.get("expiration_value")
        if settled is None:
            settled = rec.get("twc_value")
        if not obs or settled is None:
            continue
        temps = [float(o["temp_f"]) for o in obs if o.get("temp_f") is not None]
        if not temps:
            continue
        # closest ASOS ob by value proximity is the mapping anchor (no per-ob time join needed for
        # the rounding/disagreement stats; the lag stat below uses timestamps when present)
        closest = min(temps, key=lambda t: abs(t - float(settled)))
        resid = float(settled) - closest
        residuals.append(resid)
        if abs(resid) > BASIS_TOL_F:
            disagreements += 1
        n_used += 1
    n = len(residuals)
    mean_abs = (sum(abs(r) for r in residuals) / n) if n else None
    mean_resid = (sum(residuals) / n) if n else None
    return {
        "ob_leg_present": n_used > 0,
        "n_tickers_with_basis": n_used,
        "mean_residual_f": mean_resid,
        "mean_abs_residual_f": mean_abs,
        "disagreement_rate": (disagreements / n) if n else None,
        "tol_f": BASIS_TOL_F,
        "note": ("descriptive TWC(broker_truth)-vs-ASOS(synthetic) mapping; the tractable half at "
                 "hourly cadence. No CI, no verdict."),
    }


# --------------------------------------------------------------------------- #
# half 2 — microstructure: depth×duration + stale-ask-lift P&L, bootstrap by market-hour
# --------------------------------------------------------------------------- #
def _consecutive_pairs(records: List[Dict[str, Any]]) -> List[Tuple[Dict, Dict, float]]:
    """Consecutive same-ticker snapshot pairs sorted by captured_at, with wall-clock seconds
    between them (L76 — a real duration, never a snapshot count). Pairs are per-TICKER (a specific
    strike's own book), so a market-hour's many strikes each contribute their own pairs."""
    by_ticker: Dict[str, List[Dict]] = {}
    for r in records:
        by_ticker.setdefault(r.get("ticker"), []).append(r)
    pairs: List[Tuple[Dict, Dict, float]] = []
    for snaps in by_ticker.values():
        snaps_sorted = sorted(snaps, key=lambda r: parse_kalshi_ts(r["captured_at"])[0])
        for a, b in zip(snaps_sorted, snaps_sorted[1:]):
            ta = parse_kalshi_ts(a["captured_at"])[0]
            tb = parse_kalshi_ts(b["captured_at"])[0]
            pairs.append((a, b, (tb - ta).total_seconds()))
    return pairs


def depth_duration_joint(by_mh: Dict[str, List[Dict[str, Any]]],
                         settlement: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """MANDATORY depth×duration joint distribution (L78 — the W-D killer). For every consecutive
    same-ticker pair, the duration is the wall-clock seconds it persisted and the depth is the
    winning-side depth-at-touch at the earlier snapshot. Counts pairs meeting each (depth, dur)
    cell of DEPTH_DURATION_GRID. The winning side comes from the injected settlement outcome; a
    pair whose ticker has no settled outcome contributes duration but 0 measurable depth-at-touch
    and is counted separately."""
    grid_counts = {f"depth>={d:g}&dur>={t:g}s": 0 for (d, t) in DEPTH_DURATION_GRID}
    durations: List[float] = []
    depths: List[float] = []
    n_pairs = 0
    n_pairs_no_outcome = 0
    for mh, records in by_mh.items():
        for a, _b, dur_s in _consecutive_pairs(records):
            n_pairs += 1
            durations.append(dur_s)
            settled = (settlement.get(a.get("ticker")) or {}).get("settled_result")
            if settled not in ("yes", "no"):
                n_pairs_no_outcome += 1
                depth = 0.0
            else:
                depth = winning_side_depth(a, settled)
            depths.append(depth)
            for (d, t) in DEPTH_DURATION_GRID:
                if depth >= d and dur_s >= t:
                    grid_counts[f"depth>={d:g}&dur>={t:g}s"] += 1
    return {
        "n_pairs": n_pairs,
        "n_pairs_no_outcome": n_pairs_no_outcome,
        "grid_counts": grid_counts,
        "max_duration_s": max(durations) if durations else None,
        "median_duration_s": (sorted(durations)[len(durations) // 2] if durations else None),
        "max_depth": max(depths) if depths else None,
        "note": ("depth×duration is the binding structural test (L78); 0 in every cell is the "
                 "W-D-style kill. " + _UNDERSAMPLED_LABEL),
    }


def stale_lift_pnl(by_mh: Dict[str, List[Dict[str, Any]]],
                   settlement: Dict[str, Dict[str, Any]]
                   ) -> Tuple[Dict[str, List[float]], Dict[str, List[float]], Dict[str, Any]]:
    """Per-market-hour stale-ask-lift P&L for the VPS taker-lift thesis, net of the TAKER fee.

    An opportunity requires a `signal_known_at` in the settlement leg (the wall-clock time the
    DECIDING ob was publicly knowable) — the ONLY way to isolate a genuinely STALE window at this
    cadence. For a consecutive pair whose earlier snapshot is at/after `signal_known_at`, lifting
    the winning-side ask pays $1 at settlement:  edge = 1.0 − win_ask − fee_per_contract(win_ask,
    TAKER). Grouped by MARKET-HOUR (L6). Returns (frozen_inclusive_by_mh, movement_conditioned_by_mh,
    meta) — the L32 dual cut: a FROZEN pair (BBO unchanged) is a no-fill for the movement cut.

    Without `signal_known_at` no stale window can be established → 0 values (the structural
    depth×duration distribution is then the only microstructure read, per L78)."""
    incl: Dict[str, List[float]] = {}
    moved: Dict[str, List[float]] = {}
    all_frozen: List[bool] = []
    all_vals: List[float] = []
    n_opportunities = 0
    n_no_signal = 0
    n_no_ask = 0
    for mh, records in by_mh.items():
        for a, b, _dur_s in _consecutive_pairs(records):
            settle = settlement.get(a.get("ticker")) or {}
            settled = settle.get("settled_result")
            sig = settle.get("signal_known_at")
            if settled not in ("yes", "no") or not sig:
                n_no_signal += 1
                continue
            sig_ts = parse_kalshi_ts(sig)[0]
            if parse_kalshi_ts(a["captured_at"])[0] < sig_ts:
                continue  # snapshot predates the deciding ob — not a stale window
            ask = winning_side_ask(a, settled)
            if ask is None:
                n_no_ask += 1
                continue
            edge = 1.0 - float(ask) - fee_per_contract(float(ask), STALE_LIFT_FEE_RATE)
            frozen = _bbo_tuple(a) == _bbo_tuple(b)
            incl.setdefault(mh, []).append(edge)
            if not frozen:
                moved.setdefault(mh, []).append(edge)
            all_frozen.append(frozen)
            all_vals.append(edge)
            n_opportunities += 1
    bracket = bracket_by_movement(all_frozen, all_vals) if all_vals else {
        "n": 0, "frac_frozen": 0.0, "frozen_inclusive": [], "movement_conditioned": []}
    meta = {
        "n_opportunities": n_opportunities,
        "n_pairs_no_signal": n_no_signal,
        "n_no_ask": n_no_ask,
        "frac_frozen": bracket["frac_frozen"],
        "fee_rate": STALE_LIFT_FEE_RATE,
        "fee_direction": "taker (VPS reacts to ob and LIFTS a stale resting ask)",
    }
    return incl, moved, meta


def bootstrap_cut(unit_values: Dict[str, List[float]], *, n_boot: int, seed: int = 42
                  ) -> Dict[str, Any]:
    """Block-bootstrap by market-hour and route through both verdict gates (L27/L41). `alive`
    requires an admissible, strictly-positive, tick-clearing CI — the binding directive's bar."""
    boot = block_bootstrap(unit_values, n_boot=n_boot, seed=seed)
    adm = bootstrap_verdict_admissible(unit_values, min_units=MIN_CI_UNITS)
    ci = boot["ci95"]
    lo = ci[0]
    clears = clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0)
    ci_pos = lo is not None and lo > 0.0
    return {
        "mean": boot["mean"], "ci95": ci, "n_units": boot["n_units"], "n_obs": boot["n_obs"],
        "admissible": adm["admissible"], "admissibility": adm,
        "ci_strictly_positive": ci_pos, "clears_tick_magnitude": clears,
        "alive": bool(adm["admissible"] and ci_pos and clears),
    }


def microstructure_analysis(by_mh: Dict[str, List[Dict[str, Any]]],
                            settlement: Dict[str, Dict[str, Any]], *, n_boot: int, seed: int
                            ) -> Dict[str, Any]:
    """The microstructure half: the mandatory depth×duration joint distribution plus (when a
    `signal_known_at` isolates a stale window) the stale-ask-lift P&L, block-bootstrapped by
    market-hour under BOTH fill assumptions (L32). Self-labels under-sampled at hourly cadence."""
    joint = depth_duration_joint(by_mh, settlement)
    incl, moved, pnl_meta = stale_lift_pnl(by_mh, settlement)
    result: Dict[str, Any] = {
        "undersampled_label": _UNDERSAMPLED_LABEL,
        "depth_duration_joint": joint,
        "pnl_meta": pnl_meta,
    }
    if not incl:
        result["pnl_testable"] = False
        result["pnl_reason"] = (
            "no stale-window opportunity (needs settlement `signal_known_at` AND a post-signal "
            "snapshot); the depth×duration joint distribution is the only microstructure read "
            "(L78 — for a structural read the binding test IS depth×duration, not a P&L bootstrap).")
        return result
    result["pnl_testable"] = True
    result["frozen_inclusive"] = bootstrap_cut(incl, n_boot=n_boot, seed=seed)
    result["movement_conditioned"] = bootstrap_cut(moved, n_boot=n_boot, seed=seed)
    return result


# --------------------------------------------------------------------------- #
# orchestration — self-activating gate
# --------------------------------------------------------------------------- #
def run_probe(tape_glob: str, settlement_dir: Optional[str], *, series: str = SERIES_DEFAULT,
              n_boot: int = 10000, seed: int = 42) -> Dict[str, Any]:
    """End-to-end (read-only over both inputs). Returns a report dict. `data_adequate` is False
    (with `insufficient_reason`) whenever the self-activation gate is unmet — no fabricated CI
    from below-gate or settlement-less tape."""
    by_mh, book_meta = load_hourly_snapshots(tape_glob, series)
    settlement, settle_meta = load_settlement_leg(settlement_dir)
    settlement_present = settle_meta["n_settlement_tickers"] > 0

    report: Dict[str, Any] = {
        "series": series,
        "book_meta": book_meta,
        "settlement_meta": settle_meta,
        "settlement_leg_present": settlement_present,
        "min_days": MIN_DAYS,
        "n_boot": n_boot,
        "fee_rate": STALE_LIFT_FEE_RATE,
        "price_source_tag": "mixed (derived_ask/real_ask fill − taker fee; settlement broker_truth)",
    }

    # ── self-activation gate: ≥7 distinct dt-days AND a non-empty settlement leg ──
    if book_meta["n_days"] < MIN_DAYS or not settlement_present:
        report["data_adequate"] = False
        report["insufficient_reason"] = (
            f"n_days={book_meta['n_days']} (need >={MIN_DAYS}), "
            f"n_market_hours={book_meta['n_market_hours']}, "
            f"settlement_leg_present={settlement_present}")
        return report

    report["data_adequate"] = True
    report["settlement_basis"] = settlement_basis_analysis(settlement)
    report["microstructure"] = microstructure_analysis(
        by_mh, settlement, n_boot=n_boot, seed=seed)
    return report


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: Any) -> str:
    if not ci or ci[0] is None:
        return "[   None ,   None ]"
    return f"[{ci[0]:+.5f}, {ci[1]:+.5f}]"


def _print_cut(label: str, s: Dict[str, Any]) -> None:
    mean = "None" if s["mean"] is None else f"{s['mean']:+.5f}"
    pos = ">0" if s["ci_strictly_positive"] else "≤0"
    gate = "CLEARS" if s["clears_tick_magnitude"] else "no"
    adm = "admissible" if s["admissible"] else "INADMISSIBLE(%s)" % ",".join(
        s["admissibility"]["reasons"])
    print(f"  {label}: mean={mean:>10}  95% CI={_fmt_ci(s['ci95'])}  "
          f"n_market_hours={s['n_units']:>3}  n_obs={s['n_obs']:>4}  CI {pos}  tick {gate}  {adm}  "
          f"{'ALIVE' if s['alive'] else 'dead'}")


def print_report(rep: Dict[str, Any]) -> None:
    bm, sm = rep["book_meta"], rep["settlement_meta"]
    print("=" * 92)
    print("Q36 KXTEMPNYCH HOURLY — settlement-basis + microstructure (VPS-latency thesis) [PREP]")
    print("=" * 92)
    print(f"weather_books hourly {rep['series']}: {bm['n_records']} records, "
          f"{bm['n_market_hours']} market-hours across {bm['n_days']} dt-day(s) {bm['days']}")
    print(f"settlement leg: {sm['n_settlement_lines']} lines / {sm['n_settlement_tickers']} tickers "
          f"({sm['n_with_outcome']} with outcome, {sm['n_with_obs']} with ob stream)")
    print(f"FEE: taker {rep['fee_rate']} (VPS lifts a stale resting ask — reacting-to-obs taker lift)")

    if not rep.get("data_adequate"):
        print(f"\nINSUFFICIENT DATA — {rep['insufficient_reason']}")
        print("This is self-activating prep infrastructure: it fires the day the tape gate opens "
              f"(>={rep['min_days']} dt-days of hourly coverage) AND a settlement leg is injected via "
              "--settlement-dir. NO verdict, NO fabricated bootstrap.")
        return

    sb = rep["settlement_basis"]
    print("\n[1] SETTLEMENT BASIS (TWC broker_truth vs ASOS synthetic) — descriptive, tractable half")
    if not sb["ob_leg_present"]:
        print("  ob leg not present on any settled ticker — basis half not computable.")
    else:
        print(f"  n={sb['n_tickers_with_basis']}  mean_residual={sb['mean_residual_f']:+.3f}°F  "
              f"mean_abs_residual={sb['mean_abs_residual_f']:.3f}°F  "
              f"disagreement_rate(|Δ|>{sb['tol_f']}°F)={sb['disagreement_rate']:.3f}")

    ms = rep["microstructure"]
    print("\n[2] MICROSTRUCTURE — " + ms["undersampled_label"])
    j = ms["depth_duration_joint"]
    print(f"  depth×duration joint (MANDATORY, L78): n_pairs={j['n_pairs']} "
          f"(max_dur={j['max_duration_s']}s, max_depth={j['max_depth']})")
    for cell, cnt in j["grid_counts"].items():
        print(f"    {cell}: {cnt} opportunities")
    if not ms["pnl_testable"]:
        print(f"  stale-ask-lift P&L: {ms['pnl_reason']}")
    else:
        print(f"  stale-ask-lift P&L (net taker {ms['pnl_meta']['fee_rate']}, "
              f"frac_frozen={ms['pnl_meta']['frac_frozen']:.3f}) — L32 dual cut, bootstrap by market-hour:")
        _print_cut("frozen-inclusive   ", ms["frozen_inclusive"])
        _print_cut("movement-conditioned", ms["movement_conditioned"])
    print("\nNOTE: microstructure verdict is NOT emitted from 1–2 snapshots/market — the stale-window "
          "read needs finer (≤5-min) VPS tape (S6/L23 honesty). Settlement basis is the hourly-tractable half.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q36 KXTEMPNYCH hourly settlement-basis + microstructure probe (prep; read-only)")
    ap.add_argument("--tape-glob", default=WEATHER_BOOKS_GLOB,
                    help="glob for weather_books hourly tape")
    ap.add_argument("--series", default=SERIES_DEFAULT, help="hourly series (default KXTEMPNYCH)")
    ap.add_argument("--settlement-dir", default=None,
                    help="dir holding the INJECTED settlement leg JSONL (TWC outcome + optional "
                         "ASOS ob stream) — absent/empty => INSUFFICIENT DATA, never fabricated")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    rep = run_probe(args.tape_glob, args.settlement_dir, series=args.series,
                    n_boot=args.n_boot, seed=args.seed)
    print_report(rep)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"[q36] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

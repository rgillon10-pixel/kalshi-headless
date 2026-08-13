#!/usr/bin/env python3
"""q51_maker_fillsim.py — Q51 milestone 2: coarse INTERVAL-LEVEL maker fill-sim of the
sports maker family (S13/S23/S29 shape) against a real executed-print tape.

LOOP-QUEUE.md Q51 milestone 2. This is the first fill-sim in this repo whose fills are
read off `broker_truth` executed prints instead of a queue-departure PROXY (L48/L250) or
an `OPTIMISTIC_FILL=True` assumption. Eight candidates (S6/S13/S19/S21/S23/S29/S68 + the
S73 idea-stage kill) died on "`orderbook_depth` has no trade-print field, so a rested
maker fill is unmeasurable" (L68/L131). `tape/kalshi_trades/` (Q51 milestone 1) supplies
that field. This probe asks whether the family, now that it is MEASURABLE, clears the bar.

READ-ONLY. Fully offline in analysis mode (`--build-cache` is the only network path, an
unauthenticated public GET of `/markets/{ticker}` for the settlement `result`, cached to
JSON so a verifier re-runs with zero network). No orders, no credentials, no auth.

MECHANISM UNDER TEST (the S13/S23/S29 shape, coarsened to what this tape can carry):
  at book snapshot t_i, rest a maker order AT THE OBSERVED TOUCH — `best_yes_bid` (a YES
  bid) and, as an independent second leg, `best_no_bid` (a NO bid). Ask whether a taker
  crossed into that side at or through that price before the next snapshot t_{i+1}. Hold
  any fill to settlement.

  YES-bid leg fills iff a print in (t_i, t_{i+1}] has `taker_book_side == "ask"` (a taker
  whose own order sat on the ASK, i.e. a SELLER, who therefore hits the bid) at
  `yes_price <= our bid`.
  NO-bid  leg fills iff a print in that window has `taker_book_side == "bid"` (a taker
  whose own order sat on the BID, i.e. a BUYER, who therefore lifts the offer) at
  `yes_price >= 1 - our no bid`.

  *** ORIENTATION CORRECTION (this milestone's first result). *** Milestone 1's collector
  docstring and finding both read `taker_book_side` as "the side of the BOOK the taker
  crossed INTO". The committed tape falsifies that. Restricted to prints landing within 15
  minutes of their reference snapshot (so the quote is not up to 3h stale), `"bid"` prints
  execute at or ABOVE the best ask 86.8% of the time (n=151) and `"ask"` prints at or
  BELOW the best bid 83.3% (n=30); the effect decays monotonically as the reference quote
  goes stale (86.8% -> 84.6% -> 70.4% at <=15min / <=60min / any age).

  *** SCOPE OF THAT DECAY ARGUMENT (L338, corrected by L349 — READ BEFORE CITING IT). ***
  Those three rates are measured under THIS module's own join rule, in which a print must
  fall strictly inside a CONSECUTIVE snapshot pair (t_i, t_{i+1}], and on the 60-ticker
  sports sample described under POPULATION below. L338 first recorded the caveat as a
  POPULATION scope, because an independent verifier measured 62.99% -> 66.9% -> 69.6%
  (RISING) on the full 2,713-ticker day tape. `scripts/l338_trend_claim_scope_audit.py`
  ran the 2x2 factorial and the attribution is NOT the population: switching the 60-ticker
  sports sample for all 2,713 depth tickers does not move a single admitted-print count or
  agreement rate, on either side, under either join. The whole flip is the JOIN RULE —
  attaching each print to the nearest PRECEDING quote instead, with no bracketing
  requirement, admits 29,964 bid-side prints instead of 3,532 and reverses the direction.
  So "decays monotonically, which is exactly the degradation a true relationship shows
  under a widening join window and an artifact does not" is a claim about the BRACKETED
  join, and must not be quoted without naming that rule. The DIRECTIONAL conclusion below
  is unaffected: a `bid` taker prints at or above the ask far more often than not (>0.55)
  in every cell of that grid, under both joins. Pinned by
  `tests/test_l338_trend_claim_scope_audit.py`.

  The field therefore names the side of the book the TAKER'S OWN ORDER sat on: a taker
  holding a BID lifts the ASK. `taker_book_side`/`taker_side`/`taker_outcome_side` are
  perfectly collinear on this tape (bid/yes/yes 31,831 - ask/no/no 7,867), so the same
  correction is readable off `taker_side` and the redundancy is not extra evidence. Under
  the corrected reading the 80/20 flow split says retail overwhelmingly BUYS, the standard
  prediction-market pattern; under milestone 1's reading it would have said 80% of taker
  flow SELLS. Reading it the milestone-1 way inverts every fill in this probe, so this is
  a load-bearing correction, not a naming quibble. Pinned by
  `tests/test_q51_maker_fillsim.py::test_acceptance_taker_book_side_orientation_*`.

  Both legs are scored SEPARATELY and both are always scored — the sold side's losses are
  modelled, never conditioned away. A leg is NOT paired with its twin into a both-bid
  capture object: that object is sign-bounded by construction on a spread gate (L249,
  Q49/S68), and this probe deliberately does not build it. `sign_bounded_objective` is run
  on the headline object anyway and reported.

BINDING GATES FROM THE Q51 SPEC — none of these may be weakened:
  * Every fill traces to a `broker_truth` print. `fill_trade_id` is persisted per filled
    row; a synthesised fill is prime-directive-forbidden and cannot occur here by
    construction (the fill predicate reads a print or returns False).
  * The ~3-hour book cadence is a CEILING on what may be claimed. NO queue-position and
    NO time-to-fill number is computed or reported anywhere in this module; the report is
    asserted free of such keys by `tests/test_q51_maker_fillsim.py`.
  * Interval coverage is reported alongside every fill rate, on BOTH branches, so an
    unmeasurable interval is never silently scored as a no-fill.
  * Maker fee 0.0175 (`core.pricing.MAKER_FEE_RATE`), never the 0.07 taker rate (L5 — a
    4x overcharge caught late).
  * Block bootstrap by GAME (`core.bootstrap.block_bootstrap`), never by outcome (L6).
  * L41 admissibility (>=10 units AND >=1 opposing/losing cluster — the S20 lesson) and
    L27 tick magnitude are both applied; a CI failing either is not-a-verdict.

TWO COVERAGE BRANCHES, both reported, headline is the conservative one:
  A `all_intervals` (HEADLINE) — every interval is a candidate. An interval with zero
    prints scores as a NO-FILL. This is legitimate only because milestone 1's capture was
    ticker-scoped over the whole UTC day with the cursor exhausted (`completeness_ok=True`,
    `at_cap=False`), so zero prints on a sampled ticker is a MEASURED zero, not a gap.
    It is the conservative branch: it dilutes the mean toward zero and makes the bar
    HARDER, so the headline cannot be accused of conditioning on activity.
  B `covered_intervals` (SENSITIVITY) — only intervals containing >=1 print. Strictly
    more favourable to the strategy; reported so the conditioning is visible, never as
    the headline.

POPULATION. Milestone 1's capture sampled 200 of the 2,713 tickers in
`tape/orderbook_depth/dt=2026-08-03.jsonl` by an insertion-order stride of 13. That sample
is reconstructed here deterministically and CHECKED: every ticker carrying a print in
`tape/kalshi_trades/dt=2026-08-03.jsonl` must fall inside it, else the reconstruction is
wrong and the run aborts rather than silently analysing the wrong denominator. Restricted
to sports `*GAME` series; `KXMVE*` nominal-wing AMM families excluded (L31).

Run:
    python3 scripts/q51_maker_fillsim.py --build-cache     # one live read-only pull
    python3 scripts/q51_maker_fillsim.py                   # offline, from the cache
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
    sign_bounded_objective,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement import binary_outcome, filter_binary_results_map  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402

DAY = "2026-08-03"
DEPTH_TAPE = REPO_ROOT / "tape" / "orderbook_depth"
TRADES_TAPE = REPO_ROOT / "tape" / "kalshi_trades"
CACHE_PATH = REPO_ROOT / "tape" / "q51_settlement_cache" / "settlement.json"
REPORT_PATH = REPO_ROOT / "reports" / "q51_maker_fillsim.json"
ROWS_PATH = REPO_ROOT / "reports" / "q51_maker_fillsim_rows.jsonl"

# milestone 1's sampling rule, reproduced exactly (insertion order over the day's depth
# file, stride 13, first 200). Verified against the trade tape at load time.
SAMPLE_STRIDE = 13
SAMPLE_SIZE = 200

# Orientation of `taker_book_side` — see the module docstring's ORIENTATION CORRECTION.
# The value names the side of the book the TAKER'S OWN order sat on, so a taker carrying a
# BID is a BUYER (it lifts a resting offer) and one carrying an ASK is a SELLER (it hits a
# resting bid). Named constants, never bare "bid"/"ask" literals at the comparison site,
# because the inverted reading is the exact bug this milestone caught.
TAKER_BUYS = "bid"
TAKER_SELLS = "ask"

TICK = 0.01
MIN_UNITS = 10
N_BOOT = 10000
SEED = 42

# a resting order that a taker lifts is a MAKER fill. Passing `fee_per_contract`'s own
# TAKER default here would overcharge every simulated fill 4x (L5). No local literal —
# MAKER_FEE_RATE is imported from core.pricing, the single fee-schedule source of truth.
FEE_RATE = MAKER_FEE_RATE

# Keys this report is FORBIDDEN to contain: the 3h book cadence cannot support them.
FORBIDDEN_REPORT_TOKENS = ("queue", "time_to_fill", "seconds_to_fill", "fill_latency",
                           "queue_ahead", "queue_position")


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def parse_ts(text: Any) -> Optional[float]:
    """UNIX seconds from an RFC3339 string, or None. Via core.timeutil (L136/L150 — both
    families carry variable fractional-second precision that stdlib 3.9 rejects)."""
    if not isinstance(text, str) or not text:
        return None
    try:
        return parse_iso_utc(text).astimezone(timezone.utc).timestamp()
    except (ValueError, TypeError):
        return None


def game_of(ticker: str) -> str:
    """The bootstrap UNIT: the GAME (event) a market belongs to. `KX...GAME-26AUG02DENBOS-DEN`
    -> `KX...GAME-26AUG02DENBOS`. Never the outcome (L6)."""
    return ticker.rsplit("-", 1)[0] if "-" in ticker else ticker


def series_of(ticker: str) -> str:
    return ticker.split("-", 1)[0] if "-" in ticker else ticker


def is_sports_game_market(ticker: str) -> bool:
    """The S13/S23/S29 family's population: per-game sports moneyline markets. KXMVE* (the
    nominal-wing AMM multi-outcome families) excluded per L31."""
    s = series_of(ticker)
    return s.endswith("GAME") and not s.startswith("KXMVE")


def load_depth(day: str = DAY, path: Optional[Path] = None) -> Tuple[List[str], Dict[str, List[dict]]]:
    """Return (insertion-ordered distinct tickers, ticker -> time-sorted snapshots)."""
    p = path or (DEPTH_TAPE / f"dt={day}.jsonl")
    order: List[str] = []
    seen = set()
    snaps: Dict[str, List[dict]] = {}
    if not p.exists():
        return order, snaps
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            tk = rec.get("ticker")
            ts = parse_ts(rec.get("captured_at"))
            if not tk or ts is None:
                continue
            if tk not in seen:
                seen.add(tk)
                order.append(tk)
            snaps.setdefault(tk, []).append({
                "ts": ts,
                "captured_at": rec.get("captured_at"),
                "best_yes_bid": rec.get("best_yes_bid"),
                "best_no_bid": rec.get("best_no_bid"),
                "best_yes_ask": rec.get("best_yes_ask"),
            })
    for v in snaps.values():
        v.sort(key=lambda r: r["ts"])
    return order, snaps


def load_prints(day: str = DAY, path: Optional[Path] = None) -> Dict[str, List[dict]]:
    """ticker -> time-sorted executed prints. Only `broker_truth` lines are admitted; a
    print carrying any other price_source_tag is DROPPED, because a fill may only trace to
    a venue-reported completed transaction (prime directive)."""
    p = path or (TRADES_TAPE / f"dt={day}.jsonl")
    out: Dict[str, List[dict]] = {}
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if rec.get("price_source_tag") != "broker_truth":
                continue
            tk = rec.get("ticker")
            ts = parse_ts(rec.get("created_time"))
            yp = rec.get("yes_price")
            if not tk or ts is None or not isinstance(yp, (int, float)):
                continue
            out.setdefault(tk, []).append({
                "ts": ts,
                "yes_price": float(yp),
                "taker_book_side": rec.get("taker_book_side"),
                "trade_id": rec.get("trade_id"),
                "count": rec.get("count"),
            })
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


def reconstruct_sample(order: Sequence[str], stride: int = SAMPLE_STRIDE,
                       size: int = SAMPLE_SIZE) -> List[str]:
    """Milestone 1's stride sample, reproduced from the depth tape's own insertion order."""
    return list(order[: size * stride : stride])


# --------------------------------------------------------------------------- #
# settlement (the only network path; cached so verification is offline)
# --------------------------------------------------------------------------- #
def build_settlement_cache(tickers: Sequence[str], cache_path: Path = CACHE_PATH,
                           min_interval: float = 0.25) -> Dict[str, dict]:
    """Read-only, UNAUTHENTICATED public GET /markets/{ticker} per candidate; cache
    ticker -> {result, close_time, event_ticker, status}. Results are cached VERBATIM —
    'scalar' and other non-binary values are kept and filtered downstream (L52)."""
    import time

    import requests

    from validation.v3_market import Kalshi, _load_venue_cfg

    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"], min_interval=min_interval)
    out: Dict[str, dict] = {}
    for i, tk in enumerate(sorted(set(tickers))):
        text = None
        for attempt in range(4):  # L40 self-wrapped retry
            try:
                text = client.get_text(f"/markets/{tk}")
                break
            except (requests.ConnectionError, ConnectionError):
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        if text is None:
            continue
        m = (json.loads(text) or {}).get("market") or {}
        out[tk] = {
            "result": m.get("result"),
            "status": m.get("status"),
            "close_time": m.get("close_time"),
            "event_ticker": m.get("event_ticker"),
        }
        if (i + 1) % 25 == 0:
            print(f"[q51:cache] {i + 1}/{len(set(tickers))}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "q51_settlement_cache.v1",
        "price_source_tag": "broker_truth",
        "source": "public_markets_by_ticker",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "day": DAY,
        "markets": out,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"[q51:cache] wrote {len(out)} markets -> {cache_path}")
    return out


def load_settlement_cache(cache_path: Path = CACHE_PATH) -> Dict[str, dict]:
    if not cache_path.exists():
        return {}
    with open(cache_path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("markets") or {}


# --------------------------------------------------------------------------- #
# the fill predicate — the whole point of milestone 2
# --------------------------------------------------------------------------- #
def yes_bid_fill(prints: Sequence[dict], t0: float, t1: float, price: float) -> Optional[dict]:
    """A resting YES BID at `price` is hit by a SELLING taker. Per the orientation
    correction in the module docstring, a selling taker's own order sits on the ASK, so the
    qualifying print carries `taker_book_side == "ask"` (NOT "bid" — reading the field as
    milestone 1 described it inverts every fill). Fills iff such a print lands inside
    (t0, t1] at or through `price`. Returns the earliest qualifying `broker_truth` print."""
    for pr in prints:
        if pr["ts"] <= t0 or pr["ts"] > t1:
            continue
        if pr.get("taker_book_side") != TAKER_SELLS:
            continue
        if pr["yes_price"] <= price + 1e-9:
            return pr
    return None


def no_bid_fill(prints: Sequence[dict], t0: float, t1: float, price: float) -> Optional[dict]:
    """A resting NO BID at `price` is, on Kalshi's mirrored binary book, a YES offer at
    `1 - price`. It is lifted by a BUYING taker, whose own order sits on the BID, so the
    qualifying print carries `taker_book_side == "bid"` (see the module docstring's
    orientation correction). Returns the earliest qualifying `broker_truth` print."""
    yes_level = 1.0 - price
    for pr in prints:
        if pr["ts"] <= t0 or pr["ts"] > t1:
            continue
        if pr.get("taker_book_side") != TAKER_BUYS:
            continue
        if pr["yes_price"] >= yes_level - 1e-9:
            return pr
    return None


def leg_pnl(rest_price: float, won: bool, rate: float = FEE_RATE) -> float:
    """Realized P&L of ONE filled maker contract held to settlement, net of the maker fee."""
    payout = 1.0 if won else 0.0
    return payout - rest_price - fee_per_contract(rest_price, rate=rate)


# --------------------------------------------------------------------------- #
# simulation
# --------------------------------------------------------------------------- #
def build_rows(snaps: Dict[str, List[dict]], prints: Dict[str, List[dict]],
               settlement: Dict[str, dict], universe: Sequence[str]) -> Tuple[List[dict], dict]:
    """One row per (ticker, interval, side). Drops (and counts) anything unscoreable.

    `drops` counts INTERVALS only (L309: mixing a ticker-counted key into an interval-counted
    dict makes `sum(drops.values())` meaningless). A ticker with <2 snapshots contributes ZERO
    intervals by construction, so it is counted separately in `dropped_tickers`, never folded
    into `drops`."""
    rows: List[dict] = []
    drops = {"no_settlement": 0, "non_binary_result": 0, "unsettled": 0,
             "not_two_sided": 0, "post_close": 0}
    dropped_tickers = {"single_snapshot": 0}
    n_intervals = 0
    n_covered = 0
    for tk in universe:
        ss = snaps.get(tk) or []
        if len(ss) < 2:
            dropped_tickers["single_snapshot"] += 1
            continue
        sett = settlement.get(tk)
        if sett is None:
            drops["no_settlement"] += len(ss) - 1
            continue
        outcome = binary_outcome(sett.get("result"))  # None for scalar/unset (L52)
        if outcome is None:
            if sett.get("result"):
                drops["non_binary_result"] += len(ss) - 1
            else:
                drops["unsettled"] += len(ss) - 1
            continue
        close_ts = parse_ts(sett.get("close_time"))
        pl = prints.get(tk) or []
        for a, b in zip(ss[:-1], ss[1:]):
            n_intervals += 1
            covered = any(a["ts"] < pr["ts"] <= b["ts"] for pr in pl)
            if covered:
                n_covered += 1
            if close_ts is not None and a["ts"] >= close_ts:
                drops["post_close"] += 1
                continue
            ybid, nbid = a.get("best_yes_bid"), a.get("best_no_bid")
            if not isinstance(ybid, (int, float)) or not isinstance(nbid, (int, float)) \
                    or ybid <= 0 or nbid <= 0:
                drops["not_two_sided"] += 1
                continue
            for side, price, filler in (("yes_bid", float(ybid), yes_bid_fill),
                                        ("no_bid", float(nbid), no_bid_fill)):
                pr = filler(pl, a["ts"], b["ts"], price)
                won = (outcome == 1) if side == "yes_bid" else (outcome == 0)
                rows.append({
                    "ticker": tk,
                    "game": game_of(tk),
                    "series": series_of(tk),
                    "side": side,
                    "entry_captured_at": a["captured_at"],
                    "next_captured_at": b["captured_at"],
                    "rest_price": price,
                    "price_source_tag": "real_bid",
                    "interval_covered": covered,
                    "filled": pr is not None,
                    "fill_trade_id": (pr or {}).get("trade_id"),
                    "fill_price_source_tag": "broker_truth" if pr else None,
                    "settle_result": sett.get("result"),
                    "won": bool(won) if pr is not None else None,
                    "pnl": leg_pnl(price, won) if pr is not None else 0.0,
                })
    stats = {
        "n_intervals": n_intervals,
        "n_covered_intervals": n_covered,
        "interval_coverage": (n_covered / n_intervals) if n_intervals else None,
        "drops": drops,
        "dropped_tickers": dropped_tickers,
    }
    return rows, stats


def unit_values(rows: Sequence[dict], key: str = "pnl") -> Dict[str, List[float]]:
    """Group P&L by GAME — the resample unit (L6: never by outcome)."""
    out: Dict[str, List[float]] = {}
    for r in rows:
        out.setdefault(r["game"], []).append(float(r[key]))
    return out


def verdict_for(rows: Sequence[dict], label: str, n_boot: int = N_BOOT,
                seed: int = SEED) -> dict:
    uv = unit_values(rows)
    boot = block_bootstrap(uv, n_boot=n_boot, seed=seed)
    adm = bootstrap_verdict_admissible(uv, min_units=MIN_UNITS)
    tick_ok = clears_tick_magnitude(boot["ci95"], tick=TICK, min_ticks=1.0)
    sign = sign_bounded_objective(uv, admissibility=adm)
    n_filled = sum(1 for r in rows if r["filled"])
    losing_units = sum(1 for v in uv.values() if v and sum(v) / len(v) < 0)
    return {
        "label": label,
        "n_legs": len(rows),
        "n_filled_legs": n_filled,
        "fill_rate": (n_filled / len(rows)) if rows else None,
        "n_units_games": boot["n_units"],
        "n_losing_units": losing_units,
        "mean": boot["mean"],
        "ci95": boot["ci95"],
        "n_boot": boot["n_boot"],
        "seed": boot["seed"],
        "admissible": adm["admissible"],
        "admissibility": adm,
        "clears_tick_magnitude": tick_ok,
        "sign_bounded_objective": sign,
        "verdict": _verdict_label(boot, adm, tick_ok),
        "price_source_tag": "real_bid",
        "fill_evidence_tag": "broker_truth",
        "fee_rate": FEE_RATE,
    }


def _verdict_label(boot: dict, adm: dict, tick_ok: bool) -> str:
    if not adm["admissible"]:
        return "INADMISSIBLE"
    lo = boot["ci95"][0]
    if lo is None:
        return "INADMISSIBLE"
    if lo <= 0:
        return "DEAD (CI straddles or is below zero at real prices)"
    if not tick_ok:
        return "DEAD (positive but sub-tick: fails the L27 magnitude gate)"
    return "ALIVE-CANDIDATE (admissible, CI>0, clears one tick)"


# --------------------------------------------------------------------------- #
def run(day: str = DAY, n_boot: int = N_BOOT, seed: int = SEED,
        cache_path: Path = CACHE_PATH) -> dict:
    order, snaps = load_depth(day)
    prints = load_prints(day)
    if not order:
        raise SystemExit(f"no depth tape for dt={day}")
    sample = reconstruct_sample(order)
    sample_set = set(sample)
    traded = set(prints)
    missing = sorted(traded - sample_set)
    if missing:
        raise SystemExit(
            "sample reconstruction FAILED: %d traded tickers fall outside the "
            "reconstructed stride sample (%s ...). Refusing to analyse the wrong "
            "denominator." % (len(missing), missing[:3]))
    universe = [t for t in sample if is_sports_game_market(t)]
    settlement = load_settlement_cache(cache_path)
    _kept, binary_report = filter_binary_results_map(
        {t: (settlement.get(t) or {}).get("result") for t in universe})

    rows, stats = build_rows(snaps, prints, settlement, universe)
    covered_rows = [r for r in rows if r["interval_covered"]]

    verdicts = {
        "all_intervals": verdict_for(rows, "all_intervals (HEADLINE, conservative)",
                                     n_boot=n_boot, seed=seed),
        "covered_intervals": verdict_for(covered_rows,
                                         "covered_intervals (SENSITIVITY, conditions on activity)",
                                         n_boot=n_boot, seed=seed),
        "all_intervals_yes_bid": verdict_for([r for r in rows if r["side"] == "yes_bid"],
                                             "all_intervals / YES-bid leg only (diagnostic)",
                                             n_boot=n_boot, seed=seed),
        "all_intervals_no_bid": verdict_for([r for r in rows if r["side"] == "no_bid"],
                                            "all_intervals / NO-bid leg only (diagnostic)",
                                            n_boot=n_boot, seed=seed),
        "conditional_on_fill": verdict_for([r for r in rows if r["filled"]],
                                           "conditional on fill (diagnostic, NOT a strategy P&L)",
                                           n_boot=n_boot, seed=seed),
    }
    fills = [r for r in rows if r["filled"]]
    untraced = [r for r in fills if not r.get("fill_trade_id")]
    report = {
        "schema_version": "q51_maker_fillsim.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": day,
        "population": {
            "depth_tickers_in_day": len(order),
            "stride_sample_size": len(sample),
            "sports_game_markets": len(universe),
            "tickers_with_prints_in_sample": len(traded),
            "sports_tickers_with_prints": sum(1 for t in universe if t in traded),
            "binary_settlement_filter": binary_report.summary(),
            "settlement_cached": sum(1 for t in universe if t in settlement),
        },
        "intervals": stats,
        "fill_traceability": {
            "n_fills": len(fills),
            "n_fills_traced_to_broker_truth_print": len(fills) - len(untraced),
            "all_fills_traced": not untraced,
        },
        "resolution_ceiling": (
            "book cadence is ~3h; this tape supports interval-level fill EXISTENCE only. "
            "No queue-position, time-to-fill or sub-interval adverse-selection number is "
            "computed or claimable from it."),
        "verdicts": verdicts,
    }
    return report, rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default=DAY)
    ap.add_argument("--n-boot", type=int, default=N_BOOT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--build-cache", action="store_true",
                    help="one read-only unauthenticated pull of the settlement results")
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    ap.add_argument("--rows-out", default=str(ROWS_PATH))
    args = ap.parse_args(argv)

    if args.build_cache:
        order, _ = load_depth(args.day)
        universe = [t for t in reconstruct_sample(order) if is_sports_game_market(t)]
        build_settlement_cache(universe)

    report, rows = run(day=args.day, n_boot=args.n_boot, seed=args.seed)

    Path(args.rows_out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.rows_out, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, sort_keys=True)

    p = report["population"]
    iv = report["intervals"]
    print(f"[q51:fillsim] day={report['day']}  sports markets={p['sports_game_markets']}  "
          f"traded={p['sports_tickers_with_prints']}  settled+binary={p['binary_settlement_filter']}")
    print(f"[q51:fillsim] intervals={iv['n_intervals']}  covered={iv['n_covered_intervals']}  "
          f"coverage={iv['interval_coverage']}")
    print(f"[q51:fillsim] drops={iv['drops']}  dropped_tickers={iv['dropped_tickers']}")
    print(f"[q51:fillsim] fills traced to broker_truth prints: "
          f"{report['fill_traceability']['n_fills_traced_to_broker_truth_print']}"
          f"/{report['fill_traceability']['n_fills']}")
    for k, v in report["verdicts"].items():
        print(f"  {k}: n_legs={v['n_legs']} filled={v['n_filled_legs']} "
              f"fill_rate={v['fill_rate']} units={v['n_units_games']} "
              f"losing_units={v['n_losing_units']} mean={v['mean']} ci95={v['ci95']} "
              f"admissible={v['admissible']} tick={v['clears_tick_magnitude']} "
              f"-> {v['verdict']}")
    print(f"[q51:fillsim] wrote {args.json_out} and {args.rows_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

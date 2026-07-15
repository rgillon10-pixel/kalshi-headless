"""Q30 / S29 — soccer draw-aversion underpricing MAKER fill-sim (the -TIE / draw leg).

Falsifiable milestone (LOOP-QUEUE.md Q30; kb/strategies/00-index.md S29; literature
distilled at kb/quant-finance/draw-aversion-soccer.md): draw-aversion is a documented
sentiment bias in football betting — bettors dislike backing the draw (no team to root for)
and overbet the two teams, leaving the draw (the `-TIE` leg) systematically cheap. This is an
outcome-TYPE bias at a mid-probability ~0.25-0.33 leg, NOT a price-level bias, so L54's closure
of the favorite/longshot maker lens does not foreclose it. This probe rests a MAKER BID to BUY
the draw-YES leg of every 3-way-soccer market and collects $1 on settlement if the match draws.

THE FAIR TEST IS REALIZED SETTLEMENT (Kalshi's own settled result, broker_truth) — not a devig
anchor (same design as Q26/Q27, sidesteps S21's L43/L9 join-emptiness death; the settlement leg
is retrieved ex-post from Kalshi's free settled endpoint over the depth tape's OWN window, well
inside the ~60-day L11 retention).

Net per FILLED contract (maker BUY draw-YES, held to settlement), net of the flat $0.01 maker
fee (core.pricing, L18/L30):
  - match DRAWS   (-TIE settles YES) -> +$1 payout: net  1 − fill_price − $0.01.
  - match DECIDES (-TIE settles NO)  ->  $0 payout: net  0 − fill_price − $0.01  (the
    CATASTROPHIC adverse-selection leg — informed sellers dump the draw once a goal makes a
    decisive result likely). Fully in the P&L, NEVER conditioned away (binding gate 2 / L41 /
    G2). The fill model is outcome-blind, so no-draw fills are included by construction, AND the
    fill-conditional NO-draw rate is reported as its own explicit number (binding gate 2).

TARGET POPULATION (a deliberate, documented improvement over Q27's fixed 7-series list): the
`-TIE` leg of EVERY 3-way-soccer series DISCOVERED programmatically in the committed depth tape
(any series with ≥1 ticker ending in `-TIE`), pooled across all families to maximize n (binding
gate 4 power screen). The `-TIE` suffix is a clean self-disambiguating discriminator — draw-less
baseball/basketball carry no `-TIE` leg. No favorite/normalized-fair filter (every `-TIE` market
IS the target); Q27's bracket_sum / normalized-ask / favorite classification path is skipped.

Queue-aware fill-sim (L39, NOT a candlestick print) reused verbatim from Q27 (do NOT re-derive):
rest at the draw market's earliest pre-close `best_yes_bid`; queue_ahead = the `yes_bids` size
at price ≥ our bid at entry; FILLED once cumulative observed departures at price ≥ our bid across
later snapshots clear the queue (a frozen queue is a NO-FILL, L32/L48). Deliberately GENEROUS
(cancels ahead advance us, new bids jumping ahead ignored) — so a below-floor fill rate is a
robust dead-thin OUT, never a fill guarantee. fill_price is `real_bid`; settlement `broker_truth`.

BINDING GATES (LOOP-QUEUE Q30, verifier-mandated, do NOT weaken):
  (1) restrict the settlement join to games actually present in the settlement snapshot within
      the depth window, and pin the L52 scalar/void-result filter (soccer can settle scalar on
      abandonment — dropped + counted).
  (2) MODEL the adverse-selection leg, measured not assumed — report the empirical fill-
      conditional NO-draw rate as its own number; the no-draw leg is in the P&L (L41/G2).
  (3) L53 caveat — over long resting windows the fill-rate gate passes trivially, so the KILL
      lands on the EDGE test (draw-rate vs fill_price+fee), not on fill rate.
  (4) POWER screen — a hold-to-settlement per-game P&L carries a ±$1 settlement leg
      (sd≈0.44 at a ~0.25 draw rate), so the by-game CI half-width has a hard theoretical floor
      (~$0.09 at n≈24, ~$0.044 at n≈100). Reported alongside the achieved half-width so the
      reader can see whether the achieved n has power to detect a real edge.
  (5) route any CI through core.bootstrap.bootstrap_verdict_admissible (≥10 units, ≥1 opposing-
      sign cluster, L41) AND clears_tick_magnitude (tick 0.01, L27) — failing EITHER is not-a-
      verdict.

KILL CONDITIONS (any ⇒ DEAD): draw-rate ≤ mean fill_price + $0.01 fee (bias too small / L30
fee-death, S13-family) · draw leg not reliably identifiable · fill rate ≤ S19 0.45% floor ·
settlement-join or effective power below the 10-game floor · CI fails admissibility or the
tick-magnitude gate.

READ-ONLY over `tape/orderbook_depth/` (a probe never mutates tape). Sizes are FLOATS and can be
fractional (L47) — never int-coerce. An empty ladder on a wing is VALID data (L23). Fees ONLY
from core.pricing at MAKER_FEE_RATE (flat $0.01 interior, L18/L30).

Run (live settlement pull -> cache, then full analysis):
    python scripts/q30_draw_aversion_maker_probe.py --refresh-cache
Run (offline, against the committed cache — verifier mode):
    python scripts/q30_draw_aversion_maker_probe.py
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,
                            clears_tick_magnitude)
from core.io import REPO_ROOT
from core.pricing import MAKER_FEE_RATE, fee_per_contract

# `core` is pip-installed (editable) but `scripts/` is not a declared package; make the repo
# root importable so the standalone run reuses the sibling probes' helpers verbatim (L21 —
# reuse via import, do NOT copy-paste). Under pytest conftest.py already does this.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.q26_ofi_depth_imbalance_probe import (  # noqa: E402
    event_ticker_of, load_settlement_cache, parse_iso, series_of)
from scripts.q27_favorite_underpricing_fillsim import (  # noqa: E402
    bid_size_at_or_above, departures_between, maker_fee, simulate_fill)

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
CACHE_PATH = REPO_ROOT / "tape" / "q30_settlement_cache" / "settlement.json"
# Offline fallback so a verifier can run before the q30 cache lands: Q27's cache carries 40
# settled -TIE markets (KXUCLGAME/KXUECLGAME only — 3 of the ~19 families) with the same
# result/close_time/event_ticker schema. Partial, but non-empty (Q29 reused Q26's cache the
# same way).
FALLBACK_CACHE_PATH = REPO_ROOT / "tape" / "q27_settlement_cache" / "settlement.json"

TIE_SUFFIX = "-TIE"
S19_FILL_FLOOR = 0.0045     # the S19-class queue-aware fill-rate kill floor (gate 3)
MIN_CI_UNITS = 10           # fewer joined/filled GAMES than this = data-adequacy, not a CI
PRICE_TICK = 0.01           # Kalshi price tick (L27 magnitude gate)
POWER_DRAW_RATE = 0.25      # the ~0.25 draw base-rate the gate-4 theoretical floor is stated at
_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Pure -TIE (draw-leg) identification (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def is_tie_ticker(market_ticker: str) -> bool:
    """True iff `market_ticker` is a 3-way-soccer DRAW leg — its trailing outcome code is
    exactly 'TIE' (e.g. 'KXMLSGAME-26JUL12ABC-TIE'). Draw-less baseball/basketball markets
    carry no -TIE leg, so this suffix is a clean self-disambiguating discriminator. The check
    is on the LAST '-'-segment specifically (not a substring), so a team code that merely
    contains the letters TIE cannot false-positive."""
    if not market_ticker:
        return False
    return market_ticker.rsplit("-", 1)[-1] == "TIE" and TIE_SUFFIX in market_ticker


def discover_tie_series(depth_glob: str) -> Tuple[str, ...]:
    """Scan the depth tape once and return the sorted tuple of every series that has ≥1 ticker
    ending in `-TIE` present (the target soccer families, DISCOVERED not hardcoded — L7 spirit:
    read the population off the data). Read-only."""
    found: set = set()
    for fp in sorted(glob.glob(depth_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                mt = json.loads(line).get("ticker", "")
                if is_tie_ticker(mt):
                    found.add(series_of(mt))
    return tuple(sorted(found))


# --------------------------------------------------------------------------- #
# P&L + power floor (pure)
# --------------------------------------------------------------------------- #
def draw_pnl(fill_price: float, draw_settles_yes: bool) -> float:
    """P&L of one FILLED maker BUY of the draw-YES, held to settlement, net of the flat maker
    fee (core.pricing, never hand-rolled):
      match DRAWS   (-TIE settles YES) -> +1 payout: 1 − fill_price − fee.
      match DECIDES (-TIE settles NO)  ->  0 payout: 0 − fill_price − fee  (catastrophic no-draw
        leg — informed sellers dump the draw when a decisive result looks likely; modeled here
        explicitly, never conditioned away, binding gate 2 / L41)."""
    fee = maker_fee(fill_price)
    payoff = 1.0 if draw_settles_yes else 0.0
    return payoff - float(fill_price) - fee


def power_floor_halfwidth(n: int, draw_rate: float = POWER_DRAW_RATE) -> Optional[float]:
    """The gate-4 POWER screen: a hold-to-settlement per-game P&L is dominated by a ±$1
    Bernoulli settlement leg with sd = sqrt(p(1−p)) (≈0.433 at p=0.25). The theoretical
    standard error of the by-game mean therefore has a hard floor sqrt(p(1−p)/n) — ~$0.0884 at
    n=24, ~$0.0433 at n=100 (the ~$0.09 / ~$0.044 the milestone states). Reported alongside the
    achieved bootstrap CI half-width so the reader can see whether the achieved n has any power
    to detect a real underpricing above the 1¢ fee, regardless of the point estimate's sign.
    None on n ≤ 0."""
    if n <= 0:
        return None
    return math.sqrt(draw_rate * (1.0 - draw_rate) / n)


# --------------------------------------------------------------------------- #
# Settlement cache (live pull, cached to disk; verifier re-runs offline)
# --------------------------------------------------------------------------- #
def depth_tie_event_tickers(depth_glob: str, tie_series: Sequence[str]) -> Dict[str, set]:
    """Per target series, the set of event_tickers that carry a -TIE draw leg in the depth tape
    — so the live settlement pull fetches /markets ONLY for joinable soccer games (binding gate
    1: restrict the join to games present in the depth window). Read-only."""
    by_series: Dict[str, set] = {s: set() for s in tie_series}
    for fp in sorted(glob.glob(depth_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                mt = json.loads(line).get("ticker", "")
                if not is_tie_ticker(mt):
                    continue
                s = series_of(mt)
                if s in by_series:
                    by_series[s].add(event_ticker_of(mt))
    return by_series


def build_settlement_cache(series_list: Sequence[str], cache_path: Path,
                           limit: int = 500, min_interval: float = 0.25,
                           depth_glob: str = DEPTH_GLOB) -> Dict[str, dict]:
    """Pull settled events for each discovered soccer series, then each depth-window event's
    markets, and cache a flat map market_ticker -> {result, close_time, event_ticker, series}
    for the -TIE draw legs only. Only fetches /markets for event_tickers present in the depth
    tape (the joinable universe). Live network; self-wraps a ConnectionError retry (L40). Writes
    JSON so a verifier can re-run OFFLINE. Results can be 'scalar' (L52) — cached verbatim and
    filtered downstream."""
    import time

    import requests

    from collection.sports_history import fetch_settled_events
    from validation.v3_market import Kalshi, _load_venue_cfg

    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"], min_interval=min_interval)

    def _get_text_retry(path: str, **params) -> str:
        for attempt in range(4):
            try:
                return client.get_text(path, **params)
            except (requests.ConnectionError, ConnectionError):  # L40
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("unreachable")

    def _fetch_events_retry(series: str) -> list:
        for attempt in range(4):
            try:
                events, _raw = fetch_settled_events(client, series, limit=limit)
                return events
            except (requests.ConnectionError, ConnectionError):  # L40
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        return []

    wanted = depth_tie_event_tickers(depth_glob, series_list)

    out: Dict[str, dict] = {}
    per_series: Dict[str, int] = {}
    for series in series_list:
        events = _fetch_events_retry(series)
        want = wanted.get(series, set())
        n_markets = 0
        n_events_hit = 0
        for e in events:
            event_ticker = e.get("event_ticker", "")
            if not event_ticker or event_ticker not in want:
                continue
            n_events_hit += 1
            text = _get_text_retry("/markets", event_ticker=event_ticker)
            markets = json.loads(text).get("markets") or []
            for m in markets:
                mt = m.get("ticker")
                if not mt or not is_tie_ticker(mt):  # cache the DRAW leg only
                    continue
                out[mt] = {
                    "result": m.get("result"),
                    "close_time": m.get("close_time"),
                    "event_ticker": m.get("event_ticker") or event_ticker,
                    "series": series,
                }
                n_markets += 1
        per_series[series] = n_markets
        print(f"[q30:cache] {series}: {len(events)} settled events, "
              f"{n_events_hit}/{len(want)} depth-window events joined, {n_markets} -TIE markets")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "q30_settlement_cache.v1",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "series": list(series_list),
        "per_series_market_count": per_series,
        "markets": out,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"[q30:cache] wrote {len(out)} settled -TIE markets -> {cache_path}")
    return out


def load_settlement_for_run(cache_path: Path) -> Tuple[Dict[str, dict], str]:
    """Load the -TIE settlement map, preferring the q30 cache and falling back to Q27's partial
    cache (KXUCLGAME/KXUECLGAME only) if the q30 cache is absent (Q29-style fallback). Returns
    (settlement_map_filtered_to_tie, source_label)."""
    primary = load_settlement_cache(cache_path)
    src = "q30_cache"
    if not primary and cache_path != FALLBACK_CACHE_PATH:
        primary = load_settlement_cache(FALLBACK_CACHE_PATH)
        src = "q27_fallback_cache"
    tie_only = {mt: s for mt, s in primary.items() if is_tie_ticker(mt)}
    return tie_only, src


# --------------------------------------------------------------------------- #
# Depth tape loading (read-only) — ALL pre-close snapshots per -TIE market
# --------------------------------------------------------------------------- #
def load_preclose_snapshots(depth_glob: str, settlement: Dict[str, dict]
                            ) -> Tuple[Dict[str, List[dict]], dict]:
    """Scan the depth tape once. For every -TIE draw-leg market with a BINARY settlement
    (result ∈ {yes,no}, L52 — scalar/void dropped) and a close_time, collect ALL snapshots with
    captured_at < close_time (genuine pre-close), sorted ascending. Returns
    (per_market_snapshot_list, funnel_counts)."""
    funnel = {
        "tie_markets_in_depth": set(),
        "markets_settled_binary": set(),
        "markets_settled_scalar_dropped_L52": set(),
        "markets_with_preclose": set(),
    }
    per_market: Dict[str, List[dict]] = {}
    for fp in sorted(glob.glob(depth_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                mt = rec.get("ticker", "")
                if not is_tie_ticker(mt):
                    continue
                funnel["tie_markets_in_depth"].add(mt)
                s = settlement.get(mt)
                if not s:
                    continue
                result = s.get("result")
                if result == "scalar":
                    funnel["markets_settled_scalar_dropped_L52"].add(mt)
                    continue
                if result not in ("yes", "no"):
                    continue
                funnel["markets_settled_binary"].add(mt)
                close_dt = parse_iso(s.get("close_time"))
                cap_dt = parse_iso(rec.get("captured_at"))
                if close_dt is None or cap_dt is None or cap_dt >= close_dt:
                    continue
                per_market.setdefault(mt, []).append({
                    "record": rec,
                    "captured_at": cap_dt,
                    "close_time": close_dt,
                    "ttc_seconds": (close_dt - cap_dt).total_seconds(),
                    "event_ticker": s.get("event_ticker") or event_ticker_of(mt),
                    "series": s.get("series") or series_of(mt),
                    "result": result,
                })
    for mt in per_market:
        per_market[mt].sort(key=lambda d: d["captured_at"])
    funnel["markets_with_preclose"] = set(per_market.keys())
    return per_market, funnel


# --------------------------------------------------------------------------- #
# Draw-leg maker trades + fill-sim (no favorite filter — every -TIE market rests a bid)
# --------------------------------------------------------------------------- #
def build_draw_trades(per_market: Dict[str, List[dict]]) -> Tuple[List[dict], dict]:
    """One resting-maker draw-YES bid per -TIE market. Entry = its earliest pre-close snapshot;
    rest a maker BID at the entry best_yes_bid; queue_ahead = yes_bids size at price ≥ that bid.
    No favorite/normalized-fair filter (every draw leg IS the target). Markets with no entry
    best_yes_bid / empty yes_bids can't rest a bid and are counted, not traded."""
    trades: List[dict] = []
    funnel = {
        "n_tie_markets": len(per_market),
        "n_events": len({event_ticker_of(mt) for mt in per_market}),
        "n_no_restable_bid": 0,
        "n_rested": 0,
    }
    for mt, snaps in per_market.items():
        entry = snaps[0]
        entry_rec = entry["record"]
        bid = entry_rec.get("best_yes_bid")
        if bid is None or not entry_rec.get("yes_bids"):
            funnel["n_no_restable_bid"] += 1
            continue
        bid = float(bid)
        entry_ask = entry_rec.get("best_yes_ask")
        entry_spread = (float(entry_ask) - bid) if entry_ask is not None else None
        queue_ahead = bid_size_at_or_above(entry_rec.get("yes_bids"), bid)
        filled = simulate_fill(snaps, bid, queue_ahead)
        draw_settles_yes = (entry["result"] == "yes")
        trades.append({
            "market_ticker": mt,
            "event_ticker": event_ticker_of(mt),
            "series": entry["series"],
            "ttc_seconds_entry": entry["ttc_seconds"],
            "entry_yes_spread": entry_spread,
            "n_snapshots": len(snaps),
            "raw_draw_yes_bid": bid,
            "fill_price": bid,
            "queue_ahead": queue_ahead,
            "filled": filled,
            "draw_settles_yes": draw_settles_yes,
            "pnl": (draw_pnl(bid, draw_settles_yes) if filled else None),
            "price_source_tag": "real_bid(fill)+broker_truth(settle)",
        })
        funnel["n_rested"] += 1
    return trades, funnel


# Robustness cuts (L31/L48/L53): the spec entry is the EARLIEST pre-close bid, which over a
# median multi-day window sits on thin, often one-sided early books — best_yes_bid is then a
# nominal lowball, and the generous fill-sim (a cancel counts as advancing us) "fills" it. A
# wide one-sided spread is a nominal, NOT maker-capturable, price (L31/S6). So any headline CI
# is re-cut two ways: (a) a two-sided-book entry (entry spread ≤ the S6/L31 fillable ≤10¢ line),
# (b) a near-close entry where a resting maker fill is realistic. If the edge lives only on the
# wide-early-book population, it is a wing artifact, not a demonstrated fillable edge.
TWO_SIDED_SPREAD_MAX = 0.10   # S6/L31 fillable two-sided book (≤10¢); wider = one-sided wing
NEARCLOSE_TTC_HOURS = 24.0    # entries within a day of close (realistic maker-fill window)


def _bootstrap_cut(fills: Sequence[dict], n_boot: int) -> dict:
    """Bootstrap-by-game a subset of FILLED trades, reporting the same gate outputs as the
    headline so a robustness cut is judged on identical criteria."""
    n = len(fills)
    if n == 0:
        return {"n_fills": 0, "n_games": 0}
    draw_rate = sum(1 for t in fills if t["draw_settles_yes"]) / n
    mean_fill = sum(t["fill_price"] for t in fills) / n
    breakeven = mean_fill + maker_fee(mean_fill)
    uv: Dict[str, List[float]] = {}
    for t in fills:
        uv.setdefault(t["event_ticker"], []).append(t["pnl"])
    boot = block_bootstrap(uv, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(uv, min_units=MIN_CI_UNITS)
    mag = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK, min_ticks=1.0)
    ci_lo = boot["ci95"][0]
    return {
        "n_fills": n, "n_games": boot["n_units"],
        "draw_rate_among_fills": draw_rate,
        "fill_conditional_no_draw_rate": 1.0 - draw_rate,
        "mean_fill_price_real_bid": mean_fill,
        "breakeven_drawrate": breakeven,
        "net_underpricing_edge": draw_rate - breakeven,
        "boot_mean": boot["mean"], "ci95": boot["ci95"],
        "admissible": adm["admissible"], "clears_tick_magnitude": mag,
        "ci_lower_positive": ci_lo is not None and ci_lo > 0.0,
        "passes_all_gates": (boot["n_units"] >= MIN_CI_UNITS and adm["admissible"]
                             and mag and ci_lo is not None and ci_lo > 0.0),
    }


def per_game_pnl(trades: Sequence[dict]) -> Dict[str, List[float]]:
    """Group FILLED-trade net P&L by GAME (event_ticker, L6 bootstrap unit). The no-draw leg is
    included by construction (fill model is outcome-blind, binding gate 2)."""
    out: Dict[str, List[float]] = {}
    for t in trades:
        if t["filled"] and t["pnl"] is not None:
            out.setdefault(t["event_ticker"], []).append(t["pnl"])
    return out


# --------------------------------------------------------------------------- #
# Analysis / verdict
# --------------------------------------------------------------------------- #
def run(cache_path: Path = CACHE_PATH, depth_glob: str = DEPTH_GLOB,
        n_boot: int = 10000) -> dict:
    """Full offline analysis against the cached settlement + committed depth tape."""
    settlement, cache_source = load_settlement_for_run(cache_path)
    tie_series = discover_tie_series(depth_glob)
    per_market, funnel_sets = load_preclose_snapshots(depth_glob, settlement)

    games_preclose = len({event_ticker_of(mt) for mt in per_market})
    report = {
        "cache_source": cache_source,
        "n_settled_tie_markets_cached": len(settlement),
        "discovered_tie_series": list(tie_series),
        "n_discovered_tie_series": len(tie_series),
        "funnel": {
            "tie_markets_in_depth": len(funnel_sets["tie_markets_in_depth"]),
            "markets_settled_binary": len(funnel_sets["markets_settled_binary"]),
            "markets_settled_scalar_dropped_L52":
                len(funnel_sets["markets_settled_scalar_dropped_L52"]),
            "markets_with_preclose_snapshot": len(funnel_sets["markets_with_preclose"]),
            "distinct_games_with_preclose": games_preclose,
        },
    }

    trades, trade_funnel = build_draw_trades(per_market)
    report["draw_funnel"] = trade_funnel

    joinable_games = {t["event_ticker"] for t in trades}
    report["distinct_joinable_games"] = len(joinable_games)

    # gate 1/4 adequacy — BEFORE any CI (S21-class: <10 games ⇒ DEAD-by-adequacy, not a CI kill).
    if len(joinable_games) < MIN_CI_UNITS:
        report["verdict"] = "DEAD-by-adequacy"
        report["verdict_reason"] = (
            f"only {len(joinable_games)} distinct soccer games carry a -TIE resting bid with a "
            f"binary settlement (<{MIN_CI_UNITS}); untestable as collected (data-adequacy death, "
            "NOT a CI falsification). Likely the offline fallback cache covers too few families "
            "— rerun with --refresh-cache over the full discovered series list.")
        return report

    # gate 3 — queue-aware fill rate vs the S19 floor (L53: over long windows this passes
    # trivially, so the KILL must land on the edge test below, not here).
    n_rested = len(trades)
    fills = [t for t in trades if t["filled"]]
    n_fill = len(fills)
    fill_rate = n_fill / n_rested if n_rested else 0.0
    fill_prices = [t["fill_price"] for t in fills]
    mean_fill_price = (sum(fill_prices) / len(fill_prices)) if fill_prices else None
    n_draw_fills = sum(1 for t in fills if t["draw_settles_yes"])
    draw_rate_fills = (n_draw_fills / n_fill) if n_fill else None
    # binding gate 2: the fill-conditional NO-draw rate as its OWN explicit number.
    no_draw_rate_fills = (1.0 - draw_rate_fills) if draw_rate_fills is not None else None
    n_draw_rested = sum(1 for t in trades if t["draw_settles_yes"])
    draw_rate_rested = (n_draw_rested / n_rested) if n_rested else None

    report["fill"] = {
        "n_rested_draw_bids": n_rested,
        "n_fill": n_fill,
        "fill_rate": fill_rate,
        "s19_floor": S19_FILL_FLOOR,
        "mean_fill_price_real_bid": mean_fill_price,
        "draw_rate_among_fills": draw_rate_fills,
        "fill_conditional_no_draw_rate": no_draw_rate_fills,   # binding gate 2 (adverse leg)
        "draw_rate_among_all_rested": draw_rate_rested,
        "fills_draw": n_draw_fills,
        "fills_no_draw": n_fill - n_draw_fills,
    }

    if fill_rate <= S19_FILL_FLOOR + _EPS:
        report["verdict"] = "DEAD-by-fill-rate"
        report["verdict_reason"] = (
            f"queue-aware fill rate {fill_rate:.4%} ≤ S19 floor {S19_FILL_FLOOR:.4%} "
            f"({n_fill}/{n_rested} rested draw bids filled) — dead-thin (gate 3/L48)")
        return report

    # KILL (edge test, gate 3/L53): draw-rate ≤ mean fill_price + fee ⇒ the underpricing net of
    # the $0.01 maker fee is ≤ 0 (bias too small / L30 fee-death, S13-family).
    if mean_fill_price is not None and draw_rate_fills is not None:
        breakeven = mean_fill_price + maker_fee(mean_fill_price)
        report["fill"]["breakeven_drawrate"] = breakeven
        report["fill"]["net_underpricing_edge"] = draw_rate_fills - breakeven
        if draw_rate_fills <= breakeven + _EPS:
            report["verdict"] = "DEAD-by-fee"
            report["verdict_reason"] = (
                f"draw-rate among fills {draw_rate_fills:.4f} ≤ mean fill_price+fee "
                f"{breakeven:.4f} — the draw underpricing doesn't clear the price paid + $0.01 "
                "maker fee (L30 fee-death / S13-family). The catastrophic no-draw leg "
                f"(fill-conditional no-draw rate {no_draw_rate_fills:.4f}) dominates.")
            # still compute the CI + power floor below for completeness; the verdict stands.

    # gate 4/5 — block-bootstrap net P&L BY GAME (L6), through BOTH gates, + power floor.
    unit_values = per_game_pnl(trades)
    boot = block_bootstrap(unit_values, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(unit_values, min_units=MIN_CI_UNITS)
    mag = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK, min_ticks=1.0)
    ci_lo, ci_hi = boot["ci95"][0], boot["ci95"][1]
    ci_positive = ci_lo is not None and ci_lo > 0.0
    achieved_halfwidth = ((ci_hi - ci_lo) / 2.0) if (ci_lo is not None and ci_hi is not None) \
        else None
    n_units = boot["n_units"]
    report["bootstrap"] = {
        "mean": boot["mean"], "ci95": boot["ci95"],
        "n_units_games": n_units, "n_obs_fills": boot["n_obs"],
        "admissible": adm, "clears_tick_magnitude": mag,
        "ci_lower_positive": ci_positive,
    }
    report["power"] = {
        "achieved_ci_halfwidth": achieved_halfwidth,
        "theoretical_floor_at_p025": power_floor_halfwidth(n_units, POWER_DRAW_RATE),
        "theoretical_floor_at_empirical_draw_rate":
            power_floor_halfwidth(n_units, draw_rate_fills)
            if draw_rate_fills is not None else None,
        "empirical_draw_rate_among_fills": draw_rate_fills,
        "commentary": (
            "gate-4 power screen: the by-game P&L is dominated by a ±$1 Bernoulli settlement "
            "leg (sd=sqrt(p(1-p))≈0.43 at p=0.25), so the by-game CI half-width cannot fall "
            "below sqrt(p(1-p)/n). Compare achieved_ci_halfwidth to the theoretical floor to "
            "judge whether n has power to resolve a real underpricing above the 1¢ fee."),
    }

    # Entry diagnostics + robustness cuts (L31/L48/L53) — is the headline edge a wide-early-book
    # artifact? Reported for BOTH the primary verdict and the verifier, never conditioned away.
    ttc_hours = sorted(t["ttc_seconds_entry"] / 3600.0 for t in fills)
    spreads = sorted(t["entry_yes_spread"] for t in fills if t["entry_yes_spread"] is not None)

    def _median(xs):
        return xs[len(xs) // 2] if xs else None

    two_sided = [t for t in fills if t["entry_yes_spread"] is not None
                 and t["entry_yes_spread"] <= TWO_SIDED_SPREAD_MAX + _EPS]
    nearclose = [t for t in fills if t["ttc_seconds_entry"] <= NEARCLOSE_TTC_HOURS * 3600.0]
    report["entry_diagnostics"] = {
        "entry_ttc_hours_median": _median(ttc_hours),
        "entry_ttc_hours_min": ttc_hours[0] if ttc_hours else None,
        "entry_ttc_hours_max": ttc_hours[-1] if ttc_hours else None,
        "entry_spread_median": _median(spreads),
        "entry_spread_p90": spreads[int(0.9 * (len(spreads) - 1))] if spreads else None,
        "note": ("spec entry = the EARLIEST pre-close best_yes_bid; a large median ttc + a "
                 "fat spread p90 means many entries sit on thin one-sided early books where "
                 "best_yes_bid is a nominal lowball the generous fill-sim still 'fills' (L31/L48)."),
    }
    report["robustness"] = {
        "two_sided_book_entry": {
            "spread_max": TWO_SIDED_SPREAD_MAX,
            **_bootstrap_cut(two_sided, n_boot),
        },
        "nearclose_entry": {
            "ttc_hours_max": NEARCLOSE_TTC_HOURS,
            **_bootstrap_cut(nearclose, n_boot),
        },
        "note": ("if the headline CI passes but these fillable-book cuts do NOT, the edge is a "
                 "wide-early-book / entry-timing artifact (L31/L48/L53), not a demonstrated "
                 "fillable maker edge — treat a passing headline as fragile, not confirmed."),
    }

    if report.get("verdict") == "DEAD-by-fee":
        return report

    if n_units < MIN_CI_UNITS:
        report["verdict"] = "DEAD-by-adequacy"
        report["verdict_reason"] = (
            f"only {n_units} games carry a FILLED draw trade (<{MIN_CI_UNITS}) — data-adequacy "
            "dead even if the point estimate looks positive")
    elif not adm["admissible"]:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = f"bootstrap inadmissible (L41): {adm['reasons']}"
    elif not ci_positive:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = f"95% CI lower bound not > 0: ci95={boot['ci95']}"
    elif not mag:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = (
            f"CI>0 but fails the 1-tick economic-significance gate (L27): ci95={boot['ci95']}")
    else:
        rob = report.get("robustness", {})
        ts_pass = rob.get("two_sided_book_entry", {}).get("passes_all_gates")
        nc_pass = rob.get("nearclose_entry", {}).get("passes_all_gates")
        if ts_pass and nc_pass:
            report["verdict"] = "ALIVE-PROVISIONAL"
            report["verdict_reason"] = (
                "all binding gates pass AND both fillable-book robustness cuts survive — "
                "genuinely uncertain; needs verifier confirmation + shadow-paper before any "
                "capital (do NOT trade, do NOT flip the registry)")
        else:
            # Verifier-mandated (2026-07-15 two-agent review): the spec (earliest-pre-close)
            # population's headline CI is NOT a defensible verdict on its own when the
            # fillable-entry restriction (a real trader's actual resting-book population)
            # fails to reproduce it. Hand-inspection confirmed the headline is carried by
            # nickel bids on 80c+-wide, days-out one-sided books that the generous fill-sim
            # "fills" trivially (L31/L48/L53) — a nominal quote treated as fillable, the pt1
            # failure mode one abstraction up. The two-sided-book cut straddles zero and the
            # near-close cut goes NEGATIVE — both honest fillable-entry populations fail, so
            # this is DEAD, not merely "fragile ALIVE".
            report["verdict"] = "DEAD-by-fillability"
            report["verdict_reason"] = (
                "all BINDING gates pass on the spec (earliest-pre-close) population, but that "
                f"population is NOT a defensible fillable-entry proxy: two-sided-book entry cut "
                f"passes={ts_pass} (CI straddles zero and/or fails tick-magnitude), near-close "
                f"entry cut passes={nc_pass} (point estimate goes negative) — see "
                "report['robustness']. The headline CI is carried by very-early, wide/one-sided-"
                "book entries where best_yes_bid is a nominal lowball the generous fill-sim "
                "still 'fills' (L31/L48/L53), NOT a demonstrated fillable maker edge — the "
                "nominal-quote-as-fillable mistake CLAUDE.md forbids, one abstraction up from a "
                "synthetic price. Both defensible fillable-entry cuts fail to clear >0 with "
                "adequate power. DEAD-by-fillability; do NOT trade, do NOT register S29 alive.")
    return report


def _print_report(rep: dict) -> None:
    print(json.dumps(rep, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q30/S29 soccer draw-aversion underpricing maker fill-sim (read-only)")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="pull settlement live from Kalshi and rewrite the cache first")
    ap.add_argument("--cache", default=str(CACHE_PATH))
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--min-interval", type=float, default=0.25)
    ap.add_argument("--n-boot", type=int, default=10000)
    args = ap.parse_args(argv)

    cache_path = Path(args.cache)
    if args.refresh_cache:
        tie_series = discover_tie_series(DEPTH_GLOB)
        print(f"[q30:cache] discovered {len(tie_series)} -TIE soccer series: {tie_series}")
        build_settlement_cache(tie_series, cache_path, limit=args.limit,
                               min_interval=args.min_interval)
    rep = run(cache_path=cache_path, n_boot=args.n_boot)
    _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""s14_queue_fillsim.py — S14 REVALIDATION: queue-aware fill-sim for the ladder
overround-underwriting trade, replacing S14's biased candlestick-through fill proxy
with the same real price-time-priority queue model S19 already shipped for its sibling.

WHY (L39): S14's headline (+$0.0925/contract, CI [+0.063,+0.123], n=300) rests on a
candlestick fill proxy — `max(price.high) >= posted ask AND volume > 0`. That proxy
credits the INCOME leg (premium collected) without proving our resting short-YES ever
reached the FRONT of the queue: a bar only proves the price PRINTED, not that a resting
maker offer at the BACK of an existing queue was actually lifted. Because a ladder P&L is
a small net of two large legs (Sigma premium ~ the $1 winner payout), a fill proxy that is
biased UP on the income leg silently biases the whole verdict positive (binding gate #2).
This probe swaps ONLY the fill-detection mechanism for the S19 queue-aware rule and re-runs
the SAME trade. DEAD is the fully expected outcome — every prior proxy->queue-aware
conversion in this repo (S13, S19, S21, S23) died. Report honestly.

THE TRADE (unchanged from s14_ladder_fillsim — imported, not re-derived):
Per settled crypto_hourly event-hour, entry = EARLIEST capture, held to close. Rest a maker
short-YES on EVERY priced-relevant member (yes_ask >= MIN_PRICED_ASK = 0.02; 1c-floor members
net $0 either way per L30 and are skipped) PLUS the winner strike regardless of its ask.

THE ONLY CHANGE — the fill rule. For EACH member, replace the candle-through proxy with the
S19 queue-aware test (imported `s19.is_filled`):
    filled iff (ask TOUCHED: candle max_high_dollars >= yes_ask)
               AND (executed candle total_volume >= queue_ahead)
where queue_ahead = `s19.queue_ahead_at(no_bids, yes_ask)` off the `orderbook_depth` no_bids
ladder (tag real_bid, the mirror of the YES-ask side), joined by ticker + NEAREST captured_at
within DEPTH_JOIN_MAX_DELTA_SEC (600s), and (max_high, total_volume) come OFFLINE from the
committed S14 candle cache `tape/s14_ladder_fillsim/` (keyed by ticker, NEVER re-fetched). The
cached window must align with entry (abs(start_ts - entry_ts) <= CANDLE_WINDOW_TOL_SEC), the
same guard S19 uses.

Per event-hour: premium_total = Sigma member_premium(ask) over members that PASS the queue-aware
fill test; payout = 1.0 iff the WINNER strike passes the queue-aware fill test; pnl =
premium_total - payout. Bootstrap E[pnl] BY EVENT-HOUR (L6 — one settlement fixes all winners
within an hour; strikes within an hour are correlated).

THE WINNER-LEG MEASURABILITY ASYMMETRY (load-bearing; binding gate #2):
  - NON-winner priced-relevant member: unmeasurable offline (no depth join OR no aligned
    candle) -> NO-FILL -> no premium collected. Conservative — never credit unprovable income.
  - WINNER strike: "unmeasurable -> no-fill" would OPTIMISTICALLY drop the catastrophic $1
    payout leg for free (FORBIDDEN). So an event-hour is bootstrap-ELIGIBLE only if the
    winner's leg is measurable (winner has BOTH a depth join within 600s AND an aligned candle
    record). If the winner leg is NOT measurable, DROP the entire event-hour from the bootstrap
    population (do NOT count it with payout=0). The drop is on MEASURABILITY (exogenous to
    settlement), never on the winner's fill status or settle direction — once measurable, the
    winner leg is ALWAYS evaluated and its payout ALWAYS included.
The winner is in the candle cache by construction (S14 fetched every winner), so the binding
winner-measurability constraint is the DEPTH join (depth tape starts 2026-07-07, crypto
2026-07-03 — L9; only the overlap is join-eligible). Coverage is reported honestly.

READ-ONLY, FULLY OFFLINE, NO NETWORK, NO ORDERS, NO AUTH, NO EXECUTION CODE. A stray
`dt=<date>` DIRECTORY (L25/L29) is skipped by the imported loaders' is_file guards.

Run:
    python scripts/s14_queue_fillsim.py --n-boot 10000 --json-out /tmp/s14_queue.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import bracket_sum, overround  # noqa: E402
from scripts.s14_ladder_fillsim import (  # noqa: E402  (REUSE, do not re-derive)
    FLOOR_ASK,
    MIN_PRICED_ASK,
    build_earliest_captures,
    build_settlement_map,
    frac_overround_on_1c_floor,
    load_records,
    member_coord,
    member_premium,
)
from scripts.s19_wing_fade_fillsim import (  # noqa: E402  (COPY the queue pattern)
    CANDLE_WINDOW_TOL_SEC,
    DEPTH_JOIN_MAX_DELTA_SEC,
    PRICE_TICK,
    build_depth_index,
    is_filled,
    load_candle_cache,
    nearest_no_bids,
    queue_ahead_at,
)

CRYPTO_DIR = REPO_ROOT / "tape" / "crypto_hourly"
DEPTH_DIR = REPO_ROOT / "tape" / "orderbook_depth"
CANDLE_CACHE_DIR = REPO_ROOT / "tape" / "s14_ladder_fillsim"

MIN_CI_UNITS = 10          # bootstrap_verdict_admissible floor (L41); also gate #3
S19_FILL_FLOOR = 0.0045    # the S19 0.45% near-zero-fill data-adequacy floor (gate #1)

# keep FLOOR_ASK importable/referenced (documents the L30 1c-floor skip we inherit from S14)
_ = FLOOR_ASK


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


# --------------------------------------------------------------------------- #
# queue-aware fill for one member (returns None == UNMEASURABLE offline)
# --------------------------------------------------------------------------- #
def member_queue_fill(
    o: Dict[str, Any],
    entry_ts: float,
    depth_idx: Dict[str, List[Tuple[float, List[Any]]]],
    candle_cache: Dict[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Queue-aware fill test for a single ladder member (L39, S19 mechanism).

    Returns None when the member is UNMEASURABLE offline — EITHER no depth capture within
    DEPTH_JOIN_MAX_DELTA_SEC of entry (queue unknown) OR no candle-cache record whose window
    aligns with entry (executed volume / touch unknown). Otherwise returns
    `{filled, queue_ahead, total_volume, max_high}` with `filled` from `s19.is_filled`
    (touched AND executed_volume >= queue_ahead). The None sentinel lets the caller apply the
    winner-vs-non-winner measurability asymmetry (drop the event-hour vs no-fill)."""
    tk = o["ticker"]
    ask = float(o["yes_ask"])
    no_bids = nearest_no_bids(depth_idx, tk, entry_ts)
    rec = candle_cache.get(tk)
    if no_bids is None or rec is None:
        return None
    start_ts = rec.get("start_ts")
    if start_ts is None or abs(float(start_ts) - entry_ts) > CANDLE_WINDOW_TOL_SEC:
        return None
    queue_ahead = queue_ahead_at(no_bids, ask)
    total_volume = rec.get("total_volume")
    max_high = rec.get("max_high_dollars")
    filled = is_filled(max_high, total_volume, ask, queue_ahead)
    return {"filled": filled, "queue_ahead": queue_ahead,
            "total_volume": total_volume, "max_high": max_high}


# --------------------------------------------------------------------------- #
# per-event-hour simulation (structural template = s14.simulate_event; ONLY the
# fill-detection mechanism is swapped for the queue-aware test)
# --------------------------------------------------------------------------- #
def simulate_event_queue(
    event_ticker: str,
    entry: Dict[str, Any],
    settlement: Dict[str, Any],
    depth_idx: Dict[str, List[Tuple[float, List[Any]]]],
    candle_cache: Dict[str, Dict[str, Any]],
    min_priced_ask: float = MIN_PRICED_ASK,
) -> Optional[Dict[str, Any]]:
    """One row per settled event-hour. Returns None on a structural skip (no close, bad
    horizon, winner not in the ladder). Otherwise returns a row carrying a
    `winner_measurable` flag: rows with winner_measurable==False are DROPPED from the
    bootstrap population (winner-leg unmeasurability, exogenous to settlement — gate #2), but
    are still reported for honest join coverage. pnl is only meaningful when winner_measurable."""
    cur = entry["current"]
    outs = cur["outcomes"]
    close_time = cur.get("close_time")
    if not close_time:
        return None
    try:
        entry_ts = _parse_ts(entry["captured_at"])
        end_ts = _parse_ts(close_time)
    except (ValueError, KeyError, TypeError):
        return None
    if end_ts <= entry_ts:
        return None

    winner_ticker = settlement["winner_ticker"]
    winner_out = next((o for o in outs if o.get("ticker") == winner_ticker), None)
    if winner_out is None:
        return None  # winner strike absent from the captured ladder — cannot evaluate the leg

    asks = [float(o["yes_ask"]) for o in outs]
    bsum = bracket_sum(asks)
    ovr = overround(asks)

    # Evaluate the WINNER leg first — it decides bootstrap eligibility (measurability, NOT fill).
    winner_res = member_queue_fill(winner_out, entry_ts, depth_idx, candle_cache)
    winner_measurable = winner_res is not None
    winner_filled = bool(winner_res["filled"]) if winner_measurable else False

    premium_total = 0.0
    n_filled = 0
    n_priced_relevant = 0
    n_joinable = 0
    winner_ask = float(winner_out["yes_ask"])
    for o in outs:
        ask = float(o["yes_ask"])
        tk = o["ticker"]
        is_winner = tk == winner_ticker
        if ask < min_priced_ask and not is_winner:
            continue  # 1c-floor wing, nets $0 either way (L30) — no premium, not fetched
        n_priced_relevant += 1
        res = winner_res if is_winner else member_queue_fill(o, entry_ts, depth_idx,
                                                             candle_cache)
        if res is None:
            continue  # non-winner unmeasurable -> NO-FILL (conservative; never credit unproven)
        n_joinable += 1
        if res["filled"]:
            n_filled += 1
            premium_total += member_premium(ask)

    payout = 1.0 if (winner_measurable and winner_filled) else 0.0
    pnl = premium_total - payout
    return {
        "event_ticker": event_ticker,
        "series": entry.get("series"),
        "captured_at": entry["captured_at"],
        "close_time": close_time,
        "horizon_min": (end_ts - entry_ts) / 60.0,
        "n_members": len(outs),
        "bracket_sum": bsum,
        "overround": ovr,
        "frac_overround_on_1c_floor": frac_overround_on_1c_floor(outs),
        "n_priced_relevant": n_priced_relevant,
        "n_joinable": n_joinable,
        "n_filled": n_filled,
        "winner_ticker": winner_ticker,
        "winner_ask": winner_ask,
        "winner_measurable": winner_measurable,
        "winner_filled": winner_filled,
        "premium_collected": premium_total,
        "payout": payout,
        "pnl": pnl,
        "price_source_tag": "real_ask+real_bid+broker_truth",
    }


def pnl_by_event(rows: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Block-bootstrap unit = event-hour (L6). ONLY winner-measurable rows enter the
    population (winner-unmeasurable event-hours are dropped, gate #2)."""
    return {r["event_ticker"]: [r["pnl"]] for r in rows if r["winner_measurable"]}


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _pct(num: float, den: float) -> str:
    return f"{(100.0 * num / den):.2f}%" if den else "n/a"


def _fmt_ci(ci: List[Optional[float]]) -> str:
    if not ci or ci[0] is None:
        return "[None, None]"
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="S14 queue-aware ladder-underwriting fill-sim (read-only, OFFLINE, "
                    "revalidates the S14 candle-proxy result)")
    ap.add_argument("--crypto-dir", default=str(CRYPTO_DIR))
    ap.add_argument("--depth-dir", default=str(DEPTH_DIR))
    ap.add_argument("--candle-cache-dir", default=str(CANDLE_CACHE_DIR))
    ap.add_argument("--min-priced-ask", type=float, default=MIN_PRICED_ASK)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    records = load_records(Path(args.crypto_dir))
    settle = build_settlement_map(records)
    earliest = build_earliest_captures(records)
    depth_idx = build_depth_index(Path(args.depth_dir))
    candle_cache = load_candle_cache(Path(args.candle_cache_dir))

    sim_events = sorted(et for et in earliest if et in settle)

    rows: List[Dict[str, Any]] = []
    for et in sim_events:
        row = simulate_event_queue(et, earliest[et], settle[et], depth_idx, candle_cache,
                                   min_priced_ask=args.min_priced_ask)
        if row is not None:
            rows.append(row)

    n_settled_simulatable = len(rows)
    measurable_rows = [r for r in rows if r["winner_measurable"]]
    n_measurable = len(measurable_rows)
    n_dropped_winner_unmeasurable = n_settled_simulatable - n_measurable

    # fill-rate + coverage aggregates over the MEASURABLE population (the trading population)
    tot_priced_relevant = sum(r["n_priced_relevant"] for r in measurable_rows)
    tot_joinable = sum(r["n_joinable"] for r in measurable_rows)
    tot_filled = sum(r["n_filled"] for r in measurable_rows)
    fill_rate_priced_relevant = (tot_filled / tot_priced_relevant) if tot_priced_relevant else 0.0
    fill_rate_joinable = (tot_filled / tot_joinable) if tot_joinable else 0.0
    winner_fill_rate = (sum(1 for r in measurable_rows if r["winner_filled"]) / n_measurable
                        if n_measurable else 0.0)

    # coverage fractions (gate #4)
    eventhour_winner_coverage = (n_measurable / n_settled_simulatable
                                 if n_settled_simulatable else 0.0)
    member_join_coverage = (tot_joinable / tot_priced_relevant) if tot_priced_relevant else 0.0

    # bootstrap E[pnl] by event-hour over the measurable population (gate #3)
    blocks = pnl_by_event(rows)
    boot = block_bootstrap(blocks, n_boot=args.n_boot)
    ci = boot["ci95"]
    lo = ci[0]
    n_units = boot["n_units"]
    adm = bootstrap_verdict_admissible(blocks, min_units=MIN_CI_UNITS)
    clears_mag = clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0)
    positive = lo is not None and lo > 0.0

    # verdict (explicit outcomes)
    if n_measurable == 0 or n_units == 0:
        verdict = "INCONCLUSIVE_DATA_ADEQUACY"
    elif tot_filled == 0:
        verdict = "DEAD_ZERO_FILL"
    elif fill_rate_priced_relevant <= S19_FILL_FLOOR:
        verdict = "DEAD_NEAR_ZERO_FILL_DATA_ADEQUACY"
    elif positive and adm["admissible"] and clears_mag:
        verdict = "ALIVE_UNEXPECTED"
    elif positive:
        verdict = "DEAD_CI_OR_MAGNITUDE"   # lo>0 but fails admissibility or magnitude gate
    else:
        verdict = "DEAD"                    # CI not strictly > 0 — the edge death

    mean_overround = (sum(r["overround"] for r in measurable_rows) / n_measurable
                      if n_measurable else float("nan"))
    mean_bsum = (sum(r["bracket_sum"] for r in measurable_rows) / n_measurable
                 if n_measurable else float("nan"))
    mean_premium = (sum(r["premium_collected"] for r in measurable_rows) / n_measurable
                    if n_measurable else float("nan"))
    mean_payout = (sum(r["payout"] for r in measurable_rows) / n_measurable
                   if n_measurable else float("nan"))

    print("=" * 82)
    print("S14 QUEUE-AWARE LADDER-UNDERWRITING FILL-SIM (read-only, OFFLINE) — REVALIDATION")
    print("  swaps ONLY the fill rule: candle-through proxy -> S19 price-time-priority queue")
    print("=" * 82)
    print(f"crypto records: {len(records)}  settled event-hours: {len(settle)}  "
          f"depth tickers: {len(depth_idx)}  candle-cache tickers: {len(candle_cache)}")
    print(f"simulatable event-hours (earliest cap ∩ settled ∩ winner-in-ladder): "
          f"{n_settled_simulatable}")
    print("-" * 82)
    print("WINNER-LEG MEASURABILITY ASYMMETRY (gate #2):")
    print(f"  winner-measurable event-hours = {n_measurable}/{n_settled_simulatable} "
          f"({_pct(n_measurable, n_settled_simulatable)})")
    print(f"  DROPPED for winner-unmeasurability = {n_dropped_winner_unmeasurable} "
          f"(NOT counted with payout=0; drop is on measurability, exogenous to settlement)")
    print("  [depth tape starts 2026-07-07 vs crypto 2026-07-03 (L9) — only the overlap joins]")
    print("-" * 82)
    print("JOIN COVERAGE (gate #4):")
    print(f"  (a) event-hour winner-leg coverage = {eventhour_winner_coverage:.4f} "
          f"({n_measurable}/{n_settled_simulatable})")
    print(f"  (b) member-level join coverage among priced-relevant = {member_join_coverage:.4f} "
          f"({tot_joinable}/{tot_priced_relevant})")
    print("-" * 82)
    print("QUEUE-AWARE FILL RATE (gate #1 — vs the S19 0.45% floor):")
    print(f"  fills = {tot_filled}   among priced-relevant = {fill_rate_priced_relevant:.4f} "
          f"({_pct(tot_filled, tot_priced_relevant)})   among joinable = "
          f"{fill_rate_joinable:.4f} ({_pct(tot_filled, tot_joinable)})")
    print(f"  S19 floor = {S19_FILL_FLOOR:.4f} (0.45%): "
          f"{'AT/BELOW -> data-adequacy DEAD' if fill_rate_priced_relevant <= S19_FILL_FLOOR else 'ABOVE (per L53 a long resting window fills high; expect an EDGE death, not adequacy)'}")
    print(f"  winner-strike fill rate (measurable event-hours) = {winner_fill_rate:.4f} "
          f"({_pct(sum(1 for r in measurable_rows if r['winner_filled']), n_measurable)})")
    print("-" * 82)
    print("LEG DECOMPOSITION (measurable population; queue-aware):")
    print(f"  mean bracket_sum={mean_bsum:.3f}  mean overround={mean_overround:.3f}")
    print(f"  mean premium collected (income leg) = {mean_premium:+.4f}")
    print(f"  mean payout (winner $1 loss leg)    = {mean_payout:+.4f}")
    print("-" * 82)
    print("GATE (block-bootstrap E[P&L] BY EVENT-HOUR, net of the flat 1c maker fee, L6/L27/L41):")
    mean_str = "None" if boot["mean"] is None else f"{boot['mean']:+.4f}"
    print(f"  mean={mean_str}  95% CI={_fmt_ci(ci)}  n_units(event-hours)={n_units}  "
          f"n_obs={boot['n_obs']}  n_boot={args.n_boot}")
    print(f"  admissible (L41, min_units={MIN_CI_UNITS}): {adm['admissible']}  "
          f"n_opposing_units={adm['n_opposing_units']}  reasons={adm['reasons']}")
    print(f"  L27 magnitude gate (lower bound >= 1 tick $0.01): "
          f"{'CLEARS' if clears_mag else 'does NOT clear'}")
    print("-" * 82)
    print(f"S14 candle-proxy headline being revalidated: +$0.0925/contract, "
          f"CI [+0.063,+0.123], n=300")
    print(f"VERDICT: {verdict}")
    if verdict == "DEAD":
        print("  -> queue-aware CI is not strictly > 0: with the biased income-leg proxy "
              "removed, the winner fills and costs $1 while queue-aware premium collection "
              "collapses. The candle-proxy edge was an L39 artifact. Falsified.")
    elif verdict == "DEAD_CI_OR_MAGNITUDE":
        print("  -> lower bound > 0 but fails admissibility (L41) or the L27 magnitude gate. "
              "Not a verdict-grade edge. Falsified.")
    elif verdict == "DEAD_NEAR_ZERO_FILL_DATA_ADEQUACY":
        print("  -> fill rate at/below the S19 0.45% floor: data-adequacy dead, not a CI.")
    elif verdict == "DEAD_ZERO_FILL":
        print("  -> zero queue-aware fills across the measurable population.")
    elif verdict == "INCONCLUSIVE_DATA_ADEQUACY":
        print("  -> no measurable event-hours (depth/candle join too thin). Untestable as "
              "collected; NOT a falsification.")
    else:  # ALIVE_UNEXPECTED
        print("  -> !!! CI > 0 AND admissible AND clears magnitude over a testable population. "
              "This would be the project's FIRST proven edge — EXTRAORDINARY. Do NOT trade; "
              "escalate and scrutinize (a proxy->queue conversion has never lived before).")
    print("=" * 82)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "probe": "s14_queue_fillsim",
        "revalidates": {"strategy": "S14", "candle_proxy_headline_per_contract": 0.0925,
                        "candle_proxy_ci95": [0.063, 0.123], "candle_proxy_n": 300},
        "fill_rule": "queue_aware: touched(max_high>=ask) AND executed_vol>=queue_ahead "
                     "(no_bids at price>=1-ask); NOT a candle print (L39)",
        "price_source_tags": {"asks": "real_ask", "queue_depth": "real_bid(mirror no_bids)",
                              "executed_volume": "real_ask(s14 candle cache)",
                              "settlement": "broker_truth"},
        "n_records": len(records), "n_settled": len(settle),
        "n_settled_simulatable": n_settled_simulatable,
        "n_measurable_event_hours": n_measurable,
        "n_dropped_winner_unmeasurable": n_dropped_winner_unmeasurable,
        "coverage": {"eventhour_winner_leg": eventhour_winner_coverage,
                     "member_level_priced_relevant": member_join_coverage,
                     "l9_caveat": "depth 2026-07-07+ vs crypto 2026-07-03+; only overlap joins"},
        "fill": {"n_filled": tot_filled,
                 "fill_rate_priced_relevant": fill_rate_priced_relevant,
                 "fill_rate_joinable": fill_rate_joinable,
                 "winner_fill_rate": winner_fill_rate,
                 "s19_floor": S19_FILL_FLOOR},
        "legs": {"mean_bracket_sum": mean_bsum, "mean_overround": mean_overround,
                 "mean_premium_collected": mean_premium, "mean_payout": mean_payout},
        "bootstrap": {"mean": boot["mean"], "ci95": ci, "n_units": n_units,
                      "n_obs": boot["n_obs"], "n_boot": args.n_boot,
                      "admissible": adm["admissible"],
                      "n_opposing_units": adm["n_opposing_units"],
                      "admissible_reasons": adm["reasons"],
                      "clears_tick_magnitude": clears_mag},
        "verdict": verdict,
        "rows": rows,
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"[s14_queue_fillsim] wrote {args.json_out}")
    # keep member_coord referenced (imported per the reuse contract; ladder-coord helper)
    _ = member_coord
    return 0


if __name__ == "__main__":
    sys.exit(main())

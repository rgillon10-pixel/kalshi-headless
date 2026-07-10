#!/usr/bin/env python3
"""sports_clv_s7.py — Q4/S7b: build the CLV trade set (Kalshi ask vs de-vig fair).

S7's binding test needs three stages (queue Q4): S7a sourced the historical dataset
(97 World Cup 2026 games, `tape/sports_history_s7/worldcup2026.jsonl`). This stage
(S7b) turns that tape into a TRADE SET — a decision-time real_ask per outcome, a
de-vigged sharp fair probability, a fee-aware net P&L per candidate trade — but does
NOT bootstrap a confidence interval or declare a verdict; that is S7c, next stage,
"one stage per run" (LOOP-QUEUE.md). This script is pure post-processing of already-
captured tape: no network calls.

================================================================================
DECISION-TIME DEFINITION (documented precisely, honest about its limitation)
================================================================================
football-data.co.uk's H-Avg/D-Avg/A-Avg are CLOSING odds — the sharp-consensus price
right at kickoff. We do not have an exact kickoff timestamp in the tape (Kalshi's
market `open_time`/`close_time` bracket the whole trading window, not kickoff), so we
approximate it: empirically (spot-checked against captured candles, e.g. the France
vs Morocco Reg-Time market) a "Reg Time" moneyline's `close_time` lands within minutes
of the final whistle, and regulation + stoppage time is consistently under ~2h. We
therefore define:

    decision_ts := close_time - DECISION_OFFSET_HOURS   (default 4h)

as a conservative, reproducible, pre-kickoff snapshot — safely before lineups/team
news (~1h pre-kickoff) and comfortably before the final whistle, at the cost of not
landing exactly at the football-data closing-line instant (our snapshot is earlier
than "closing", so any market drift between decision_ts and true kickoff is priced
into OUR entry but not into the sharp "closing" comparator — a real, stated limitation,
not hidden). A precise kickoff feed would tighten this; none is free.

The tradeable price at decision_ts is the LAST candle (by `end_period_ts`) at or
before decision_ts — a strictly causal, no-look-ahead read, same discipline as S1's
T-24h rule. If no candle exists at or before decision_ts (the 7-day candle-window cap
from S7a bit and decision_ts falls earlier than the earliest captured candle), that
OUTCOME is unusable and the whole game is dropped (a 2-of-3-legs bracket_sum would
mis-normalize the overround) — logged as `missing_decision_candle`, never silently
substituted.

================================================================================
TRADE RULE
================================================================================
Single-leg, BUY YES only (S7's stated design: "single-leg directional"). For each of
a game's 3 mutually-exclusive outcome markets (home/away/tie), compare the sharp
de-vigged fair probability (`synthetic`, from S7a's football-data closing-odds leg)
against Kalshi's own bracket-normalized implied probability (Hard Rule #3:
`core.pricing.normalized_ask`, never the raw ask). If fair > normalized_ask (sharp
consensus says this outcome is MORE likely than Kalshi's ladder implies), the outcome
is a nominal-edge candidate; `--min-edge` (default 0.0) sets how large that nominal
gap must be before it becomes a trade. The ACTUAL fill price paid, and the ACTUAL P&L,
uses the raw per-outcome ask (`raw_yes_ask`) — never the normalized probability
(Hard Rule #3 governs reading a probability off an ask; it does not relabel the ask
itself as something other than the price you pay).

Fee model: `scripts.fee_breakeven.fee_per_contract`, taker rate 0.07, same formula as
every other probe in this repo (`fee = ceil_cent(0.07 * p * (1-p))`).

Net P&L per trade = payoff(1 if outcome settled 'yes' else 0) - raw_yes_ask - fee.

No bootstrap here. This stage reports the raw signal (n trades, mean nominal edge,
mean gross/net P&L) so S7c can decide whether a block-bootstrap by game is even worth
running before committing to that stage's CI math.

Run:
    python -m scripts.sports_clv_s7                  # full pass over S7a's tape
    python -m scripts.sports_clv_s7 --min-edge 0.02   # require 2c nominal edge
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.canonical import canonical_json
from core.io import REPO_ROOT
from core.pricing import bracket_sum, normalized_ask, overround
from core.timeutil import _parse_iso
from scripts.fee_breakeven import fee_per_contract
from scripts.sports_history_s7a import TEAM_NAME_ALIASES  # reuse the one alias table

IN_PATH = REPO_ROOT / "tape" / "sports_history_s7" / "worldcup2026.jsonl"
STORE = REPO_ROOT / "tape" / "sports_clv_s7"
SCHEMA_VERSION = "sports_clv_s7.v0"
DECISION_OFFSET_HOURS = 4.0
TAKER_FEE_RATE = 0.07
SIDES = ("home", "away", "tie")


def _slug(name: str) -> str:
    canon = TEAM_NAME_ALIASES.get(name, name)
    import re
    return re.sub(r"[^a-z0-9]", "", canon.lower())


# --------------------------------------------------------------------------- #
# tape loading
# --------------------------------------------------------------------------- #
def load_tape(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    if not path.exists():
        return records
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def dedupe_latest(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """S7a appends every run; a re-run may re-source the same settled game. Keep the
    lexicographically-latest `run_id` per `kalshi_event_ticker` (run_id is a sortable
    `YYYYMMDDTHHMMSSZ` string), so a stale duplicate pass never doubles a game's trades."""
    best: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        key = rec.get("kalshi_event_ticker", "")
        cur = best.get(key)
        if cur is None or rec.get("run_id", "") > cur.get("run_id", ""):
            best[key] = rec
    return list(best.values())


# --------------------------------------------------------------------------- #
# outcome -> side mapping
# --------------------------------------------------------------------------- #
def map_outcome_side(yes_sub_title: str, home_team: str, away_team: str) -> Optional[str]:
    """'Reg Time: <Team>' / 'Reg Time: Tie' -> 'home'/'away'/'tie'. None if the
    sub-title names neither team (an outcome the caller must treat as unusable, not
    guess at)."""
    sub = (yes_sub_title or "").strip()
    if sub.lower().endswith("tie"):
        return "tie"
    prefix = "reg time:"
    if sub.lower().startswith(prefix):
        name = sub[len(prefix):].strip()
    else:
        name = sub
    slug = _slug(name)
    if slug == _slug(home_team):
        return "home"
    if slug == _slug(away_team):
        return "away"
    return None


# --------------------------------------------------------------------------- #
# decision-time candle selection
# --------------------------------------------------------------------------- #
def decision_candle(candles: List[Dict[str, Any]], decision_ts: int) -> Optional[Dict[str, Any]]:
    """Last candle (by end_period_ts) at or before decision_ts — causal, no look-ahead.
    None if every candle is strictly after decision_ts (the outcome has no price yet
    at decision time, or the captured window was truncated past it)."""
    eligible = [c for c in candles if int(c["end_period_ts"]) <= decision_ts]
    if not eligible:
        return None
    return max(eligible, key=lambda c: int(c["end_period_ts"]))


# --------------------------------------------------------------------------- #
# per-game trade construction
# --------------------------------------------------------------------------- #
def build_game_trades(record: Dict[str, Any], min_edge: float,
                      decision_offset_hours: float = DECISION_OFFSET_HOURS
                      ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Returns (trades, drop_reason). drop_reason is None iff the game's bracket was
    usable (all 3 legs mapped + candled); trades may still be [] if no leg cleared
    min_edge — a usable game with zero trades is not a drop."""
    odds_match = record.get("odds_match") or {}
    if not odds_match.get("matched"):
        return [], "odds_unmatched"

    outcomes = record.get("outcomes") or []
    if len(outcomes) != 3:
        return [], f"unexpected_outcome_count={len(outcomes)}"

    home_team, away_team = record.get("home_team", ""), record.get("away_team", "")
    close_times = {o.get("close_time", "") for o in outcomes}
    if len(close_times) != 1 or not next(iter(close_times)):
        return [], "inconsistent_close_time"
    close_ts = int(_parse_iso(next(iter(close_times))).timestamp())
    decision_ts = close_ts - int(decision_offset_hours * 3600)

    by_side: Dict[str, Dict[str, Any]] = {}
    for o in outcomes:
        side = map_outcome_side(o.get("yes_sub_title", ""), home_team, away_team)
        if side is None:
            return [], f"unmapped_outcome_side:{o.get('yes_sub_title', '')!r}"
        if side in by_side:
            return [], f"duplicate_side:{side}"
        by_side[side] = o
    if set(by_side) != set(SIDES):
        return [], f"incomplete_side_set:{sorted(by_side)}"

    candle_by_side: Dict[str, Dict[str, Any]] = {}
    for side, o in by_side.items():
        candle = decision_candle(o.get("candles") or [], decision_ts)
        if candle is None:
            return [], f"missing_decision_candle:{side}"
        candle_by_side[side] = candle

    fair_by_side = {
        "home": odds_match.get("fair_home"),
        "away": odds_match.get("fair_away"),
        "tie": odds_match.get("fair_draw"),
    }
    if any(fair_by_side[s] is None for s in SIDES):
        return [], "incomplete_fair_probs"

    entry_price_by_side = {
        side: float(candle_by_side[side]["yes_ask"]["close_dollars"]) for side in SIDES
    }
    bsum = bracket_sum(entry_price_by_side[s] for s in SIDES)
    if bsum <= 0:
        return [], "non_positive_bracket_sum"

    trades: List[Dict[str, Any]] = []
    for side in SIDES:
        entry_price = entry_price_by_side[side]
        norm_ask = normalized_ask(entry_price, bsum)
        fair_prob = float(fair_by_side[side])
        edge = fair_prob - norm_ask
        if edge <= min_edge:
            continue

        o = by_side[side]
        result = (o.get("result") or "").strip().lower()
        if result not in ("yes", "no"):
            continue  # unsettled/ambiguous leg — not a usable trade, game not dropped
        payoff = 1.0 if result == "yes" else 0.0
        fee = fee_per_contract(entry_price, TAKER_FEE_RATE)
        gross_pnl = payoff - entry_price
        net_pnl = gross_pnl - fee

        trades.append({
            "schema_version": SCHEMA_VERSION,
            "kalshi_event_ticker": record.get("kalshi_event_ticker", ""),
            "market_ticker": o.get("market_ticker", ""),
            "side": side,
            "home_team": home_team, "away_team": away_team,
            "decision_ts": decision_ts,
            "decision_candle_end_period_ts": int(candle_by_side[side]["end_period_ts"]),
            "raw_yes_ask": entry_price,
            "bracket_sum": bsum,
            "overround_absorbed": overround(entry_price_by_side[s] for s in SIDES),
            "member_count": len(SIDES),
            "normalized_ask": norm_ask,
            "fair_prob": fair_prob,
            "nominal_edge": edge,
            "fee": fee,
            "result": result,
            "gross_pnl": gross_pnl,
            "net_pnl": net_pnl,
            "price_source_tag_kalshi": "real_ask",
            "price_source_tag_odds": "synthetic",
            "models_json": {
                "odds_model": "football_data_devig_multiplicative",
                "decision_offset_hours": decision_offset_hours,
                "fee_rate": TAKER_FEE_RATE,
            },
        })
    return trades, None


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def run(in_path: Optional[Path] = None, store: Optional[Path] = None,
        min_edge: float = 0.0, decision_offset_hours: float = DECISION_OFFSET_HOURS
        ) -> Dict[str, Any]:
    in_path = Path(in_path) if in_path is not None else IN_PATH
    store = Path(store) if store is not None else STORE

    records = dedupe_latest(load_tape(in_path))
    all_trades: List[Dict[str, Any]] = []
    drop_reasons: Dict[str, int] = {}
    n_usable_games = 0

    for rec in records:
        trades, drop_reason = build_game_trades(rec, min_edge, decision_offset_hours)
        if drop_reason is not None:
            drop_reasons[drop_reason.split(":")[0]] = drop_reasons.get(drop_reason.split(":")[0], 0) + 1
            continue
        n_usable_games += 1
        all_trades.extend(trades)

    n_trades = len(all_trades)
    mean_edge = sum(t["nominal_edge"] for t in all_trades) / n_trades if n_trades else None
    mean_gross = sum(t["gross_pnl"] for t in all_trades) / n_trades if n_trades else None
    mean_net = sum(t["net_pnl"] for t in all_trades) / n_trades if n_trades else None
    mean_overround = (sum(t["overround_absorbed"] for t in all_trades) / n_trades
                      if n_trades else None)
    n_games_win = len({t["kalshi_event_ticker"] for t in all_trades})

    store.mkdir(parents=True, exist_ok=True)
    out_path = store / "trades.jsonl"
    with open(out_path, "w") as f:
        for t in all_trades:
            f.write(canonical_json(t) + "\n")

    summary = {
        "schema_version": SCHEMA_VERSION,
        "n_games_in_tape": len(records),
        "n_games_usable": n_usable_games,
        "n_games_dropped": len(records) - n_usable_games,
        "drop_reasons": drop_reasons,
        "min_edge": min_edge,
        "decision_offset_hours": decision_offset_hours,
        "n_trades": n_trades,
        "n_games_with_a_trade": n_games_win,
        "mean_nominal_edge": mean_edge,
        "mean_gross_pnl": mean_gross,
        "mean_net_pnl": mean_net,
        "mean_overround_absorbed": mean_overround,
        "out_path": str(out_path),
        "note": "point estimate only, NOT bootstrapped — S7c runs the block-bootstrap "
                "by game and the verdict.",
    }
    (store / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"[sports_clv_s7] {n_usable_games}/{len(records)} games usable "
          f"(dropped: {drop_reasons}), {n_trades} candidate trades across "
          f"{n_games_win} games, mean_net_pnl={mean_net}, "
          f"mean_overround_absorbed={mean_overround} -> {out_path}")
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S7b CLV trade-set construction (offline, no network)")
    ap.add_argument("--in-path", default=None)
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--min-edge", type=float, default=0.0,
                    help="minimum nominal (pre-fee) edge to count as a trade")
    ap.add_argument("--decision-offset-hours", type=float, default=DECISION_OFFSET_HOURS)
    args = ap.parse_args(argv)
    run(in_path=Path(args.in_path) if args.in_path else None,
        store=Path(args.out_dir) if args.out_dir else None,
        min_edge=args.min_edge, decision_offset_hours=args.decision_offset_hours)
    return 0


if __name__ == "__main__":
    sys.exit(main())

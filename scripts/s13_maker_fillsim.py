#!/usr/bin/env python3
"""s13_maker_fillsim.py — S13: maker-side (bid) fill-sim on the proven S7 sports rich-ask.

LOOP-QUEUE.md Q9. S7c proved the TAKER side is DEAD: buying Kalshi's pregame ask runs
+2.35c rich vs DraftKings-devig fair (95% CI [-0.0245,-0.0225], n=80 games/237 outcomes,
`scripts/s7c_sports_clv_bootstrap.py`). A rich ask is exactly the mirror-image setup for a
MAKER: instead of paying the rich ask, rest a bid below the DK-devig fair and let someone
else cross the spread into you. This script papers that strategy — no order code, read-only
analysis over already-captured tape plus one new (read-only, cached) Kalshi data pull.

Design (matches `kb/strategies/00-index.md` S13's own spec):
  - bid_price = fair_prob (DraftKings-close devig, S7c's already-proven fair anchor) - 1c,
    clamped to Kalshi's tradeable [0.01, 0.99].
  - fill = does the market ever TRADE at or below bid_price between the market's open_time
    and the game's actual kickoff (ESPN's kickoff, same anchor S7b/S7c use — not Kalshi's own
    `close_time`, which is resolution time, see `sports_history.py`'s "second trap")? Read off
    hourly candlestick `price.low_dollars` (the realized trade low each hour, NOT the ask
    low — a trade at/below bid_price is what actually crosses into a resting bid).
  - fill rate = fraction of priced (game, outcome) pairs that filled.
  - edge_after_fee, CONDITIONAL ON FILL, uses fair_prob (DK-close devig) as the fair anchor
    — same anchor S7c already validated, so a filled maker bid inherits the same proven edge
    estimate, net of Kalshi's taker-side-equivalent fee on the bid price.

Honest adverse-selection check (Q9's own ask: "compare fair-at-fill vs fair-at-entry, never
assume the entry edge survives the fill"): the resting bid can only be INFORMED, at the
moment it is placed (market open, days before kickoff for World Cup markets), by whatever
line existed then — DraftKings' OPENING moneyline, not the closing one S7c/the bid price
itself uses. `fair_entry` = devig(DK open line); `fair_fill` = devig(DK close line) = the
same `fair_prob` already in the `sports_clv_join.v1` record. The gap between them is exactly
how much the "true" fair moved between entry and (the neighborhood of) a fill — a real,
measurable adverse-selection signal from data already in `tape/sports_history/`, no new ESPN
pull needed. This is a proxy (we don't know the *instant* of fill, only that one occurred
somewhere in the window), stated plainly, not smoothed over.

Two data legs, both already partially captured:
  - `tape/sports_clv/*.jsonl` (`sports_clv_join.v1`, built by S7b/S7c): matched game, per-
    outcome ticker/fair_key/fair_prob(close-devig)/pregame_ask.
  - `tape/sports_history/*.jsonl` (`sports_history_kalshi.v1` for each ticker's open_time,
    `sports_history_espn.v1` for the raw DK open+close moneyline).
  - NEW: hourly candlesticks for each priced outcome ticker, `open_time` -> kickoff, fetched
    live (read-only GET, cached to `tape/sports_maker_fillsim/` so reruns don't re-hit Kalshi
    for a game already resolved).

Run:
    python scripts/s13_maker_fillsim.py
    python scripts/s13_maker_fillsim.py --n-boot 20000 --json-out /tmp/s13.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collection.sports_history import american_to_decimal  # noqa: E402
from collection.sports_pairs import devig_multiplicative  # noqa: E402
from core.canonical import canonical_json, sha256_hex  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import fee_per_contract  # noqa: E402
from scripts.s7c_sports_clv_bootstrap import block_bootstrap, load_games  # noqa: E402

CLV_TAPE_GLOB = str(REPO_ROOT / "tape" / "sports_clv" / "dt=*.jsonl")
HISTORY_TAPE_GLOB = str(REPO_ROOT / "tape" / "sports_history" / "dt=*.jsonl")
CANDLES_CACHE_DIR = REPO_ROOT / "tape" / "sports_maker_fillsim"
BID_OFFSET = 0.01
MIN_PRICE, MAX_PRICE = 0.01, 0.99
# A resting bid that gets filled is a MAKER fill, not a taker one — Kalshi's published fee
# schedule (kb/kalshi-api/03-fees-and-breakeven.md) charges 0.0175, a quarter of the 0.07
# taker rate `core.pricing.fee_per_contract`'s own default models. Passing that default here
# unmodified would silently overcharge every simulated fill by 4x its real fee.
MAKER_FEE_RATE = 0.0175


# --------------------------------------------------------------------------- #
# load the two already-captured legs
# --------------------------------------------------------------------------- #
def load_history_records(tape_glob: str = HISTORY_TAPE_GLOB) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(tape_glob)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
    return out


def kalshi_outcome_windows(history_records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{outcome_ticker: {open_time, close_time, series}}`, deduped by (ticker), keeping the
    record from the most recent `capture_id` (a game may have been captured more than once
    across day-files as more of the tournament settled)."""
    best_capture: Dict[str, str] = {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in history_records:
        if r.get("schema_version") != "sports_history_kalshi.v1":
            continue
        cap = r.get("capture_id", "")
        for o in r.get("outcomes", []):
            ticker = o.get("ticker")
            if not ticker or not o.get("open_time"):
                continue
            if ticker in best_capture and cap <= best_capture[ticker]:
                continue
            best_capture[ticker] = cap
            out[ticker] = {"open_time": o["open_time"], "close_time": o.get("close_time"),
                          "series": r.get("series")}
    return out


def espn_moneylines(history_records: List[Dict[str, Any]]) -> Dict[Any, Dict[str, Any]]:
    """`{espn_event_id: moneyline_dict}` (raw, both open+close legs), deduped keeping the
    most recent `capture_id`."""
    best_capture: Dict[Any, str] = {}
    out: Dict[Any, Dict[str, Any]] = {}
    for r in history_records:
        if r.get("schema_version") != "sports_history_espn.v1":
            continue
        eid = r.get("espn_event_id")
        ml = r.get("moneyline")
        if eid is None or not ml:
            continue
        cap = r.get("capture_id", "")
        if eid in best_capture and cap <= best_capture[eid]:
            continue
        best_capture[eid] = cap
        out[eid] = ml
    return out


# --------------------------------------------------------------------------- #
# fair-at-entry (DK OPEN devig) — the adverse-selection comparison leg
# --------------------------------------------------------------------------- #
def devig_fair_probs(moneyline: Optional[Dict[str, Any]], suffix: str) -> Optional[Dict[str, float]]:
    """De-vig DK's `{suffix}` (open|close) leg into fair probs, keyed home/away[/draw] —
    mirrors `sports_history.devig_closing_fair_probs` but parameterized so the same logic
    covers both legs (no duplicated de-vig call). `synthetic` (CLAUDE.md: a de-vig is a
    model, never a fill) — caller tags it."""
    if not moneyline:
        return None
    keys = ["home", "away"] + (["draw"] if f"draw_{suffix}" in moneyline else [])
    raw = [moneyline.get(f"{k}_{suffix}") for k in keys]
    if any(r is None for r in raw):
        return None
    fair = devig_multiplicative([american_to_decimal(r) for r in raw])
    return dict(zip(keys, fair))


def bid_price_for(fair_prob: float, offset: float = BID_OFFSET) -> float:
    """Resting-bid quote: fair minus one cent, clamped to Kalshi's tradeable range."""
    p = round(fair_prob - offset, 2)
    return min(max(p, MIN_PRICE), MAX_PRICE)


# --------------------------------------------------------------------------- #
# fill detection — live (cached) Kalshi candlesticks, open_time -> kickoff
# --------------------------------------------------------------------------- #
def fetch_candles_default(series: str, ticker: str, start_ts: int, end_ts: int) -> Dict[str, Any]:
    """Live GET of hourly candlesticks (read-only market data, no auth). Isolated as its own
    function so tests inject a fake and never hit the network."""
    from validation.v3_market import Kalshi, _load_venue_cfg
    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"], min_interval=0.2)
    text = client.get_text(f"/series/{series}/markets/{ticker}/candlesticks",
                           start_ts=start_ts, end_ts=end_ts, period_interval=60)
    candles = json.loads(text).get("candlesticks") or []
    return {"candles": candles, "raw_sha256": sha256_hex(text)}


def summarize_min_low(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce a raw candlestick list to just what the fill-sim needs: the minimum realized
    trade price (`price.low_dollars`) over the whole window and its timestamp. A resting
    bid's fill depends only on whether the trade price ever dipped to/through it — keeping
    every candle's full OHLC, yes-ask, yes-bid, and volume fields would balloon the cache ~100x for
    a multi-month World Cup pregame window (measured live: 98MB for 237 tickers) for no
    analytical benefit."""
    best_low: Optional[float] = None
    best_ts: Optional[int] = None
    for c in candles:
        low = (c.get("price") or {}).get("low_dollars")
        if low is None:
            continue
        low = float(low)
        if best_low is None or low < best_low:
            best_low, best_ts = low, c.get("end_period_ts")
    return {"min_low_dollars": best_low, "min_low_end_period_ts": best_ts,
            "n_candles": len(candles)}


def load_candle_summary_cache(cache_dir: Path = CANDLES_CACHE_DIR) -> Dict[str, Dict[str, Any]]:
    """Read the whole cache ONCE per run. The original design re-read+re-parsed this file
    from scratch inside the per-ticker fetch call — O(n^2) in ticker count, and slow enough
    (with the pre-trim, un-summarized cache) to make a 237-ticker run take 10+ minutes even
    fully warm. Load once, look up in memory."""
    cached: Dict[str, Dict[str, Any]] = {}
    if cache_dir.exists():
        for path in sorted(cache_dir.glob("dt=*.jsonl")):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        cached[rec["ticker"]] = rec
    return cached


def get_or_fetch_candle_summary(
    ticker: str, series: str, start_ts: int, end_ts: int,
    cache: Dict[str, Dict[str, Any]], cache_dir: Path = CANDLES_CACHE_DIR,
    fetcher: Callable[[str, str, int, int], Dict[str, Any]] = fetch_candles_default,
) -> Dict[str, Any]:
    """One cached, summarized candlestick pull per ticker. `cache` is an in-memory dict the
    caller loads ONCE via `load_candle_summary_cache` and passes to every call (never re-read
    from disk here) — a cache hit costs a dict lookup, a miss appends one line to disk."""
    if ticker in cache:
        return cache[ticker]

    fetched = fetcher(series, ticker, start_ts, end_ts)
    summary = summarize_min_low(fetched["candles"])
    rec = {
        "schema_version": "sports_maker_fillsim_candle_summary.v1",
        "ticker": ticker, "series": series, "start_ts": start_ts, "end_ts": end_ts,
        **summary, "raw_sha256": fetched["raw_sha256"], "price_source_tag": "real_ask",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    cache[ticker] = rec
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        f.write(canonical_json(rec) + "\n")
    return rec


def detect_fill(summary: Dict[str, Any], bid_price: float) -> Tuple[bool, Optional[int]]:
    """Filled = the window's minimum realized trade price (`price.low_dollars`, NOT the ask
    low — a trade at/below bid_price is what actually crosses into a resting bid) reached at
    or below bid_price at some point."""
    low = summary.get("min_low_dollars")
    if low is None:
        return False, None
    if low <= bid_price + 1e-9:
        return True, summary.get("min_low_end_period_ts")
    return False, None


# --------------------------------------------------------------------------- #
# per-outcome simulation
# --------------------------------------------------------------------------- #
def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def simulate_outcomes(
    games: List[Dict[str, Any]],
    windows: Dict[str, Dict[str, Any]],
    moneylines: Dict[Any, Dict[str, Any]],
    candle_fetcher: Callable[[str, str, int, int], Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """One result row per priced (game, outcome): bid price, fill, and (if filled) the
    edge_after_fee at both the DK-close anchor (fair_fill) and the DK-open anchor
    (fair_entry) so the caller can see how much fair moved before a fill happened."""
    rows: List[Dict[str, Any]] = []
    for g in games:
        ml = moneylines.get(g.get("espn_event_id"))
        fair_open = devig_fair_probs(ml, "open") if ml else None
        for o in g.get("outcomes", []):
            fair_close = o.get("fair_prob")
            fair_key = o.get("fair_key")
            ticker = o.get("ticker")
            if fair_close is None or fair_key is None or not ticker:
                continue
            win = windows.get(ticker)
            if win is None or not win.get("open_time"):
                continue
            kickoff_raw = g.get("kickoff_ts")
            if not kickoff_raw:
                continue
            try:
                start_ts = int(_parse_iso(win["open_time"]).timestamp())
                end_ts = int(_parse_iso(kickoff_raw).timestamp())
            except ValueError:
                continue
            if end_ts <= start_ts:
                continue

            bid = bid_price_for(fair_close)
            summary = candle_fetcher(win.get("series") or g.get("series"), ticker, start_ts, end_ts)
            filled, fill_end_ts = detect_fill(summary, bid)
            fee = fee_per_contract(bid, rate=MAKER_FEE_RATE)

            row: Dict[str, Any] = {
                "kalshi_event_ticker": g["kalshi_event_ticker"], "ticker": ticker,
                "series": g.get("series"), "fair_key": fair_key,
                "fair_close": fair_close, "bid_price": bid, "fee_per_contract": fee,
                "filled": filled, "fill_end_period_ts": fill_end_ts,
                "n_candles": summary.get("n_candles", 0),
            }
            if filled:
                row["edge_after_fee_fill_anchor"] = fair_close - bid - fee
                fair_entry = (fair_open or {}).get(fair_key) if fair_open else None
                row["fair_entry"] = fair_entry
                if fair_entry is not None:
                    row["edge_after_fee_entry_anchor"] = fair_entry - bid - fee
                    row["fair_move_entry_to_fill_anchor"] = fair_close - fair_entry
            rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# aggregation + bootstrap
# --------------------------------------------------------------------------- #
def fill_rate_by_game(rows: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for r in rows:
        out.setdefault(r["kalshi_event_ticker"], []).append(1.0 if r["filled"] else 0.0)
    return out


def filled_edges_by_game(rows: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for r in rows:
        if r["filled"] and r.get("edge_after_fee_fill_anchor") is not None:
            out.setdefault(r["kalshi_event_ticker"], []).append(r["edge_after_fee_fill_anchor"])
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S13 maker fill-sim (read-only, paper)")
    ap.add_argument("--clv-tape-glob", default=CLV_TAPE_GLOB)
    ap.add_argument("--history-tape-glob", default=HISTORY_TAPE_GLOB)
    ap.add_argument("--candles-cache-dir", default=str(CANDLES_CACHE_DIR))
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    games = load_games(args.clv_tape_glob)
    history = load_history_records(args.history_tape_glob)
    windows = kalshi_outcome_windows(history)
    moneylines = espn_moneylines(history)

    cache_dir = Path(args.candles_cache_dir)
    cache = load_candle_summary_cache(cache_dir)

    def fetcher(series, ticker, start_ts, end_ts):
        return get_or_fetch_candle_summary(ticker, series, start_ts, end_ts,
                                           cache=cache, cache_dir=cache_dir)

    rows = simulate_outcomes(games, windows, moneylines, fetcher)
    n_attempted = len(rows)
    n_filled = sum(1 for r in rows if r["filled"])
    fill_rate = n_filled / n_attempted if n_attempted else float("nan")

    fill_blocks = fill_rate_by_game(rows)
    fill_point, fill_lo, fill_hi, n_games_fill, _ = block_bootstrap(fill_blocks, args.n_boot)

    edge_blocks = filled_edges_by_game(rows)
    edge_point, edge_lo, edge_hi, n_games_edge, n_outcomes_edge = block_bootstrap(
        edge_blocks, args.n_boot)
    clears = edge_lo > 0.0 if n_outcomes_edge else False

    fair_moves = [r["fair_move_entry_to_fill_anchor"] for r in rows
                  if r["filled"] and r.get("fair_move_entry_to_fill_anchor") is not None]
    mean_fair_move = sum(fair_moves) / len(fair_moves) if fair_moves else None

    print("=" * 78)
    print("S13 MAKER FILL-SIM (read-only, paper) — bid = DK-close-devig fair - 1c")
    print("=" * 78)
    print(f"games loaded: {len(games)}  priced (ticker,window) attempts: {n_attempted}")
    print(f"fill rate = {fill_rate:.1%} ({n_filled}/{n_attempted}); "
          f"block-bootstrap by game: point={fill_point:.1%} "
          f"95% CI=[{fill_lo:.1%}, {fill_hi:.1%}] (n_games={n_games_fill})")
    print(f"edge_after_fee | filled (n_games={n_games_edge}, n_outcomes={n_outcomes_edge}): "
          f"point={edge_point:+.5f}  95% CI=[{edge_lo:+.5f}, {edge_hi:+.5f}]")
    print(f"VERDICT: lower CI bound {'STRICTLY CLEARS' if clears else 'does NOT clear'} zero "
          f"-> {'EDGE' if clears else 'DEAD (null result)' if n_outcomes_edge else 'NO FILLS YET'}")
    if mean_fair_move is not None:
        print(f"adverse-selection check: mean(fair_close - fair_open) over filled outcomes "
              f"= {mean_fair_move:+.5f} (n={len(fair_moves)}) — how much the DK line moved "
              f"between the bid's entry anchor and its close-based fill anchor")

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "n_games_loaded": len(games), "n_attempted": n_attempted, "n_filled": n_filled,
        "fill_rate_point": fill_rate,
        "fill_rate_bootstrap": {"point": fill_point, "ci95_lo": fill_lo, "ci95_hi": fill_hi,
                                "n_games": n_games_fill},
        "edge_after_fee_filled_bootstrap": {
            "point": edge_point, "ci95_lo": edge_lo, "ci95_hi": edge_hi,
            "n_games": n_games_edge, "n_outcomes": n_outcomes_edge,
        },
        "verdict": "EDGE" if clears else ("DEAD" if n_outcomes_edge else "NO_FILLS_YET"),
        "mean_fair_move_entry_to_fill_anchor": mean_fair_move,
        "n_boot": args.n_boot,
        "price_source_tag": "mixed",  # composite metric: real_ask (bid/fill) + synthetic (devig)
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2))
        print(f"[s13_maker_fillsim] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

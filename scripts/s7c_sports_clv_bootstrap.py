#!/usr/bin/env python3
"""s7c_sports_clv_bootstrap.py — S7c: block-bootstrap CI on S7b's sports CLV edge.

LOOP-QUEUE.md Q4/S7c. Reads the accumulated `tape/sports_clv/*.jsonl` (S7b's
`sports_clv_join.v1` records: real pregame Kalshi ask vs DraftKings-close de-vigged fair
prob, per outcome, per matched game) and asks the binding question: does the mean
`edge_after_fee` clear zero once resampled at the GAME level (not the outcome level —
outcomes within one game are correlated draws, sharing the same de-vig and market
conditions, so bootstrapping by outcome would understate the true variance).

READ-ONLY. This script never fetches network data or writes tape; it only re-derives a
verdict from what S7a/S7b already captured. Duplicate games across day-files (the join was
re-run more than once as more of the tournament settled) are deduped by
`kalshi_event_ticker`, keeping the record from the most recent `capture_id`.

Run:
    python scripts/s7c_sports_clv_bootstrap.py
    python scripts/s7c_sports_clv_bootstrap.py --n-boot 20000 --json-out /tmp/s7c.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.io import REPO_ROOT  # noqa: E402

CLV_TAPE_GLOB = str(REPO_ROOT / "tape" / "sports_clv" / "dt=*.jsonl")


def load_games(tape_glob: str = CLV_TAPE_GLOB) -> List[Dict]:
    """Read every `sports_clv_join.v1` record across all day-files, deduped by
    `kalshi_event_ticker` (keep the most recent `capture_id` if a game was joined more than
    once across separate runs)."""
    by_ticker: Dict[str, Dict] = {}
    for path in sorted(glob.glob(tape_glob)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("schema_version") != "sports_clv_join.v1":
                    continue
                key = rec["kalshi_event_ticker"]
                prev = by_ticker.get(key)
                if prev is None or rec["capture_id"] > prev["capture_id"]:
                    by_ticker[key] = rec
    return list(by_ticker.values())


def priced_edges_by_game(games: List[Dict]) -> Dict[str, List[float]]:
    """`{kalshi_event_ticker: [edge_after_fee, ...]}` for games with >=1 priced outcome."""
    out: Dict[str, List[float]] = {}
    for g in games:
        edges = [o["edge_after_fee"] for o in g.get("outcomes", [])
                 if o.get("edge_after_fee") is not None]
        if edges:
            out[g["kalshi_event_ticker"]] = edges
    return out


def block_bootstrap(edges_by_game: Dict[str, List[float]], n_boot: int, seed: int = 12345
                    ) -> Tuple[float, float, float, int, int]:
    """Block-bootstrap by GAME: each resample draws whole games (all their priced outcomes)
    with replacement, then takes the mean `edge_after_fee` across the pooled outcomes.
    Returns (point_mean, lo95, hi95, n_games, n_outcomes)."""
    tickers = sorted(edges_by_game)
    blocks = [np.array(edges_by_game[t], dtype=float) for t in tickers]
    n_outcomes = sum(len(b) for b in blocks)
    if not blocks:
        return float("nan"), float("nan"), float("nan"), 0, 0
    point = float(np.mean(np.concatenate(blocks)))
    rng = np.random.default_rng(seed)
    n_blocks = len(blocks)
    means = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n_blocks, size=n_blocks)
        sample = np.concatenate([blocks[j] for j in idx])
        means[i] = sample.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return point, float(lo), float(hi), n_blocks, n_outcomes


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S7c sports CLV block-bootstrap (by game)")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--tape-glob", default=CLV_TAPE_GLOB)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    games = load_games(args.tape_glob)
    edges_by_game = priced_edges_by_game(games)
    point, lo, hi, n_games, n_outcomes = block_bootstrap(edges_by_game, args.n_boot)
    clears = lo > 0.0

    by_series: Dict[str, List[str]] = defaultdict(list)
    for g in games:
        if g["kalshi_event_ticker"] in edges_by_game:
            by_series[g["series"]].append(g["kalshi_event_ticker"])

    print("=" * 78)
    print("S7c SPORTS CLV BLOCK-BOOTSTRAP (by game)  edge_after_fee = fair_prob - ask - fee")
    print("=" * 78)
    print(f"games loaded (deduped): {len(games)}  priced (>=1 outcome): {n_games}  "
          f"priced outcomes: {n_outcomes}")
    for series, tickers in sorted(by_series.items()):
        print(f"  {series}: {len(tickers)} games")
    print(f"\nmean edge_after_fee (point estimate) = {point:+.5f}")
    print(f"95% block-bootstrap CI (n_boot={args.n_boot}) = [{lo:+.5f}, {hi:+.5f}]")
    print(f"\nVERDICT: lower CI bound {'STRICTLY CLEARS' if clears else 'does NOT clear'} "
          f"zero -> {'EDGE' if clears else 'DEAD (null result)'}")

    if args.json_out:
        result = {
            "n_games_loaded": len(games), "n_games_priced": n_games,
            "n_outcomes_priced": n_outcomes,
            "by_series_n_games": {k: len(v) for k, v in by_series.items()},
            "mean_edge_after_fee": point, "ci95_lo": lo, "ci95_hi": hi,
            "n_boot": args.n_boot, "verdict": "EDGE" if clears else "DEAD",
            "price_source_tag": "mixed",  # composite metric — real_ask vs synthetic-devig
        }
        Path(args.json_out).write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

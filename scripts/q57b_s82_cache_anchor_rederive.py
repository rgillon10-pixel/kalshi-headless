#!/usr/bin/env python3
"""Independent re-derivation of Q57(b)'s headline numbers. REDUNDANCY, NOT VERIFICATION.

No `Task`/subagent tool exists in this harness, so no independent `verifier` agent could be
dispatched (the L287/L288/L290/L291/L295/L308/L313/L325/L349 precedent). The sanctioned
fallback is a SECOND IMPLEMENTATION that shares no code with the first, so that a defect
must be present in both to survive. It cannot catch an error both implementations share and
is not claimed to: Q57(b)'s result stays PROVISIONAL until a second AGENT confirms it.

What is deliberately NOT shared with `scripts/q57b_s82_cache_anchor_probe.py`:
  * its own JSONL reader and its own settlement readers (straight off the tape files,
    never `core.settlement_sources`),
  * its own ISO-to-epoch parser, by string slicing and `calendar.timegm`, never
    `core.timeutil.parse_iso_utc`,
  * its own game-id / sports-series predicates, never `scripts.q51_maker_fillsim`,
  * its own flow aggregation, entry picker, fillability band and fee FORMULA, re-derived
    from Kalshi's published round-up-to-the-cent rule. The RATE constant is imported,
    because `scripts/invariants.py::no_handrolled_fee_rate` forbids a literal fee rate
    anywhere outside `core/pricing.py` (L5: a hand-rolled rate once overcharged an S13
    draft 4x) - the same posture `scripts/q56_s81_rederive.py` takes,
  * its own block bootstrap at a DIFFERENT seed (20260817), so agreement on the CI is
    agreement on the distribution, not on one random draw.

Run:
    python3 scripts/q57b_s82_cache_anchor_rederive.py
Writes `reports/q57b_s82_cache_anchor_rederive.json`. Exit 0 always.
"""
from __future__ import annotations

import calendar
import glob
import json
import math
import os
import random
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.pricing import TAKER_FEE_RATE  # noqa: E402  (rate constant only; formula below)

REPORT = os.path.join(ROOT, "reports", "q57b_s82_cache_anchor_rederive.json")

TAKER_RATE = TAKER_FEE_RATE   # rate imported (L5 / no_handrolled_fee_rate); formula below
BAND_LO, BAND_HI = 0.02, 0.98
MIN_ABS_RHO = 0.20
MIN_WINDOW_COUNT = 100.0
N_BOOT = 10000
SEED = 20260817


def epoch(iso: str) -> float:
    """ISO-8601 UTC to epoch seconds, by string slicing. Handles a trailing Z, a
    +00:00 offset, and an optional fractional part - the three shapes the committed
    tape actually exhibits."""
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1]
    elif s.endswith("+00:00"):
        s = s[:-6]
    date, _, clock = s.partition("T")
    y, mo, d = int(date[0:4]), int(date[5:7]), int(date[8:10])
    hh, mm = int(clock[0:2]), int(clock[3:5])
    ss_part = clock[6:]
    if "." in ss_part:
        whole, _, frac = ss_part.partition(".")
        sec = int(whole) + float("0." + frac)
    else:
        sec = int(ss_part) if ss_part else 0
    base = calendar.timegm((y, mo, d, hh, mm, 0, 0, 0, 0))
    return base + float(sec)


def fee(price: float) -> float:
    """Kalshi fee per contract: round the whole-order fee UP to the cent."""
    return math.ceil(TAKER_RATE * price * (1.0 - price) * 100.0) / 100.0


def is_game(ticker: str) -> bool:
    head = ticker.split("-")[0]
    return head[-4:] == "GAME" and head[:5] != "KXMVE"


def game_of(ticker: str) -> str:
    i = ticker.rfind("-")
    return ticker[:i] if i > 0 else ticker


def jsonl(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for raw in fh:
            raw = raw.strip()
            if raw:
                yield json.loads(raw)


def read_prints() -> Dict[str, List[tuple]]:
    """ticker to sorted [(ts, signed_count, count)] over sports GAME markets."""
    out: Dict[str, List[tuple]] = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(ROOT, "tape", "kalshi_trades",
                                              "dt=*.jsonl"))):
        for rec in jsonl(path):
            tk = rec.get("ticker")
            if not isinstance(tk, str) or not is_game(tk):
                continue
            side = rec.get("taker_outcome_side")
            if side not in ("yes", "no"):
                continue
            c = float(rec.get("count") or 0.0)
            out[tk].append((epoch(rec["created_time"]), c if side == "yes" else -c, c))
    for tk in out:
        out[tk].sort()
    return dict(out)


def read_depth(keep) -> Dict[str, List[tuple]]:
    """ticker to sorted [(ts, captured_at, yes_ask, no_ask)] for real_ask rows only."""
    out: Dict[str, List[tuple]] = defaultdict(list)
    for path in sorted(glob.glob(os.path.join(ROOT, "tape", "orderbook_depth",
                                              "dt=*.jsonl"))):
        for rec in jsonl(path):
            tk = rec.get("ticker")
            if tk not in keep:
                continue
            tags = rec.get("price_source_tags") or {}
            if tags.get("asks") != "real_ask":
                continue
            out[tk].append((epoch(rec["captured_at"]), rec["captured_at"],
                            rec.get("best_yes_ask"), rec.get("best_no_ask")))
    for tk in out:
        out[tk].sort()
    return dict(out)


def read_anchor(keep) -> Tuple[Dict[str, float], dict]:
    """The DELTA-1 union anchor, re-read from both families independently."""
    ledger: Dict[str, set] = defaultdict(set)
    for path in sorted(glob.glob(os.path.join(ROOT, "tape", "settlement_ledger",
                                              "dt=*.jsonl"))):
        for rec in jsonl(path):
            tk = rec.get("ticker")
            if tk in keep and rec.get("close_time"):
                ledger[tk].add(rec["close_time"])
    cache: Dict[str, set] = defaultdict(set)
    for path in sorted(glob.glob(os.path.join(ROOT, "tape", "q51_settlement_cache",
                                              "settlement*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        for tk, m in (blob.get("markets") or {}).items():
            if tk in keep and isinstance(m, dict) and m.get("close_time"):
                cache[tk].add(m["close_time"])
    keys = set(ledger) | set(cache)
    closes = {tk: min(epoch(v) for v in (ledger.get(tk, set()) | cache.get(tk, set())))
              for tk in keys}
    audit = {"n_tickers_ledger": len(ledger), "n_tickers_cache": len(cache),
             "n_tickers_union": len(keys),
             "n_tickers_added_by_cache": len(set(cache) - set(ledger)),
             "n_tickers_in_both": len(set(ledger) & set(cache))}
    return closes, audit


def read_outcomes(keep) -> Dict[str, int]:
    """ticker to 1/0, straight off the two families that actually carry these tickers
    (settlement_ledger and q51_settlement_cache). Anything not a clean yes/no is
    DROPPED, never scored as a loss."""
    out: Dict[str, int] = {}
    for path in sorted(glob.glob(os.path.join(ROOT, "tape", "settlement_ledger",
                                              "dt=*.jsonl"))):
        for rec in jsonl(path):
            tk = rec.get("ticker")
            res = (rec.get("result") or "").strip().lower()
            if tk in keep and res in ("yes", "no"):
                out[tk] = 1 if res == "yes" else 0
    for path in sorted(glob.glob(os.path.join(ROOT, "tape", "q51_settlement_cache",
                                              "settlement*.json"))):
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        for tk, m in (blob.get("markets") or {}).items():
            if tk not in keep or not isinstance(m, dict):
                continue
            res = (m.get("result") or "").strip().lower()
            if res in ("yes", "no"):
                out.setdefault(tk, 1 if res == "yes" else 0)
    return out


def cell(prints, depth, closes, window_min: float, lag_min: float) -> List[dict]:
    """One pre-registered cell, re-derived: one entry per GAME, argmax abs(rho)."""
    per_game: Dict[str, dict] = {}
    for tk in sorted(prints):
        close = closes.get(tk)
        if close is None:
            continue
        snaps = [s for s in depth.get(tk, []) if s[0] <= close]
        if not snaps:
            continue
        ts, cap, yes_ask, no_ask = snaps[-1]
        if close - ts > lag_min * 60.0:
            continue
        lo = ts - window_min * 60.0
        net = tot = 0.0
        n = 0
        for pts, signed, c in prints[tk]:
            if lo < pts <= ts:
                net += signed
                tot += c
                n += 1
        if n == 0 or tot < MIN_WINDOW_COUNT:
            continue
        rho = net / tot
        if abs(rho) < MIN_ABS_RHO:
            continue
        fade = "no" if rho > 0 else "yes"
        ask = no_ask if fade == "no" else yes_ask
        other = yes_ask if fade == "no" else no_ask
        if ask is None or float(ask) < 0.01:
            continue
        ask = float(ask)
        if ask < BAND_LO or ask > BAND_HI:
            continue
        g = game_of(tk)
        row = {"game": g, "ticker": tk, "rho": rho, "fade_side": fade,
               "entry_ask": ask, "entry_captured_at": cap,
               "entry_lag_minutes": round((close - ts) / 60.0, 2),
               "overround": (round(ask + float(other) - 1.0, 6)
                             if other is not None else None)}
        cur = per_game.get(g)
        if cur is None or (abs(rho), cur["ticker"]) > (abs(cur["rho"]), row["ticker"]):
            per_game[g] = row
    return [per_game[g] for g in sorted(per_game)]


def boot(unit_values: Dict[str, List[float]], seed: int = SEED) -> dict:
    units = sorted(unit_values)
    if not units:
        return {"n_units": 0, "n_obs": 0, "mean": None, "ci95": [None, None]}
    tot = sum(sum(v) for v in unit_values.values())
    cnt = sum(len(v) for v in unit_values.values())
    rng = random.Random(seed)
    means = []
    for _ in range(N_BOOT):
        s = 0.0
        k = 0
        for _ in units:
            v = unit_values[units[rng.randrange(len(units))]]
            s += sum(v)
            k += len(v)
        if k:
            means.append(s / k)
    means.sort()
    return {"n_units": len(units), "n_obs": cnt, "mean": tot / cnt,
            "ci95": [means[int(0.025 * len(means))], means[int(0.975 * len(means))]],
            "n_boot": N_BOOT, "seed": seed}


def side_census(rows: Sequence[dict]) -> dict:
    """Per-side UNIT counts, and units whose every entry is on the minority side."""
    by_game: Dict[str, List[str]] = defaultdict(list)
    for r in rows:
        by_game[r["game"]].append(r["fade_side"])
    per_side = {"yes": 0, "no": 0}
    for sides in by_game.values():
        for s in set(sides):
            per_side[s] += 1
    minority = min(per_side, key=lambda s: (per_side[s], s))
    exclusive = sum(1 for sides in by_game.values() if set(sides) == {minority})
    return {"n_units": len(by_game), "units_per_side": per_side,
            "minority_side": minority, "minority_units_exclusive": exclusive}


def run() -> dict:
    prints = read_prints()
    keep = set(prints)
    depth = read_depth(keep)
    closes, anchor = read_anchor(keep)
    outcomes = read_outcomes(keep)

    rep = {"probe": "q57b_s82_cache_anchor_rederive",
           "role": "REDUNDANCY, not verification (no second AGENT was dispatchable)",
           "n_trade_tickers": len(keep),
           "n_trade_games": len({game_of(t) for t in keep}),
           "n_settled_binary": len(outcomes),
           "anchor_audit": anchor, "cells": []}

    for name, win, lag, score in (("primary_minimal_change", 120.0, 60.0, True),
                                  ("secondary_verifier_identified", 15.0, 240.0, True),
                                  ("diagnostic_window_only", 15.0, 60.0, False)):
        rows = [r for r in cell(prints, depth, closes, win, lag)
                if r["ticker"] in outcomes]
        cen = side_census(rows)
        out = {"name": name, "flow_window_minutes": win, "max_entry_lag_minutes": lag,
               "n_units": cen["n_units"], "units_per_side": cen["units_per_side"],
               "minority_units_exclusive": cen["minority_units_exclusive"],
               "mean_overround": (round(sum(r["overround"] for r in rows
                                            if r["overround"] is not None)
                                        / max(1, sum(1 for r in rows
                                                     if r["overround"] is not None)), 6)
                                  if rows else None)}
        if score and cen["n_units"] >= 10 and cen["minority_units_exclusive"] >= 2:
            uv: Dict[str, List[float]] = defaultdict(list)
            for r in rows:
                o = outcomes[r["ticker"]]
                won = (o == 1) if r["fade_side"] == "yes" else (o == 0)
                uv[r["game"]].append(round((1.0 if won else 0.0) - r["entry_ask"]
                                           - fee(r["entry_ask"]), 6))
            out["bootstrap"] = boot(uv)
            out["n_fade_wins"] = sum(1 for r in rows
                                     if ((outcomes[r["ticker"]] == 1)
                                         if r["fade_side"] == "yes"
                                         else (outcomes[r["ticker"]] == 0)))
            fresh = [v for r, v in ((r, uv[r["game"]][0]) for r in rows)
                     if r["entry_lag_minutes"] <= 60.0]
            stale = [v for r, v in ((r, uv[r["game"]][0]) for r in rows)
                     if r["entry_lag_minutes"] > 60.0]
            out["staleness_split"] = {
                "n_entries_lag_le_60min": len(fresh),
                "mean_pnl_lag_le_60min": (round(sum(fresh) / len(fresh), 6)
                                          if fresh else None),
                "n_entries_lag_gt_60min": len(stale),
                "mean_pnl_lag_gt_60min": (round(sum(stale) / len(stale), 6)
                                          if stale else None),
                "note": ("DESCRIPTIVE, post-hoc: the pre-registered staleness rule is "
                         "60 minutes, so the lag_gt_60min entries exist ONLY in the "
                         "secondary cell. price_source_tag real_ask on both arms."),
            }
        rep["cells"].append(out)
    return rep


def main() -> int:
    rep = run()
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps(rep, indent=2, sort_keys=True))
    print("wrote " + REPORT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Q57b redundancy re-derivation — an INDEPENDENT second implementation.

WHY THIS EXISTS
---------------
LOOP-QUEUE.md's two-agent verdict rule wants a producer AND an independent `verifier` AGENT.
This harness exposes no `Task`/subagent tool (the L287/L288/L290/L291/L295/L308/L313/L325/
L349 precedent), so the sanctioned redundancy fallback runs instead: a second implementation
that shares NO code with `scripts/q57b_anchor_widening_census.py` and re-derives every
headline number from the raw tape.

**A second IMPLEMENTATION is not a second AGENT.** Agreement here downgrades transcription
risk, not reasoning risk, so any verdict resting on it stays PROVISIONAL.

INDEPENDENCE, ENFORCED
----------------------
`tests/test_q57b_rederive.py` AST-pins that this module imports NEITHER
`scripts.q57b_anchor_widening_census` NOR `scripts.q57_s82_flow_fade_probe` NOR
`core.bootstrap` NOR `core.settlement_sources` NOR `core.timeutil`. Concretely it uses:
  * its own line-by-line JSONL reader (no shared loader);
  * its own ISO-8601 -> epoch parser by string slicing + `calendar.timegm` (no `parse_iso_utc`);
  * its own sports-ticker predicate (no `core.markets`);
  * its own settled-set reader over the settlement families (no `resolve_market_results`);
  * its own minority-side counter (no `sign_variation_admissible`);
  * a flow accumulator written as a running scan rather than a per-ticker windowed slice.

Run:
    python3 scripts/q57b_rederive.py
Prints an AGREE/DISAGREE table. Exit 0 if every compared field agrees, else 1.
"""
from __future__ import annotations

import calendar
import glob
import json
import os
import sys
from typing import Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TAPE = os.path.join(ROOT, "tape")


# --------------------------------------------------------------------------- #
# own primitives
# --------------------------------------------------------------------------- #
def epoch(s: str) -> float:
    """ISO-8601 UTC -> epoch seconds, by string slicing. Deliberately NOT `parse_iso_utc`."""
    y, mo, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
    h, mi = int(s[11:13]), int(s[14:16])
    sec = 0.0
    if len(s) > 17 and s[16] == ":":
        j = 17
        while j < len(s) and (s[j].isdigit() or s[j] == "."):
            j += 1
        sec = float(s[17:j])
    return float(calendar.timegm((y, mo, d, h, mi, 0, 0, 0, 0))) + sec


def rows_of(path: str):
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def looks_like_sports_game(ticker: str) -> bool:
    """Own predicate: the committed GAME markets are `KX<LEAGUE>GAME-<date><teams>-<side>`."""
    return "GAME-" in ticker and ticker.startswith("KX")


def game_of(ticker: str) -> str:
    i = ticker.rfind("-")
    return ticker[:i] if i > 0 else ticker


# --------------------------------------------------------------------------- #
# own loaders
# --------------------------------------------------------------------------- #
def read_prints() -> Dict[str, List[Tuple[float, str, float]]]:
    out: Dict[str, List[Tuple[float, str, float]]] = {}
    for p in sorted(glob.glob(os.path.join(TAPE, "kalshi_trades", "dt=*.jsonl"))):
        for r in rows_of(p):
            tk = r.get("ticker")
            if not isinstance(tk, str) or not looks_like_sports_game(tk):
                continue
            out.setdefault(tk, []).append(
                (epoch(r["created_time"]), r.get("taker_outcome_side"),
                 float(r.get("count") or 0.0)))
    for tk in out:
        out[tk].sort()
    return out


def read_depth(keep) -> Dict[str, List[Tuple[float, Optional[float], Optional[float]]]]:
    out: Dict[str, List[Tuple[float, Optional[float], Optional[float]]]] = {}
    for p in sorted(glob.glob(os.path.join(TAPE, "orderbook_depth", "dt=*.jsonl"))):
        for r in rows_of(p):
            tk = r.get("ticker")
            if tk not in keep:
                continue
            if ((r.get("price_source_tags") or {}).get("asks")) != "real_ask":
                continue
            out.setdefault(tk, []).append(
                (epoch(r["captured_at"]), r.get("best_yes_ask"), r.get("best_no_ask")))
    for tk in out:
        out[tk].sort()
    return out


def read_ledger_closes(keep) -> Dict[str, float]:
    best: Dict[str, float] = {}
    for p in sorted(glob.glob(os.path.join(TAPE, "settlement_ledger", "dt=*.jsonl"))):
        for r in rows_of(p):
            tk, ct = r.get("ticker"), r.get("close_time")
            if tk in keep and ct:
                e = epoch(ct)
                if tk not in best or e < best[tk]:
                    best[tk] = e
    return best


def read_cache_closes(keep) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for p in sorted(glob.glob(os.path.join(TAPE, "q51_settlement_cache", "*.json"))):
        with open(p, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        mk = blob.get("markets") or {}
        pairs = list(mk.items()) if isinstance(mk, dict) else [(m.get("ticker"), m) for m in mk]
        for tk, m in pairs:
            if not isinstance(m, dict):
                continue
            tk = tk or m.get("ticker")
            ct = m.get("close_time")
            if tk in keep and ct:
                out.setdefault(tk, []).append(epoch(ct))
    return out


def read_settled(keep) -> set:
    """Own settled-set reader: the two families that actually carry these tickers."""
    settled = set()
    for p in sorted(glob.glob(os.path.join(TAPE, "settlement_ledger", "dt=*.jsonl"))):
        for r in rows_of(p):
            if r.get("ticker") in keep and str(r.get("result", "")).lower() in ("yes", "no"):
                settled.add(r["ticker"])
    for p in sorted(glob.glob(os.path.join(TAPE, "q51_settlement_cache", "*.json"))):
        with open(p, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        mk = blob.get("markets") or {}
        pairs = list(mk.items()) if isinstance(mk, dict) else [(m.get("ticker"), m) for m in mk]
        for tk, m in pairs:
            if not isinstance(m, dict):
                continue
            tk = tk or m.get("ticker")
            if tk in keep and str(m.get("result", "")).lower() in ("yes", "no"):
                settled.add(tk)
    return settled


# --------------------------------------------------------------------------- #
# own candidate builder + own minority counter
# --------------------------------------------------------------------------- #
def build(prints, depth, closes, settled, win_min, lag_min, rho_min, cnt_min):
    per_game: Dict[str, Tuple[float, str, str]] = {}
    for tk in sorted(prints):
        if tk not in closes:
            continue
        close = closes[tk]
        snap = None
        for s in depth.get(tk, []):          # running scan, not a slice+[-1]
            if s[0] <= close:
                snap = s
            else:
                break
        if snap is None or (close - snap[0]) > lag_min * 60.0:
            continue
        lo = snap[0] - win_min * 60.0
        net = tot = 0.0
        for ts, side, c in prints[tk]:
            if ts <= lo or ts > snap[0]:
                continue
            if side == "yes":
                net += c
            elif side == "no":
                net -= c
            else:
                continue
            tot += c
        if tot <= 0.0 or tot < cnt_min:
            continue
        rho = net / tot
        if -rho_min < rho < rho_min:
            continue
        fade = "no" if rho > 0 else "yes"
        ask = snap[2] if fade == "no" else snap[1]
        if ask is None:
            continue
        ask = float(ask)
        if ask <= 0.0 or ask >= 1.0 or ask < 0.02 or ask > 0.98:
            continue
        if tk not in settled:
            continue
        g = game_of(tk)
        key = (abs(rho), [c for c in [tk]][0])
        cur = per_game.get(g)
        if cur is None or (abs(rho), tk) > (cur[0], cur[2]):
            per_game[g] = (abs(rho), fade, tk)
    return per_game


def minority(per_game) -> Tuple[Dict[str, int], Optional[int], bool]:
    counts = {"yes": 0, "no": 0}
    for _, fade, _ in per_game.values():
        counts[fade] += 1
    # one entry per game => every unit is EXCLUSIVE to its side
    mside = "yes" if counts["yes"] <= counts["no"] else "no"
    return ({k: v for k, v in counts.items() if v}, counts[mside], counts[mside] >= 2)


# --------------------------------------------------------------------------- #
def derive() -> dict:
    prints = read_prints()
    keep = set(prints)
    depth = read_depth(keep)
    ledger = read_ledger_closes(keep)
    cache_raw = read_cache_closes(keep)
    settled = read_settled(keep)
    cmin = {k: min(v) for k, v in cache_raw.items()}
    cmax = {k: max(v) for k, v in cache_raw.items()}
    umin = dict(cmin); umin.update(ledger)

    def cell(closes, w, lag, rho=0.20, cnt=100.0):
        pg = build(prints, depth, closes, settled, w, lag, rho, cnt)
        cnts, nmin, adm = minority(pg)
        return len(pg), cnts, nmin, adm

    b_n, b_c, _, _ = cell(ledger, 120, 60)
    p_n, p_c, p_m, p_a = cell(umin, 120, 60)

    # anchor-rewrite invariance
    rewritten = sum(1 for v in cache_raw.values() if max(v) - min(v) > 0.5)
    same = 0
    for tk, v in cache_raw.items():
        pick = []
        for e in (min(v), max(v)):
            s = None
            for d in depth.get(tk, []):
                if d[0] <= e:
                    s = d[0]
                else:
                    break
            pick.append(s)
        if pick[0] == pick[1]:
            same += 1

    def within(closes, budget=60.0):
        n = 0
        for tk, e in closes.items():
            s = None
            for d in depth.get(tk, []):
                if d[0] <= e:
                    s = d[0]
                else:
                    break
            if s is not None and (e - s) <= budget * 60.0:
                n += 1
        return n

    WIN = [15, 30, 45, 60, 90, 120, 180, 240]
    LAG = [30, 60, 90, 120, 180, 240, 360, 720]
    RHO = [0.10, 0.15, 0.20, 0.30, 0.40]
    CNT = [0.0, 50.0, 100.0, 250.0]
    n_cells = n_floor = n_adm = n_faith = 0
    adm_lags, adm_wins = [], set()
    for w in WIN:
        for lag in LAG:
            for rho in RHO:
                for cnt in CNT:
                    n_cells += 1
                    n, _, _, adm = cell(umin, w, lag, rho, cnt)
                    if n >= 10:
                        n_floor += 1
                        if adm:
                            n_adm += 1
                            adm_lags.append(lag)
                            adm_wins.add(w)
                            if lag <= 60:
                                n_faith += 1
    return {
        "n_game_tickers": len(prints),
        "n_games": len({game_of(t) for t in prints}),
        "n_settled_binary": len(settled),
        "n_ledger_closes": len(ledger),
        "n_cache_closes": len(cache_raw),
        "n_anchor_overlap": len(set(ledger) & set(cache_raw)),
        "baseline_units": b_n, "baseline_sides": b_c,
        "primary_units": p_n, "primary_sides": p_c,
        "primary_admissible": p_a,
        "widening_is_a_noop": (b_n == p_n and b_c == p_c),
        "n_close_time_rewritten": rewritten,
        "entry_snapshot_identical": same,
        "ledger_within_60min": within(ledger),
        "cache_within_60min": within(cmin),
        "grid_n_cells": n_cells,
        "grid_n_meeting_unit_floor": n_floor,
        "grid_n_admissible": n_adm,
        "grid_n_admissible_mechanism_faithful": n_faith,
        "grid_admissible_min_lag": (min(adm_lags) if adm_lags else None),
        "grid_admissible_windows": sorted(adm_wins),
    }


COMPARE = [
    ("n_game_tickers", lambda r: r["substrate"]["n_game_tickers"]),
    ("n_games", lambda r: r["substrate"]["n_games"]),
    ("n_settled_binary", lambda r: r["substrate"]["n_settled_binary"]),
    ("n_ledger_closes", lambda r: r["substrate"]["n_ledger_close_times"]),
    ("n_cache_closes", lambda r: r["substrate"]["cache"]["n_tickers_with_close_time"]),
    ("n_anchor_overlap", lambda r: r["substrate"]["union"]["min"]["n_both"]),
    ("baseline_units", lambda r: r["baseline_ledger_only"]["n_game_units"]),
    ("baseline_sides", lambda r: r["baseline_ledger_only"]["units_per_side"]),
    ("primary_units", lambda r: r["primary"]["n_game_units"]),
    ("primary_sides", lambda r: r["primary"]["units_per_side"]),
    ("primary_admissible", lambda r: r["primary"]["admissible"]),
    ("widening_is_a_noop", lambda r: r["widening_is_a_noop_at_the_sealed_spec"]),
    ("n_close_time_rewritten", lambda r: r["anchor_rewrite_invariance"]["n_close_time_rewritten"]),
    ("entry_snapshot_identical",
     lambda r: r["anchor_rewrite_invariance"]["entry_snapshot_identical_under_min_and_max_rule"]),
    ("ledger_within_60min",
     lambda r: r["entry_lag_profile"]["settlement_ledger"]["n_within_inherited_lag_budget"]),
    ("cache_within_60min",
     lambda r: r["entry_lag_profile"]["q51_settlement_cache"]["n_within_inherited_lag_budget"]),
    ("grid_n_cells", lambda r: r["grid"]["n_cells"]),
    ("grid_n_meeting_unit_floor", lambda r: r["grid"]["n_meeting_unit_floor"]),
    ("grid_n_admissible", lambda r: r["grid"]["n_admissible"]),
    ("grid_n_admissible_mechanism_faithful",
     lambda r: r["grid"]["n_admissible_and_mechanism_faithful"]),
    ("grid_admissible_min_lag", lambda r: r["grid"]["admissible_min_lag_minutes"]),
    ("grid_admissible_windows", lambda r: r["grid"]["admissible_windows_used"]),
]


def compare(mine: dict, report: dict) -> List[Tuple[str, object, object, bool]]:
    out = []
    for key, getter in COMPARE:
        theirs = getter(report)
        ours = mine[key]
        out.append((key, ours, theirs, ours == theirs))
    return out


def main() -> int:
    path = os.path.join(ROOT, "reports", "q57b_anchor_widening_census.json")
    if not os.path.exists(path):
        print("census report absent — run scripts/q57b_anchor_widening_census.py first")
        return 1
    with open(path, "r", encoding="utf-8") as fh:
        report = json.load(fh)
    mine = derive()
    rows = compare(mine, report)
    bad = [r for r in rows if not r[3]]
    print(f"{'field':42s} {'rederived':>26s} {'census':>26s}  ok")
    for k, a, b, ok in rows:
        print(f"{k:42s} {str(a):>26s} {str(b):>26s}  {'OK' if ok else 'DISAGREE'}")
    print(f"\n{len(rows) - len(bad)}/{len(rows)} fields agree "
          f"(redundancy, NOT independent verification — no second agent ran)")
    return 0 if not bad else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""q57_s82_rederive.py — INDEPENDENT second implementation of the Q57 / S82 headline numbers.

Why this file exists. Q57 declares the S82 milestone VERDICT-CLASS and therefore subject to
the two-agent rule. The executing harness carries no `Task`/subagent tool (the
L287/L288/L290/L291/L295/L308/L313/L325 precedent, and Q57's own text: "run it PROVISIONAL if
no `verifier` subagent is available in the executing harness"). This is the sanctioned
redundancy fallback: a from-scratch re-derivation that shares NOTHING with the probe except
the committed tape on disk.

Deliberately NOT shared with `scripts/q57_s82_flow_fade_probe.py`:
  * its own JSONL/JSON readers — no `core.io`, and the probe module is never imported;
  * its own ISO-8601 -> epoch parser, written by string slicing and integer day arithmetic
    (no `datetime`, no `core.timeutil`, no `fromisoformat` anywhere);
  * its own settled-set reader, straight off `tape/settlement_ledger/dt=*.jsonl` and
    `tape/q51_settlement_cache/*.json` — NOT `core.settlement_sources`;
  * its own sports-ticker filter, game-key split, window/flow/collapse loop, and per-side
    unit census, all written top-down in one function.

Nothing here reads a settlement RESULT VALUE, because the probe's verdict is
POPULATION-INADEQUATE and no P&L was computed: there is no CI to re-draw. What is re-derived
is exactly what the verdict rests on — the entry population, the per-side GAME-unit counts,
the sensitivity headline, and the minority-arm fillability split. All are EXACT integers and
are compared exactly (no bootstrap noise tolerance is needed or granted).

READ-ONLY, fully offline. Run:
    python3 scripts/q57_s82_rederive.py
Exit 0 if every headline agrees with `reports/q57_s82_flow_fade.json`, 1 otherwise.
"""
from __future__ import annotations

import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(REPO, "reports", "q57_s82_flow_fade.json")

_CUM = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def epoch(ts):
    """ISO-8601 -> UTC epoch seconds, by string slicing. No datetime, no fromisoformat.

    Accepts 'YYYY-MM-DDTHH:MM:SS[.ffffff][Z|+00:00]'. Every timestamp this probe touches is
    UTC (both tapes persist UTC), so a non-zero offset is a hard error rather than a silent
    mis-parse."""
    y = int(ts[0:4]); mo = int(ts[5:7]); d = int(ts[8:10])
    h = int(ts[11:13]); mi = int(ts[14:16]); s = int(ts[17:19])
    rest = ts[19:]
    frac = 0.0
    if rest.startswith("."):
        j = 1
        while j < len(rest) and rest[j].isdigit():
            j += 1
        frac = float("0." + rest[1:j])
        rest = rest[j:]
    if rest not in ("", "Z", "+00:00", "+0000"):
        raise ValueError(f"non-UTC or unparsed offset in {ts!r}")
    # days since 1970-01-01, civil calendar
    days = 0
    if y >= 1970:
        for yy in range(1970, y):
            days += 366 if (yy % 4 == 0 and (yy % 100 != 0 or yy % 400 == 0)) else 365
    else:  # pragma: no cover - no pre-1970 tape exists
        raise ValueError(ts)
    days += _CUM[mo - 1]
    if mo > 2 and (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
        days += 1
    days += d - 1
    return days * 86400 + h * 3600 + mi * 60 + s + frac


def is_game(tk):
    """`*GAME` sports moneyline, KXMVE* excluded (L31) — re-implemented, not imported."""
    head = tk.split("-")[0]
    return head.endswith("GAME") and not head.startswith("KXMVE")


def load():
    prints, depth, closes = {}, {}, {}
    for p in sorted(glob.glob(os.path.join(REPO, "tape", "kalshi_trades", "dt=*.jsonl"))):
        with open(p) as fh:
            for ln in fh:
                if not ln.strip():
                    continue
                r = json.loads(ln)
                tk = r.get("ticker")
                if not isinstance(tk, str) or not is_game(tk):
                    continue
                prints.setdefault(tk, []).append(
                    (epoch(r["created_time"]), r.get("taker_outcome_side"),
                     float(r.get("count") or 0.0)))
    for v in prints.values():
        v.sort()
    want = set(prints)
    for p in sorted(glob.glob(os.path.join(REPO, "tape", "orderbook_depth", "dt=*.jsonl"))):
        with open(p) as fh:
            for ln in fh:
                if not ln.strip():
                    continue
                r = json.loads(ln)
                tk = r.get("ticker")
                if tk not in want:
                    continue
                if (r.get("price_source_tags") or {}).get("asks") != "real_ask":
                    continue
                depth.setdefault(tk, []).append(
                    (epoch(r["captured_at"]), r["captured_at"],
                     r.get("best_yes_ask"), r.get("best_no_ask")))
    for v in depth.values():
        v.sort()
    for p in sorted(glob.glob(os.path.join(REPO, "tape", "settlement_ledger", "dt=*.jsonl"))):
        with open(p) as fh:
            for ln in fh:
                if not ln.strip():
                    continue
                r = json.loads(ln)
                tk, ct = r.get("ticker"), r.get("close_time")
                if tk in want and ct:
                    e = epoch(ct)
                    closes[tk] = min(e, closes[tk]) if tk in closes else e
    return prints, depth, closes


def settled_set(want):
    """Settled-BINARY membership only (never a value), off two families read directly."""
    out = set()
    for p in sorted(glob.glob(os.path.join(REPO, "tape", "settlement_ledger", "dt=*.jsonl"))):
        with open(p) as fh:
            for ln in fh:
                if not ln.strip():
                    continue
                r = json.loads(ln)
                if r.get("ticker") in want and str(r.get("result", "")).strip().lower() in ("yes", "no"):
                    out.add(r["ticker"])
    for p in sorted(glob.glob(os.path.join(REPO, "tape", "q51_settlement_cache", "*.json"))):
        with open(p) as fh:
            blob = json.load(fh)
        mk = blob.get("markets") or {}
        items = mk.items() if isinstance(mk, dict) else ((m.get("ticker"), m) for m in mk)
        for tk, m in items:
            if tk in want and str((m or {}).get("result", "")).strip().lower() in ("yes", "no"):
                out.add(tk)
    return out


def population(prints, depth, closes, window_min, min_rho, min_count, max_lag_min):
    """Ticker candidates -> one per game (argmax |rho|, ties -> min ticker). Own loop."""
    cand = []
    for tk in sorted(prints):
        c = closes.get(tk)
        if c is None:
            continue
        snaps = [s for s in depth.get(tk, []) if s[0] <= c]
        if not snaps:
            continue
        ts, cap, ya, na = snaps[-1]
        if (c - ts) > max_lag_min * 60.0:
            continue
        lo = ts - window_min * 60.0
        net = tot = 0.0
        n = 0
        for pts, side, cnt in prints[tk]:
            if pts <= lo or pts > ts:
                continue
            if side == "yes":
                net += cnt
            elif side == "no":
                net -= cnt
            else:
                continue
            tot += cnt
            n += 1
        if n == 0 or tot <= 0.0 or tot < min_count:
            continue
        rho = net / tot
        if abs(rho) < min_rho:
            continue
        fade = "no" if rho > 0 else "yes"
        ask = na if fade == "no" else ya
        if ask is None or float(ask) < 0.01:
            continue
        ask = float(ask)
        if not (0.02 <= ask <= 0.98):
            continue
        cand.append((tk.rsplit("-", 1)[0], tk, abs(rho), fade, ask, cap))
    best = {}
    for g, tk, ar, fade, ask, cap in cand:
        cur = best.get(g)
        if cur is None or ar > cur[2] or (ar == cur[2] and tk < cur[1]):
            best[g] = (g, tk, ar, fade, ask, cap)
    return len(cand), [best[g] for g in sorted(best)]


def main():
    prints, depth, closes = load()
    want = set(prints)
    settled = settled_set(want)
    n_cand, games = population(prints, depth, closes, 120.0, 0.20, 100.0, 60.0)
    scoreable = [g for g in games if g[1] in settled]
    sides = {}
    for g in scoreable:
        sides.setdefault(g[3], 0)
        sides[g[3]] += 1

    # sensitivity: same outcome-blind grid, own loops
    cells = adequate = passing = 0
    max_minority = 0
    for w in (30.0, 60.0, 120.0, 240.0, 480.0):
        for rho in (0.05, 0.10, 0.20, 0.40):
            for mc in (0.0, 100.0, 1000.0):
                for lag in (30.0, 60.0, 240.0, 4320.0):
                    _, gg = population(prints, depth, closes, w, rho, mc, lag)
                    ss = [x for x in gg if x[1] in settled]
                    per = {}
                    for x in ss:
                        per[x[3]] = per.get(x[3], 0) + 1
                    minority = min(per.values()) if len(per) > 1 else 0
                    cells += 1
                    if len(ss) >= 10:
                        adequate += 1
                        if minority >= 1:
                            passing += 1
                    max_minority = max(max_minority, minority)

    # minority-arm fillability, no gates at all
    neg = {"n": 0, "absent": 0, "floor": 0, "in_band": 0}
    pos_n = 0
    for tk in sorted(prints):
        c = closes.get(tk)
        if c is None:
            continue
        snaps = [s for s in depth.get(tk, []) if s[0] <= c]
        if not snaps:
            continue
        ts, cap, ya, na = snaps[-1]
        lo = ts - 120.0 * 60.0
        net = tot = 0.0
        n = 0
        for pts, side, cnt in prints[tk]:
            if pts <= lo or pts > ts:
                continue
            if side == "yes":
                net += cnt
            elif side == "no":
                net -= cnt
            else:
                continue
            tot += cnt
            n += 1
        if n == 0 or tot <= 0.0:
            continue
        rho = net / tot
        if rho > 0:
            pos_n += 1
        elif rho < 0:
            neg["n"] += 1
            ask = ya
            if ask is None:
                neg["absent"] += 1
            elif float(ask) <= 0.015:
                neg["floor"] += 1
            elif 0.02 <= float(ask) <= 0.98:
                neg["in_band"] += 1

    mine = {
        "n_ticker_candidates": n_cand,
        "n_game_entries": len(games),
        "n_entries_scoreable": len(scoreable),
        "n_game_units": len({g[0] for g in scoreable}),
        "units_per_side": dict(sorted(sides.items())),
        "sens_cells": cells,
        "sens_adequate": adequate,
        "sens_passing": passing,
        "sens_max_minority": max_minority,
        "neg_flow_n": neg["n"],
        "neg_flow_share": round(neg["n"] / (neg["n"] + pos_n), 4) if (neg["n"] + pos_n) else None,
        "neg_ask_absent": neg["absent"],
        "neg_ask_floor": neg["floor"],
        "neg_ask_in_band": neg["in_band"],
        "n_tickers_with_close_time": len(closes),
        "n_trade_games": len({t.rsplit("-", 1)[0] for t in want}),
    }

    with open(REPORT) as fh:
        rep = json.load(fh)
    p, sv, ma = rep["population"], rep["sign_variation_sensitivity"], rep["minority_arm_fillability"]
    theirs = {
        "n_ticker_candidates": rep["n_ticker_candidates"],
        "n_game_entries": rep["n_game_entries"],
        "n_entries_scoreable": p["n_entries_scoreable"],
        "n_game_units": p["n_game_units"],
        "units_per_side": {k: v for k, v in sorted(
            p["sign_variation"]["census"]["units_per_side"].items()) if v},
        "sens_cells": sv["n_cells"],
        "sens_adequate": sv["n_cells_meeting_unit_floor"],
        "sens_passing": sv["n_cells_meeting_unit_floor_and_sign_variation"],
        "sens_max_minority": sv["max_minority_exclusive_over_all_cells"],
        "neg_flow_n": ma["negative_flow_fade_to_yes"].get("n", 0),
        "neg_flow_share": ma["negative_flow_share"],
        "neg_ask_absent": ma["negative_flow_fade_to_yes"].get("ask_absent_one_sided_book", 0),
        "neg_ask_floor": ma["negative_flow_fade_to_yes"].get("ask_pinned_at_tick_floor", 0),
        "neg_ask_in_band": ma["negative_flow_fade_to_yes"].get("ask_in_price_band", 0),
        "n_tickers_with_close_time": rep["substrate"]["n_tickers_with_close_time"],
        "n_trade_games": rep["substrate"]["n_trade_games"],
    }
    bad = []
    print(f"{'key':32s} {'rederived':>14s} {'probe':>14s}  ok")
    for k in mine:
        ok = mine[k] == theirs[k]
        if not ok:
            bad.append(k)
        print(f"{k:32s} {str(mine[k]):>14s} {str(theirs[k]):>14s}  {'OK' if ok else 'MISMATCH'}")
    if bad:
        print(f"\nMISMATCH on {len(bad)} headline(s): {bad}")
        return 1
    print("\nAll headlines re-derived independently and agree EXACTLY.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

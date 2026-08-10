#!/usr/bin/env python3
"""q56_s80_rederive.py — INDEPENDENT second implementation of the Q56 / S80 headline numbers.

Why this file exists. The Q56 spec makes the S80 verdict VERDICT-CLASS and therefore subject
to the two-agent rule. The producing sub-context carried no `Task`/subagent tool (the
L287/L288/L290/L291/L295/L308/L313/L325 precedent), so this is the sanctioned no-verifier
redundancy fallback: a from-scratch re-derivation that shares NOTHING with the probe except
the committed tape on disk and the one fee coefficient the invariants require every module to
import rather than hand-roll.

What is deliberately NOT shared with `scripts/q56_s80_print_vwap_overshoot_maker_fade.py`:
  * its own JSONL readers (no `core.io`, no import of the probe module at all);
  * its own ISO-8601 parser, written by string slicing to UTC epoch seconds — no
    `datetime.fromisoformat`, no `core.timeutil`;
  * its own settlement reader, straight off `tape/settlement_ledger/dt=*.jsonl` and
    `tape/q51_settlement_cache/settlement.json` — NOT `core.settlement_sources`;
  * its own fee arithmetic (the round-up-to-cent rule re-implemented from the schedule text);
  * its own VWAP/window/trigger/queue/fill loop, written top-down in one function;
  * its own block bootstrap over its own `random.Random`.
`MAKER_FEE_RATE` is imported because `scripts/invariants.py::no_handrolled_fee_rate` forbids
any module but `core/pricing.py` from spelling a schedule rate — the FORMULA around it is
re-derived here, which is the part that has historically been wrong (L5).

The bootstrap CI is a genuinely independent DRAW (a different unit ordering feeds a different
`random.Random` stream), so it is expected to agree to bootstrap noise, not bit-identically.
The pooled MEAN, every population count, the fill count and the K1 overshoot are all exact
and are compared exactly.

READ-ONLY, fully offline. Run:
    python3 scripts/q56_s80_rederive.py
"""
from __future__ import annotations

import glob
import json
import math
import os
import random
import statistics
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from core.pricing import MAKER_FEE_RATE  # noqa: E402  (constant only; formula re-derived below)

WINDOW_SEC = 30 * 60
THETA = 0.02
MIN_ANCHOR = 5
MIN_RECENT = 3
NBOOT = 10000
SEED = 42


def iso_epoch(s):
    """Seconds since 1970-01-01T00:00:00Z from an ISO-8601 UTC stamp, by string slicing.
    Handles a trailing 'Z' or '+00:00' and an arbitrary fractional part. Deliberately does
    not use the datetime module's parser."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1]
    elif "+" in s[10:]:
        s = s[:s.index("+", 10)]
    date, _, clock = s.partition("T")
    y, mo, d = (int(x) for x in date.split("-"))
    frac = 0.0
    if "." in clock:
        clock, _, f = clock.partition(".")
        frac = float("0." + f)
    hh, mm, ss = (int(x) for x in clock.split(":"))
    # days from civil (Howard Hinnant's algorithm), independent of the calendar library
    yy = y - (mo <= 2)
    era = (yy if yy >= 0 else yy - 399) // 400
    yoe = yy - era * 400
    doy = (153 * (mo + (-3 if mo > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    days = era * 146097 + doe - 719468
    return days * 86400 + hh * 3600 + mm * 60 + ss + frac


def maker_fee(price):
    """Kalshi fee, round UP to the cent, at the MAKER coefficient. Re-derived from the
    schedule text rather than called out of core.pricing."""
    return math.ceil(MAKER_FEE_RATE * price * (1.0 - price) * 100.0) / 100.0


def read_prints():
    out = {}
    for path in sorted(glob.glob(os.path.join(REPO, "tape", "kalshi_trades", "dt=*.jsonl"))):
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            tk = r.get("ticker") or ""
            if not tk.split("-")[0].endswith("GAME"):
                continue
            out.setdefault(tk, []).append(
                (iso_epoch(r["created_time"]), float(r["yes_price"]), float(r["count"]),
                 r.get("taker_book_side"), r.get("trade_id")))
    for tk in out:
        out[tk].sort(key=lambda x: (x[0], x[4] or ""))
    return out


def read_books(tickers):
    out = {}
    for path in sorted(glob.glob(os.path.join(REPO, "tape", "orderbook_depth", "dt=*.jsonl"))):
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ticker") in tickers:
                out.setdefault(r["ticker"], []).append(r)
    for tk in out:
        out[tk].sort(key=lambda r: iso_epoch(r["captured_at"]))
    return out


def read_settlements(tickers):
    """Independent settlement read: the day-partitioned ledger plus the q51 cache blob."""
    res = {}
    for path in sorted(glob.glob(os.path.join(REPO, "tape", "settlement_ledger", "dt=*.jsonl"))):
        for line in open(path):
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("ticker") in tickers and r.get("result") in ("yes", "no"):
                res[r["ticker"]] = r["result"]
    for path in sorted(glob.glob(os.path.join(REPO, "tape", "q51_settlement_cache", "*.json"))):
        blob = json.load(open(path))
        for tk, m in (blob.get("markets") or {}).items():
            if tk in tickers and (m or {}).get("result") in ("yes", "no"):
                res.setdefault(tk, m["result"])
    return res


def boot(units, n_boot=NBOOT, seed=SEED):
    keys = sorted(units)
    if not keys:
        return None, [None, None]
    tot = sum(sum(units[k]) for k in keys)
    cnt = sum(len(units[k]) for k in keys)
    mean = tot / cnt
    rng = random.Random(seed)
    ms = []
    for _ in range(n_boot):
        t = c = 0.0
        for _ in keys:
            v = units[rng.choice(keys)]
            t += sum(v)
            c += len(v)
        if c:
            ms.append(t / c)
    ms.sort()
    return mean, [ms[int(0.025 * len(ms))], ms[int(0.975 * len(ms))]]


def main():
    prints = read_prints()
    books = read_books(set(prints))
    res = read_settlements(set(prints))

    # --- K1: per-ticker print VWAP vs settlement, aligned to the registered fade direction
    k1_units = {}
    lead, trail = [], []
    for tk, prs in prints.items():
        if tk not in res:
            continue
        w = sum(p[2] for p in prs)
        if w <= 0:
            continue
        v = sum(p[1] * p[2] for p in prs) / w
        settle = 1.0 if res[tk] == "yes" else 0.0
        over = v - settle
        chased_yes = v >= 0.5
        (lead if chased_yes else trail).append(over)
        k1_units.setdefault(tk.rsplit("-", 1)[0], []).append(over if chased_yes else -over)
    k1_mean, k1_ci = boot(k1_units)

    # --- the registered leg
    n_cand = n_fill = 0
    units_all, units_fill = {}, {}
    traceable = 0
    for tk in sorted(books):
        prs = prints.get(tk) or []
        if not prs or tk not in res:
            continue
        snaps = books[tk]
        for i in range(len(snaps) - 1):
            t0 = iso_epoch(snaps[i]["captured_at"])
            t1 = iso_epoch(snaps[i + 1]["captured_at"])
            a = [p for p in prs if p[0] < t0 - WINDOW_SEC]
            rcnt = [p for p in prs if t0 - WINDOW_SEC <= p[0] < t0]
            if len(a) < MIN_ANCHOR or len(rcnt) < MIN_RECENT:
                continue
            aw, rw = sum(p[2] for p in a), sum(p[2] for p in rcnt)
            if aw <= 0 or rw <= 0:
                continue
            chase = (sum(p[1] * p[2] for p in rcnt) / rw) - (sum(p[1] * p[2] for p in a) / aw)
            if abs(chase) < THETA - 1e-9 or chase == 0:
                continue
            side = "no" if chase > 0 else "yes"
            snap = snaps[i]
            price = snap.get("best_no_bid") if side == "no" else snap.get("best_yes_bid")
            if price is None:
                continue
            price = float(price)
            book_side = snap.get("no_bids") if side == "no" else snap.get("yes_bids")
            ahead = sum(float(lv[1]) for lv in (book_side or []) if float(lv[0]) >= price - 1e-9)
            got = None
            run = 0.0
            for p in prs:
                if not (t0 < p[0] <= t1):
                    continue
                if side == "no":
                    ok = p[3] == "bid" and p[1] >= (1.0 - price) - 1e-9
                else:
                    ok = p[3] == "ask" and p[1] <= price + 1e-9
                if not ok:
                    continue
                run += p[2]
                if run > ahead + 1e-9:
                    got = p[4]
                    break
            n_cand += 1
            game = tk.rsplit("-", 1)[0]
            if got is None:
                units_all.setdefault(game, []).append(0.0)
                continue
            n_fill += 1
            traceable += 1 if got else 0
            win = (side == res[tk])
            pnl = (1.0 if win else 0.0) - price - maker_fee(price)
            units_all.setdefault(game, []).append(pnl)
            units_fill.setdefault(game, []).append(pnl)

    m_all, ci_all = boot(units_all)
    m_fill, ci_fill = boot(units_fill)

    out = {
        "rederive_of": "q56_s80_print_vwap_overshoot_maker_fade",
        "independent": True,
        "tape": {"n_tickers": len(prints), "n_games": len({t.rsplit('-', 1)[0] for t in prints}),
                 "n_prints": sum(len(v) for v in prints.values()),
                 "n_settled_tickers": len(res)},
        "K1": {"n_units_games": len(k1_units), "mean": k1_mean, "ci95": k1_ci,
               "maker_fee_at_0_50": maker_fee(0.50),
               "mean_overshoot_leading_side": statistics.mean(lead) if lead else None,
               "n_leading": len(lead),
               "mean_overshoot_trailing_side": statistics.mean(trail) if trail else None,
               "n_trailing": len(trail)},
        "fill": {"n_candidates": n_cand, "n_fills": n_fill,
                 "fill_rate": (n_fill / n_cand) if n_cand else None,
                 "n_games_with_candidate": len(units_all),
                 "n_games_with_fill": len(units_fill),
                 "fills_traceable_to_print_id": traceable},
        "branch_all_candidates": {"mean": m_all, "ci95": ci_all},
        "branch_conditional_on_fill": {"mean": m_fill, "ci95": ci_fill},
        "price_source_tags": {"fill_price": "real_bid", "fill_evidence": "broker_truth",
                              "settlement": "broker_truth", "signal": "broker_truth"},
    }
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

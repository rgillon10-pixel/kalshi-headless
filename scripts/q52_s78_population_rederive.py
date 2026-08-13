#!/usr/bin/env python3
"""Independent re-derivation of the Q52/S78 sealed probe's OUTCOME-BLIND population report.

This is the sanctioned NO-VERIFIER REDUNDANCY FALLBACK, and it is reported as redundancy,
never as verification (the L287/L288/L290/L291/L295/L308/L313/L325 precedent chain, and the
`scripts/q56_s80_rederive.py` shape). It shares NO code with the probe: its own JSONL
readers, its own hand-rolled ISO-8601 parser, its own game key, its own orientation
statement, its own linear-scan book join, its own queue-aware fill loop, and a settlement
read that goes straight at the committed cache/ledger files instead of through
`core.settlement_sources`. Two implementations agreeing is evidence the number is not a
typo; it is NOT the two-agent verdict rule, which needs a second AGENT.

What it re-derives (all outcome-blind — it never reads a settlement result's VALUE):
  * the train/holdout day split and the straddling-game drop
  * the 4-cell TRAIN markout table and which cells the admission rule admits
  * the holdout candidate count, fill count, and bootstrap-unit (game) count
  * the exclusive-minority-side unit count

Read-only, offline, no network, no credentials.
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from core.pricing import MAKER_FEE_RATE as MAKER_RATE  # noqa: E402  (see the L5 note below)

TRADES = os.path.join(REPO, "tape", "kalshi_trades")
DEPTH = os.path.join(REPO, "tape", "orderbook_depth")

# Spec constants restated from the sealed pre-registration ON PURPOSE. Importing them would
# make an agreement between the two implementations partly circular.
HORIZON_S = 30 * 60.0
PRICE_THRESHOLD = 0.50
WIDE_SPREAD_MIN = 0.03
MAX_STALENESS_S = 240 * 60.0
MAX_INTERVAL_S = 240 * 60.0
MIN_TRAIN_PRINTS = 30
BAND_LO, BAND_HI = 0.02, 0.98
# The RATE is imported, not restated. Independence stops at L5's line: a hand-rolled fee
# LITERAL is a GATING invariant failure (`no_handrolled_fee_rate`) precisely because a
# 4x maker/taker mix-up sank an S13 draft, and this file's first draft tripped it. The
# rate is a venue FACT with one sanctioned site; what stays independent here is the
# round-up-to-cent FORMULA below, which is the part an implementation can get wrong.
MIN_UNITS = 10
MIN_EXCLUSIVE_MINORITY = 2


def _epoch(text: str) -> Optional[float]:
    """Hand-rolled ISO-8601 -> epoch seconds. Deliberately not `core.timeutil.parse_iso_utc`."""
    if not text:
        return None
    t = text.strip().replace("Z", "+00:00")
    date_part, _, rest = t.partition("T")
    try:
        y, mo, d = (int(x) for x in date_part.split("-"))
    except Exception:
        return None
    off = 0.0
    for sign in ("+", "-"):
        idx = rest.rfind(sign)
        if idx > 0:
            hh, _, mm = rest[idx + 1:].partition(":")
            mag = int(hh) * 3600 + int(mm or 0) * 60
            off = -mag if sign == "+" else mag
            rest = rest[:idx]
            break
    hms, _, frac = rest.partition(".")
    try:
        h, mi, s = (int(x) for x in hms.split(":"))
    except Exception:
        return None
    days = _days_from_civil(y, mo, d)
    sub = float("0." + frac) if frac else 0.0
    return days * 86400.0 + h * 3600.0 + mi * 60.0 + s + sub + off


def _days_from_civil(y: int, m: int, d: int) -> int:
    """Howard Hinnant's civil-from-days inverse — no datetime module anywhere in this file."""
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _day_of(epoch_s: float) -> str:
    days = int(math.floor(epoch_s / 86400.0))
    z = days + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + (3 if mp < 10 else -9)
    y += m <= 2
    return "%04d-%02d-%02d" % (y, m, d)


def _fee(price: float) -> float:
    return math.ceil(MAKER_RATE * price * (1.0 - price) * 100.0) / 100.0


def _game(ticker: str) -> str:
    return ticker.rsplit("-", 1)[0]


def _is_game(ticker: str) -> bool:
    return ticker.split("-", 1)[0].endswith("GAME")


def load() -> Tuple[Dict[str, List[tuple]], Dict[str, List[tuple]]]:
    prints: Dict[str, List[tuple]] = {}
    for path in sorted(glob.glob(os.path.join(TRADES, "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                tk = r.get("ticker")
                if not tk or not _is_game(tk):
                    continue
                ts = _epoch(r.get("created_time") or "")
                if ts is None:
                    continue
                prints.setdefault(tk, []).append(
                    (ts, float(r.get("yes_price") or 0.0), float(r.get("count") or 0.0),
                     str(r.get("taker_book_side") or ""), str(r.get("trade_id") or "")))
    for v in prints.values():
        v.sort(key=lambda x: (x[0], x[4]))

    books: Dict[str, List[tuple]] = {}
    for path in sorted(glob.glob(os.path.join(DEPTH, "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                tk = r.get("ticker")
                if not tk or tk not in prints:
                    continue
                ts = _epoch(r.get("captured_at") or "")
                if ts is None:
                    continue
                books.setdefault(tk, []).append((ts, r))
    for v in books.values():
        v.sort(key=lambda x: x[0])
    return prints, books


def settled_binary() -> set:
    """Which tickers carry a binary result — read STRAIGHT at the committed cache/ledger
    files. Membership only: the result's VALUE is never returned."""
    out = set()
    for pat in ("q51_settlement_cache/*.json", "q56_settlement_cache/*.json",
                "q26_settlement_cache/*.json", "q27_settlement_cache/*.json",
                "q29_settlement_cache/*.json", "q30_settlement_cache/*.json"):
        for path in sorted(glob.glob(os.path.join(REPO, "tape", pat))):
            try:
                blob = json.load(open(path))
            except Exception:
                continue
            for tk, rec in (blob.get("markets") or {}).items():
                if isinstance(rec, dict) and str(rec.get("result", "")).lower() in ("yes", "no"):
                    out.add(tk)
    for path in sorted(glob.glob(os.path.join(REPO, "tape", "settlement_ledger", "dt=*.jsonl"))):
        with open(path) as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = json.loads(line)
                if str(r.get("result", "")).lower() in ("yes", "no") and r.get("ticker"):
                    out.add(r["ticker"])
    return out


def maker_leg(yes_price: float, tbs: str) -> Optional[Tuple[str, float]]:
    """Independent orientation statement: `taker_book_side` is where the TAKER'S order sat.
    'bid' => the taker was the buyer => the maker ended up SHORT yes, i.e. long NO."""
    if tbs == "bid":
        return ("no", 1.0 - yes_price)
    if tbs == "ask":
        return ("yes", yes_price)
    return None


# The cent-tick epsilon. NOT cosmetic: on a venue quoted in whole cents, `0.71 - 0.68`
# evaluates to 0.029999999999999916 in binary floating point, so an EXACT `>= 0.03` test
# calls a genuine three-cent spread TIGHT. The first draft of this file used the exact test
# and disagreed with the probe on 163 cheap and 96 rich TRAIN prints and on the holdout's
# per-side unit census — a mismatch manufactured entirely by the comparison convention, not
# by the data. Kept behind a flag so the discovery stays reproducible.
EPS = 1e-9


def cell(price: float, spread: float, *, exact_boundary: bool = False) -> str:
    eps = 0.0 if exact_boundary else EPS
    return ("rich" if price >= PRICE_THRESHOLD - eps else "cheap") + "/" + \
           ("wide" if spread >= WIDE_SPREAD_MIN - eps else "tight")


def run(*, exact_boundary: bool = False) -> dict:
    prints, books = load()
    days = sorted({_day_of(p[0]) for rows in prints.values() for p in rows})
    cut = len(days) // 2
    train_days, hold_days = set(days[:cut]), set(days[cut:])

    gdays: Dict[str, set] = {}
    for tk, rows in prints.items():
        gdays.setdefault(_game(tk), set()).update(_day_of(p[0]) for p in rows)
    train_g = {g for g, ds in gdays.items() if (ds & train_days) and not (ds & hold_days)}
    hold_g = {g for g, ds in gdays.items() if (ds & hold_days) and not (ds & train_days)}
    strad = {g for g, ds in gdays.items() if (ds & train_days) and (ds & hold_days)}

    # ---- TRAIN cell table -------------------------------------------------- #
    agg: Dict[str, List[float]] = {}
    for tk, rows in prints.items():
        if _game(tk) not in train_g:
            continue
        snaps = books.get(tk) or []
        for i, p in enumerate(rows):
            leg = maker_leg(p[1], p[3])
            if leg is None:
                continue
            side, mprice = leg
            mark = None
            for q in rows[i + 1:]:
                if q[0] > p[0] + HORIZON_S:
                    break
                if q[0] > p[0]:
                    mark = q[1]
            if mark is None:
                continue
            snap = None
            for ts, rec in snaps:                      # linear scan, not a bisect
                if ts <= p[0]:
                    snap = (ts, rec)
                else:
                    break
            if snap is None or p[0] - snap[0] > MAX_STALENESS_S:
                continue
            hi, lo = snap[1].get("best_yes_ask"), snap[1].get("best_yes_bid")
            if hi is None or lo is None:
                continue
            mo = (p[1] - mark) if side == "no" else (mark - p[1])
            k = cell(mprice, float(hi) - float(lo), exact_boundary=exact_boundary)
            a = agg.setdefault(k, [0.0, 0.0, 0])
            a[0] += mo
            a[1] += mprice
            a[2] += 1

    table, admitted = {}, set()
    for k in ("cheap/tight", "cheap/wide", "rich/tight", "rich/wide"):
        s, ps, n = agg.get(k, [0.0, 0.0, 0])
        if n == 0:
            table[k] = {"n": 0, "mean_markout": None, "net_of_fee": None, "admitted": False}
            continue
        mm, mp = s / n, ps / n
        net = mm - _fee(mp)
        ok = n >= MIN_TRAIN_PRINTS and net > 0
        table[k] = {"n": n, "mean_markout": mm, "mean_maker_price": mp,
                    "net_of_fee": net, "admitted": ok}
        if ok:
            admitted.add(k)

    # ---- HOLDOUT candidates + queue-aware fills ---------------------------- #
    settled = settled_binary()
    n_cand = n_score = n_fill = 0
    units: Dict[str, set] = {}
    for tk in sorted(prints):
        if _game(tk) not in hold_g:
            continue
        snaps = books.get(tk) or []
        if len(snaps) < 2:
            continue
        rows = prints[tk]
        for i in range(len(snaps) - 1):
            t0, rec = snaps[i]
            t1 = snaps[i + 1][0]
            if t1 - t0 > MAX_INTERVAL_S:
                continue
            hi, lo = rec.get("best_yes_ask"), rec.get("best_yes_bid")
            if hi is None or lo is None:
                continue
            spread = float(hi) - float(lo)
            window = [p for p in rows if t0 < p[0] <= t1]
            for side in ("yes", "no"):
                bid = rec.get("best_yes_bid") if side == "yes" else rec.get("best_no_bid")
                if bid is None:
                    continue
                bid = float(bid)
                if not (BAND_LO <= bid <= BAND_HI):
                    continue
                if cell(bid, spread, exact_boundary=exact_boundary) not in admitted:
                    continue
                n_cand += 1
                if tk not in settled:
                    continue
                n_score += 1
                units.setdefault(_game(tk), set()).add(side)
                ladder = rec.get("yes_bids") if side == "yes" else rec.get("no_bids")
                qa = sum(float(l[1]) for l in (ladder or []) if float(l[0]) >= bid - 1e-9)
                cum = 0.0
                for _, yp, cnt, tbs, _tid in window:
                    consumes = (tbs == "bid" and yp >= (1.0 - bid) - 1e-9) if side == "no" \
                        else (tbs == "ask" and yp <= bid + 1e-9)
                    if not consumes:
                        continue
                    cum += cnt
                    if cum > qa + 1e-9:
                        n_fill += 1
                        break

    per_side = {"yes": 0, "no": 0}
    excl = {"yes": 0, "no": 0}
    for g, sides in units.items():
        for s in sides:
            per_side[s] += 1
        if len(sides) == 1:
            excl[next(iter(sides))] += 1
    minority = min(per_side, key=lambda s: per_side[s]) if units else None
    excl_minority = excl.get(minority, 0) if minority else 0

    return {
        "trade_days": days,
        "train_days": sorted(train_days), "holdout_days": sorted(hold_days),
        "n_games_total": len(gdays), "n_train_games": len(train_g),
        "n_holdout_games": len(hold_g), "n_straddling_games_dropped": len(strad),
        "train_cell_table": table, "admitted_cells": sorted(admitted),
        "n_candidates_all": n_cand, "n_candidates_scoreable": n_score,
        "n_fills_scoreable": n_fill, "n_units": len(units),
        "units_per_side": per_side, "exclusive_units_per_side": excl,
        "exclusive_minority_units": excl_minority,
        "gate_clears_min_units": len(units) >= MIN_UNITS,
        "gate_clears_exclusive_minority": excl_minority >= MIN_EXCLUSIVE_MINORITY,
        "price_source_tags": {"rest_price": "real_bid", "fill_evidence": "broker_truth",
                              "toxicity_signal": "broker_truth", "settlement": "broker_truth"},
        "exact_boundary": exact_boundary,
        "network_calls": 0,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--exact-boundary", action="store_true",
                    help="use an EXACT >= threshold test (reproduces the float-noise mismatch)")
    args = ap.parse_args(argv)
    rep = run(exact_boundary=args.exact_boundary)
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print("REDERIVE cells=%s train_g=%d hold_g=%d strad=%d cand=%d/%d fills=%d units=%d "
              "excl_minority=%d" % (rep["admitted_cells"], rep["n_train_games"],
                                    rep["n_holdout_games"], rep["n_straddling_games_dropped"],
                                    rep["n_candidates_scoreable"], rep["n_candidates_all"],
                                    rep["n_fills_scoreable"], rep["n_units"],
                                    rep["exclusive_minority_units"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

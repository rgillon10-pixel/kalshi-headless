#!/usr/bin/env python3
"""q56_s81_rederive.py — INDEPENDENT second implementation of the Q56 / S81 headline numbers.

Why this file exists. Firing S81's sealed binding test is VERDICT-CLASS and therefore subject
to LOOP-QUEUE.md's two-agent rule. No `Task`/subagent tool exists in this run's harness (the
L287/L288/L290/L291/L295/L308/L313/L325 precedent), so this is the sanctioned no-verifier
REDUNDANCY fallback — and it is reported as redundancy, never as verification. It cannot catch
an error the two implementations share (both read the same tape and both believe the
pre-registered design), and it is not claimed to.

What is deliberately NOT shared with `scripts/q56_s81_funding_regime_settlement_probe.py`:
  * its own JSONL readers — no `core.io`, no `scripts.hl_funding_tape_quality`, and it never
    imports the probe module at all;
  * its own ISO-8601 -> UTC-epoch parser, written by string slicing + days-from-civil — no
    `datetime.fromisoformat`, no `core.timeutil`;
  * the funding baseline re-derived from L318's TEXT (0.01% per 8h, hourly) rather than
    imported as a constant;
  * its own hour indexing, regime labelling and run blocking, written top-down;
  * its own entry-snapshot selection, adjacent-above leg picker and fillability band;
  * its own settlement reader, straight off `tape/crypto_hourly/`'s embedded
    `previous_settlement` blocks and `tape/q56_settlement_cache/settlement*.json` — NOT
    `core.settlement_sources`, NOT `core.settlement`;
  * its own fee arithmetic (round-up-to-cent, re-derived from the schedule text);
  * its own block bootstrap over its own `random.Random`, on a DIFFERENT seed.
`TAKER_FEE_RATE` is imported because `scripts/invariants.py::no_handrolled_fee_rate` forbids
any module but `core/pricing.py` from spelling a schedule rate. The FORMULA around it is
re-derived here, which is the part that has historically been wrong (L5).

Exact-agreement expectations: every population count, the scored-row count, the unit count and
the pooled MEAN are exact and compared exactly. The bootstrap CI is an independent DRAW (own
RNG, own seed) and is expected to agree to bootstrap noise only — the sign CONCLUSION is what
is compared there.

READ-ONLY, fully offline. Run:
    python3 scripts/q56_s81_rederive.py
"""
from __future__ import annotations

import glob
import json
import math
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from core.pricing import TAKER_FEE_RATE  # noqa: E402  (rate constant only; formula below)

# L318, in words: Hyperliquid's funding interest baseline is 0.01% per 8 hours. Per hour:
BASELINE = (0.01 / 100.0) / 8.0
MAX_ASK = 0.98
MIN_TICK = 0.01
NBOOT = 10000
SEED = 20260811          # deliberately NOT the probe's 42


# ─── own time parsing ────────────────────────────────────────────────────────────────
def _days_from_civil(y, m, d):
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def iso_epoch(s):
    """Seconds (float) since the epoch from an ISO-8601 UTC stamp, by string slicing."""
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1]
    elif "+" in s[10:]:
        s = s[:s.index("+", 10)]
    date_part, _, time_part = s.partition("T")
    y, mo, d = (int(x) for x in date_part.split("-"))
    hh, mm, rest = time_part.split(":")[0], time_part.split(":")[1], time_part.split(":")[2]
    frac = 0.0
    if "." in rest:
        sec, _, f = rest.partition(".")
        frac = float("0." + f)
    else:
        sec = rest
    return _days_from_civil(y, mo, d) * 86400 + int(hh) * 3600 + int(mm) * 60 + int(sec) + frac


# ─── own readers ─────────────────────────────────────────────────────────────────────
def jsonl(pattern):
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    yield obj


def funding_hours():
    out = {}
    for rec in jsonl(os.path.join(REPO, "tape/hyperliquid_funding/dt=*.jsonl")):
        if rec.get("record_type") != "funding_history":
            continue
        coin = rec.get("coin")
        if not coin:
            continue
        for pr in rec.get("prints") or []:
            ms, rate = pr.get("time_ms"), pr.get("funding_rate")
            if not isinstance(ms, (int, float)) or rate is None:
                continue
            out[(coin, int(round(ms / 3600000.0)))] = float(rate)
    return out


def label_of(rate):
    if rate == BASELINE:
        return "pin"
    if rate < 0:
        return "negative"
    if rate < BASELINE:
        return "sub_baseline"
    return "above_baseline"


def runs_of(hours):
    """(coin, hour) -> (run_id, label); a maximal block of CONSECUTIVE same-label hours."""
    out = {}
    coins = {}
    for (coin, hour) in hours:
        coins.setdefault(coin, []).append(hour)
    for coin, hs in coins.items():
        prev_h = prev_l = None
        idx = 0
        for hour in sorted(hs):
            lab = label_of(hours[(coin, hour)])
            if prev_h is None or hour != prev_h + 1 or lab != prev_l:
                idx += 1
            out[(coin, hour)] = ("%s-run%04d" % (coin, idx), lab)
            prev_h, prev_l = hour, lab
    return out


# ─── own settlement reader (embedded crypto_hourly + the Q56 backfill cache) ─────────
BINARY = {"yes", "no"}


def settlement_map():
    out = {}
    for rec in jsonl(os.path.join(REPO, "tape/crypto_hourly/dt=*.jsonl")):
        block = rec.get("previous_settlement")
        if not isinstance(block, dict):
            continue
        for tk, res in (block.get("results") or {}).items():
            if isinstance(res, str) and res.strip().lower() in BINARY:
                out.setdefault(tk, res.strip().lower())
    for path in sorted(glob.glob(os.path.join(REPO,
                                              "tape/q56_settlement_cache/settlement*.json"))):
        with open(path, encoding="utf-8") as fh:
            blob = json.load(fh)
        for tk, rec in (blob.get("markets") or {}).items():
            res = rec.get("result")
            if isinstance(res, str) and res.strip().lower() in BINARY:
                out.setdefault(tk, res.strip().lower())
    return out


# ─── own entry construction ──────────────────────────────────────────────────────────
def entries(runs):
    best = {}
    for rec in jsonl(os.path.join(REPO, "tape/crypto_hourly/dt=*.jsonl")):
        cur = rec.get("current") or {}
        if cur.get("status") != "ok":
            continue
        event, sym = cur.get("event_ticker"), rec.get("symbol")
        cap, close = rec.get("captured_at"), cur.get("close_time")
        if not (event and sym and cap and close):
            continue
        try:
            cap_e, close_e = iso_epoch(cap), iso_epoch(close)
        except (ValueError, IndexError):
            continue
        if cap_e >= close_e:
            continue
        key = (str(sym), str(event))
        if key not in best or cap_e > best[key][0]:
            best[key] = (cap_e, rec)

    rows = []
    for (coin, event), (cap_e, rec) in sorted(best.items()):
        spot = (rec.get("spot") or {}).get("price")
        if spot is None:
            continue
        run = runs.get((coin, int(cap_e // 3600)))
        if run is None:
            continue
        run_id, lab = run
        outs = [o for o in ((rec.get("current") or {}).get("outcomes") or [])
                if o.get("strike_type") == "between"
                and o.get("floor_strike") is not None and o.get("cap_strike") is not None]
        holding = [o for o in outs
                   if float(o["floor_strike"]) <= float(spot) <= float(o["cap_strike"])]
        leg = None
        if len(holding) == 1:
            above = [o for o in outs
                     if float(o["floor_strike"]) > float(holding[0]["cap_strike"])]
            if above:
                leg = min(above, key=lambda o: float(o["floor_strike"]))
        ask = None if leg is None else leg.get("yes_ask")
        bid = None if leg is None else leg.get("yes_bid")
        fillable = (ask is not None and bid is not None
                    and not math.isnan(float(ask))
                    and float(ask) >= MIN_TICK - 1e-9
                    and float(ask) <= MAX_ASK and float(bid) > 0.0)
        cell = ("informative" if lab in ("sub_baseline", "negative")
                else "control" if lab == "pin" else "excluded")
        rows.append({"coin": coin, "event": event, "run_id": run_id, "regime": lab,
                     "cell": cell, "leg": None if leg is None else leg.get("ticker"),
                     "ask": None if ask is None else float(ask), "fillable": bool(fillable)})
    return rows


# ─── own fee + bootstrap ─────────────────────────────────────────────────────────────
def fee(price):
    """Round-up-to-cent on rate * P * (1-P), re-derived from the published schedule."""
    return math.ceil(TAKER_FEE_RATE * price * (1.0 - price) * 100.0) / 100.0


def boot(units, n_boot=NBOOT, seed=SEED):
    keys = sorted(units)
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        tot = cnt = 0
        for _ in keys:
            vals = units[keys[rng.randrange(len(keys))]]
            tot += sum(vals)
            cnt += len(vals)
        if cnt:
            means.append(tot / cnt)
    means.sort()
    lo = means[int(0.025 * (len(means) - 1))]
    hi = means[int(math.ceil(0.975 * (len(means) - 1)))]
    return lo, hi


def main():
    hours = funding_hours()
    rows = entries(runs_of(hours))
    settled = settlement_map()
    joinable = [r for r in rows if r["leg"] in settled]
    inf = [r for r in joinable if r["cell"] == "informative"]
    inf_fill = [r for r in inf if r["fillable"]]
    units = {}
    for r in inf_fill:
        pnl = (1.0 if settled[r["leg"]] == "yes" else 0.0) - r["ask"] - fee(r["ask"])
        units.setdefault(r["run_id"], []).append(pnl)
    vals = [v for lst in units.values() for v in lst]
    mean = sum(vals) / len(vals) if vals else None
    lo, hi = boot(units) if units else (None, None)
    n_opposing = sum(1 for lst in units.values() if sum(lst) / len(lst) > 0) if mean is not None \
        and mean < 0 else sum(1 for lst in units.values() if sum(lst) / len(lst) < 0)
    out = {
        "n_entry_rows": len(rows),
        "n_joinable": len(joinable),
        "n_unjoinable": len(rows) - len(joinable),
        "informative_entries": len(inf),
        "informative_fillable": len(inf_fill),
        "informative_runs": len({r["run_id"] for r in inf}),
        "informative_fillable_runs": len(units),
        "control_entries": sum(1 for r in joinable if r["cell"] == "control"),
        "n_scored": len(vals),
        "mean": mean,
        "ci95_independent_draw": [lo, hi],
        "n_opposing_units": n_opposing,
        "seed": SEED,
        "n_boot": NBOOT,
    }
    print(json.dumps(out, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

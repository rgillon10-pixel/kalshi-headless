#!/usr/bin/env python3
"""Q51 — data-quality deep-dive on the `kalshi_trades` executed-print tape.

Idle-run policy (c) (LOOP-QUEUE.md, protocol v3), 2026-08-04. READ-ONLY and FULLY OFFLINE:
this module opens committed tape files and nothing else — no network, no credentials, no
orders, no writes outside `reports/`. It produces a DATA-QUALITY verdict, never a P&L,
never a CI, never a registry flip.

Why a second look at a one-day-old family. `tape/kalshi_trades/` landed the same day as this
audit (Q51 milestone 1) and was immediately re-read backwards (L279): milestone 1's headline
coverage number survived the correction, but nothing had yet audited the tape as a TAPE —
its internal identity, its day-boundary behaviour, or the direction of its join to
`orderbook_depth`. Milestone 1 measured coverage BOOK-SIDE ("of the book intervals I hold,
how many contain a print?"). This module measures the DUAL, PRINT-SIDE ("of the prints I
hold, how many sit inside a book interval I can price against?"). The two are not the same
number and the gap between them is the finding.

Six measurements, each falsifiable from committed bytes:

1. `tape_integrity` — trade_id uniqueness, the `yes_price + no_price == 1` book identity,
   tick granularity, positive size, `trade_day` vs the UTC day of `created_time`, capture
   ordering (`captured_at >= created_time`), the tag/schema enum, hour-of-day coverage, and
   the two fields whose SHAPE is easy to misread: `event_ticker` (structurally null — the
   `/markets/trades` payload has no such field, verified live 2026-08-04 with one read-only
   public GET) and `raw_sha256` (a per-QUERY digest shared by every line of a ticker's pull,
   NOT a per-line content hash — a consumer must not treat it as line-level integrity).
2. `print_join_profile` — the dual coverage above, plus the staleness ladder: how old is the
   preceding book snapshot at the moment each print executes. Reported twice: same-day only
   (what `scripts/q51_maker_fillsim.py` actually reads) and with adjacent days admitted
   (the best case the tape could support).
3. `book_pass_profile` — the cadence of the `orderbook_depth` passes themselves, because a
   print-side coverage hole is a BOOK-side defect: if the depth collector skips passes, the
   trade tape is fine and the join still dies.
4. `fill_capacity` — the size question every fill-sim in this repo has so far ignored. A
   print is evidence that SOMEONE traded; it bounds how much of MY resting order could have
   filled. Given the already-committed milestone-2 rows, how much qualifying size actually
   landed in each filled leg's interval, and what order size does that support?
5. `event_key_check` — `game_of()` (the bootstrap unit, L6) is derived from the ticker
   STRING because the print tape has no event field. Validated against the venue's own
   `event_ticker` from `tape/q51_settlement_cache/` — a derived resample unit that disagrees
   with the venue would invalidate every block bootstrap built on it.
6. `settlement_gate` — offline, from the committed cache: when does Q51 milestone 3's
   time gate actually open? (The queue spec says "once the 2026-08-04..08-09 games have been
   played"; the cache's own close_times say otherwise.)

Run:
    python3 scripts/q51_trade_tape_quality.py
    python3 scripts/q51_trade_tape_quality.py --day 2026-08-03 --json-out reports/x.json
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402

from scripts.q51_maker_fillsim import (  # noqa: E402
    CACHE_PATH,
    DAY,
    DEPTH_TAPE,
    ROWS_PATH,
    TAKER_BUYS,
    TAKER_SELLS,
    TRADES_TAPE,
    game_of,
    load_depth,
    load_prints,
    parse_ts,
)

REPORT_PATH = REPO_ROOT / "reports" / "q51_trade_tape_quality.json"
SCHEMA_VERSION = "q51_trade_tape_quality.v1"

# Order sizes the capacity curve is evaluated at. 1 is the unit every fill-sim in this repo
# has implicitly assumed; the larger rungs say what the same evidence supports at scale.
CAPACITY_SIZES = (1.0, 10.0, 100.0, 1000.0)

# Staleness rungs (minutes) for the print-side freshness ladder.
FRESHNESS_RUNGS = (15.0, 60.0, 180.0)


# --------------------------------------------------------------------------- #
# raw loading (integrity needs every field, not the fill-sim's projection)
# --------------------------------------------------------------------------- #
def load_raw_prints(day: str = DAY, path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every line of the trade day-file as parsed JSON, in file order. Malformed lines are
    COUNTED by the caller, not silently dropped, so a parse failure lowers the verdict."""
    p = path or (TRADES_TAPE / f"dt={day}.jsonl")
    out: List[Dict[str, Any]] = []
    if not p.exists():
        return out
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"__parse_error__": True})
    return out


def load_depth_multi(days: Sequence[str]) -> Dict[str, List[dict]]:
    """ticker -> time-sorted snapshots unioned across several day-files."""
    merged: Dict[str, List[dict]] = {}
    for d in days:
        _, snaps = load_depth(d)
        for tk, rows in snaps.items():
            merged.setdefault(tk, []).extend(rows)
    for v in merged.values():
        v.sort(key=lambda r: r["ts"])
    return merged


def adjacent_days(day: str) -> List[str]:
    """[day-1, day, day+1] as YYYY-MM-DD."""
    d = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return [(d.replace(hour=12) + _delta(k)).strftime("%Y-%m-%d") for k in (-1, 0, 1)]


def _delta(days: int):
    from datetime import timedelta

    return timedelta(days=days)


# --------------------------------------------------------------------------- #
# 1. tape integrity
# --------------------------------------------------------------------------- #
def tape_integrity(raw: Sequence[Dict[str, Any]], day: str = DAY) -> Dict[str, Any]:
    """Line-level facts about the trade tape alone. Every counter is a DEFECT count except
    where named `n_*`/`distinct_*`; a healthy tape reports zeros."""
    n = len(raw)
    parse_errors = sum(1 for r in raw if r.get("__parse_error__"))
    rows = [r for r in raw if not r.get("__parse_error__")]

    ids = collections.Counter(r.get("trade_id") for r in rows)
    dup_ids = sum(v - 1 for v in ids.values() if v > 1)

    price_identity_violations = 0
    sub_tick_prices = 0
    nonpositive_size = 0
    fractional_size = 0
    for r in rows:
        yp, np_ = r.get("yes_price"), r.get("no_price")
        if isinstance(yp, (int, float)) and isinstance(np_, (int, float)):
            if abs(float(yp) + float(np_) - 1.0) > 1e-9:
                price_identity_violations += 1
        if isinstance(yp, (int, float)):
            if abs(float(yp) * 100.0 - round(float(yp) * 100.0)) > 1e-9:
                sub_tick_prices += 1
        c = r.get("count")
        if not isinstance(c, (int, float)) or float(c) <= 0:
            nonpositive_size += 1
        elif abs(float(c) - round(float(c))) > 1e-9:
            fractional_size += 1

    day_mismatch = 0
    captured_before_created = 0
    hours = collections.Counter()
    for r in rows:
        ct = r.get("created_time") or ""
        ts = parse_ts(ct)
        if ts is None:
            day_mismatch += 1
            continue
        utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        if utc.strftime("%Y-%m-%d") != (r.get("trade_day") or ""):
            day_mismatch += 1
        hours[utc.strftime("%H")] += 1
        cap = parse_ts(r.get("captured_at"))
        if cap is not None and cap < ts:
            captured_before_created += 1

    shas = collections.Counter(r.get("raw_sha256") for r in rows)
    sizes = sorted(float(r["count"]) for r in rows
                   if isinstance(r.get("count"), (int, float)) and float(r["count"]) > 0)

    return {
        "n_lines": n,
        "n_parse_errors": parse_errors,
        "n_distinct_trade_ids": len(ids),
        "n_duplicate_trade_ids": dup_ids,
        "n_price_identity_violations": price_identity_violations,
        "n_sub_tick_prices": sub_tick_prices,
        "n_nonpositive_size": nonpositive_size,
        "n_fractional_size": fractional_size,
        "frac_fractional_size": round(fractional_size / len(rows), 4) if rows else None,
        "n_trade_day_mismatch": day_mismatch,
        "n_captured_before_created": captured_before_created,
        "n_hours_covered": len(hours),
        "hour_histogram": dict(sorted(hours.items())),
        "distinct_schema_versions": sorted({str(r.get("schema_version")) for r in rows}),
        "distinct_price_source_tags": sorted({str(r.get("price_source_tag")) for r in rows}),
        "distinct_capture_ids": sorted({str(r.get("capture_id")) for r in rows}),
        "n_distinct_tickers": len({r.get("ticker") for r in rows}),
        # the two easily-misread fields
        "n_event_ticker_null": sum(1 for r in rows if r.get("event_ticker") is None),
        "event_ticker_is_structurally_null": all(r.get("event_ticker") is None for r in rows),
        "n_distinct_raw_sha256": len(shas),
        "max_raw_sha256_multiplicity": max(shas.values()) if shas else 0,
        "raw_sha256_is_per_line_hash": len(shas) == len(rows),
        "side_triples": {
            "|".join(str(x) for x in k): v for k, v in sorted(
                collections.Counter(
                    (r.get("taker_book_side"), r.get("taker_outcome_side"), r.get("taker_side"))
                    for r in rows).items(), key=lambda kv: -kv[1])
        },
        "size_percentiles": _percentiles(sizes),
        "day": day,
    }


def _percentiles(sorted_vals: Sequence[float]) -> Dict[str, Optional[float]]:
    if not sorted_vals:
        return {k: None for k in ("p01", "p10", "p50", "p90", "p99", "max")}
    n = len(sorted_vals)

    def at(p: float) -> float:
        return round(float(sorted_vals[min(n - 1, int(p * n))]), 4)

    return {"p01": at(0.01), "p10": at(0.10), "p50": at(0.50), "p90": at(0.90),
            "p99": at(0.99), "max": round(float(sorted_vals[-1]), 4)}


# --------------------------------------------------------------------------- #
# 2. print-side join profile (the DUAL of milestone 1's interval coverage)
# --------------------------------------------------------------------------- #
def print_join_profile(prints: Dict[str, List[dict]],
                       snaps: Dict[str, List[dict]]) -> Dict[str, Any]:
    """Of the prints we hold, how many can be priced against a bracketing book interval?

    A print is `inside` iff its ticker has >=2 snapshots and its event time lies within
    [first_snapshot, last_snapshot]. `after_last` is the failure mode that matters: the book
    collector stopped covering a ticker while it was still trading, so every later print is
    evidence about a market we can no longer quote. Prints are never silently dropped — the
    four buckets partition the tape exactly."""
    inside = before_first = after_last = no_book = 0
    fresh = {r: 0 for r in FRESHNESS_RUNGS}
    ages: List[float] = []
    n_prints = 0
    per_ticker: Dict[str, Dict[str, int]] = {}
    for tk, pl in prints.items():
        v = [s["ts"] for s in (snaps.get(tk) or [])]
        v.sort()
        stats = {"n_prints": len(pl), "n_snapshots": len(v), "inside": 0, "after_last": 0}
        for pr in pl:
            n_prints += 1
            t = pr["ts"]
            if len(v) < 2:
                no_book += 1
                continue
            if t < v[0]:
                before_first += 1
                continue
            if t > v[-1]:
                after_last += 1
                stats["after_last"] += 1
                continue
            inside += 1
            stats["inside"] += 1
            age = (t - v[bisect.bisect_right(v, t) - 1]) / 60.0
            ages.append(age)
            for rung in FRESHNESS_RUNGS:
                if age <= rung:
                    fresh[rung] += 1
        per_ticker[tk] = stats

    def frac(k: int) -> Optional[float]:
        return round(k / n_prints, 4) if n_prints else None

    return {
        "n_prints": n_prints,
        "n_inside_book_span": inside,
        "n_before_first_snapshot": before_first,
        "n_after_last_snapshot": after_last,
        "n_ticker_has_under_two_snapshots": no_book,
        "frac_inside_book_span": frac(inside),
        "frac_after_last_snapshot": frac(after_last),
        "buckets_partition_the_tape":
            inside + before_first + after_last + no_book == n_prints,
        "freshness_ladder": {f"within_{int(r)}min": {"n": fresh[r], "frac": frac(fresh[r])}
                             for r in FRESHNESS_RUNGS},
        "median_reference_quote_age_min":
            round(statistics.median(ages), 1) if ages else None,
        "worst_dropout_tickers": sorted(
            ({"ticker": t, **s} for t, s in per_ticker.items() if s["after_last"]),
            key=lambda d: -d["after_last"])[:10],
    }


# --------------------------------------------------------------------------- #
# 3. book pass cadence (the defect is BOOK-side, not trade-side)
# --------------------------------------------------------------------------- #
def book_pass_profile(days: Sequence[str]) -> Dict[str, Any]:
    """Capture-pass times of `orderbook_depth` over `days`, from the tape's own
    `captured_at` values, plus the largest hole between consecutive passes."""
    times: set = set()
    for d in days:
        p = DEPTH_TAPE / f"dt={d}.jsonl"
        if not p.exists():
            continue
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = parse_ts(rec.get("captured_at"))
                if ts is not None:
                    times.add(round(ts / 60.0) * 60.0)  # pass granularity, not per-ticker jitter
    ts_sorted = sorted(times)
    gaps = [(b - a) / 60.0 for a, b in zip(ts_sorted, ts_sorted[1:])]
    return {
        "days": list(days),
        "n_passes": len(ts_sorted),
        "first_pass": _iso(ts_sorted[0]) if ts_sorted else None,
        "last_pass": _iso(ts_sorted[-1]) if ts_sorted else None,
        "median_gap_min": round(statistics.median(gaps), 1) if gaps else None,
        "max_gap_min": round(max(gaps), 1) if gaps else None,
        "max_gap_starts_at": _iso(ts_sorted[gaps.index(max(gaps))]) if gaps else None,
        "pass_times": [_iso(t) for t in ts_sorted],
    }


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# --------------------------------------------------------------------------- #
# 4. fill capacity — how much size did the qualifying prints actually supply?
# --------------------------------------------------------------------------- #
def qualifying_size(prints: Sequence[dict], t0: float, t1: float, price: float,
                    side: str) -> Tuple[float, Optional[float]]:
    """(total, first) qualifying print size in (t0, t1] for a resting order at `price`.

    Orientation is imported wholesale from `q51_maker_fillsim` (L279): a resting YES bid is
    hit by a SELLING taker (`taker_book_side == TAKER_SELLS`); a resting NO bid is lifted by
    a BUYING taker (`TAKER_BUYS`). This function NEVER invents a fill — it only sums the
    sizes of prints that the already-tested predicate would have accepted."""
    total = 0.0
    first: Optional[float] = None
    for pr in prints:
        if pr["ts"] <= t0 or pr["ts"] > t1:
            continue
        if side == "yes_bid":
            ok = pr.get("taker_book_side") == TAKER_SELLS and pr["yes_price"] <= price + 1e-9
        elif side == "no_bid":
            ok = pr.get("taker_book_side") == TAKER_BUYS and pr["yes_price"] >= (1.0 - price) - 1e-9
        else:
            ok = False
        if not ok:
            continue
        c = pr.get("count")
        c = float(c) if isinstance(c, (int, float)) else 0.0
        if first is None:
            first = c
        total += c
    return total, first


def fill_capacity(prints: Dict[str, List[dict]], rows_path: Path = ROWS_PATH,
                  sizes: Sequence[float] = CAPACITY_SIZES) -> Optional[Dict[str, Any]]:
    """Capacity curve over the ALREADY-COMMITTED milestone-2 rows. Returns None if those
    rows are absent — this audit never re-runs the fill-sim and never re-derives a P&L."""
    if not rows_path.exists():
        return None
    rows = []
    with open(rows_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    filled = [r for r in rows if r.get("filled")]
    firsts: List[float] = []
    totals: List[float] = []
    untraceable = 0
    for r in filled:
        t0 = parse_ts(r.get("entry_captured_at"))
        t1 = parse_ts(r.get("next_captured_at"))
        pl = prints.get(r.get("ticker")) or []
        if t0 is None or t1 is None or not pl:
            untraceable += 1
            continue
        tot, first = qualifying_size(pl, t0, t1, float(r["rest_price"]), str(r.get("side")))
        if first is None:
            untraceable += 1
            continue
        firsts.append(first)
        totals.append(tot)
    n = len(firsts)
    try:
        rel = str(rows_path.relative_to(REPO_ROOT))
    except ValueError:      # a caller-supplied path outside the repo (tests, ad-hoc reruns)
        rel = str(rows_path)
    return {
        "rows_path": rel,
        "n_legs": len(rows),
        "n_filled_legs": len(filled),
        "n_traced": n,
        "n_untraceable": untraceable,
        "first_print_size_percentiles": _percentiles(sorted(firsts)),
        "interval_total_size_percentiles": _percentiles(sorted(totals)),
        "capacity_curve": {
            str(q): {
                "frac_fillable_on_first_print":
                    round(sum(1 for x in firsts if x >= q) / n, 4) if n else None,
                "frac_fillable_on_interval_total":
                    round(sum(1 for x in totals if x >= q) / n, 4) if n else None,
            } for q in sizes
        },
    }


# --------------------------------------------------------------------------- #
# 5. the derived bootstrap unit vs the venue's own event key
# --------------------------------------------------------------------------- #
def event_key_check(cache_path: Path = CACHE_PATH) -> Dict[str, Any]:
    """`game_of(ticker)` is the block-bootstrap unit (L6) and is DERIVED from the ticker
    string, because the print tape carries no event field. Check it against the venue's own
    `event_ticker` — a derived unit that disagrees would invalidate the resampling."""
    if not cache_path.exists():
        return {"checked": 0, "mismatches": [], "cache_present": False}
    markets = (json.load(open(cache_path, encoding="utf-8")) or {}).get("markets") or {}
    mismatches = []
    checked = 0
    for tk, rec in sorted(markets.items()):
        et = (rec or {}).get("event_ticker")
        if not et:
            continue
        checked += 1
        if game_of(tk) != et:
            mismatches.append({"ticker": tk, "venue_event_ticker": et, "derived": game_of(tk)})
    return {"cache_present": True, "checked": checked, "n_mismatches": len(mismatches),
            "mismatches": mismatches[:10]}


# --------------------------------------------------------------------------- #
# 6. when does milestone 3's time gate actually open?
# --------------------------------------------------------------------------- #
def settlement_gate(cache_path: Path = CACHE_PATH) -> Dict[str, Any]:
    """Offline gate arithmetic from the committed settlement cache: how many of the sampled
    markets are still unsettled, and on what date does each become resolvable? The answer is
    a DATE for a future run to fire on, not a claim about any edge."""
    if not cache_path.exists():
        return {"cache_present": False}
    payload = json.load(open(cache_path, encoding="utf-8")) or {}
    markets = payload.get("markets") or {}
    unsettled_close_days = collections.Counter()
    n_settled = 0
    for _tk, rec in markets.items():
        rec = rec or {}
        if rec.get("result"):
            n_settled += 1
            continue
        ct = rec.get("close_time") or ""
        unsettled_close_days[ct[:10] or "unknown"] += 1
    days = sorted(unsettled_close_days)
    cum = 0
    schedule = []
    for d in days:
        cum += unsettled_close_days[d]
        schedule.append({"close_day": d, "n_closing": unsettled_close_days[d],
                         "cumulative_resolvable": n_settled + cum})
    return {
        "cache_present": True,
        "pulled_at": payload.get("pulled_at"),
        "n_markets": len(markets),
        "n_already_settled": n_settled,
        "n_unsettled": len(markets) - n_settled,
        "last_close_day": days[-1] if days else None,
        "resolution_schedule": schedule,
    }


# --------------------------------------------------------------------------- #
def build_report(day: str = DAY) -> Dict[str, Any]:
    raw = load_raw_prints(day)
    prints = load_prints(day)
    same_day = load_depth(day)[1]
    multi = load_depth_multi(adjacent_days(day))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "day": day,
        "offline": True,
        "integrity": tape_integrity(raw, day=day),
        "join": {
            "same_day_books": print_join_profile(prints, same_day),
            "adjacent_days_books": print_join_profile(prints, multi),
        },
        "book_passes": book_pass_profile(adjacent_days(day)),
        "capacity": fill_capacity(prints),
        "event_key": event_key_check(),
        "settlement_gate": settlement_gate(),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q51 trade-tape data-quality deep-dive")
    ap.add_argument("--day", default=DAY)
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    rep = build_report(args.day)
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)

    i, j, b = rep["integrity"], rep["join"], rep["book_passes"]
    print(f"[q51:quality] day={rep['day']}  lines={i['n_lines']}  tickers={i['n_distinct_tickers']}  "
          f"dup_ids={i['n_duplicate_trade_ids']}  price_identity_violations="
          f"{i['n_price_identity_violations']}  hours={i['n_hours_covered']}/24  "
          f"fractional_size={i['frac_fractional_size']}")
    for name in ("same_day_books", "adjacent_days_books"):
        p = j[name]
        print(f"[q51:quality] {name:>19}: inside_book_span={p['frac_inside_book_span']}  "
              f"after_last_snapshot={p['frac_after_last_snapshot']}  "
              f"fresh<=15min={p['freshness_ladder']['within_15min']['frac']}  "
              f"median_quote_age={p['median_reference_quote_age_min']}min")
    print(f"[q51:quality] book passes={b['n_passes']} median_gap={b['median_gap_min']}min "
          f"max_gap={b['max_gap_min']}min at {b['max_gap_starts_at']}")
    if rep["capacity"]:
        c = rep["capacity"]
        print(f"[q51:quality] capacity: traced {c['n_traced']}/{c['n_filled_legs']} fills; "
              + "  ".join(f"q={q}:{v['frac_fillable_on_interval_total']}"
                          for q, v in c["capacity_curve"].items()))
    e, g = rep["event_key"], rep["settlement_gate"]
    print(f"[q51:quality] event_key: {e.get('checked')} checked, {e.get('n_mismatches')} mismatches")
    if g.get("cache_present"):
        print(f"[q51:quality] gate: {g['n_unsettled']}/{g['n_markets']} unsettled, "
              f"last close day {g['last_close_day']}")
    print(f"[q51:quality] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

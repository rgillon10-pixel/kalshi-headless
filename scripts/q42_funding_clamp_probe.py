#!/usr/bin/env python3
"""q42_funding_clamp_probe.py — Q42 part (1): characterize the Kalshi crypto-perp
funding-rate "exactly-zero" anomaly over already-committed tape (READ-ONLY, OFFLINE).

LOOP-QUEUE.md Q42. The 2026-07-16 perps recon (collection/perp_tape.py docstring) claims
finalized funding prints are EXACTLY 0 in 62-99% of 8h windows per contract — a dead
band/clamp, since Hyperliquid's same-window BTC funding is never 0. This probe is the
DISCOVERY/CHARACTERIZATION half of Q42: it reproduces (or corrects) that claim off the
committed `tape/perp_tape/dt=*.jsonl` funding_rates records and, crucially, distinguishes a
genuine DEAD-BAND/CLAMP from a symmetric-ROUNDING/quantization artifact.

This is NOT a P&L strategy verdict: no block-bootstrap CI, no fee math, no registry change.
Every funding number is `broker_truth` (finalized venue prints) and is reported with that tag.

The day file holds THREE funding_rates records: one `mode=="backfill"` (1447 prints, full
since-launch history 2026-06-03->) and two `mode=="recent"` (39 prints each, trailing 24h).
The backfill record is the primary population by default (largest, most complete). Prints are
deduped on (market_ticker, funding_time) at analysis time (collector persists them un-deduped).

THE CRUX — clamp vs rounding discriminator (per contract + pooled):
  * Compute the smallest nonzero |funding_rate| magnitude (`min_abs_nonzero`) and an inferred
    quantization tick (the smallest gap between sorted distinct |rate| values — the data's own
    granularity; the nonzero rates are NOT pre-rounded so this is tiny).
  * ticks_from_zero = min_abs_nonzero / inferred_tick.
      - ticks_from_zero >= CLAMP_TICK_RATIO_HIGH  -> GENUINE DEAD-BAND/CLAMP: nonzeros start
        many granularity-steps away from 0, i.e. there is a clear GAP over (0, min_abs_nonzero),
        so sub-band rates are forced to exactly 0.
      - ticks_from_zero <= CLAMP_TICK_RATIO_LOW   -> ROUNDING/QUANTIZATION ARTIFACT: the
        smallest nonzero is ~one tick from 0, so the zeros are just the rounding bucket
        straddling zero, not a structural clamp.
      - in between -> AMBIGUOUS (report the numbers, claim nothing).
  * A contract with too few nonzero prints (e.g. LINK ~1 nonzero) cannot have its distribution
    characterized -> honest DATA-ADEQUACY note, never a fabricated verdict.

Read-only. NO network. Run:
    python3 scripts/q42_funding_clamp_probe.py
    python3 scripts/q42_funding_clamp_probe.py --json-out /tmp/q42.json
"""
from __future__ import annotations

import argparse
import glob
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.stats import safe_pstdev  # noqa: E402  (Hard Rule #2 — no bare pstdev)

# Default primary population: the full since-launch backfill funding history.
DEFAULT_TAPE_GLOB = "tape/perp_tape/dt=*.jsonl"
PRICE_SOURCE_TAG = "broker_truth"

# clamp-vs-rounding discriminator thresholds (dimensionless: min_abs_nonzero / inferred_tick).
# A rounding bucket puts the smallest nonzero ~1 tick from 0; a dead-band pushes it many
# granularity-steps out (a genuine gap). The band between is left AMBIGUOUS on purpose.
CLAMP_TICK_RATIO_HIGH = 10.0
CLAMP_TICK_RATIO_LOW = 2.0

# fewest nonzero prints for which a distribution/clamp read is honestly computable.
MIN_NONZERO_FOR_VERDICT = 3


# --------------------------------------------------------------------------- #
# loading — injectable so tests are fully offline (path/glob OR a record list)
# --------------------------------------------------------------------------- #
def load_records(source: Any) -> List[Dict[str, Any]]:
    """Return a flat list of JSONL records from `source`, which may be:
      - a list/tuple of already-parsed record dicts (returned as-is), or
      - a str/Path pointing at a single .jsonl file or a glob matching many.
    Pure: no network, no mutation. A path that matches nothing yields []."""
    if isinstance(source, (list, tuple)):
        return list(source)
    pattern = str(source)
    paths = sorted(glob.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern]
    records: List[Dict[str, Any]] = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def collect_funding_prints(records: Sequence[Dict[str, Any]], mode: str = "backfill"
                           ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Flatten every `prints` entry out of funding_rates records matching `mode`.

    Returns (prints, meta) where meta records how many records/prints were read and the
    source tags seen (honest completeness accounting; a probe never silently drops a leg)."""
    fr_records = [r for r in records
                  if r.get("record_type") == "funding_rates" and r.get("mode") == mode]
    prints: List[Dict[str, Any]] = []
    tags: set = set()
    for rec in fr_records:
        tags.add(rec.get("price_source_tag"))
        for pr in rec.get("prints") or []:
            prints.append(pr)
    meta = {
        "mode": mode,
        "n_records_matched": len(fr_records),
        "n_prints_read": len(prints),
        "source_tags_seen": sorted(t for t in tags if t is not None),
    }
    return prints, meta


def dedup_prints(prints: Sequence[Dict[str, Any]]
                 ) -> Tuple[List[Dict[str, Any]], int]:
    """Dedup on (market_ticker, funding_time); keep first occurrence. Returns
    (deduped, n_dropped)."""
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for pr in prints:
        key = (pr.get("market_ticker"), pr.get("funding_time"))
        if key in seen:
            continue
        seen.add(key)
        out.append(pr)
    return out, len(prints) - len(out)


# --------------------------------------------------------------------------- #
# per-contract statistics
# --------------------------------------------------------------------------- #
def _rate_split(prints: Sequence[Dict[str, Any]]
                ) -> Tuple[List[float], List[float], int]:
    """Split prints' funding_rate into (zeros, nonzeros, n_none). None is EXCLUDED and
    counted separately — a missing rate is not a zero (never conflated)."""
    zeros: List[float] = []
    nonzeros: List[float] = []
    n_none = 0
    for pr in prints:
        r = pr.get("funding_rate")
        if r is None:
            n_none += 1
        elif r == 0.0:
            zeros.append(0.0)
        else:
            nonzeros.append(float(r))
    return zeros, nonzeros, n_none


def infer_tick(abs_values: Sequence[float]) -> Optional[float]:
    """Infer a quantization granularity as the smallest positive gap between sorted DISTINCT
    |values|. Returns None if fewer than 2 distinct values (a gap is undefined)."""
    distinct = sorted(set(abs_values))
    gaps = [b - a for a, b in zip(distinct, distinct[1:]) if b - a > 0]
    return min(gaps) if gaps else None


def nonzero_distribution(nonzeros: Sequence[float]) -> Dict[str, Any]:
    """min/max/mean/median/std of nonzero rates, plus |rate| min/max, pos/neg counts, and
    the inferred tick. n<2 leaves std None (no dispersion of a single point)."""
    if not nonzeros:
        return {"n": 0, "min": None, "max": None, "mean": None, "median": None,
                "std": None, "min_abs": None, "max_abs": None,
                "n_positive": 0, "n_negative": 0, "inferred_tick": None}
    absv = [abs(x) for x in nonzeros]
    return {
        "n": len(nonzeros),
        "min": min(nonzeros),
        "max": max(nonzeros),
        "mean": statistics.fmean(nonzeros),
        "median": statistics.median(nonzeros),
        # Hard Rule #2: population stdev only via safe_pstdev (n>=4 floor); a std over <4
        # nonzero points is noise, so leave it None below the floor rather than force it.
        "std": (safe_pstdev(nonzeros) if len(nonzeros) >= 4 else None),
        "min_abs": min(absv),
        "max_abs": max(absv),
        "n_positive": sum(1 for x in nonzeros if x > 0),
        "n_negative": sum(1 for x in nonzeros if x < 0),
        "inferred_tick": infer_tick(absv),
    }


def clamp_vs_rounding(dist: Dict[str, Any]) -> Dict[str, Any]:
    """Decide clamp vs rounding vs ambiguous vs data-adequacy from a nonzero distribution.

    Does NOT hardcode a conclusion: the computed ticks_from_zero (min_abs_nonzero / inferred
    tick) drives it. `gap_to_median` (min_abs_nonzero / median|rate|) is reported as a
    corroborating, unit-free measure of how far the smallest nonzero sits from the typical one."""
    n = dist["n"]
    min_abs = dist["min_abs"]
    tick = dist["inferred_tick"]
    # gap_to_median: how far the smallest nonzero sits from the TYPICAL nonzero magnitude
    # (a unit-free corroborating measure; near 1 means the distribution is bounded away from 0).
    gap_to_median = None
    if dist["median"] is not None and dist["median"] != 0.0 and min_abs is not None:
        gap_to_median = min_abs / abs(dist["median"])

    if n < MIN_NONZERO_FOR_VERDICT or tick is None:
        return {
            "verdict": "DATA-ADEQUACY: too few nonzero prints (%d < %d) to characterize the "
                       "distribution — no clamp/rounding claim" % (n, MIN_NONZERO_FOR_VERDICT),
            "verdict_code": "data_adequacy",
            "min_abs_nonzero": min_abs,
            "inferred_tick": tick,
            "ticks_from_zero": None,
            "gap_to_median": gap_to_median,
        }

    ticks_from_zero = min_abs / tick if tick > 0 else None
    if ticks_from_zero is not None and ticks_from_zero >= CLAMP_TICK_RATIO_HIGH:
        code = "clamp"
        verdict = ("GENUINE DEAD-BAND/CLAMP: smallest nonzero |rate|=%.3e sits %.1f "
                   "granularity-ticks above 0 (tick=%.3e) — a clear gap over (0, min_abs_nonzero); "
                   "sub-band rates forced to exactly 0" % (min_abs, ticks_from_zero, tick))
    elif ticks_from_zero is not None and ticks_from_zero <= CLAMP_TICK_RATIO_LOW:
        code = "rounding"
        verdict = ("ROUNDING/QUANTIZATION ARTIFACT: smallest nonzero |rate|=%.3e is only %.2f "
                   "tick(s) from 0 (tick=%.3e) — zeros are the rounding bucket straddling zero, "
                   "not a structural clamp" % (min_abs, ticks_from_zero, tick))
    else:
        code = "ambiguous"
        verdict = ("AMBIGUOUS: smallest nonzero |rate|=%.3e is %.2f ticks from 0 (tick=%.3e) — "
                   "between the rounding (<=%.1f) and clamp (>=%.1f) thresholds; no claim"
                   % (min_abs, ticks_from_zero, tick, CLAMP_TICK_RATIO_LOW, CLAMP_TICK_RATIO_HIGH))
    return {
        "verdict": verdict,
        "verdict_code": code,
        "min_abs_nonzero": min_abs,
        "inferred_tick": tick,
        "ticks_from_zero": ticks_from_zero,
        "gap_to_median": gap_to_median,
    }


def _hour_of_day(funding_time: str) -> Optional[int]:
    """UTC hour-of-day from an ISO8601 funding_time like '2026-06-03T20:00:00Z'. None on a
    grammar mismatch (never guessed)."""
    if not funding_time or len(funding_time) < 13 or funding_time[10] != "T":
        return None
    try:
        h = int(funding_time[11:13])
    except ValueError:
        return None
    return h if 0 <= h <= 23 else None


def hour_of_day_zero_fraction(prints: Sequence[Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    """Per UTC hour-of-day slot: total prints, zero count, zero fraction. Reveals whether
    zeros concentrate in particular 8h funding slots or spread evenly."""
    buckets: Dict[int, Dict[str, int]] = {}
    for pr in prints:
        h = _hour_of_day(pr.get("funding_time", ""))
        if h is None:
            continue
        r = pr.get("funding_rate")
        if r is None:
            continue
        b = buckets.setdefault(h, {"n": 0, "zeros": 0})
        b["n"] += 1
        if r == 0.0:
            b["zeros"] += 1
    return {h: {"n": b["n"], "zeros": b["zeros"],
                "zero_fraction": (b["zeros"] / b["n"]) if b["n"] else None}
            for h, b in sorted(buckets.items())}


def contract_stats(prints: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Full per-contract stat block for one ticker's deduped prints."""
    zeros, nonzeros, n_none = _rate_split(prints)
    n_total = len(zeros) + len(nonzeros)  # None excluded from the denominator
    dist = nonzero_distribution(nonzeros)
    return {
        "n_prints_total": n_total,
        "n_none_excluded": n_none,
        "n_zero": len(zeros),
        "zero_fraction": (len(zeros) / n_total) if n_total else None,
        "nonzero_distribution": dist,
        "clamp_vs_rounding": clamp_vs_rounding(dist),
        "hour_of_day": hour_of_day_zero_fraction(prints),
        "price_source_tag": PRICE_SOURCE_TAG,
    }


def analyze(records: Sequence[Dict[str, Any]], mode: str = "backfill") -> Dict[str, Any]:
    """End-to-end: collect -> dedup -> per-contract + pooled stats. Returns a JSON-able report."""
    raw_prints, load_meta = collect_funding_prints(records, mode=mode)
    deduped, n_dropped = dedup_prints(raw_prints)

    by_ticker: Dict[str, List[Dict[str, Any]]] = {}
    for pr in deduped:
        by_ticker.setdefault(pr.get("market_ticker", ""), []).append(pr)

    per_contract = {t: contract_stats(ps) for t, ps in sorted(by_ticker.items())}
    pooled = contract_stats(deduped)

    return {
        "price_source_tag": PRICE_SOURCE_TAG,
        "mode": mode,
        "load": {
            **load_meta,
            "n_prints_after_dedup": len(deduped),
            "n_dedup_dropped": n_dropped,
        },
        "n_contracts": len(per_contract),
        "per_contract": per_contract,
        "pooled": pooled,
    }


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _f(v: Optional[float], nd: int = 6) -> str:
    return "None" if v is None else f"{v:.{nd}f}"


def _print_report(rep: Dict[str, Any]) -> None:
    ld = rep["load"]
    print("=" * 100)
    print("Q42 (1) — KALSHI CRYPTO-PERP FUNDING 'EXACTLY-ZERO' ANOMALY (read-only, offline)")
    print("=" * 100)
    print(f"source_tag={rep['price_source_tag']}  mode={rep['mode']}  "
          f"records_matched={ld['n_records_matched']}  prints_read={ld['n_prints_read']}  "
          f"after_dedup={ld['n_prints_after_dedup']}  dedup_dropped={ld['n_dedup_dropped']}  "
          f"tags_seen={ld['source_tags_seen']}")
    print("-" * 100)
    hdr = (f"{'contract':<14}{'n':>5}{'zero':>6}{'zero_frac':>10}{'nz':>5}"
           f"{'min_abs_nz':>14}{'inf_tick':>13}{'ticks/0':>10}  verdict")
    print(hdr)
    for t, cs in rep["per_contract"].items():
        d = cs["nonzero_distribution"]
        cvr = cs["clamp_vs_rounding"]
        tfz = cvr["ticks_from_zero"]
        print(f"{t:<14}{cs['n_prints_total']:>5}{cs['n_zero']:>6}"
              f"{_f(cs['zero_fraction'], 4):>10}{d['n']:>5}"
              f"{_f(d['min_abs'], 8):>14}{_f(cvr['inferred_tick'], 9):>13}"
              f"{('None' if tfz is None else f'{tfz:.1f}'):>10}  {cvr['verdict_code']}")
    print("-" * 100)
    pc = rep["pooled"]
    pd = pc["nonzero_distribution"]
    pcvr = pc["clamp_vs_rounding"]
    tfz = pcvr["ticks_from_zero"]
    gtm = pcvr["gap_to_median"]
    tfz_s = "None" if tfz is None else f"{tfz:.1f}"
    gtm_s = "None" if gtm is None else f"{gtm:.3f}"
    print(f"POOLED  n={pc['n_prints_total']}  zeros={pc['n_zero']}  "
          f"zero_fraction={_f(pc['zero_fraction'], 4)}  nonzero={pd['n']}  "
          f"pos={pd['n_positive']} neg={pd['n_negative']}  none_excluded={pc['n_none_excluded']}")
    print(f"POOLED  min_abs_nonzero={_f(pd['min_abs'], 8)}  inferred_tick={_f(pcvr['inferred_tick'], 9)}"
          f"  ticks_from_zero={tfz_s}  gap_to_median={gtm_s}")
    print(f"POOLED VERDICT: {pcvr['verdict']}")
    print("-" * 100)
    print("Pooled zero-fraction by UTC hour-of-day slot (8h funding windows):")
    for h, b in pc["hour_of_day"].items():
        print(f"  {h:02d}:00Z  n={b['n']:>5}  zeros={b['zeros']:>5}  "
              f"zero_fraction={_f(b['zero_fraction'], 4)}")
    print("=" * 100)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q42 (1) — characterize the Kalshi perp funding exactly-zero anomaly (offline)")
    ap.add_argument("--tape", default=DEFAULT_TAPE_GLOB,
                    help="tape path or glob (default: %(default)s)")
    ap.add_argument("--mode", default="backfill", choices=["backfill", "recent"],
                    help="which funding_rates record mode to characterize (default: backfill)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    records = load_records(args.tape)
    rep = analyze(records, mode=args.mode)
    _print_report(rep)

    if args.json_out:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "price_source_tag": PRICE_SOURCE_TAG,
            "tape": args.tape,
            "clamp_tick_ratio_high": CLAMP_TICK_RATIO_HIGH,
            "clamp_tick_ratio_low": CLAMP_TICK_RATIO_LOW,
            "min_nonzero_for_verdict": MIN_NONZERO_FOR_VERDICT,
            "report": rep,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"[q42] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

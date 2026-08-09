#!/usr/bin/env python3
"""Data-quality deep-dive on `tape/hyperliquid_funding/` (the Q42 cross-venue join's
off-venue leg). READ-ONLY and FULLY OFFLINE — opens committed tape and nothing else: no
network, no credentials, no writes outside `reports/`, no tape mutation.

Idle-run policy (c) (LOOP-QUEUE.md protocol v3), 2026-08-09. This is a DATA-QUALITY /
coverage / join-ability characterization, NOT a verdict: no P&L, no fee model, no
bootstrap CI, no registry change. Every funding number on both legs is `broker_truth`
(venue-computed finalized prints, never a fill).

Why a second pass. `findings/2026-07-26-hyperliquid-funding-tape-audit.md` audited this
family's SHAPE (schema, key-sets, null-freeness, append-only history, day-file-vs-print
coverage, source tags) and found one 2-row duplicate. It never audited the family's
VALUES, and it predates 13 days of new tape (`dt=2026-07-27` … `dt=2026-08-08`). The
headline here is a value-distribution fact the shape audit could not have seen.

Five measurements, each falsifiable from committed bytes:

1. `hour_coverage` — the only honest coverage metric for this family (L-note carried by
   `scripts/tape_gap_monitor.py::RETROSPECTIVE_LIST_FAMILIES`): the union of embedded
   `prints[].time_ms` on a 1h grid, NOT `dt=` day-file presence. Reports span, missing
   hour runs, duplicated hours and their runs.
2. `duplicate_lines` — byte-identical repeated JSONL lines (a duplicate APPEND of one
   capture, distinct from the `(coin, time_ms)` overlap of two different captures). This
   family's only occurrence is ALREADY-KNOWN history, not a new finding: capture
   `20260728T070413Z` (BTC+ETH, 2 lines) is 2 of the 1,358 lines L285 censused across six
   families on `dt=2026-07-28`. It is measured here so the two duplicate CLASSES can be
   told apart — subtracting it leaves the 70 duplicate hours/coin that (3) explains.
3. `start_ms_regressions` — the in-tape diagnosis of WHY duplicate prints appear. Every
   `mode=incremental` record persists the `start_ms` it computed from
   `collection/hyperliquid_funding.py::_committed_time_ms` (a LOCAL-working-tree read).
   A record whose `start_ms` sits BEHIND the newest print an earlier-captured record
   already archived proves that pass could not see its predecessor's write, and re-emits
   the overlap. The 07-26 audit needed `git log -S` archaeology to reach this; the
   persisted field makes it a pure-tape check.
4. `baseline_pin_profile` — what fraction of Hyperliquid hourly prints sit at EXACTLY the
   venue's interest-rate baseline (0.01% per 8h = 1.25e-05 per hour), and in how many
   autocorrelated runs. A pinned hour is a constant, not an observation.
5. `degenerate_window_profile` — the join-ability payload. Re-runs Q42's own 8h window
   join (imported from `scripts/q42_crossvenue_funding_join.py`, never re-implemented)
   and counts the windows where BOTH legs are at their venue's constant: Kalshi's ±1bp
   dead-band clamp at exactly 0.0 AND all 8 Hyperliquid hours at exactly the baseline.
   Those windows carry a differential with zero variance — nominal n, no information.

Run:
    python3 scripts/hl_funding_tape_quality.py
    python3 scripts/hl_funding_tape_quality.py --json-out reports/hl_funding_tape_quality.json
"""
from __future__ import annotations

import argparse
import collections
import glob as globmod
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import q42_crossvenue_funding_join as Q42  # noqa: E402  (sibling script; path set above)

from core.timeutil import parse_iso_utc  # noqa: E402  (L136/L150: never raw fromisoformat)

REPO_ROOT = Path(__file__).resolve().parents[1]
HL_GLOB = str(REPO_ROOT / "tape" / "hyperliquid_funding" / "dt=*.jsonl")
PERP_GLOB = str(REPO_ROOT / "tape" / "perp_tape" / "dt=*.jsonl")

PRICE_SOURCE_TAG = "broker_truth"
HOUR_MS = 3600_000

# Hyperliquid's interest-rate baseline: 0.01% per 8h => 0.00125% = 1.25e-05 per HOUR.
# A print equal to this to the last bit is the venue's constant, not a market observation.
HL_BASELINE_HOURLY_RATE = 1.25e-05

# Kalshi's finalized perp funding is clamped to exactly 0.0 inside its +/-1bp dead band
# (Q42 part 1, `findings/2026-07-17-q42-funding-clamp-characterization.md`).
KALSHI_CLAMP_VALUE = 0.0


# --------------------------------------------------------------------------- #
# loading (injectable: a glob string, a path, or an already-parsed record list)
# --------------------------------------------------------------------------- #
def load_lines(source: Any) -> List[Tuple[str, str]]:
    """Return [(path, raw_line)] for every non-blank line under `source`.

    `source` may be a list/tuple of `(path, line)` pairs (returned as-is, for tests) or a
    str/Path file/glob. Pure: no network, no mutation."""
    if isinstance(source, (list, tuple)):
        return [(str(p), str(l)) for p, l in source]
    pattern = str(source)
    paths = sorted(globmod.glob(pattern)) if any(c in pattern for c in "*?[") else [pattern]
    out: List[Tuple[str, str]] = []
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.strip():
                    out.append((p, line))
    return out


def parse_records(lines: Sequence[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Parse `(path, line)` pairs into records; a malformed line is skipped, never fatal."""
    recs: List[Dict[str, Any]] = []
    for path, line in lines:
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            continue
        if isinstance(rec, dict):
            rec = dict(rec)
            rec["_path"] = path
            recs.append(rec)
    return recs


def _hour_index(ms: Any) -> Optional[int]:
    """Nearest whole-hour index (HL stamps a few ms past :00). Same rule Q42 joins on."""
    if not isinstance(ms, (int, float)):
        return None
    return int(round(ms / HOUR_MS))


def _iso_hour(hour_index: int) -> str:
    return datetime.fromtimestamp(hour_index * HOUR_MS / 1000, timezone.utc).strftime(
        "%Y-%m-%dT%H:%MZ")


def flatten_prints(records: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """{coin -> [print rows]} across every `funding_history` record, NOT deduped (the
    duplicate structure is the thing being measured). Each row keeps its writing record's
    `capture_id`/`captured_at`/`mode` so a duplicate can be attributed."""
    out: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for rec in records:
        if rec.get("record_type") != "funding_history":
            continue
        coin = rec.get("coin")
        if not coin:
            continue
        for pr in rec.get("prints") or []:
            hi = _hour_index(pr.get("time_ms"))
            if hi is None:
                continue
            out[coin].append({
                "hour_index": hi,
                "time_ms": pr.get("time_ms"),
                "funding_rate": pr.get("funding_rate"),
                "premium": pr.get("premium"),
                "capture_id": rec.get("capture_id"),
                "captured_at": rec.get("captured_at"),
                "mode": rec.get("mode"),
            })
    return dict(out)


# --------------------------------------------------------------------------- #
# 1. hour coverage (the only honest coverage metric for a retrospective-list family)
# --------------------------------------------------------------------------- #
def _runs(sorted_hours: Sequence[int]) -> List[Tuple[int, int]]:
    """Collapse a sorted hour-index list into [(start, end)] inclusive consecutive runs."""
    runs: List[List[int]] = []
    for h in sorted_hours:
        if runs and h == runs[-1][1] + 1:
            runs[-1][1] = h
        else:
            runs.append([h, h])
    return [(a, b) for a, b in runs]


def hour_coverage(prints_by_coin: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Per-coin 1h-grid coverage over the union of embedded print hours."""
    out: Dict[str, Any] = {}
    for coin, rows in sorted(prints_by_coin.items()):
        counts = collections.Counter(r["hour_index"] for r in rows)
        hours = sorted(counts)
        if not hours:
            out[coin] = {"n_rows": 0, "n_distinct_hours": 0}
            continue
        present = set(hours)
        missing = [h for h in range(hours[0], hours[-1] + 1) if h not in present]
        dup_hours = sorted(h for h, n in counts.items() if n > 1)
        out[coin] = {
            "n_rows": len(rows),
            "n_distinct_hours": len(hours),
            "span_start": _iso_hour(hours[0]),
            "span_end": _iso_hour(hours[-1]),
            "n_expected_hours": hours[-1] - hours[0] + 1,
            "n_missing_hours": len(missing),
            "missing_runs": [[_iso_hour(a), _iso_hour(b), b - a + 1] for a, b in _runs(missing)],
            "n_duplicate_hours": len(dup_hours),
            "duplicate_hour_fraction": len(dup_hours) / len(hours),
            "n_redundant_rows": len(rows) - len(hours),
            "max_multiplicity": max(counts.values()),
            "duplicate_runs": [[_iso_hour(a), _iso_hour(b), b - a + 1]
                               for a, b in _runs(dup_hours)],
            "price_source_tag": PRICE_SOURCE_TAG,
        }
    return out


def duplicate_value_conflicts(prints_by_coin: Dict[str, List[Dict[str, Any]]]
                              ) -> Dict[str, Any]:
    """Do duplicated hours ever disagree on `(funding_rate, premium)`? A conflict would make
    the duplicates a CORRECTNESS problem rather than a count-inflation one."""
    out: Dict[str, Any] = {}
    for coin, rows in sorted(prints_by_coin.items()):
        vals: Dict[int, set] = collections.defaultdict(set)
        for r in rows:
            vals[r["hour_index"]].add((r["funding_rate"], r["premium"]))
        conflicts = sorted(h for h, s in vals.items() if len(s) > 1)
        out[coin] = {"n_conflicting_hours": len(conflicts),
                     "conflicting_hours": [_iso_hour(h) for h in conflicts[:10]]}
    return out


# --------------------------------------------------------------------------- #
# 2. byte-identical duplicate lines
# --------------------------------------------------------------------------- #
def duplicate_lines(lines: Sequence[Tuple[str, str]]) -> Dict[str, Any]:
    """Byte-identical repeated JSONL lines — the same capture appended twice."""
    counts = collections.Counter(line for _, line in lines)
    groups = []
    for line, n in counts.items():
        if n < 2:
            continue
        try:
            rec = json.loads(line)
        except (ValueError, TypeError):
            rec = {}
        groups.append({
            "capture_id": rec.get("capture_id"),
            "coin": rec.get("coin"),
            "mode": rec.get("mode"),
            "n_prints": rec.get("n_prints"),
            "n_copies": n,
            "paths": sorted({p for p, l in lines if l == line}),
        })
    groups.sort(key=lambda g: (str(g["capture_id"]), str(g["coin"])))
    return {
        "n_lines": len(lines),
        "n_duplicate_line_groups": len(groups),
        "n_extra_lines": sum(g["n_copies"] - 1 for g in groups),
        "groups": groups,
    }


# --------------------------------------------------------------------------- #
# 3. start_ms regressions — the in-tape mechanism for duplicate prints
# --------------------------------------------------------------------------- #
def start_ms_regressions(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Per coin, walk `mode=incremental` records in capture order and flag any whose
    persisted `start_ms` sits BEHIND the newest `time_ms` an earlier record already
    archived — proof that pass read a working tree missing its predecessor's write.

    Ties are not regressions: `start_ms == running_max` is the collector working exactly as
    designed (fetch from the last archived print inclusive)."""
    per_coin: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for rec in records:
        if rec.get("record_type") != "funding_history" or rec.get("mode") != "incremental":
            continue
        prints = rec.get("prints") or []
        times = [p.get("time_ms") for p in prints if isinstance(p.get("time_ms"), (int, float))]
        if not times or not rec.get("coin"):
            continue
        per_coin[rec["coin"]].append({
            "captured_at": rec.get("captured_at"),
            "capture_id": rec.get("capture_id"),
            "start_ms": rec.get("start_ms"),
            "min_ms": min(times),
            "max_ms": max(times),
            "n_prints": len(times),
        })
    out: Dict[str, Any] = {}
    for coin, rows in sorted(per_coin.items()):
        rows.sort(key=lambda r: (str(r["captured_at"]), str(r["capture_id"])))
        running_max: Optional[int] = None
        regressions = []
        for r in rows:
            sm = r["start_ms"]
            if (running_max is not None and isinstance(sm, (int, float))
                    and sm < running_max):
                regressions.append({
                    "captured_at": r["captured_at"],
                    "capture_id": r["capture_id"],
                    "start_hour": _iso_hour(_hour_index(sm)),
                    "already_archived_through": _iso_hour(_hour_index(running_max)),
                    "n_re_emitted_hours": max(
                        0, _hour_index(running_max) - _hour_index(sm)),
                })
            if running_max is None or r["max_ms"] > running_max:
                running_max = r["max_ms"]
        out[coin] = {
            "n_incremental_records": len(rows),
            "n_start_ms_regressions": len(regressions),
            "regression_fraction": (len(regressions) / len(rows)) if rows else None,
            "regressions": regressions,
        }
    return out


def capture_cadence(records: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Distribution of the gap between consecutive committed capture instants. Descriptive
    only — this family is single-WRITE-per-new-print, so a gap is upper-bounded by the host
    scheduler's own cadence, which is a GLOBAL ops property (L117), not a family defect."""
    stamps = sorted({r.get("captured_at") for r in records
                     if r.get("record_type") == "funding_history" and r.get("captured_at")})
    parsed = []
    for s in stamps:
        try:
            parsed.append(parse_iso_utc(str(s)))
        except (ValueError, TypeError):
            continue
    gaps = [(parsed[i + 1] - parsed[i]).total_seconds() / 3600.0
            for i in range(len(parsed) - 1)]
    return {
        "n_capture_instants": len(parsed),
        "first": parsed[0].isoformat() if parsed else None,
        "last": parsed[-1].isoformat() if parsed else None,
        "median_gap_hours": statistics.median(gaps) if gaps else None,
        "mean_gap_hours": statistics.fmean(gaps) if gaps else None,
        "max_gap_hours": max(gaps) if gaps else None,
    }


# --------------------------------------------------------------------------- #
# 4. baseline pin profile
# --------------------------------------------------------------------------- #
def baseline_pin_profile(prints_by_coin: Dict[str, List[Dict[str, Any]]],
                         baseline: float = HL_BASELINE_HOURLY_RATE) -> Dict[str, Any]:
    """Per coin: how many DISTINCT hours sit at exactly the venue baseline, and how those
    hours cluster into consecutive runs (a 269h run is one regime, not 269 observations)."""
    out: Dict[str, Any] = {}
    for coin, rows in sorted(prints_by_coin.items()):
        table: Dict[int, float] = {}
        for r in rows:
            rate = r.get("funding_rate")
            if rate is None or r["hour_index"] in table:
                continue
            table[r["hour_index"]] = float(rate)
        hours = sorted(table)
        if not hours:
            out[coin] = {"n_hours": 0}
            continue
        pinned = [h for h in hours if table[h] == baseline]
        runs = _runs(pinned)
        rates = [table[h] for h in hours]
        out[coin] = {
            "baseline": baseline,
            "n_hours": len(hours),
            "n_pinned_hours": len(pinned),
            "pinned_fraction": len(pinned) / len(hours),
            "n_pinned_runs": len(runs),
            "longest_pinned_run_hours": max((b - a + 1) for a, b in runs) if runs else 0,
            "median_pinned_run_hours": statistics.median([b - a + 1 for a, b in runs])
                                       if runs else None,
            "n_zero_rate_hours": sum(1 for r in rates if r == 0.0),
            "n_negative_rate_hours": sum(1 for r in rates if r < 0),
            "min_rate": min(rates),
            "max_rate": max(rates),
            "max_rate_equals_baseline": max(rates) == baseline,
            "n_distinct_rate_values": len(set(rates)),
            "price_source_tag": PRICE_SOURCE_TAG,
        }
    return out


# --------------------------------------------------------------------------- #
# 5. degenerate joined windows — the join-ability payload
# --------------------------------------------------------------------------- #
def degenerate_window_profile(kalshi_prints: Sequence[Dict[str, Any]],
                              hl_table: Dict[int, float],
                              baseline: float = HL_BASELINE_HOURLY_RATE,
                              clamp: float = KALSHI_CLAMP_VALUE) -> Dict[str, Any]:
    """Of the 8h windows Q42's join actually admits, how many have BOTH legs at a venue
    constant (Kalshi clamped to `clamp`, all 8 HL hours at `baseline`)?

    Window membership and the 8h compounding both come from `q42_crossvenue_funding_join`
    (`WINDOW_HOURS`, `_compound`) so this can never drift from the join it describes."""
    n = n_kalshi_clamped = n_all_pinned = n_both = 0
    degenerate_diffs: List[float] = []
    for kp in kalshi_prints:
        hT = kp.get("hour_index")
        krate = kp.get("funding_rate")
        if hT is None or krate is None:
            continue
        hours = [hT - i for i in range(Q42.WINDOW_HOURS - 1, -1, -1)]
        if not all(h in hl_table for h in hours):
            continue
        n += 1
        k_clamped = (float(krate) == clamp)
        all_pinned = all(hl_table[h] == baseline for h in hours)
        n_kalshi_clamped += k_clamped
        n_all_pinned += all_pinned
        if k_clamped and all_pinned:
            n_both += 1
            degenerate_diffs.append(Q42._compound([hl_table[h] for h in hours]) - float(krate))
    return {
        "n_windows_joined": n,
        "n_kalshi_clamped": n_kalshi_clamped,
        "kalshi_clamped_fraction": (n_kalshi_clamped / n) if n else None,
        "n_all8_hl_pinned": n_all_pinned,
        "all8_hl_pinned_fraction": (n_all_pinned / n) if n else None,
        "n_both_degenerate": n_both,
        "both_degenerate_fraction": (n_both / n) if n else None,
        "n_distinct_degenerate_differentials": len(set(degenerate_diffs)),
        "degenerate_differential": degenerate_diffs[0] if degenerate_diffs else None,
        "price_source_tag": PRICE_SOURCE_TAG,
    }


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def build_report(hl_source: Any = HL_GLOB, perp_source: Any = PERP_GLOB,
                 asset_map: Dict[str, Dict[str, str]] = Q42.ASSET_MAP) -> Dict[str, Any]:
    lines = load_lines(hl_source)
    records = parse_records(lines)
    prints_by_coin = flatten_prints(records)

    perp_records = Q42.load_records(perp_source)
    tickers = [v["kalshi_ticker"] for v in asset_map.values()]
    coins = [v["hl_coin"] for v in asset_map.values()]
    kalshi_all = Q42.collect_kalshi_prints(perp_records, tickers, mode=("backfill", "recent"))
    hl_tables = Q42.collect_hl_hourly(records, coins)

    degeneracy = {}
    for asset, spec in asset_map.items():
        kp = [p for p in kalshi_all if p["ticker"] == spec["kalshi_ticker"]]
        degeneracy[asset] = {
            "kalshi_ticker": spec["kalshi_ticker"], "hl_coin": spec["hl_coin"],
            **degenerate_window_profile(kp, hl_tables.get(spec["hl_coin"], {})),
        }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "price_source_tag": PRICE_SOURCE_TAG,
        "hl_source": str(hl_source) if not isinstance(hl_source, (list, tuple)) else "<inline>",
        "perp_source": str(perp_source) if not isinstance(perp_source, (list, tuple)) else "<inline>",
        "n_lines": len(lines),
        "n_records": len(records),
        "hour_coverage": hour_coverage(prints_by_coin),
        "duplicate_value_conflicts": duplicate_value_conflicts(prints_by_coin),
        "duplicate_lines": duplicate_lines(lines),
        "start_ms_regressions": start_ms_regressions(records),
        "capture_cadence": capture_cadence(records),
        "baseline_pin_profile": baseline_pin_profile(prints_by_coin),
        "degenerate_windows": degeneracy,
    }


def _print_report(rep: Dict[str, Any]) -> None:
    print("=" * 100)
    print("tape/hyperliquid_funding/ — DATA-QUALITY DEEP-DIVE (read-only, offline)")
    print("=" * 100)
    print(f"source_tag={rep['price_source_tag']}  lines={rep['n_lines']}  "
          f"records={rep['n_records']}")
    print("-" * 100)
    print("1. HOUR COVERAGE (union of embedded prints[].time_ms — NOT dt= file presence)")
    for coin, c in rep["hour_coverage"].items():
        print(f"  [{coin}] rows={c['n_rows']} distinct_hours={c['n_distinct_hours']} "
              f"span {c['span_start']} -> {c['span_end']}")
        print(f"        missing={c['n_missing_hours']}/{c['n_expected_hours']}  "
              f"duplicate_hours={c['n_duplicate_hours']} "
              f"({c['duplicate_hour_fraction']:.4f})  redundant_rows={c['n_redundant_rows']}"
              f"  max_multiplicity={c['max_multiplicity']}")
        for a, b, n in c["missing_runs"][:10]:
            print(f"        MISSING {a} -> {b} ({n}h)")
    for coin, v in rep["duplicate_value_conflicts"].items():
        print(f"  [{coin}] duplicated hours disagreeing on (rate, premium): "
              f"{v['n_conflicting_hours']}")
    print("-" * 100)
    d = rep["duplicate_lines"]
    print(f"2. BYTE-IDENTICAL DUPLICATE LINES: {d['n_duplicate_line_groups']} group(s), "
          f"{d['n_extra_lines']} extra line(s)")
    for g in d["groups"]:
        print(f"     {g['capture_id']} {g['coin']} {g['mode']} n_prints={g['n_prints']} "
              f"x{g['n_copies']}")
    print("-" * 100)
    print("3. start_ms REGRESSIONS (incremental pass could not see its predecessor's write)")
    for coin, r in rep["start_ms_regressions"].items():
        print(f"  [{coin}] {r['n_start_ms_regressions']}/{r['n_incremental_records']} records "
              f"({(r['regression_fraction'] or 0):.4f})")
        for g in r["regressions"][:5]:
            print(f"        {g['captured_at'][:19]} start={g['start_hour']} but tape already "
                  f"held {g['already_archived_through']} (+{g['n_re_emitted_hours']}h re-emitted)")
    cc = rep["capture_cadence"]
    print(f"     capture instants={cc['n_capture_instants']}  median gap="
          f"{(cc['median_gap_hours'] or 0):.2f}h  max gap={(cc['max_gap_hours'] or 0):.2f}h "
          f"(global scheduler property, not a family defect — L117)")
    print("-" * 100)
    print(f"4. HL BASELINE PIN (exactly {HL_BASELINE_HOURLY_RATE:g}/hr = 0.01% per 8h)")
    for coin, b in rep["baseline_pin_profile"].items():
        print(f"  [{coin}] pinned={b['n_pinned_hours']}/{b['n_hours']} "
              f"({b['pinned_fraction']:.4f}) in {b['n_pinned_runs']} runs  "
              f"longest={b['longest_pinned_run_hours']}h median_run={b['median_pinned_run_hours']}h")
        print(f"        zero_rate_hours={b['n_zero_rate_hours']}  neg={b['n_negative_rate_hours']}"
              f"  min={b['min_rate']:.4e} max={b['max_rate']:.4e} "
              f"max==baseline={b['max_rate_equals_baseline']}  distinct={b['n_distinct_rate_values']}")
    print("-" * 100)
    print("5. DEGENERATE JOINED WINDOWS (both legs at a venue constant)")
    for asset, g in rep["degenerate_windows"].items():
        print(f"  [{asset}] joined={g['n_windows_joined']}  kalshi_clamped="
              f"{g['n_kalshi_clamped']} ({(g['kalshi_clamped_fraction'] or 0):.4f})  "
              f"all8_HL_pinned={g['n_all8_hl_pinned']} "
              f"({(g['all8_hl_pinned_fraction'] or 0):.4f})")
        print(f"        BOTH degenerate = {g['n_both_degenerate']} "
              f"({(g['both_degenerate_fraction'] or 0):.4f}) — distinct differential values "
              f"across them: {g['n_distinct_degenerate_differentials']} "
              f"(value={g['degenerate_differential']})")
    print("=" * 100)
    print("Data-quality characterization only — NOT a verdict: no P&L, no fee model, no CI, "
          "no registry change. Both legs broker_truth (venue prints, never fills).")
    print("=" * 100)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="tape/hyperliquid_funding/ data-quality deep-dive (read-only, offline)")
    ap.add_argument("--hl-tape", default=HL_GLOB)
    ap.add_argument("--perp-tape", default=PERP_GLOB)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    rep = build_report(args.hl_tape, args.perp_tape)
    _print_report(rep)
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=2, default=str))
        print(f"[hl-funding-audit] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

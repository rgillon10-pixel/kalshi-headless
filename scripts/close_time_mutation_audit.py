#!/usr/bin/env python3
"""Read-only census: is a Kalshi market's `close_time` a fixed schedule, or is it rewritten?

The question, and why it is worth a run
---------------------------------------
`scripts/q51_m3_fill_projection.py` reads `close_time` out of a deliberately FROZEN
pre-settlement cache and documents that choice as safe on an explicit premise -- `close_time`
is *"a SCHEDULE field, never an outcome"* (`:51`, `:118-119`, and the emitted report field
`what_is_read_from_the_cache`). Four sports probes (`q26`, `q28`, `q29`, `q30`) additionally
use a cached `close_time` as the boundary that defines a "pre-close" snapshot
(`captured_at < close_time`) and, in `q26`/`q28`, as the origin of a time-to-close FEATURE
(`ttc_seconds` / `ttc_hours`).

Nothing in this repo had ever measured whether that premise holds. It is measurable, because
committed tape contains two independent substrates that answer it from opposite directions:

  A. `tape/q51_settlement_cache/` holds THREE pulls of the SAME 60-ticker population --
     `settlement-m2-2026-08-04.json` (pulled before most of them settled) and
     `settlement-m3-2026-08-10.json` / `settlement.json` (pulled after). A paired
     before/after observation of one population is exactly the experiment.
  B. `tape/universe_sweep/` re-observes LIVE open markets across ~26 committed days, so it
     measures whether close_time drifts WHILE a market is open -- the control that separates
     "this field is just noisy" from "this field is rewritten at settlement".

Regimes are classified by the SETTLEMENT STATE of the rows, never by the timestamps
themselves (`core.close_time_mutation`), because the trustworthiness of the timestamp is the
thing under test.

Discipline
----------
DESCRIPTIVE ONLY. No verdict, no CI, no bootstrap, no P&L, no Kelly, no registry flip, no
network, and the only file written is the report under `reports/`. No price is read or
persisted, so no `price_source_tag` attaches to this audit's own outputs; the rows it counts
carry their sources' tags (`broker_truth` on every settlement cache that declares one).

Run:
    python3 scripts/close_time_mutation_audit.py
    python3 scripts/close_time_mutation_audit.py --tape-root <dir> --no-live
"""
from __future__ import annotations

import argparse
import glob
import itertools
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.close_time_mutation import (  # noqa: E402
    OPEN_TO_OPEN, OPEN_TO_SETTLED, REGIMES, SETTLED_TO_SETTLED,
    PairedObservation, classify_pair, close_date, result_conflict, summarize,
)
# L345/L348: re-export the ANCHORED root rather than re-declaring the relative literal
# "tape". A relative root would silently score whatever tree the process happened to start in
# -- the exact defect the settlement-root-anchoring gate caught on brand-new code on 08-15.
from core.settlement_sources import (  # noqa: E402
    CACHE_MARKETS_MAP, DEFAULT_TAPE_ROOT, SETTLEMENT_SOURCES, SettlementSource,
)

REPORT_PATH = os.path.join(os.path.dirname(DEFAULT_TAPE_ROOT), "reports",
                           "close_time_mutation_audit.json")

#: Families whose records are LIVE re-observations of open markets (the drift control).
LIVE_FAMILY_GLOB = "universe_sweep/dt=*.jsonl"


# --------------------------------------------------------------------------- #
# cache-blob loading
# --------------------------------------------------------------------------- #
def cache_sources() -> Tuple[SettlementSource, ...]:
    """The declared sources that are `{"markets": {ticker: row}}` blobs, in registry order.

    Read from `core.settlement_sources` rather than hardcoded, so a source added there is
    audited here automatically instead of being silently skipped (L358's drift lesson).
    """
    return tuple(s for s in SETTLEMENT_SOURCES if s.kind == CACHE_MARKETS_MAP)


def load_cache_blob(path: str) -> Optional[Dict[str, Any]]:
    """Load one cache blob -> {"path", "pulled_at", "price_source_tag", "markets"}, else None."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            blob = json.load(fh)
    except (ValueError, OSError):
        return None
    if not isinstance(blob, Mapping):
        return None
    markets = blob.get("markets")
    if not isinstance(markets, Mapping):
        return None
    return {
        "path": path,
        "pulled_at": blob.get("pulled_at") if isinstance(blob.get("pulled_at"), str) else None,
        "price_source_tag": (blob.get("price_source_tag")
                             if isinstance(blob.get("price_source_tag"), str) else None),
        "markets": {t: r for t, r in markets.items()
                    if isinstance(t, str) and isinstance(r, Mapping)},
    }


def _pull_key(blob: Mapping[str, Any]) -> Tuple[str, str]:
    """Sort key: pulled_at when present, else the path. Never a fabricated timestamp.

    A blob with no `pulled_at` sorts by path and is flagged in the report; guessing an order
    for it would let the audit report a direction of change it did not observe.
    """
    return (blob.get("pulled_at") or "", blob.get("path") or "")


def load_all_cache_blobs(root: str = DEFAULT_TAPE_ROOT) -> List[Dict[str, Any]]:
    """Every readable cache blob under every declared CACHE_MARKETS_MAP source, pull-ordered."""
    out: List[Dict[str, Any]] = []
    for src in cache_sources():
        for path in sorted(glob.glob(os.path.join(root, src.path_glob))):
            blob = load_cache_blob(path)
            if blob is None:
                continue
            blob["source"] = src.name
            blob["label"] = f"{src.name}:{os.path.basename(path)}"
            out.append(blob)
    out.sort(key=_pull_key)
    return out


# --------------------------------------------------------------------------- #
# pairing
# --------------------------------------------------------------------------- #
def pair_blobs(earlier: Mapping[str, Any], later: Mapping[str, Any]
               ) -> List[PairedObservation]:
    """Classify every ticker the two blobs share. Order is the caller's; never re-inferred."""
    em, lm = earlier["markets"], later["markets"]
    return [classify_pair(t, em[t], lm[t], earlier["label"], later["label"])
            for t in sorted(set(em) & set(lm))]


def blob_pair_report(blobs: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Pairwise census over every ordered blob pair that shares at least one ticker."""
    pairs_out: List[Dict[str, Any]] = []
    all_obs: List[PairedObservation] = []
    conflicts: List[Dict[str, Any]] = []
    for a, b in itertools.combinations(blobs, 2):  # blobs already pull-ordered
        obs = pair_blobs(a, b)
        if not obs:
            continue
        all_obs.extend(obs)
        for t in sorted(set(a["markets"]) & set(b["markets"])):
            if result_conflict(a["markets"][t], b["markets"][t]):
                conflicts.append({
                    "ticker": t,
                    "earlier": a["label"], "earlier_result": a["markets"][t].get("result"),
                    "later": b["label"], "later_result": b["markets"][t].get("result"),
                })
        s = summarize(obs)
        pairs_out.append({
            "earlier": a["label"], "earlier_pulled_at": a["pulled_at"],
            "later": b["label"], "later_pulled_at": b["pulled_at"],
            "n_common": len(obs),
            "n_instant_changed": sum(1 for o in obs if o.instant_changed),
            "n_date_changed": sum(1 for o in obs if o.date_changed),
            "by_regime": s["by_regime"],
        })
    # A ticker shared by three blobs appears in three pairs, so the pooled counts above are
    # OBSERVATION counts, not market counts. Quoting them as markets would inflate the
    # headline by the number of redundant pulls -- report the distinct unit alongside, and
    # never let the two share a name.
    distinct: Dict[str, Dict[str, bool]] = {}
    for o in all_obs:
        d = distinct.setdefault(o.ticker, {r: False for r in REGIMES})
        d[o.regime] = True
        if o.instant_changed:
            d["instant_changed"] = True
        if o.date_changed:
            d["date_changed"] = True
    distinct_counts = {
        "n_distinct_tickers": len(distinct),
        "n_distinct_instant_changed": sum(1 for d in distinct.values()
                                          if d.get("instant_changed")),
        "n_distinct_date_changed": sum(1 for d in distinct.values() if d.get("date_changed")),
        "n_distinct_open_to_settled": sum(1 for d in distinct.values()
                                          if d.get(OPEN_TO_SETTLED)),
    }
    return {
        "n_blob_pairs_with_overlap": len(pairs_out),
        "pairs": pairs_out,
        "pooled": summarize(all_obs),
        "distinct_ticker_counts": distinct_counts,
        "settled_result_conflicts": conflicts,
        "n_settled_result_conflicts": len(conflicts),
    }


# --------------------------------------------------------------------------- #
# live-tape drift control (universe_sweep)
# --------------------------------------------------------------------------- #
def live_drift_report(root: str = DEFAULT_TAPE_ROOT, family_glob: str = LIVE_FAMILY_GLOB
                      ) -> Dict[str, Any]:
    """Do close_times drift while a market is still OPEN? First vs last live observation.

    Only tickers observed at >=2 DISTINCT `captured_at` instants count; a ticker seen once
    cannot answer a stability question and is excluded rather than counted as stable.
    """
    first: Dict[str, Tuple[str, Any, Any]] = {}
    last: Dict[str, Tuple[str, Any, Any]] = {}
    n_records = 0
    n_malformed = 0
    for path in sorted(glob.glob(os.path.join(root, family_glob))):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    n_malformed += 1
                    continue
                if not isinstance(rec, Mapping):
                    n_malformed += 1
                    continue
                n_records += 1
                t, ca = rec.get("ticker"), rec.get("captured_at")
                if not isinstance(t, str) or not isinstance(ca, str):
                    continue
                entry = (ca, rec.get("close_time"), rec.get("status"))
                if t not in first or ca < first[t][0]:
                    first[t] = entry
                if t not in last or ca > last[t][0]:
                    last[t] = entry
    repeat = [t for t in first if last[t][0] != first[t][0]]
    changed: List[Dict[str, Any]] = []
    stable = 0
    undated = 0
    for t in sorted(repeat):
        fa, fc, fs = first[t]
        la, lc, ls = last[t]
        obs = classify_pair(t, {"close_time": fc, "status": fs},
                            {"close_time": lc, "status": ls}, "live_first", "live_last")
        if obs.undated:
            undated += 1
        elif obs.instant_changed:
            changed.append({"ticker": t, "first_captured_at": fa, "first_close_time": fc,
                            "last_captured_at": la, "last_close_time": lc,
                            "delta_hours": obs.delta_hours})
        else:
            stable += 1
    return {
        "family_glob": family_glob,
        "n_records": n_records,
        "n_malformed": n_malformed,
        "n_distinct_tickers": len(first),
        "n_tickers_observed_twice_or_more": len(repeat),
        "n_close_time_stable": stable,
        "n_close_time_changed": len(changed),
        "n_undated": undated,
        "examples_changed": changed[:10],
    }


# --------------------------------------------------------------------------- #
# derived-value exposure: the UTC date a day-bucketing probe keys on
# --------------------------------------------------------------------------- #
def date_bucket_exposure(blobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """For every overlapping blob pair, how many shared tickers change UTC CLOSE DATE?

    This is the granularity `q51_m3_fill_projection._close_date_map` buckets on, so it is the
    honest measure of what a day-keyed consumer actually inherits from a placeholder close.
    """
    out: List[Dict[str, Any]] = []
    for a, b in itertools.combinations(blobs, 2):
        common = sorted(set(a["markets"]) & set(b["markets"]))
        if not common:
            continue
        n_dated = 0
        n_changed = 0
        for t in common:
            da = close_date(a["markets"][t].get("close_time"))
            db = close_date(b["markets"][t].get("close_time"))
            if da is None or db is None:
                continue
            n_dated += 1
            if da != db:
                n_changed += 1
        out.append({"earlier": a["label"], "later": b["label"], "n_common": len(common),
                    "n_dated": n_dated, "n_close_date_changed": n_changed})
    return out


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def build_report(root: str = DEFAULT_TAPE_ROOT, include_live: bool = True) -> Dict[str, Any]:
    blobs = load_all_cache_blobs(root)
    report: Dict[str, Any] = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "tape_root": root,
        "discipline": ("descriptive only: no verdict, no CI, no bootstrap, no P&L, no Kelly, "
                       "no registry flip, no network, no price read or persisted"),
        "cache_blobs": [
            {"label": b["label"], "source": b["source"], "path": os.path.relpath(b["path"], root),
             "pulled_at": b["pulled_at"], "price_source_tag": b["price_source_tag"],
             "n_markets": len(b["markets"]),
             "n_settled_rows": sum(1 for r in b["markets"].values()
                                   if (isinstance(r.get("result"), str) and r["result"].strip())
                                   or (isinstance(r.get("status"), str)
                                       and r["status"].strip().lower()
                                       in ("settled", "finalized", "determined")))}
            for b in blobs
        ],
        "n_cache_blobs": len(blobs),
        "n_blobs_without_pulled_at": sum(1 for b in blobs if not b["pulled_at"]),
        "blob_pairs": blob_pair_report(blobs),
        "close_date_exposure": date_bucket_exposure(blobs),
    }
    report["live_drift"] = live_drift_report(root) if include_live else None
    return report


def format_summary(report: Mapping[str, Any]) -> List[str]:
    lines: List[str] = []
    bp = report["blob_pairs"]
    pooled = bp["pooled"]["by_regime"]
    lines.append("=" * 78)
    lines.append("CLOSE_TIME MUTATION AUDIT (read-only, descriptive)")
    lines.append("=" * 78)
    lines.append(f"cache blobs: {report['n_cache_blobs']}  "
                 f"(no pulled_at: {report['n_blobs_without_pulled_at']})")
    dc = bp["distinct_ticker_counts"]
    lines.append(f"overlapping blob pairs: {bp['n_blob_pairs_with_overlap']}  "
                 f"paired observations: {bp['pooled']['n_pairs']}  "
                 f"DISTINCT tickers: {dc['n_distinct_tickers']}")
    lines.append(f"distinct tickers whose close_time instant changed: "
                 f"{dc['n_distinct_instant_changed']}  (close DATE changed: "
                 f"{dc['n_distinct_date_changed']}; open->settled: "
                 f"{dc['n_distinct_open_to_settled']})")
    for r in REGIMES:
        b = pooled[r]
        if not b["n"]:
            continue
        lines.append(
            f"  {r:<20} n={b['n']:<6} instant_changed={b['instant_changed']:<6} "
            f"date_changed={b['date_changed']:<6} earlier={b['moved_earlier']} "
            f"later={b['moved_later']} "
            f"median_delta_h={b['delta_hours_median'] if b['delta_hours_median'] is None else round(b['delta_hours_median'], 2)}")
    lines.append(f"settled-vs-settled RESULT conflicts: {bp['n_settled_result_conflicts']}")
    live = report.get("live_drift")
    if live:
        lines.append(f"live control ({live['family_glob']}): {live['n_records']} records, "
                     f"{live['n_tickers_observed_twice_or_more']} tickers re-observed, "
                     f"close_time stable={live['n_close_time_stable']} "
                     f"changed={live['n_close_time_changed']}")
    for row in report["close_date_exposure"]:
        if row["n_close_date_changed"]:
            lines.append(f"  close-DATE changed {row['n_close_date_changed']}/{row['n_dated']}"
                         f"  {row['earlier']} -> {row['later']}")
    lines.append("=" * 78)
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tape-root", default=DEFAULT_TAPE_ROOT)
    ap.add_argument("--report-path", default=REPORT_PATH)
    ap.add_argument("--no-live", action="store_true",
                    help="skip the universe_sweep drift control (it reads ~1.1M records)")
    args = ap.parse_args(argv)
    report = build_report(args.tape_root, include_live=not args.no_live)
    os.makedirs(os.path.dirname(args.report_path), exist_ok=True)
    with open(args.report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("\n".join(format_summary(report)))
    print(f"report -> {args.report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""universe_sweep_liquidity_census.py — DATA-QUALITY census of the universe_sweep tape family.

LOOP-QUEUE idle-policy (c) data-adequacy deep-dive. This is a DESCRIPTIVE / DATA-ADEQUACY
characterization, NOT a strategy probe: there is NO edge tested, NO bootstrap, NO CI, NO P&L,
NO fills. It answers Q46's Ryan-gated storage design call (b) — "add an activity/liquidity
discovery filter to shrink both the target universe AND the storage" — by measuring, across the
FULL committed `tape/universe_sweep/` history, what fraction of the breadth census actually
carries a buyable quote vs. is a no-offer dead-tail artifact (L105).

Read-only over committed tape. No network. Precedent shape: scripts/q25_depth_tape_anatomy.py
(read-only, JSON-out under findings/, offline fixture tests).

TIER DEFINITIONS (binding, per L47 / L105 / Hard Rule #3):
  * FILLABLE : yes_ask > 0.0 AND yes_ask_size >= 1.0   (a real buyable quote; a yes_ask==0 leg
               is the ABSENCE of a resting offer, NOT a $0.00 fill — never counted fillable).
  * LIQUID   : yes_ask > 0.0 AND yes_ask_size >= 10.0   (the repo's 10-contract depth floor, L26).
  * ACTIVITY : volume_24h>0 / open_interest>0 / volume>0 (three separate activity flags).
All *_size / volume fields are treated as FLOATS (L47 — a real observed best-level size was
91,316.82 contracts; int-truncation silently corrupts the read). No arithmetic on yes_ask as a
probability (Hard Rule #3) — this is pure counting/fractions.

Honest accounting: a malformed JSON line is COUNTED (n_malformed) and skipped, never silently
dropped. Every number is descriptive over `real_ask`-tagged data.

Run:
    python scripts/universe_sweep_liquidity_census.py
    python scripts/universe_sweep_liquidity_census.py --tape-root tape/universe_sweep \
        --json-out findings/universe_sweep_liquidity_census.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.io import REPO_ROOT  # noqa: E402

DEFAULT_TAPE_ROOT = REPO_ROOT / "tape" / "universe_sweep"
DEFAULT_JSON_OUT = REPO_ROOT / "findings" / "universe_sweep_liquidity_census.json"

LIQUID_SIZE_FLOOR = 10.0   # L26/Q23 depth floor
FILLABLE_SIZE_FLOOR = 1.0  # a single buyable contract


def _as_float(v: Any) -> Optional[float]:
    """Coerce a numeric-ish field to float WITHOUT int-truncation (L47). None if not numeric."""
    if v is None:
        return None
    if isinstance(v, bool):  # guard: bool is an int subclass, never a size
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def is_fillable(rec: Dict[str, Any]) -> bool:
    """A real buyable quote: a positive resting ask with >= 1.0 contract of size (L105 / L47)."""
    ask = _as_float(rec.get("yes_ask"))
    size = _as_float(rec.get("yes_ask_size"))
    if ask is None or size is None:
        return False
    return ask > 0.0 and size >= FILLABLE_SIZE_FLOOR


def is_liquid(rec: Dict[str, Any]) -> bool:
    """A quote resting >= the repo's 10-contract depth floor (L26)."""
    ask = _as_float(rec.get("yes_ask"))
    size = _as_float(rec.get("yes_ask_size"))
    if ask is None or size is None:
        return False
    return ask > 0.0 and size >= LIQUID_SIZE_FLOOR


def _positive(rec: Dict[str, Any], key: str) -> bool:
    v = _as_float(rec.get(key))
    return v is not None and v > 0.0


def series_prefix(rec: Dict[str, Any]) -> str:
    """Dead-tail bucketing key: the stored `series` if present, else the ticker's first segment."""
    s = rec.get("series")
    if isinstance(s, str) and s:
        return s
    tk = rec.get("ticker") or ""
    if isinstance(tk, str) and "-" in tk:
        return tk.split("-", 1)[0]
    return tk or "<unknown>"


class Accum:
    """A per-cell (pooled / per-day / per-pass) tally over census lines."""

    def __init__(self) -> None:
        self.n = 0
        self.n_bytes = 0
        self.n_fillable = 0
        self.n_fillable_bytes = 0
        self.n_liquid = 0
        self.n_liquid_bytes = 0
        self.n_vol24 = 0
        self.n_oi = 0
        self.n_vol = 0
        self.n_activity = 0        # any of vol24 / oi / vol
        self.n_activity_bytes = 0

    def add(self, rec: Dict[str, Any], nbytes: int) -> None:
        self.n += 1
        self.n_bytes += nbytes
        if is_fillable(rec):
            self.n_fillable += 1
            self.n_fillable_bytes += nbytes
        if is_liquid(rec):
            self.n_liquid += 1
            self.n_liquid_bytes += nbytes
        v24 = _positive(rec, "volume_24h")
        oi = _positive(rec, "open_interest")
        vol = _positive(rec, "volume")
        self.n_vol24 += int(v24)
        self.n_oi += int(oi)
        self.n_vol += int(vol)
        if v24 or oi or vol:
            self.n_activity += 1
            self.n_activity_bytes += nbytes

    @staticmethod
    def _frac(num: int, den: int) -> Optional[float]:
        return round(num / den, 6) if den else None

    def summary(self) -> Dict[str, Any]:
        return {
            "n_lines": self.n,
            "n_bytes": self.n_bytes,
            "fillable": {
                "n": self.n_fillable,
                "frac_lines": self._frac(self.n_fillable, self.n),
                "frac_bytes": self._frac(self.n_fillable_bytes, self.n_bytes),
            },
            "liquid": {
                "n": self.n_liquid,
                "frac_lines": self._frac(self.n_liquid, self.n),
                "frac_bytes": self._frac(self.n_liquid_bytes, self.n_bytes),
            },
            "activity": {
                "n_any": self.n_activity,
                "frac_any_lines": self._frac(self.n_activity, self.n),
                "frac_any_bytes": self._frac(self.n_activity_bytes, self.n_bytes),
                "frac_volume_24h": self._frac(self.n_vol24, self.n),
                "frac_open_interest": self._frac(self.n_oi, self.n),
                "frac_volume": self._frac(self.n_vol, self.n),
            },
        }


def census(tape_root: Path) -> Dict[str, Any]:
    """Walk every dt=*.jsonl pass under `tape_root`; return the full descriptive census."""
    files = sorted(Path(tape_root).glob("dt=*.jsonl"))
    pooled = Accum()
    per_day: Dict[str, Accum] = defaultdict(Accum)
    per_pass: Dict[str, Accum] = defaultdict(Accum)
    pass_day: Dict[str, str] = {}
    # dead-tail (NOT fillable) series composition, pooled
    dead_by_series: Dict[str, int] = defaultdict(int)
    whole_by_series: Dict[str, int] = defaultdict(int)
    n_dead = 0
    n_malformed = 0

    for fp in files:
        day = fp.name[len("dt="):-len(".jsonl")]
        with open(fp, "r", encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                nbytes = len(raw.encode("utf-8"))
                try:
                    rec = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    n_malformed += 1
                    continue
                if not isinstance(rec, dict):
                    n_malformed += 1
                    continue
                pooled.add(rec, nbytes)
                per_day[day].add(rec, nbytes)
                cid = rec.get("capture_id") or "<no-capture-id>"
                per_pass[cid].add(rec, nbytes)
                pass_day.setdefault(cid, day)
                sp = series_prefix(rec)
                whole_by_series[sp] += 1
                if not is_fillable(rec):
                    n_dead += 1
                    dead_by_series[sp] += 1

    # dead-tail top series ranking
    dead_rank = sorted(dead_by_series.items(), key=lambda kv: kv[1], reverse=True)
    top_dead = [
        {
            "series": s,
            "n_dead": c,
            "frac_of_dead": round(c / n_dead, 6) if n_dead else None,
            "frac_of_census": round(c / pooled.n, 6) if pooled.n else None,
        }
        for s, c in dead_rank[:10]
    ]
    # most-dominant dead-tail series as share of the WHOLE census
    dom_series, dom_dead_n = (dead_rank[0] if dead_rank else (None, 0))
    dominant = {
        "series": dom_series,
        "n_dead": dom_dead_n,
        "frac_of_census": round(dom_dead_n / pooled.n, 6) if (pooled.n and dom_series) else None,
        "n_in_census": whole_by_series.get(dom_series, 0) if dom_series else 0,
    }

    # pass-over-pass stability: per-day min/max/mean of pass-level fillable fraction
    day_passes: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for cid, acc in per_pass.items():
        frac = acc._frac(acc.n_fillable, acc.n)
        day_passes[pass_day[cid]].append(
            {"capture_id": cid, "n_lines": acc.n, "fillable_frac": frac})
    stability: Dict[str, Any] = {}
    for day, plist in sorted(day_passes.items()):
        plist_sorted = sorted(plist, key=lambda p: p["capture_id"])
        fracs = [p["fillable_frac"] for p in plist_sorted if p["fillable_frac"] is not None]
        stability[day] = {
            "n_passes": len(plist_sorted),
            "fillable_frac_min": round(min(fracs), 6) if fracs else None,
            "fillable_frac_max": round(max(fracs), 6) if fracs else None,
            "fillable_frac_mean": round(sum(fracs) / len(fracs), 6) if fracs else None,
            "passes": plist_sorted,
        }

    return {
        "schema": "universe_sweep_liquidity_census.v1",
        "tape_root": str(tape_root),
        "n_files": len(files),
        "n_lines": pooled.n,
        "n_malformed": n_malformed,
        "tier_definitions": {
            "fillable": "yes_ask > 0.0 AND yes_ask_size >= 1.0",
            "liquid": f"yes_ask > 0.0 AND yes_ask_size >= {LIQUID_SIZE_FLOOR}",
            "activity_any": "volume_24h>0 OR open_interest>0 OR volume>0",
        },
        "pooled": pooled.summary(),
        "per_day": {d: per_day[d].summary() for d in sorted(per_day)},
        "dead_tail": {
            "n_dead": n_dead,
            "frac_of_census_dead": round(n_dead / pooled.n, 6) if pooled.n else None,
            "top_series": top_dead,
            "most_dominant_series": dominant,
        },
        "pass_stability": stability,
        "storage_decision": {
            "note": "kept-fraction if the collector had filtered to each tier at capture time",
            "fillable_keep_frac_lines": pooled.summary()["fillable"]["frac_lines"],
            "fillable_keep_frac_bytes": pooled.summary()["fillable"]["frac_bytes"],
            "liquid_keep_frac_lines": pooled.summary()["liquid"]["frac_lines"],
            "liquid_keep_frac_bytes": pooled.summary()["liquid"]["frac_bytes"],
            "activity_keep_frac_lines": pooled.summary()["activity"]["frac_any_lines"],
            "activity_keep_frac_bytes": pooled.summary()["activity"]["frac_any_bytes"],
        },
    }


def _fmt_pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x * 100:6.2f}%"


def print_summary(rep: Dict[str, Any]) -> None:
    p = rep["pooled"]
    print("=" * 78)
    print("UNIVERSE_SWEEP LIQUIDITY CENSUS (descriptive / data-adequacy — no edge, no CI)")
    print("=" * 78)
    print(f"tape_root      : {rep['tape_root']}")
    print(f"files          : {rep['n_files']}   lines: {rep['n_lines']:,}   "
          f"malformed(skipped): {rep['n_malformed']}")
    print("-" * 78)
    print("POOLED tiers (of whole census):")
    print(f"  FILLABLE (ask>0 & size>=1)   : {_fmt_pct(p['fillable']['frac_lines'])} of lines  "
          f"({p['fillable']['n']:,})   bytes {_fmt_pct(p['fillable']['frac_bytes'])}")
    print(f"  LIQUID   (ask>0 & size>=10)  : {_fmt_pct(p['liquid']['frac_lines'])} of lines  "
          f"({p['liquid']['n']:,})   bytes {_fmt_pct(p['liquid']['frac_bytes'])}")
    print(f"  ACTIVITY (vol24|oi|vol > 0)  : {_fmt_pct(p['activity']['frac_any_lines'])} of lines  "
          f"({p['activity']['n_any']:,})   bytes {_fmt_pct(p['activity']['frac_any_bytes'])}")
    print(f"    - volume_24h>0             : {_fmt_pct(p['activity']['frac_volume_24h'])}")
    print(f"    - open_interest>0          : {_fmt_pct(p['activity']['frac_open_interest'])}")
    print(f"    - volume>0                 : {_fmt_pct(p['activity']['frac_volume'])}")
    print("-" * 78)
    print("PER-DAY fillable / liquid / activity fraction:")
    for d, s in rep["per_day"].items():
        print(f"  {d}  n={s['n_lines']:>6,}  fillable {_fmt_pct(s['fillable']['frac_lines'])}"
              f"  liquid {_fmt_pct(s['liquid']['frac_lines'])}"
              f"  activity {_fmt_pct(s['activity']['frac_any_lines'])}")
    print("-" * 78)
    dt = rep["dead_tail"]
    print(f"DEAD-TAIL (not fillable) = {_fmt_pct(dt['frac_of_census_dead'])} of census "
          f"({dt['n_dead']:,} lines). Top series by share of dead tail:")
    for row in dt["top_series"]:
        print(f"  {row['series']:<42} {_fmt_pct(row['frac_of_dead'])} of dead  "
              f"({_fmt_pct(row['frac_of_census'])} of census, n={row['n_dead']:,})")
    dom = dt["most_dominant_series"]
    print(f"  >> single most-dominant dead-tail series: {dom['series']} = "
          f"{_fmt_pct(dom['frac_of_census'])} of the WHOLE census")
    print("-" * 78)
    print("PASS-OVER-PASS stability (per-day pass-level fillable%):")
    for d, s in rep["pass_stability"].items():
        print(f"  {d}  passes={s['n_passes']}  fillable% "
              f"min {_fmt_pct(s['fillable_frac_min'])} "
              f"max {_fmt_pct(s['fillable_frac_max'])} "
              f"mean {_fmt_pct(s['fillable_frac_mean'])}")
    print("-" * 78)
    sd = rep["storage_decision"]
    print("STORAGE-DECISION headline (kept-fraction if filtered at capture time):")
    print(f"  keep FILLABLE tier : lines {_fmt_pct(sd['fillable_keep_frac_lines'])}  "
          f"bytes {_fmt_pct(sd['fillable_keep_frac_bytes'])}")
    print(f"  keep LIQUID   tier : lines {_fmt_pct(sd['liquid_keep_frac_lines'])}  "
          f"bytes {_fmt_pct(sd['liquid_keep_frac_bytes'])}")
    print(f"  keep ACTIVITY tier : lines {_fmt_pct(sd['activity_keep_frac_lines'])}  "
          f"bytes {_fmt_pct(sd['activity_keep_frac_bytes'])}")
    print("=" * 78)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tape-root", default=str(DEFAULT_TAPE_ROOT),
                    help="dir holding dt=*.jsonl universe_sweep passes")
    ap.add_argument("--json-out", default=str(DEFAULT_JSON_OUT),
                    help="machine-readable JSON summary output path")
    args = ap.parse_args(argv)

    tape_root = Path(args.tape_root)
    if not tape_root.exists():
        print(f"[census] tape root not found: {tape_root}", file=sys.stderr)
        return 2
    rep = census(tape_root)
    print_summary(rep)
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
    print(f"[census] wrote JSON summary -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

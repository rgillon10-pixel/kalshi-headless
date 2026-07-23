#!/usr/bin/env python3
"""universe_sweep_family_shapes.py — breadth idea-gen prep over the universe_sweep tape.

LOOP-QUEUE idle-run policy (d): an OBSERVATIONS MEMO from accumulated tape, feeding the NEXT
Q21 idea-gen round. This is DESCRIPTIVE breadth-discovery (prime directive #2: collect where
others aren't), NOT a strategy probe: NO edge tested, NO bootstrap, NO CI, NO P&L, NO fills,
NO registry change. Read-only over committed tape. No network.

It answers one falsifiable idea-gen question: across the full committed `tape/universe_sweep/`
breadth census, are there liquid, genuinely-ACTIVE Kalshi series-FAMILIES that the strategy
registry has never touched (outside weather / crypto-ladders / sports-moneyline / econ / fed /
perp), whose top-of-book carries a GENUINE two-sided quote (a YES ask AND a YES bid, both with
size) — i.e. a surface a future round could point a dedicated collector at?

TWO enabling findings this script pins (both verifiable from committed tape):

  (A) SCHEMA DEFECT (fresh, sibling to L96's always-zero `volume_24h`): the breadth collector
      `collection/universe_sweep.py` maps only the YES-side sizes (`yes_bid_size_fp`,
      `yes_ask_size_fp`; lines 116-117) and NEVER the no-side (`no_ask_size_fp`,
      `no_bid_size_fp`) — so `no_ask_size`/`no_bid_size` are persisted 0.0 on 100% of lines.
      A naive consumer reading `no_ask_size==0` would falsely conclude "no NO-side offer".
  (B) MIRROR (why (A) is recoverable, not lost): a Kalshi binary's NO ask IS the mirror of its
      YES bid — `no_ask == 1 - yes_bid` and `no_bid == 1  minus yes_ask` hold EXACTLY on this tape.
      So the fillable NO-ask size equals `yes_bid_size`, and the correct two-sided test uses the
      YES-side sizes, NOT the dropped `no_ask_size`.

Given (A)+(B), two-sidedness is measured as: yes_ask>0 & yes_ask_size>=1 AND yes_bid>0 &
yes_bid_size>=1. A wide ~$0.98 bid-ask (1c bid / 99c ask) is reported as its median spread so
the L31 nominal-not-capturable-spread artifact families are visibly distinguished from genuine
tight two-sided liquidity — the script makes NO claim that any family is tradeable.

All *_size fields are FLOATS (L47). No arithmetic on yes_ask as a probability (Hard Rule #3):
spread is a subtraction (yes_ask minus yes_bid), never a normalization. Every input line is
`real_ask`-tagged committed tape; a malformed line is COUNTED (n_malformed), never silently
dropped.

Run:
    python scripts/universe_sweep_family_shapes.py
    python scripts/universe_sweep_family_shapes.py --tape-root tape/universe_sweep \
        --json-out findings/universe_sweep_family_shapes.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.io import REPO_ROOT  # noqa: E402

DEFAULT_TAPE_ROOT = REPO_ROOT / "tape" / "universe_sweep"
DEFAULT_JSON_OUT = REPO_ROOT / "findings" / "universe_sweep_family_shapes.json"

FILLABLE_SIZE_FLOOR = 1.0  # a single buyable contract (L105 / L47)

# Coarse prefix map for triage ONLY — which series-families the strategy registry has already
# tested (so the breadth memo can highlight the UNTESTED remainder). Not authoritative; a family
# not on this list is flagged "untested" for a human to confirm, never auto-registered.
TESTED_PREFIXES = (
    "KXHIGH", "KXLOW", "KXTEMP",              # weather (S1/S5/S33/Q36/Q37)
    "KXBTC", "KXETH",                          # crypto hourly ladders (S8/S10/S14)
    "KXWC",                                    # World Cup rounds/games (S7/S9/S17)
    "KXFED", "KXCPI", "KXNFP", "KXPAYROLL", "KXGDP",  # econ/fed (S2/S12/S16/S17)
)
DEADTAIL_PREFIXES = ("KXMVE",)                 # auto-generated multi-leg no-offer tail (L105/L125)


def _as_float(v: Any) -> Optional[float]:
    """Coerce a numeric-ish field to float WITHOUT int-truncation (L47). None if not numeric."""
    if v is None:
        return None
    if isinstance(v, bool):  # bool is an int subclass; never a size/price
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def classify_series(series: str) -> str:
    """tested / deadtail / untested — coarse triage bucket (see TESTED_PREFIXES caveat)."""
    s = series or ""
    if any(s.startswith(p) for p in DEADTAIL_PREFIXES):
        return "deadtail"
    if any(s.startswith(p) for p in TESTED_PREFIXES) or "GAME" in s or "PERP" in s:
        return "tested"
    return "untested"


def mirror_holds(rec: Dict[str, Any], tol: float = 1e-6) -> Optional[bool]:
    """True/False if the Kalshi NO/YES mirror (no_ask==1-yes_bid, no_bid==1 minus yes_ask) holds on a
    two-priced line; None if the line lacks both YES prices (mirror untestable)."""
    ya = _as_float(rec.get("yes_ask"))
    yb = _as_float(rec.get("yes_bid"))
    na = _as_float(rec.get("no_ask"))
    nb = _as_float(rec.get("no_bid"))
    if ya is None or yb is None or na is None or nb is None:
        return None
    if not (ya > 0 and yb > 0):
        return None
    return abs(na - (1.0 - yb)) < tol and abs(nb - (1.0 - ya)) < tol


def yes_ask_fillable(rec: Dict[str, Any]) -> bool:
    ya = _as_float(rec.get("yes_ask"))
    yas = _as_float(rec.get("yes_ask_size"))
    return ya is not None and yas is not None and ya > 0.0 and yas >= FILLABLE_SIZE_FLOOR


def yes_bid_fillable(rec: Dict[str, Any]) -> bool:
    """A fillable YES bid == a fillable NO ask (mirror). Uses yes_bid_size because the collector
    drops no_ask_size (schema defect A)."""
    yb = _as_float(rec.get("yes_bid"))
    ybs = _as_float(rec.get("yes_bid_size"))
    return yb is not None and ybs is not None and yb > 0.0 and ybs >= FILLABLE_SIZE_FLOOR


def is_two_sided(rec: Dict[str, Any]) -> bool:
    """Genuine two-sided top of book: a fillable YES ask AND a fillable YES bid (== fillable NO
    ask via mirror). NOT via the dropped no_ask_size (which is always 0.0)."""
    return yes_ask_fillable(rec) and yes_bid_fillable(rec)


def _positive(rec: Dict[str, Any], key: str) -> bool:
    v = _as_float(rec.get(key))
    return v is not None and v > 0.0


class FamAccum:
    def __init__(self) -> None:
        self.n = 0
        self.n_active = 0          # volume>0 or open_interest>0
        self.n_two_sided = 0
        self.sum_volume = 0.0
        self.max_oi = 0.0
        self.events: set = set()
        self.spreads: List[float] = []   # yes_ask minus yes_bid on two-sided lines

    def add(self, rec: Dict[str, Any]) -> None:
        self.n += 1
        if _positive(rec, "volume") or _positive(rec, "open_interest"):
            self.n_active += 1
        if is_two_sided(rec):
            self.n_two_sided += 1
            ya = _as_float(rec.get("yes_ask")) or 0.0
            yb = _as_float(rec.get("yes_bid")) or 0.0
            self.spreads.append(ya - yb)
        v = _as_float(rec.get("volume"))
        if v:
            self.sum_volume += v
        oi = _as_float(rec.get("open_interest")) or 0.0
        if oi > self.max_oi:
            self.max_oi = oi
        ev = rec.get("event_ticker")
        if ev:
            self.events.add(ev)

    def summary(self, series: str) -> Dict[str, Any]:
        med = round(statistics.median(self.spreads), 4) if self.spreads else None
        return {
            "series": series,
            "klass": classify_series(series),
            "n_lines": self.n,
            "n_active": self.n_active,
            "n_two_sided": self.n_two_sided,
            "sum_volume": int(self.sum_volume),
            "max_open_interest": int(self.max_oi),
            "n_events": len(self.events),
            "median_two_sided_spread": med,
        }


def size_field_population(recs_iter) -> Dict[str, Any]:
    """Nonzero-count for each of the four top-of-book size fields (schema-defect evidence A)."""
    tot = 0
    fields = ("yes_ask_size", "yes_bid_size", "no_ask_size", "no_bid_size")
    pos = {k: 0 for k in fields}
    mx = {k: 0.0 for k in fields}
    for rec in recs_iter:
        tot += 1
        for k in fields:
            v = _as_float(rec.get(k)) or 0.0
            if v > 0.0:
                pos[k] += 1
            if v > mx[k]:
                mx[k] = v
    return {
        "n_lines": tot,
        "nonzero": pos,
        "nonzero_frac": {k: (round(pos[k] / tot, 6) if tot else None) for k in fields},
        "max": mx,
    }


def analyze(tape_root: Path) -> Dict[str, Any]:
    files = sorted(Path(tape_root).glob("dt=*.jsonl"))
    fam: Dict[str, FamAccum] = defaultdict(FamAccum)
    n_lines = 0
    n_malformed = 0
    n_bad_tag = 0
    # schema-defect + mirror tallies
    size_pos = {k: 0 for k in ("yes_ask_size", "yes_bid_size", "no_ask_size", "no_bid_size")}
    size_max = {k: 0.0 for k in ("yes_ask_size", "yes_bid_size", "no_ask_size", "no_bid_size")}
    mirror_tot = 0
    mirror_ok = 0

    for fp in files:
        with open(fp, "r", encoding="utf-8") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                try:
                    rec = json.loads(raw)
                except (json.JSONDecodeError, ValueError):
                    n_malformed += 1
                    continue
                if not isinstance(rec, dict):
                    n_malformed += 1
                    continue
                n_lines += 1
                if rec.get("price_source_tag") != "real_ask":
                    n_bad_tag += 1
                for k in size_pos:
                    v = _as_float(rec.get(k)) or 0.0
                    if v > 0.0:
                        size_pos[k] += 1
                    if v > size_max[k]:
                        size_max[k] = v
                mh = mirror_holds(rec)
                if mh is not None:
                    mirror_tot += 1
                    mirror_ok += int(mh)
                fam[rec.get("series") or "<none>"].add(rec)

    fam_rows = [acc.summary(s) for s, acc in fam.items()]
    # untested families with a genuine two-sided line, ranked by two-sided count
    untested_two = sorted(
        [r for r in fam_rows if r["klass"] == "untested" and r["n_two_sided"] > 0],
        key=lambda r: (-r["n_two_sided"], -r["n_active"]),
    )
    # the honest shortlist: untested + two-sided + genuinely ACTIVE (real volume/OI), tight-ish
    shortlist = sorted(
        [r for r in untested_two if r["n_active"] > 0
         and r["median_two_sided_spread"] is not None
         and r["median_two_sided_spread"] <= 0.15],
        key=lambda r: (-r["n_active"], r["median_two_sided_spread"]),
    )

    klass_totals: Dict[str, Dict[str, int]] = defaultdict(lambda: {"families": 0, "lines": 0,
                                                                    "active": 0, "two_sided": 0})
    for r in fam_rows:
        kt = klass_totals[r["klass"]]
        kt["families"] += 1
        kt["lines"] += r["n_lines"]
        kt["active"] += r["n_active"]
        kt["two_sided"] += r["n_two_sided"]

    return {
        "schema": "universe_sweep_family_shapes.v1",
        "tape_root": str(tape_root),
        "n_files": len(files),
        "n_lines": n_lines,
        "n_malformed": n_malformed,
        "n_not_real_ask_tag": n_bad_tag,
        "size_field_population": {
            "note": "no_ask_size / no_bid_size are dropped by collection/universe_sweep.py "
                    "(only yes-side sizes mapped, lines 116-117) — schema defect A",
            "nonzero": size_pos,
            "nonzero_frac": {k: (round(size_pos[k] / n_lines, 6) if n_lines else None)
                             for k in size_pos},
            "max": size_max,
        },
        "mirror_check": {
            "note": "no_ask==1-yes_bid AND no_bid==1 minus yes_ask on lines with both YES prices>0 "
                    "(finding B — the dropped no-side size is recoverable as the YES-side size)",
            "n_tested": mirror_tot,
            "n_holds": mirror_ok,
            "frac_holds": round(mirror_ok / mirror_tot, 6) if mirror_tot else None,
        },
        "class_totals": dict(klass_totals),
        "untested_two_sided_families": untested_two,
        "active_tight_shortlist": shortlist,
    }


def print_summary(rep: Dict[str, Any]) -> None:
    print("=" * 82)
    print("UNIVERSE_SWEEP FAMILY SHAPES (breadth idea-gen prep — no edge, no CI, no registration)")
    print("=" * 82)
    print(f"tape_root : {rep['tape_root']}  files={rep['n_files']}  lines={rep['n_lines']:,}  "
          f"malformed={rep['n_malformed']}  non-real_ask={rep['n_not_real_ask_tag']}")
    sp = rep["size_field_population"]["nonzero_frac"]
    print("-" * 82)
    print("SCHEMA DEFECT A (size-field nonzero fraction):")
    for k in ("yes_ask_size", "yes_bid_size", "no_ask_size", "no_bid_size"):
        f = sp[k]
        print(f"  {k:16} nonzero {('%.3f%%' % (f*100)) if f is not None else 'n/a':>9}")
    mc = rep["mirror_check"]
    print(f"MIRROR B: no_ask==1-yes_bid & no_bid==1 minus yes_ask holds "
          f"{mc['n_holds']}/{mc['n_tested']} "
          f"({('%.2f%%' % (mc['frac_holds']*100)) if mc['frac_holds'] is not None else 'n/a'})")
    print("-" * 82)
    print("CLASS TOTALS:")
    for k, v in rep["class_totals"].items():
        print(f"  {k:9} families={v['families']:>4}  lines={v['lines']:>8,}  "
              f"active={v['active']:>7,}  two_sided={v['two_sided']:>6,}")
    print("-" * 82)
    print(f"UNTESTED families with a genuine two-sided line: "
          f"{len(rep['untested_two_sided_families'])}")
    print("ACTIVE + TIGHT (<=15c median spread) shortlist — raw idea-gen material only:")
    print(f"  {'series':30} {'n':>5} {'2side':>5} {'active':>6} {'sumvol':>8} "
          f"{'maxOI':>7} {'events':>6} {'medspread':>9}")
    for r in rep["active_tight_shortlist"]:
        print(f"  {r['series'][:30]:30} {r['n_lines']:>5} {r['n_two_sided']:>5} "
              f"{r['n_active']:>6} {r['sum_volume']:>8} {r['max_open_interest']:>7} "
              f"{r['n_events']:>6} {r['median_two_sided_spread']:>9.3f}")
    print("=" * 82)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tape-root", default=str(DEFAULT_TAPE_ROOT))
    ap.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    args = ap.parse_args(argv)
    tape_root = Path(args.tape_root)
    if not tape_root.exists():
        print(f"[family-shapes] tape root not found: {tape_root}", file=sys.stderr)
        return 2
    rep = analyze(tape_root)
    print_summary(rep)
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
    print(f"[family-shapes] wrote JSON summary -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

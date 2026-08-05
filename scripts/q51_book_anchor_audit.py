"""q51_book_anchor_audit — can ANY committed book family anchor the executed-print tape?

READ-ONLY, fully OFFLINE (no network, no credential, no order verb). Verdict class:
**DATA-ADEQUACY**. This script produces NO edge claim, NO P&L, NO bootstrap CI and NO
registry change.

Why this exists. L280 (2026-08-04, `findings/2026-08-04-q51-trade-tape-quality-deepdive.md`)
measured the print-side dual of the Q51 join and got **10.1%**: of the executed prints we
hold, only one in ten sits inside an `orderbook_depth` book interval we can price against.
The finding named the defect BOOK-side (depth cadence: median gap 180 min, max 1,080 min).
Two follow-up questions were left open, and both change what the repo should build next:

1. **Breadth fix?** `tape/universe_sweep/` is the repo's OTHER book family — 652 MB, 17 days,
   full-universe top-of-book WITH `yes_bid_size`/`yes_ask_size`. If it covers the print
   tickers `orderbook_depth` drops, the print-side hole closes for free on already-committed
   tape. This script answers that as a measurement, not an assumption.
2. **Criterion sensitivity?** L280's rule is a BRACKET: a print is usable iff its ticker has
   >=2 snapshots AND the print falls inside [first, last]. That is the right rule for "can I
   quote this market at the moment it printed". It is NOT the rule a resting-maker fill-sim
   needs, which is weaker: a PRIOR quote to derive the resting price from, then prints after
   it. The two criteria are reported side by side so nobody reads 10.1% as the fill-sim's
   population bound without also reading the staleness it costs to relax it.

Non-negotiables observed here:
* The control must reproduce. `anchor_coverage(..., BRACKET)` over `orderbook_depth`'s
  same-day tape MUST return L280's 10.1%; if it does not, this script's numbers are void and
  the discrepancy IS the finding. Pinned by an acceptance test.
* Buckets partition the print tape exactly under BOTH criteria — a print is never silently
  dropped, and a coverage gap always lowers the number rather than vanishing (L10).
* Every family's `price_source_tag`s are censused into the report, so no number here rests on
  an untagged price (CLAUDE.md trust default: untagged => synthetic).
* A relaxed criterion never gets to claim the strict one's authority: the freshness ladder and
  median anchor age travel WITH the coverage fraction in the same dict.

Run:
    python3 scripts/q51_book_anchor_audit.py            # -> reports/q51_book_anchor_audit.json
"""
from __future__ import annotations

import argparse
import bisect
import collections
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.io import REPO_ROOT  # noqa: E402

from scripts.q51_maker_fillsim import (  # noqa: E402
    DAY,
    DEPTH_TAPE,
    MIN_UNITS,
    game_of,
    load_depth,
    load_prints,
    parse_ts,
)
from scripts.q51_trade_tape_quality import adjacent_days  # noqa: E402

SWEEP_TAPE = REPO_ROOT / "tape" / "universe_sweep"
REPORT_PATH = REPO_ROOT / "reports" / "q51_book_anchor_audit.json"
SCHEMA_VERSION = "q51_book_anchor_audit.v1"

# The two anchor criteria, named so no call site passes a bare string literal.
BRACKET = "bracket"   # L280's rule: >=2 snapshots AND print inside [first, last]
PRIOR = "prior"       # the fill-sim's rule: >=1 snapshot at or before the print

# Staleness rungs (minutes) — same rungs as L280's ladder so the two are comparable,
# plus a 12h rung because the relaxed criterion admits anchors that stale.
FRESHNESS_RUNGS = (15.0, 60.0, 180.0, 720.0)

# `universe_sweep` writes exactly this many rows per capture when its pager is cap-bound
# (`collection/universe_sweep.py`: MAX_CALLS=20 * PAGE_LIMIT=1000). Measured at-cap on
# 100% of committed captures by the 2026-08-03 saturation finding; re-derived here, never
# assumed — `sweep_panel_profile` reports the observed sizes.
SWEEP_ROW_CAP = 20000


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def _iter_lines(path: Path) -> Iterable[dict]:
    """Parsed JSON objects from a JSONL day-file; unparseable lines are skipped by the
    caller's own counter, never by silently shrinking a denominator."""
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                yield {"__parse_error__": True}


def load_sweep(days: Sequence[str], tape_root: Optional[Path] = None
               ) -> Dict[str, List[float]]:
    """ticker -> time-sorted capture timestamps from `universe_sweep` day-files.

    Only the timestamp is retained: this module asks WHETHER a market was observed and WHEN,
    never what its price was — no price crosses from here into any P&L."""
    root = tape_root or SWEEP_TAPE
    snaps: Dict[str, List[float]] = collections.defaultdict(list)
    for d in days:
        for rec in _iter_lines(root / f"dt={d}.jsonl"):
            if rec.get("__parse_error__"):
                continue
            tk = rec.get("ticker")
            ts = parse_ts(rec.get("captured_at"))
            if tk and ts is not None:
                snaps[tk].append(ts)
    for v in snaps.values():
        v.sort()
    return dict(snaps)


def load_depth_ts(days: Sequence[str]) -> Dict[str, List[float]]:
    """ticker -> time-sorted `orderbook_depth` snapshot timestamps, unioned over days."""
    merged: Dict[str, List[float]] = collections.defaultdict(list)
    for d in days:
        for tk, rows in load_depth(d)[1].items():
            merged[tk].extend(r["ts"] for r in rows)
    for v in merged.values():
        v.sort()
    return dict(merged)


def union_snaps(*sources: Dict[str, List[float]]) -> Dict[str, List[float]]:
    """Merge several ticker->timestamps maps. Union is the fairest possible reading of
    'what could the repo anchor against if it used everything it has'."""
    out: Dict[str, List[float]] = collections.defaultdict(list)
    for s in sources:
        for tk, v in s.items():
            out[tk].extend(v)
    for v in out.values():
        v.sort()
    return dict(out)


# --------------------------------------------------------------------------- #
# 1. is `universe_sweep` a PANEL or a rotating census?
# --------------------------------------------------------------------------- #
def sweep_panel_profile(days: Sequence[str], tape_root: Optional[Path] = None
                        ) -> Dict[str, Any]:
    """The question that decides whether `universe_sweep` can anchor anything at all.

    A book family is usable as an anchor only if it OBSERVES THE SAME MARKET MORE THAN ONCE.
    A cap-truncated sweep whose enumeration slice rotates between passes produces enormous
    breadth and zero panel depth: every ticker seen once, no price change, no interval, no
    anchor-then-print join. `is_panel` is False when the modal ticker is observed exactly
    once — a structural verdict about the family, independent of any strategy."""
    obs: collections.Counter = collections.Counter()
    per_day: Dict[str, Dict[str, Any]] = {}
    tags: collections.Counter = collections.Counter()
    n_parse_errors = 0
    for d in days:
        caps: collections.Counter = collections.Counter()
        tickers: set = set()
        for rec in _iter_lines((tape_root or SWEEP_TAPE) / f"dt={d}.jsonl"):
            if rec.get("__parse_error__"):
                n_parse_errors += 1
                continue
            tk = rec.get("ticker")
            caps[rec.get("capture_id")] += 1
            tags[rec.get("price_source_tag") or "__untagged__"] += 1
            if tk:
                obs[tk] += 1
                tickers.add(tk)
        if not caps:
            continue
        sizes = sorted(caps.values())
        per_day[d] = {
            "n_lines": sum(sizes),
            "n_captures": len(sizes),
            "n_distinct_tickers": len(tickers),
            "capture_sizes": sizes,
            "all_captures_at_cap": all(s == SWEEP_ROW_CAP for s in sizes),
        }
    if not obs:
        return {"days": list(days), "n_lines": 0, "is_panel": None,
                "note": "no committed universe_sweep lines for these days"}
    hist = collections.Counter(obs.values())
    n_tickers = len(obs)
    once = hist.get(1, 0)
    return {
        "days": list(days),
        "per_day": per_day,
        "n_lines": sum(obs.values()),
        "n_parse_errors": n_parse_errors,
        "n_distinct_tickers": n_tickers,
        "observations_per_ticker_histogram": {str(k): v for k, v in sorted(hist.items())},
        "max_observations_per_ticker": max(hist),
        "n_tickers_observed_once": once,
        "frac_tickers_observed_once": round(once / n_tickers, 4),
        "n_tickers_ever_revisited": n_tickers - once,
        "frac_captures_at_row_cap": round(
            sum(1 for d in per_day.values() for s in d["capture_sizes"] if s == SWEEP_ROW_CAP)
            / max(1, sum(d["n_captures"] for d in per_day.values())), 4),
        "price_source_tag_census": dict(tags),
        # A family whose MODAL ticker is seen once cannot supply a second observation of
        # anything; that is the whole finding, stated as a boolean.
        "is_panel": hist.most_common(1)[0][0] > 1,
    }


# --------------------------------------------------------------------------- #
# 2. anchor coverage under both criteria
# --------------------------------------------------------------------------- #
def anchor_coverage(prints: Dict[str, List[dict]],
                    snaps: Dict[str, List[float]],
                    criterion: str) -> Dict[str, Any]:
    """Of the prints we hold, how many can be anchored to a book observation?

    BRACKET (L280): usable iff the ticker has >=2 observations AND the print time lies within
    [first, last]. Reproduces the published 10.1% exactly — it is the control.
    PRIOR: usable iff >=1 observation lands at or before the print. This is what a resting
    maker fill-sim actually needs (a quote to rest against, then prints after it), and it is
    STRICTLY WEAKER, so it always returns a number >= BRACKET's. The freshness ladder is
    returned in the same dict precisely so the weaker number cannot be quoted alone.

    The returned buckets partition the print tape exactly; `buckets_partition_the_tape`
    is False if they ever do not, and a caller must treat that as a void result."""
    if criterion not in (BRACKET, PRIOR):
        raise ValueError(f"unknown criterion: {criterion!r}")
    usable = 0
    no_observation = 0        # ticker never observed by this family
    too_few = 0               # BRACKET only: observed, but < 2 times
    before_first = 0
    after_last = 0            # BRACKET only: print past the family's last look at the ticker
    ages: List[float] = []
    fresh = {r: 0 for r in FRESHNESS_RUNGS}
    n_prints = 0
    for tk, pl in prints.items():
        v = snaps.get(tk) or []
        for pr in pl:
            n_prints += 1
            t = pr["ts"]
            if not v:
                no_observation += 1
                continue
            if criterion == BRACKET and len(v) < 2:
                too_few += 1
                continue
            i = bisect.bisect_right(v, t)
            if i == 0:
                before_first += 1
                continue
            if criterion == BRACKET and t > v[-1]:
                after_last += 1
                continue
            usable += 1
            age = (t - v[i - 1]) / 60.0
            ages.append(age)
            for rung in FRESHNESS_RUNGS:
                if age <= rung:
                    fresh[rung] += 1

    def frac(k: int) -> Optional[float]:
        return round(k / n_prints, 4) if n_prints else None

    buckets = usable + no_observation + too_few + before_first + after_last
    return {
        "criterion": criterion,
        "n_prints": n_prints,
        "n_usable": usable,
        "frac_usable": frac(usable),
        "n_ticker_never_observed": no_observation,
        "n_ticker_under_two_observations": too_few,
        "n_before_first_observation": before_first,
        "n_after_last_observation": after_last,
        "buckets_partition_the_tape": buckets == n_prints,
        "median_anchor_age_min": round(statistics.median(ages), 1) if ages else None,
        "p90_anchor_age_min": (round(sorted(ages)[int(0.90 * (len(ages) - 1))], 1)
                               if ages else None),
        "freshness_ladder": {f"within_{int(r)}min": {"n": fresh[r], "frac": frac(fresh[r])}
                             for r in FRESHNESS_RUNGS},
    }


def fresh_anchor_unit_profile(prints: Dict[str, List[dict]],
                              snaps: Dict[str, List[float]],
                              max_age_min: float = 15.0) -> Dict[str, Any]:
    """The number that actually decides whether a fill-sim is CONSTRUCTIBLE on this tape.

    Coverage fractions are not the bound; RESAMPLE UNITS are. A print is admitted here only
    if some book observation of its own ticker lands at or before it and is younger than
    `max_age_min` — the freshest-anchor population, the only one a fill-sim can price without
    quoting a hours-stale book. Units are GAMES (L6: outcomes inside one event are not
    independent draws), derived via the shared `game_of`, and compared against the repo's
    own `MIN_UNITS` floor (L41). `clears_unit_floor` False means no CI may be computed on
    this population at all — an adequacy verdict, not a weak result."""
    n_prints = 0
    fresh = 0
    units: collections.Counter = collections.Counter()
    for tk, pl in prints.items():
        v = snaps.get(tk) or []
        for pr in pl:
            n_prints += 1
            if not v:
                continue
            i = bisect.bisect_right(v, pr["ts"])
            if i == 0:
                continue
            if (pr["ts"] - v[i - 1]) / 60.0 <= max_age_min:
                fresh += 1
                units[game_of(tk)] += 1
    return {
        "max_anchor_age_min": max_age_min,
        "n_prints": n_prints,
        "n_fresh_anchored_prints": fresh,
        "frac_fresh_anchored": round(fresh / n_prints, 4) if n_prints else None,
        "n_resample_units": len(units),
        "unit_definition": "game (L6) via game_of(ticker)",
        "min_units_floor": MIN_UNITS,
        "clears_unit_floor": len(units) >= MIN_UNITS,
        "prints_per_unit": sorted(units.values(), reverse=True),
    }


def ticker_coverage(prints: Dict[str, List[dict]],
                    named: Dict[str, Dict[str, List[float]]]) -> Dict[str, Any]:
    """Print-ticker and PRINT-WEIGHTED coverage per family. Print-weighted is the honest
    denominator: 42 tickers carry very unequal print counts, so a ticker-count coverage
    figure can flatter a family that only covers the quiet ones."""
    pt = set(prints)
    weights = {tk: len(v) for tk, v in prints.items()}
    total_w = sum(weights.values())
    out: Dict[str, Any] = {"n_print_tickers": len(pt), "n_prints": total_w, "families": {}}
    for name, snaps in named.items():
        hit = pt & set(snaps)
        w = sum(weights[t] for t in hit)
        out["families"][name] = {
            "n_print_tickers_covered": len(hit),
            "frac_print_tickers_covered": round(len(hit) / len(pt), 4) if pt else None,
            "n_prints_on_covered_tickers": w,
            "frac_prints_on_covered_tickers": round(w / total_w, 4) if total_w else None,
        }
    return out


# --------------------------------------------------------------------------- #
# 3. report
# --------------------------------------------------------------------------- #
def depth_tag_census(days: Sequence[str]) -> Dict[str, int]:
    """`orderbook_depth` stores a tag DICT (`price_source_tags`), not a scalar — censused
    separately so the report has an explicit tag for every family it touches."""
    tags: collections.Counter = collections.Counter()
    for d in days:
        for rec in _iter_lines(DEPTH_TAPE / f"dt={d}.jsonl"):
            if rec.get("__parse_error__"):
                continue
            t = rec.get("price_source_tags")
            tags[json.dumps(t, sort_keys=True) if t else "__untagged__"] += 1
    return dict(tags)


def build_report(day: str = DAY, sweep_days: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    days = adjacent_days(day)
    prints = load_prints(day)
    depth_same = load_depth_ts([day])
    depth_adj = load_depth_ts(days)
    sweep_adj = load_sweep(days)
    union_adj = union_snaps(depth_adj, sweep_adj)

    families = {
        "orderbook_depth_same_day": depth_same,
        "orderbook_depth_adjacent": depth_adj,
        "universe_sweep_adjacent": sweep_adj,
        "union_adjacent": union_adj,
    }
    coverage = {name: {c: anchor_coverage(prints, s, c) for c in (BRACKET, PRIOR)}
                for name, s in families.items()}

    all_sweep_days = sorted(p.name[3:-6] for p in SWEEP_TAPE.glob("dt=*.jsonl")) \
        if sweep_days is None else list(sweep_days)

    return {
        "schema_version": SCHEMA_VERSION,
        "verdict_class": "DATA-ADEQUACY — no edge claim, no P&L, no CI, no registry change",
        "print_day": day,
        "book_days": days,
        "control": {
            "definition": "L280's BRACKET criterion over orderbook_depth same-day tape",
            "published_frac_usable": 0.101,
            "reproduced_frac_usable":
                coverage["orderbook_depth_same_day"][BRACKET]["frac_usable"],
            "reproduces": abs((coverage["orderbook_depth_same_day"][BRACKET]["frac_usable"]
                               or 0.0) - 0.101) < 0.001,
        },
        "ticker_coverage": ticker_coverage(prints, families),
        "anchor_coverage": coverage,
        "fresh_anchor_unit_profile": {
            name: {f"within_{int(r)}min": fresh_anchor_unit_profile(prints, s_, r)
                   for r in (15.0, 60.0, 180.0)}
            for name, s_ in families.items() if name != "universe_sweep_adjacent"
        },
        "universe_sweep_panel_profile": sweep_panel_profile(all_sweep_days),
        "price_source_tags": {
            "kalshi_trades": "broker_truth (enforced at load: non-broker_truth lines dropped)",
            "orderbook_depth": depth_tag_census(days),
            "universe_sweep": "see universe_sweep_panel_profile.price_source_tag_census",
        },
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day", default=DAY)
    ap.add_argument("--out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    rep = build_report(args.day)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    c = rep["control"]
    print(f"control (L280 bracket, depth same-day): {c['reproduced_frac_usable']} "
          f"vs published {c['published_frac_usable']} -> "
          f"{'REPRODUCES' if c['reproduces'] else 'DOES NOT REPRODUCE — numbers void'}")
    for name, byc in rep["anchor_coverage"].items():
        print(f"  {name:28s} bracket={byc[BRACKET]['frac_usable']:<8} "
              f"prior={byc[PRIOR]['frac_usable']:<8} "
              f"median_anchor_age_min={byc[PRIOR]['median_anchor_age_min']}")
    for name, byr in rep["fresh_anchor_unit_profile"].items():
        u = byr["within_15min"]
        print(f"  {name:28s} fresh<=15min prints={u['n_fresh_anchored_prints']:<6} "
              f"units={u['n_resample_units']:<4} clears_floor({u['min_units_floor']})="
              f"{u['clears_unit_floor']}")
    p = rep["universe_sweep_panel_profile"]
    print(f"universe_sweep: {p['n_lines']} lines / {p['n_distinct_tickers']} tickers / "
          f"observed-once {p['frac_tickers_observed_once']} / is_panel={p['is_panel']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only data-quality audit of `tape/polymarket_cpi_pairs/`: the collector DETECTS an
invalid derived probability and flags it honestly — does the defect stop there?

The family's Kalshi leg is SYNTHETIC by construction: `collection/polymarket_pairs.py::
price_cpi_bucket_from_kalshi` differences Kalshi's cumulative "exceed T" ladder into a
Polymarket-shaped bucket probability (an `exact` bucket is the difference between the offer
on the T-minus-one-step rung and the offer on the T rung, both `real_ask` on Kalshi's side).
When the ladder is locally inverted that difference goes NEGATIVE, and the collector says so:
it never clips, and it sets `monotonicity_violation: True`. That half is honest.

The half this audit measures is what happens NEXT. The record's `prob_gap`
(`derived_prob - polymarket.best_ask`) is computed and persisted from the same invalid number,
with no flag of its own, so a consumer that reads `prob_gap` without also reading
`kalshi.monotonicity_violation` inherits a value that cannot be a difference of two
probabilities at all. Two committed records carry `|prob_gap| > 1.0`.

Second question, the one that decides whether this is repairable in place: the record persists
the THRESHOLDS it differenced (`kalshi_inputs = {exceed_le, exceed_ge}`) but NOT the two
`yes_ask` legs, so a violating record cannot be diagnosed from this family's own tape (which
rung inverted, by how much, one-sided quote vs genuinely crossed book). `tape/econ_prints/`
holds the same `KXCPI*` events' full `real_ask` ladder — this script measures how much of the
violating cohort that join actually reconstructs, with a FRESHNESS LADDER beside every coverage
fraction (L283) and measured from BOTH sides of the join (L280): the pairs-side "how many
violations can I diagnose?" AND the econ-side "how many ladder inversions did the pairs family's
own cadence never sample?".

Strike spacing is never hardcoded — the collector assumes a 0.1 CPI step, and this audit checks
that against `core.pricing.infer_strike_spacing` over each ladder's own strikes (L7).

DESCRIPTIVE ONLY: no gate, no bootstrap CI, no P&L, no verdict, no registry change, no network,
no writes outside the `--out` report. Read-only over tape.

Run:
    python3 scripts/polymarket_cpi_pairs_monotonicity_audit.py --max-day 2026-08-04
    python3 scripts/polymarket_cpi_pairs_monotonicity_audit.py --pairs-dir <dir> --econ-dir <dir>

`--max-day` closes the window: without it, tomorrow's collector pass silently moves every
number a finding quoted (and every acceptance test that pinned them).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Repo root on sys.path so `core` / `scripts` imports work when run directly (L232).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import infer_strike_spacing  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts.polymarket_pair_terms_audit import (  # noqa: E402
    GitRunner, _default_git_runner, resolve_git_ref,
)

DEFAULT_PAIRS_DIR = REPO_ROOT / "tape" / "polymarket_cpi_pairs"
DEFAULT_ECON_DIR = REPO_ROOT / "tape" / "econ_prints"
REPORT_PATH = REPO_ROOT / "reports" / "polymarket_cpi_pairs_monotonicity_audit.json"

PAIR_SCHEMA = "polymarket_cpi_pairs.v1"
ECON_SCHEMA = "econ_prints.v1"

# Mirrors `collection/polymarket_pairs.py::price_cpi_bucket_from_kalshi`'s own tolerance. Kept
# as a named constant so the INDEPENDENT re-derivation below is comparable to the persisted
# flag on identical terms rather than on a tighter/looser bar of this script's invention.
VIOLATION_TOL = 1e-9

# A difference of two probabilities lives in [-1, 1]. Anything outside is arithmetically
# impossible and is the clearest evidence that the invalid derived value leaked downstream.
IMPOSSIBLE_ABS_GAP = 1.0

# Coverage without freshness is not coverage (L283) — every join fraction is reported against
# this ladder of |econ_prints capture - pairs capture| bounds.
JOIN_AGE_BOUNDS_HOURS: Tuple[float, ...] = (0.05, 0.25, 1.0, 6.0, 24.0)

# A resting offer with no bid behind it is a NOMINAL quote, not a two-sided market (the L105
# no-offer distinction, one level up). Used only to LABEL the anatomy of an inversion.
WIDE_SPREAD = 0.5

# Kalshi lists this family's ladders as cumulative `greater` strikes; the differencing
# transform reads no other strike_type.
LADDER_STRIKE_TYPE = "greater"

# The collector's assumed CPI bucket step (`collection/polymarket_pairs.py::_CPI_BUCKET_STEP`).
# NOT used for any computation here — reported only so it can be compared against each
# ladder's OWN inferred spacing (L7: never trust a hardcoded width, read it off the data).
COLLECTOR_ASSUMED_STEP = 0.1


# --------------------------------------------------------------------------- #
# per-record classification (pure)
# --------------------------------------------------------------------------- #
def is_out_of_unit_interval(p: Optional[float], tol: float = VIOLATION_TOL) -> Optional[bool]:
    """Independent re-derivation of the collector's `monotonicity_violation` predicate. None on
    a missing/non-numeric probability — an honest "not measured", never a guessed False."""
    if not isinstance(p, (int, float)) or isinstance(p, bool):
        return None
    return not (-tol <= float(p) <= 1.0 + tol)


def classify_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Per-record view of the defect. Pure, no I/O.

    `flag_persisted`  -> what the collector wrote.
    `flag_recomputed` -> what this script derives from `derived_prob` alone.
    `flags_agree`     -> the two agree (the honesty half: does the flag track the defect?).
    `gap_impossible`  -> `|prob_gap| > 1` — a value that cannot be a difference of two
                         probabilities, and therefore proof the invalid input propagated.
    """
    kalshi = rec.get("kalshi") if isinstance(rec.get("kalshi"), dict) else {}
    poly = rec.get("polymarket") if isinstance(rec.get("polymarket"), dict) else {}
    inputs = kalshi.get("kalshi_inputs") if isinstance(kalshi.get("kalshi_inputs"), dict) else {}

    derived = kalshi.get("derived_prob")
    persisted = kalshi.get("monotonicity_violation")
    recomputed = is_out_of_unit_interval(derived)
    gap = rec.get("prob_gap")
    gap_num = isinstance(gap, (int, float)) and not isinstance(gap, bool)

    return {
        "schema_version": rec.get("schema_version"),
        "capture_id": rec.get("capture_id"),
        "captured_at": rec.get("captured_at"),
        "series": rec.get("series"),
        "period": rec.get("period"),
        "event_ticker": kalshi.get("event_ticker"),
        "bucket_kind": rec.get("bucket_kind"),
        "bucket_value": rec.get("bucket_value"),
        "derived_prob": derived,
        "flag_persisted": persisted if isinstance(persisted, bool) else None,
        "flag_recomputed": recomputed,
        "flags_agree": (isinstance(persisted, bool) and persisted == recomputed),
        "prob_gap": gap if gap_num else None,
        "abs_prob_gap": abs(float(gap)) if gap_num else None,
        "gap_persisted": gap_num,
        "gap_impossible": bool(gap_num and abs(float(gap)) > IMPOSSIBLE_ABS_GAP),
        "exceed_le": inputs.get("exceed_le"),
        "exceed_ge": inputs.get("exceed_ge"),
        "polymarket_best_ask": poly.get("best_ask"),
        # CLAUDE.md trust default: an absent tag is `synthetic`, never "fine".
        "kalshi_price_source_tag": kalshi.get("price_source_tag") or "synthetic",
        "polymarket_price_source_tag": poly.get("price_source_tag") or "synthetic",
    }


def gap_cohort_stats(abs_gaps: Sequence[float]) -> Dict[str, Any]:
    """Dispersion of a cohort's |prob_gap|. Empty cohort -> nulls, never zeros."""
    vals = [float(v) for v in abs_gaps]
    if not vals:
        return {"n": 0, "mean_abs_gap": None, "median_abs_gap": None,
                "max_abs_gap": None, "sum_abs_gap": 0.0}
    return {
        "n": len(vals),
        "mean_abs_gap": round(statistics.mean(vals), 6),
        "median_abs_gap": round(statistics.median(vals), 6),
        "max_abs_gap": round(max(vals), 6),
        "sum_abs_gap": round(sum(vals), 6),
    }


# --------------------------------------------------------------------------- #
# tape loading
# --------------------------------------------------------------------------- #
def _parse_ts(value: Any) -> Optional[datetime]:
    """Tape timestamp -> aware UTC datetime, None on anything unparseable. Routed through
    `core.timeutil.parse_iso_utc` (L136/L150): the stdlib parser rejects bare-`Z` / short
    fractional-second forms on the declared Python floor, which is 38% of committed tape."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return parse_iso_utc(value)
    except (ValueError, TypeError):
        return None


def _day_of(path: Path) -> str:
    name = path.name
    return name[3:-6] if name.startswith("dt=") and name.endswith(".jsonl") else name


def _day_files(tape_dir: Path, max_day: Optional[str]) -> List[Path]:
    """`dt=*.jsonl` files under `tape_dir`, optionally capped at `max_day` (inclusive).

    The cap exists so an audit — and the acceptance tests that pin its numbers — describes a
    CLOSED window: without it, tomorrow's collector pass silently changes today's headline."""
    if not Path(tape_dir).is_dir():
        return []
    files = sorted(p for p in Path(tape_dir).glob("dt=*.jsonl") if p.is_file())
    if max_day is None:
        return files
    return [p for p in files if _day_of(p) <= max_day]


def load_pair_records(pairs_dir: Path = DEFAULT_PAIRS_DIR, max_day: Optional[str] = None,
                      ) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Every `polymarket_cpi_pairs.v1` line under `pairs_dir`, each annotated with its tape
    `day` and parsed timestamp. Non-pair / unparseable lines are COUNTED, never silently
    dropped."""
    pairs_dir = Path(pairs_dir)
    out: List[Dict[str, Any]] = []
    meta = {"n_files": 0, "n_lines": 0, "n_bad_json": 0, "n_other_schema": 0}
    for path in _day_files(pairs_dir, max_day):
        meta["n_files"] += 1
        day = _day_of(path)
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                meta["n_lines"] += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    meta["n_bad_json"] += 1
                    continue
                if not isinstance(rec, dict):
                    meta["n_bad_json"] += 1
                    continue
                if rec.get("schema_version") != PAIR_SCHEMA:
                    meta["n_other_schema"] += 1
                    continue
                rec["_day"] = day
                rec["_ts"] = _parse_ts(rec.get("captured_at"))
                out.append(rec)
    return out, meta


def load_econ_ladders(econ_dir: Path = DEFAULT_ECON_DIR, max_day: Optional[str] = None,
                      ) -> Dict[str, List[Dict[str, Any]]]:
    """`event_ticker -> [ladder, ...]` sorted by capture time, from `tape/econ_prints/`.

    A ladder is `{captured_at, day, asks, bids, tags, spacing}` where `asks`/`bids` map a
    rounded `floor_strike` to that rung's `yes_ask`/`yes_bid` as FLOATS (no int coercion —
    L47's rule generalizes: a price is never truncated on the way in). `spacing` is the
    ladder's OWN inferred strike gap (L7), not the collector's assumed step.
    """
    econ_dir = Path(econ_dir)
    out: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for path in _day_files(econ_dir, max_day):
        day = _day_of(path)
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict) or rec.get("schema_version") != ECON_SCHEMA:
                    continue
                ts = _parse_ts(rec.get("captured_at"))
                events = ((rec.get("open_events") or {}).get("events")
                          if isinstance(rec.get("open_events"), dict) else None) or []
                for ev in events:
                    if not isinstance(ev, dict):
                        continue
                    ticker = ev.get("event_ticker")
                    if not isinstance(ticker, str) or not ticker:
                        continue
                    asks: Dict[float, Optional[float]] = {}
                    bids: Dict[float, Optional[float]] = {}
                    tags: Dict[float, str] = {}
                    for s in ev.get("strikes") or []:
                        if not isinstance(s, dict):
                            continue
                        if s.get("strike_type") != LADDER_STRIKE_TYPE:
                            continue
                        fs = s.get("floor_strike")
                        if not isinstance(fs, (int, float)) or isinstance(fs, bool):
                            continue
                        k = round(float(fs), 1)
                        ya, yb = s.get("yes_ask"), s.get("yes_bid")
                        asks[k] = float(ya) if isinstance(ya, (int, float)) \
                            and not isinstance(ya, bool) else None
                        bids[k] = float(yb) if isinstance(yb, (int, float)) \
                            and not isinstance(yb, bool) else None
                        tags[k] = s.get("price_source_tag") or "synthetic"
                    if not asks:
                        continue
                    out[ticker].append({
                        "captured_at": ts, "day": day, "asks": asks, "bids": bids,
                        "tags": tags, "spacing": infer_strike_spacing(asks.keys()),
                    })
    for ticker in out:
        out[ticker].sort(key=lambda lad: (lad["captured_at"] is None, lad["captured_at"]))
    return dict(out)


# --------------------------------------------------------------------------- #
# the join
# --------------------------------------------------------------------------- #
def needed_strikes(info: Dict[str, Any]) -> Optional[List[float]]:
    """The strike(s) the record's own `kalshi_inputs` says were differenced. None when the
    bucket kind is unknown or an input the kind requires is missing."""
    kind = info.get("bucket_kind")
    lo, hi = info.get("exceed_le"), info.get("exceed_ge")
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool)  # noqa: E731
    if kind == "floor":
        return [round(float(hi), 1)] if num(hi) else None
    if kind == "ceiling":
        return [round(float(lo), 1)] if num(lo) else None
    if kind == "exact":
        return [round(float(lo), 1), round(float(hi), 1)] if num(lo) and num(hi) else None
    return None


def reconstruct_prob(kind: str, asks: Dict[float, Optional[float]],
                     lo: Optional[float], hi: Optional[float]) -> Optional[float]:
    """Re-apply the collector's own differencing transform to a real_ask ladder read from
    `tape/econ_prints/`. None when a needed rung is absent or unpriced — never a guess."""
    def ask(k: Optional[float]) -> Optional[float]:
        if k is None:
            return None
        return asks.get(round(float(k), 1))
    if kind == "floor":
        a = ask(hi)
        return None if a is None else 1.0 - a
    if kind == "ceiling":
        return ask(lo)
    if kind == "exact":
        a_lo, a_hi = ask(lo), ask(hi)
        return None if (a_lo is None or a_hi is None) else a_lo - a_hi
    return None


def join_to_econ_ladder(info: Dict[str, Any],
                        ladders: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Nearest-in-time `econ_prints` ladder for this record's event that actually PRICES every
    rung the record differenced, plus what that ladder says about the record.

    Nearest-in-time over the whole family (not same-day-only) on purpose: the age is reported
    as a ladder of bounds (L283) rather than being pre-baked into a single yes/no, so a reader
    can see whether a "joinable" claim rests on a 3-second-old quote or a 6-hour-old one.
    """
    out: Dict[str, Any] = {
        "joined": False, "reason": None, "age_hours": None, "ladder_captured_at": None,
        "ladder_day": None, "ladder_spacing": None, "reconstructed_prob": None,
        "reconstruction_abs_diff": None, "reconstruction_exact": None,
        "inversion_reproduced": None, "ask_lo": None, "ask_hi": None, "bid_hi": None,
        "high_rung_spread": None, "high_rung_one_sided": None, "rung_tags": None,
    }
    ticker = info.get("event_ticker")
    ts = info.get("_ts")
    need = needed_strikes(info)
    cands = ladders.get(ticker) if isinstance(ticker, str) else None
    if not cands:
        out["reason"] = "no_econ_capture_for_event"
        return out
    if ts is None:
        out["reason"] = "unparseable_record_timestamp"
        return out
    if need is None:
        out["reason"] = "record_inputs_incomplete"
        return out

    priced = [lad for lad in cands
              if lad["captured_at"] is not None
              and all(lad["asks"].get(k) is not None for k in need)]
    if not priced:
        out["reason"] = "needed_rungs_absent_or_unpriced"
        return out
    best = min(priced, key=lambda lad: abs((lad["captured_at"] - ts).total_seconds()))
    age = abs((best["captured_at"] - ts).total_seconds()) / 3600.0

    lo, hi = info.get("exceed_le"), info.get("exceed_ge")
    recon = reconstruct_prob(str(info.get("bucket_kind")), best["asks"], lo, hi)
    derived = info.get("derived_prob")
    diff = (abs(recon - float(derived))
            if recon is not None and isinstance(derived, (int, float))
            and not isinstance(derived, bool) else None)

    a_lo = best["asks"].get(round(float(lo), 1)) if lo is not None else None
    a_hi = best["asks"].get(round(float(hi), 1)) if hi is not None else None
    b_hi = best["bids"].get(round(float(hi), 1)) if hi is not None else None
    spread = (a_hi - b_hi) if (a_hi is not None and b_hi is not None) else None

    out.update({
        "joined": True,
        "age_hours": round(age, 6),
        "ladder_captured_at": best["captured_at"].isoformat(),
        "ladder_day": best["day"],
        "ladder_spacing": best["spacing"],
        "reconstructed_prob": recon,
        "reconstruction_abs_diff": diff,
        "reconstruction_exact": (diff is not None and diff <= VIOLATION_TOL),
        "inversion_reproduced": (is_out_of_unit_interval(recon)
                                 if recon is not None else None),
        "ask_lo": a_lo, "ask_hi": a_hi, "bid_hi": b_hi,
        "high_rung_spread": (round(spread, 6) if spread is not None else None),
        "high_rung_one_sided": (b_hi is not None and b_hi <= 0.0),
        "rung_tags": sorted({best["tags"].get(k, "synthetic") for k in need}),
    })
    return out


def join_freshness_ladder(ages: Sequence[Optional[float]], n_total: int,
                          bounds: Sequence[float] = JOIN_AGE_BOUNDS_HOURS) -> Dict[str, Any]:
    """Coverage fraction WITH its freshness ladder attached (L283) — a join is only as good as
    the age of the quote it lands on."""
    vals = [float(a) for a in ages if a is not None]
    rung = {}
    for b in bounds:
        n = sum(1 for a in vals if a <= b)
        rung[f"within_{b}h"] = {"n": n,
                                "frac": round(n / n_total, 6) if n_total else None}
    return {
        "n_total": n_total,
        "n_joined": len(vals),
        "frac_joined": round(len(vals) / n_total, 6) if n_total else None,
        "median_age_hours": round(statistics.median(vals), 6) if vals else None,
        "max_age_hours": round(max(vals), 6) if vals else None,
        "freshness_ladder": rung,
    }


# --------------------------------------------------------------------------- #
# the other side of the join (L280)
# --------------------------------------------------------------------------- #
def shadow_inversion_by_day(records: List[Dict[str, Any]],
                            ladders: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """The PRINT-SIDE question, one level over (L280): on each tape day, how often was the very
    rung pair this family pairs actually inverted in `econ_prints`, versus how many violations
    the family's own cadence recorded? A day of zero flags with a non-zero shadow rate is an
    under-SAMPLED defect, not a healed one."""
    paired: Dict[str, Dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for rec in records:
        info = classify_record(rec)
        if info["bucket_kind"] != "exact":
            continue
        need = needed_strikes(info)
        if need is None or len(need) != 2:
            continue
        paired[rec["_day"]][str(info["event_ticker"])].add((need[0], need[1]))

    rows: Dict[str, Dict[str, Any]] = {}
    for day, by_ticker in paired.items():
        obs = inv = 0
        for ticker, rung_pairs in by_ticker.items():
            for lad in ladders.get(ticker, []):
                if lad["day"] != day:
                    continue
                for lo, hi in rung_pairs:
                    a_lo, a_hi = lad["asks"].get(lo), lad["asks"].get(hi)
                    if a_lo is None or a_hi is None:
                        continue
                    obs += 1
                    if (a_lo - a_hi) < -VIOLATION_TOL:
                        inv += 1
        rows[day] = {
            "n_econ_rung_pair_observations": obs,
            "n_econ_inverted": inv,
            "frac_econ_inverted": round(inv / obs, 6) if obs else None,
        }
    return rows


# --------------------------------------------------------------------------- #
# git provenance
# --------------------------------------------------------------------------- #
def uncommitted_tape_paths(dirs: Sequence[Path], repo_root: Path = REPO_ROOT,
                           run_git: GitRunner = _default_git_runner) -> Optional[List[str]]:
    """Paths under `dirs` that differ from the index/HEAD (L242: every count below describes
    the WORKING TREE). None when git is unavailable — never raises, never poisons the report."""
    rels: List[str] = []
    for d in dirs:
        try:
            rels.append(str(Path(d).resolve().relative_to(Path(repo_root).resolve())))
        except ValueError:
            return None
    try:
        out = run_git(["-C", str(repo_root), "status", "--porcelain", "--"] + rels)
    except (RuntimeError, OSError):
        return None
    return sorted(line.strip() for line in out.splitlines() if line.strip())


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def audit(pairs_dir: Path = DEFAULT_PAIRS_DIR, econ_dir: Path = DEFAULT_ECON_DIR,
          repo_root: Path = REPO_ROOT, run_git: GitRunner = _default_git_runner,
          max_day: Optional[str] = None) -> Dict[str, Any]:
    records, meta = load_pair_records(pairs_dir, max_day)
    ladders = load_econ_ladders(econ_dir, max_day)

    infos: List[Dict[str, Any]] = []
    joins: List[Dict[str, Any]] = []
    for rec in records:
        info = classify_record(rec)
        info["_ts"] = rec.get("_ts")
        info["_day"] = rec.get("_day")
        infos.append(info)
        joins.append(join_to_econ_ladder(info, ladders))

    viol_idx = [i for i, f in enumerate(infos) if f["flag_persisted"] is True]
    clean_idx = [i for i, f in enumerate(infos) if f["flag_persisted"] is False]

    # --- honesty of the flag itself (co-occurrence, both directions) ------------------- #
    cooccurrence: Counter = Counter()
    for f in infos:
        cooccurrence[f"persisted={f['flag_persisted']},recomputed={f['flag_recomputed']}"] += 1
    n_disagree = sum(1 for f in infos if not f["flags_agree"])

    # --- containment of the metric derived FROM the flagged-invalid value -------------- #
    all_gaps = [f["abs_prob_gap"] for f in infos if f["abs_prob_gap"] is not None]
    viol_gaps = [infos[i]["abs_prob_gap"] for i in viol_idx
                 if infos[i]["abs_prob_gap"] is not None]
    clean_gaps = [infos[i]["abs_prob_gap"] for i in clean_idx
                  if infos[i]["abs_prob_gap"] is not None]
    st_all, st_viol, st_clean = (gap_cohort_stats(all_gaps), gap_cohort_stats(viol_gaps),
                                 gap_cohort_stats(clean_gaps))
    impossible = [
        {"captured_at": infos[i]["captured_at"], "event_ticker": infos[i]["event_ticker"],
         "bucket_kind": infos[i]["bucket_kind"], "bucket_value": infos[i]["bucket_value"],
         "derived_prob": infos[i]["derived_prob"],
         "polymarket_best_ask": infos[i]["polymarket_best_ask"],
         "prob_gap": infos[i]["prob_gap"],
         "flag_persisted": infos[i]["flag_persisted"],
         "kalshi_inputs": {"exceed_le": infos[i]["exceed_le"],
                           "exceed_ge": infos[i]["exceed_ge"]},
         "econ_prints_diagnosis": {
             "ask_at_exceed_le": joins[i]["ask_lo"], "ask_at_exceed_ge": joins[i]["ask_hi"],
             "yes_bid_at_exceed_ge": joins[i]["bid_hi"],
             "ladder_captured_at": joins[i]["ladder_captured_at"],
             "age_hours": joins[i]["age_hours"],
             "rung_price_source_tags": joins[i]["rung_tags"]},
         }
        for i in range(len(infos)) if infos[i]["gap_impossible"]
    ]
    n_viol_with_gap = sum(1 for i in viol_idx if infos[i]["gap_persisted"])

    # --- the join, pairs-side ---------------------------------------------------------- #
    def join_block(idxs: Sequence[int]) -> Dict[str, Any]:
        ages = [joins[i]["age_hours"] for i in idxs]
        blk = join_freshness_ladder(ages, len(idxs))
        joined = [i for i in idxs if joins[i]["joined"]]
        exact = [i for i in joined if joins[i]["reconstruction_exact"]]
        diffs = [joins[i]["reconstruction_abs_diff"] for i in joined
                 if joins[i]["reconstruction_abs_diff"] is not None]
        # A reconstruction miss is a STALENESS artifact, not a failed join, so the fresh
        # sub-population is reported separately rather than pooled (L283's freshness rule
        # applied to the reconstruction, not just to the coverage count).
        fresh = [joins[i]["reconstruction_abs_diff"] for i in joined
                 if joins[i]["reconstruction_abs_diff"] is not None
                 and (joins[i]["age_hours"] or 0.0) <= 1.0]
        blk["reconstruction"] = {
            "n_reconstructed": len(diffs),
            "n_exact_to_1e_9": len(exact),
            "frac_exact": round(len(exact) / len(idxs), 6) if idxs else None,
            "max_abs_diff": round(max(diffs), 9) if diffs else None,
            "n_reconstructed_on_joins_within_1h": len(fresh),
            "max_abs_diff_on_joins_within_1h": round(max(fresh), 9) if fresh else None,
            "meaning": ("re-applying the collector's own differencing transform to the "
                        "econ_prints real_ask ladder reproduces the persisted synthetic "
                        "derived_prob — the raw legs the pairs schema drops are recoverable"),
        }
        blk["failure_reasons"] = dict(sorted(Counter(
            joins[i]["reason"] for i in idxs if not joins[i]["joined"]).items()))
        return blk

    # --- anatomy of the inversions (what the join lets you SAY) ------------------------- #
    anat: Counter = Counter()
    spreads: List[float] = []
    rung_pattern: Counter = Counter()
    for i in viol_idx:
        j = joins[i]
        if not j["joined"]:
            anat["undiagnosable"] += 1
            continue
        if j["inversion_reproduced"]:
            anat["inversion_reproduced_in_real_ask_ladder"] += 1
        else:
            anat["not_reproduced_ladder_disagrees"] += 1
        if j["high_rung_one_sided"]:
            anat["high_rung_one_sided_no_bid"] += 1
        if j["high_rung_spread"] is not None:
            spreads.append(j["high_rung_spread"])
            anat["high_rung_spread_wide" if j["high_rung_spread"] >= WIDE_SPREAD
                 else "high_rung_spread_tight"] += 1
        rung_pattern[f"ask_lo={j['ask_lo']},ask_hi={j['ask_hi']}"] += 1

    # --- temporal -------------------------------------------------------------------- #
    shadow = shadow_inversion_by_day(records, ladders)
    by_day: Dict[str, Dict[str, Any]] = {}
    for day in sorted({str(f["_day"]) for f in infos}):
        idxs = [i for i, f in enumerate(infos) if f["_day"] == day]
        row = {
            "n_records": len(idxs),
            "n_exact_bucket": sum(1 for i in idxs if infos[i]["bucket_kind"] == "exact"),
            "n_capture_passes": len({infos[i]["capture_id"] for i in idxs}),
            "n_violations": sum(1 for i in idxs if infos[i]["flag_persisted"] is True),
            "n_impossible_gaps": sum(1 for i in idxs if infos[i]["gap_impossible"]),
        }
        row.update(shadow.get(day, {"n_econ_rung_pair_observations": 0,
                                    "n_econ_inverted": 0, "frac_econ_inverted": None}))
        by_day[day] = row
    undersampled = sorted(d for d, r in by_day.items()
                          if r["n_violations"] == 0 and r["n_econ_inverted"] > 0)

    # --- spacing check (L7) ------------------------------------------------------------ #
    spacing_by_series: Dict[str, Dict[str, int]] = defaultdict(Counter)
    for ticker, lads in ladders.items():
        if not ticker.startswith("KXCPI"):
            continue
        for lad in lads:
            key = "null" if lad["spacing"] is None else str(round(lad["spacing"], 4))
            spacing_by_series[ticker.split("-")[0]][key] += 1

    # --- tags -------------------------------------------------------------------------- #
    tag_census = {
        "kalshi_leg": dict(sorted(Counter(f["kalshi_price_source_tag"]
                                          for f in infos).items())),
        "polymarket_leg": dict(sorted(Counter(f["polymarket_price_source_tag"]
                                              for f in infos).items())),
        "econ_prints_rungs_used_in_join": dict(sorted(Counter(
            t for j in joins for t in (j["rung_tags"] or [])).items())),
        "note": ("prob_gap is a SYNTHETIC-minus-REAL_ASK difference and carries no tag of its "
                 "own; per CLAUDE.md's trust default an untagged number is `synthetic`"),
    }

    git_ref = resolve_git_ref(repo_root, run_git)
    return {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "max_day": max_day,
        "git_ref": git_ref,
        "uncommitted_tape_paths": uncommitted_tape_paths([Path(pairs_dir), Path(econ_dir)],
                                                          repo_root, run_git),
        "pairs_tape_dir": str(pairs_dir),
        "econ_tape_dir": str(econ_dir),
        "population": {
            **meta,
            "n_pair_records": len(infos),
            "n_by_series": dict(sorted(Counter(str(f["series"]) for f in infos).items())),
            "n_by_event_ticker": dict(sorted(Counter(str(f["event_ticker"])
                                                     for f in infos).items())),
            "n_by_bucket_kind": dict(sorted(Counter(str(f["bucket_kind"])
                                                    for f in infos).items())),
            "n_econ_events_indexed": len(ladders),
            "n_econ_ladders_indexed": sum(len(v) for v in ladders.values()),
        },
        "violation_detection": {
            "n_violations_persisted": len(viol_idx),
            "n_violations_recomputed": sum(1 for f in infos if f["flag_recomputed"] is True),
            "frac_violating": round(len(viol_idx) / len(infos), 6) if infos else None,
            "cooccurrence_persisted_vs_recomputed": dict(sorted(cooccurrence.items())),
            "n_flag_disagreements": n_disagree,
            "flag_is_honest": n_disagree == 0,
            "n_by_bucket_kind": dict(sorted(Counter(str(infos[i]["bucket_kind"])
                                                    for i in viol_idx).items())),
            "n_by_event_ticker": dict(sorted(Counter(str(infos[i]["event_ticker"])
                                                     for i in viol_idx).items())),
            "derived_prob_range_on_violations": {
                "min": min((infos[i]["derived_prob"] for i in viol_idx), default=None),
                "max": max((infos[i]["derived_prob"] for i in viol_idx), default=None),
            },
        },
        "prob_gap_containment": {
            "n_violating_records_with_a_persisted_prob_gap": n_viol_with_gap,
            "frac_of_violations_carrying_a_gap": (round(n_viol_with_gap / len(viol_idx), 6)
                                                  if viol_idx else None),
            "all_records": st_all,
            "violating_cohort": st_viol,
            "clean_cohort": st_clean,
            "frac_of_total_abs_gap_mass_from_violating_cohort": (
                round(st_viol["sum_abs_gap"] / st_all["sum_abs_gap"], 6)
                if st_all["sum_abs_gap"] else None),
            "frac_of_headline_mean_that_is_excess_over_clean_cohort": (
                round((st_all["mean_abs_gap"] - st_clean["mean_abs_gap"])
                      / st_all["mean_abs_gap"], 6)
                if st_all["mean_abs_gap"] else None),
            "n_impossible_abs_gap_gt_1": len(impossible),
            "impossible_records": impossible,
            "meaning": ("the collector flags the invalid derived_prob and then computes "
                        "prob_gap from it anyway; the gap carries no flag of its own, so a "
                        "consumer that reads prob_gap without also reading "
                        "kalshi.monotonicity_violation inherits the defect"),
        },
        "econ_prints_join": {
            "join_key": "kalshi.event_ticker + kalshi_inputs strike(s), nearest capture in time",
            "all_records": join_block(list(range(len(infos)))),
            "violating_cohort": join_block(viol_idx),
            "clean_cohort": join_block(clean_idx),
            "inversion_anatomy": {
                **{k: v for k, v in sorted(anat.items())},
                "median_high_rung_spread": (round(statistics.median(spreads), 6)
                                            if spreads else None),
                "top_rung_ask_patterns": dict(rung_pattern.most_common(8)),
                "meaning": ("a violating record's two real_ask legs are recoverable from "
                            "econ_prints, which is what turns 'this number is invalid' into "
                            "'this rung was quoted one-sided at ask≈$1 with no bid'"),
            },
        },
        "temporal": {
            "by_day": by_day,
            "days_with_zero_flags_but_a_nonzero_econ_inversion_rate": undersampled,
            "meaning": ("the pairs family's violation count is bounded by its own capture "
                        "cadence: a day can record 0 violations while the same rungs were "
                        "observably inverted in econ_prints (L280 — measure a join from both "
                        "sides; L283 — a hole can be cadence, not breadth)"),
        },
        "ladder_spacing_check": {
            "collector_assumed_step": COLLECTOR_ASSUMED_STEP,
            "inferred_spacing_by_series": {k: dict(sorted(v.items()))
                                           for k, v in sorted(spacing_by_series.items())},
            "meaning": ("L7 — the collector hardcodes a 0.1 CPI step; this is that assumption "
                        "checked against each ladder's own inferred spacing, not re-hardcoded"),
        },
        "source_tags": tag_census,
        "scope": ("DESCRIPTIVE / DATA-QUALITY ONLY — read-only over tape; no gate, no "
                  "bootstrap CI, no P&L, no strategy verdict, no registry change, no "
                  "collector write-path change"),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="read-only monotonicity/diagnosability audit of "
                                             "tape/polymarket_cpi_pairs (DESCRIPTIVE ONLY)")
    ap.add_argument("--pairs-dir", default=str(DEFAULT_PAIRS_DIR))
    ap.add_argument("--econ-dir", default=str(DEFAULT_ECON_DIR))
    ap.add_argument("--out", default=str(REPORT_PATH))
    ap.add_argument("--max-day", default=None,
                    help="cap the audited window at this tape day (inclusive, e.g. 2026-08-04)")
    ap.add_argument("--stdout", action="store_true",
                    help="print the full report instead of a summary")
    args = ap.parse_args(argv)

    rep = audit(Path(args.pairs_dir), Path(args.econ_dir), max_day=args.max_day)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if args.stdout:
        print(json.dumps(rep, indent=2, sort_keys=True))
        return 0

    v = rep["violation_detection"]
    g = rep["prob_gap_containment"]
    j = rep["econ_prints_join"]["violating_cohort"]
    print(f"records={rep['population']['n_pair_records']} "
          f"violations={v['n_violations_persisted']} ({v['frac_violating']}) "
          f"flag_is_honest={v['flag_is_honest']} (disagreements={v['n_flag_disagreements']})")
    print(f"prob_gap persisted on {g['n_violating_records_with_a_persisted_prob_gap']}/"
          f"{v['n_violations_persisted']} violating records; "
          f"|gap|>1 impossible={g['n_impossible_abs_gap_gt_1']} "
          f"max|gap|={g['all_records']['max_abs_gap']}")
    print(f"  mean|gap| all={g['all_records']['mean_abs_gap']} "
          f"violating={g['violating_cohort']['mean_abs_gap']} "
          f"clean={g['clean_cohort']['mean_abs_gap']} "
          f"(headline excess over clean = "
          f"{g['frac_of_headline_mean_that_is_excess_over_clean_cohort']})")
    print(f"econ_prints join on the violating cohort: frac_joined={j['frac_joined']} "
          f"median_age_h={j['median_age_hours']} "
          f"exact_reconstruction={j['reconstruction']['frac_exact']}")
    for k, val in j["freshness_ladder"].items():
        print(f"    {k:<14} n={val['n']:<6} frac={val['frac']}")
    print(f"under-sampled days (0 flags, econ ladder inverted): "
          f"{rep['temporal']['days_with_zero_flags_but_a_nonzero_econ_inversion_rate']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

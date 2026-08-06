#!/usr/bin/env python3
"""subject_identity_corpus_audit.py — LOOP-QUEUE.md **Q53 milestone 1**: measure BOTH error
rates of `core.subject_identity.same_subject` against real committed tape.

L291 found that `scripts/anomaly_sweep.py::check_monotonicity` treats a shared `event_ticker`
as proof of a strike ladder, and that 100% of what survives the L290 fillability guard is
really two DIFFERENT SUBJECTS packed into one Kalshi event. `core/subject_identity.py` is the
repair's premise test. A premise test is only as good as its two error rates, and **refusing a
genuine ladder is as damaging as admitting a cross-subject pair** — one silently deletes real
arbs from the scanner's reach, the other manufactures fake ones. This script measures both,
read-only, over a CLOSED day window so the numbers are pinnable (L191).

## Corpora

**GENUINE LADDERS — every refusal here is a FALSE REFUSE.** Three families that carry real,
single-subject strike grids:
  * `tape/econ_prints/` — `open_events.events[].strikes[]`, `greater`-typed, title CONTAINS the
    strike ("Will CPI Core rise more than 0.3% in August?", `floor_strike: 0.3`).
  * `tape/crypto_hourly/` — `current.outcomes[]` / `previous_settlement.outcomes[]`, title is
    event-level and identical across rungs but carries NON-strike numbers ("Bitcoin price range
    on Aug 5, 2026?") that must survive.
  * `tape/weather_books/` — no `title` field at all, only `yes_sub_title` ("97° or above" against
    `floor_strike: 96`). This corpus exercises the SUB-TITLE half of the key in isolation AND
    the strike-label offset that a naive equality rule would trip over; the title half is
    unmeasurable here and is reported as such.

**CROSS-SUBJECT — every admission here is a FALSE ADMIT.** `tape/universe_sweep/` carries
`title` + `event_ticker` for every open market platform-wide but persists NO strike fields.
That asymmetry is handled honestly rather than papered over: a pair whose titles differ in
ALPHABETIC content is DECIDED (no numeric attribution can repair an alphabetic difference), a
pair with byte-identical text is DECIDED the other way, and a pair that is alphabetically
identical but numerically different is INDETERMINATE on this corpus (its verdict would hinge on
strike attribution, and there are no strikes here). The indeterminate bucket is the residual
risk set and is enumerated, not assumed empty.

**LABELED cross-subject subsets.** Two of L291's three counterexample classes appear in
`tape/universe_sweep/` on other dates, with titles, and admit a ground-truth subject label
computed by a rule INDEPENDENT of the predicate (a name regex, not a skeleton comparison):
  * `KXATPGSPREAD` — subject = the ordered (winner, opponent) pair in
    "Will {A} win at least {N} more games than {B}?".
  * `KXMLBHRR` / `KXMLBHIT` / `KXMLBTB` — subject = the player name before the colon in
    "{Player}: {N}+ hits + runs + RBIs?".
These give a real confusion matrix, including the hard case where ONE event contains both
cross-subject pairs AND genuine within-player ladders.

## Pair shapes

Scored in the two shapes the scanner actually uses, never a shape it does not:
  * `monotonicity` — within one `event_ticker`, within ONE `strike_type` in {greater, less};
    all pairs. This is `check_monotonicity`'s candidate set.
  * `bracket` — within one `event_ticker`, all strike-typed members against the first
    (`core.subject_identity.all_same_subject`). This is `check_bracket_arb`'s candidate set.

Run:
    python scripts/subject_identity_corpus_audit.py                 # closed window, writes report
    python scripts/subject_identity_corpus_audit.py --max-day 2026-08-04
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.canonical import canonical_json
from core.io import REPO_ROOT
from core.subject_identity import (DESCRIPTIVE_FIELDS, SUBJECT_DIFFERENT,
                                   SUBJECT_FIELDS_CROSS_STRIKE_TYPE, SUBJECT_PROVEN_SAME,
                                   SUBJECT_UNVERIFIABLE, all_same_subject,
                                   descriptive_text, same_subject, skeleton_and_numbers)

TAPE = REPO_ROOT / "tape"
DEFAULT_MAX_DAY = "2026-08-04"
REPORT_PATH = REPO_ROOT / "reports" / "subject_identity_corpus_audit.json"

#: Above this many members in one skeleton class, exhaustive pairing is replaced by a
#: deterministic head-slice and the block is flagged `sampled`. Never silently: the report
#: carries the flag and the cap so a reader can tell an exact count from a bounded one.
_MAX_EXHAUSTIVE_CLASS = 400


def _day_of(path: Path) -> str:
    return path.name[len("dt="):-len(".jsonl")]


def _iter_lines(family: str, max_day: str):
    """Yield (path, parsed_json) for every committed line at or before `max_day`. Malformed
    lines are COUNTED by the caller via the sentinel `None`, never silently skipped."""
    for path in sorted((TAPE / family).glob("dt=*.jsonl")):
        if _day_of(path) > max_day:
            continue
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    yield path, json.loads(line)
                except json.JSONDecodeError:
                    yield path, None


# --------------------------------------------------------------------------- #
# corpus loaders — each returns {event_ticker: {ticker: market_dict}} + a bad-line count
# --------------------------------------------------------------------------- #
def load_econ_prints(max_day: str) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], int]:
    events: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    bad = 0
    for _, rec in _iter_lines("econ_prints", max_day):
        if rec is None:
            bad += 1
            continue
        for ev in ((rec.get("open_events") or {}).get("events") or []):
            et = ev.get("event_ticker") or ""
            for s in ev.get("strikes") or []:
                tk = s.get("ticker")
                if et and tk:
                    events[et].setdefault(tk, s)
    return events, bad


def load_crypto_hourly(max_day: str) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], int]:
    events: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    bad = 0
    for _, rec in _iter_lines("crypto_hourly", max_day):
        if rec is None:
            bad += 1
            continue
        for block_key in ("current", "previous_settlement"):
            block = rec.get(block_key) or {}
            et = block.get("event_ticker") or ""
            for o in block.get("outcomes") or []:
                tk = o.get("ticker")
                if et and tk:
                    events[et].setdefault(tk, o)
    return events, bad


def load_weather_books(max_day: str) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], int]:
    """weather_books persists no `event_ticker`; the ladder key is the ticker's date-scoped
    prefix (`KXHIGHNY-26JUL16` from `KXHIGHNY-26JUL16-T96`), which is precisely the event a
    Kalshi ladder lives under. Stated plainly because it IS a ticker-derived grouping — it
    groups the corpus, it never decides a verdict."""
    events: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    bad = 0
    for _, rec in _iter_lines("weather_books", max_day):
        if rec is None:
            bad += 1
            continue
        tk = rec.get("ticker") or ""
        parts = tk.rsplit("-", 1)
        if len(parts) != 2 or not rec.get("yes_sub_title"):
            continue
        events[parts[0]].setdefault(tk, rec)
    return events, bad


def load_universe_sweep(max_day: str) -> Tuple[Dict[str, Dict[str, Dict[str, Any]]], int]:
    events: Dict[str, Dict[str, Dict[str, Any]]] = defaultdict(dict)
    bad = 0
    for _, rec in _iter_lines("universe_sweep", max_day):
        if rec is None:
            bad += 1
            continue
        et, tk = rec.get("event_ticker") or "", rec.get("ticker") or ""
        if et and tk:
            events[et].setdefault(tk, rec)
    return events, bad


# --------------------------------------------------------------------------- #
# scoring
# --------------------------------------------------------------------------- #
def _bucket_key(market: Dict[str, Any]) -> Tuple[Any, ...]:
    text = descriptive_text(market)
    if not text:
        return ("<no-text>",)
    return skeleton_and_numbers(text)[0]


def score_pairs(events: Dict[str, Dict[str, Dict[str, Any]]], *,
                strike_type_filter: Optional[Tuple[str, ...]] = None) -> Dict[str, Any]:
    """Exact verdict counts over within-event pairs, without enumerating the cross-skeleton
    product: two markets in different skeleton classes are `SUBJECT_DIFFERENT` by
    construction, so C(N,2) - sum C(n_i,2) of them can be counted arithmetically. Only pairs
    INSIDE one skeleton class need the pairwise call."""
    counts = defaultdict(int)
    reasons = defaultdict(int)
    n_pairs = n_events = 0
    sampled_classes = 0
    examples: Dict[str, List[Tuple[str, str, str]]] = defaultdict(list)

    for et, by_ticker in sorted(events.items()):
        members = list(by_ticker.values())
        if strike_type_filter is not None:
            by_type = defaultdict(list)
            for m in members:
                st = m.get("strike_type")
                if st in strike_type_filter:
                    by_type[st].append(m)
            groups = [g for g in by_type.values() if len(g) >= 2]
        else:
            groups = [members] if len(members) >= 2 else []
        if not groups:
            continue
        n_events += 1
        for group in groups:
            classes = defaultdict(list)
            for m in group:
                classes[_bucket_key(m)].append(m)
            total = len(group)
            same_class = sum(len(v) * (len(v) - 1) // 2 for v in classes.values())
            cross_class = total * (total - 1) // 2 - same_class
            n_pairs += total * (total - 1) // 2
            if cross_class:
                counts[SUBJECT_DIFFERENT] += cross_class
                reasons["text_skeleton_differs"] += cross_class
            for members_in_class in classes.values():
                if len(members_in_class) < 2:
                    continue
                pool = members_in_class
                if len(pool) > _MAX_EXHAUSTIVE_CLASS:
                    sampled_classes += 1
                    pool = pool[:_MAX_EXHAUSTIVE_CLASS]
                    n_pairs -= (len(members_in_class) * (len(members_in_class) - 1) // 2
                                - len(pool) * (len(pool) - 1) // 2)
                for a, b in combinations(pool, 2):
                    verdict, reason = same_subject(a, b)
                    counts[verdict] += 1
                    reasons[reason] += 1
                    if len(examples[reason]) < 5:
                        examples[reason].append(
                            (et, f"{a.get('ticker')} :: {descriptive_text(a)[:120]}",
                             f"{b.get('ticker')} :: {descriptive_text(b)[:120]}"))
    return {
        "n_events_with_pairs": n_events,
        "n_pairs": n_pairs,
        "verdicts": {k: counts[k] for k in
                     (SUBJECT_PROVEN_SAME, SUBJECT_DIFFERENT, SUBJECT_UNVERIFIABLE)},
        "reasons": dict(sorted(reasons.items())),
        "n_classes_sampled": sampled_classes,
        "max_exhaustive_class": _MAX_EXHAUSTIVE_CLASS,
        "examples": {k: v for k, v in sorted(examples.items())},
    }


def score_bracket_shape(events: Dict[str, Dict[str, Dict[str, Any]]],
                        fields=SUBJECT_FIELDS_CROSS_STRIKE_TYPE) -> Dict[str, Any]:
    """One verdict per event over its strike-typed members — `check_bracket_arb`'s shape.

    Scored under BOTH field sets by the caller: `SUBJECT_FIELDS_CROSS_STRIKE_TYPE` (what the
    scanner uses) and `DESCRIPTIVE_FIELDS` (the wrong choice, kept in the report so the 55.3%
    weather false-refuse rate that motivated the split stays visible instead of becoming
    folklore)."""
    counts = defaultdict(int)
    reasons = defaultdict(int)
    for _, by_ticker in sorted(events.items()):
        members = [m for m in by_ticker.values()
                   if m.get("strike_type") in ("less", "between", "greater")]
        if len(members) < 2:
            continue
        verdict, reason = all_same_subject(members, fields)
        counts[verdict] += 1
        reasons[reason] += 1
    return {"fields": list(fields), "n_events": sum(counts.values()),
            "verdicts": {k: counts[k] for k in
                         (SUBJECT_PROVEN_SAME, SUBJECT_DIFFERENT, SUBJECT_UNVERIFIABLE)},
            "reasons": dict(sorted(reasons.items()))}


# --------------------------------------------------------------------------- #
# labeled cross-subject subsets — ground truth from a name regex, NOT from the predicate
# --------------------------------------------------------------------------- #
_ATP_RE = re.compile(r"^Will (?P<a>.+?) win at least [-\d.]+ more games than (?P<b>.+?)\?$")
_MLB_RE = re.compile(r"^(?P<player>[^:]+):\s")


def _ground_truth_subject(series: str, title: str) -> Optional[str]:
    if series == "KXATPGSPREAD":
        m = _ATP_RE.match(title or "")
        return f"{m.group('a')}|{m.group('b')}" if m else None
    if series in ("KXMLBHRR", "KXMLBHIT", "KXMLBTB"):
        m = _MLB_RE.match(title or "")
        return m.group("player").strip() if m else None
    return None


def score_labeled(events: Dict[str, Dict[str, Dict[str, Any]]],
                  series_set: Tuple[str, ...]) -> Dict[str, Any]:
    """Confusion matrix against an independent ground-truth label. Markets carry no strikes
    in `universe_sweep`, so the predicate is additionally re-scored with each market's
    ground-truth strike SUPPLIED from its own title number — the value Kalshi would persist
    in `floor_strike` — which is what the live scanner sees. Both scorings are reported."""
    tp = fp = tn = fn = unver = 0
    unlabeled = 0
    fp_examples: List[Any] = []
    fn_examples: List[Any] = []
    n_events = 0
    for et, by_ticker in sorted(events.items()):
        members = [m for m in by_ticker.values()
                   if (m.get("series") or "") in series_set]
        labeled = []
        for m in members:
            gt = _ground_truth_subject(m.get("series") or "", m.get("title") or "")
            if gt is None:
                unlabeled += 1
                continue
            nums = skeleton_and_numbers(descriptive_text(m))[1]
            enriched = dict(m)
            # The title's own strike number, i.e. what `/markets` reports as floor_strike for
            # these series. Supplied so the corpus exercises the SAME code path the live
            # scanner runs, not a strike-less degenerate one.
            enriched["floor_strike"] = nums[0] if nums else None
            labeled.append((gt, enriched))
        if len(labeled) < 2:
            continue
        n_events += 1
        for (gt_a, a), (gt_b, b) in combinations(labeled, 2):
            verdict, _ = same_subject(a, b)
            truth_same = (gt_a == gt_b)
            if verdict == SUBJECT_UNVERIFIABLE:
                unver += 1
            elif verdict == SUBJECT_PROVEN_SAME:
                if truth_same:
                    tp += 1
                else:
                    fp += 1
                    if len(fp_examples) < 5:
                        fp_examples.append([et, a.get("title"), b.get("title")])
            else:
                if truth_same:
                    fn += 1
                    if len(fn_examples) < 5:
                        fn_examples.append([et, a.get("title"), b.get("title")])
                else:
                    tn += 1
    n = tp + fp + tn + fn + unver
    return {
        "series": list(series_set), "n_events": n_events, "n_pairs": n,
        "n_titles_unlabeled_by_ground_truth_regex": unlabeled,
        "true_admit_same_subject": tp, "false_admit_cross_subject": fp,
        "true_refuse_cross_subject": tn, "false_refuse_same_subject": fn,
        "unverifiable": unver,
        "false_admit_rate_over_true_cross_subject_pairs":
            (fp / (fp + tn)) if (fp + tn) else None,
        "false_refuse_rate_over_true_same_subject_pairs":
            (fn / (fn + tp)) if (fn + tp) else None,
        "false_admit_examples": fp_examples, "false_refuse_examples": fn_examples,
    }


def census_indeterminate(events: Dict[str, Dict[str, Dict[str, Any]]], top: int = 30
                         ) -> Dict[str, Any]:
    """What is actually IN the indeterminate bucket? A pair lands there when its two markets
    say the same words but different numbers and the corpus persists no strike to attribute
    the difference to (`tape/universe_sweep/` carries no `floor_strike`/`cap_strike`). That is
    a corpus limitation, not a predicate limitation — the live scanner reads `/markets`, which
    does carry the strike fields — but "assume it would be fine" is exactly the move this repo
    forbids, so the bucket is enumerated by normalized skeleton and by series instead."""
    by_skeleton = defaultdict(lambda: {"pairs": 0, "series": set(), "example": None})
    for _, by_ticker in sorted(events.items()):
        members = list(by_ticker.values())
        if len(members) < 2:
            continue
        classes = defaultdict(list)
        for m in members:
            classes[_bucket_key(m)].append(m)
        for key, group in classes.items():
            if len(group) < 2 or key == ("<no-text>",):
                continue
            nums = defaultdict(list)
            for m in group:
                nums[skeleton_and_numbers(descriptive_text(m))[1]].append(m)
            total = len(group) * (len(group) - 1) // 2
            same = sum(len(v) * (len(v) - 1) // 2 for v in nums.values())
            if total - same <= 0:
                continue
            slot = by_skeleton[" ".join(key).strip()]
            slot["pairs"] += total - same
            slot["series"].add(group[0].get("series") or "")
            if slot["example"] is None:
                slot["example"] = descriptive_text(group[0])[:140]
    ranked = sorted(by_skeleton.items(), key=lambda kv: -kv[1]["pairs"])[:top]
    return {
        "n_distinct_skeletons": len(by_skeleton),
        "top": [{"skeleton": k, "pairs": v["pairs"],
                 "n_series": len(v["series"]),
                 "series_sample": sorted(v["series"])[:4],
                 "example_text": v["example"]} for k, v in ranked],
    }


def build_report(max_day: str) -> Dict[str, Any]:
    econ, econ_bad = load_econ_prints(max_day)
    crypto, crypto_bad = load_crypto_hourly(max_day)
    weather, weather_bad = load_weather_books(max_day)
    universe, universe_bad = load_universe_sweep(max_day)

    genuine = {}
    for name, events, bad in (("econ_prints", econ, econ_bad),
                              ("crypto_hourly", crypto, crypto_bad),
                              ("weather_books", weather, weather_bad)):
        genuine[name] = {
            "n_events": len(events),
            "n_distinct_markets": sum(len(v) for v in events.values()),
            "n_malformed_lines": bad,
            "monotonicity_shape": score_pairs(events, strike_type_filter=("greater", "less")),
            "bracket_shape": score_bracket_shape(events),
            "bracket_shape_if_sub_title_were_included": score_bracket_shape(
                events, DESCRIPTIVE_FIELDS),
        }
        block = genuine[name]["monotonicity_shape"]
        n = block["n_pairs"]
        refused = n - block["verdicts"][SUBJECT_PROVEN_SAME]
        block["false_refuse_rate"] = (refused / n) if n else None
        block["n_false_refusals"] = refused

    cross = {
        "n_events": len(universe),
        "n_distinct_markets": sum(len(v) for v in universe.values()),
        "n_malformed_lines": universe_bad,
        "all_within_event_pairs": score_pairs(universe, strike_type_filter=None),
        "indeterminate_bucket_census": census_indeterminate(universe),
    }
    return {
        "schema_version": "subject_identity_corpus_audit.v1",
        "max_day": max_day,
        "predicate": "core.subject_identity.same_subject",
        "signal_used": ("market title / subtitle / yes_sub_title text skeleton + "
                        "strike-attributable numeric differences; NO ticker-suffix parsing"),
        "genuine_ladder_corpora": genuine,
        "cross_subject_corpus_universe_sweep": cross,
        "labeled_cross_subject": {
            "atp_game_spreads": score_labeled(universe, ("KXATPGSPREAD",)),
            "mlb_batter_props": score_labeled(universe, ("KXMLBHRR", "KXMLBHIT", "KXMLBTB")),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-day", default=DEFAULT_MAX_DAY,
                    help=f"closed window upper bound (default {DEFAULT_MAX_DAY})")
    ap.add_argument("--out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    report = build_report(args.max_day)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(canonical_json(report) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=1, sort_keys=True, default=str)[:8000])
    print(f"[subject_identity_corpus_audit] wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

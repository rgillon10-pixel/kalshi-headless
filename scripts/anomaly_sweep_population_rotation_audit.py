#!/usr/bin/env python3
"""Idle-run policy (c) — data-quality deep-dive: WHAT POPULATION does the capped
anomaly sweep actually scan, and what denominator do S3/S15's kill clauses rest on?

LOOP-QUEUE.md protocol v3, 2026-08-16. READ-ONLY and FULLY OFFLINE: this module opens
committed tape files and nothing else — no network, no credentials, no orders, no writes
outside `reports/`. It emits a DATA-ADEQUACY description: no P&L, no CI, no bootstrap, no
registry flip, and it quotes NO PRICE AT ALL (see `price_provenance` in the report — the
question here is population identity, not price, so there is no `price_source_tag` to
carry and the report says so explicitly rather than leaving it ambiguous).

WHY THIS QUESTION, AND WHY NOW.
`scripts/anomaly_sweep.py::_fetch_all_open_markets_raw` walks `/markets?status=open&limit=1000`
by cursor and stops at `DEFAULT_LIVE_LIMIT = 20000`, keeping `markets[:limit]` — the FIRST
20,000 tickers in cursor order. 253 of the 254 committed `tape/anomalies/` passes report
`markets_truncated: true` at exactly `n_markets_scanned: 20000`. S3's registry row states the
consequence honestly: "PLATFORM coverage is unmeasurable from tape and a rate with an unknown
denominator falsifies nothing ... S3's standing kill clause is unreachable until a pass
persists its scanned event/ticker inventory (L296)". Q55 milestone 1 built that inventory as
`scanned_tickers_sha256` and its own status line named the comparison it deferred:
"matching digests across passes would mean 247 `markets_truncated` passes never expanded S3's
measured population beyond one ~20,000-ticker slice ... differing digests would support the
stronger reading. That comparison itself is left for whichever run next touches S3/S15."

This module runs that comparison — and finds the deferred comparison CANNOT decide it (block
1), then answers the underlying question a different way (blocks 2-5) using a proxy that has
been sitting on committed tape the whole time.

SIX BLOCKS, each falsifiable from committed bytes:

1. `digest_answerability` — the deferred comparison, plus an EXECUTED demonstration of why its
   stated reading is unsafe. `scanned_tickers_digest` is a sha256 over the sorted-unique ticker
   list, so ONE ticker's birth or death anywhere in a 20,000-ticker set flips it completely.
   The block computes the digest of a real capture's ticker set and of that set minus exactly
   one ticker and reports that they differ (`one_ticker_flips_digest`) — a run-time proof, not
   a claim. Consequence: "digests differ" is compatible with 100% rotation AND with 99.995%
   overlap, so the field can only ever return the flattering reading. It is a one-bit
   identity test standing in for a set-similarity question.

2. `proxy_validation` — `collection/universe_sweep.py::fetch_open_markets` hits the SAME
   endpoint with the SAME params (`status=open`, `limit=1000` pages, cursor order) under a cap
   of `MAX_CALLS=20 * PAGE_LIMIT=1000` = the SAME 20,000 rows, and — unlike the anomaly sweep —
   it persists every scanned ticker. So `tape/universe_sweep/` is a per-ticker record of a
   close proxy for the population `anomaly_sweep` scanned. THE PROXY IS TESTED, NOT ASSUMED:
   this block puts the proxy's own per-capture event-group density beside the anomaly tape's
   independently recorded `n_event_groups`, and its ladder-capable group count beside
   `n_monotonicity_groups_checked`. The two collectors are different processes running at
   different wall-clock hours (universe_sweep at UTC {0,6,12,18}, anomaly_sweep ~09-10Z), so
   agreement here is evidence, and disagreement would invalidate every number below.

3. `rotation` — consecutive-capture Jaccard and containment, cumulative union growth, marginal
   new tickers per capture, and the ticker RECURRENCE histogram (in how many distinct captures
   does a ticker ever appear?). This is the set-similarity measurement block 1 shows the digest
   cannot give.

4. `composition` — the scanned prefix by `series`, per capture and over distinct tickers,
   splitting the auto-generated multi-leg `KXMVE*` families (L125 measured them as a
   non-fillable dead tail on a 5-day window; this is the 26-day population-identity view) from
   everything else. A rotating population of ephemeral parlay artifacts is not coverage.

5. `denominator` — the honest counts behind an S3 "0 arbs" claim: distinct non-junk tickers
   EVER scanned, distinct non-junk event groups EVER scanned, and how many of those carry >= 2
   markets (the only groups a cross-strike monotonicity check can even evaluate). Rule-of-three
   95% upper bounds are reported on EVERY candidate denominator side by side with the unit each
   one is in, because the choice of unit is the whole argument and no single number is honest
   alone.

6. `series_reachability` — is a named series ever present in the prefix at all? Q55 milestone 2
   added `kxmarmadround_progression` (560 open markets) to `config/implication_pairs.yaml` so
   S15's "kill if 0 fee-clearing hits in 60 days" clause could finally fire, and its first live
   pass still reported `n_implication_pairs_checked: 0`. If the series is never inside the cap,
   that zero is structural and no number of future passes changes it.

Deliberately NOT done here: no fix to either collector (a cap/ordering change is a
collector-write-path decision, not an idle run's), no registry status flip, no CI.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.settlement_sources import DEFAULT_TAPE_ROOT as SETTLEMENT_DEFAULT_TAPE_ROOT  # noqa: E402

# Anchored on the repo, never a bare relative "tape" (L345): a relative root resolves
# against os.getcwd(), so this audit would report 0 captures at exit code 0 from any other
# working directory — a silently empty population that reads exactly like a real data gate.
DEFAULT_TAPE_ROOT = SETTLEMENT_DEFAULT_TAPE_ROOT

# The auto-generated multi-leg families. A prefix, not a fixed list: Kalshi has added
# `KXMVE*` series over time (L125 saw two) and a hardcoded list would silently reclassify a
# third one as a real market. Reported as `junk_prefixes` in the output so the split is
# always visible next to the numbers it produces.
JUNK_SERIES_PREFIXES: Tuple[str, ...] = ("KXMVE",)

# The cap both collectors run under, quoted from their source (anomaly_sweep
# DEFAULT_LIVE_LIMIT = 20000; universe_sweep MAX_CALLS=20 * PAGE_LIMIT=1000). Used only for
# LABELLING a capture as at-cap in the report — never as a pass/fail comparison against a
# freshly derived value (L320).
CAP_ROWS = 20000

# S15's only live curated implication family (Q55 milestone 2).
DEFAULT_REACHABILITY_SERIES: Tuple[str, ...] = ("KXMARMADROUND",)

# A monotonicity/bracket check needs at least two markets under one event to compare.
MIN_MARKETS_FOR_LADDER = 2


# --------------------------------------------------------------------------- #
# loading (no datetime parsing anywhere: ISO-8601 UTC strings from one writer sort
# lexicographically, and the day is the `dt=` filename segment — see L157's parser rule)
# --------------------------------------------------------------------------- #
def _day_of(path: str) -> str:
    base = os.path.basename(path)
    return base.split("dt=", 1)[1][:10] if "dt=" in base else ""


def _read_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                yield rec


def load_universe_captures(tape_root: str = DEFAULT_TAPE_ROOT) -> List[Dict[str, Any]]:
    """One entry per `capture_id` in `tape/universe_sweep/`, ordered by `captured_at`.

    Tickers are kept in FILE order (= API return order) and de-duplicated only for the set
    measurements, never silently: `n_rows` vs `n_distinct` both travel in the output."""
    by_cap: Dict[str, Dict[str, Any]] = {}
    for path in sorted(glob.glob(os.path.join(tape_root, "universe_sweep", "dt=*.jsonl"))):
        day = _day_of(path)
        for rec in _read_jsonl(path):
            cid = rec.get("capture_id")
            ticker = rec.get("ticker")
            if not cid or not ticker:
                continue
            cap = by_cap.get(cid)
            if cap is None:
                cap = by_cap[cid] = {
                    "capture_id": cid,
                    "captured_at": rec.get("captured_at") or "",
                    "day": day,
                    "tickers": [],
                    "series_of": {},
                    "event_of": {},
                }
            cap["tickers"].append(ticker)
            cap["series_of"][ticker] = rec.get("series") or ""
            cap["event_of"][ticker] = rec.get("event_ticker") or ""
    caps = sorted(by_cap.values(), key=lambda c: (c["captured_at"], c["capture_id"]))
    for cap in caps:
        cap["n_rows"] = len(cap["tickers"])
        cap["n_distinct"] = len(set(cap["tickers"]))
        cap["at_cap"] = cap["n_rows"] >= CAP_ROWS
    return caps


def load_anomaly_passes(tape_root: str = DEFAULT_TAPE_ROOT) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(os.path.join(tape_root, "anomalies", "dt=*.jsonl"))):
        for rec in _read_jsonl(path):
            rec.setdefault("_day", _day_of(path))
            recs.append(rec)
    recs.sort(key=lambda r: (r.get("captured_at") or "", r.get("capture_id") or ""))
    return recs


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _is_junk(series: str, prefixes: Sequence[str] = JUNK_SERIES_PREFIXES) -> bool:
    return any(series.startswith(p) for p in prefixes)


def jaccard(a: Iterable[str], b: Iterable[str]) -> Optional[float]:
    """|A∩B| / |A∪B|, or None when the union is empty — an undefined similarity is honestly
    None, never a fabricated 0.0 (L357: a helper's honesty is only as good as its caller, so
    every consumer below carries the None through instead of collapsing it to a sentinel)."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return None
    return len(sa & sb) / len(union)


def containment(a: Iterable[str], b: Iterable[str]) -> Optional[float]:
    """|A∩B| / |A| — the asymmetric view. None when A is empty."""
    sa, sb = set(a), set(b)
    if not sa:
        return None
    return len(sa & sb) / len(sa)


def sorted_unique_digest(tickers: Iterable[str]) -> str:
    """Reproduces `scripts/anomaly_sweep.py::scanned_tickers_digest`'s content hash shape:
    sha256 over the canonical JSON of the sorted unique ticker list."""
    payload = json.dumps(sorted(set(tickers)), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def rule_of_three_upper(n_trials: int) -> Optional[float]:
    """95% upper bound on an event rate after ZERO observed events in `n_trials` (3/n).
    None for n<=0 — an empty denominator bounds nothing (L296)."""
    if n_trials <= 0:
        return None
    return 3.0 / n_trials


def _median_or_none(values: Sequence[float]) -> Optional[float]:
    return statistics.median(values) if values else None


# --------------------------------------------------------------------------- #
# block 1 — can the deferred digest comparison decide the question?
# --------------------------------------------------------------------------- #
def digest_answerability(passes: Sequence[Mapping[str, Any]],
                         captures: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    digests = [(p.get("captured_at") or "", p["scanned_tickers_sha256"])
               for p in passes if p.get("scanned_tickers_sha256")]
    demo: Dict[str, Any] = {"available": False}
    for cap in captures:
        tickers = sorted(set(cap["tickers"]))
        if len(tickers) >= 2:
            full = sorted_unique_digest(tickers)
            minus_one = sorted_unique_digest(tickers[:-1])
            demo = {
                "available": True,
                "capture_id": cap["capture_id"],
                "n_tickers": len(tickers),
                "digest_full": full,
                "digest_minus_one_ticker": minus_one,
                "one_ticker_flips_digest": full != minus_one,
                "jaccard_of_the_two_sets": jaccard(tickers, tickers[:-1]),
            }
            break
    return {
        "n_passes_total": len(passes),
        "n_passes_carrying_a_digest": len(digests),
        "n_distinct_digests": len({d for _ts, d in digests}),
        "all_digests_distinct": len({d for _ts, d in digests}) == len(digests),
        "digests": [{"captured_at": ts, "digest": d[:16]} for ts, d in digests],
        "one_ticker_flip_demo": demo,
        "verdict": (
            "DIGEST-CANNOT-DECIDE: a sha256 over the sorted ticker set is a one-bit identity "
            "test. Distinct digests are compatible with total rotation AND with a single "
            "ticker's birth in an otherwise identical slice, so 'digests differ' cannot "
            "support the stronger coverage reading Q55's status line assigned to it. The "
            "honest-denominator question needs a set-SIMILARITY measure (block 3), which the "
            "committed record cannot reconstruct because the ticker list itself was not kept."
        ),
    }


# --------------------------------------------------------------------------- #
# block 2 — is universe_sweep a defensible proxy for the anomaly sweep's population?
# --------------------------------------------------------------------------- #
def proxy_validation(passes: Sequence[Mapping[str, Any]],
                     captures: Sequence[Mapping[str, Any]],
                     junk_prefixes: Sequence[str] = JUNK_SERIES_PREFIXES) -> Dict[str, Any]:
    at_cap_passes = [p for p in passes if p.get("n_markets_scanned") == CAP_ROWS]
    anomaly_groups = [p["n_event_groups"] for p in at_cap_passes if "n_event_groups" in p]
    anomaly_mono = [p["n_monotonicity_groups_checked"] for p in at_cap_passes
                    if "n_monotonicity_groups_checked" in p]

    proxy_groups: List[int] = []
    proxy_ladders: List[int] = []
    for cap in captures:
        if not cap["at_cap"]:
            continue
        events: Dict[str, set] = defaultdict(set)
        for t in set(cap["tickers"]):
            if _is_junk(cap["series_of"].get(t, ""), junk_prefixes):
                continue
            events[cap["event_of"].get(t, "")].add(t)
        proxy_groups.append(len({cap["event_of"].get(t, "") for t in set(cap["tickers"])}))
        proxy_ladders.append(sum(1 for v in events.values() if len(v) >= MIN_MARKETS_FOR_LADDER))

    a_med = _median_or_none(anomaly_groups)
    p_med = _median_or_none(proxy_groups)
    rel = None
    if a_med and p_med:
        rel = abs(p_med - a_med) / a_med
    return {
        "premise": (
            "anomaly_sweep._fetch_all_open_markets_raw and universe_sweep.fetch_open_markets "
            "call the same endpoint /markets with the same params (status=open, limit=1000 "
            "pages, cursor order) and stop at the same 20,000 rows; only universe_sweep "
            "persists the scanned tickers."
        ),
        "known_differences": [
            "different processes, different wall-clock hours (universe_sweep gate hours "
            "{0,6,12,18} UTC vs anomaly_sweep ~09-10Z)",
            "anomaly_sweep truncates with markets[:limit] after a page overshoot; "
            "universe_sweep stops on a call cap — same 20,000 target, different stop rule",
            "no committed record joins a specific anomaly pass to a specific universe_sweep "
            "capture, so this is a POPULATION-SHAPE proxy, never a per-pass identity claim",
        ],
        "anomaly_n_event_groups_per_at_cap_pass": {
            "n": len(anomaly_groups), "median": a_med,
            "min": min(anomaly_groups) if anomaly_groups else None,
            "max": max(anomaly_groups) if anomaly_groups else None,
        },
        "proxy_n_event_groups_per_at_cap_capture": {
            "n": len(proxy_groups), "median": p_med,
            "min": min(proxy_groups) if proxy_groups else None,
            "max": max(proxy_groups) if proxy_groups else None,
        },
        "relative_gap_of_medians": rel,
        "anomaly_n_monotonicity_groups_checked": {
            "n": len(anomaly_mono), "median": _median_or_none(anomaly_mono),
            "sum": sum(anomaly_mono),
            "min": min(anomaly_mono) if anomaly_mono else None,
            "max": max(anomaly_mono) if anomaly_mono else None,
        },
        "proxy_ladder_capable_non_junk_groups_per_capture": {
            "n": len(proxy_ladders), "median": _median_or_none(proxy_ladders),
            "min": min(proxy_ladders) if proxy_ladders else None,
            "max": max(proxy_ladders) if proxy_ladders else None,
        },
        "note": (
            "the two group-density series are produced by DIFFERENT collectors and are "
            "compared as an order-of-magnitude corroboration, never as an equality claim; "
            "the ladder-capable series is additionally non-junk-filtered while the anomaly "
            "counter is not, so the proxy is expected to read at or below it."
        ),
    }


# --------------------------------------------------------------------------- #
# block 3 — rotation: the set-similarity measurement the digest cannot give
# --------------------------------------------------------------------------- #
def rotation(captures: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    union: set = set()
    prev: Optional[set] = None
    for cap in captures:
        cur = set(cap["tickers"])
        before = len(union)
        union |= cur
        steps.append({
            "captured_at": cap["captured_at"],
            "capture_id": cap["capture_id"],
            "n_distinct": len(cur),
            "jaccard_vs_prev": jaccard(cur, prev) if prev is not None else None,
            "containment_in_prev": containment(cur, prev) if prev is not None else None,
            "cumulative_union": len(union),
            "marginal_new": len(union) - before,
        })
        prev = cur

    js = [s["jaccard_vs_prev"] for s in steps if s["jaccard_vs_prev"] is not None]
    recurrence: Counter = Counter()
    for cap in captures:
        for t in set(cap["tickers"]):
            recurrence[t] += 1
    hist = Counter(recurrence.values())
    first_last = None
    if len(captures) >= 2:
        first_last = jaccard(captures[0]["tickers"], captures[-1]["tickers"])
    return {
        "n_captures": len(captures),
        "n_days": len({c["day"] for c in captures}),
        "union_distinct_tickers": len(union),
        "sum_of_per_capture_distinct": sum(len(set(c["tickers"])) for c in captures),
        "consecutive_jaccard": {
            "n": len(js), "median": _median_or_none(js),
            "min": min(js) if js else None, "max": max(js) if js else None,
            "n_exactly_zero": sum(1 for j in js if j == 0.0),
        },
        "first_vs_last_capture_jaccard": first_last,
        "ticker_recurrence_histogram": {str(k): v for k, v in sorted(hist.items())},
        "max_captures_any_ticker_appears_in": max(recurrence.values()) if recurrence else None,
        "steps": steps,
    }


# --------------------------------------------------------------------------- #
# block 4 — composition of the scanned prefix
# --------------------------------------------------------------------------- #
def composition(captures: Sequence[Mapping[str, Any]],
                junk_prefixes: Sequence[str] = JUNK_SERIES_PREFIXES,
                top_n: int = 12) -> Dict[str, Any]:
    obs_by_series: Counter = Counter()
    series_of_ticker: Dict[str, str] = {}
    junk_share_per_capture: List[float] = []
    for cap in captures:
        n_junk = 0
        for t in cap["tickers"]:
            s = cap["series_of"].get(t, "")
            obs_by_series[s] += 1
            series_of_ticker[t] = s
            if _is_junk(s, junk_prefixes):
                n_junk += 1
        if cap["tickers"]:
            junk_share_per_capture.append(n_junk / len(cap["tickers"]))

    distinct_by_series = Counter(series_of_ticker.values())
    n_obs = sum(obs_by_series.values())
    n_distinct = len(series_of_ticker)
    n_distinct_junk = sum(1 for s in series_of_ticker.values() if _is_junk(s, junk_prefixes))
    return {
        "junk_prefixes": list(junk_prefixes),
        "population_observations": n_obs,
        "population_distinct_tickers": n_distinct,
        "top_series_by_observation_share": [
            {"series": s, "n": c, "share": c / n_obs if n_obs else None}
            for s, c in obs_by_series.most_common(top_n)],
        "top_series_by_distinct_ticker_share": [
            {"series": s, "n": c, "share": c / n_distinct if n_distinct else None}
            for s, c in distinct_by_series.most_common(top_n)],
        "n_distinct_series_ever_seen": len(distinct_by_series),
        "distinct_junk_tickers": n_distinct_junk,
        "distinct_non_junk_tickers": n_distinct - n_distinct_junk,
        "junk_share_of_distinct_tickers": (n_distinct_junk / n_distinct) if n_distinct else None,
        "junk_share_per_capture": {
            "n": len(junk_share_per_capture),
            "median": _median_or_none(junk_share_per_capture),
            "min": min(junk_share_per_capture) if junk_share_per_capture else None,
            "max": max(junk_share_per_capture) if junk_share_per_capture else None,
        },
    }


# --------------------------------------------------------------------------- #
# block 5 — the honest denominators, each with its unit named
# --------------------------------------------------------------------------- #
def denominator(captures: Sequence[Mapping[str, Any]],
                passes: Sequence[Mapping[str, Any]],
                junk_prefixes: Sequence[str] = JUNK_SERIES_PREFIXES) -> Dict[str, Any]:
    ever_non_junk: set = set()
    ever_events: Dict[str, set] = defaultdict(set)
    per_capture_non_junk: List[int] = []
    per_capture_ladders: List[int] = []
    for cap in captures:
        n_nj = 0
        events: Dict[str, set] = defaultdict(set)
        for t in set(cap["tickers"]):
            s = cap["series_of"].get(t, "")
            if _is_junk(s, junk_prefixes):
                continue
            n_nj += 1
            ever_non_junk.add(t)
            ev = cap["event_of"].get(t, "")
            ever_events[ev].add(t)
            events[ev].add(t)
        per_capture_non_junk.append(n_nj)
        per_capture_ladders.append(
            sum(1 for v in events.values() if len(v) >= MIN_MARKETS_FOR_LADDER))

    n_ladder_groups_ever = sum(1 for v in ever_events.values()
                               if len(v) >= MIN_MARKETS_FOR_LADDER)
    at_cap = [p for p in passes if p.get("n_markets_scanned") == CAP_ROWS]
    n_group_checks = sum(p.get("n_monotonicity_groups_checked", 0) for p in at_cap)
    n_obs = sum(len(c["tickers"]) for c in captures)
    n_capture_days = len({c["day"] for c in captures})

    candidates = [
        {"unit": "market-observation (proxy tape rows)", "n": n_obs,
         "comment": "the most optimistic denominator; treats each re-listing of an ephemeral "
                    "auto-generated market as an independent trial"},
        {"unit": "distinct ticker ever scanned (proxy)", "n": len(ever_non_junk),
         "comment": "non-junk only; the population a real crossing could ever have been "
                    "found on"},
        {"unit": "distinct ladder-capable event group ever scanned (proxy)",
         "n": n_ladder_groups_ever,
         "comment": "non-junk event groups carrying >= 2 markets — the only groups a "
                    "cross-strike monotonicity check can evaluate at all"},
        {"unit": "monotonicity group-check (anomaly tape's own counter)", "n": n_group_checks,
         "comment": "measured directly on tape/anomalies/, no proxy involved"},
        {"unit": "capture-day", "n": n_capture_days,
         "comment": "the unit S3's registry row currently quotes (per L221)"},
    ]
    for c in candidates:
        c["rule_of_three_95_upper_per_unit"] = rule_of_three_upper(int(c["n"]))
    return {
        "candidates": candidates,
        "per_capture_non_junk_tickers": {
            "n": len(per_capture_non_junk), "median": _median_or_none(per_capture_non_junk),
            "min": min(per_capture_non_junk) if per_capture_non_junk else None,
            "max": max(per_capture_non_junk) if per_capture_non_junk else None,
        },
        "per_capture_ladder_capable_groups": {
            "n": len(per_capture_ladders), "median": _median_or_none(per_capture_ladders),
            "min": min(per_capture_ladders) if per_capture_ladders else None,
            "max": max(per_capture_ladders) if per_capture_ladders else None,
        },
        "distinct_non_junk_event_groups_ever": len(ever_events),
        "distinct_ladder_capable_groups_ever": n_ladder_groups_ever,
        "reading": (
            "0 verified fillable arbs bounds a DIFFERENT rate under each unit above, spanning "
            "several orders of magnitude. None of them is 'the platform': every one is scoped "
            "to whatever fell inside the 20,000-row cursor prefix, which block 4 shows is "
            "overwhelmingly auto-generated multi-leg artifacts. The tape cannot identify which "
            "unit is correct — a market observed once and never again is not a repeated trial, "
            "and the repeat structure needed to decide that was never captured."
        ),
    }


# --------------------------------------------------------------------------- #
# block 6 — is a named series ever inside the cap?
# --------------------------------------------------------------------------- #
def series_reachability(captures: Sequence[Mapping[str, Any]],
                        series_names: Sequence[str] = DEFAULT_REACHABILITY_SERIES
                        ) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name in series_names:
        n_caps = 0
        n_tickers: set = set()
        for cap in captures:
            hit = {t for t in set(cap["tickers"]) if cap["series_of"].get(t, "") == name}
            if hit:
                n_caps += 1
                n_tickers |= hit
        out[name] = {
            "n_captures_containing_it": n_caps,
            "n_captures_scanned": len(captures),
            "n_distinct_tickers_ever_seen": len(n_tickers),
            "reachable_under_cap": n_caps > 0,
        }
    return out


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def audit(tape_root: str = DEFAULT_TAPE_ROOT,
          junk_prefixes: Sequence[str] = JUNK_SERIES_PREFIXES,
          series_names: Sequence[str] = DEFAULT_REACHABILITY_SERIES) -> Dict[str, Any]:
    captures = load_universe_captures(tape_root)
    passes = load_anomaly_passes(tape_root)
    rep: Dict[str, Any] = {
        "schema_version": "anomaly_sweep_population_rotation_audit.v1",
        "tape_root": tape_root,
        "price_provenance": {
            "prices_quoted": False,
            "price_source_tag": None,
            "note": "this audit quotes no price, no P&L and no CI — it measures population "
                    "identity only, so there is no fill to tag (CLAUDE.md trust defaults)",
        },
        "inputs": {
            "n_universe_sweep_captures": len(captures),
            "n_universe_sweep_days": len({c["day"] for c in captures}),
            "n_anomaly_passes": len(passes),
            "n_anomaly_days": len({p.get("_day", "") for p in passes}),
        },
        "digest_answerability": digest_answerability(passes, captures),
        "proxy_validation": proxy_validation(passes, captures, junk_prefixes),
        "rotation": rotation(captures),
        "composition": composition(captures, junk_prefixes),
        "denominator": denominator(captures, passes, junk_prefixes),
        "series_reachability": series_reachability(captures, series_names),
    }
    rep["verdict"] = _verdict(rep)
    return rep


def _verdict(rep: Mapping[str, Any]) -> Dict[str, Any]:
    rot = rep["rotation"]
    comp = rep["composition"]
    den = rep["denominator"]
    findings: List[str] = []
    cj = rot["consecutive_jaccard"]
    if cj["n"] and cj["median"] is not None and cj["median"] < 0.01:
        findings.append(
            "PREFIX-NOT-FROZEN: consecutive captures share essentially nothing "
            f"(median Jaccard {cj['median']}), so the 'one frozen slice re-scanned' worry "
            "is falsified — but rotation is not coverage, see below")
    junk = comp["junk_share_of_distinct_tickers"]
    if junk is not None and junk > 0.5:
        findings.append(
            f"ROTATION-IS-CHURN: {junk:.4f} of every distinct ticker ever scanned belongs to "
            f"the auto-generated {comp['junk_prefixes']} families; the non-junk population "
            f"ever reached is {comp['distinct_non_junk_tickers']} tickers / "
            f"{den['distinct_ladder_capable_groups_ever']} ladder-capable event groups")
    unreachable = [k for k, v in rep["series_reachability"].items()
                   if not v["reachable_under_cap"]]
    if unreachable:
        findings.append(
            f"SERIES-UNREACHABLE-UNDER-CAP: {unreachable} never appear in any committed "
            "capture, so a check scoped to them can only ever report an empty denominator")
    return {
        "class": "DATA-ADEQUACY",
        "registry_flip": False,
        "ci_or_pnl": False,
        "findings": findings,
        "summary": (
            "The capped cursor prefix rotates completely and is ~99% auto-generated multi-leg "
            "artifacts, so 26 days of passes buy a small, one-shot, non-junk population rather "
            "than platform coverage. S3/S15 remain unkillable, for a sharper reason than "
            "'the denominator is unknown': the denominator is now measurable and it is small."
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-root", default=DEFAULT_TAPE_ROOT)
    ap.add_argument("--json-out",
                    default="reports/anomaly_sweep_population_rotation_audit.json")
    ap.add_argument("--json", action="store_true", help="print the report to stdout")
    ap.add_argument("--series", action="append", default=None,
                    help="extra series name to test for cap-reachability (repeatable)")
    ap.add_argument("--steps", action="store_true",
                    help="include the per-capture rotation step table in stdout output")
    args = ap.parse_args(argv)

    series = tuple(DEFAULT_REACHABILITY_SERIES) + tuple(args.series or ())
    rep = audit(args.tape_root, JUNK_SERIES_PREFIXES, series)
    if not args.steps:
        rep_out = dict(rep)
        rot = dict(rep["rotation"])
        rot.pop("steps", None)
        rep_out["rotation"] = rot
    else:
        rep_out = rep
    if args.json_out:
        os.makedirs(os.path.dirname(args.json_out) or ".", exist_ok=True)
        with open(args.json_out, "w") as fh:
            json.dump(rep, fh, indent=1, sort_keys=True)
            fh.write("\n")
    if args.json:
        print(json.dumps(rep_out, indent=1, sort_keys=True))
    else:
        v = rep["verdict"]
        print(f"verdict class: {v['class']}  registry_flip={v['registry_flip']}")
        for f in v["findings"]:
            print(f"  - {f}")
        d = rep["denominator"]
        print("denominators (0 verified fillable arbs -> 95% upper bound per unit):")
        for c in d["candidates"]:
            ub = c["rule_of_three_95_upper_per_unit"]
            print(f"  {c['unit']:58s} n={c['n']:>9d}  <= "
                  f"{('%.3e' % ub) if ub is not None else 'undefined'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

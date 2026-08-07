#!/usr/bin/env python3
"""Data-quality deep-dive on `tape/sports_pairs/` (LOOP-QUEUE.md idle-run policy (c),
2026-08-07). READ-ONLY and FULLY OFFLINE: this module opens committed tape files and
nothing else -- no network, no credentials, no orders, no writes outside `reports/`. It
produces a DATA-ADEQUACY report, never a P&L, never a CI, never a registry flip.

Why this family, why now. `sports_pairs` is the repo's LARGEST tape family (35 canonical
`dt=*.jsonl` day-files, 147,264 lines as of 2026-08-07) and the substrate under every sports
strategy the project has ever run (S7/S11/S13/S22/S23/S24/S28/S29, and S79's continuation
lane). Its only dedicated finding is `findings/2026-07-19-sports-pairs-join-adequacy-dataquality.md`,
which measured a DIFFERENT question (can a synthetic fair anchor be joined to a real resting
book?) over the family's first 16 days and its `sports_pairs.v1` schema. The v2 schema, first
seen 2026-07-12T21:23:03Z, added `game_start` (Kalshi's `occurrence_datetime`) -- and only with
that field does the question this module asks become answerable at all:

    HOW CLOSE TO ITS OWN KICKOFF DOES THIS TAPE ACTUALLY OBSERVE A GAME?

Every near-close sports entry rule ("taker the book in the last hour", "rest a maker quote into
kickoff") is silently conditioned on the answer. L251 is the standing warning: an entry rule that
looks temporal can in fact be selecting on a collector artifact.

Four measurements, each falsifiable from committed bytes:

1. `close_proximity` -- per DISTINCT GAME (`event_ticker`), the gap between its LAST pre-kickoff
   capture and its own `game_start`. **Availability-corrected** (the L302 class): scored ONLY on
   games whose kickoff falls inside the v2 observation window `[first v2 capture, last capture]`.
   A game whose kickoff is still in the future has a terminal gap bounded by the tape's end, not
   by the collector -- pooling those inflates the median (uncorrected 216.1 min vs corrected
   155.7 min on the 2026-08-07 tree) and is exactly the availability bias this repo has already
   been bitten by once.
2. `cadence_null` -- the falsifiable null for (1). If a game were captured on every family pass
   until kickoff, its terminal gap would be ~U(0, C) for C = the family's own local cadence, and
   near-close availability would be ~min(1, 60/C). Reported as predicted-vs-observed so the null
   can be REJECTED by the number rather than argued away.
3. `pre_kickoff_dropout` -- the non-inferential version of (2). A game is PROVABLY dropped when at
   least one family pass that DID capture the same `series` ran strictly between the game's last
   observation and its kickoff, and that pass does not contain the game. This does not infer from a
   distribution; it names the passes. The kickoff-minus-first-missed-pass lead is reported as a
   LOWER BOUND on the drop lead (the true drop instant lies between the last observation and the
   first missed pass -- the tape cannot resolve it finer than its own cadence).
   Two admissible causes, and this module does NOT claim to separate them: the event left
   `/markets?status=open` (`collection.sports_pairs._fetch_open_markets_raw` queries `status=open`
   ONLY), or its group stopped satisfying `is_moneyline_group`. What IS excluded by measurement is
   the hollow-book cause: `run()` appends a record for every confirmed group unconditionally, and
   `completeness_ok` is True on 100% of committed records.
4. `field_hazards` -- schema-version split (v1 carries NO `game_start`, so measurement (1) is
   structurally unanswerable on that share of the family), the `game_date`-vs-`game_start` calendar
   offset (a join hazard: `game_date` is parsed out of the TICKER, `game_start` is Kalshi's UTC
   `occurrence_datetime`, and they disagree by a full day on a large minority of records), the
   `odds_leg.status` census (the S7/S11 sharp-odds anchor), and the `price_source_tag` census.

Byte-identical duplicate lines are deduplicated before scoring and reported separately; the
family's known 228-row duplicate (`dt=2026-07-28`, pass `20260728T065420Z`) is already recorded in
`findings/2026-08-05-duplicate-tape-line-census-l282-attribution-falsified.md` (L285) and is NOT
re-attributed here.

Run:
    python3 scripts/sports_pairs_close_proximity_audit.py
    python3 scripts/sports_pairs_close_proximity_audit.py --tape-dir tape/sports_pairs --json-out reports/x.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.timeutil import parse_iso_utc  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TAPE_DIR = REPO_ROOT / "tape" / "sports_pairs"
REPORT_PATH = REPO_ROOT / "reports" / "sports_pairs_close_proximity_audit.json"

V2 = "sports_pairs.v2"
#: minutes-before-kickoff buckets the report always emits
PROXIMITY_THRESHOLDS_MIN: Tuple[int, ...] = (5, 15, 30, 60, 120, 180, 360, 720)
#: the headline "near-close" bucket every sports entry rule cares about
NEAR_CLOSE_MIN = 60
#: local-cadence estimation window before kickoff, and the minimum passes needed to estimate it
CADENCE_LOOKBACK_HOURS = 12
MIN_PASSES_FOR_CADENCE = 3


# --------------------------------------------------------------------------- #
# loading (L25 file-shape gating: canonical `dt=YYYY-MM-DD.jsonl` only)
# --------------------------------------------------------------------------- #
def canonical_day_files(tape_dir: Path) -> List[Path]:
    return sorted(p for p in Path(tape_dir).glob("dt=*.jsonl") if p.is_file())


def non_canonical_entries(tape_dir: Path) -> List[str]:
    """Anything in the family dir that is NOT a canonical day-file -- the L25 debris class.
    Reported, never silently swept into the denominator."""
    out = []
    for p in sorted(Path(tape_dir).iterdir()):
        if p.name.startswith("dt=") and p.name.endswith(".jsonl") and p.is_file():
            continue
        out.append(p.name + ("/" if p.is_dir() else ""))
    return out


def load_records(tape_dir: Path) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Parse canonical day-files. Returns (deduplicated records, load diagnostics)."""
    records: List[Dict[str, Any]] = []
    n_lines = 0
    n_invalid = 0
    dup_by_day: Dict[str, int] = {}
    for path in canonical_day_files(tape_dir):
        seen: set = set()
        dups = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s:
                continue
            n_lines += 1
            h = hashlib.sha1(s.encode("utf-8")).hexdigest()
            if h in seen:
                dups += 1
                continue
            seen.add(h)
            try:
                records.append(json.loads(s))
            except Exception:
                n_invalid += 1
        if dups:
            dup_by_day[path.name] = dups
    diag = {
        "n_day_files": len(canonical_day_files(tape_dir)),
        "n_lines_read": n_lines,
        "n_json_invalid": n_invalid,
        "n_duplicate_lines_dropped": sum(dup_by_day.values()),
        "duplicate_lines_by_day_file": dict(sorted(dup_by_day.items())),
        "non_canonical_entries": non_canonical_entries(tape_dir),
    }
    return records, diag


# --------------------------------------------------------------------------- #
# indexing
# --------------------------------------------------------------------------- #
def pass_index(records: List[Dict[str, Any]]) -> List[Tuple[str, Any, frozenset]]:
    """Family passes, time-ordered: (capture_id, captured_at, series covered by that pass)."""
    ts: Dict[str, Any] = {}
    ser: Dict[str, set] = defaultdict(set)
    for r in records:
        cid = r.get("capture_id")
        if not cid:
            continue
        t = parse_iso_utc(r["captured_at"])
        if cid not in ts or t < ts[cid]:
            ts[cid] = t
        ser[cid].add(r.get("series"))
    return sorted(((c, ts[c], frozenset(ser[c])) for c in ts), key=lambda x: x[1])


def game_index(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """v2 games that publish a `game_start`, keyed by `event_ticker`."""
    games: Dict[str, Dict[str, Any]] = {}
    for r in records:
        if r.get("schema_version") != V2 or not r.get("game_start"):
            continue
        et = r.get("event_ticker")
        if not et:
            continue
        g = games.setdefault(et, {"game_start": parse_iso_utc(r["game_start"]),
                                  "series": r.get("series"), "captures": []})
        g["captures"].append(parse_iso_utc(r["captured_at"]))
    for g in games.values():
        g["captures"].sort()
    return games


def _pct(xs: List[float], q: float) -> Optional[float]:
    """Linear-interpolated percentile on a sorted list (no numpy dependency)."""
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * (q / 100.0)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


# --------------------------------------------------------------------------- #
# (1) close proximity, availability-corrected
# --------------------------------------------------------------------------- #
def reached_games(games: Dict[str, Dict[str, Any]],
                  window_end: Any = None) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """AVAILABILITY CORRECTION (L302 class): keep only games whose kickoff falls inside the v2
    observation window `[first v2 capture, window_end]`. A game whose kickoff is AFTER the
    family's last pass is RIGHT-CENSORED -- its terminal gap is at least (kickoff - tape_end)
    no matter how good the collector is, so scoring it measures the tape's end date, not the
    collector. Conversely `game_start <= window_end` guarantees at least one pass ran at or
    after kickoff, which is exactly the condition under which the terminal gap is uncensored.

    `window_end` defaults to the last v2 game capture; callers with the FULL pass index
    (including `sports_pairs.v1` records, which carry no `game_start` and so never enter
    `games`) should pass the family's true last pass instant instead."""
    if not games:
        return {}, {"window_start": None, "window_end": None, "n_all": 0, "n_reached": 0,
                    "n_excluded_kickoff_outside_window": 0}
    lo = min(g["captures"][0] for g in games.values())
    hi = window_end or max(g["captures"][-1] for g in games.values())
    keep = {k: g for k, g in games.items() if lo <= g["game_start"] <= hi}
    return keep, {"window_start": lo.isoformat(), "window_end": hi.isoformat(),
                  "n_all": len(games), "n_reached": len(keep),
                  "n_excluded_kickoff_outside_window": len(games) - len(keep)}


def close_proximity(reached: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    gaps: List[float] = []
    by_series: Dict[str, List[float]] = defaultdict(list)
    n_no_pre = 0
    n_any_post_kickoff = 0
    for g in reached.values():
        pre = [c for c in g["captures"] if c <= g["game_start"]]
        if any(c > g["game_start"] for c in g["captures"]):
            n_any_post_kickoff += 1
        if not pre:
            n_no_pre += 1
            continue
        gap = (g["game_start"] - max(pre)).total_seconds() / 60.0
        gaps.append(gap)
        by_series[g["series"]].append(gap)
    n = len(gaps)
    buckets = {
        f"le_{t}_min": {"n": sum(1 for x in gaps if x <= t),
                        "frac": round(sum(1 for x in gaps if x <= t) / n, 6) if n else None}
        for t in PROXIMITY_THRESHOLDS_MIN
    }
    series_rows = []
    for s, xs in sorted(by_series.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        series_rows.append({
            "series": s, "n_games": len(xs),
            "median_gap_min": round(_pct(xs, 50), 1),
            "n_le_near_close": sum(1 for x in xs if x <= NEAR_CLOSE_MIN),
        })
    return {
        "n_games_scored": n,
        "n_games_no_pre_kickoff_capture": n_no_pre,
        "n_games_with_post_kickoff_capture": n_any_post_kickoff,
        "terminal_gap_min_percentiles": {f"p{q}": (round(_pct(gaps, q), 1) if n else None)
                                         for q in (0, 5, 10, 25, 50, 75, 90, 95, 100)},
        "proximity_buckets": buckets,
        "near_close_min": NEAR_CLOSE_MIN,
        "by_series": series_rows,
    }


# --------------------------------------------------------------------------- #
# (2) the cadence null
# --------------------------------------------------------------------------- #
def cadence_null(reached: Dict[str, Dict[str, Any]],
                 passes: List[Tuple[str, Any, frozenset]]) -> Dict[str, Any]:
    """If a game were captured on EVERY pass until kickoff, its terminal gap would be ~U(0, C).
    Predicted near-close availability is then mean(min(1, NEAR_CLOSE_MIN / C)). Rejecting this
    null is what licenses measurement (3)."""
    ptimes = [t for _, t, _ in passes]
    ratios: List[float] = []
    cadences: List[float] = []
    obs_near = 0
    n = 0
    for g in reached.values():
        gs = g["game_start"]
        lo = gs - timedelta(hours=CADENCE_LOOKBACK_HOURS)
        local = [t for t in ptimes if lo <= t <= gs]
        if len(local) < MIN_PASSES_FOR_CADENCE:
            continue
        iv = sorted((local[i + 1] - local[i]).total_seconds() / 60.0 for i in range(len(local) - 1))
        c = _pct(iv, 50)
        if not c or c <= 0:
            continue
        pre = [x for x in g["captures"] if x <= gs]
        if not pre:
            continue
        gap = (gs - max(pre)).total_seconds() / 60.0
        n += 1
        cadences.append(c)
        ratios.append(gap / c)
        if gap <= NEAR_CLOSE_MIN:
            obs_near += 1
    if not n:
        return {"n_games_scored": 0, "null_rejected": None}
    pred = sum(min(1.0, NEAR_CLOSE_MIN / c) for c in cadences) / n
    obs = obs_near / n
    within = [r for r in ratios if r <= 1.0]
    return {
        "n_games_scored": n,
        "lookback_hours": CADENCE_LOOKBACK_HOURS,
        "local_cadence_min_percentiles": {f"p{q}": round(_pct(cadences, q), 1) for q in (25, 50, 75)},
        "gap_over_cadence_percentiles": {f"p{q}": round(_pct(ratios, q), 3) for q in (25, 50, 75, 90, 99, 100)},
        "frac_gap_within_one_cadence": round(len(within) / n, 6),
        "mean_ratio_within_one_cadence": round(sum(within) / len(within), 4) if within else None,
        "uniform_null_mean_ratio_reference": 0.5,
        "predicted_near_close_frac_under_null": round(pred, 6),
        "observed_near_close_frac": round(obs, 6),
        "shortfall_ratio": round(pred / obs, 4) if obs else None,
        "null_rejected": bool(obs < pred / 2.0),
    }


# --------------------------------------------------------------------------- #
# (3) provable pre-kickoff dropout
# --------------------------------------------------------------------------- #
def pre_kickoff_dropout(reached: Dict[str, Dict[str, Any]],
                        passes: List[Tuple[str, Any, frozenset]]) -> Dict[str, Any]:
    leads: List[float] = []
    missed_counts: List[int] = []
    n_dropped = 0
    n_cadence_only = 0
    examples: List[Dict[str, Any]] = []
    for et, g in sorted(reached.items()):
        gs = g["game_start"]
        pre = [c for c in g["captures"] if c <= gs]
        if not pre:
            continue
        last = max(pre)
        missed = [(cid, t) for cid, t, ser in passes if last < t <= gs and g["series"] in ser]
        if not missed:
            n_cadence_only += 1
            continue
        n_dropped += 1
        lead = (gs - missed[0][1]).total_seconds() / 60.0
        leads.append(lead)
        missed_counts.append(len(missed))
        if len(examples) < 5:
            examples.append({"event_ticker": et, "series": g["series"],
                             "game_start": gs.isoformat(),
                             "last_capture": last.isoformat(),
                             "first_missed_pass": missed[0][0],
                             "n_missed_passes": len(missed),
                             "drop_lead_lower_bound_min": round(lead, 1)})
    total = n_dropped + n_cadence_only
    return {
        "n_games_scored": total,
        "n_provably_dropped_pre_kickoff": n_dropped,
        "frac_provably_dropped": round(n_dropped / total, 6) if total else None,
        "n_cadence_limited_only": n_cadence_only,
        "drop_lead_lower_bound_min_percentiles": ({f"p{q}": round(_pct(leads, q), 1)
                                                   for q in (25, 50, 75, 90, 100)} if leads else {}),
        "missed_passes_per_dropped_game": ({"median": round(_pct(missed_counts, 50), 1),
                                            "p90": round(_pct(missed_counts, 90), 1),
                                            "max": max(missed_counts)} if missed_counts else {}),
        "examples": examples,
        "admissible_causes": [
            "event absent from /markets?status=open (collection.sports_pairs._fetch_open_markets_raw)",
            "group no longer satisfies collection.sports_pairs.is_moneyline_group",
        ],
        "excluded_cause_hollow_book": "run() appends a record per confirmed group unconditionally",
    }


# --------------------------------------------------------------------------- #
# (4) field hazards
# --------------------------------------------------------------------------- #
def field_hazards(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    schema = Counter(r.get("schema_version", "<none>") for r in records)
    odds = Counter()
    tags = Counter()
    offsets = Counter()
    mismatch_hours = Counter()
    n_dated = 0
    completeness = Counter()
    for r in records:
        ol = r.get("odds_leg")
        odds[(ol or {}).get("status", "<none>") if isinstance(ol, dict) else "<none>"] += 1
        completeness[bool(r.get("completeness_ok"))] += 1
        for o in r.get("outcomes") or []:
            tags[o.get("price_source_tag", "<untagged>")] += 1
        if r.get("schema_version") == V2 and r.get("game_start") and r.get("game_date"):
            n_dated += 1
            gs = parse_iso_utc(r["game_start"])
            d = (gs.date() - date.fromisoformat(r["game_date"])).days
            offsets[d] += 1
            if d != 0:
                mismatch_hours[gs.hour] += 1
    n_v1 = schema.get("sports_pairs.v1", 0)
    n_mismatch = sum(v for k, v in offsets.items() if k != 0)
    return {
        "schema_versions": dict(sorted(schema.items())),
        "frac_records_without_game_start": round(n_v1 / len(records), 6) if records else None,
        "odds_leg_status": dict(sorted(odds.items())),
        "n_odds_matched": odds.get("matched", 0),
        "frac_odds_matched": round(odds.get("matched", 0) / len(records), 6) if records else None,
        "price_source_tags": dict(sorted(tags.items())),
        "completeness_ok": {str(k): v for k, v in sorted(completeness.items())},
        "game_date_minus_game_start_utc_date_days": {str(k): v for k, v in sorted(offsets.items())},
        "n_game_date_disagrees_with_utc_kickoff_date": n_mismatch,
        "frac_game_date_disagrees": round(n_mismatch / n_dated, 6) if n_dated else None,
        "utc_hour_of_disagreeing_kickoffs": {str(k): v for k, v in sorted(mismatch_hours.items())},
    }


def capture_cadence(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_day: Dict[str, set] = defaultdict(set)
    for r in records:
        by_day[parse_iso_utc(r["captured_at"]).date().isoformat()].add(r.get("capture_id"))
    rows = {d: len(v) for d, v in sorted(by_day.items())}
    days = sorted(rows)
    recent = days[-7:]
    return {
        "passes_by_day": rows,
        "n_days": len(days),
        "peak_day": max(rows, key=lambda d: rows[d]) if rows else None,
        "peak_passes": max(rows.values()) if rows else None,
        "recent_7day_mean_passes": round(sum(rows[d] for d in recent) / len(recent), 2) if recent else None,
        "missing_calendar_days": [
            (date.fromisoformat(days[0]) + timedelta(days=i)).isoformat()
            for i in range((date.fromisoformat(days[-1]) - date.fromisoformat(days[0])).days + 1)
            if (date.fromisoformat(days[0]) + timedelta(days=i)).isoformat() not in rows
        ] if days else [],
    }


def build_report(tape_dir: Path = TAPE_DIR) -> Dict[str, Any]:
    records, diag = load_records(tape_dir)
    passes = pass_index(records)
    games = game_index(records)
    reached, window = reached_games(games, window_end=(passes[-1][1] if passes else None))
    return {
        "generated_by": "scripts/sports_pairs_close_proximity_audit.py",
        "tape_dir": str(tape_dir),
        "n_records": len(records),
        "load": diag,
        "n_passes": len(passes),
        "availability_window": window,
        "close_proximity": close_proximity(reached),
        "cadence_null": cadence_null(reached, passes),
        "pre_kickoff_dropout": pre_kickoff_dropout(reached, passes),
        "field_hazards": field_hazards(records),
        "capture_cadence": capture_cadence(records),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    rep = build_report(Path(args.tape_dir))
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)

    cp, cn, dr, fh, cc = (rep["close_proximity"], rep["cadence_null"],
                          rep["pre_kickoff_dropout"], rep["field_hazards"], rep["capture_cadence"])
    w = rep["availability_window"]
    print(f"[sports_pairs:proximity] n_records={rep['n_records']} n_passes={rep['n_passes']} "
          f"dup_lines_dropped={rep['load']['n_duplicate_lines_dropped']}")
    print(f"[sports_pairs:proximity] availability-corrected: {w['n_reached']}/{w['n_all']} v2 games "
          f"reached kickoff inside the window ({w['n_excluded_kickoff_outside_window']} excluded)")
    nc = cp["proximity_buckets"][f"le_{NEAR_CLOSE_MIN}_min"]
    print(f"[sports_pairs:proximity] terminal pre-kickoff gap median="
          f"{cp['terminal_gap_min_percentiles']['p50']} min; <={NEAR_CLOSE_MIN}m: "
          f"{nc['n']}/{cp['n_games_scored']} ({nc['frac']})")
    print(f"[sports_pairs:proximity] cadence null: predicted={cn['predicted_near_close_frac_under_null']} "
          f"observed={cn['observed_near_close_frac']} shortfall={cn['shortfall_ratio']}x "
          f"rejected={cn['null_rejected']}")
    print(f"[sports_pairs:proximity] provably dropped pre-kickoff: "
          f"{dr['n_provably_dropped_pre_kickoff']}/{dr['n_games_scored']} "
          f"({dr['frac_provably_dropped']}), lead lower-bound median="
          f"{dr['drop_lead_lower_bound_min_percentiles'].get('p50')} min")
    print(f"[sports_pairs:proximity] hazards: no-game_start frac={fh['frac_records_without_game_start']}, "
          f"odds matched={fh['n_odds_matched']} ({fh['frac_odds_matched']}), "
          f"game_date disagrees={fh['frac_game_date_disagrees']}")
    print(f"[sports_pairs:proximity] cadence: peak={cc['peak_passes']} passes/day on {cc['peak_day']}, "
          f"recent 7-day mean={cc['recent_7day_mean_passes']}, missing days={cc['missing_calendar_days']}")
    print(f"[sports_pairs:proximity] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

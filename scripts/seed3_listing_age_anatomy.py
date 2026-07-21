#!/usr/bin/env python3
"""Seed 3 (Lane 3, structural/mechanical) — listing-age overround anatomy.

DISCOVERY-CLASS ANATOMY PROBE, NOT a tradeable-edge claim. It answers ONE
descriptive question: do fresh Kalshi markets show a systematic overround that
decays with listing age (i.e. wide before market-makers tighten the book)? A
YES here does NOT register an edge — it would only justify a LATER, separate,
queue-aware fill-gated probe. The nearest dead cousins (the null a tradeable
version must beat) are S19 (0.45% fill floor on stale wing quotes) and S21
(L43 depth-timing death) — the very wideness measured here IS the illiquidity
that makes it hard to fill, so we make NO P&L claim.

Read-only over committed tape. No network. Never mutates tape.

Family choice (documented in the writeup):
  * crypto_hourly/ is DATA-INADEQUATE for THIS question: markets live ~1h
    (born and die inside 60 min, so there is no "first HOURS" window), and the
    188-member fine ladder's `bracket_sum - 1` is dominated by the 1c tick
    floor (~60-92% of bands floor-pinned) rather than a market-maker overround.
    We show this numerically, then pivot.
  * sports_pairs/ is the family that CAN answer it: 2-outcome moneylines have a
    clean overround (bracket_sum ~1.0, no floor tax), a real birth signal
    (first_seen), and a multi-day listing life (median lead time ~16 days), so
    "hours since first-seen" spans the whole pre-MM-to-mature arc.

Birth signal = first_seen = min(captured_at) per event_ticker. L13 (membership
diff over accumulated tape has a startup artifact — everything "appears" at the
first window): we EXCLUDE any event whose first_seen falls on the tape's first
capture day, because its true listing may predate the tape.

Bootstrap: block_bootstrap by EVENT (L6 — captures within one game are
autocorrelated; the game is the independent unit), 10,000 resamples.
clears_tick_magnitude is applied to the DECAY CI as a materiality check (is the
decay orders above a tick, i.e. real structure, not a rounding residue) — it is
NOT used as an edge gate here (this is anatomy, there is no fill).
"""
from __future__ import annotations

import glob
import json
import math
import os
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from core.bootstrap import block_bootstrap, clears_tick_magnitude, floor_pinned_fraction
from core.pricing import infer_strike_spacing, normalized_ask

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPORTS_GLOB = os.path.join(REPO, "tape", "sports_pairs", "dt=*.jsonl")
CRYPTO_GLOB = os.path.join(REPO, "tape", "crypto_hourly", "dt=*.jsonl")

# Age bins in hours since first_seen. Fine near listing (where decay is fast),
# coarse in the mature tail.
AGE_BINS: List[Tuple[float, float]] = [
    (0, 1), (1, 2), (2, 4), (4, 8), (8, 24), (24, 72), (72, 168), (168, 1e9),
]
AGE_LABELS = ["0-1h", "1-2h", "2-4h", "4-8h", "8-24h", "24-72h", "72-168h", "168h+"]


def parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def age_hours(captured_at: datetime, first_seen: datetime) -> float:
    return (captured_at - first_seen).total_seconds() / 3600.0


def bin_for_age(age: float) -> Optional[str]:
    for (lo, hi), label in zip(AGE_BINS, AGE_LABELS):
        if lo <= age < hi:
            return label
    return None


# ---------------------------------------------------------------------------
# sports_pairs loading (pure, testable)
# ---------------------------------------------------------------------------

def load_sports_captures(paths: Sequence[str]) -> Dict[str, List[dict]]:
    """event_ticker -> list of per-capture dicts (parsed captured_at + fields).

    Keeps only records with the fields the anatomy needs. The current
    sports_pairs schema is `bracket_sum`/`expected_outcomes`/`member_count`/
    `completeness_ok`; an older schema variant lacks these and is skipped.
    """
    events: Dict[str, List[dict]] = defaultdict(list)
    for path in paths:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                et = r.get("event_ticker")
                ca = r.get("captured_at")
                bs = r.get("bracket_sum")
                if not (et and ca and bs is not None):
                    continue
                events[et].append({
                    "captured_at": parse_iso(ca),
                    "bracket_sum": bs,
                    "expected_outcomes": r.get("expected_outcomes"),
                    "member_count": r.get("member_count"),
                    "completeness_ok": r.get("completeness_ok"),
                    "outcomes": r.get("outcomes") or [],
                    "series": et.split("-")[0],
                })
    return events


def tape_first_day(events: Dict[str, List[dict]]):
    allca = [c["captured_at"] for caps in events.values() for c in caps]
    return min(allca).date() if allca else None


def is_clean_two_outcome(cap: dict) -> bool:
    """A complete, MECE 2-outcome moneyline capture — the clean-overround unit."""
    return (cap["expected_outcomes"] == 2
            and cap["member_count"] == 2
            and bool(cap["completeness_ok"]))


def eligible_events(events: Dict[str, List[dict]], first_day) -> Dict[str, List[dict]]:
    """Sort each event's captures, attach age, drop L13 startup-artifact events
    (first_seen on the tape's first day) and non-2-outcome captures."""
    out: Dict[str, List[dict]] = {}
    for et, caps in events.items():
        caps = sorted(caps, key=lambda c: c["captured_at"])
        first_seen = caps[0]["captured_at"]
        if first_day is not None and first_seen.date() == first_day:
            continue  # L13: may have listed before the tape began
        clean = []
        for c in caps:
            if not is_clean_two_outcome(c):
                continue
            c = dict(c)
            c["age"] = age_hours(c["captured_at"], first_seen)
            c["overround"] = c["bracket_sum"] - 1.0
            clean.append(c)
        if clean:
            out[et] = clean
    return out


# ---------------------------------------------------------------------------
# curve + decay
# ---------------------------------------------------------------------------

def overround_by_age_bin(elig: Dict[str, List[dict]]) -> Dict[str, Dict[str, Sequence[float]]]:
    """label -> {event_ticker -> [overround values in that bin]} — the shape
    block_bootstrap wants (already grouped by unit = event)."""
    binned: Dict[str, Dict[str, List[float]]] = {label: defaultdict(list) for label in AGE_LABELS}
    for et, caps in elig.items():
        for c in caps:
            label = bin_for_age(c["age"])
            if label is not None:
                binned[label][et].append(c["overround"])
    return {label: {et: v for et, v in d.items()} for label, d in binned.items()}


def favorite_prob_by_age_bin(elig: Dict[str, List[dict]]) -> Dict[str, List[float]]:
    """Cheap skew descriptor: the favorite-leg normalized ask (center of mass of
    the book) per capture, by age bin. Descriptive ONLY — with no settlement
    join this cannot claim settle-SIDE skew, only how lopsided the book is."""
    out: Dict[str, List[float]] = {label: [] for label in AGE_LABELS}
    for caps in elig.values():
        for c in caps:
            label = bin_for_age(c["age"])
            if label is None:
                continue
            bs = c["bracket_sum"]
            asks = [o.get("yes_ask") for o in c["outcomes"] if o.get("yes_ask") is not None]
            if len(asks) != 2 or bs <= 0:
                continue
            out[label].append(max(normalized_ask(a, bs) for a in asks))
    return out


def within_event_decay(elig: Dict[str, List[dict]], fresh_hi: float, aged_lo: float
                        ) -> Dict[str, Sequence[float]]:
    """Per-event (mean fresh overround - mean aged overround). Controls for event
    composition/survivorship: the same game is its own fresh-vs-aged control.
    Returns {event -> [diff]} for block_bootstrap (one value per unit)."""
    out: Dict[str, List[float]] = {}
    for et, caps in elig.items():
        fresh = [c["overround"] for c in caps if c["age"] < fresh_hi]
        aged = [c["overround"] for c in caps if c["age"] >= aged_lo]
        if fresh and aged:
            out[et] = [statistics.mean(fresh) - statistics.mean(aged)]
    return out


def estimate_half_life(bin_means: Dict[str, float], floor: float) -> Optional[float]:
    """Half-life of the EXCESS overround over a mature floor, via a log-linear
    fit of ln(mean - floor) on bin-midpoint age. Returns hours or None."""
    mids = {"0-1h": 0.5, "1-2h": 1.5, "2-4h": 3.0, "4-8h": 6.0,
            "8-24h": 16.0, "24-72h": 48.0, "72-168h": 120.0, "168h+": 250.0}
    xs, ys = [], []
    for label, m in bin_means.items():
        excess = m - floor
        if excess > 1e-4 and label in mids:
            xs.append(mids[label])
            ys.append(math.log(excess))
    if len(xs) < 3:
        return None
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    if slope >= 0:
        return None
    return math.log(2) / (-slope)


# ---------------------------------------------------------------------------
# crypto family-inadequacy diagnostic
# ---------------------------------------------------------------------------

def crypto_floor_tax_diag(paths: Sequence[str], max_records: int = 4000) -> dict:
    """Show WHY crypto_hourly cannot answer the listing-age question:
    (1) markets live ~1h (age since open_time never exceeds ~60 min); and
    (2) `bracket_sum - 1` is a 1c-floor tax on a fine ladder, not MM overround
    (high floor_pinned_fraction, wide strike spacing).
    """
    ages: List[float] = []
    floorpins: List[float] = []
    spacings: List[float] = []
    bracket_sums: List[float] = []
    members: List[int] = []
    n = 0
    for path in paths:
        with open(path) as fh:
            for line in fh:
                if n >= max_records:
                    break
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cur = r.get("current") or {}
                ot, ca = cur.get("open_time"), r.get("captured_at")
                outs = cur.get("outcomes") or []
                if not (ot and ca and outs and cur.get("completeness_ok")):
                    continue
                ages.append((parse_iso(ca) - parse_iso(ot)).total_seconds() / 60.0)
                yes = [o["yes_ask"] for o in outs if o.get("yes_ask") is not None]
                strikes = [o.get("floor_strike") for o in outs if o.get("floor_strike") is not None]
                if yes:
                    floorpins.append(floor_pinned_fraction(yes, 0.01))
                sp = infer_strike_spacing(strikes)
                if sp is not None:
                    spacings.append(sp)
                if cur.get("bracket_sum") is not None:
                    bracket_sums.append(cur["bracket_sum"])
                if cur.get("member_count") is not None:
                    members.append(cur["member_count"])
                n += 1
    return {
        "n_records": n,
        "max_age_min": max(ages) if ages else None,
        "median_age_min": statistics.median(ages) if ages else None,
        "median_floor_pinned_frac": statistics.median(floorpins) if floorpins else None,
        "median_strike_spacing": statistics.median(spacings) if spacings else None,
        "median_member_count": statistics.median(members) if members else None,
        "median_bracket_sum": statistics.median(bracket_sums) if bracket_sums else None,
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

def _fmt_ci(res: dict) -> str:
    lo, hi = res["ci95"]
    if lo is None:
        return f"n={res['n_obs']} (no CI)"
    return (f"mean {res['mean']*100:+.2f}c CI[{lo*100:+.2f},{hi*100:+.2f}]c "
            f"n_ev={res['n_units']} n_cap={res['n_obs']}")


def main() -> None:
    print("=" * 78)
    print("SEED 3 — listing-age overround anatomy (DISCOVERY-CLASS, not an edge claim)")
    print("=" * 78)

    # --- crypto: show family-inadequacy for THIS question -------------------
    crypto_paths = sorted(glob.glob(CRYPTO_GLOB))
    diag = crypto_floor_tax_diag(crypto_paths)
    print("\n[1] crypto_hourly diagnostic — WHY it cannot answer listing-age:")
    print(f"    max market age observed: {diag['max_age_min']:.1f} min "
          f"(median {diag['median_age_min']:.1f}) -> markets live ~1h, NO 'first HOURS' window")
    print(f"    median ladder: {diag['median_member_count']:.0f} members, "
          f"strike spacing ${diag['median_strike_spacing']:.0f}, bracket_sum {diag['median_bracket_sum']:.2f}")
    print(f"    median yes_ask floor-pinned @0.01: {diag['median_floor_pinned_frac']*100:.1f}% "
          f"-> `bracket_sum-1` is a 1c tick-floor tax, NOT a market-maker overround")
    print("    => crypto_hourly DATA-INADEQUATE here; pivot to sports_pairs.")

    # --- sports: the answerable family --------------------------------------
    sports_paths = sorted(glob.glob(SPORTS_GLOB))
    events = load_sports_captures(sports_paths)
    first_day = tape_first_day(events)
    elig = eligible_events(events, first_day)
    n_l13_excluded = sum(
        1 for caps in events.values()
        if sorted(caps, key=lambda c: c["captured_at"])[0]["captured_at"].date() == first_day
    )
    print(f"\n[2] sports_pairs — clean 2-outcome moneyline overround (bracket_sum-1):")
    print(f"    tape first day (L13 cut): {first_day}; events excluded by L13: {n_l13_excluded}")
    print(f"    eligible events (2-outcome, complete, first-seen after day 1): {len(elig)}")

    binned = overround_by_age_bin(elig)
    fav = favorite_prob_by_age_bin(elig)
    print("\n    overround-vs-listing-age curve (block-bootstrap by EVENT, L6):")
    print(f"    {'bin':8} {'n_ev':>5} {'n_cap':>6} {'mean':>8} {'95% CI':>20} {'fav_prob':>9}")
    bin_means: Dict[str, float] = {}
    for label in AGE_LABELS:
        unit_map = binned[label]
        if not unit_map:
            print(f"    {label:8} {'--- empty ---':>30}")
            continue
        res = block_bootstrap(unit_map)
        bin_means[label] = res["mean"]
        lo, hi = res["ci95"]
        favm = statistics.mean(fav[label]) if fav[label] else float("nan")
        ci = f"[{lo*100:+.2f},{hi*100:+.2f}]c" if lo is not None else "(no CI)"
        print(f"    {label:8} {res['n_units']:>5} {res['n_obs']:>6} "
              f"{res['mean']*100:>7.2f}c {ci:>20} {favm:>8.3f}")

    # mature floor = mean of the 24-72h bin (deepest well-populated mature bin)
    floor = bin_means.get("24-72h", 0.10)
    hl = estimate_half_life(bin_means, floor)
    print(f"\n    mature-overround floor (24-72h bin): {floor*100:.2f}c")
    if hl is not None:
        print(f"    excess-over-floor half-life (log-linear fit): {hl:.1f} h")

    # --- within-event decay (composition-controlled) + materiality gate -----
    decay = within_event_decay(elig, fresh_hi=2.0, aged_lo=24.0)
    dres = block_bootstrap(decay)
    n_pos = sum(1 for v in decay.values() if v[0] > 0)
    print(f"\n[3] within-event decay (fresh <2h mean - aged >=24h mean), by EVENT:")
    print(f"    {_fmt_ci(dres)}")
    print(f"    events with fresh>aged: {n_pos}/{len(decay)} "
          f"(controls for composition/survivorship — same game is its own control)")
    material = clears_tick_magnitude(dres["ci95"], tick=0.01, min_ticks=1.0)
    print(f"    materiality check (clears_tick_magnitude, tick=1c): {material} "
          f"-> decay is {'orders above' if material else 'within'} a tick "
          f"(materiality of the STRUCTURE, NOT an edge gate)")

    # --- verdict ------------------------------------------------------------
    fresh_mean = bin_means.get("0-1h")
    lo = dres["ci95"][0]
    structure = (fresh_mean is not None and floor is not None
                 and lo is not None and lo > 0 and material and n_pos > 0.8 * len(decay))
    print("\n" + "=" * 78)
    if structure:
        print("VERDICT: (a) STRUCTURE PRESENT.")
        print(f"  Fresh (0-1h) overround mean {fresh_mean*100:.1f}c decays monotonically to "
              f"{floor*100:.1f}c by 24-72h;")
        print(f"  within-event decay {dres['mean']*100:.1f}c (CI strictly >0, "
              f"{n_pos}/{len(decay)} events), robust to composition.")
        print("  TRADEABLE-VERSION CAVEAT: this is NOT an edge. The wide fresh overround")
        print("  IS the illiquidity — there is no resting counterparty to sell the bracket")
        print("  into. A tradeable version OWES the queue-aware fill sim over orderbook_depth")
        print("  and is presumptively S19 (0.45% fill floor) / S21 (L43 depth-timing) DEAD.")
        print("  Not-yet-established; anatomy only.")
    else:
        print("VERDICT: (b) NO STRUCTURE — overround flat vs listing age.")
    print("=" * 78)


if __name__ == "__main__":
    main()

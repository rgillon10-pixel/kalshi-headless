#!/usr/bin/env python3
"""Q57b / S82 — the ANCHOR-WIDENING retest, executed as a sealed OUTCOME-BLIND census.

WHAT THIS IS
------------
LOOP-QUEUE.md Q57's own reopen condition names exactly two roads back in:

  (a) keep the `settlement_ledger` anchor at a 15-min flow window "once one more settled
      game lands" — a near-term data-adequacy wait;
  (b) "widen the entry anchor to `tape/q51_settlement_cache/` as its OWN pre-registered
      choice (not a post-hoc addition) at `sign_variation_admissible`'s real
      `min_exclusive_minority_units=2` floor."

This module executes (b), pre-registered BEFORE any outcome value is read and, in fact,
without ever reading one at all. It is OUTCOME-BLIND BY CONSTRUCTION: it imports
`settled_ticker_set` (which tickers settled binary — membership) and never `outcome_map`,
`binary_outcome` or `score_rows` (how they settled — value). `tests/` pins that by AST.

WHY OUTCOME-BLIND IS THE RIGHT CLASS, NOT A DODGE
--------------------------------------------------
Q57's binding gate (2) is a POPULATION gate: >= 10 independent game units (L41) and a
two-sided population (L312/L321). A CI computed on a population that fails those gates does
not measure the signal, and reading the outcome values anyway would burn the tape's
re-testability for the properly-powered retest that path (a) is waiting for. So the
falsifiable question this module answers is a population question, and the honest verdict
class is DATA-ADEQUACY, never P&L. No price is persisted by this module beyond the
`real_ask` entry asks it inherits from the Q57 probe's own outcome-blind candidate builder.

THE TWIN DISCIPLINE (L36/L102)
-------------------------------
Every signal/candidate/collapse rule is IMPORTED from `scripts.q57_s82_flow_fade_probe`, not
re-implemented. A copy would let the two specs drift silently, and the whole point of (b) is
that it changes exactly the anchor and nothing else. The ONLY thing this module adds is a
second close-time SOURCE and the reporting around it.

Run:
    python3 scripts/q57b_anchor_widening_census.py
Writes `reports/q57b_anchor_widening_census.json`. Exit 0 always (a verdict is not an error).
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))          # L266: direct-CLI invocation must work, not just -m

from core.bootstrap import sign_variation_admissible          # noqa: E402
from core.io import REPO_ROOT                                  # noqa: E402
from core.timeutil import parse_iso_utc                        # noqa: E402
from scripts.q57_s82_flow_fade_probe import (                  # noqa: E402
    DEPTH_TAPE,
    LEDGER_TAPE,
    SIDE_NO,
    SIDE_YES,
    TRADES_TAPE,
    collapse_to_games,
    entry_candidates,
    game_id_of,
    load_close_times,
    load_depth,
    load_prints,
    settled_ticker_set,
)

CACHE_TAPE = REPO_ROOT / "tape" / "q51_settlement_cache"
REPORT_PATH = REPO_ROOT / "reports" / "q57b_anchor_widening_census.json"

# --------------------------------------------------------------------------- #
# THE PRE-REGISTRATION. Sealed 2026-08-17, BEFORE any population was counted under it.
#
# Q57's reopen path (b) mandates TWO changes to the Q57 seal and no others. Both are
# recorded here with the direction of the change, because one of them is a STRENGTHENING and
# a reader must not mistake it for a relaxation:
#
#   D1 close_anchor : settlement_ledger.close_time
#                  -> UNION(settlement_ledger.close_time, q51_settlement_cache.close_time)
#      Direction: WIDENING of the anchored population. Mandated verbatim by Q57's reopen
#      condition (b). Precedence + aggregation rules are spelled out below and are
#      themselves pre-registered, because "the union" alone is under-specified.
#
#   D2 min_exclusive_minority_units : 1 -> 2
#      Direction: STRICTER. The Q57 probe used 1, which is BELOW
#      `core.bootstrap.sign_variation_admissible`'s own default of 2; Q57's verifier round
#      flagged that as an undisclosed relaxation. This restores the library default.
#
# EVERY OTHER CONSTANT IS INHERITED BYTE-FOR-BYTE FROM THE Q57 SEAL and is re-read from that
# module at import time rather than retyped, so a future edit to Q57's seal cannot leave this
# one silently stale.
# --------------------------------------------------------------------------- #
from scripts.q57_s82_flow_fade_probe import PREREGISTRATION as Q57_PREREG  # noqa: E402

PREREGISTRATION: Dict[str, object] = {
    "sealed_on": "2026-08-17",
    "strategy": "S82",
    "queue_item": "Q57b",
    "executes": "LOOP-QUEUE.md Q57 reopen path (b) — anchor widening",
    "verdict_class": "DATA-ADEQUACY (population). This module computes NO CI and reads NO "
                     "settlement result VALUE, by construction.",
    "inherits_seal": "scripts.q57_s82_flow_fade_probe.PREREGISTRATION",
    "inherited_sha256": None,          # filled below from the Q57 module's own seal
    # -- D1 ------------------------------------------------------------------
    "close_anchor": "UNION(settlement_ledger.close_time, q51_settlement_cache.close_time)",
    # A ticker present in BOTH families would need a tie-break. Which family wins is
    # pre-registered here rather than discovered: the LEDGER wins, because it is a
    # per-day append-only capture with an explicit `dt`, while the cache is a
    # re-fetched snapshot blob. (On the committed tape the two sets turn out to be
    # DISJOINT, so this rule is never exercised — reported, not assumed.)
    "anchor_precedence": "settlement_ledger wins on a ticker present in both",
    # Within the cache a ticker may carry SEVERAL distinct close_time strings across
    # capture files (L360/L361: Kalshi rewrites close_time EARLIER at settlement). Both
    # aggregation rules are pre-registered and BOTH are reported, because neither is
    # obviously right: `min` reproduces the Q57 probe's own rule, `max` is the
    # ex-ante-knowable value a trader could actually have seen.
    "cache_aggregation_rules_reported": ["min", "max"],
    "cache_aggregation_rule_primary": "min",   # identical semantics to the Q57 seal
    # -- D2 ------------------------------------------------------------------
    "min_exclusive_minority_units": 2,         # library default; Q57's probe used 1
    # -- inherited, unchanged ------------------------------------------------
    "unit": "game",
    "entry_instant_rule": Q57_PREREG["entry_instant_rule"],
    "max_entry_lag_minutes": Q57_PREREG["max_entry_lag_minutes"],
    "flow_window_minutes": Q57_PREREG["flow_window_minutes"],
    "min_abs_rho": Q57_PREREG["min_abs_rho"],
    "min_window_count": Q57_PREREG["min_window_count"],
    "entry_price_band": Q57_PREREG["entry_price_band"],
    "entry_price_source_tag": Q57_PREREG["entry_price_source_tag"],
    "direction": Q57_PREREG["direction"],
    "min_units": Q57_PREREG["min_units"],      # L41
    # -- the pre-registered SECONDARY question -------------------------------
    # A single cell that fails a population gate can be an artifact of the constants.
    # Q57's own run answered that with a 240-cell outcome-blind grid on the LEDGER anchor;
    # this repeats it on the UNION anchor. It reports population SHAPE only (unit counts,
    # side counts) and never a return, so it costs no multiplicity (L362).
    "grid_axes": {
        "flow_window_minutes": [15, 30, 45, 60, 90, 120, 180, 240],
        "max_entry_lag_minutes": [30, 60, 90, 120, 180, 240, 360, 720],
        "min_abs_rho": [0.10, 0.15, 0.20, 0.30, 0.40],
        "min_window_count": [0.0, 50.0, 100.0, 250.0],
    },
    # -- the pre-registered DISPOSITION rule, sealed before counting ----------
    "disposition_rule": (
        "PRIMARY = the inherited seal under the UNION anchor at min_exclusive_minority_units=2. "
        "If PRIMARY clears BOTH the L41 unit floor and the sign-variation floor -> Q57 path (b) "
        "is OPEN and a separate scoring run may compute the CI. If PRIMARY fails, the honest "
        "class is DATA-ADEQUACY and path (b) is CLOSED unless the grid shows a "
        "MECHANISM-FAITHFUL cell that clears both; a cell is mechanism-faithful ONLY if it "
        "keeps max_entry_lag_minutes <= the inherited 60, because the inherited seal's own "
        "justification for 60 is 'the depth collector's own cadence: the tightest lag that "
        "can be met by a once-an-hour capture'. A cell that clears the floors only by filling "
        "at a materially staler book has bought sign variation with mechanism, not with data."
    ),
}


def preregistration_sha256(spec: Optional[Dict[str, object]] = None) -> str:
    payload = json.dumps(spec if spec is not None else PREREGISTRATION,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


try:
    from scripts.q57_s82_flow_fade_probe import PREREG_SHA256 as Q57_SHA
    PREREGISTRATION["inherited_sha256"] = Q57_SHA
except Exception:                                   # pragma: no cover - defensive
    pass

PREREG_SHA256 = preregistration_sha256()

MIN_UNITS = int(PREREGISTRATION["min_units"])
MIN_MINORITY_UNITS = int(PREREGISTRATION["min_exclusive_minority_units"])
INHERITED_LAG_MINUTES = float(PREREGISTRATION["max_entry_lag_minutes"])
SIDES = (SIDE_YES, SIDE_NO)


# --------------------------------------------------------------------------- #
# D1: the second close-time source
# --------------------------------------------------------------------------- #
def load_cache_close_times(tickers: FrozenSet[str], tape_dir: Path = CACHE_TAPE
                           ) -> Tuple[Dict[str, Dict[str, str]], dict]:
    """ticker -> {capture_file: close_time_string}, restricted to `tickers`.

    Returns the RAW per-file strings rather than a single epoch, because the whole point of
    the L360/L361 exposure is that a ticker can carry several and collapsing them here would
    destroy the evidence this census exists to weigh."""
    per: Dict[str, Dict[str, str]] = defaultdict(dict)
    files: List[str] = []
    for path in sorted(Path(tape_dir).glob("*.json")):
        files.append(path.name)
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        markets = blob.get("markets") or {}
        if isinstance(markets, dict):
            items = list(markets.items())
        else:
            items = [((m or {}).get("ticker"), m) for m in markets]
        for tk, m in items:
            if not isinstance(m, dict):
                continue
            tk = tk or m.get("ticker")
            ct = m.get("close_time")
            if tk in tickers and ct:
                per[tk][path.name] = ct
    return dict(per), {"family": "q51_settlement_cache",
                       "files_read": files,
                       "n_tickers_with_close_time": len(per)}


def cache_close_epochs(per: Dict[str, Dict[str, str]], rule: str) -> Dict[str, float]:
    """Collapse the per-file strings to one epoch per ticker under `rule` ('min'|'max')."""
    if rule not in ("min", "max"):
        raise ValueError(f"unregistered aggregation rule: {rule!r}")
    agg = min if rule == "min" else max
    return {tk: agg(parse_iso_utc(v).timestamp() for v in d.values())
            for tk, d in per.items() if d}


def union_close_times(ledger: Dict[str, float], cache: Dict[str, float]
                      ) -> Tuple[Dict[str, float], dict]:
    """The D1 anchor. `anchor_precedence` is pre-registered: the LEDGER wins an overlap."""
    out = dict(cache)
    out.update(ledger)                      # ledger last => ledger wins (pre-registered)
    lk, ck = set(ledger), set(cache)
    return out, {
        "n_ledger_only": len(lk - ck),
        "n_cache_only": len(ck - lk),
        "n_both": len(lk & ck),
        "n_union": len(out),
        "precedence_rule_exercised": bool(lk & ck),
    }


# --------------------------------------------------------------------------- #
# F1: is the L360/L361 close_time rewrite BINDING on the entry instant?
# --------------------------------------------------------------------------- #
def anchor_rewrite_invariance(per: Dict[str, Dict[str, str]],
                              depth: Dict[str, List[dict]]) -> dict:
    """Q57 declared the anchor's ex-ante knowability UNVERIFIED. This MEASURES whether it
    matters: the entry instant is 'the last depth snapshot at or before close', so if the
    same snapshot is selected under the earliest and the latest recorded `close_time`, the
    rewrite cannot move any entry price and the look-ahead exposure is NON-BINDING on this
    population — regardless of how large the rewrite itself is."""
    rewritten = 0
    spreads_min: List[float] = []
    same = differs = no_snapshot = 0
    examples: List[dict] = []
    for tk, d in sorted(per.items()):
        eps = [parse_iso_utc(v).timestamp() for v in d.values()]
        lo, hi = min(eps), max(eps)
        if hi - lo > 0.5:
            rewritten += 1
            spreads_min.append((hi - lo) / 60.0)
        s_lo = [s for s in depth.get(tk, []) if s["ts"] <= lo]
        s_hi = [s for s in depth.get(tk, []) if s["ts"] <= hi]
        if not s_lo and not s_hi:
            no_snapshot += 1
            continue
        a = s_lo[-1]["ts"] if s_lo else None
        b = s_hi[-1]["ts"] if s_hi else None
        if a == b:
            same += 1
        else:
            differs += 1
            if len(examples) < 3:
                examples.append({"ticker": tk, "close_times": sorted(set(d.values()))})
    spreads_min.sort()

    def _q(xs: List[float], f: float) -> Optional[float]:
        return round(xs[min(len(xs) - 1, int(f * len(xs)))], 2) if xs else None

    return {
        "n_tickers": len(per),
        "n_close_time_rewritten": rewritten,
        "rewrite_spread_minutes": {"min": _q(spreads_min, 0.0), "p50": _q(spreads_min, 0.5),
                                   "max": (round(spreads_min[-1], 2) if spreads_min else None)},
        "entry_snapshot_identical_under_min_and_max_rule": same,
        "entry_snapshot_differs": differs,
        "n_without_any_pre_close_snapshot": no_snapshot,
        "rewrite_is_binding_on_entry_instant": differs > 0,
        "note": ("If `rewrite_is_binding_on_entry_instant` is False, Q57's declared anchor "
                 "look-ahead cannot have moved a single entry price on this population. That "
                 "does NOT make the anchor ex-ante knowable in general (L360/L361 stands); it "
                 "makes the exposure non-binding HERE, which is a narrower and checkable claim."),
    }


# --------------------------------------------------------------------------- #
# F3: WHY the widening does or does not add units — the entry-lag profile
# --------------------------------------------------------------------------- #
def entry_lag_profile(closes: Dict[str, float], depth: Dict[str, List[dict]],
                      label: str) -> dict:
    """Distribution of (close - last pre-close depth snapshot) in minutes.

    An anchor source only contributes a UNIT if some depth snapshot sits inside the lag
    budget. A source can therefore widen the CLOSE-TIME population by a lot and the
    DEPTH-COVERED population by nothing, which is the distinction this reports."""
    lags: List[float] = []
    no_snap = 0
    for tk, close in closes.items():
        snaps = [s for s in depth.get(tk, []) if s["ts"] <= close]
        if not snaps:
            no_snap += 1
            continue
        lags.append((close - snaps[-1]["ts"]) / 60.0)
    lags.sort()

    def _q(f: float) -> Optional[float]:
        return round(lags[min(len(lags) - 1, int(f * len(lags)))], 2) if lags else None

    return {
        "source": label,
        "n_tickers_with_close_time": len(closes),
        "n_without_pre_close_depth_snapshot": no_snap,
        "n_with_pre_close_depth_snapshot": len(lags),
        "entry_lag_minutes": {"p10": _q(0.10), "p50": _q(0.50), "p90": _q(0.90),
                              "max": (round(lags[-1], 2) if lags else None)},
        "n_within_inherited_lag_budget": sum(1 for x in lags if x <= INHERITED_LAG_MINUTES),
        "inherited_lag_budget_minutes": INHERITED_LAG_MINUTES,
    }


# --------------------------------------------------------------------------- #
# the census cell — population shape only, never a return
# --------------------------------------------------------------------------- #
def census_cell(prints: Dict[str, List[dict]], depth: Dict[str, List[dict]],
                closes: Dict[str, float], settled: FrozenSet[str], *,
                window_minutes: float, lag_minutes: float,
                min_abs_rho: float, min_window_count: float) -> dict:
    rows, drops = entry_candidates(prints, depth, closes,
                                   window_s=window_minutes * 60.0,
                                   min_abs_rho=min_abs_rho,
                                   min_window_count=min_window_count,
                                   max_entry_lag_s=lag_minutes * 60.0)
    games = [g for g in collapse_to_games(rows) if g["ticker"] in settled]
    sides: Dict[str, List[str]] = defaultdict(list)
    for g in games:
        sides[g["game"]].append(g["fade_side"])
    sv = sign_variation_admissible(sides,
                                   min_exclusive_minority_units=MIN_MINORITY_UNITS,
                                   sides=SIDES)
    per_side: Dict[str, int] = defaultdict(int)
    for g in games:
        per_side[g["fade_side"]] += 1
    n_units = len({g["game"] for g in games})
    return {
        "flow_window_minutes": window_minutes,
        "max_entry_lag_minutes": lag_minutes,
        "min_abs_rho": min_abs_rho,
        "min_window_count": min_window_count,
        "n_game_units": n_units,
        "units_per_side": dict(sorted(per_side.items())),
        "meets_unit_floor": n_units >= MIN_UNITS,
        "n_exclusive_minority_units": sv.get("minority_side_units_exclusive"),
        "sign_variation_admissible": bool(sv["admissible"]),
        "sign_variation_reasons": list(sv.get("reasons") or []),
        "admissible": bool(n_units >= MIN_UNITS and sv["admissible"]),
        "mechanism_faithful": lag_minutes <= INHERITED_LAG_MINUTES,
        "n_entries_pre_collapse": len(rows),
        "drops": dict(sorted(drops.items())),
    }


def preregistered_grid(prints, depth, closes, settled) -> dict:
    axes = PREREGISTRATION["grid_axes"]
    cells: List[dict] = []
    for w in axes["flow_window_minutes"]:                 # type: ignore[index]
        for lag in axes["max_entry_lag_minutes"]:         # type: ignore[index]
            for rho in axes["min_abs_rho"]:               # type: ignore[index]
                for cnt in axes["min_window_count"]:      # type: ignore[index]
                    c = census_cell(prints, depth, closes, settled,
                                    window_minutes=w, lag_minutes=lag,
                                    min_abs_rho=rho, min_window_count=cnt)
                    cells.append({k: c[k] for k in (
                        "flow_window_minutes", "max_entry_lag_minutes", "min_abs_rho",
                        "min_window_count", "n_game_units", "units_per_side",
                        "meets_unit_floor", "n_exclusive_minority_units",
                        "sign_variation_admissible", "admissible", "mechanism_faithful")})
    adm = [c for c in cells if c["admissible"]]
    faithful = [c for c in adm if c["mechanism_faithful"]]
    return {
        "n_cells": len(cells),
        "n_meeting_unit_floor": sum(1 for c in cells if c["meets_unit_floor"]),
        "n_admissible": len(adm),
        "n_admissible_and_mechanism_faithful": len(faithful),
        "admissible_min_lag_minutes": (min(c["max_entry_lag_minutes"] for c in adm)
                                       if adm else None),
        "admissible_windows_used": sorted({c["flow_window_minutes"] for c in adm}),
        "admissible_cells": adm,
        "mechanism_faithful_admissible_cells": faithful,
    }


# --------------------------------------------------------------------------- #
def run(trades_dir: Path = TRADES_TAPE, depth_dir: Path = DEPTH_TAPE,
        ledger_dir: Path = LEDGER_TAPE, cache_dir: Path = CACHE_TAPE) -> dict:
    prints = load_prints(trades_dir)
    tickers = frozenset(prints)
    depth = load_depth(tickers, depth_dir)
    ledger, ledger_distinct_max = load_close_times(tickers, ledger_dir)
    per, cache_info = load_cache_close_times(tickers, cache_dir)

    anchors: Dict[str, Dict[str, float]] = {"settlement_ledger_only": ledger}
    union_info: Dict[str, dict] = {}
    for rule in PREREGISTRATION["cache_aggregation_rules_reported"]:   # type: ignore[union-attr]
        cache_eps = cache_close_epochs(per, rule)
        u, info = union_close_times(ledger, cache_eps)
        anchors[f"union_cache_{rule}"] = u
        union_info[rule] = info
        anchors[f"cache_only_{rule}"] = cache_eps

    settled, settle_info = settled_ticker_set(sorted(tickers))
    primary_rule = str(PREREGISTRATION["cache_aggregation_rule_primary"])
    primary_anchor = anchors[f"union_cache_{primary_rule}"]

    def _primary_cell(closes: Dict[str, float]) -> dict:
        return census_cell(prints, depth, closes, settled,
                           window_minutes=float(PREREGISTRATION["flow_window_minutes"]),
                           lag_minutes=float(PREREGISTRATION["max_entry_lag_minutes"]),
                           min_abs_rho=float(PREREGISTRATION["min_abs_rho"]),
                           min_window_count=float(PREREGISTRATION["min_window_count"]))

    primary = _primary_cell(primary_anchor)
    baseline = _primary_cell(ledger)
    widening_is_a_noop = (primary["n_game_units"] == baseline["n_game_units"]
                          and primary["units_per_side"] == baseline["units_per_side"])

    grid = preregistered_grid(prints, depth, primary_anchor, settled)

    # Q57's OTHER reopen road, costed so the wait is quoted in the scarce arm rather than
    # guessed at. The coordinates are not chosen here — they are the ones Q57's own reopen
    # text names for path (a): the LEDGER anchor at a 15-minute flow window. Reported under
    # both anchors so the F1 no-op is visible at this cell too. Descriptive; it adds no
    # degree of freedom and does not enter the seal.
    path_a = {
        "coordinates_source": "LOOP-QUEUE.md Q57 reopen path (a): ledger anchor, 15-min window",
        "flow_window_minutes": 15,
        "max_entry_lag_minutes": float(PREREGISTRATION["max_entry_lag_minutes"]),
    }
    for label, closes in (("settlement_ledger_only", ledger),
                          (f"union_cache_{primary_rule}", primary_anchor)):
        c = census_cell(prints, depth, closes, settled,
                        window_minutes=15.0,
                        lag_minutes=float(PREREGISTRATION["max_entry_lag_minutes"]),
                        min_abs_rho=float(PREREGISTRATION["min_abs_rho"]),
                        min_window_count=float(PREREGISTRATION["min_window_count"]))
        path_a[label] = {k: c[k] for k in (
            "n_game_units", "units_per_side", "meets_unit_floor",
            "n_exclusive_minority_units", "sign_variation_admissible", "admissible")}
    path_a["units_short_of_L41_floor"] = max(
        0, MIN_UNITS - path_a["settlement_ledger_only"]["n_game_units"])
    path_a["minority_units_short_of_floor"] = max(
        0, MIN_MINORITY_UNITS
        - (path_a["settlement_ledger_only"]["n_exclusive_minority_units"] or 0))

    if primary["admissible"]:
        disposition = "PATH_B_OPEN"
    elif grid["n_admissible_and_mechanism_faithful"] > 0:
        disposition = "PATH_B_OPEN_VIA_MECHANISM_FAITHFUL_GRID_CELL"
    else:
        disposition = "PATH_B_CLOSED_DATA_ADEQUACY"

    report = {
        "schema": "q57b_anchor_widening_census.v1",
        "preregistration": PREREGISTRATION,
        "preregistration_sha256": PREREG_SHA256,
        "verdict_class": "DATA-ADEQUACY (population). No CI, no P&L, no outcome VALUE read.",
        "outcome_blind": True,
        "substrate": {
            "n_game_tickers": len(tickers),
            "n_games": len({game_id_of(t) for t in tickers}),
            "n_tickers_with_depth": len(depth),
            "n_ledger_close_times": len(ledger),
            "ledger_close_time_distinct_values_max": ledger_distinct_max,
            "cache": cache_info,
            "union": union_info,
            "settlement": settle_info,
            "n_settled_binary": len(settled),
        },
        "anchor_rewrite_invariance": anchor_rewrite_invariance(per, depth),
        "entry_lag_profile": {
            "settlement_ledger": entry_lag_profile(ledger, depth, "settlement_ledger"),
            "q51_settlement_cache": entry_lag_profile(
                cache_close_epochs(per, primary_rule), depth, "q51_settlement_cache"),
        },
        "primary": primary,
        "baseline_ledger_only": baseline,
        "widening_is_a_noop_at_the_sealed_spec": widening_is_a_noop,
        "grid": grid,
        "path_a_cost": path_a,
        "disposition": disposition,
        "disposition_rule": PREREGISTRATION["disposition_rule"],
    }
    return report


def main() -> int:
    rep = run()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
        fh.write("\n")
    p, b, g = rep["primary"], rep["baseline_ledger_only"], rep["grid"]
    print(f"Q57b anchor-widening census  prereg_sha256={PREREG_SHA256[:16]}…")
    print(f"  baseline (ledger only) : {b['n_game_units']:3d} units {b['units_per_side']}")
    print(f"  PRIMARY  (union anchor): {p['n_game_units']:3d} units {p['units_per_side']}  "
          f"admissible={p['admissible']}")
    print(f"  widening is a no-op at the sealed spec: {rep['widening_is_a_noop_at_the_sealed_spec']}")
    print(f"  grid: {g['n_cells']} cells, {g['n_meeting_unit_floor']} meet the unit floor, "
          f"{g['n_admissible']} also sign-varying, "
          f"{g['n_admissible_and_mechanism_faithful']} of those mechanism-faithful")
    print(f"  DISPOSITION: {rep['disposition']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Q57(b) / S82 - the cache-anchored retest the Q57 verifier round left open.

READ-ONLY, fully offline, no network, no order path. This is the reopen path Q57's own
newest status names verbatim:

    "(b) widens the entry anchor to `q51_settlement_cache` as its OWN pre-registered choice
     (not a post-hoc addition) at `sign_variation_admissible`'s real
     `min_exclusive_minority_units=2` floor."

WHY A SECOND MODULE AND NOT AN EDIT OF THE SEALED PROBE
-------------------------------------------------------
`scripts/q57_s82_flow_fade_probe.py` carries a SEALED pre-registration whose sha256 is
pinned by a test. Editing it to widen the anchor would break that seal and turn a spec
change into something indistinguishable from tuning. So the sealed probe is imported and
REUSED verbatim (L36/L102 - one site per rule: `game_id_of`, `load_prints`, `load_depth`,
`entry_candidates`, `collapse_to_games`, `outcome_map`, `score_rows`, the fee, the bands),
and only the two things Q57(b) authorises change, under a NEW seal of this module's own:

  DELTA 1 (the reopen condition): the close-time anchor is the UNION of
          `tape/settlement_ledger/` and `tape/q51_settlement_cache/`, not the ledger alone.
  DELTA 2 (the reopen condition): the sign-variation floor is
          `min_exclusive_minority_units = 2` - `core.bootstrap.sign_variation_admissible`'s
          REAL default. The sealed probe used 1, an undisclosed relaxation the verifier
          round caught.

Everything else is byte-identical to the sealed spec by construction: the entry price is a
`real_ask` from `tape/orderbook_depth/`, one Kalshi taker fee, hold to `broker_truth`
settlement, block-bootstrap by GAME, n_boot 10,000, seed 42, price band [0.02, 0.98].

THE CELLS, AND THE MULTIPLICITY THIS RUN OWNS UP TO
----------------------------------------------------
Two cells are scored, both sealed here BEFORE any outcome value was read:

  PRIMARY   `primary_minimal_change` - every constant of the sealed spec unchanged
            (window 120 min, max entry lag 60 min, |rho| >= 0.20, count floor 100); the ONLY
            differences from the sealed probe are DELTA 1 and DELTA 2. This is the verdict
            cell: it is the honest "change exactly one thing" reading of reopen path (b).

  SECONDARY `secondary_verifier_identified` - window 15 min, max entry lag 240 min. NOT
            independently derived: this is the exact cell the Q57 verifier round reported as
            clearing both floors under the cache anchor (12 GAME units, {no:10, yes:2}, 2
            exclusive-minority units). It is pre-registered here because Q57(b) asks for it
            by name, and it is DISCLOSED, not laundered: the cell was chosen after a search
            over the population - an OUTCOME-BLIND search (unit counts and side counts only,
            no return, no settlement value), but a search. A CI on it therefore carries
            selection exposure the primary does not, and it may never be quoted alone.

  DIAGNOSTIC `diagnostic_window_only` (window 15 min, lag 60 min) is reported
            POPULATION-ONLY, never scored, so the window-vs-lag attribution is visible
            without spending a third CI on it.

Scoring two cells is a multiplicity of 2 and is declared as such; neither cell may be
cherry-picked into a headline. The PRIMARY is the verdict cell regardless of outcome.

THE LOOK-AHEAD DIRECTION, RESTATED FOR THE WIDER ANCHOR (L360/L361)
--------------------------------------------------------------------
Kalshi REWRITES `close_time` at settlement, always EARLIER. The cache family is exactly
where that mutation is observable (the sealed probe's own cross-family audit found 48/60
tickers carrying more than one distinct `close_time`, one moving 14 days earlier). This
module keeps the sealed probe's aggregation rule - the MINIMUM observed close - and reports
the anchor delta rather than hiding it. `min` is the post-settlement (rewritten) value where
a rewrite happened, so the entry instant it produces is NOT provably ex-ante knowable. That
can only FLATTER the strategy, so it never softens a negative result; a POSITIVE result
would owe that check before any graduation, and the verdict note says so.

Run:
    python3 scripts/q57b_s82_cache_anchor_probe.py
Writes `reports/q57b_s82_cache_anchor.json`. Exit 0 always (a verdict is not an error).
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
    entry_instant_concentration,
    kish_effective_n,
    sign_variation_admissible,
)
from core.io import REPO_ROOT  # noqa: E402
from core.settlement_sources import DEFAULT_TAPE_ROOT  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts import q57_s82_flow_fade_probe as P  # noqa: E402

CACHE_GLOB = "tape/q51_settlement_cache/settlement*.json"
REPORT_PATH = REPO_ROOT / "reports" / "q57b_s82_cache_anchor.json"

# --------------------------------------------------------------------------- #
# THE PRE-REGISTRATION. Sealed 2026-08-17, BEFORE any outcome value was read.
# Changing any value changes PREREG_B_SHA256 and breaks the seal test - that
# failing test is the intended alarm, not a bug.
# --------------------------------------------------------------------------- #
PREREGISTRATION_B: Dict[str, object] = {
    "sealed_on": "2026-08-17",
    "strategy": "S82",
    "queue_item": "Q57(b)",
    "derives_from": "scripts/q57_s82_flow_fade_probe.py PREREGISTRATION",
    "close_anchor": "min of settlement_ledger and q51_settlement_cache close_time",
    "min_exclusive_minority_units": 2,
    "unit": "game",
    "entry_instant_rule": "last_orderbook_depth_snapshot_at_or_before_close",
    "flow_weight": "count",
    "flow_sign_convention": "+count when the taker BUYS yes, -count when taker buys no",
    "signal": "rho = net_signed_count / total_count over the window, on one ticker",
    "game_ticker_rule": "argmax abs(rho) over the game tickers; ties choose min ticker",
    "min_abs_rho": 0.20,
    "min_window_count": 100.0,
    "direction": "FADE",
    "entry_price_field": "best_no_ask if rho positive else best_yes_ask",
    "entry_price_source_tag": "real_ask",
    "entry_price_band": [0.02, 0.98],
    "exit": "hold_to_settlement",
    "fee_legs": 1,
    "fee_side": "taker",
    "min_units": 10,
    "n_boot": 10000,
    "seed": 42,
    "tick": 0.01,
    "min_ticks": 1.0,
    "scored_cells": [
        {"name": "primary_minimal_change", "flow_window_minutes": 120,
         "max_entry_lag_minutes": 60, "role": "verdict cell"},
        {"name": "secondary_verifier_identified", "flow_window_minutes": 15,
         "max_entry_lag_minutes": 240,
         "role": "disclosed selection exposure; never quoted alone"},
    ],
    "population_only_cells": [
        {"name": "diagnostic_window_only", "flow_window_minutes": 15,
         "max_entry_lag_minutes": 60, "role": "window-vs-lag attribution, never scored"},
    ],
    "multiplicity_scored_cells": 2,
}

MIN_MINORITY_UNITS_B = int(PREREGISTRATION_B["min_exclusive_minority_units"])
MIN_UNITS = int(PREREGISTRATION_B["min_units"])
N_BOOT = int(PREREGISTRATION_B["n_boot"])
SEED = int(PREREGISTRATION_B["seed"])
TICK = float(PREREGISTRATION_B["tick"])
MIN_TICKS = float(PREREGISTRATION_B["min_ticks"])


def preregistration_b_sha256(spec: Optional[Dict[str, object]] = None) -> str:
    payload = json.dumps(spec if spec is not None else PREREGISTRATION_B,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


PREREG_B_SHA256 = preregistration_b_sha256()


# --------------------------------------------------------------------------- #
# DELTA 1 - the widened anchor
# --------------------------------------------------------------------------- #
def load_close_times_union(tickers: FrozenSet[str],
                           ledger_dir: Path = P.LEDGER_TAPE,
                           root: Path = REPO_ROOT) -> Tuple[Dict[str, float], dict]:
    """ticker to min observed close epoch over BOTH families, plus a provenance audit.

    The audit is the point as much as the anchor: it reports how many tickers the cache
    ADDS (the whole reason path (b) exists), how many the two families DISAGREE on, and
    the signed size of that disagreement (L360/L361 - the rewrite is always earlier, so
    a disagreement is expected, not a bug)."""
    ledger: Dict[str, set] = defaultdict(set)
    for p in sorted(Path(ledger_dir).glob("dt=*.jsonl")):
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                tk = r.get("ticker")
                if tk in tickers and r.get("close_time"):
                    ledger[tk].add(r["close_time"])

    cache: Dict[str, set] = defaultdict(set)
    for path in sorted(glob.glob(str(Path(root) / CACHE_GLOB))):
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        markets = blob.get("markets") or {}
        items = markets.items() if isinstance(markets, dict) else (
            (m.get("ticker"), m) for m in markets)
        for tk, m in items:
            if not isinstance(m, dict):
                continue
            tk = tk or m.get("ticker")
            ct = m.get("close_time")
            if tk in tickers and ct:
                cache[tk].add(ct)

    def _min(vals) -> float:
        return min(parse_iso_utc(v).timestamp() for v in vals)

    keys = set(ledger) | set(cache)
    closes = {tk: _min(set(ledger.get(tk, set())) | set(cache.get(tk, set())))
              for tk in keys}

    both = sorted(set(ledger) & set(cache))
    deltas = []
    for tk in both:
        d = _min(cache[tk]) - _min(ledger[tk])
        if d != 0.0:
            deltas.append((tk, round(d / 60.0, 3)))
    all_vals = {tk: set(ledger.get(tk, set())) | set(cache.get(tk, set())) for tk in keys}
    audit = {
        "n_tickers_ledger": len(ledger),
        "n_tickers_cache": len(cache),
        "n_tickers_union": len(keys),
        "n_tickers_added_by_cache": len(set(cache) - set(ledger)),
        "n_tickers_in_both": len(both),
        "n_tickers_disagreeing": len(deltas),
        "disagreement_minutes_examples": sorted(deltas)[:5],
        "close_time_distinct_values_max": max((len(v) for v in all_vals.values()),
                                              default=0),
        "anchor_aggregation": ("min - the earliest observed close, i.e. the "
                               "POST-settlement value where a rewrite happened. See the "
                               "module docstring: this can only flatter a positive "
                               "result, never rescue a negative one."),
    }
    return closes, audit


# --------------------------------------------------------------------------- #
# DELTA 2 - the population gate at the real floor
# --------------------------------------------------------------------------- #
def population_gate(rows: Sequence[dict], settled: FrozenSet[str]) -> dict:
    """Adequacy WITHOUT any outcome value, at min_exclusive_minority_units = 2."""
    scoreable = [r for r in rows if r["ticker"] in settled]
    sides: Dict[str, List[str]] = defaultdict(list)
    for r in scoreable:
        sides[r["game"]].append(r["fade_side"])
    sv = sign_variation_admissible(sides,
                                   min_exclusive_minority_units=MIN_MINORITY_UNITS_B,
                                   sides=(P.SIDE_YES, P.SIDE_NO))
    conc = entry_instant_concentration([r["entry_captured_at"] for r in scoreable],
                                       unit_labels=[r["game"] for r in scoreable])
    n_units = len({r["game"] for r in scoreable})
    overrounds = [r["overround"] for r in scoreable if r["overround"] is not None]
    return {
        "n_entries_all": len(rows),
        "n_entries_scoreable": len(scoreable),
        "n_game_units": n_units,
        "min_units": MIN_UNITS,
        "meets_unit_floor": n_units >= MIN_UNITS,
        "sign_variation": sv,
        "entry_instant_concentration": conc,
        "n_overround_measurable": len(overrounds),
        "mean_overround": (round(sum(overrounds) / len(overrounds), 6)
                           if overrounds else None),
        "price_source_tag": P.S82_ENTRY_PRICE_TAG,
        "admissible": bool(n_units >= MIN_UNITS and sv["admissible"]),
    }


def run_cell(prints, depth, closes, settled, *, name: str, window_minutes: float,
             max_lag_minutes: float, score: bool, settlement_root: str) -> dict:
    """One pre-registered cell. score=False makes it population-only - that branch never
    reads an outcome VALUE at all (membership in `settled` is a label class, not a
    result)."""
    cand, drops = P.entry_candidates(
        prints, depth, closes,
        window_s=window_minutes * 60.0,
        min_abs_rho=float(PREREGISTRATION_B["min_abs_rho"]),
        min_window_count=float(PREREGISTRATION_B["min_window_count"]),
        max_entry_lag_s=max_lag_minutes * 60.0)
    rows = P.collapse_to_games(cand)
    pop = population_gate(rows, settled)
    cell: dict = {
        "name": name,
        "flow_window_minutes": window_minutes,
        "max_entry_lag_minutes": max_lag_minutes,
        "scored_cell": bool(score),
        "n_ticker_candidates": len(cand),
        "n_game_entries": len(rows),
        "entry_drops": drops,
        "population": pop,
    }
    if not score:
        cell["verdict"] = "POPULATION-ONLY (never scored, by pre-registration)"
        return cell
    if not pop["admissible"]:
        reasons = []
        if not pop["meets_unit_floor"]:
            reasons.append(f"{pop['n_game_units']} game units below the L41 floor "
                           f"{MIN_UNITS}")
        if not pop["sign_variation"]["admissible"]:
            reasons.append("sign-variation gate (L312/L321) at the real floor "
                           f"{MIN_MINORITY_UNITS_B}: "
                           + ",".join(pop["sign_variation"]["reasons"]))
        cell["verdict"] = "INSUFFICIENT DATA"
        cell["note"] = ("POPULATION-INADEQUATE - no CI computed, no outcome value read. "
                        + "; ".join(reasons))
        return cell

    scoreable = [r for r in rows if r["ticker"] in settled]
    outcomes = P.outcome_map(sorted({r["ticker"] for r in scoreable}),
                             root=settlement_root)
    scored = P.score_rows(scoreable, outcomes)
    uv = P.unit_values(scored)
    boot = block_bootstrap(uv, n_boot=N_BOOT, seed=SEED)
    adm = bootstrap_verdict_admissible(uv, min_units=MIN_UNITS)
    kish = kish_effective_n([len(v) for v in uv.values()])
    clears = clears_tick_magnitude(boot["ci95"], tick=TICK, min_ticks=MIN_TICKS)
    alive = bool(adm["admissible"] and boot["ci95"][0] is not None
                 and boot["ci95"][0] > 0.0 and clears)
    cell.update({
        "scored": [
            {k: s[k] for k in ("game", "ticker", "entry_captured_at",
                               "entry_lag_minutes", "rho", "total_count", "fade_side",
                               "entry_ask", "overround", "fee", "settled_yes",
                               "fade_won", "pnl", "price_source_tag")}
            for s in scored],
        "bootstrap": boot,
        "admissibility": adm,
        "kish_effective_n": kish,
        "clears_tick_magnitude": clears,
        "n_fade_wins": sum(1 for s in scored if s["fade_won"]),
        "verdict": "ALIVE" if alive else "NOT ALIVE",
        "note": ("CI strictly above 0 net of one taker fee AND clears the L27 tick gate "
                 "- a POSITIVE result here would still owe the L360/L361 ex-ante-anchor "
                 "check before any graduation." if alive else
                 "CI does not clear the real-ask bar (above 0 net of fee AND at least "
                 "1 tick, L27/L41)."),
    })
    return cell


def run(trades_dir: Path = P.TRADES_TAPE, depth_dir: Path = P.DEPTH_TAPE,
        ledger_dir: Path = P.LEDGER_TAPE, root: Path = REPO_ROOT,
        settlement_root: str = DEFAULT_TAPE_ROOT) -> dict:
    prints = P.load_prints(trades_dir)
    tickers = frozenset(prints)
    depth = P.load_depth(tickers, depth_dir)
    closes, anchor_audit = load_close_times_union(tickers, ledger_dir, root)
    settled, coverage = P.settled_ticker_set(sorted(tickers), root=settlement_root)

    rep: dict = {
        "probe": "q57b_s82_cache_anchor",
        "strategy": "S82",
        "queue_item": "Q57(b)",
        "preregistration": PREREGISTRATION_B,
        "preregistration_sha256": PREREG_B_SHA256,
        "sealed_probe_sha256": P.PREREG_SHA256,
        "fee_rate": P.FEE_RATE,
        "substrate": {
            "n_trade_tickers": len(tickers),
            "n_trade_games": len({P.game_id_of(t) for t in tickers}),
            "n_tickers_with_depth": len(depth),
            "n_tickers_with_close_time": len(closes),
        },
        "anchor_audit": anchor_audit,
        "settlement_coverage": coverage,
        "flow_orientation_audit": P.flow_orientation_audit(prints),
    }

    cells = [
        run_cell(prints, depth, closes, settled, name="primary_minimal_change",
                 window_minutes=120.0, max_lag_minutes=60.0, score=True,
                 settlement_root=settlement_root),
        run_cell(prints, depth, closes, settled, name="secondary_verifier_identified",
                 window_minutes=15.0, max_lag_minutes=240.0, score=True,
                 settlement_root=settlement_root),
        run_cell(prints, depth, closes, settled, name="diagnostic_window_only",
                 window_minutes=15.0, max_lag_minutes=60.0, score=False,
                 settlement_root=settlement_root),
    ]
    rep["cells"] = cells
    primary = cells[0]
    rep["verdict"] = primary["verdict"]
    rep["verdict_cell"] = primary["name"]
    rep["multiplicity_scored_cells"] = sum(1 for c in cells if c["scored_cell"])
    rep["note"] = ("Verdict is the PRIMARY (minimal-change) cell. The secondary cell was "
                   "identified by the Q57 verifier round on an OUTCOME-BLIND population "
                   "search and carries selection exposure the primary does not; it may "
                   "never be quoted alone.")
    return rep


def _fmt_cell(c: dict) -> str:
    p = c["population"]
    sv = p["sign_variation"]["census"]
    L = [f"  [{c['name']}] window={c['flow_window_minutes']}min "
         f"lag<={c['max_entry_lag_minutes']}min -> {c['verdict']}",
         f"      entries {c['n_ticker_candidates']} ticker / {c['n_game_entries']} game; "
         f"scoreable {p['n_entries_scoreable']} / {p['n_game_units']} units "
         f"(floor {p['min_units']})",
         f"      sides {sv['units_per_side']} exclusive-minority="
         f"{sv['minority_side_units_exclusive']} (floor {MIN_MINORITY_UNITS_B}); "
         f"mean overround {p['mean_overround']} (real_ask)"]
    if "bootstrap" in c:
        b = c["bootstrap"]
        L.append(f"      block bootstrap mean ${b['mean']:+.5f} 95% CI "
                 f"[{b['ci95'][0]:+.5f}, {b['ci95'][1]:+.5f}] n_units={b['n_units']} "
                 f"n_obs={b['n_obs']} kish={c['kish_effective_n']['kish_n']}")
        L.append(f"      admissible={c['admissibility']['admissible']} "
                 f"clears_tick={c['clears_tick_magnitude']} "
                 f"fade wins {c['n_fade_wins']}/{b['n_obs']}")
    L.append(f"      {c.get('note', '')}")
    return "\n".join(L)


def _fmt_human(rep: dict) -> str:
    a = rep["anchor_audit"]
    L = [f"Q57(b) / S82 - cache-anchored retest  [{rep['verdict']} on "
         f"{rep['verdict_cell']}]",
         f"  prereg sha256   {rep['preregistration_sha256'][:16]}... "
         f"(sealed probe {rep['sealed_probe_sha256'][:12]}...)",
         f"  substrate       {rep['substrate']['n_trade_games']} traded games / "
         f"{rep['substrate']['n_tickers_with_close_time']} tickers with a close anchor",
         f"  anchor          ledger {a['n_tickers_ledger']} + cache "
         f"{a['n_tickers_cache']} = union {a['n_tickers_union']} (cache ADDS "
         f"{a['n_tickers_added_by_cache']}; {a['n_tickers_disagreeing']}/"
         f"{a['n_tickers_in_both']} disagree)"]
    for c in rep["cells"]:
        L.append(_fmt_cell(c))
    L.append(f"  {rep['note']}")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    rep = run()
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(_fmt_human(rep))
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

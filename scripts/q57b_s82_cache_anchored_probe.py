#!/usr/bin/env python3
"""Q57(b) / S82 — cache-anchored re-test of the game-level signed-taker-flow FADE taker.

REOPEN PATH (b) of LOOP-QUEUE.md Q57, exactly as that item's newest-dated Status line
(the independent verifier's correction round) specifies it:

    "reopen via a properly PRE-REGISTERED retest that ... (b) widens the entry anchor to
     `q51_settlement_cache` as its OWN pre-registered choice (not a post-hoc addition) at
     `sign_variation_admissible`'s real `min_exclusive_minority_units=2` floor."

WHAT MAKES THIS A SEAL AND NOT TUNING
-------------------------------------
The three constants that differ from the first probe — the anchor source, `flow_window_minutes`
= 15, `max_entry_lag_minutes` = 240 — and the minority floor of 2 are NOT chosen here. They are
quoted verbatim out of Q57's Status text, which was committed to `main` at commit `d78c528`
BEFORE this run existed. `PREREG_SOURCE_COMMIT` pins that. The verifier's observation that fixed
them ("12 GAME units, {no:10, yes:2}, 2 EXCLUSIVE-minority units on 2 distinct games") is a
POPULATION-COMPOSITION statement: no settlement result VALUE was read and no CI was computed in
either prior round. So the constants are POPULATION-INFORMED but OUTCOME-BLIND. That is a real
and disclosed weakness — an outcome-blind population choice cannot manufacture a positive mean,
but it CAN choose the cell with the most favourable variance structure — and it is why this
probe reports the alternative anchors as robustness rows rather than burying them.

WHY THIS REUSES THE SIBLING MODULE INSTEAD OF REIMPLEMENTING IT
---------------------------------------------------------------
`scripts/q57_s82_flow_fade_probe.py` has already been re-derived to the digit twice: once by
`scripts/q57_s82_rederive.py` (16/16 headlines, and it caught a real def-time-default-argument
defect) and once by an independent `verifier` subagent working from a from-scratch reader that
shared no code. A THIRD fresh implementation here would trade audited code for unaudited code.
So the loaders, the window/flow arithmetic, the entry rule, the game collapse and the scoring
are IMPORTED. What this module owns is exactly what changes: the union close-time anchor, the
minority floor of 2, an L51 proof restated for a 15-minute window, and the robustness sweep.

DECISION THE PREREG TEXT DID NOT FULLY DETERMINE (declared, with its sensitivity reported)
-------------------------------------------------------------------------------------------
`q51_settlement_cache` carries MORE THAN ONE distinct `close_time` for 48 of its 60 tickers
(L360/L361: Kalshi rewrites `close_time` at settlement, always EARLIER). The queue text does not
say which to take. This module pre-registers the EARLIEST — the most-rewritten, latest-observed
value, which pushes the entry instant furthest back and is therefore the most conservative
choice on the look-ahead axis — and reports the LATEST-anchor population and CI as a DISCLOSED
robustness row. It also matches the sibling probe's existing `load_close_times`, which already
takes `min(...)`, so the two anchors stay comparable.

L51 DIFFERENTIATION NOW RUNS THE OTHER WAY ON ONE AXIS — SAID OUT LOUD
-----------------------------------------------------------------------
The first probe argued differentiation from the dead S79 partly on "120 min is 4x S79's 30-min
lookback". At 15 minutes that argument INVERTS (15 is half of 30). Differentiation therefore
rests on the three axes that survive: DISJOINT entry-price families (`orderbook_depth`/`real_ask`
vs `kalshi_trades`/`broker_truth` — no entry price can coincide), one close-anchored instant per
game vs S79's hourly UTC grid, and a scale-free `rho` vs an absolute contract threshold. The
VOID condition is unchanged and is still not met.

Read-only. Fully offline. No network. No order path.

Run:  python3 scripts/q57b_s82_cache_anchored_probe.py [--json]
Writes `reports/q57b_s82_cache_anchored.json`. Exit 0 always (a verdict is not an error).
"""
from __future__ import annotations

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
from core.pricing import TAKER_FEE_RATE  # noqa: E402
from core.settlement_sources import DEFAULT_TAPE_ROOT  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts import q57_s82_flow_fade_probe as P  # noqa: E402

CACHE_TAPE = REPO_ROOT / "tape" / "q51_settlement_cache"
REPORT_PATH = REPO_ROOT / "reports" / "q57b_s82_cache_anchored.json"

SIDE_YES = P.SIDE_YES
SIDE_NO = P.SIDE_NO

# --------------------------------------------------------------------------- #
# THE PRE-REGISTRATION. Every value is either (a) quoted from Q57's Status line as
# committed at PREREG_SOURCE_COMMIT, or (b) identical to the first probe's sealed spec.
# Nothing is chosen here on the basis of a return distribution; nothing was tuned after a
# CI was seen, because no CI has ever been computed on S82 in any round.
# --------------------------------------------------------------------------- #
PREREG_SOURCE_COMMIT = "d78c528"
PREREG_SOURCE = ("LOOP-QUEUE.md Q57, newest-dated Status line (independent verifier "
                 "correction round, 2026-08-16), committed to main at d78c528 before this "
                 "probe existed")

PREREGISTRATION: Dict[str, object] = {
    "sealed_on": "2026-08-16",
    "strategy": "S82",
    "queue_item": "Q57",
    "reopen_path": "b",
    "prereg_source_commit": PREREG_SOURCE_COMMIT,
    "prereg_source": PREREG_SOURCE,
    "unit": "game",
    # ── THE ONE STRUCTURAL CHANGE: the entry anchor ────────────────────────────────
    "close_anchor": ("union(settlement_ledger.close_time, q51_settlement_cache.close_time); "
                     "settlement_ledger wins where a ticker appears in both"),
    "close_anchor_multivalue_rule": "earliest distinct close_time within the winning source",
    "entry_instant_rule": "last_orderbook_depth_snapshot_at_or_before_close",
    # ── the two constants Q57's Status text names for path (b) ─────────────────────
    "max_entry_lag_minutes": 240,
    "flow_window_minutes": 15,
    # ── identical to the first probe's sealed spec ─────────────────────────────────
    "flow_weight": "count",
    "flow_sign_convention": "+count when the taker BUYS yes, -count when the taker buys no",
    "signal": "rho = net_signed_count / total_count over the window, on one ticker",
    "game_ticker_rule": "argmax |rho| over the game's traded tickers; ties -> min(ticker)",
    "min_abs_rho": 0.20,
    "min_window_count": 100.0,
    "direction": "FADE",
    "entry_price_field": "best_no_ask if rho>0 else best_yes_ask",
    "entry_price_source_tag": "real_ask",
    "entry_price_band": [0.02, 0.98],
    "exit": "hold_to_settlement",
    "fee_legs": 1,
    "fee_side": "taker",
    "min_units": 10,
    # ── the floor the verifier corrected the first probe on ────────────────────────
    "min_exclusive_minority_units": 2,   # sign_variation_admissible's REAL default
    "n_boot": 10000,
    "seed": 42,
    "tick": 0.01,
    "min_ticks": 1.0,
}

MAX_ENTRY_LAG_S = float(PREREGISTRATION["max_entry_lag_minutes"]) * 60.0
FLOW_WINDOW_S = float(PREREGISTRATION["flow_window_minutes"]) * 60.0
MIN_ABS_RHO = float(PREREGISTRATION["min_abs_rho"])
MIN_WINDOW_COUNT = float(PREREGISTRATION["min_window_count"])
MIN_UNITS = int(PREREGISTRATION["min_units"])
MIN_MINORITY_UNITS = int(PREREGISTRATION["min_exclusive_minority_units"])
N_BOOT = int(PREREGISTRATION["n_boot"])
SEED = int(PREREGISTRATION["seed"])
TICK = float(PREREGISTRATION["tick"])
MIN_TICKS = float(PREREGISTRATION["min_ticks"])

# Imported, never spelled (L5: a 4x maker/taker fee mix-up went uncaught for weeks).
FEE_RATE = TAKER_FEE_RATE


def preregistration_sha256(spec: Optional[Dict[str, object]] = None) -> str:
    payload = json.dumps(spec if spec is not None else PREREGISTRATION,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


PREREG_SHA256 = preregistration_sha256()


# --------------------------------------------------------------------------- #
# the anchor — the only loader this module owns
# --------------------------------------------------------------------------- #
def load_cache_close_times(tickers: FrozenSet[str], tape_dir: Path = CACHE_TAPE,
                           *, pick: str = "earliest",
                           ) -> Tuple[Dict[str, float], Dict[str, int]]:
    """ticker -> close epoch from `tape/q51_settlement_cache/*.json`, plus a mutation census.

    `pick` is "earliest" (pre-registered) or "latest" (robustness only). A ticker carrying
    several distinct `close_time` strings across captures is the L360/L361 rewrite: Kalshi
    moves `close_time` EARLIER at settlement, so "earliest" is the settled, most-rewritten,
    least-flattering value.
    """
    if pick not in ("earliest", "latest"):
        raise ValueError(f"pick must be 'earliest' or 'latest' (got {pick!r})")
    seen: Dict[str, set] = defaultdict(set)
    for path in sorted(Path(tape_dir).glob("*.json")):
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
        markets = blob.get("markets") or {}
        if isinstance(markets, dict):
            items = list(markets.items())
        else:
            items = [(m.get("ticker"), m) for m in markets if isinstance(m, dict)]
        for tk, m in items:
            if not tk or tk not in tickers or not isinstance(m, dict):
                continue
            ct = m.get("close_time")
            if ct:
                seen[tk].add(ct)
    agg = min if pick == "earliest" else max
    out = {tk: agg(parse_iso_utc(v).timestamp() for v in vals) for tk, vals in seen.items()}
    census = {
        "n_tickers_in_cache_and_traded": len(seen),
        "n_with_multiple_close_times": sum(1 for v in seen.values() if len(v) > 1),
        "max_distinct_close_times": max((len(v) for v in seen.values()), default=0),
    }
    return out, census


def union_close_times(tickers: FrozenSet[str], *, pick: str = "earliest",
                      ledger_dir: Path = P.LEDGER_TAPE, cache_dir: Path = CACHE_TAPE,
                      ) -> Tuple[Dict[str, float], dict]:
    """The pre-registered anchor: ledger ∪ cache, LEDGER WINS on a ticker in both.

    Precedence matters and is pre-registered rather than left to dict-update order: the
    ledger is the incumbent, already-scored source, so keeping it authoritative means this
    probe's population is a strict SUPERSET of the first probe's at the same constants —
    the widening is additive, not a substitution that could silently move existing units.
    """
    led, led_distinct_max = P.load_close_times(tickers, ledger_dir)
    cache, cache_census = load_cache_close_times(tickers, cache_dir, pick=pick)
    merged = dict(cache)
    merged.update(led)                      # ledger precedence
    added = sorted(set(cache) - set(led))
    return merged, {
        "n_from_settlement_ledger": len(led),
        "n_from_q51_settlement_cache": len(cache),
        "n_in_both": len(set(led) & set(cache)),
        "n_added_by_cache": len(added),
        "n_union": len(merged),
        "ledger_close_time_distinct_values_max": led_distinct_max,
        "cache_mutation_census": cache_census,
        "multivalue_pick": pick,
        "precedence": "settlement_ledger",
    }


# --------------------------------------------------------------------------- #
# Q57 gate (3), restated for a 15-minute window
# --------------------------------------------------------------------------- #
def l51_differentiation(rows: Sequence[dict], *,
                        window_minutes: float = float(PREREGISTRATION["flow_window_minutes"]),
                        ) -> dict:
    """Outcome-blind proof that S82(b)'s population is not S79's with the sign flipped.

    The window axis NO LONGER helps: 15 min is HALF S79's 30-min lookback, not 4x it. Said
    plainly in `window_axis_note` rather than quietly dropped. The VOID condition — a shared
    entry-price surface AND an identical decision rule — is still not met, on three axes that
    do not depend on the window at all.
    """
    same_price_surface = (P.S82_ENTRY_PRICE_FAMILY == P.S79_ENTRY_PRICE_FAMILY)
    same_decision_rule = False   # close-anchored, one per game vs an hourly UTC grid
    return {
        "voided": bool(same_price_surface and same_decision_rule),
        "s82b_window_minutes": window_minutes,
        "s79_window_minutes": P.S79_LOOKBACK_MINUTES,
        "window_ratio": window_minutes / float(P.S79_LOOKBACK_MINUTES),
        "window_axis_note": ("At 15 min the window is HALF S79's 30-min lookback, so the "
                             "first probe's '4x wider window' differentiation argument does "
                             "NOT carry over and is not relied on here."),
        "s82b_decision_rule": PREREGISTRATION["entry_instant_rule"],
        "s79_decision_rule": f"every_{P.S79_DECISION_GRID_MINUTES}min_utc_grid_instant",
        "s82b_entry_price_family": P.S82_ENTRY_PRICE_FAMILY,
        "s82b_entry_price_tag": P.S82_ENTRY_PRICE_TAG,
        "s79_entry_price_family": P.S79_ENTRY_PRICE_FAMILY,
        "s79_entry_price_tag": P.S79_ENTRY_PRICE_TAG,
        "entry_price_surfaces_disjoint": not same_price_surface,
        "s82b_signal_statistic": "scale_free_ratio",
        "s79_signal_statistic": "absolute_contract_threshold",
        "s82b_direction": "FADE",
        "s79_direction": "FOLLOW",
        "n_s82b_entries": len(rows),
        "n_s82b_distinct_entry_instants": len({r["entry_captured_at"] for r in rows}),
        "surviving_differentiation_axes": ["disjoint_entry_price_family",
                                           "close_anchored_instant_vs_hourly_grid",
                                           "scale_free_rho_vs_absolute_threshold"],
    }


# --------------------------------------------------------------------------- #
# population — owns its own minority floor of 2 (does NOT rebind the sibling's global)
# --------------------------------------------------------------------------- #
def population_report(rows: Sequence[dict], settled: FrozenSet[str], *,
                      min_units: int = MIN_UNITS,
                      min_minority: int = MIN_MINORITY_UNITS) -> dict:
    """Adequacy WITHOUT any outcome value. `scoreable` = an entry on a settled ticker.

    The floors are explicit keyword arguments. The sibling module's `population_report`
    reads MODULE GLOBALS for both, and rebinding another module's globals to change a gate
    is precisely the class of defect `q57_s82_rederive.py` caught last round.
    """
    scoreable = [r for r in rows if r["ticker"] in settled]
    sides: Dict[str, List[str]] = defaultdict(list)
    for r in scoreable:
        sides[r["game"]].append(r["fade_side"])
    sv = sign_variation_admissible(sides, min_exclusive_minority_units=min_minority,
                                   sides=(SIDE_YES, SIDE_NO))
    conc = entry_instant_concentration([r["entry_captured_at"] for r in scoreable],
                                       unit_labels=[r["game"] for r in scoreable])
    n_units = len({r["game"] for r in scoreable})
    overrounds = [r["overround"] for r in scoreable if r["overround"] is not None]
    return {
        "n_entries_all": len(rows),
        "n_entries_scoreable": len(scoreable),
        "n_game_units": n_units,
        "min_units": min_units,
        "meets_unit_floor": n_units >= min_units,
        "min_exclusive_minority_units": min_minority,
        "sign_variation": sv,
        "entry_instant_concentration": conc,
        "n_overround_measurable": len(overrounds),
        "mean_overround": (round(sum(overrounds) / len(overrounds), 6) if overrounds else None),
        "price_source_tag": P.S82_ENTRY_PRICE_TAG,
        "admissible": bool(n_units >= min_units and sv["admissible"]),
    }


# --------------------------------------------------------------------------- #
def _entries(prints, depth, closes) -> Tuple[List[dict], List[dict], Dict[str, int]]:
    cand, drops = P.entry_candidates(
        prints, depth, closes,
        window_s=FLOW_WINDOW_S, min_abs_rho=MIN_ABS_RHO,
        min_window_count=MIN_WINDOW_COUNT, max_entry_lag_s=MAX_ENTRY_LAG_S)
    return cand, P.collapse_to_games(cand), drops


def _score(rows, settled, settlement_root) -> dict:
    """CI on a given entry population. Called for the pre-registered cell AND for the
    robustness anchors, so a robustness row is never a different code path."""
    scoreable = [r for r in rows if r["ticker"] in settled]
    outcomes = P.outcome_map(sorted({r["ticker"] for r in scoreable}), root=settlement_root)
    scored = P.score_rows(scoreable, outcomes)
    uv = P.unit_values(scored)
    if not uv:
        return {"n_units": 0, "bootstrap": None, "scored": []}
    boot = block_bootstrap(uv, n_boot=N_BOOT, seed=SEED)
    return {
        "n_units": len(uv),
        "bootstrap": boot,
        "admissibility": bootstrap_verdict_admissible(uv, min_units=MIN_UNITS),
        "kish_effective_n": kish_effective_n([len(v) for v in uv.values()]),
        "clears_tick_magnitude": clears_tick_magnitude(boot["ci95"], tick=TICK,
                                                       min_ticks=MIN_TICKS),
        "n_fade_wins": sum(1 for s in scored if s["fade_won"]),
        "price_source_tag": P.S82_ENTRY_PRICE_TAG,
        "scored": scored,
    }


def robustness_anchors(prints, depth, tickers, settled, settlement_root) -> List[dict]:
    """The anchors NOT pre-registered, each scored through the same `_score` path.

    A pre-registered choice whose alternatives are hidden is a choice made after the fact.
    Every row here reports its own population AND its own CI so a reader can see whether the
    headline depends on the anchor decision.
    """
    out: List[dict] = []
    variants = [
        ("prereg_union_earliest", dict(pick="earliest")),
        ("union_latest_close_time", dict(pick="latest")),
    ]
    for name, kw in variants:
        closes, prov = union_close_times(tickers, **kw)
        _, rows, _ = _entries(prints, depth, closes)
        pop = population_report(rows, settled)
        sc = _score(rows, settled, settlement_root)
        out.append({
            "anchor": name,
            "n_game_units": pop["n_game_units"],
            "units_per_side": pop["sign_variation"]["census"]["units_per_side"],
            "minority_exclusive": pop["sign_variation"]["census"]["minority_side_units_exclusive"],
            "n_added_by_cache": prov["n_added_by_cache"],
            "mean": (sc["bootstrap"]["mean"] if sc["bootstrap"] else None),
            "ci95": (sc["bootstrap"]["ci95"] if sc["bootstrap"] else None),
            "price_source_tag": P.S82_ENTRY_PRICE_TAG,
        })
    # cache-only and ledger-only anchors: population shape only (outcome-blind)
    for name, closes in (
            ("cache_only", load_cache_close_times(tickers)[0]),
            ("ledger_only", P.load_close_times(tickers, P.LEDGER_TAPE)[0])):
        _, rows, _ = _entries(prints, depth, closes)
        pop = population_report(rows, settled)
        out.append({
            "anchor": name,
            "n_game_units": pop["n_game_units"],
            "units_per_side": pop["sign_variation"]["census"]["units_per_side"],
            "minority_exclusive": pop["sign_variation"]["census"]["minority_side_units_exclusive"],
            "mean": None, "ci95": None, "note": "population shape only, outcome-blind",
        })
    return out


# --------------------------------------------------------------------------- #
# Is the +mean an EDGE, or is it entry-price level? (the check this result needs most)
# --------------------------------------------------------------------------- #
def concentration_and_calibration(scored: Sequence[dict], *, n_boot: int = N_BOOT,
                                  seed: int = SEED) -> dict:
    """Three checks that a 12-unit positive point estimate MUST survive to mean anything.

    (1) JACKKNIFE FRAGILITY. Drop each GAME unit in turn and re-run the identical block
        bootstrap. A mean carried by one unit is not a population property. Reports the
        worst-case mean, how many leave-one-out CIs would have been strictly > 0, and the
        single unit whose removal costs the most.

    (2) CALIBRATION NULL. A `real_ask` of 0.93 is the venue's own 93% claim. Under perfect
        calibration the expected number of fade wins is the SUM of the entry asks, and the
        expected mean P&L is exactly minus the mean fee. The honest size of the "edge" is
        the EXCESS wins over that sum — on a 12-unit sample that excess is a small integer
        and should be quoted as one, not as a dollar mean that hides how few events it is.

    (3) PRICE-ORDERED SEPARATION. If every winning unit has a higher entry ask than every
        losing unit, the P&L is ordered by PRICE LEVEL, not by the flow signal — i.e. the
        population is "the expensive side won", which any price-taking rule reproduces
        without reference to `rho`. Also reports the rank correlation between |rho| (the
        actual signal) and per-unit P&L: if the signal carried the edge, that is where it
        would show, and a near-zero value says the strategy's own statistic is inert.

    Pure. Reads only per-unit values the caller already scored; computes no new price.
    """
    if not scored:
        return {"n_units": 0, "note": "no scored units"}
    by_game: Dict[str, List[dict]] = defaultdict(list)
    for s in scored:
        by_game[s["game"]].append(s)
    games = sorted(by_game)

    # ── (1) jackknife ──────────────────────────────────────────────────────────
    loo: List[dict] = []
    for g in games:
        uv = {k: [x["pnl"] for x in v] for k, v in by_game.items() if k != g}
        if len(uv) < 2:
            continue
        b = block_bootstrap(uv, n_boot=n_boot, seed=seed)
        loo.append({"dropped_unit": g, "mean": b["mean"], "ci95": b["ci95"],
                    "ci_lower_gt_zero": bool(b["ci95"][0] is not None and b["ci95"][0] > 0.0)})
    worst = min(loo, key=lambda d: d["mean"]) if loo else None

    # ── (2) calibration null ───────────────────────────────────────────────────
    asks = [s["entry_ask"] for s in scored]
    fees = [s["fee"] for s in scored]
    wins = sum(1 for s in scored if s["fade_won"])
    expected_wins = sum(asks)
    calib = {
        "n_obs": len(scored),
        "observed_fade_wins": wins,
        "expected_fade_wins_if_asks_calibrated": round(expected_wins, 4),
        "excess_wins": round(wins - expected_wins, 4),
        "calibrated_null_mean_pnl": round(-sum(fees) / len(fees), 6),
        "price_source_tag": P.S82_ENTRY_PRICE_TAG,
        "note": ("The dollar mean is this excess-win count divided by n. Quoting it as a "
                 "per-contract dollar figure hides that it rests on a small integer number "
                 "of binary events."),
    }

    # ── (3) price-ordered separation + signal inertness ────────────────────────
    win_asks = [s["entry_ask"] for s in scored if s["fade_won"]]
    lose_asks = [s["entry_ask"] for s in scored if not s["fade_won"]]
    separated = bool(win_asks and lose_asks and min(win_asks) > max(lose_asks))

    def _rank(xs: Sequence[float]) -> List[float]:
        order = sorted(range(len(xs)), key=lambda i: xs[i])
        r = [0.0] * len(xs)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    def _pearson(a: Sequence[float], b: Sequence[float]) -> Optional[float]:
        n = len(a)
        if n < 3:
            return None
        ma, mb = sum(a) / n, sum(b) / n
        va = sum((x - ma) ** 2 for x in a)
        vb = sum((x - mb) ** 2 for x in b)
        if va <= 0 or vb <= 0:
            return None
        cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
        return round(cov / (va ** 0.5 * vb ** 0.5), 4)

    pnls = [s["pnl"] for s in scored]
    abs_rho = [abs(s["rho"]) for s in scored]
    sep = {
        "win_ask_min": (min(win_asks) if win_asks else None),
        "lose_ask_max": (max(lose_asks) if lose_asks else None),
        "perfectly_price_ordered": separated,
        "spearman_abs_rho_vs_pnl": _pearson(_rank(abs_rho), _rank(pnls)),
        "spearman_entry_ask_vs_pnl": _pearson(_rank(asks), _rank(pnls)),
        "price_source_tag": P.S82_ENTRY_PRICE_TAG,
        "note": ("`perfectly_price_ordered` True means every winning unit was entered at a "
                 "STRICTLY higher real_ask than every losing unit: the outcome split is a "
                 "restatement of the entry price level and carries no information about the "
                 "flow signal. Compare the two rank correlations — if |rho| (the strategy's "
                 "own statistic) ranks P&L no better than the entry ask does, the signal is "
                 "inert on this population."),
    }

    return {
        "n_units": len(games),
        "jackknife": {
            "n_leave_one_out_fits": len(loo),
            "full_mean": round(sum(pnls) / len(pnls), 6),
            "worst_leave_one_out": worst,
            "n_loo_ci_lower_gt_zero": sum(1 for d in loo if d["ci_lower_gt_zero"]),
            "max_single_unit_mean_contribution": (
                round((sum(pnls) / len(pnls)) - worst["mean"], 6) if worst else None),
            "fits": loo,
        },
        "calibration_null": calib,
        "price_ordering": sep,
    }


def run(trades_dir: Path = P.TRADES_TAPE, depth_dir: Path = P.DEPTH_TAPE,
        settlement_root: str = DEFAULT_TAPE_ROOT) -> dict:
    prints = P.load_prints(trades_dir)
    tickers = frozenset(prints)
    depth = P.load_depth(tickers, depth_dir)
    closes, anchor_prov = union_close_times(tickers)

    cand, rows, drops = _entries(prints, depth, closes)

    rep: dict = {
        "probe": "q57b_s82_cache_anchored",
        "strategy": "S82",
        "queue_item": "Q57",
        "reopen_path": "b",
        "preregistration": PREREGISTRATION,
        "preregistration_sha256": PREREG_SHA256,
        "fee_rate": FEE_RATE,
        "price_provenance": {"prices_quoted": True,
                             "price_source_tag": P.S82_ENTRY_PRICE_TAG,
                             "entry_price_family": P.S82_ENTRY_PRICE_FAMILY,
                             "synthetic_prices_used": False},
        "anchor_provenance": anchor_prov,
        "close_time_cross_family_audit": P.close_time_cross_family_audit(tickers),
        "flow_orientation_audit": P.flow_orientation_audit(prints),
        "substrate": {
            "n_trade_tickers": len(tickers),
            "n_trade_games": len({P.game_id_of(t) for t in tickers}),
            "n_tickers_with_depth": len(depth),
            "n_tickers_with_close_time": len(closes),
        },
        "entry_drops": drops,
        "n_ticker_candidates": len(cand),
        "n_game_entries": len(rows),
    }

    # ── Q57 gate (3) BEFORE any outcome value is read ────────────────────────────────
    diff = l51_differentiation(rows)
    rep["l51_differentiation"] = diff
    if diff["voided"]:
        rep["verdict"] = "VOID"
        rep["note"] = "L51: population is S79's with the sign flipped. Not scored."
        return rep

    settled, coverage = P.settled_ticker_set(sorted(tickers), root=settlement_root)
    rep["settlement_coverage"] = coverage
    pop = population_report(rows, settled)
    rep["population"] = pop

    # the pre-committed claim this run exists to check
    cen = pop["sign_variation"]["census"]
    rep["precommitted_claim_check"] = {
        "source": PREREG_SOURCE,
        "expected": {"n_game_units": 12, "units_per_side": {"no": 10, "yes": 2},
                     "minority_exclusive": 2},
        "observed": {"n_game_units": pop["n_game_units"],
                     "units_per_side": cen["units_per_side"],
                     "minority_exclusive": cen["minority_side_units_exclusive"]},
        "reproduced": bool(pop["n_game_units"] == 12
                           and dict(cen["units_per_side"]) == {"no": 10, "yes": 2}
                           and cen["minority_side_units_exclusive"] == 2),
    }

    if not pop["admissible"]:
        reasons = []
        if not pop["meets_unit_floor"]:
            reasons.append(f"{pop['n_game_units']} game units < L41 floor {MIN_UNITS}")
        if not pop["sign_variation"]["admissible"]:
            reasons.append("sign-variation gate (L312/L321): "
                           + ",".join(pop["sign_variation"]["reasons"]))
        rep["verdict"] = "INSUFFICIENT DATA"
        rep["note"] = ("POPULATION-INADEQUATE — no CI computed, no outcome value read. "
                       + "; ".join(reasons))
        return rep

    sc = _score(rows, settled, settlement_root)
    rep["bootstrap"] = sc["bootstrap"]
    rep["admissibility"] = sc["admissibility"]
    rep["kish_effective_n"] = sc["kish_effective_n"]
    rep["clears_tick_magnitude"] = sc["clears_tick_magnitude"]
    rep["n_fade_wins"] = sc["n_fade_wins"]
    rep["scored"] = [
        {k: s[k] for k in ("game", "ticker", "entry_captured_at", "entry_lag_minutes",
                           "rho", "total_count", "fade_side", "entry_ask", "overround",
                           "fee", "settled_yes", "fade_won", "pnl", "price_source_tag")}
        for s in sc["scored"]]
    rep["robustness_anchors"] = robustness_anchors(prints, depth, tickers, settled,
                                                   settlement_root)
    rep["concentration_and_calibration"] = concentration_and_calibration(sc["scored"])

    boot = sc["bootstrap"]
    alive = bool(sc["admissibility"]["admissible"] and boot["ci95"][0] is not None
                 and boot["ci95"][0] > 0.0 and sc["clears_tick_magnitude"])
    rep["verdict"] = "ALIVE" if alive else "DEAD"
    rep["note"] = ("CI strictly > 0 net of one taker fee AND clears the L27 tick gate."
                   if alive else
                   "CI does not clear the real-ask bar (>0 net of fee AND >= 1 tick, L27/L41).")
    return rep


def _fmt_human(rep: dict) -> str:
    L = [f"Q57(b) / S82 — cache-anchored flow-fade taker  [{rep['verdict']}]",
         f"  prereg sha256   {rep['preregistration_sha256'][:16]}… "
         f"(source commit {PREREG_SOURCE_COMMIT})",
         f"  anchor          {rep['anchor_provenance']['n_from_settlement_ledger']} ledger + "
         f"{rep['anchor_provenance']['n_added_by_cache']} added by cache = "
         f"{rep['anchor_provenance']['n_union']} tickers "
         f"(cache mutation: {rep['anchor_provenance']['cache_mutation_census']})",
         f"  entries         {rep['n_ticker_candidates']} ticker → {rep['n_game_entries']} game",
         f"  entry drops     {rep['entry_drops']}"]
    if "population" in rep:
        p = rep["population"]
        cen = p["sign_variation"]["census"]
        L.append(f"  scoreable       {p['n_entries_scoreable']} entries / "
                 f"{p['n_game_units']} game units (floor {p['min_units']})")
        L.append(f"  sides           {cen['units_per_side']} exclusive-minority="
                 f"{cen['minority_side_units_exclusive']} (floor {MIN_MINORITY_UNITS})")
        L.append(f"  mean overround  {p['mean_overround']}  [real_ask]")
    if "precommitted_claim_check" in rep:
        c = rep["precommitted_claim_check"]
        L.append(f"  precommit check reproduced={c['reproduced']}  "
                 f"expected={c['expected']}  observed={c['observed']}")
    if rep.get("bootstrap"):
        b = rep["bootstrap"]
        L.append(f"  block bootstrap mean ${b['mean']:+.4f} 95% CI "
                 f"[{b['ci95'][0]:+.4f}, {b['ci95'][1]:+.4f}]  "
                 f"n_units={b['n_units']} n_obs={b['n_obs']}  [real_ask, net 1 taker fee]")
        L.append(f"  kish eff n      {rep['kish_effective_n']['kish_n']}")
        L.append(f"  admissible={rep['admissibility']['admissible']} "
                 f"clears_tick={rep['clears_tick_magnitude']} "
                 f"fade wins {rep['n_fade_wins']}/{b['n_obs']}")
    cc = rep.get("concentration_and_calibration")
    if cc and cc.get("n_units"):
        jk, cal, po = cc["jackknife"], cc["calibration_null"], cc["price_ordering"]
        w = jk["worst_leave_one_out"]
        L.append(f"  jackknife       worst leave-one-out mean ${w['mean']:+.4f} "
                 f"(drop {w['dropped_unit'][:34]}); "
                 f"{jk['n_loo_ci_lower_gt_zero']}/{jk['n_leave_one_out_fits']} LOO CIs > 0")
        L.append(f"  calibration     {cal['observed_fade_wins']} wins vs "
                 f"{cal['expected_fade_wins_if_asks_calibrated']} expected if real_asks "
                 f"calibrated → excess {cal['excess_wins']:+} wins on n={cal['n_obs']}")
        L.append(f"  price ordering  perfectly_price_ordered={po['perfectly_price_ordered']} "
                 f"(win_ask_min={po['win_ask_min']} > lose_ask_max={po['lose_ask_max']}); "
                 f"spearman |rho|~pnl={po['spearman_abs_rho_vs_pnl']} "
                 f"ask~pnl={po['spearman_entry_ask_vs_pnl']}")
    for r in rep.get("robustness_anchors", []):
        L.append(f"  robustness      {r['anchor']:<26} units={r['n_game_units']} "
                 f"{r['units_per_side']} minority_excl={r['minority_exclusive']} "
                 f"ci95={r['ci95']}")
    L.append(f"  {rep.get('note', '')}")
    return "\n".join(L)


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    rep = run()
    os.makedirs(REPORT_PATH.parent, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, sort_keys=True)
        fh.write("\n")
    if "--json" in argv:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(_fmt_human(rep))
        print(f"\nwrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

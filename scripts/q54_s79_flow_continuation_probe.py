#!/usr/bin/env python3
"""Q54 / S79 — Aggressor-flow continuation taker on signed `taker_book_side` trade flow.

PRE-REGISTERED, GATE-SEALED PROBE. Built 2026-08-08, BEFORE its data gate opened, under
LOOP-QUEUE.md's idle-run policy (b) ("write + offline-test the probe script for the next
gated queue item so it fires the day its gate opens"). It is committed in a state where it
CANNOT yet produce a number, and that is the point — see THE SEAL below.

MECHANISM (kb/strategies/00-index.md S79; LOOP-QUEUE.md Q54)
------------------------------------------------------------
`tape/kalshi_trades/` carries every executed print's aggressor direction in
`taker_book_side`. Signed aggressor flow is the classic short-horizon continuation signal in
a limit-order market: informed takers move price, and the move persists. S79 asks whether
following that flow pays a TAKER on Kalshi sports moneylines. The registered prior is a
KILL: a round trip costs ~2x the 0.07 taker fee plus the spread, and S24 measured these same
sports mid-moves MEAN-REVERTING (0.454 continuation). S79 was registered `collect-and-revisit`
anyway because the SIGNED-FLOW conditioning variable had never been tested — it is distinct
from S22's depth imbalance (dead: the mid already integrates the resting ladder) and
opposite in sign to S24's fade.

THE VARIANT BUILT HERE, AND THE ONE DELIBERATELY NOT BUILT
----------------------------------------------------------
Q54 names two exits. Only one is measurable, so only one is pre-registered:

  * BUILT — hold-to-settlement, SINGLE taker fee. Entry pays the taker fee once at the
    aggressor print price (`broker_truth`); the position is carried to the venue's own
    settlement, which costs nothing. This is the variant whose every input is already a
    committed venue-reported fact.
  * NOT BUILT — the seconds-to-minutes round-trip exit. `tape/orderbook_depth/` supplies
    4 captures/day on the one committed trade day: the S9 cadence wall. There is no
    fillable exit surface at that horizon, and inventing one would be a synthetic fill
    price (prime-directive-forbidden). Adding it later requires the Q47 `orderbook_delta`
    daemon or a trade-cadence book, NOT a change to this file's gates.

Note what the single-fee variant does to the registered kill prior: it removes exactly one
of the two fee legs the prior leans on. The prior therefore survives here only through the
entry fee and the mean-reversion evidence, which is a weaker (i.e. fairer) form of it. That
is a reason to run the test, not a prediction that it passes.

THE SEAL — why a probe built before its gate must be unable to peek
------------------------------------------------------------------
The committed tape TODAY holds one trade day, whose settled population is 9 games against
the L41 floor of 10. A probe that merely *reported* `INSUFFICIENT DATA` while having already
computed the 9-game answer would have spent its own pre-registration: whoever later chose
the lookback, the flow threshold or the price band would be choosing them having seen the
returns, which is the L41 luckiest-cell failure with extra steps.

So the refusal here is STRUCTURAL, not cosmetic:

  * `population_report()` is outcome-blind by CONSTRUCTION. It never receives, reads or
    returns a settlement `result`. It establishes which tickers are settled through
    `settled_ticker_set()`, which collapses each result to `is_binary_result(...) -> bool`
    — the LABEL CLASS, never the direction.
  * `outcome_map()` (the only function in this module that reads a result's VALUE) and
    `score_rows()` (the only one that computes a return) are unreachable from `run()`
    unless `population_report()["admissible"]` is True.
  * Below the floor the emitted report is asserted free of every outcome/P&L token
    (`FORBIDDEN_SEALED_TOKENS`) by the acceptance tests — the same pattern
    `scripts/q51_m3_fill_projection.py` uses to stay out of forecast territory.
  * `PREREGISTRATION` is hashed into `PREREG_SHA256`, pinned by a test. Any later edit to a
    spec constant breaks that test loudly, so tuning-after-seeing-data cannot be a quiet
    diff. Re-pinning it after the gate opens is a declaration, not a bug fix.

The probe therefore self-activates: the day a settlement family covers a 10th traded game,
this file computes and reports the verdict with the spec it was sealed with today.

PRE-REGISTERED SPEC (locked 2026-08-08; every value chosen from mechanism, not from data)
-----------------------------------------------------------------------------------------
  unit                    GAME (`event_ticker` prefix of the market ticker) — L6, never the
                          outcome, so the two legs of one game cannot both vote.
  universe                per-game sports moneyline markets (`*GAME`, KXMVE* excluded per
                          L31) that carry >=1 `broker_truth` print AND a binary settlement
                          from any declared source in `core.settlement_sources` (L300 — nine
                          families, not just `settlement_ledger`).
  decision instants       every whole UTC hour of the trade day (60 min grid).
  signal                  net signed YES flow over the preceding 30 minutes:
                          +count for `taker_book_side == "bid"` (a taker whose own order sat
                          on the bid is a BUYER — the L279 orientation correction), -count
                          for `"ask"`. Named constants imported from the Q51 probe; no bare
                          "bid"/"ask" literal at a comparison site, because the inverted
                          reading is the exact bug L279 caught.
  entry gate              |net flow| >= 10.0 contracts.
  entry                   the FIRST print at/after the decision instant, within 5 minutes,
                          whose own aggressor direction AGREES with the signal's sign.
                          Entry price = that print's executed price (`broker_truth`) — YES
                          side at `yes_price`, NO side at its complement. Never a midpoint,
                          never a quote, never a synthetic (the pt1 wall).
  price band              entry price in [0.02, 0.98]; outside it a 1-tick move is a
                          >50% relative move and the fee model degenerates (L27/L249:
                          values pinned at an exact bound are not evidence).
  exit                    hold to settlement (`broker_truth`), $1 or $0.
  cost                    ONE taker fee at entry, `core.pricing.fee_per_contract` at
                          `TAKER_FEE_RATE`. No hand-rolled rate (L5/L18/L30).
  sign-variation gate     the SCOREABLE population must carry entries on BOTH sides, with
                          >= 2 distinct game units on the MINORITY side. Without that the
                          "signed-flow" verdict is mechanically a verdict about one
                          direction — a directional bet, not a test of the conditioning
                          variable — and with a single minority unit the difference cannot
                          be block-bootstrapped at all (L41's own logic, applied to the
                          SIGNAL rather than to the outcome). Added 2026-08-08 from this
                          file's own outcome-blind diagnostics; see THE SIGN-VARIATION
                          HOLE below.
  verdict rule            block bootstrap BY GAME (L6), n=10000, seed 42; admissible only
                          via `bootstrap_verdict_admissible(min_units=10)` (L41); ALIVE only
                          if the CI is strictly > 0 AND clears one tick (L27).

THE SIGN-VARIATION HOLE (measured 2026-08-08, outcome-blind, on the committed tape)
-----------------------------------------------------------------------------------
Running the sealed spec over the one committed trade day enumerates 82 entry candidates, of
which 67 land on a settled market. ALL 67 are on the SAME side (YES): the 5 NO-side
candidates the tape produces belong to two games that have not settled. So on the population
that could actually be scored, S79's conditioning variable is CONSTANT — the strategy
degenerates into "buy YES whenever 30-minute net flow clears 10 contracts", and any CI it
produced would be evidence about buying YES sports moneylines, not about signed flow.

This is not a one-day fluke. L279 measured the venue's flow asymmetry directly: 31,831 buy
prints against 7,867 sell prints (80/20) on this same tape, because retail overwhelmingly
BUYS in prediction markets. A net-flow signal aggregated over a 30-minute window will
therefore be positive nearly always, for structural reasons that more days of tape do not
remove. Q54's Status line names two gate conditions (settled units < 10; no fillable
seconds-to-minutes exit book). This is a THIRD, and it is the one a longer tape is least
likely to clear on its own.

BINDING MANDATE FOR WHOEVER FIRES THIS (pre-registered here, before any outcome is visible;
the Q52 "mandated tightenings" precedent): if the sign-variation gate ever opens, an ALIVE
reading is NOT admissible on the headline CI alone. The primary must additionally be
decomposed against an ALWAYS-MAJORITY-SIDE benchmark run on the identical entry instants and
prices, and the PAIRED per-unit difference (primary minus benchmark) must itself be block-
bootstrapped by game with a CI > 0. Otherwise a majority arm that is 90%+ of the population
carries the verdict and the minority arm — the only identifying variation S79 actually
claims — contributes nothing. That decomposition is deliberately NOT built today: it cannot
be exercised against reality on a population with zero minority-side entries, and shipping
an untestable second scoring arm would add verdict surface (L41) without adding evidence.

VERDICTS
--------
  GATED-by-adequacy     the adequacy gate is shut — too few settled game units, and/or no
                        sign variation in the scoreable population. This is the sealed
                        state; nothing outcome-dependent is computed. `gate_reasons` names
                        every failing condition, never just the first.
  DEAD-by-population    settled units exist but no entry candidate survives the gates.
  DEAD-by-CI            admissible CI whose lower bound is <= 0, or <= one tick (L27).
  ALIVE-PROVISIONAL     admissible CI strictly > 0 and clearing one tick. PROVISIONAL until
                        an independent `verifier` re-run confirms it (protocol v3 two-agent
                        rule); it may NOT flip `kb/strategies/00-index.md` on its own.

A DEAD verdict recorded cleanly is a full success (CLAUDE.md Stop rules).

Read-only. No network anywhere: settlement is read from already-committed tape through
`core.settlement_sources`, never fetched.

Run:
    python3 scripts/q54_s79_flow_continuation_probe.py
    python3 scripts/q54_s79_flow_continuation_probe.py --json
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement import binary_outcome, is_binary_result  # noqa: E402
from core.settlement_sources import DEFAULT_TAPE_ROOT, resolve_market_results  # noqa: E402
from scripts import q51_maker_fillsim as M  # noqa: E402

TRADES_TAPE = REPO_ROOT / "tape" / "kalshi_trades"
REPORT_PATH = REPO_ROOT / "reports" / "q54_s79_flow_continuation.json"

# --------------------------------------------------------------------------- #
# THE PRE-REGISTRATION. Sealed 2026-08-08, before the gate opened.
# Changing any value here changes PREREG_SHA256 and breaks
# tests/test_q54_s79_flow_continuation_probe.py::test_preregistration_hash_is_sealed.
# That test failing is the intended alarm, not an inconvenience: after the gate opens, a
# spec change is a declaration that the design was tuned with the outcomes visible.
# --------------------------------------------------------------------------- #
PREREGISTRATION: Dict[str, object] = {
    "sealed_on": "2026-08-08",
    "unit": "game",
    "lookback_minutes": 30,
    "decision_grid_minutes": 60,
    "min_signed_flow_contracts": 10.0,
    "max_entry_lag_minutes": 5,
    "entry_price_band": [0.02, 0.98],
    "exit": "hold_to_settlement",
    "fee_legs": 1,
    "fee_side": "taker",
    "min_units": 10,
    "min_minority_side_units": 2,
    "n_boot": 10000,
    "seed": 42,
    "tick": 0.01,
    "min_ticks": 1.0,
}

LOOKBACK_S = float(PREREGISTRATION["lookback_minutes"]) * 60.0
GRID_S = float(PREREGISTRATION["decision_grid_minutes"]) * 60.0
MIN_FLOW = float(PREREGISTRATION["min_signed_flow_contracts"])
MAX_ENTRY_LAG_S = float(PREREGISTRATION["max_entry_lag_minutes"]) * 60.0
BAND_LO, BAND_HI = (float(x) for x in PREREGISTRATION["entry_price_band"])  # type: ignore[union-attr]
MIN_UNITS = int(PREREGISTRATION["min_units"])
MIN_MINORITY_SIDE_UNITS = int(PREREGISTRATION["min_minority_side_units"])
N_BOOT = int(PREREGISTRATION["n_boot"])
SEED = int(PREREGISTRATION["seed"])
TICK = float(PREREGISTRATION["tick"])
MIN_TICKS = float(PREREGISTRATION["min_ticks"])

# The fee side is TAKER: this strategy CROSSES the spread to follow the flow. Imported from
# core.pricing, never a literal (L5 — an S13 draft charged maker fills the taker rate, a 4x
# overcharge that alone ate a 1-cent edge; the mirror error would UNDERcharge here).
FEE_RATE = TAKER_FEE_RATE

# L279 orientation, imported rather than restated so this probe cannot drift from the
# corrected reading: a taker whose own order sits on the BID is a BUYER of YES.
TAKER_BUYS = M.TAKER_BUYS
TAKER_SELLS = M.TAKER_SELLS

SIDE_YES = "yes"
SIDE_NO = "no"

# KEY tokens the SEALED (pre-gate) report is forbidden to carry. The check is deliberately
# KEY-level, not a substring scan of the serialized blob: a blob scan flags the gate note's
# own prose ("nothing outcome-dependent was computed") and any ticker that happens to spell
# a token, which would make the guard noisy and then ignored (L155 — a check that
# over-reports gets disabled, and a disabled check protects nothing). What must be absent is
# a FIELD carrying an outcome-derived value, and a field is a key.
FORBIDDEN_SEALED_KEY_TOKENS = ("pnl", "mean", "ci95", "won", "bootstrap", "profit",
                               "outcome", "settle_result", "admissibility")


def _walk_keys(obj: object) -> List[str]:
    """Every key name appearing anywhere in a nested report structure."""
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_walk_keys(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_walk_keys(v))
    return out


def sealed_report_key_violations(report: Dict[str, object]) -> List[str]:
    """Keys in a SEALED report that would betray an outcome-derived value. Empty list is the
    only acceptable answer while the gate is shut — that emptiness is what makes the refusal
    structural rather than cosmetic."""
    return sorted({k for k in _walk_keys(report)
                   for tok in FORBIDDEN_SEALED_KEY_TOKENS if tok in k.lower()})


def preregistration_sha256(spec: Optional[Dict[str, object]] = None) -> str:
    """A stable digest of the sealed spec. Canonical JSON (sorted keys, compact) so the
    hash tracks VALUES, not dict insertion order or formatting."""
    payload = json.dumps(spec if spec is not None else PREREGISTRATION,
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


PREREG_SHA256 = "SEALED"  # replaced at import time below; literal kept for grep-ability
PREREG_SHA256 = preregistration_sha256()


# --------------------------------------------------------------------------- #
# loading — multi-day, so the probe self-activates when a new trade day lands
# --------------------------------------------------------------------------- #
def trade_day_paths(tape_dir: Path = TRADES_TAPE) -> List[Path]:
    """Every committed `dt=*.jsonl` day of the trade tape, oldest first. Globbed rather
    than pinned to a DAY constant precisely so a newly committed day activates the probe
    without an edit (the whole point of building it before the gate)."""
    return [Path(p) for p in sorted(glob.glob(str(tape_dir / "dt=*.jsonl")))]


def load_all_prints(tape_dir: Path = TRADES_TAPE) -> Dict[str, List[dict]]:
    """ticker -> time-sorted `broker_truth` prints across ALL committed trade days.

    Per-day loading delegates to `scripts.q51_maker_fillsim.load_prints`, so the
    broker_truth-only admission rule and the field mapping are shared with the Q51 probe
    rather than re-implemented (a second copy is how orientation bugs like L279 survive a
    repair in one file)."""
    out: Dict[str, List[dict]] = {}
    for p in trade_day_paths(tape_dir):
        for tk, rows in M.load_prints(path=p).items():
            out.setdefault(tk, []).extend(rows)
    for v in out.values():
        v.sort(key=lambda r: r["ts"])
    return out


def eligible_tickers(prints: Dict[str, List[dict]]) -> List[str]:
    """Sports moneyline markets only (`*GAME`, KXMVE* excluded — L31), sorted."""
    return sorted(tk for tk in prints if M.is_sports_game_market(tk))


def settled_ticker_set(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT
                       ) -> Tuple[FrozenSet[str], Dict[str, object]]:
    """OUTCOME-BLIND settlement membership: which of `tickers` carry a BINARY result.

    Returns the ticker set plus a coverage summary. It deliberately does NOT return, log or
    retain any result VALUE — `is_binary_result` collapses the label to its class, so a
    caller learns THAT a market settled and never HOW. This is the function
    `population_report()` is allowed to call; `outcome_map()` is not."""
    rep = resolve_market_results(tickers, root=root)
    settled = frozenset(t for t, m in rep.resolved.items() if is_binary_result(m.result))
    coverage = {
        "n_requested": rep.requested,
        "n_settled_binary": len(settled),
        "n_non_binary": len(rep.non_binary),
        "n_listed_unsettled": len(rep.listed_unsettled),
        "n_unresolved": len(rep.unresolved),
        "per_source_hits": dict(sorted(rep.per_source_hits.items())),
        "sources_scanned": list(rep.sources_scanned),
        "sources_absent_on_disk": list(rep.sources_absent_on_disk),
    }
    return settled, coverage


def outcome_map(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT) -> Dict[str, int]:
    """ticker -> 1 (yes) / 0 (no). THE ONLY function here that reads an outcome's VALUE.

    Unreachable from `run()` unless the adequacy gate has already passed. Non-binary and
    unknown results are DROPPED, never scored as a loss (L52 — `binary_outcome` returns
    None and the caller must decide, which is decided here as 'exclude')."""
    rep = resolve_market_results(tickers, root=root)
    out: Dict[str, int] = {}
    for t, m in rep.resolved.items():
        o = binary_outcome(m.result)
        if o is not None:
            out[t] = o
    return out


# --------------------------------------------------------------------------- #
# signal + entry enumeration — outcome-independent by construction
# --------------------------------------------------------------------------- #
def signed_flow(prints: Sequence[dict], t_end: float, lookback_s: float = LOOKBACK_S
                ) -> float:
    """Net signed YES flow over (t_end - lookback, t_end]. `+count` for a BUYING taker,
    `-count` for a SELLING one, under the L279 orientation. Sizes stay FLOAT (L47 — a
    fractional `count` is valid venue data and int-coercion silently drops it)."""
    t0 = t_end - lookback_s
    net = 0.0
    for pr in prints:
        ts = pr["ts"]
        if ts <= t0:
            continue
        if ts > t_end:
            break
        c = pr.get("count")
        if not isinstance(c, (int, float)):
            continue
        side = pr.get("taker_book_side")
        if side == TAKER_BUYS:
            net += float(c)
        elif side == TAKER_SELLS:
            net -= float(c)
    return net


def decision_instants(prints: Sequence[dict], grid_s: float = GRID_S) -> List[float]:
    """Whole-grid instants strictly inside a ticker's own print span. The first instant is
    the first grid point at least one full lookback AFTER the ticker's first print, so no
    decision is taken on a truncated lookback window (a partial window would silently mean
    a different signal than the pre-registered one)."""
    if not prints:
        return []
    first, last = prints[0]["ts"], prints[-1]["ts"]
    start = first + LOOKBACK_S
    k0 = int(start // grid_s)
    if k0 * grid_s < start:
        k0 += 1
    out: List[float] = []
    k = k0
    while k * grid_s <= last:
        out.append(float(k * grid_s))
        k += 1
    return out


def first_agreeing_print(prints: Sequence[dict], t0: float, sign: int,
                         max_lag_s: float = MAX_ENTRY_LAG_S) -> Optional[dict]:
    """The first print in [t0, t0 + max_lag] whose aggressor direction agrees with `sign`.

    Entry is an EXECUTED print, never a quote: this is the whole reason the trade tape
    exists (the prime directive forbids filling against a synthesized price)."""
    want = TAKER_BUYS if sign > 0 else TAKER_SELLS
    for pr in prints:
        if pr["ts"] < t0:
            continue
        if pr["ts"] > t0 + max_lag_s:
            return None
        if pr.get("taker_book_side") == want:
            return pr
    return None


def entry_candidates(prints: Dict[str, List[dict]], tickers: Sequence[str]) -> List[dict]:
    """Every pre-registered entry the tape supports, WITHOUT any settlement input.

    A row carries its unit (game), side, entry price, the trade_id it fills against and the
    signal that produced it. No outcome, no P&L — those belong to `score_rows`."""
    rows: List[dict] = []
    for tk in tickers:
        seq = prints.get(tk) or []
        for t in decision_instants(seq):
            flow = signed_flow(seq, t)
            if abs(flow) < MIN_FLOW:
                continue
            sign = 1 if flow > 0 else -1
            pr = first_agreeing_print(seq, t, sign)
            if pr is None:
                continue
            yes_price = float(pr["yes_price"])
            side = SIDE_YES if sign > 0 else SIDE_NO
            entry_price = yes_price if side == SIDE_YES else 1.0 - yes_price
            if not (BAND_LO - 1e-9 <= entry_price <= BAND_HI + 1e-9):
                continue
            rows.append({
                "ticker": tk,
                "unit": M.game_of(tk),
                "decision_ts": t,
                "signed_flow": flow,
                "side": side,
                "entry_price": entry_price,
                "entry_trade_id": pr.get("trade_id"),
                "entry_ts": pr["ts"],
                "price_source_tag": "broker_truth",
            })
    return rows


def population_report(rows: Sequence[dict], settled: FrozenSet[str],
                      coverage: Dict[str, object]) -> Dict[str, object]:
    """The ADEQUACY verdict, computed with no outcome value anywhere in scope.

    `admissible` here is the unit-count half of L41 only. The opposing-cluster half needs
    per-unit means, hence outcomes, hence it can only be evaluated after the gate opens —
    `bootstrap_verdict_admissible` applies it there, and a population that clears the count
    can still be ruled inadmissible then."""
    scoreable = [r for r in rows if r["ticker"] in settled]
    units = sorted({r["unit"] for r in scoreable})
    per_unit = defaultdict(int)
    for r in scoreable:
        per_unit[r["unit"]] += 1
    sides = defaultdict(int)
    for r in scoreable:
        sides[r["side"]] += 1
    n_units = len(units)

    # SIGN VARIATION — the third gate, measured on the SCOREABLE population only. Units are
    # counted per side because a minority arm concentrated in one game cannot be
    # block-bootstrapped (L6/L41 applied to the signal). A side with zero entries is
    # reported as 0, never omitted: an absent key reads as "not measured" (L289/L296).
    units_by_side = {SIDE_YES: set(), SIDE_NO: set()}
    for r in scoreable:
        units_by_side[r["side"]].add(r["unit"])
    per_side_units = {k: len(v) for k, v in units_by_side.items()}
    minority_units = min(per_side_units.values()) if per_side_units else 0
    sign_variation = {
        "units_per_side": dict(sorted(per_side_units.items())),
        "minority_side_units": minority_units,
        "min_minority_side_units": MIN_MINORITY_SIDE_UNITS,
        "ok": minority_units >= MIN_MINORITY_SIDE_UNITS,
    }

    reasons: List[str] = []
    if n_units < MIN_UNITS:
        reasons.append("below_min_units")
    if not sign_variation["ok"]:
        reasons.append("no_sign_variation")
    return {
        "n_entry_candidates_all": len(rows),
        "n_entry_candidates_settled": len(scoreable),
        "n_units": n_units,
        "min_units": MIN_UNITS,
        "units_short_of_floor": max(0, MIN_UNITS - n_units),
        "entries_per_unit": dict(sorted(per_unit.items())),
        "side_split": dict(sorted(sides.items())),
        "sign_variation": sign_variation,
        "settlement_coverage": coverage,
        "gate_reasons": reasons,
        "admissible": not reasons,
    }


# --------------------------------------------------------------------------- #
# scoring — reachable ONLY once the adequacy gate has opened
# --------------------------------------------------------------------------- #
def score_rows(rows: Sequence[dict], outcomes: Dict[str, int]) -> List[dict]:
    """Per-entry realized P&L per contract, net of ONE taker fee at entry.

    payout(1 if the held side wins else 0) - entry_price - fee_per_contract(entry_price).
    Both the entry price and the payout are `broker_truth`; nothing here is synthetic."""
    out: List[dict] = []
    for r in rows:
        o = outcomes.get(r["ticker"])
        if o is None:
            continue
        won = (o == 1) if r["side"] == SIDE_YES else (o == 0)
        entry = float(r["entry_price"])
        fee = fee_per_contract(entry, FEE_RATE)
        row = dict(r)
        row["won"] = bool(won)
        row["fee"] = fee
        row["pnl"] = (1.0 if won else 0.0) - entry - fee
        out.append(row)
    return out


def unit_values(scored: Sequence[dict]) -> Dict[str, List[float]]:
    """game -> its per-entry P&Ls. The bootstrap unit is the GAME (L6), never the entry and
    never the outcome side."""
    uv: Dict[str, List[float]] = defaultdict(list)
    for r in scored:
        uv[r["unit"]].append(float(r["pnl"]))
    return dict(uv)


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def run(tape_dir: Path = TRADES_TAPE, settlement_root: str = DEFAULT_TAPE_ROOT
        ) -> Dict[str, object]:
    prints = load_all_prints(tape_dir)
    tickers = eligible_tickers(prints)
    settled, coverage = settled_ticker_set(tickers, root=settlement_root)
    rows = entry_candidates(prints, tickers)
    pop = population_report(rows, settled, coverage)

    report: Dict[str, object] = {
        "schema_version": "q54_s79_flow_continuation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queue_item": "Q54",
        "strategy": "S79",
        "preregistration": dict(PREREGISTRATION),
        "preregistration_sha256": PREREG_SHA256,
        "trade_days": [p.name for p in trade_day_paths(tape_dir)],
        "n_tickers_with_prints": len(prints),
        "n_sports_game_tickers": len(tickers),
        "population": pop,
        "price_source_tag": "broker_truth",
        "fee_side": "taker",
        "network_calls": 0,
    }

    if not pop["admissible"]:
        # SEALED BRANCH — no outcome value is read, no return is computed, and the report
        # below is asserted free of every FORBIDDEN_SEALED_TOKEN by the acceptance tests.
        report["status"] = "INSUFFICIENT DATA"
        report["verdict"] = "GATED-by-adequacy"
        sv = pop["sign_variation"]
        report["gate_reasons"] = list(pop["gate_reasons"])
        report["gate_note"] = (
            f"gate shut on {pop['gate_reasons']}: {pop['n_units']} settled game units vs "
            f"the L41 floor of {MIN_UNITS} ({pop['units_short_of_floor']} more needed); "
            f"minority-side units {sv['minority_side_units']} vs floor "
            f"{sv['min_minority_side_units']} (units per side {sv['units_per_side']}). "
            "Nothing outcome-dependent was computed: the pre-registration is intact and "
            "this file is unchanged from its sealed state."
        )
        return report

    outcomes = outcome_map([r["ticker"] for r in rows], root=settlement_root)
    scored = score_rows(rows, outcomes)
    uv = unit_values(scored)
    adm = bootstrap_verdict_admissible(uv, min_units=MIN_UNITS)
    boot = block_bootstrap(uv, n_boot=N_BOOT, seed=SEED)
    clears = clears_tick_magnitude(boot["ci95"], tick=TICK, min_ticks=MIN_TICKS)

    if not scored:
        verdict, status = "DEAD-by-population", "NO SCOREABLE ENTRIES"
    elif not adm["admissible"]:
        verdict, status = "DEAD-by-adequacy", "INADMISSIBLE"
    elif boot["ci95"][0] is not None and boot["ci95"][0] > 0 and clears:
        verdict, status = "ALIVE-PROVISIONAL", "OK"
    else:
        verdict, status = "DEAD-by-CI", "OK"

    report["status"] = status
    report["verdict"] = verdict
    report["n_scored"] = len(scored)
    report["bootstrap"] = boot
    report["admissibility"] = adm
    report["clears_tick_magnitude"] = clears
    report["verdict_note"] = (
        "ALIVE-PROVISIONAL is PROVISIONAL: protocol v3's two-agent rule requires an "
        "independent verifier re-run before this may flip kb/strategies/00-index.md."
    )
    return report


def _fmt_human(rep: Dict[str, object]) -> str:
    pop = rep["population"]  # type: ignore[index]
    lines = [
        f"Q54 / S79 aggressor-flow continuation taker — {rep['verdict']} ({rep['status']})",
        f"  pre-registration sha256 : {rep['preregistration_sha256'][:16]}… "
        f"(sealed {PREREGISTRATION['sealed_on']})",
        f"  trade days              : {len(rep['trade_days'])}",  # type: ignore[arg-type]
        f"  sports game tickers     : {rep['n_sports_game_tickers']}",
        f"  entry candidates        : {pop['n_entry_candidates_all']} "
        f"({pop['n_entry_candidates_settled']} on settled markets)",
        f"  bootstrap units (games) : {pop['n_units']} / {pop['min_units']} floor",
        f"  sign variation          : units per side {pop['sign_variation']['units_per_side']}"
        f", minority floor {pop['sign_variation']['min_minority_side_units']}",
    ]
    if rep["verdict"] == "GATED-by-adequacy":
        lines.append(f"  gate                    : {rep['gate_note']}")
    else:
        b = rep["bootstrap"]  # type: ignore[index]
        lines.append(f"  mean / CI95             : {b['mean']} / {b['ci95']}  "
                     f"[broker_truth entry, single taker fee]")
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the raw report JSON")
    ap.add_argument("--no-write", action="store_true", help="do not write the report file")
    args = ap.parse_args(argv)
    rep = run()
    if args.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(_fmt_human(rep))
    if not args.no_write:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"[q54] report -> {os.path.relpath(REPORT_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

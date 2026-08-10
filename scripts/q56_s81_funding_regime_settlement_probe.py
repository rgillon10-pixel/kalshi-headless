#!/usr/bin/env python3
"""Q56 / S81 — Funding-regime-conditioned crypto-hourly directional settlement bias.

PRE-REGISTERED, GATE-SEALED PROBE. Built 2026-08-10, the day S81 was registered
(kalshi-edge-hunter Q21 round #26). It is committed in a state where it CANNOT produce a
P&L number, because its own outcome-blind adequacy path measures the joined population as
below floor — see THE SEAL below.

MECHANISM (kb/strategies/00-index.md S81; LOOP-QUEUE.md Q56)
------------------------------------------------------------
Hyperliquid's hourly perp funding rate is a crowding meter: when it sits BELOW the venue's
0.01%-per-8h interest baseline (L318) the perp is trading at a discount to index — the
crowded side is SHORT; when it goes outright NEGATIVE, shorts are paying longs, the most
crowded short state the tape contains. S81 asks whether that crowd bleeds into Kalshi's
hourly crypto ladder and settles AGAINST itself: i.e. whether, in short-crowded funding
hours, the hourly BTC/ETH price prints ABOVE where the Kalshi ladder is priced, so a taker
buying the near-money UP bracket at a real ask is paid.

Counterparty: the perp momentum crowd bleeding sentiment into Kalshi's hourly crypto book.

THE ARM THIS TAPE ADMITS, AND THE ONE IT DOES NOT
--------------------------------------------------
The registered mechanism is symmetric (crowded long -> bet DOWN, crowded short -> bet UP).
The committed funding tape is NOT: across 3,268 committed coin-hours the rate sits ABOVE
baseline in exactly 1 (measured by this module's own `regime_census`, reported in the
report's `funding_census` block). So only the SHORT-CROWDED arm is testable, every entry is
an UP bet, and a positive result would be (a) scope-limited to that arm and (b) confounded
with realized drift over the sample. That confound is why `pin` (the dead-band regime, which
by L318 carries no crowding information at all) is pre-registered as a CONTROL cell: the same
UP-leg trade in pinned hours is the drift benchmark. The control is a benchmark, never a
strategy, and it is never the headline.

THE SEAL — an outcome-blind adequacy path, and a scoring path unreachable behind it
-----------------------------------------------------------------------------------
The joined population is thin in exactly the cell that matters, so a probe that "reported
INSUFFICIENT DATA" while having already computed the answer would have spent its own
pre-registration (L41 luckiest-cell, with extra steps). The refusal is STRUCTURAL:

  * `population_report()` is outcome-blind by CONSTRUCTION. It receives the settled-ticker
    SET produced by `settled_ticker_set()`, which collapses every result to
    `is_binary_result(...) -> bool` — the label CLASS, never the direction. No function
    reachable from it ever sees a "yes"/"no".
  * `outcome_map()` (the only function that reads a result's VALUE) and `score_rows()` (the
    only one that computes a return) are unreachable from `run()` unless
    `population_report()["admissible"]` is True.
  * `PREREGISTRATION` is hashed into `PREREG_SHA256` and pinned by a test, so tuning a spec
    constant after seeing data cannot be a quiet diff.

The probe self-activates: the first run on which the informative cell clears all three
adequacy gates below, this file computes and reports the verdict with the spec sealed today.

PRE-REGISTERED SPEC (locked 2026-08-10; every value chosen from mechanism, not from returns)
--------------------------------------------------------------------------------------------
  regime label        per (coin, UTC hour) from `tape/hyperliquid_funding/`:
                      `pin` (rate == the 0.01%/8h interest baseline, L318's dead band),
                      `sub_baseline` (0 <= rate < baseline), `negative` (rate < 0),
                      `above_baseline` (rate > baseline). The baseline constant is imported
                      from `scripts/hl_funding_tape_quality.py`, the site that measured it —
                      never re-typed here.
  informative cell    {`sub_baseline`, `negative`} — the short-crowded regimes.
  control cell        {`pin`} — L318's dead band: a pinned hour tells you nothing a
                      neighbouring pinned hour didn't already say. Benchmark only.
  unit (L6)           the REGIME RUN: maximal consecutive-hour block, per coin, of identical
                      label. L318/L324's house rule — never the hour, never the window,
                      because pinned/sub-baseline hours arrive in long autocorrelated runs.
  entry snapshot      one per (coin, event_ticker): the LATEST `crypto_hourly` capture with
                      `current.status == "ok"` whose `captured_at` is STRICTLY BEFORE the
                      event's own `close_time` (the ~5-min-pre-close snapshot). No post-close
                      capture may ever be an entry.
  entry leg           the ADJACENT-ABOVE bracket: the `between` outcome with the smallest
                      `floor_strike` strictly greater than the cap of the bracket containing
                      spot. Single leg. Spot (`coinbase`, tag `synthetic`) is used ONLY to
                      pick which bracket is adjacent — it is never a price, never a fill and
                      never an edge input (Hard rule #1).
  fillability         `core.pricing.is_fillable_ask(yes_ask)` AND `yes_ask <= 0.98` AND a
                      two-sided quote (`yes_bid > 0`). The band excludes the 1-tick-pinned
                      wings where a 1-tick move is a >50% relative move (L27/L249) and where
                      S10 died on a no-fillable-price ladder.
  fee                 `core.pricing.fee_per_contract` at `TAKER_FEE_RATE`, charged ONCE at
                      entry. Settlement costs nothing; there is no exit leg.
  P&L                 payoff (1.0 if the leg's own binary settlement is YES else 0.0) minus
                      entry ask minus entry fee. Prices: `real_ask` (entry), `broker_truth`
                      (settlement, via `core.settlement_sources` — nine declared families,
                      L300, not a hand-rolled read of one).
  bootstrap           `core.bootstrap.bootstrap_verdict_admissible` + `block_bootstrap`,
                      n_boot 10,000, seed 42, blocked by regime run; verdict must also clear
                      `clears_tick_magnitude` (L27).
  adequacy gates      ALL THREE required before any outcome value is read:
                      (1) >= 10 informative regime runs (L41);
                      (2) Kish effective n over those runs >= 10 (L322/L326 — a nominal run
                          count inflated by two long runs is not 10 independent blocks; this
                          is STRICTER than L41 alone and is adopted from the lessons ledger,
                          not invented here, and it is chosen with zero outcome information);
                      (3) >= 10 informative entries carrying a fillable adjacent-above leg.

WHAT A KILL LOOKS LIKE (Q56's own clause): funding does not predict hourly settlement
direction beyond the fee / CI straddles 0 / joinable population below floor. The third is a
DATA-ADEQUACY verdict, not an edge verdict, and it does not flip a registry row on its own.

Pure read-only: no network, no credentials, no writes outside `reports/`.
"""
from __future__ import annotations

import argparse
import glob as globmod
import hashlib
import json
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
    kish_effective_n,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import TAKER_FEE_RATE, fee_per_contract, is_fillable_ask  # noqa: E402
from core.settlement import binary_outcome, is_binary_result  # noqa: E402
from core.settlement_sources import resolve_market_results  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402
from scripts.hl_funding_tape_quality import (  # noqa: E402
    HL_BASELINE_HOURLY_RATE,
    flatten_prints,
    load_lines,
    parse_records,
)

REPORT_PATH = REPO_ROOT / "reports" / "q56_s81_funding_regime_settlement.json"
CRYPTO_GLOB = str(REPO_ROOT / "tape" / "crypto_hourly" / "dt=*.jsonl")
FUNDING_GLOB = str(REPO_ROOT / "tape" / "hyperliquid_funding" / "dt=*.jsonl")

# ─── PRE-REGISTRATION (hash-locked; see PREREG_SHA256) ───────────────────────────────
PREREGISTRATION: Dict[str, object] = {
    "candidate": "S81",
    "queue_item": "Q56",
    "locked": "2026-08-10",
    "informative_regimes": ["sub_baseline", "negative"],
    "control_regimes": ["pin"],
    "direction_for_informative": "up",
    "entry_leg": "adjacent_above_between_bracket",
    "entry_snapshot": "latest_ok_capture_strictly_before_close",
    "max_entry_ask": 0.98,
    "require_two_sided_quote": True,
    "fee_rate_name": "TAKER_FEE_RATE",
    "fee_legs": 1,
    "unit": "regime_run_per_coin",
    "min_units": 10,
    "min_kish_effective_n": 10.0,
    "min_fillable_entries": 10,
    "n_boot": 10000,
    "seed": 42,
    "tick": 0.01,
    "min_ticks": 1.0,
}

MAX_ENTRY_ASK: float = float(PREREGISTRATION["max_entry_ask"])
MIN_UNITS: int = int(PREREGISTRATION["min_units"])
MIN_KISH_EFFECTIVE_N: float = float(PREREGISTRATION["min_kish_effective_n"])
MIN_FILLABLE_ENTRIES: int = int(PREREGISTRATION["min_fillable_entries"])
N_BOOT: int = int(PREREGISTRATION["n_boot"])
SEED: int = int(PREREGISTRATION["seed"])
INFORMATIVE_REGIMES: FrozenSet[str] = frozenset(PREREGISTRATION["informative_regimes"])
CONTROL_REGIMES: FrozenSet[str] = frozenset(PREREGISTRATION["control_regimes"])

# tokens that must NOT appear in a sealed (gate-shut) report — pinned by the tests
FORBIDDEN_SEALED_TOKENS: Tuple[str, ...] = (
    "pnl", "mean", "ci95", "edge_after_fee", "payoff", "verdict_ci", "n_wins",
)


def preregistration_sha256() -> str:
    blob = json.dumps(PREREGISTRATION, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


PREREG_SHA256 = "SEALED"  # replaced at import time below; literal kept for grep-ability
PREREG_SHA256 = preregistration_sha256()


# ─── funding regimes ─────────────────────────────────────────────────────────────────
def regime_label(rate: float, baseline: float = HL_BASELINE_HOURLY_RATE) -> str:
    """L318's three-plus-one states. A rate EXACTLY at the interest baseline is the venue's
    dead band (`pin`) and carries no crowding information; below it the perp trades at a
    discount (crowded short); outright negative is the extreme of that."""
    if rate == baseline:
        return "pin"
    if rate < 0:
        return "negative"
    if rate < baseline:
        return "sub_baseline"
    return "above_baseline"


def _funding_lines(source: object) -> List[Tuple[str, str]]:
    """Accept a glob string, a single path, OR an explicit list of day-file paths (what the
    acceptance tests pass so they never glob a growing family). `load_lines` itself reads a
    list as already-parsed `(path, line)` pairs, so a list of PATHS is expanded here."""
    if isinstance(source, (list, tuple)):
        out: List[Tuple[str, str]] = []
        for item in source:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append((str(item[0]), str(item[1])))
            else:
                out.extend(load_lines(str(item)))
        return out
    return load_lines(source)


def funding_hours(source: object = FUNDING_GLOB) -> Dict[Tuple[str, int], float]:
    """(coin, UTC hour index) -> funding rate, from committed Hyperliquid tape."""
    prints_by_coin = flatten_prints(parse_records(_funding_lines(source)))
    out: Dict[Tuple[str, int], float] = {}
    for coin, prints in prints_by_coin.items():
        for p in prints:
            hour = p.get("hour_index")
            rate = p.get("funding_rate")
            if hour is None or rate is None:
                continue
            out[(coin, int(hour))] = float(rate)
    return out


def regime_census(hours: Dict[Tuple[str, int], float]) -> Dict[str, Dict[str, int]]:
    census: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for (coin, _hour), rate in hours.items():
        census[coin][regime_label(rate)] += 1
    return {c: dict(sorted(v.items())) for c, v in sorted(census.items())}


def regime_runs(hours: Dict[Tuple[str, int], float]) -> Dict[Tuple[str, int], Tuple[str, str]]:
    """(coin, hour) -> (run_id, label). A run is a maximal block of CONSECUTIVE hours with
    the same label on the same coin (L318/L324: a 269-hour pin is one regime, not 269
    observations). A missing hour breaks the run — an unobserved hour is not evidence of
    continuity."""
    out: Dict[Tuple[str, int], Tuple[str, str]] = {}
    by_coin: Dict[str, List[int]] = defaultdict(list)
    for (coin, hour) in hours:
        by_coin[coin].append(hour)
    for coin, hs in by_coin.items():
        prev_hour: Optional[int] = None
        prev_label: Optional[str] = None
        run_index = 0
        for hour in sorted(hs):
            label = regime_label(hours[(coin, hour)])
            if prev_hour is None or hour != prev_hour + 1 or label != prev_label:
                run_index += 1
            out[(coin, hour)] = (f"{coin}-run{run_index:04d}", label)
            prev_hour, prev_label = hour, label
    return out


# ─── crypto-hourly entry snapshots ───────────────────────────────────────────────────
def load_crypto_records(source: object = CRYPTO_GLOB) -> List[dict]:
    paths: List[str]
    if isinstance(source, (list, tuple)):
        paths = [str(p) for p in source]
    else:
        paths = sorted(globmod.glob(str(source)))
    records: List[dict] = []
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    return records


def entry_snapshots(records: Sequence[dict]) -> Dict[Tuple[str, str], dict]:
    """One entry candidate per (coin, event_ticker): the LATEST `ok` capture strictly before
    that event's own close_time. Post-close captures are excluded outright — a capture at or
    after close cannot be an entry, and admitting one would be look-ahead."""
    best: Dict[Tuple[str, str], dict] = {}
    for rec in records:
        current = rec.get("current") or {}
        if current.get("status") != "ok":
            continue
        event = current.get("event_ticker")
        symbol = rec.get("symbol")
        captured_at = rec.get("captured_at")
        close_time = current.get("close_time")
        if not (event and symbol and captured_at and close_time):
            continue
        try:
            captured = parse_iso_utc(captured_at)
            close = parse_iso_utc(close_time)
        except (ValueError, TypeError):
            continue
        if captured >= close:
            continue
        key = (str(symbol), str(event))
        incumbent = best.get(key)
        if incumbent is None or captured > parse_iso_utc(incumbent["captured_at"]):
            best[key] = rec
    return best


def adjacent_above_leg(outcomes: Sequence[dict], spot: float) -> Optional[dict]:
    """The single directional leg: the `between` bracket immediately ABOVE the one that
    contains spot. Returns the outcome dict, or None when the ladder does not bracket spot
    or has no bracket above it."""
    brackets = [o for o in outcomes
                if o.get("strike_type") == "between"
                and o.get("floor_strike") is not None
                and o.get("cap_strike") is not None]
    if not brackets:
        return None
    holding = [o for o in brackets
               if float(o["floor_strike"]) <= spot <= float(o["cap_strike"])]
    if len(holding) != 1:
        return None
    cap = float(holding[0]["cap_strike"])
    above = [o for o in brackets if float(o["floor_strike"]) > cap]
    if not above:
        return None
    return min(above, key=lambda o: float(o["floor_strike"]))


def leg_is_fillable(leg: dict) -> bool:
    """Pre-registered fillability band. Uses the raw resting ask as a COST (never as a
    probability — Hard rule #3 is about probability arithmetic, and no normalisation happens
    here); requires a genuinely two-sided quote so the leg is not a 1-tick-pinned wing."""
    ask = leg.get("yes_ask")
    bid = leg.get("yes_bid")
    if ask is None or bid is None:
        return False
    ask_dollars = float(ask)
    if not is_fillable_ask(ask_dollars):
        return False
    if ask_dollars > MAX_ENTRY_ASK:
        return False
    return float(bid) > 0.0


def candidate_rows(records: Sequence[dict],
                   runs: Dict[Tuple[str, int], Tuple[str, str]]) -> List[dict]:
    """Outcome-blind candidate construction: every (coin, event) entry snapshot, its regime
    run and label, its adjacent-above leg and whether that leg is fillable. NO settlement
    value is read anywhere in this function."""
    rows: List[dict] = []
    for (coin, event), rec in sorted(entry_snapshots(records).items()):
        current = rec.get("current") or {}
        spot_block = rec.get("spot") or {}
        spot = spot_block.get("price")
        if spot is None:
            continue
        captured = parse_iso_utc(rec["captured_at"])
        hour_index = int(captured.timestamp() // 3600)
        run = runs.get((coin, hour_index))
        if run is None:
            continue
        run_id, label = run
        leg = adjacent_above_leg(current.get("outcomes") or [], float(spot))
        rows.append({
            "coin": coin,
            "event_ticker": event,
            "captured_at": rec["captured_at"],
            "close_time": current.get("close_time"),
            "hour_index": hour_index,
            "regime": label,
            "run_id": run_id,
            "cell": ("informative" if label in INFORMATIVE_REGIMES
                     else "control" if label in CONTROL_REGIMES else "excluded"),
            "leg_ticker": (leg or {}).get("ticker"),
            "entry_ask_dollars": (None if leg is None or leg.get("yes_ask") is None
                                  else float(leg["yes_ask"])),
            "leg_yes_bid": (None if leg is None or leg.get("yes_bid") is None
                            else float(leg["yes_bid"])),
            "leg_fillable": bool(leg is not None and leg_is_fillable(leg)),
            "price_source_tag": (leg or {}).get("price_source_tag", "synthetic"),
            "spot_source_tag": spot_block.get("price_source_tag", "synthetic"),
        })
    return rows


# ─── settlement (membership only, on the adequacy path) ──────────────────────────────
def settled_ticker_set(tickers: Sequence[str]) -> Tuple[FrozenSet[str], dict]:
    """Collapse every declared settlement family's answer to MEMBERSHIP: which of these
    tickers carry a BINARY result. The direction is deliberately dropped here — this is the
    only settlement call the adequacy path may make (the seal)."""
    report = resolve_market_results(tickers)
    settled = frozenset(t for t, m in report.resolved.items() if is_binary_result(m.result))
    coverage = {
        "summary": report.coverage_summary(),
        "requested": report.requested,
        "n_resolved": len(report.resolved),
        "n_non_binary": len(report.non_binary),
        "per_source_hits": dict(sorted(report.per_source_hits.items())),
    }
    return settled, coverage


# ─── adequacy (outcome-blind) ────────────────────────────────────────────────────────
def population_report(rows: Sequence[dict], settled: FrozenSet[str],
                      funding_census: Optional[dict] = None) -> dict:
    """THE GATE. Outcome-blind by construction: `settled` is a membership set, never a map
    to a direction. Emits the three pre-registered adequacy gates and their verdict."""
    joinable = [r for r in rows if r["leg_ticker"] in settled]
    cells: Dict[str, List[dict]] = defaultdict(list)
    for row in joinable:
        cells[row["cell"]].append(row)

    def cell_block(name: str) -> dict:
        rs = cells.get(name, [])
        fillable = [r for r in rs if r["leg_fillable"]]
        sizes_by_run: Dict[str, int] = defaultdict(int)
        for r in fillable:
            sizes_by_run[r["run_id"]] += 1
        kish = kish_effective_n(sorted(sizes_by_run.values()))
        return {
            "n_entries": len(rs),
            "n_fillable_entries": len(fillable),
            "n_runs": len({r["run_id"] for r in rs}),
            "n_fillable_runs": len(sizes_by_run),
            "kish": kish,
            "by_regime": dict(sorted({
                lab: sum(1 for r in rs if r["regime"] == lab)
                for lab in {r["regime"] for r in rs}
            }.items())),
            "by_coin": dict(sorted({
                c: sum(1 for r in rs if r["coin"] == c)
                for c in {r["coin"] for r in rs}
            }.items())),
            "run_sizes": sorted(sizes_by_run.values(), reverse=True),
        }

    informative = cell_block("informative")
    control = cell_block("control")
    kish_n = informative["kish"].get("kish_n")
    reasons: List[str] = []
    if informative["n_fillable_runs"] < MIN_UNITS:
        reasons.append("below_min_units")
    if kish_n is None or kish_n < MIN_KISH_EFFECTIVE_N:
        reasons.append("below_min_kish_effective_n")
    if informative["n_fillable_entries"] < MIN_FILLABLE_ENTRIES:
        reasons.append("below_min_fillable_entries")

    return {
        "preregistration_sha256": PREREG_SHA256,
        "n_entry_snapshots": len(rows),
        "n_joinable": len(joinable),
        "n_unjoinable": len(rows) - len(joinable),
        "informative_cell": informative,
        "control_cell": control,
        "excluded_cell": cell_block("excluded"),
        "gates": {
            "min_units": MIN_UNITS,
            "min_kish_effective_n": MIN_KISH_EFFECTIVE_N,
            "min_fillable_entries": MIN_FILLABLE_ENTRIES,
        },
        "gate_reasons": reasons,
        "admissible": not reasons,
        "funding_census": funding_census or {},
    }


# ─── scoring (unreachable while the gate is shut) ────────────────────────────────────
def outcome_map(tickers: Sequence[str]) -> Dict[str, int]:
    """The ONLY function in this module that reads a settlement DIRECTION. Reachable from
    `run()` only after `population_report()["admissible"]` is True."""
    report = resolve_market_results(tickers)
    out: Dict[str, int] = {}
    for ticker, market in report.resolved.items():
        value = binary_outcome(market.result)
        if value is not None:
            out[ticker] = int(value)
    return out


def score_rows(rows: Sequence[dict], outcomes: Dict[str, int]) -> List[dict]:
    """Single-leg taker P&L, one fee at entry, settlement free. Entry price is the resting
    `real_ask`; payoff is `broker_truth`."""
    scored: List[dict] = []
    for row in rows:
        if not row["leg_fillable"]:
            continue
        outcome = outcomes.get(row["leg_ticker"])
        if outcome is None:
            continue
        entry = float(row["entry_ask_dollars"])
        fee = fee_per_contract(entry, TAKER_FEE_RATE)
        payoff = 1.0 if outcome == 1 else 0.0
        scored.append(dict(row, fee_dollars=fee, settled_yes=bool(outcome),
                           pnl_dollars=payoff - entry - fee,
                           price_source_tag_entry="real_ask",
                           price_source_tag_settlement="broker_truth"))
    return scored


def verdict_block(scored: Sequence[dict]) -> dict:
    unit_values: Dict[str, List[float]] = defaultdict(list)
    for row in scored:
        unit_values[row["run_id"]].append(float(row["pnl_dollars"]))
    admissibility = bootstrap_verdict_admissible(unit_values, min_units=MIN_UNITS)
    boot = block_bootstrap(unit_values, n_boot=N_BOOT, seed=SEED)
    return {
        "n_scored": len(scored),
        "bootstrap": boot,
        "admissibility": admissibility,
        "clears_tick_magnitude": clears_tick_magnitude(boot.get("ci95") or [None, None]),
        "kish": kish_effective_n([len(v) for v in unit_values.values()]),
    }


# ─── driver ──────────────────────────────────────────────────────────────────────────
def run(crypto_source: object = CRYPTO_GLOB,
        funding_source: object = FUNDING_GLOB) -> dict:
    hours = funding_hours(funding_source)
    runs = regime_runs(hours)
    records = load_crypto_records(crypto_source)
    rows = candidate_rows(records, runs)
    leg_tickers = sorted({r["leg_ticker"] for r in rows if r["leg_ticker"]})
    settled, coverage = settled_ticker_set(leg_tickers)
    population = population_report(rows, settled, funding_census=regime_census(hours))
    report = {
        "schema_version": "q56_s81_probe.v1",
        "candidate": "S81",
        "queue_item": "Q56",
        "preregistration": PREREGISTRATION,
        "preregistration_sha256": PREREG_SHA256,
        "settlement_coverage": coverage,
        "population": population,
    }
    if not population["admissible"]:
        report["status"] = "SEALED_INSUFFICIENT_DATA"
        report["note"] = (
            "Adequacy gate shut; no settlement direction was read and no P&L was computed. "
            "Gate reasons: " + ", ".join(population["gate_reasons"])
        )
        return report
    joinable = [r for r in rows if r["leg_ticker"] in settled and r["cell"] == "informative"]
    outcomes = outcome_map(sorted({r["leg_ticker"] for r in joinable}))
    scored = score_rows(joinable, outcomes)
    report["status"] = "SCORED"
    report["verdict"] = verdict_block(scored)
    return report


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--crypto-glob", default=CRYPTO_GLOB)
    ap.add_argument("--funding-glob", default=FUNDING_GLOB)
    ap.add_argument("--out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    report = run(args.crypto_glob, args.funding_glob)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    pop = report["population"]
    inf = pop["informative_cell"]
    print(f"Q56/S81 probe — prereg {PREREG_SHA256[:12]}…")
    print(f"  entry snapshots {pop['n_entry_snapshots']} / joinable {pop['n_joinable']}")
    print(f"  informative cell: {inf['n_entries']} entries "
          f"({inf['n_fillable_entries']} fillable) over {inf['n_runs']} runs "
          f"({inf['n_fillable_runs']} fillable runs), kish {inf['kish'].get('kish_n')}")
    print(f"  control cell:     {pop['control_cell']['n_entries']} entries over "
          f"{pop['control_cell']['n_runs']} runs")
    print(f"  status: {report['status']}")
    if report["status"] == "SEALED_INSUFFICIENT_DATA":
        print(f"  gate reasons: {', '.join(pop['gate_reasons'])}")
    else:
        print(f"  verdict: {json.dumps(report['verdict']['bootstrap'])}")
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

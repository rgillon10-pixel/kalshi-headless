#!/usr/bin/env python3
"""Q54 / S79 — ADVERSARIAL SELF-CHECKS on the probe's own DEAD-by-CI verdict.

This file does NOT re-run, re-tune or second-guess the sealed probe
(`scripts/q54_s79_flow_continuation_probe.py`, PREREG_SHA256 `3f56818136b97206…`). It imports
it unchanged, rebuilds exactly the population `run()` builds, and then attacks the verdict the
way a verifier would. It computes NO new bootstrap, NO per-side CI and NO slice mean: a second
scoring arm shipped alongside a DEAD reading would add verdict surface without adding evidence
(L41), and the probe's own BINDING MANDATE conditions the always-majority-side benchmark
decomposition on an ALIVE reading, which this is not.

The five checks (each answers "is the DEAD verdict an artifact of my own construction?"):

  A. SIGN-BOUNDEDNESS (L249). A DEAD verdict on an object whose entry gate bounds the P&L sign
     is an artifact, not news. `core.bootstrap.sign_bounded_objective` is reported verbatim
     beside `bootstrap_verdict_admissible`.
  B. UNIT INTEGRITY (L6). The bootstrap unit must be the GAME, and the two outcome legs of one
     game must not vote as two units. Checked against the VENUE's own `event_ticker` field in
     the settlement tape, not just against the probe's own string split.
  C. FEE (L5/L18/L30). Exactly ONE taker leg, rate imported from `core.pricing`. One row's fee
     is re-derived by hand from the imported constant and the arithmetic printed.
  D. PRICE PROVENANCE (prime directive). Entry = an EXECUTED print that exists on the trade
     tape; exit = the venue's own settlement. No quote, midpoint or synthetic in the P&L path.
  E. POPULATION COMPOSITION — descriptive only.

Read-only. No network. No mutation of tape/ or of the probe.

Run:
    python3 scripts/q54_s79_verdict_selfchecks.py
    python3 scripts/q54_s79_verdict_selfchecks.py --json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.bootstrap import (  # noqa: E402
    bootstrap_verdict_admissible,
    entry_instant_concentration,
    sign_bounded_objective,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement_sources import DEFAULT_TAPE_ROOT, resolve_market_results  # noqa: E402
from scripts import q54_s79_flow_continuation_probe as Q  # noqa: E402

REPORT_PATH = REPO_ROOT / "reports" / "q54_s79_verdict_selfchecks.json"

# Tags that must NOT appear anywhere in the P&L path. `real_ask` is included deliberately:
# S79's entry is an executed print, so even a legitimate-looking quote tag would mean the
# instrument silently changed.
FORBIDDEN_PRICE_TAGS = ("synthetic", "midpoint", "real_ask", "real_bid")


# --------------------------------------------------------------------------- #
# population rebuild — identical to the probe's own run(), no re-parameterization
# --------------------------------------------------------------------------- #
def rebuild(tape_dir: Path = Q.TRADES_TAPE, settlement_root: str = DEFAULT_TAPE_ROOT) -> dict:
    prints = Q.load_all_prints(tape_dir)
    tickers = Q.eligible_tickers(prints)
    settled, coverage = Q.settled_ticker_set(tickers, root=settlement_root)
    rows = Q.entry_candidates(prints, tickers)
    pop = Q.population_report(rows, settled, coverage)
    outcomes = Q.outcome_map([r["ticker"] for r in rows], root=settlement_root)
    scored = Q.score_rows(rows, outcomes)
    uv = Q.unit_values(scored)
    return {"prints": prints, "tickers": tickers, "settled": settled, "rows": rows,
            "pop": pop, "outcomes": outcomes, "scored": scored, "unit_values": uv}


# --------------------------------------------------------------------------- #
# A. sign-boundedness (L249)
# --------------------------------------------------------------------------- #
def check_sign_bounded(uv: Dict[str, List[float]]) -> dict:
    adm = bootstrap_verdict_admissible(uv, min_units=Q.MIN_UNITS)
    sbo = sign_bounded_objective(uv, admissibility=adm)
    return {
        "admissibility": adm,
        "sign_bounded_objective": sbo,
        # A DEAD verdict is evidence only on an object that COULD have disagreed.
        "verdict_is_artifact_of_a_bounded_object": bool(
            sbo.get("one_sided_support") or sbo.get("inadmissibility_is_definitional")),
    }


# --------------------------------------------------------------------------- #
# B. unit integrity (L6)
# --------------------------------------------------------------------------- #
def venue_event_tickers(tickers: Sequence[str], root: str = DEFAULT_TAPE_ROOT
                        ) -> Dict[str, str]:
    """ticker -> the VENUE-reported `event_ticker`, read straight off the settlement tape.

    This is the independent leg of the L6 check: the probe derives its unit by string split
    (`game_of`), so confirming that split against the venue's own event field catches a
    ticker grammar the split mis-reads (the class of bug that would let one game's two legs
    vote as two units)."""
    rep = resolve_market_results(tickers, root=root)
    out: Dict[str, str] = {}
    for t, m in rep.resolved.items():
        raw: Optional[dict] = None
        p = Path(m.path)
        if not p.exists():
            continue
        if p.suffix == ".jsonl":
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue
                    if rec.get("ticker") == t:
                        raw = rec
        else:
            try:
                blob = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                blob = {}
            mk = (blob.get("markets") or {}).get(t)
            if isinstance(mk, dict):
                raw = mk
        if raw and raw.get("event_ticker"):
            out[t] = str(raw["event_ticker"])
    return out


def check_unit_integrity(scored: Sequence[dict], root: str = DEFAULT_TAPE_ROOT) -> dict:
    tickers = sorted({r["ticker"] for r in scored})
    ev = venue_event_tickers(tickers, root=root)
    split_mismatch = sorted(t for t, e in ev.items() if Q.M.game_of(t) != e)
    unit_of_ticker: Dict[str, set] = defaultdict(set)
    for r in scored:
        unit_of_ticker[r["unit"]].add(r["ticker"])
    # A unit key that IS a full market ticker would mean an outcome leg voting as a unit.
    unit_equals_a_ticker = sorted(u for u in unit_of_ticker if u in set(tickers))
    multi_leg_units = {u: sorted(v) for u, v in unit_of_ticker.items() if len(v) > 1}
    return {
        "n_scored_tickers": len(tickers),
        "n_units": len(unit_of_ticker),
        "n_tickers_with_a_venue_event_ticker": len(ev),
        "unit_vs_venue_event_ticker_mismatches": split_mismatch,
        "unit_key_that_is_itself_a_market_ticker": unit_equals_a_ticker,
        "n_units_carrying_both_outcome_legs": len(multi_leg_units),
        "units_carrying_both_outcome_legs": multi_leg_units,
        "ok": (not split_mismatch and not unit_equals_a_ticker),
    }


# --------------------------------------------------------------------------- #
# C. fee (L5/L18/L30)
# --------------------------------------------------------------------------- #
def check_fee(scored: Sequence[dict]) -> dict:
    """Every scored row pays exactly ONE taker fee, at the IMPORTED rate.

    `hand_derivation` recomputes one row's fee from the fee formula and the imported
    constant, with the intermediate products, so the number in the finding is checkable by
    eye and not by trust."""
    bad_fee = [r for r in scored
               if abs(r["fee"] - fee_per_contract(r["entry_price"], TAKER_FEE_RATE)) > 1e-12]
    # single-leg identity: pnl == payout - entry - ONE fee  (a second leg would break it)
    bad_legs = [r for r in scored
                if abs(r["pnl"] - ((1.0 if r["won"] else 0.0) - r["entry_price"] - r["fee"]))
                > 1e-12]
    ex = max(scored, key=lambda r: r["fee"]) if scored else None
    hand = None
    if ex is not None:
        p = float(ex["entry_price"])
        raw = TAKER_FEE_RATE * p * (1.0 - p)
        hand = {
            "ticker": ex["ticker"],
            "entry_trade_id": ex["entry_trade_id"],
            "entry_price": p,
            "imported_TAKER_FEE_RATE": TAKER_FEE_RATE,
            "rate_times_p_times_1_minus_p": raw,
            "times_100": raw * 100.0,
            "ceil_to_cent_over_100": math.ceil(raw * 100.0) / 100.0,
            "fee_per_contract_from_core_pricing": fee_per_contract(p, TAKER_FEE_RATE),
            "fee_charged_by_probe": ex["fee"],
            "agrees": abs(math.ceil(raw * 100.0) / 100.0 - ex["fee"]) < 1e-12,
        }
    return {
        "fee_rate_used": Q.FEE_RATE,
        "fee_rate_is_the_imported_taker_rate": Q.FEE_RATE == TAKER_FEE_RATE,
        "fee_legs_pre_registered": Q.PREREGISTRATION["fee_legs"],
        "n_rows_with_a_wrong_fee": len(bad_fee),
        "n_rows_violating_the_single_leg_identity": len(bad_legs),
        "total_fees_charged": round(sum(r["fee"] for r in scored), 6),
        "distinct_fee_values": sorted({round(r["fee"], 6) for r in scored}),
        "hand_derivation": hand,
        "ok": not bad_fee and not bad_legs and Q.FEE_RATE == TAKER_FEE_RATE,
    }


# --------------------------------------------------------------------------- #
# D. price provenance (prime directive)
# --------------------------------------------------------------------------- #
def tape_trade_ids(tape_dir: Path = Q.TRADES_TAPE) -> Dict[str, dict]:
    """trade_id -> the raw `broker_truth` tape line. Read from the RAW jsonl, so an entry is
    proved to be a real executed print rather than a row the probe minted."""
    out: Dict[str, dict] = {}
    for p in Q.trade_day_paths(tape_dir):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("price_source_tag") != "broker_truth":
                    continue
                tid = rec.get("trade_id")
                if tid:
                    out[str(tid)] = rec
    return out


def _all_string_values(obj: object) -> List[str]:
    out: List[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_all_string_values(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_all_string_values(v))
    elif isinstance(obj, str):
        out.append(obj)
    return out


def forbidden_price_tags_in(report: object) -> List[str]:
    """Any forbidden price-source token appearing anywhere in a report."""
    blob = " ".join(_all_string_values(report)).lower()
    return sorted({t for t in FORBIDDEN_PRICE_TAGS if t in blob})


def check_price_provenance(scored: Sequence[dict], probe_report: dict,
                           tape_dir: Path = Q.TRADES_TAPE,
                           root: str = DEFAULT_TAPE_ROOT) -> dict:
    ids = tape_trade_ids(tape_dir)
    missing = [r["entry_trade_id"] for r in scored if str(r["entry_trade_id"]) not in ids]
    price_mismatch = []
    for r in scored:
        raw = ids.get(str(r["entry_trade_id"]))
        if raw is None:
            continue
        yp = float(raw["yes_price"])
        expect = yp if r["side"] == Q.SIDE_YES else 1.0 - yp
        if abs(expect - float(r["entry_price"])) > 1e-9:
            price_mismatch.append(r["entry_trade_id"])
    bad_tag = [r["entry_trade_id"] for r in scored if r["price_source_tag"] != "broker_truth"]
    raw_tags = sorted({str(ids[str(r["entry_trade_id"])].get("price_source_tag"))
                       for r in scored if str(r["entry_trade_id"]) in ids})
    rep = resolve_market_results(sorted({r["ticker"] for r in scored}), root=root)
    settle_tags = sorted({m.price_source_tag for m in rep.resolved.values()})
    settle_sources = dict(sorted(Counter(m.source for m in rep.resolved.values()).items()))
    return {
        "n_entries": len(scored),
        "n_entry_prints_not_found_on_the_trade_tape": len(missing),
        "n_entry_prices_disagreeing_with_the_tape_print": len(price_mismatch),
        "n_rows_not_tagged_broker_truth": len(bad_tag),
        "entry_price_source_tags_on_the_raw_tape": raw_tags,
        "settlement_price_source_tags": settle_tags,
        "settlement_sources_used": settle_sources,
        "forbidden_price_tags_in_probe_report": forbidden_price_tags_in(probe_report),
        "ok": (not missing and not price_mismatch and not bad_tag
               and raw_tags == ["broker_truth"] and settle_tags == ["broker_truth"]
               and not forbidden_price_tags_in(probe_report)),
    }


# --------------------------------------------------------------------------- #
# E. population composition — DESCRIPTIVE ONLY (no CI, no slice mean)
# --------------------------------------------------------------------------- #
def describe_population(built: dict) -> dict:
    scored = built["scored"]
    rows = built["rows"]
    pop = built["pop"]
    per_unit = Counter(r["unit"] for r in scored)
    per_side = Counter(r["side"] for r in scored)
    units_by_side = defaultdict(set)
    days = Counter()
    for r in scored:
        units_by_side[r["side"]].add(r["unit"])
        days[datetime.fromtimestamp(r["entry_ts"], timezone.utc).date().isoformat()] += 1
    conc = entry_instant_concentration([r["decision_ts"] for r in scored],
                                       unit_labels=[r["unit"] for r in scored])
    return {
        "n_entry_candidates_all": len(rows),
        "n_entry_candidates_settled": pop["n_entry_candidates_settled"],
        "n_scored": len(scored),
        "n_units": len(per_unit),
        "entries_per_side": dict(sorted(per_side.items())),
        "units_per_side": {k: len(v) for k, v in sorted(units_by_side.items())},
        "minority_side_units": min(len(v) for v in units_by_side.values()) if units_by_side else 0,
        "entries_per_unit_min": min(per_unit.values()) if per_unit else 0,
        "entries_per_unit_median": sorted(per_unit.values())[len(per_unit) // 2] if per_unit else 0,
        "entries_per_unit_max": max(per_unit.values()) if per_unit else 0,
        "entries_per_unit": dict(sorted(per_unit.items())),
        "entry_days": dict(sorted(days.items())),
        "n_entry_days": len(days),
        "entry_instant_concentration": conc,
        "trade_days": [p.name for p in Q.trade_day_paths()],
    }


# --------------------------------------------------------------------------- #
# run
# --------------------------------------------------------------------------- #
def run(tape_dir: Path = Q.TRADES_TAPE, settlement_root: str = DEFAULT_TAPE_ROOT) -> dict:
    probe_report = Q.run(tape_dir=tape_dir, settlement_root=settlement_root)
    built = rebuild(tape_dir, settlement_root)
    checks = {
        "A_sign_boundedness": check_sign_bounded(built["unit_values"]),
        "B_unit_integrity": check_unit_integrity(built["scored"], root=settlement_root),
        "C_fee": check_fee(built["scored"]),
        "D_price_provenance": check_price_provenance(built["scored"], probe_report,
                                                     tape_dir=tape_dir, root=settlement_root),
        "E_population": describe_population(built),
    }
    return {
        "schema_version": "q54_s79_verdict_selfchecks.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queue_item": "Q54",
        "strategy": "S79",
        "probe_preregistration_sha256": Q.PREREG_SHA256,
        "probe_verdict": probe_report.get("verdict"),
        "probe_bootstrap": probe_report.get("bootstrap"),
        "probe_clears_tick_magnitude": probe_report.get("clears_tick_magnitude"),
        "price_source_tag": "broker_truth",
        "fee_side": "taker",
        "network_calls": 0,
        "checks": checks,
        "all_checks_ok": bool(
            not checks["A_sign_boundedness"]["verdict_is_artifact_of_a_bounded_object"]
            and checks["B_unit_integrity"]["ok"] and checks["C_fee"]["ok"]
            and checks["D_price_provenance"]["ok"]),
    }


def _fmt_human(rep: dict) -> str:
    c = rep["checks"]
    a, b, f, d, e = (c["A_sign_boundedness"], c["B_unit_integrity"], c["C_fee"],
                     c["D_price_provenance"], c["E_population"])
    sbo = a["sign_bounded_objective"]
    return "\n".join([
        f"Q54 / S79 verdict self-checks — probe verdict {rep['probe_verdict']}",
        f"  bootstrap               : mean {rep['probe_bootstrap']['mean']:.6f} "
        f"CI95 {rep['probe_bootstrap']['ci95']} n_units {rep['probe_bootstrap']['n_units']}",
        f"  A sign-boundedness      : verdict_bearing={sbo['verdict_bearing']} "
        f"one_sided={sbo['one_sided_support']} "
        f"definitional={sbo['inadmissibility_is_definitional']} "
        f"(+{sbo['n_positive']}/-{sbo['n_negative']}/0:{sbo['n_zero']})",
        f"  B unit integrity        : ok={b['ok']} units={b['n_units']} "
        f"tickers={b['n_scored_tickers']} both-leg units={b['n_units_carrying_both_outcome_legs']}",
        f"  C fee                   : ok={f['ok']} rate={f['fee_rate_used']} "
        f"legs={f['fee_legs_pre_registered']} distinct fees {f['distinct_fee_values']}",
        f"  D price provenance      : ok={d['ok']} entry tags {d['entry_price_source_tags_on_the_raw_tape']} "
        f"settlement tags {d['settlement_price_source_tags']}",
        f"  E population            : {e['n_scored']} scored / {e['n_units']} units / "
        f"sides {e['entries_per_side']} / units per side {e['units_per_side']} / "
        f"{e['n_entry_days']} entry days",
        f"  all_checks_ok           : {rep['all_checks_ok']}",
    ])


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
        print(f"[q54-selfcheck] report -> {os.path.relpath(REPORT_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

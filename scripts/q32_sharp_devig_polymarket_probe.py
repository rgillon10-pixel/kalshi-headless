#!/usr/bin/env python3
"""q32_sharp_devig_polymarket_probe.py — Q32: sharp-sportsbook de-vig vs Polymarket sports price.

LOOP-QUEUE.md Q32 (regime-change follow-up, 2026-07-15). S7/S7c proved the sharp-line-de-vig
edge is DEAD against KALSHI fills (2026-07-04 verdict, block-bootstrap CI [-0.0245, -0.0225],
strictly < 0) — but that tested the WRONG venue: Kalshi's sports books are already sharp. Now
that Polymarket is a tradeable venue, the open question is whether Polymarket's (plausibly
softer, more retail/crypto-native) sports price is systematically off the same sharp de-vig by
enough to clear Polymarket's LOWER sports taker fee (0.03–0.05 vs Kalshi's 0.07).

── STATUS: PROBE-PREP, NOT A VERDICT ──────────────────────────────────────────────────────────
This probe needs TWO legs that do not yet exist in tape together:
  (a) the odds-api de-vig-fair leg — present in `tape/sports_pairs/*.jsonl` ONLY when
      `ODDS_API_KEY` is in the VPS env (Q1). Until then every game carries
      `odds_leg: {"status": "blocked_key"}` and there is nothing to join.
  (b) a Polymarket per-game sports MONEYLINE leg — NO such tape family exists yet (Q33 is
      BLOCKED on Ryan's Polymarket-US KYC credentials). This script therefore reads it from an
      INJECTABLE `--polymarket-tape-dir`; the ONE thing that needs pointing at real data once
      Q33 (or an international-book equivalent) lands is that path.
Because BOTH legs are blocked, this file is written + offline-tested against FIXTURES so it
fires the moment both legs land. It makes NO edge claim, writes NO findings/ verdict, and
registers NOTHING in kb/strategies. When run against real, incomplete tape it prints an honest
"insufficient data" line and exits cleanly — it NEVER fabricates a bootstrap from empty input.

── EXPECTED SCHEMA for the Polymarket sports leg (the (b) leg this script consumes) ───────────
One JSONL file per day under `--polymarket-tape-dir` (e.g. `tape/polymarket_sports_pairs/`),
one line per matched (game, outcome). Shape modeled on `collection/polymarket_pairs.py`'s records
(bitemporal `captured_at`, honest match status, real CLOB `real_ask` — never `outcomePrices`):

  {
    "schema_version": "polymarket_sports_pairs.v0",   # v0 = proposed, not yet captured
    "capture_id": "20260716T201742Z",                 # dedupe key (keep most-recent per join key)
    "captured_at": "2026-07-16T20:17:42+00:00",        # bitemporal — provenance/persistence
    "kalshi_event_ticker": "KXAFLGAME-26JUL100540NMKCOL",   # GAME join key (== sports_pairs event_ticker)
    "kalshi_ticker": "KXAFLGAME-26JUL100540NMKCOL-COL",     # OUTCOME join key (== sports_pairs outcome.ticker)
    "outcome_name": "Collingwood Magpies",
    "poly_yes_ask": 0.55,                              # the fillable object, tag real_ask
    "price_source_tag": "real_ask",                    # MUST be real_ask (a book BBO, not a mid/last)
    "polymarket_market_id": "0xabc...",                 # provenance
    "resolution_equivalent": true,                      # binding gate — see below
    "resolution_equivalence_note": "kickoff/regulation-time/OT + UMA-vs-book source checked"
  }

`resolution_equivalent` is LOAD-BEARING (Q31/Q32 binding gate + regime note item 3): include a
(game, outcome) in the edge population ONLY if the odds-api game definition and the Polymarket
market resolve on structurally identical criteria (kickoff, regulation-time vs incl.-OT, the
UMA-oracle-vs-sharp-book source). A non-equivalent pair is a directional bet, not an edge — it is
EXCLUDED and COUNTED, never assumed equivalent. The collector that eventually writes this leg
owns setting the flag honestly (mirroring polymarket_pairs' `unmatched`/`ambiguous` refusal to
force a match); this probe trusts the flag but reports how many it dropped for it.

── SIGN CONVENTION (documented; a modeling choice to re-settle when real data lands) ──────────
Per the Q32 spec the metric is:
    edge_after_fee = poly_yes_ask − devig_fair − polymarket_sports_fee(poly_yes_ask)
i.e. how much Polymarket's YES ask sits ABOVE the sharp de-vigged fair probability, net of the
Polymarket sports fee. Positive ⇒ Polymarket YES is priced RICH vs sharp fair by more than the
fee (a sell-the-overpriced-YES read); the mirror buy-the-cheap-side direction and the fact that
Polymarket's NO-token book is NOT currently captured (Q31 tape-coverage gap) are the two things
to settle against the real leg before any positivity is called an actionable fill. The de-vig
anchor is and stays `synthetic` (Hard Rule #1 — a de-vig is a model, never a fill); the fillable
object is Polymarket's `real_ask` net of the Polymarket fee via core.pricing (never hand-rolled).

── PROVENANCE CAVEAT (stated on every number, not baked into an assumption) ───────────────────
The Polymarket leg is `real_ask` off whatever venue the leg-writer captured. Our existing
Polymarket tape is the INTERNATIONAL CLOB (clob.polymarket.com), NOT Polymarket-US (QCEX) — the
venue Ryan actually fills. If this runs on the international book, every number carries the
"not a Polymarket-US fill" caveat (regime note item 2). This script does not assume which book
it ends up pointed at; it prints the caveat and echoes back the tag it actually saw.

READ-ONLY over tape. Fees ONLY from core.pricing. Block-bootstrap by GAME (L6 — outcomes within
a game share the same de-vig and market state, they are not independent draws). Run:
    python scripts/q32_sharp_devig_polymarket_probe.py --polymarket-tape-dir tape/polymarket_sports_pairs
    python scripts/q32_sharp_devig_polymarket_probe.py --polymarket-tape-dir <dir> --n-boot 10000 --json-out /tmp/q32.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    POLYMARKET_SPORTS_TAKER_RATE,
    POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC,
    polymarket_fee_per_contract,
)

SPORTS_PAIRS_GLOB = str(REPO_ROOT / "tape" / "sports_pairs" / "dt=*.jsonl")
# The Polymarket sports leg has NO default tape family yet (Q33 blocked) — the CLI REQUIRES
# --polymarket-tape-dir so it is never silently hardcoded to a family name that doesn't exist.
POLY_SCHEMA_VERSION = "polymarket_sports_pairs.v0"

PRICE_TICK = 0.01
MIN_CI_UNITS = 10  # shared data-adequacy floor (matches bootstrap_verdict_admissible default)


# --------------------------------------------------------------------------- #
# leg (a): the odds-api de-vig-fair anchor, off sports_pairs tape (tag synthetic)
# --------------------------------------------------------------------------- #
def load_devig_fair_by_ticker(tape_glob: str = SPORTS_PAIRS_GLOB
                               ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Read every `sports_pairs` game with a MATCHED odds_leg and return
    `{kalshi_outcome_ticker: {"fair_prob", "outcome_name", "event_ticker", "series"}}`.

    Games are deduped by `event_ticker`, keeping the most-recent `capture_id` (a game is
    re-captured hour over hour; we want its latest de-vig anchor). Only `odds_leg.status ==
    "matched"` games contribute, and within them only outcomes whose de-vig `fair_prob` is
    non-null (an unmapped outcome stays out of the join, counted in meta). fair_prob is
    `synthetic` — a model, never a fill (Hard Rule #1).
    """
    by_event: Dict[str, Dict] = {}
    for path in sorted(glob.glob(tape_glob)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if not str(rec.get("schema_version", "")).startswith("sports_pairs"):
                    continue
                key = rec.get("event_ticker")
                if not key:
                    continue
                prev = by_event.get(key)
                if prev is None or str(rec.get("capture_id", "")) > str(prev.get("capture_id", "")):
                    by_event[key] = rec

    fair_by_ticker: Dict[str, Dict[str, Any]] = {}
    n_games_total = len(by_event)
    n_games_matched = 0
    n_outcomes_with_fair = 0
    for event_ticker, rec in by_event.items():
        odds_leg = rec.get("odds_leg") or {}
        if odds_leg.get("status") != "matched":
            continue
        n_games_matched += 1
        series = rec.get("series")
        for paired in odds_leg.get("outcomes", []):
            fair = paired.get("fair_prob")
            tkr = paired.get("kalshi_ticker")
            if fair is None or not tkr:
                continue
            fair_by_ticker[tkr] = {
                "fair_prob": float(fair),
                "outcome_name": paired.get("kalshi_outcome_name"),
                "event_ticker": event_ticker,
                "series": series,
            }
            n_outcomes_with_fair += 1
    meta = {
        "n_games_total": n_games_total,
        "n_games_matched_odds": n_games_matched,
        "n_outcomes_with_fair": n_outcomes_with_fair,
    }
    return fair_by_ticker, meta


# --------------------------------------------------------------------------- #
# leg (b): the Polymarket per-game sports moneyline leg (tag real_ask)
# --------------------------------------------------------------------------- #
def _poly_ask(rec: Dict[str, Any]) -> Optional[float]:
    """Read the Polymarket YES ask off a leg record. Canonical field is top-level
    `poly_yes_ask`; tolerate a nested `polymarket.{poly_yes_ask,best_ask}` shape too (the
    eventual collector may nest its book block the way polymarket_pairs does). Returns None if
    absent."""
    v = rec.get("poly_yes_ask")
    if v is None:
        pm = rec.get("polymarket") or {}
        v = pm.get("poly_yes_ask", pm.get("best_ask"))
    return float(v) if v is not None else None


def load_polymarket_sports_leg(poly_tape_dir: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Read the Polymarket sports leg JSONL under `poly_tape_dir`, deduped by `kalshi_ticker`
    keeping the most-recent `capture_id`. Returns (records, meta). Missing dir / no files is an
    honest empty result (the self-activating guard, not a crash)."""
    by_ticker: Dict[str, Dict] = {}
    n_lines = 0
    n_files = 0
    for path in sorted(glob.glob(str(Path(poly_tape_dir) / "dt=*.jsonl"))):
        n_files += 1
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                n_lines += 1
                key = rec.get("kalshi_ticker")
                if not key:
                    continue
                prev = by_ticker.get(key)
                if prev is None or str(rec.get("capture_id", "")) > str(prev.get("capture_id", "")):
                    by_ticker[key] = rec
    meta = {"n_poly_files": n_files, "n_poly_lines": n_lines, "n_poly_tickers": len(by_ticker)}
    return list(by_ticker.values()), meta


# --------------------------------------------------------------------------- #
# join — game+outcome, resolution-equivalence gated, block unit = GAME
# --------------------------------------------------------------------------- #
def join_edges(fair_by_ticker: Dict[str, Dict[str, Any]], poly_records: List[Dict[str, Any]],
               *, sports_rate: float = POLYMARKET_SPORTS_TAKER_RATE
               ) -> Tuple[Dict[str, List[float]], Dict[str, Any]]:
    """Join the Polymarket real_ask leg to the de-vig-fair anchor on `kalshi_ticker`, apply the
    resolution-equivalence gate, and return `{event_ticker: [edge_after_fee, ...]}` grouped by
    GAME (L6) plus honest exclusion counts.

    edge_after_fee = poly_yes_ask − devig_fair − polymarket_fee(poly_yes_ask, sports_rate)
    (see the module SIGN CONVENTION note). A pair is included ONLY if: it has a de-vig fair
    anchor, a numeric real_ask, AND `resolution_equivalent` is True. Every other pair is dropped
    into a counted bucket, never assumed in.
    """
    edges_by_game: Dict[str, List[float]] = {}
    n_no_fair = 0            # Polymarket outcome with no sharp de-vig anchor (can't score)
    n_not_equivalent = 0     # resolution_equivalent False — a directional bet, excluded
    n_missing_flag = 0       # resolution_equivalent absent — treated as NOT equivalent (never assumed)
    n_no_ask = 0             # no numeric real_ask
    n_joined = 0
    tags_seen: Dict[str, int] = {}
    for rec in poly_records:
        tkr = rec.get("kalshi_ticker")
        anchor = fair_by_ticker.get(tkr) if tkr else None
        if anchor is None:
            n_no_fair += 1
            continue
        if "resolution_equivalent" not in rec:
            n_missing_flag += 1
            continue
        if rec.get("resolution_equivalent") is not True:
            n_not_equivalent += 1
            continue
        ask = _poly_ask(rec)
        if ask is None:
            n_no_ask += 1
            continue
        tag = rec.get("price_source_tag", "untagged")
        tags_seen[tag] = tags_seen.get(tag, 0) + 1
        fee = polymarket_fee_per_contract(ask, rate=sports_rate)
        edge = ask - anchor["fair_prob"] - fee
        edges_by_game.setdefault(anchor["event_ticker"], []).append(edge)
        n_joined += 1
    meta = {
        "n_joined_outcomes": n_joined,
        "n_joined_games": len(edges_by_game),
        "n_excluded_no_fair_anchor": n_no_fair,
        "n_excluded_not_resolution_equivalent": n_not_equivalent,
        "n_excluded_missing_equivalence_flag": n_missing_flag,
        "n_excluded_no_real_ask": n_no_ask,
        "price_source_tags_seen": tags_seen,
        "sports_rate": sports_rate,
    }
    return edges_by_game, meta


# --------------------------------------------------------------------------- #
# one bootstrap scenario (a given sports fee rate) routed through both gates
# --------------------------------------------------------------------------- #
def bootstrap_scenario(edges_by_game: Dict[str, List[float]], *, n_boot: int, seed: int = 42
                       ) -> Dict[str, Any]:
    """Block-bootstrap by GAME and route the CI through both verdict gates
    (bootstrap_verdict_admissible + clears_tick_magnitude). `alive` requires an admissible,
    strictly-positive, tick-clearing CI — the same bar the binding directive sets."""
    boot = block_bootstrap(edges_by_game, n_boot=n_boot, seed=seed)
    adm = bootstrap_verdict_admissible(edges_by_game, min_units=MIN_CI_UNITS)
    ci = boot["ci95"]
    lo = ci[0]
    clears = clears_tick_magnitude(ci, tick=PRICE_TICK, min_ticks=1.0)
    ci_strictly_positive = lo is not None and lo > 0.0
    alive = bool(adm["admissible"] and ci_strictly_positive and clears)
    return {
        "mean": boot["mean"], "ci95": ci,
        "n_units": boot["n_units"], "n_obs": boot["n_obs"],
        "admissible": adm["admissible"], "admissibility": adm,
        "ci_strictly_positive": ci_strictly_positive,
        "clears_tick_magnitude": clears,
        "alive": alive,
    }


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #
def run_probe(sports_glob: str, poly_tape_dir: str, *, n_boot: int = 10000, seed: int = 42
              ) -> Dict[str, Any]:
    """End-to-end (pure over its inputs; both legs read read-only). Returns a report dict.
    `data_adequate` is False (with `insufficient_reason`) whenever there is nothing to bootstrap
    — the self-activating guard: no fabricated CI from missing/empty legs."""
    fair_by_ticker, fair_meta = load_devig_fair_by_ticker(sports_glob)
    poly_records, poly_meta = load_polymarket_sports_leg(poly_tape_dir)

    # Primary scenario = conservative rate; sensitivity = the optimistic low end of 0.03–0.05.
    edges_primary, join_primary = join_edges(
        fair_by_ticker, poly_records, sports_rate=POLYMARKET_SPORTS_TAKER_RATE)
    edges_optimistic, join_optimistic = join_edges(
        fair_by_ticker, poly_records, sports_rate=POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC)

    report: Dict[str, Any] = {
        "fair_meta": fair_meta,
        "poly_meta": poly_meta,
        "join_meta_conservative": join_primary,
        "join_meta_optimistic": join_optimistic,
        "sports_rate_conservative": POLYMARKET_SPORTS_TAKER_RATE,
        "sports_rate_optimistic": POLYMARKET_SPORTS_TAKER_RATE_OPTIMISTIC,
        "n_boot": n_boot,
        "price_source_tag": "mixed (poly real_ask − devig synthetic − poly fee)",
        "provenance_caveat": (
            "Polymarket leg is real_ask off the venue the leg-writer captured; our existing "
            "Polymarket tape is the INTERNATIONAL CLOB, NOT Polymarket-US (QCEX) — if this ran "
            "on the international book these numbers are NOT a Polymarket-US fill (regime note 2)."
        ),
    }

    # ── self-activating data-adequacy guard: never bootstrap missing/empty legs ──
    if not fair_by_ticker:
        report["data_adequate"] = False
        report["insufficient_reason"] = (
            "no de-vig-fair anchor in tape/sports_pairs (odds_leg still blocked_no_key — Q1). "
            "Nothing to join.")
        return report
    if not poly_records:
        report["data_adequate"] = False
        report["insufficient_reason"] = (
            "no Polymarket sports leg found under --polymarket-tape-dir (Q33 leg not captured). "
            "Nothing to join.")
        return report
    if join_primary["n_joined_outcomes"] == 0:
        report["data_adequate"] = False
        report["insufficient_reason"] = (
            "0 resolution-equivalent (game, outcome) pairs joined (excluded: "
            f"{join_primary['n_excluded_no_fair_anchor']} no-fair-anchor, "
            f"{join_primary['n_excluded_not_resolution_equivalent']} not-equivalent, "
            f"{join_primary['n_excluded_missing_equivalence_flag']} missing-flag, "
            f"{join_primary['n_excluded_no_real_ask']} no-real-ask). Nothing to bootstrap.")
        return report

    report["data_adequate"] = True
    report["scenario_conservative"] = bootstrap_scenario(edges_primary, n_boot=n_boot, seed=seed)
    report["scenario_optimistic"] = bootstrap_scenario(edges_optimistic, n_boot=n_boot, seed=seed)

    # A verdict is only quotable if the bootstrap has enough distinct game units to be testable.
    n_units = report["scenario_conservative"]["n_units"]
    report["testable"] = n_units >= MIN_CI_UNITS
    if not report["testable"]:
        report["verdict"] = (
            f"UNTESTABLE (data-adequacy: {n_units} < {MIN_CI_UNITS} game units — a positive-"
            "looking CI here is a resampling artifact, not a verdict)")
    elif report["scenario_conservative"]["alive"]:
        report["verdict"] = (
            "ALIVE at the conservative (0.05) sports fee — CI strictly > 0, admissible, clears "
            "the 1-tick gate. CANDIDATE only: owes the provenance caveat + two-agent verifier.")
    else:
        report["verdict"] = (
            "DEAD at the conservative (0.05) sports fee — CI fails the >0/admissible/tick bar "
            "(soft-flow hypothesis not supported at fillable Polymarket prices net of fee).")
    return report


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: Any) -> str:
    if not ci or ci[0] is None:
        return "[   None ,   None ]"
    return f"[{ci[0]:+.5f}, {ci[1]:+.5f}]"


def _print_scenario(label: str, rate: float, s: Dict[str, Any]) -> None:
    mean = "None" if s["mean"] is None else f"{s['mean']:+.5f}"
    pos = ">0" if s["ci_strictly_positive"] else "≤0"
    gate = "CLEARS" if s["clears_tick_magnitude"] else "no"
    adm = "admissible" if s["admissible"] else "INADMISSIBLE(%s)" % ",".join(
        s["admissibility"]["reasons"])
    print(f"  {label} (fee rate {rate:.2f}): mean={mean:>10}  95% CI={_fmt_ci(s['ci95'])}  "
          f"n_games={s['n_units']:>3}  n_outcomes={s['n_obs']:>4}  CI {pos}  tick {gate}  {adm}")


def print_report(rep: Dict[str, Any]) -> None:
    fm, pm = rep["fair_meta"], rep["poly_meta"]
    print("=" * 90)
    print("Q32 SHARP-DEVIG vs POLYMARKET SPORTS PRICE  "
          "edge = poly_real_ask − devig_synthetic_fair − poly_fee")
    print("=" * 90)
    print(f"sports_pairs games: {fm['n_games_total']} total, {fm['n_games_matched_odds']} with a "
          f"MATCHED odds_leg, {fm['n_outcomes_with_fair']} outcomes with a de-vig fair anchor")
    print(f"polymarket sports leg: {pm['n_poly_lines']} lines across {pm['n_poly_files']} files, "
          f"{pm['n_poly_tickers']} distinct outcome tickers")
    print(f"PROVENANCE: {rep['provenance_caveat']}")

    if not rep.get("data_adequate"):
        print("\nINSUFFICIENT DATA — legs not yet captured: " + rep["insufficient_reason"])
        print("This is prep infrastructure: point --polymarket-tape-dir at the real leg (and let "
              "ODDS_API_KEY populate the odds leg) and re-run. NO verdict is produced.")
        return

    j = rep["join_meta_conservative"]
    print(f"\njoined resolution-equivalent (game, outcome) pairs: {j['n_joined_outcomes']} "
          f"across {j['n_joined_games']} games")
    print(f"  excluded: {j['n_excluded_no_fair_anchor']} no-fair-anchor, "
          f"{j['n_excluded_not_resolution_equivalent']} NOT-resolution-equivalent, "
          f"{j['n_excluded_missing_equivalence_flag']} missing-equivalence-flag, "
          f"{j['n_excluded_no_real_ask']} no-real-ask")
    print(f"  price_source_tags seen on the fillable leg: {j['price_source_tags_seen']}")
    print()
    _print_scenario("conservative", rep["sports_rate_conservative"], rep["scenario_conservative"])
    _print_scenario("optimistic  ", rep["sports_rate_optimistic"], rep["scenario_optimistic"])
    print(f"\nVERDICT: {rep['verdict']}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q32 sharp-devig vs Polymarket sports price probe (prep; read-only)")
    ap.add_argument("--sports-glob", default=SPORTS_PAIRS_GLOB,
                    help="glob for sports_pairs de-vig tape (leg a)")
    ap.add_argument("--polymarket-tape-dir", required=True,
                    help="dir holding the Polymarket sports leg JSONL (leg b) — the ONE path to "
                         "point at real data once Q33 or an international-book equivalent lands")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    rep = run_probe(args.sports_glob, args.polymarket_tape_dir, n_boot=args.n_boot, seed=args.seed)
    print_report(rep)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"[q32] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

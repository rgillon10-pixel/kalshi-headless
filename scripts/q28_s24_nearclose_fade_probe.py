"""Q28 / S24 — Near-close hourly-return overreaction fade on two-sided sports books.

Falsifiable milestone (LOOP-QUEUE.md Q28; kb/strategies/00-index.md S24, Theme 7
behavioral / De Bondt-Thaler): an hourly-scale near-close mid JUMP in a two-sided sports
book (retail overreacting to the last salient in-game event) is claimed to partially
REVERSE over the next snapshot — fade the jump. This probe charges the FULL realized
round-trip (enter at the ask, exit at the bid, BOTH taker fees) and block-bootstraps by
GAME (L6). The load-bearing distinctness gate: if the ONLY profitable exit is
hold-to-settlement, the "edge" is a directional settlement bet keyed on a recent jump —
that is S22's mechanism (already DEAD), NOT a new S24 reversal edge, and must be routed to
S22's slot, never registered as S24 (the anti-overlap guard).

READ-ONLY over `tape/orderbook_depth/` (a probe never mutates tape). Unlike Q26 (which kept
only the LAST pre-close snapshot per market), S24 needs the FULL per-market price PATH: for
each target-series market with a settlement + close_time, ALL snapshots with
captured_at < close_time, ordered by captured_at. Settlement (result/close_time/event_ticker)
is loaded OFFLINE from Q26's committed cache (`tape/q26_settlement_cache/settlement.json`) —
no new live pull. Settlement is `broker_truth`; the entry ask is `real_ask`, the exit bid is
`real_bid`; the mid is a derived observable off those book fields.

Build order (cheap kills first):
  GATE 1  jump-population adequacy — ≥10 distinct GAMES carry a ≥X¢ jump in the near-close
                                    window, or DEAD-by-adequacy (hourly cadence too coarse).
  GATE 2  reversal-vs-momentum precheck — a SIGN question (L41: opposing cluster NOT
                                    guaranteed). Momentum (mean next-step SAME sign as the
                                    jump AND reversal fraction ≤0.5) → DEAD-by-momentum.
  GATE 3  full round-trip fade P&L — enter at ask(t+1), exit at bid(t+2); 2× taker fee +
                                    2× half-spread (the ≈6-8¢ realized hurdle). Exclude a
                                    missing / ≥$1.00 (L26 mirror) / ≤0 ask and COUNT it.
  GATE 4  block-bootstrap CI by GAME — bootstrap_verdict_admissible (L41) AND block_bootstrap
                                    AND clears_tick_magnitude (L27) on the round-trip, PLUS
                                    the anti-overlap hold-to-settlement bootstrap.

Verdict is one of: DEAD-by-adequacy / DEAD-by-momentum / DEAD-by-round-trip / DEAD-by-CI /
S22-DUPLICATE-ROUTE / ALIVE-PROVISIONAL. A DEAD verdict recorded cleanly is a full success.

Threshold X: Q25 found 58-94% of consecutive hourly pairs frozen (zero mid change) and a
mid moves in 0.5¢ steps (each BBO side is 1¢-granular), so a 1¢ mid move can be a single
one-tick-per-side bounce. PRIMARY X = 2¢ (clearly beyond a one-tick flicker); the sweep
X∈{2,3,4,5}¢ shows the population thinning. Near-close window is a ttc BUCKET (ttc ≤
NEAR_CLOSE_HOURS), NOT minute precision — sports HHMM tz is unverified (L46). A max
pair-gap guard keeps a jump/next-step genuinely consecutive rather than spanning a
multi-hour collection hole (L13-family gap artifact).

Sizes are FLOATS (L47); a one-sided/empty ladder is VALID data (L23). Fees ALWAYS from
`core.pricing` at TAKER_FEE_RATE — never hand-rolled (L18/L30).

Run (offline, against the committed depth tape + Q26 cache — the only mode):
    python scripts/q28_s24_nearclose_fade_probe.py
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,
                            clears_tick_magnitude)
from core.io import REPO_ROOT
from core.pricing import TAKER_FEE_RATE, fee_per_contract

# `core` is pip-installed (editable) but `scripts/` is not a declared package, so make the
# repo root importable before reusing the sibling probe's helpers verbatim (Q28 spec: reuse
# `series_of` / `event_ticker_of` / `parse_iso` / `mid_yes` / `load_settlement_cache`, do NOT
# re-derive). Under pytest conftest.py already does this; this keeps the standalone run working.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.q26_ofi_depth_imbalance_probe import (  # noqa: E402
    event_ticker_of, load_settlement_cache, mid_yes, parse_iso, series_of)

TARGET_SERIES = ("KXKBOGAME", "KXNPBGAME", "KXWNBAGAME", "KXMLBGAME",
                 "KXUCLGAME", "KXUECLGAME", "KXUELGAME")

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
CACHE_PATH = REPO_ROOT / "tape" / "q26_settlement_cache" / "settlement.json"

# --- probe design constants (justified in the module docstring) ---------------- #
X_PRIMARY = 0.02                       # ≥2¢ mid move: clearly beyond a one-tick BBO flicker
X_SWEEP = (0.02, 0.03, 0.04, 0.05)     # population-thinning sweep for the reader
NEAR_CLOSE_HOURS = 4.0                 # ttc bucket — the live-game window (games run ~3h)
MAX_PAIR_GAP_HOURS = 1.5               # keep a jump/next-step genuinely consecutive (L13)


# --------------------------------------------------------------------------- #
# Pure fade helpers (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def jump_of(mid_prev: Optional[float], mid_now: Optional[float]) -> Optional[float]:
    """Signed mid change mid(t+1) − mid(t). None if either mid is missing."""
    if mid_prev is None or mid_now is None:
        return None
    return mid_now - mid_prev


def is_jump_event(jump: Optional[float], x_threshold: float) -> bool:
    """A jump event = |mid change| ≥ threshold (with a tiny float tolerance). A frozen pair
    (jump exactly 0) is never an event."""
    if jump is None:
        return False
    return abs(jump) >= x_threshold - 1e-9


def fade_side_of_jump(jump: Optional[float]) -> Optional[str]:
    """FADE AGAINST the jump: a jump UP (mid rose) → buy NO; a jump DOWN → buy YES. None at
    exactly 0 (no jump to fade). This is OPPOSITE the jump's own direction by construction."""
    if jump is None or jump == 0:
        return None
    return "no" if jump > 0 else "yes"


def reverses(jump: float, next_step: Optional[float]) -> Optional[bool]:
    """Did the next-step mid change move OPPOSITE to the jump (a reversal)? None if the
    next-step is missing or exactly 0 (no directional move to classify)."""
    if next_step is None or next_step == 0:
        return None
    return (jump > 0) != (next_step > 0)


def round_trip_pnl(entry_ask: Optional[float], exit_bid: Optional[float]) -> Optional[float]:
    """Realized next-snapshot round-trip: BUY the fade side at its ask(t+1), SELL it at its
    bid(t+2). Net = bid_exit − ask_entry − fee(entry) − fee(exit), charging BOTH taker fees
    AND both half-spreads (the full ≈6-8¢ realized round-trip). Returns None (caller excludes
    + counts) when the entry ask is missing / ≥$1.00 (L26 mirror — no fillable price) / ≤0,
    or the exit bid is missing (no realized exit at the next snapshot). Prices are
    `real_ask` (entry) / `real_bid` (exit); the arithmetic is side-agnostic (the caller has
    already resolved which side's ask/bid to pass)."""
    if entry_ask is None or entry_ask >= 1.0 or entry_ask <= 0.0:
        return None
    if exit_bid is None:
        return None
    fee_in = fee_per_contract(entry_ask, TAKER_FEE_RATE)
    fee_out = fee_per_contract(exit_bid, TAKER_FEE_RATE)
    return float(exit_bid) - float(entry_ask) - fee_in - fee_out


def hold_to_settlement_pnl(fade_side: str, settled_yes: int,
                           entry_ask: Optional[float]) -> Optional[float]:
    """ANTI-OVERLAP exit: hold the fade entry to settlement instead of exiting at t+2.
    Net = settlement_payoff − ask_entry − ONE taker fee (settlement is free; NO exit fee,
    NO exit half-spread). fade='no' pays $1 when settled NO; fade='yes' pays $1 when settled
    YES. Returns None on the same unfillable-entry exclusions as the round-trip. Settlement
    is `broker_truth`, the entry ask `real_ask`."""
    if entry_ask is None or entry_ask >= 1.0 or entry_ask <= 0.0:
        return None
    if fade_side == "no":
        payoff = 1.0 if settled_yes == 0 else 0.0
    else:
        payoff = 1.0 if settled_yes == 1 else 0.0
    fee = fee_per_contract(entry_ask, TAKER_FEE_RATE)
    return payoff - float(entry_ask) - fee


# --------------------------------------------------------------------------- #
# Depth tape loading — the FULL per-market pre-close price PATH (read-only)
# --------------------------------------------------------------------------- #
def load_price_paths(depth_glob: str, settlement: Dict[str, dict]
                     ) -> Tuple[Dict[str, List[dict]], dict]:
    """Scan the depth tape once. For every target-series market ticker with a retrieved
    yes/no settlement (L52: filter out 'scalar') AND a close_time, collect ALL snapshots
    with captured_at < close_time, ordered ascending by captured_at.

    Returns (paths, funnel). paths[market_ticker] = ordered list of snapshot dicts:
        {captured_at, ttc_hours, mid, best_yes_ask, best_no_ask, best_yes_bid, best_no_bid,
         event_ticker, settled_yes}
    """
    funnel = {
        "markets_in_depth": set(),
        "markets_settled_joined": set(),
        "markets_with_path": set(),
    }
    paths: Dict[str, List[dict]] = defaultdict(list)
    for fp in sorted(glob.glob(depth_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                mt = rec.get("ticker", "")
                if series_of(mt) not in TARGET_SERIES:
                    continue
                funnel["markets_in_depth"].add(mt)
                s = settlement.get(mt)
                if not s or s.get("result") not in ("yes", "no"):  # L52
                    continue
                funnel["markets_settled_joined"].add(mt)
                close_dt = parse_iso(s.get("close_time"))
                cap_dt = parse_iso(rec.get("captured_at"))
                if close_dt is None or cap_dt is None or cap_dt >= close_dt:
                    continue
                paths[mt].append({
                    "captured_at": cap_dt,
                    "ttc_hours": (close_dt - cap_dt).total_seconds() / 3600.0,
                    "mid": mid_yes(rec.get("best_yes_bid"), rec.get("best_yes_ask")),
                    "best_yes_ask": rec.get("best_yes_ask"),
                    "best_no_ask": rec.get("best_no_ask"),
                    "best_yes_bid": rec.get("best_yes_bid"),
                    "best_no_bid": rec.get("best_no_bid"),
                    "event_ticker": s.get("event_ticker") or event_ticker_of(mt),
                    "settled_yes": 1 if s.get("result") == "yes" else 0,
                })
    for mt in paths:
        paths[mt].sort(key=lambda r: r["captured_at"])
    funnel["markets_with_path"] = set(paths.keys())
    return dict(paths), funnel


# --------------------------------------------------------------------------- #
# Jump / trade extraction over consecutive snapshots
# --------------------------------------------------------------------------- #
def _gap_hours(a: dict, b: dict) -> float:
    return (b["captured_at"] - a["captured_at"]).total_seconds() / 3600.0


def jump_events(path: List[dict], x_threshold: float, near_close_hours: float,
                max_gap_hours: float) -> List[dict]:
    """All near-close, genuinely-consecutive jump events on one market path. A pair (t,t+1)
    qualifies if both mids exist, the t+1 snapshot is in the near-close ttc bucket, the pair
    gap ≤ max_gap_hours, and |mid change| ≥ x_threshold. Used by GATE 1's sweep."""
    out: List[dict] = []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        j = jump_of(a["mid"], b["mid"])
        if not is_jump_event(j, x_threshold):
            continue
        if b["ttc_hours"] > near_close_hours:
            continue
        if _gap_hours(a, b) > max_gap_hours:
            continue
        out.append({"i": i, "jump": j, "ttc_hours": b["ttc_hours"],
                    "event_ticker": b["event_ticker"]})
    return out


def fade_trades(path: List[dict], x_threshold: float, near_close_hours: float,
                max_gap_hours: float) -> List[dict]:
    """For each near-close consecutive jump at (t,t+1) with a t+2 snapshot also within
    max_gap_hours, build the fade trade: enter at t+1 ask, exit at t+2 bid (round-trip) and
    also its hold-to-settlement counterpart. Emits one row per candidate triple (round-trip
    and/or hold P&L may be None if that leg is unfillable — the caller funnels those)."""
    out: List[dict] = []
    for i in range(len(path) - 2):
        a, b, c = path[i], path[i + 1], path[i + 2]
        j = jump_of(a["mid"], b["mid"])
        if not is_jump_event(j, x_threshold):
            continue
        if b["ttc_hours"] > near_close_hours:
            continue
        if _gap_hours(a, b) > max_gap_hours or _gap_hours(b, c) > max_gap_hours:
            continue
        fade = fade_side_of_jump(j)
        if fade is None:
            continue
        next_step = jump_of(b["mid"], c["mid"])
        if fade == "no":
            entry_ask, exit_bid = b["best_no_ask"], c["best_no_bid"]
        else:
            entry_ask, exit_bid = b["best_yes_ask"], c["best_yes_bid"]
        out.append({
            "event_ticker": b["event_ticker"],
            "settled_yes": a["settled_yes"],
            "jump": j,
            "next_step": next_step,
            "fade_side": fade,
            "entry_ask": entry_ask,
            "exit_bid": exit_bid,
            "rt_pnl": round_trip_pnl(entry_ask, exit_bid),
            "hold_pnl": hold_to_settlement_pnl(fade, a["settled_yes"], entry_ask),
        })
    return out


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _quantiles(vals: List[float]) -> dict:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)
    def q(p):
        return s[min(n - 1, int(p * n))]
    return {"n": n, "min": s[0], "p10": q(0.10), "median": q(0.50),
            "p90": q(0.90), "max": s[-1], "mean": sum(s) / n}


def jump_sweep(paths: Dict[str, List[dict]]) -> List[dict]:
    """GATE 1 population table: per threshold, jump-event count + distinct games + the ttc
    distribution of the jump events (at the primary window/gap guard)."""
    table = []
    for x in X_SWEEP:
        events = 0
        games = set()
        ttcs: List[float] = []
        for path in paths.values():
            for ev in jump_events(path, x, NEAR_CLOSE_HOURS, MAX_PAIR_GAP_HOURS):
                events += 1
                games.add(ev["event_ticker"])
                ttcs.append(ev["ttc_hours"])
        table.append({"x_threshold": x, "n_jump_events": events,
                      "n_distinct_games": len(games),
                      "ttc_hours_dist": _quantiles(ttcs)})
    return table


def gate2_direction(trades: List[dict]) -> dict:
    """Reversal-vs-momentum precheck on the next-step mid change conditioned on jump sign."""
    up_next, dn_next = [], []
    n_rev, n_dir = 0, 0
    for t in trades:
        r = reverses(t["jump"], t["next_step"])
        if r is None:
            continue
        n_dir += 1
        if r:
            n_rev += 1
        (up_next if t["jump"] > 0 else dn_next).append(t["next_step"])
    up_mean = sum(up_next) / len(up_next) if up_next else None
    dn_mean = sum(dn_next) / len(dn_next) if dn_next else None
    # Momentum = the conditional means point the SAME way as the jump (up→up, down→down)
    # AND fewer than half of jumps reverse. Reversal-direction means (up→down / down→up)
    # keep the mechanism alive even when the reversal FREQUENCY is below 0.5.
    momentum = (n_dir > 0 and (n_rev / n_dir) <= 0.5
                and (up_mean is not None and up_mean > 0)
                and (dn_mean is not None and dn_mean < 0))
    return {
        "n_with_next_step": n_dir,
        "reversal_fraction": (n_rev / n_dir) if n_dir else None,
        "mean_next_step_after_jump_up": up_mean,
        "mean_next_step_after_jump_down": dn_mean,
        "is_momentum": momentum,
    }


def gate3_roundtrip(trades: List[dict]) -> Tuple[Dict[str, List[float]], Dict[str, List[float]], dict]:
    """Build the by-GAME unit maps for the round-trip and hold-to-settlement P&L, with the
    trade/exclusion funnel (a shared exclusion: an unfillable entry ask kills BOTH exits)."""
    rt_units: Dict[str, List[float]] = defaultdict(list)
    hs_units: Dict[str, List[float]] = defaultdict(list)
    n_candidates = len(trades)
    n_excl_entry = 0     # unfillable/mirror/missing entry ask (excludes both legs)
    n_excl_exit = 0      # entry fine but no t+2 bid (excludes round-trip only)
    rt_all, hs_all = [], []
    for t in trades:
        if t["hold_pnl"] is None:
            # entry ask unfillable -> neither leg tradeable
            n_excl_entry += 1
            continue
        hs_units[t["event_ticker"]].append(t["hold_pnl"])
        hs_all.append(t["hold_pnl"])
        if t["rt_pnl"] is None:
            n_excl_exit += 1        # entry ok, no realized next-snapshot exit
            continue
        rt_units[t["event_ticker"]].append(t["rt_pnl"])
        rt_all.append(t["rt_pnl"])
    funnel = {
        "n_candidate_triples": n_candidates,
        "n_excluded_unfillable_entry": n_excl_entry,
        "n_excluded_no_exit_bid": n_excl_exit,
        "n_roundtrip_trades": len(rt_all),
        "n_hold_trades": len(hs_all),
        "n_games_roundtrip": len(rt_units),
        "n_games_hold": len(hs_units),
        "mean_roundtrip_pnl": (sum(rt_all) / len(rt_all)) if rt_all else None,
        "mean_hold_pnl": (sum(hs_all) / len(hs_all)) if hs_all else None,
    }
    return dict(rt_units), dict(hs_units), funnel


def _boot_block(unit_values: Dict[str, List[float]]) -> dict:
    boot = block_bootstrap(unit_values)
    adm = bootstrap_verdict_admissible(unit_values, min_units=10)
    mag = clears_tick_magnitude(boot["ci95"], tick=0.01, min_ticks=1.0)
    ci_lo = boot["ci95"][0]
    clears = (ci_lo is not None and ci_lo > 0 and adm["admissible"] and mag
              and len(unit_values) >= 10)
    return {"bootstrap": boot, "admissible": adm, "clears_tick_magnitude": mag,
            "n_games": len(unit_values), "clears": clears}


def run(cache_path=CACHE_PATH, depth_glob: str = DEPTH_GLOB,
        x_primary: float = X_PRIMARY) -> dict:
    settlement = load_settlement_cache(cache_path)
    paths, funnel_sets = load_price_paths(depth_glob, settlement)

    report = {
        "params": {"x_primary": x_primary, "near_close_hours": NEAR_CLOSE_HOURS,
                   "max_pair_gap_hours": MAX_PAIR_GAP_HOURS,
                   "target_series": list(TARGET_SERIES)},
        "n_settled_markets_cached": len(settlement),
        "funnel": {
            "markets_in_depth": len(funnel_sets["markets_in_depth"]),
            "markets_settled_joined": len(funnel_sets["markets_settled_joined"]),
            "markets_with_path": len(funnel_sets["markets_with_path"]),
        },
        "price_source_tags": {"entry": "real_ask", "exit": "real_bid",
                              "settlement": "broker_truth", "mid": "derived(real_ask,real_bid)"},
    }

    sweep = jump_sweep(paths)
    report["gate1_jump_sweep"] = sweep
    primary = next(r for r in sweep if abs(r["x_threshold"] - x_primary) < 1e-9)
    games_primary = primary["n_distinct_games"]

    # GATE 1 — adequacy
    if games_primary < 10:
        report["verdict"] = "DEAD-by-adequacy"
        report["verdict_reason"] = (
            f"only {games_primary} distinct games carry a ≥{x_primary*100:.0f}¢ near-close "
            "jump (<10) — hourly cadence too coarse to populate the jump test (S9-family)")
        return report

    trades = [t for path in paths.values()
              for t in fade_trades(path, x_primary, NEAR_CLOSE_HOURS, MAX_PAIR_GAP_HOURS)]

    # GATE 2 — direction precheck
    g2 = gate2_direction(trades)
    report["gate2_direction"] = g2

    # GATE 3 — round-trip funnel
    rt_units, hs_units, g3 = gate3_roundtrip(trades)
    report["gate3_roundtrip"] = g3

    # GATE 4 — bootstraps (both cuts, by GAME)
    rt = _boot_block(rt_units)
    hs = _boot_block(hs_units)
    report["gate4_roundtrip_S24"] = rt
    report["gate4_hold_to_settlement_antioverlap"] = hs

    # --- verdict ---
    if g2["is_momentum"]:
        report["verdict"] = "DEAD-by-momentum"
        report["verdict_reason"] = (
            f"jumps CONTINUE: reversal fraction {g2['reversal_fraction']:.3f} ≤0.5 and the "
            f"conditional next-step means point WITH the jump (up→{g2['mean_next_step_after_jump_up']:+.4f}, "
            f"down→{g2['mean_next_step_after_jump_down']:+.4f}) — no reversal to fade")
        return report

    if rt["clears"]:
        report["verdict"] = "ALIVE-PROVISIONAL"
        report["verdict_reason"] = (
            "round-trip CI strictly >0, admissible (L41), clears the 1-tick magnitude gate "
            "(L27) — a genuine S24 near-close reversal fade; needs verifier + shadow-paper")
        return report

    if hs["clears"]:
        report["verdict"] = "S22-DUPLICATE-ROUTE"
        report["verdict_reason"] = (
            "round-trip does NOT clear but hold-to-settlement DOES — the only profitable exit "
            "is a directional settlement bet keyed on a recent jump, which IS S22's mechanism "
            "(already DEAD). NOT a new S24 edge; flag as a duplicate route, do not register.")
        return report

    rt_mean = rt["bootstrap"]["mean"]
    if rt_mean is not None and rt_mean < 0:
        report["verdict"] = "DEAD-by-round-trip"
        report["verdict_reason"] = (
            f"the full realized round-trip is net NEGATIVE (mean {rt_mean:+.4f}, "
            f"95% CI {[round(x,4) for x in rt['bootstrap']['ci95']]}): the ≈6-8¢ round-trip "
            "cost (2× taker fee + 2× half-spread) swamps the sub-cent near-close reversal. "
            "Hold-to-settlement also fails to clear, so it is not an S22 route either.")
    else:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = (
            f"round-trip point estimate non-negative but the CI fails a gate: "
            f"ci95={rt['bootstrap']['ci95']}, admissible={rt['admissible']['admissible']}, "
            f"clears_tick_magnitude={rt['clears_tick_magnitude']}, n_games={rt['n_games']}")
    return report


def _print_report(rep: dict) -> None:
    print(json.dumps(rep, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q28/S24 near-close fade probe (read-only, offline)")
    ap.add_argument("--cache", default=str(CACHE_PATH))
    ap.add_argument("--x-primary", type=float, default=X_PRIMARY)
    args = ap.parse_args(argv)
    from pathlib import Path
    rep = run(cache_path=Path(args.cache), x_primary=args.x_primary)
    _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())

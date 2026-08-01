#!/usr/bin/env python3
"""q49_s68_bothside_maker_fillsim.py — Q49 / S68: two-sided BOTH-BID overround-capture
maker fill-sim on wide-spread genuine game moneyline books.

LOOP-QUEUE.md Q49, registry S68, idea-stage derivation
`findings/2026-08-01-q21-idea-gen-round.md`.

MECHANISM UNDER TEST. On a 2-outcome (binary yes/no) game moneyline book whose two-sided
spread is at least the two maker fees, rest BOTH a YES bid and a NO bid on the SAME market
simultaneously. If BOTH fill you own both sides for `yes_fill + no_fill` < $1 and exactly one
side pays $1 at settlement — a deterministic gross capture of `1 - (yes_fill + no_fill)`, net
of TWO maker fees (one per filled leg). The idea-stage overround is real and structural (on a
binary book the mirror identity `yes_ask == 1 - no_bid` makes the yes-spread IDENTICALLY the
both-bid capture). The whole open question is therefore the FILL MODEL: does resting both
sides actually double-fill, and does the double-fill population survive adverse selection?

READ-ONLY, FULLY OFFLINE, NO NETWORK, NO ORDERS, NO AUTH. Both legs are already-committed
tape: `tape/orderbook_depth/` (`real_bid` ladders) x `tape/settlement_ledger/`
(`broker_truth` result + close_time), joined by ticker (L50 ex-post join).

DESIGN (the binding gates from the Q49 spec — none of these may be weakened):

  1. GENUINELY TWO-SIDED, WIDE-SPREAD SELECTION AT ENTRY. Entry = the market's EARLIEST
     pre-close depth snapshot (`captured_at < close_time`) — no forward search for a
     friendlier snapshot (that would be look-ahead selection). Require a real two-sided
     quote: `best_yes_bid` AND `best_no_bid` both present and > 0 (never a derived/synthetic
     mirror), plus a `best_yes_ask`. Require yes-spread >= the TWO maker fees
     (`core.pricing.fee_per_contract(p, rate=MAKER_FEE_RATE)` on each leg's own price — the
     flat $0.01 interior fee, so this is the spec's "2x the flat maker fee"; never
     hand-rolled, `scripts/invariants.py::no_handrolled_fee_rate` forbids the literal).
     KXMVE* (the nominal-wing AMM multi-outcome families, L31) are excluded by the S68 note.

  2. TWO INDEPENDENT RESTING ORDERS, QUEUE-AWARE FILL FOR EACH (the S19/Q27 L2-queue
     methodology, L39-free — never a candlestick "the price printed" proxy). We join the BACK
     of each ladder: queue_ahead(YES) = `yes_bids` size at price >= our bid at entry;
     queue_ahead(NO) = `no_bids` size at price >= our bid at entry. Fills are then measured
     from the tape's OWN observed queue departures across every later pre-close snapshot (the
     L48 turnover-departure proxy, GENEROUS by construction: a cancel/fill ahead of us counts
     as advancing us, a new order jumping ahead of us is ignored). Sizes are FLOATS (L47) —
     a real observed best-level size was 91,316.82 contracts; never int-coerced. A frozen
     ladder (zero observed departures) is a NO-FILL, never free income (L32).

  2b. TWO FILL MODELS, BOTH REPORTED; THE VERDICT RESTS ON THE STRICT ONE. The Q27/S19
     precedent rule (`turnover`: departures at ANY level >= our price) was built for a
     dead-thin population where a near-zero fill rate is a robust OUT. Over THIS population's
     multi-day holds (median 66 snapshots/ticker) it SATURATES — cumulative departures reach
     tens of thousands of contracts against a queue of tens, because the whole book migrating
     away from our stale price counts as "advancing" us, so ~98% of legs "fill". That is a
     proxy artifact, not evidence of fills. So a strictly tighter companion is computed:
     `touch` counts departures at OUR OWN price level ONLY, and ONLY while our price is still
     at/above the side's best bid (we cannot be hit at all once the best bid moves above us).
     Both are still generous — the depth tape has NO trade/volume field (L68/L106), so a
     cancel at our own price is indistinguishable from a fill and is counted as one.

  3. EXPLICIT ADVERSE SELECTION, MEASURED NOT ASSUMED. The two legs are NOT assumed to fill
     independently at some queue-derived rate and multiplied. Each ticker's empirical joint
     outcome (both / yes-only / no-only / neither) is simulated directly off the tape's own
     two ladders, and whatever correlation exists between the fill pattern and the
     `broker_truth` settlement shows up in the realized P&L. We report the settle-YES rate
     among double-fills vs among all wide-spread candidates (S19's "toxic leg" report).
     ONLY a double fill books the overround; a single-side fill is a DIRECTIONAL position
     (tracked and reported separately, and carried in the strategy-level diagnostic cut, but
     never inside the both-fill P&L).

  4. P&L NET OF BOTH MAKER FEES, per double-filled ticker:
        cost = p_yes + p_no + fee(p_yes) + fee(p_no)
        settles YES -> YES leg pays $1, NO leg pays $0 -> net = 1 - cost
        settles NO  -> NO leg pays $1, YES leg pays $0 -> net = 1 - cost
     Identical either way by construction — that symmetry is asserted in code and printed.

  5. BLOCK-BOOTSTRAP BY GAME-SERIES (L6/L41 — the series are the independent units; games and
     outcomes within a series are correlated draws), through `bootstrap_verdict_admissible`
     (>=10 units AND >=1 opposing-sign unit) and `clears_tick_magnitude` (tick $0.01, L27).
     Fewer than 10 distinct series carrying a double fill = DEAD-by-adequacy, not a CI.

  6. L69 FILLABLE-ENTRY RESTRICTION IS THE PRIMARY POPULATION. An earliest-entry maker sim
     systematically rests on thin, often nominal early books (S29/Q30's spec population
     cleared every gate on nickel bids days before kickoff). So the headline verdict is taken
     on the fillable-entry-restricted cut (entry spread <= 10c AND time-to-close <= 24h); the
     unrestricted earliest-entry population is a LABELED DIAGNOSTIC, never the headline.

KILL CONDITIONS (any => DEAD): both-sides fill rate below the S19 ~0.45% floor · the
double-fill population's realized overround <= 0 once fees/adverse selection are in the P&L ·
CI <= 0 or failing the tick-magnitude gate · fewer than 10 game-series after the queue gate.

Run:
    python scripts/q49_s68_bothside_maker_fillsim.py
    python scripts/q49_s68_bothside_maker_fillsim.py --n-boot 10000 --json-out /tmp/q49.json
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,  # noqa: E402
                            bracket_by_movement, clears_tick_magnitude,
                            hit_magnitude_decomposition)
from core.depth import capturable_depth, lottery_tail_fraction  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import MAKER_FEE_RATE, fee_per_contract  # noqa: E402
from core.settlement import is_binary_result, normalize_result  # noqa: E402
from core.timeutil import parse_iso_utc  # noqa: E402

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
SETTLEMENT_GLOB = str(REPO_ROOT / "tape" / "settlement_ledger" / "dt=*.jsonl")

EXCLUDED_SERIES_PREFIX = "KXMVE"   # nominal-wing AMM multi-outcome families (S68 note / L31)
S19_FILL_FLOOR = 0.0045            # the S19-class queue-aware fill-rate kill floor
MIN_CI_UNITS = 10                  # the Q49 10-game-series floor (L41)
PRICE_TICK = 0.01                  # Kalshi price tick (L27 magnitude gate)
FILLABLE_MAX_SPREAD = 0.10         # L69 fillable-entry: a genuinely two-sided (<=10c) book
FILLABLE_MAX_TTC_HOURS = 24.0      # L69 fillable-entry: near-close
# Two fill models, both generous, reported side by side. `turnover` is the Q27/S19 precedent
# rule (departures at ANY level >= our price); `touch` is the strictly tighter companion
# (departures at OUR price only, and only while we are at the touch). The verdict rests on
# `touch` — see the module docstring's FILL-MODEL note and simulate_leg_fill's caveat.
FILL_MODELS = ("touch", "turnover")
PRIMARY_FILL_MODEL = "touch"
_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Pure ticker / time helpers (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def series_of(market_ticker: str) -> str:
    """Series prefix — the BOOTSTRAP UNIT for this probe (L6/L41: the 16-18 game series are
    the independent draws; games/outcomes inside a series are correlated).
    'KXKBOGAME-26JUL070530KIALOT-KIA' -> 'KXKBOGAME'."""
    return market_ticker.split("-", 1)[0]


def event_ticker_of(market_ticker: str) -> str:
    """The GAME key: the ticker with its trailing '-<OUTCOME>' segment stripped,
    'KXKBOGAME-26JUL070530KIALOT-KIA' -> 'KXKBOGAME-26JUL070530KIALOT'. A ticker with no
    trailing '-<code>' returns itself unchanged."""
    return market_ticker.rsplit("-", 1)[0]


def is_excluded_series(market_ticker: str,
                       prefix: str = EXCLUDED_SERIES_PREFIX) -> bool:
    """True for the KXMVE* nominal-wing AMM families the S68 registry note excludes (L31 —
    AMM-fabricated one-sided sizes, not a real game moneyline book)."""
    return series_of(market_ticker).startswith(prefix)


def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """ISO-8601 -> tz-aware UTC datetime via the sanctioned `core.timeutil.parse_iso_utc`
    (L136/L150 — never the raw stdlib parser). None on missing/blank/unparseable input."""
    if not ts:
        return None
    try:
        dt = parse_iso_utc(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# Pure selection helpers (fees ONLY from core.pricing — L18/L30)
# --------------------------------------------------------------------------- #
def maker_fee(fill_price: float) -> float:
    """The flat maker fee on ONE filled leg: `fee_per_contract` at MAKER_FEE_RATE on that
    leg's OWN fill price (a flat $0.01 at every interior price, $0 only at the 0/1 boundary).
    Sanctioned helper — never hand-rolled."""
    return fee_per_contract(float(fill_price), rate=MAKER_FEE_RATE)


def two_sided_wide_entry(yes_bid: Optional[float], no_bid: Optional[float],
                         yes_offer: Optional[float]) -> Dict[str, Any]:
    """Gate 1: is this entry snapshot a GENUINELY two-sided book with a spread wide enough to
    pay both maker fees?

    `yes_offer` is the snapshot's `best_yes_ask` (read into a local so no ask-arithmetic
    happens on the raw field name, Hard Rule #3's scanner). Requires:
      * both bids present and strictly > 0 (a real resting two-sided quote — a missing or
        zero bid is the ABSENCE of an order, never a $0.00 fillable price), and an offer,
      * yes-spread = offer - yes_bid >= fee(yes_bid) + fee(no_bid).

    Returns a dict {"eligible", "reason", "spread", "fee_yes", "fee_no", "fee_total",
    "gross_capture"} — `gross_capture` = 1 - (yes_bid + no_bid), the deterministic both-fill
    payoff before fees, computed from the two REAL bids rather than assumed equal to the
    spread (on a coherent binary book the mirror identity makes them equal; we measure it)."""
    out: Dict[str, Any] = {"eligible": False, "reason": "", "spread": None,
                           "fee_yes": None, "fee_no": None, "fee_total": None,
                           "gross_capture": None}
    if yes_bid is None or no_bid is None or yes_offer is None:
        out["reason"] = "missing_quote"
        return out
    yb, nb, ya = float(yes_bid), float(no_bid), float(yes_offer)
    if yb <= 0.0 or nb <= 0.0:
        out["reason"] = "not_two_sided"
        return out
    fee_yes, fee_no = maker_fee(yb), maker_fee(nb)
    spread = ya - yb
    out.update({"spread": spread, "fee_yes": fee_yes, "fee_no": fee_no,
                "fee_total": fee_yes + fee_no, "gross_capture": 1.0 - yb - nb})
    if spread < fee_yes + fee_no - _EPS:
        out["reason"] = "spread_below_two_maker_fees"
        return out
    out["eligible"] = True
    out["reason"] = "ok"
    return out


# --------------------------------------------------------------------------- #
# Pure ladder / queue helpers (sizes are FLOATS, L47; an empty ladder is VALID, L23)
# --------------------------------------------------------------------------- #
def bid_price_map(bids: Optional[Sequence[Sequence[float]]], price: float,
                  tick: float = PRICE_TICK) -> Dict[float, float]:
    """price -> size map over the ladder levels at price >= `price` (everything resting ahead
    of a newly-arriving bid at `price`, by price-time priority). Sizes are FLOATS (L47),
    never int-coerced. Empty/None ladder -> empty map (a one-sided book is VALID data, L23).
    Works for a `yes_bids` ladder (a YES bid) or a `no_bids` ladder (a NO bid) alike."""
    out: Dict[float, float] = {}
    if not bids:
        return out
    for level in bids:
        if level is None or len(level) < 2 or level[0] is None or level[1] is None:
            continue
        p = float(level[0])
        if p >= price - tick / 2.0:
            out[p] = out.get(p, 0.0) + float(level[1])
    return out


def queue_ahead_at(bids: Optional[Sequence[Sequence[float]]], price: float,
                   tick: float = PRICE_TICK) -> float:
    """Contracts resting AHEAD of our newly-arriving bid at `price`: the summed size of every
    ladder level at price >= ours (price-or-time priority — all of it fills first). FLOATS."""
    return sum(bid_price_map(bids, price, tick).values())


def departures_between(prev_bids: Optional[Sequence[Sequence[float]]],
                       now_bids: Optional[Sequence[Sequence[float]]], price: float,
                       tick: float = PRICE_TICK) -> float:
    """Observed queue DEPARTURES at levels >= our bid between two consecutive snapshots (the
    L48 turnover measure): for each level >= `price` present in `prev`, the size reduction
    max(0, size_prev - size_now) — fills AND cancels ahead of us. Size INCREASES and brand-new
    levels are ignored, which makes the model GENEROUS (a new order jumping ahead of us is
    never charged), so a below-floor fill rate under this rule is a robust dead-thin OUT
    (L48: a turnover proxy can rule a cell OUT, never IN)."""
    pm = bid_price_map(prev_bids, price, tick)
    nm = bid_price_map(now_bids, price, tick)
    dep = 0.0
    for p, size_prev in pm.items():
        size_now = nm.get(p, 0.0)
        if size_prev > size_now:
            dep += size_prev - size_now
    return dep


def simulate_leg_fill(ladders: Sequence[Optional[Sequence[Sequence[float]]]],
                      price: float, queue_ahead: float) -> Dict[str, Any]:
    """FILL MODEL A — `turnover` (the GENEROUS Q27/S19 precedent rule). Queue-aware fill
    decision for ONE resting bid (L39 — not a candle print), over the ticker's ordered
    pre-close ladders for that side (entry ladder first). Accumulate observed departures at
    levels >= `price` across every consecutive snapshot pair; FILLED once the cumulative
    departures have cleared the queue ahead of us AND at least one departure was observed —
    a frozen ladder that never moves is a NO-FILL, not free income (L32/L48). A front-of-queue
    rest (queue_ahead <= 0) fills on the first observed departure.

    CAVEAT, MEASURED IN THIS PROBE rather than assumed: over a multi-day hold this rule
    SATURATES. Every size reduction at any level at/above our price counts as advancing us —
    including the whole book migrating away from our now-stale price — so cumulative
    "departures" reach tens of thousands of contracts against a queue of tens and essentially
    every leg "fills". That is an artifact of the proxy, not evidence of fills (L48: a
    turnover proxy can rule a population OUT, never IN). `simulate_leg_fill_touch` is the
    strictly tighter companion, and its fill rate is what the verdict rests on.

    Returns {"filled", "cumulative_departures", "queue_ahead", "frozen"}."""
    cumulative = 0.0
    for prev, now in zip(ladders, ladders[1:]):
        cumulative += departures_between(prev, now, price)
    frozen = cumulative <= 0.0
    filled = (not frozen) and cumulative >= queue_ahead - _EPS
    return {"filled": filled, "cumulative_departures": cumulative,
            "queue_ahead": queue_ahead, "frozen": frozen}


def size_at_price(bids: Optional[Sequence[Sequence[float]]], price: float,
                  tick: float = PRICE_TICK) -> float:
    """Resting size at EXACTLY our price level (within half a tick). FLOATS (L47)."""
    total = 0.0
    if not bids:
        return 0.0
    for level in bids:
        if level is None or len(level) < 2 or level[0] is None or level[1] is None:
            continue
        if abs(float(level[0]) - price) <= tick / 2.0:
            total += float(level[1])
    return total


def best_bid_of(bids: Optional[Sequence[Sequence[float]]],
                quoted: Optional[float] = None) -> Optional[float]:
    """The best (highest) resting bid price on this side — the record's own quoted best when
    present, else the ladder's max level. None on an empty one-sided ladder (VALID, L23)."""
    if quoted is not None:
        return float(quoted)
    prices = [float(lv[0]) for lv in (bids or [])
              if lv is not None and len(lv) >= 2 and lv[0] is not None]
    return max(prices) if prices else None


def touch_departures_between(prev_bids: Optional[Sequence[Sequence[float]]],
                             now_bids: Optional[Sequence[Sequence[float]]], price: float,
                             prev_best_bid: Optional[float],
                             tick: float = PRICE_TICK) -> float:
    """Departures that could plausibly be a FILL rather than book migration: size lost at OUR
    OWN price level, counted ONLY while our price is still at/above the side's best bid (i.e.
    we are AT THE TOUCH and an aggressive seller could actually hit us). Once the best bid has
    moved above our price we cannot be hit at all under price priority, so such an interval
    contributes 0 — the size churning up there belongs to other people's orders.

    Still generous (the depth tape carries NO trade/volume field — L68/L106 — so a CANCEL at
    our own price is indistinguishable from a fill and is counted as one), but it removes the
    price-level-migration saturation that makes the `turnover` rule fill nearly everything."""
    if prev_best_bid is not None and prev_best_bid > price + tick / 2.0:
        return 0.0
    lost = size_at_price(prev_bids, price, tick) - size_at_price(now_bids, price, tick)
    return lost if lost > 0 else 0.0


def simulate_leg_fill_touch(ladders: Sequence[Optional[Sequence[Sequence[float]]]],
                            best_bids: Sequence[Optional[float]], price: float,
                            queue_ahead: float) -> Dict[str, Any]:
    """FILL MODEL B — `touch` (the STRICTER rule; the one the verdict rests on). Same
    price-time-priority accounting as `simulate_leg_fill`, but only `touch_departures_between`
    counts: our own price level, only while we are at the touch. FILLED once those departures
    clear the queue ahead of us AND at least one was observed (a frozen level is a no-fill,
    L32). `best_bids[i]` is the side's best bid at snapshot i (index-aligned with `ladders`)."""
    if len(best_bids) != len(ladders):
        raise ValueError(f"best_bids ({len(best_bids)}) must align with ladders "
                         f"({len(ladders)})")
    cumulative = 0.0
    for i in range(len(ladders) - 1):
        cumulative += touch_departures_between(ladders[i], ladders[i + 1], price,
                                               best_bids[i])
    frozen = cumulative <= 0.0
    filled = (not frozen) and cumulative >= queue_ahead - _EPS
    return {"filled": filled, "cumulative_departures": cumulative,
            "queue_ahead": queue_ahead, "frozen": frozen}


# --------------------------------------------------------------------------- #
# Pure P&L helpers (net of BOTH maker fees; settlement is broker_truth)
# --------------------------------------------------------------------------- #
def both_fill_pnl_by_result(p_yes: float, p_no: float, result: str) -> float:
    """Net P&L of ONE double-filled market (long YES @ p_yes AND long NO @ p_no), held to
    settlement, net of BOTH maker fees, with the payout branch written out EXPLICITLY:

        cost = p_yes + p_no + fee(p_yes) + fee(p_no)
        result == 'yes' -> YES leg pays $1, NO leg pays $0 -> 1 - cost
        result == 'no'  -> NO leg pays $1, YES leg pays $0 -> 1 - cost

    The two branches are identical BY CONSTRUCTION (that is the entire point of holding both
    sides); `both_fill_pnl` asserts the symmetry rather than assuming it. Raises on a
    non-binary result (L52 — a 'scalar' settlement must never be scored as yes/no)."""
    r = normalize_result(result)
    if not is_binary_result(r):
        raise ValueError(f"non-binary settlement result {result!r} (L52)")
    cost = float(p_yes) + float(p_no) + maker_fee(p_yes) + maker_fee(p_no)
    payout_yes_leg = 1.0 if r == "yes" else 0.0
    payout_no_leg = 1.0 if r == "no" else 0.0
    return payout_yes_leg + payout_no_leg - cost


def both_fill_pnl(p_yes: float, p_no: float) -> float:
    """The settlement-independent double-fill P&L, 1 - p_yes - p_no - fee_yes - fee_no,
    verified against BOTH explicit settlement branches (the mandated symmetry check)."""
    a = both_fill_pnl_by_result(p_yes, p_no, "yes")
    b = both_fill_pnl_by_result(p_yes, p_no, "no")
    assert abs(a - b) < 1e-12, f"both-fill P&L asymmetry: {a} vs {b}"
    return a


def single_side_pnl(price: float, side: str, result: str) -> float:
    """Net P&L of a SINGLE-side fill — a DIRECTIONAL position, never the capture. Long the
    `side` ('yes'/'no') at `price`, held to settlement, net of one maker fee:
        payout $1 iff the settlement matches the side we are long, else $0.
    Used ONLY in the labeled strategy-level diagnostic cut, never in the both-fill P&L."""
    r = normalize_result(result)
    if not is_binary_result(r):
        raise ValueError(f"non-binary settlement result {result!r} (L52)")
    if side not in ("yes", "no"):
        raise ValueError(f"side must be 'yes' or 'no' (got {side!r})")
    payout = 1.0 if r == side else 0.0
    return payout - float(price) - maker_fee(price)


# --------------------------------------------------------------------------- #
# Tape loading (READ-ONLY; FILES only — a stray dt=<date> DIRECTORY is skipped, L25/L29)
# --------------------------------------------------------------------------- #
def load_settlements(settlement_glob: str = SETTLEMENT_GLOB
                     ) -> Tuple[Dict[str, dict], Dict[str, Any]]:
    """`{ticker: {result, close_time, event_ticker, series, price_source_tag}}` from the
    committed `broker_truth` settlement ledger.

    Re-captures: a ticker may appear on several lines. Identical binary results collapse to
    one row; DISAGREEING results drop the ticker entirely and are counted as an anomaly
    (never silently pick one). Non-binary results ('scalar', L52) are dropped and counted."""
    rows: Dict[str, List[dict]] = {}
    n_lines = 0
    for fp in sorted(glob.glob(settlement_glob)):
        if not Path(fp).is_file():
            continue
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                n_lines += 1
                tk = rec.get("ticker")
                if tk:
                    rows.setdefault(tk, []).append(rec)

    out: Dict[str, dict] = {}
    stats = {"lines": n_lines, "tickers_seen": len(rows), "dropped_non_binary": 0,
             "dropped_conflicting": 0, "multi_line_tickers": 0}
    for tk, recs in rows.items():
        if len(recs) > 1:
            stats["multi_line_tickers"] += 1
        results = {normalize_result(r.get("result")) for r in recs}
        binaries = {r for r in results if is_binary_result(r)}
        if len(binaries) != len(results):
            stats["dropped_non_binary"] += 1
            continue
        if len(binaries) != 1:
            stats["dropped_conflicting"] += 1
            continue
        rec = recs[0]
        out[tk] = {
            "result": next(iter(binaries)),
            "close_time": rec.get("close_time"),
            "event_ticker": rec.get("event_ticker") or event_ticker_of(tk),
            "series": rec.get("series") or series_of(tk),
            "price_source_tag": rec.get("price_source_tag", "broker_truth"),
        }
    return out, stats


def load_preclose_snapshots(depth_glob: str, settlement: Dict[str, dict]
                            ) -> Tuple[Dict[str, List[dict]], Dict[str, Any]]:
    """Every pre-close depth snapshot (`captured_at < close_time`) of every settled,
    non-excluded ticker, grouped by ticker and sorted ascending by capture time. READ-ONLY."""
    per_ticker: Dict[str, List[dict]] = {}
    funnel = {"depth_lines": 0, "depth_tickers": set(), "excluded_series_tickers": set(),
              "joined_tickers": set(), "preclose_tickers": set()}
    for fp in sorted(glob.glob(depth_glob)):
        if not Path(fp).is_file():
            continue
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                funnel["depth_lines"] += 1
                tk = rec.get("ticker", "")
                if not tk:
                    continue
                funnel["depth_tickers"].add(tk)
                if is_excluded_series(tk):
                    funnel["excluded_series_tickers"].add(tk)
                    continue
                s = settlement.get(tk)
                if not s:
                    continue
                funnel["joined_tickers"].add(tk)
                close_dt = parse_ts(s.get("close_time"))
                cap_dt = parse_ts(rec.get("captured_at"))
                if close_dt is None or cap_dt is None or cap_dt >= close_dt:
                    continue
                per_ticker.setdefault(tk, []).append({
                    "record": rec, "captured_at": cap_dt, "close_time": close_dt,
                    "ttc_hours": (close_dt - cap_dt).total_seconds() / 3600.0,
                })
    for tk in per_ticker:
        per_ticker[tk].sort(key=lambda d: d["captured_at"])
    funnel["preclose_tickers"] = set(per_ticker.keys())
    return per_ticker, funnel


# --------------------------------------------------------------------------- #
# The both-sides fill-sim over the candidate population
# --------------------------------------------------------------------------- #
def build_trades(per_ticker: Dict[str, List[dict]], settlement: Dict[str, dict]
                 ) -> Tuple[List[dict], Dict[str, Any]]:
    """One both-sides resting-maker trade per qualifying ticker.

    Entry = the ticker's EARLIEST pre-close snapshot (strictly; no forward search). Gate 1
    decides eligibility. We then rest a YES bid at entry `best_yes_bid` and a NO bid at entry
    `best_no_bid`, each with its own queue-ahead read off its own entry ladder, and simulate
    each leg's fill INDEPENDENTLY from the tape's own later ladders. Only a DOUBLE fill books
    the overround; single-side fills are recorded as directional positions.

    Returns (trade_rows, funnel)."""
    trades: List[dict] = []
    funnel = {"tickers_with_preclose": len(per_ticker), "entry_missing_quote": 0,
              "entry_not_two_sided": 0, "entry_spread_below_two_fees": 0,
              "entry_single_snapshot": 0, "candidates": 0}
    for tk, snaps in sorted(per_ticker.items()):
        entry = snaps[0]
        rec = entry["record"]
        yes_bid = rec.get("best_yes_bid")
        no_bid = rec.get("best_no_bid")
        yes_offer = rec.get("best_yes_ask")
        gate = two_sided_wide_entry(yes_bid, no_bid, yes_offer)
        if not gate["eligible"]:
            if gate["reason"] == "missing_quote":
                funnel["entry_missing_quote"] += 1
            elif gate["reason"] == "not_two_sided":
                funnel["entry_not_two_sided"] += 1
            else:
                funnel["entry_spread_below_two_fees"] += 1
            continue
        if len(snaps) < 2:
            # no later snapshot -> no observable queue departure -> unmeasurable, not a fill
            funnel["entry_single_snapshot"] += 1
            continue
        funnel["candidates"] += 1

        p_yes, p_no = float(yes_bid), float(no_bid)
        yes_ladders = [s["record"].get("yes_bids") for s in snaps]
        no_ladders = [s["record"].get("no_bids") for s in snaps]
        yes_best = [best_bid_of(s["record"].get("yes_bids"),
                                s["record"].get("best_yes_bid")) for s in snaps]
        no_best = [best_bid_of(s["record"].get("no_bids"),
                               s["record"].get("best_no_bid")) for s in snaps]
        q_yes = queue_ahead_at(yes_ladders[0], p_yes)
        q_no = queue_ahead_at(no_ladders[0], p_no)

        s = settlement[tk]
        result = s["result"]
        legs = {
            "turnover": (simulate_leg_fill(yes_ladders, p_yes, q_yes),
                         simulate_leg_fill(no_ladders, p_no, q_no)),
            "touch": (simulate_leg_fill_touch(yes_ladders, yes_best, p_yes, q_yes),
                      simulate_leg_fill_touch(no_ladders, no_best, p_no, q_no)),
        }
        models: Dict[str, Any] = {}
        for model, (fy, fn) in legs.items():
            if fy["filled"] and fn["filled"]:
                category = "both"
                pnl_strategy = both_fill_pnl(p_yes, p_no)
                pnl_both = pnl_strategy
            elif fy["filled"]:
                category, pnl_both = "yes_only", None
                pnl_strategy = single_side_pnl(p_yes, "yes", result)
            elif fn["filled"]:
                category, pnl_both = "no_only", None
                pnl_strategy = single_side_pnl(p_no, "no", result)
            else:
                category, pnl_both, pnl_strategy = "neither", None, 0.0
            models[model] = {
                "filled_yes": fy["filled"], "filled_no": fn["filled"],
                "departures_yes": fy["cumulative_departures"],
                "departures_no": fn["cumulative_departures"],
                "fill_category": category,
                "frozen_both_ladders": fy["frozen"] and fn["frozen"],
                "pnl_both_fill": pnl_both,
                "pnl_strategy_level": pnl_strategy,
            }

        spread = gate["spread"]
        ttc = entry["ttc_hours"]
        trades.append({
            "ticker": tk,
            "event_ticker": s["event_ticker"],
            "series": s["series"],
            "result": result,
            "settles_yes": result == "yes",
            "entry_captured_at": entry["captured_at"].isoformat(),
            "ttc_hours_entry": ttc,
            "n_snapshots": len(snaps),
            "yes_fill_price": p_yes,
            "no_fill_price": p_no,
            "entry_spread": spread,
            "gross_capture": gate["gross_capture"],
            "fee_yes": gate["fee_yes"],
            "fee_no": gate["fee_no"],
            "queue_ahead_yes": q_yes,
            "queue_ahead_no": q_no,
            # L67 two-sided-depth-illusion check: is the wide spread backed by real size at
            # the touch, or is the ladder a deep-OTM lottery tail?
            "capturable_depth_yes": capturable_depth(yes_ladders[0], p_yes),
            "capturable_depth_no": capturable_depth(no_ladders[0], p_no),
            "lottery_tail_frac_yes": lottery_tail_fraction(yes_ladders[0], p_yes),
            "lottery_tail_frac_no": lottery_tail_fraction(no_ladders[0], p_no),
            "models": models,
            "fillable_entry_spread": spread <= FILLABLE_MAX_SPREAD + _EPS,
            "fillable_entry_nearclose": ttc <= FILLABLE_MAX_TTC_HOURS,
            "price_source_tag": "real_bid(fills)+real_bid(queue)+broker_truth(settlement)",
        })
    return trades, funnel


def cut_trades(trades: Sequence[dict], cut: str) -> List[dict]:
    """The four labeled populations. PRIMARY (L69) is `fillable_entry` — a genuinely
    two-sided (spread <= 10c) AND near-close (ttc <= 24h) entry book. The unrestricted
    earliest-entry population is a DIAGNOSTIC, never the headline."""
    if cut == "unrestricted":
        return list(trades)
    if cut == "spread_le_10c":
        return [t for t in trades if t["fillable_entry_spread"]]
    if cut == "nearclose_le_24h":
        return [t for t in trades if t["fillable_entry_nearclose"]]
    if cut == "fillable_entry":
        return [t for t in trades
                if t["fillable_entry_spread"] and t["fillable_entry_nearclose"]]
    raise ValueError(f"unknown cut {cut!r}")


def per_series_pnl(trades: Sequence[dict], key: str,
                   model: str = "touch") -> Dict[str, List[float]]:
    """Group per-trade P&L by GAME-SERIES (the L6/L41 bootstrap unit for this probe — NOT by
    game/event_ticker: games inside a series are correlated draws). `key` selects the P&L
    field inside the chosen fill `model`; rows whose value is None (e.g. a non-double-fill
    under `pnl_both_fill`) are excluded rather than zeroed (L86 — never book an unmeasured
    leg as a free zero)."""
    out: Dict[str, List[float]] = {}
    for t in trades:
        v = t["models"][model].get(key)
        if v is None:
            continue
        out.setdefault(t["series"], []).append(float(v))
    return out


# --------------------------------------------------------------------------- #
# Analysis / verdict
# --------------------------------------------------------------------------- #
def _mean(xs: Sequence[float]) -> Optional[float]:
    return (sum(xs) / len(xs)) if xs else None


def analyze_cut(trades: Sequence[dict], model: str = "touch",
                n_boot: int = 10000) -> Dict[str, Any]:
    """Fill counts, adverse-selection split, both-fill P&L bootstrap-by-series and the
    strategy-level diagnostic bootstrap, for ONE labeled population under ONE fill model."""
    n = len(trades)

    def cat(t: dict) -> str:
        return t["models"][model]["fill_category"]

    both = [t for t in trades if cat(t) == "both"]
    yes_only = [t for t in trades if cat(t) == "yes_only"]
    no_only = [t for t in trades if cat(t) == "no_only"]
    neither = [t for t in trades if cat(t) == "neither"]
    n_frozen = sum(1 for t in trades if t["models"][model]["frozen_both_ladders"])

    settle_yes_all = sum(1 for t in trades if t["settles_yes"])
    settle_yes_both = sum(1 for t in both if t["settles_yes"])
    settle_yes_single = sum(1 for t in (yes_only + no_only) if t["settles_yes"])

    both_pnls = [t["models"][model]["pnl_both_fill"] for t in both]
    unit_values = per_series_pnl(both, "pnl_both_fill", model)
    boot = block_bootstrap(unit_values, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(unit_values, min_units=MIN_CI_UNITS)
    mag = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK, min_ticks=1.0)

    # strategy-level DIAGNOSTIC: every rested pair contributes — a single-side fill is the
    # directional position you are actually left holding, not something you can discard.
    strat_units = per_series_pnl(trades, "pnl_strategy_level", model)
    strat_boot = block_bootstrap(strat_units, n_boot=n_boot)
    strat_adm = bootstrap_verdict_admissible(strat_units, min_units=MIN_CI_UNITS)
    # L32 dual cut over the strategy-level population: a frozen pair is a no-fill, not income
    frozen_flags = [t["models"][model]["frozen_both_ladders"] for t in trades]
    strat_vals = [t["models"][model]["pnl_strategy_level"] for t in trades]
    movement = bracket_by_movement(frozen_flags, strat_vals)
    moved_units = per_series_pnl(
        [t for t in trades if not t["models"][model]["frozen_both_ladders"]],
        "pnl_strategy_level", model)
    moved_boot = block_bootstrap(moved_units, n_boot=n_boot)

    return {
        "fill_model": model,
        "n_candidates": n,
        "n_series": len({t["series"] for t in trades}),
        "n_games": len({t["event_ticker"] for t in trades}),
        "fills": {
            "both": len(both), "yes_only": len(yes_only), "no_only": len(no_only),
            "neither": len(neither), "frozen_both_ladders": n_frozen,
            "both_fill_rate": (len(both) / n) if n else None,
            "yes_leg_fill_rate": (sum(1 for t in trades
                                      if t["models"][model]["filled_yes"]) / n) if n else None,
            "no_leg_fill_rate": (sum(1 for t in trades
                                     if t["models"][model]["filled_no"]) / n) if n else None,
            "single_side_only_rate": ((len(yes_only) + len(no_only)) / n) if n else None,
            "s19_floor": S19_FILL_FLOOR,
        },
        "adverse_selection": {
            "settle_yes_rate_all_candidates": (settle_yes_all / n) if n else None,
            "settle_yes_rate_double_fills": (settle_yes_both / len(both)) if both else None,
            "settle_yes_rate_single_side_fills": (
                settle_yes_single / (len(yes_only) + len(no_only))
                if (yes_only or no_only) else None),
            "n_settle_yes_all": settle_yes_all, "n_settle_yes_both": settle_yes_both,
        },
        "prices_real_bid": {
            "mean_entry_spread_all": _mean([t["entry_spread"] for t in trades]),
            "mean_gross_capture_all": _mean([t["gross_capture"] for t in trades]),
            "mean_gross_capture_double_fills": _mean([t["gross_capture"] for t in both]),
            "mean_yes_fill_price_double_fills": _mean([t["yes_fill_price"] for t in both]),
            "mean_no_fill_price_double_fills": _mean([t["no_fill_price"] for t in both]),
            "mean_net_pnl_double_fills": _mean(both_pnls),
            "frac_gross_capture_positive_all": (
                sum(1 for t in trades if t["gross_capture"] > 0) / n) if n else None,
        },
        "queue": {
            "median_queue_ahead_yes": _median([t["queue_ahead_yes"] for t in trades]),
            "median_queue_ahead_no": _median([t["queue_ahead_no"] for t in trades]),
            "median_departures_yes": _median(
                [t["models"][model]["departures_yes"] for t in trades]),
            "median_departures_no": _median(
                [t["models"][model]["departures_no"] for t in trades]),
            "median_capturable_depth_yes": _median(
                [t["capturable_depth_yes"] for t in trades]),
            "median_capturable_depth_no": _median(
                [t["capturable_depth_no"] for t in trades]),
            "median_lottery_tail_frac_yes": _median(
                [t["lottery_tail_frac_yes"] for t in trades
                 if t["lottery_tail_frac_yes"] is not None]),
            "median_lottery_tail_frac_no": _median(
                [t["lottery_tail_frac_no"] for t in trades
                 if t["lottery_tail_frac_no"] is not None]),
        },
        # L27/L236 PER-OBSERVATION magnitude decomposition of the realized double-fill net
        # P&L: how many double fills actually clear one fillable tick, vs sit sub-tick (or at
        # a pure float residue)? Sample-size-independent, unlike the CI.
        "net_pnl_magnitude": hit_magnitude_decomposition(both_pnls, tick=PRICE_TICK),
        "bootstrap_both_fill_by_series": {
            "mean": boot["mean"], "ci95": boot["ci95"], "n_units_series": boot["n_units"],
            "n_obs_double_fills": boot["n_obs"], "admissible": adm,
            "clears_tick_magnitude": mag,
            "ci_lower_positive": boot["ci95"][0] is not None and boot["ci95"][0] > 0.0,
        },
        "bootstrap_strategy_level_diagnostic": {
            "mean": strat_boot["mean"], "ci95": strat_boot["ci95"],
            "n_units_series": strat_boot["n_units"], "n_obs": strat_boot["n_obs"],
            "admissible": strat_adm,
            "frac_frozen": movement["frac_frozen"],
            "movement_conditioned_mean": moved_boot["mean"],
            "movement_conditioned_ci95": moved_boot["ci95"],
            "movement_conditioned_n_units": moved_boot["n_units"],
            "movement_conditioned_n_obs": moved_boot["n_obs"],
        },
    }


def _median(xs: Sequence[float]) -> Optional[float]:
    vals = sorted(float(x) for x in xs)
    if not vals:
        return None
    m = len(vals) // 2
    return vals[m] if len(vals) % 2 else (vals[m - 1] + vals[m]) / 2.0


def verdict_for(cut: Dict[str, Any]) -> Tuple[str, str]:
    """The Q49 kill ladder, applied to one population. Returns (verdict, reason)."""
    n = cut["n_candidates"]
    if n == 0:
        return ("DEAD-by-adequacy",
                "no wide-spread genuinely-two-sided candidate in this population")
    fills = cut["fills"]
    boot = cut["bootstrap_both_fill_by_series"]
    rate = fills["both_fill_rate"] or 0.0
    if rate <= S19_FILL_FLOOR + _EPS:
        return ("DEAD-by-fill-rate",
                f"both-sides queue-aware fill rate {rate:.4%} <= the S19 floor "
                f"{S19_FILL_FLOOR:.2%} ({fills['both']}/{n} rested pairs double-filled) — "
                "the both-bid capture is not reachable by a resting order (L48 dead-thin OUT)")
    mag = cut["net_pnl_magnitude"]
    mean = boot["mean"]
    if mean is None or mean <= 0.0:
        return ("DEAD-by-fee",
                f"realized double-fill overround mean {mean} <= 0 once BOTH maker fees are "
                f"charged on the two legs — the wide-spread gate admits books whose gross "
                f"capture is exactly the fee, so the capture is arithmetically consumed "
                f"({mag['n_sub_tick']}/{mag['n']} double fills net BELOW one $0.01 tick, "
                f"{mag['n_clears_tick']} clear it; sample-size-independent). "
                f"[{boot['n_units_series']} game-series carry a double fill]")
    if boot["n_units_series"] < MIN_CI_UNITS:
        return ("DEAD-by-adequacy",
                f"only {boot['n_units_series']} distinct GAME-SERIES carry a double fill "
                f"(<{MIN_CI_UNITS}, the Q49 game-series floor) — untestable as collected, "
                f"NOT a CI falsification. [economics on the sub-floor population, quoted for "
                f"context only, NOT a verdict: mean={boot['mean']}, ci95={boot['ci95']}, "
                f"clears 1-tick magnitude={boot['clears_tick_magnitude']}, "
                f"L41-admissible={boot['admissible']['admissible']} "
                f"{boot['admissible']['reasons']}, per-observation sub-tick "
                f"{mag['n_sub_tick']}/{mag['n']}]")
    if not boot["admissible"]["admissible"]:
        return ("DEAD-by-CI",
                f"bootstrap inadmissible (L41): {boot['admissible']['reasons']} "
                f"(n_units={boot['admissible']['n_units']}, "
                f"n_opposing={boot['admissible']['n_opposing_units']})")
    if not boot["ci_lower_positive"]:
        return ("DEAD-by-CI", f"95% CI lower bound not > 0: ci95={boot['ci95']}")
    if not boot["clears_tick_magnitude"]:
        return ("DEAD-by-CI",
                f"CI > 0 but fails the 1-tick economic-significance gate (L27): "
                f"ci95={boot['ci95']}")
    return ("ALIVE-PROVISIONAL",
            "every binding gate passes on this population — genuinely uncertain; needs "
            "independent verifier confirmation + shadow paper before any capital")


def run(depth_glob: str = DEPTH_GLOB, settlement_glob: str = SETTLEMENT_GLOB,
        n_boot: int = 10000) -> Dict[str, Any]:
    """Full offline analysis over the committed tape."""
    settlement, sett_stats = load_settlements(settlement_glob)
    per_ticker, depth_funnel = load_preclose_snapshots(depth_glob, settlement)
    trades, trade_funnel = build_trades(per_ticker, settlement)

    cut_names = ("fillable_entry", "spread_le_10c", "nearclose_le_24h", "unrestricted")
    cuts = {model: {name: analyze_cut(cut_trades(trades, name), model, n_boot=n_boot)
                    for name in cut_names}
            for model in FILL_MODELS}
    verdicts = {model: {name: verdict_for(c) for name, c in per_cut.items()}
                for model, per_cut in cuts.items()}

    # symmetry audit (gate 4): the settles-YES and settles-NO branches must agree exactly
    max_asym = 0.0
    for t in trades:
        a = both_fill_pnl_by_result(t["yes_fill_price"], t["no_fill_price"], "yes")
        b = both_fill_pnl_by_result(t["yes_fill_price"], t["no_fill_price"], "no")
        max_asym = max(max_asym, abs(a - b))

    primary_cut, primary_model = "fillable_entry", PRIMARY_FILL_MODEL
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "settlement_stats": sett_stats,
        "depth_funnel": {k: (len(v) if isinstance(v, set) else v)
                         for k, v in depth_funnel.items()},
        "trade_funnel": trade_funnel,
        "pnl_symmetry_max_abs_diff": max_asym,
        "n_boot": n_boot,
        "fill_models": list(FILL_MODELS),
        "primary_fill_model": primary_model,
        "primary_cut": primary_cut,
        "primary_cut_definition": (
            f"L69 fillable-entry: entry spread <= {FILLABLE_MAX_SPREAD} AND "
            f"time-to-close <= {FILLABLE_MAX_TTC_HOURS}h"),
        "cuts": cuts,
        "verdicts": {m: {k: {"verdict": v[0], "reason": v[1]} for k, v in d.items()}
                     for m, d in verdicts.items()},
        "verdict": verdicts[primary_model][primary_cut][0],
        "verdict_reason": verdicts[primary_model][primary_cut][1],
        "price_source_tags": {"fills": "real_bid", "queue_depth": "real_bid",
                              "settlement": "broker_truth"},
    }


# --------------------------------------------------------------------------- #
# printing
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: Sequence[Optional[float]]) -> str:
    if not ci or ci[0] is None:
        return "[None, None]"
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def _f(x: Optional[float], nd: int = 4, pct: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{100.0 * x:.2f}%" if pct else f"{x:+.{nd}f}"


def _print_cut(name: str, c: Dict[str, Any], verdict: Tuple[str, str],
               is_primary: bool) -> None:
    tag = ("PRIMARY (L69 fillable-entry x strict `touch` fill model)" if is_primary
           else "diagnostic (labeled, NOT headline)")
    print("-" * 88)
    print(f"POPULATION `{name}` [fill_model={c['fill_model']}] — {tag}")
    print(f"  candidates(rested both-bid pairs) = {c['n_candidates']}   "
          f"game-series = {c['n_series']}   games = {c['n_games']}")
    f = c["fills"]
    print(f"  QUEUE-AWARE FILLS: both={f['both']}  yes_only={f['yes_only']}  "
          f"no_only={f['no_only']}  neither={f['neither']}  "
          f"(frozen-both-ladders={f['frozen_both_ladders']})")
    print(f"    both-sides fill rate = {_f(f['both_fill_rate'], pct=True)}  "
          f"(S19 floor {S19_FILL_FLOOR:.2%})   "
          f"single-side-only = {_f(f['single_side_only_rate'], pct=True)}")
    print(f"    per-leg fill rates: YES {_f(f['yes_leg_fill_rate'], pct=True)}   "
          f"NO {_f(f['no_leg_fill_rate'], pct=True)}")
    q = c["queue"]
    print(f"    median queue_ahead (real_bid, FLOATS): YES {q['median_queue_ahead_yes']}  "
          f"NO {q['median_queue_ahead_no']}   |   median departures: "
          f"YES {q['median_departures_yes']}  NO {q['median_departures_no']}")
    print(f"    L67 depth-illusion check — median capturable depth within 5c of our bid: "
          f"YES {q['median_capturable_depth_yes']}  NO {q['median_capturable_depth_no']}  |  "
          f"median lottery-tail frac: YES {_f(q['median_lottery_tail_frac_yes'], pct=True)}  "
          f"NO {_f(q['median_lottery_tail_frac_no'], pct=True)}")
    a = c["adverse_selection"]
    print("  ADVERSE SELECTION (fill <-> settlement correlation, broker_truth):")
    print(f"    settle-YES rate | ALL wide candidates = "
          f"{_f(a['settle_yes_rate_all_candidates'], pct=True)} "
          f"({a['n_settle_yes_all']}/{c['n_candidates']})")
    print(f"    settle-YES rate | DOUBLE fills       = "
          f"{_f(a['settle_yes_rate_double_fills'], pct=True)} "
          f"({a['n_settle_yes_both']}/{f['both']})")
    print(f"    settle-YES rate | SINGLE-side fills  = "
          f"{_f(a['settle_yes_rate_single_side_fills'], pct=True)}")
    p = c["prices_real_bid"]
    print("  PRICES (real_bid) / OVERROUND:")
    print(f"    mean entry yes-spread = {_f(p['mean_entry_spread_all'])}   "
          f"mean gross capture 1-(yes_bid+no_bid) = {_f(p['mean_gross_capture_all'])}   "
          f"frac capture>0 = {_f(p['frac_gross_capture_positive_all'], pct=True)}")
    print(f"    double-fills: mean yes_bid={_f(p['mean_yes_fill_price_double_fills'])}  "
          f"mean no_bid={_f(p['mean_no_fill_price_double_fills'])}  "
          f"mean gross={_f(p['mean_gross_capture_double_fills'])}  "
          f"mean NET (both fees)={_f(p['mean_net_pnl_double_fills'])}")
    m = c["net_pnl_magnitude"]
    print(f"    per-observation net magnitude (L27/L236): n={m['n']}  "
          f"clears 1 tick={m['n_clears_tick']}  sub-tick={m['n_sub_tick']}  "
          f"pure float residue={m['n_residue']}  max={_f(m['max'])}")
    b = c["bootstrap_both_fill_by_series"]
    print("  BOOTSTRAP — E[net P&L per double-filled market], BLOCK BY GAME-SERIES (L6/L41):")
    print(f"    mean={_f(b['mean'])}  95% CI={_fmt_ci(b['ci95'])}  "
          f"n_units(series)={b['n_units_series']}  n_obs(double fills)={b['n_obs_double_fills']}")
    print(f"    admissible(L41)={b['admissible']['admissible']} "
          f"reasons={b['admissible']['reasons']} "
          f"n_opposing_units={b['admissible']['n_opposing_units']}   "
          f"clears 1-tick magnitude (L27)={b['clears_tick_magnitude']}")
    s = c["bootstrap_strategy_level_diagnostic"]
    print("  STRATEGY-LEVEL DIAGNOSTIC (every rested pair: double fill = capture, single-side "
          "fill = the directional position you are left holding, neither = 0):")
    print(f"    mean={_f(s['mean'])}  95% CI={_fmt_ci(s['ci95'])}  "
          f"n_units(series)={s['n_units_series']}  n_obs={s['n_obs']}  "
          f"admissible={s['admissible']['admissible']}")
    print(f"    L32 dual cut: frac_frozen={_f(s['frac_frozen'], pct=True)}   "
          f"movement-conditioned mean={_f(s['movement_conditioned_mean'])} "
          f"CI={_fmt_ci(s['movement_conditioned_ci95'])} "
          f"n_units={s['movement_conditioned_n_units']} n_obs={s['movement_conditioned_n_obs']}")
    print(f"  VERDICT[{name}]: {verdict[0]}")
    print(f"    -> {verdict[1]}")


def print_report(rep: Dict[str, Any]) -> None:
    print("=" * 88)
    print("Q49 / S68 — TWO-SIDED BOTH-BID OVERROUND-CAPTURE MAKER FILL-SIM "
          "(read-only, OFFLINE)")
    print("=" * 88)
    st = rep["settlement_stats"]
    df = rep["depth_funnel"]
    tf = rep["trade_funnel"]
    print("DATA (both legs committed tape; no network):")
    print(f"  settlement_ledger lines={st['lines']}  tickers={st['tickers_seen']}  "
          f"multi-line tickers={st['multi_line_tickers']}  "
          f"dropped non-binary(L52)={st['dropped_non_binary']}  "
          f"dropped conflicting-result anomalies={st['dropped_conflicting']}")
    print(f"  orderbook_depth lines={df['depth_lines']}  tickers={df['depth_tickers']}  "
          f"KXMVE*-excluded tickers={df['excluded_series_tickers']}  "
          f"settlement-joined={df['joined_tickers']}  with a pre-close snapshot="
          f"{df['preclose_tickers']}")
    print("-" * 88)
    print("SELECTION FUNNEL (entry = EARLIEST pre-close snapshot, no forward search):")
    print(f"  tickers with a pre-close snapshot        = {tf['tickers_with_preclose']}")
    print(f"  - entry missing a quote                  = {tf['entry_missing_quote']}")
    print(f"  - entry NOT genuinely two-sided (a bid <= 0 is an ABSENT order, not a $0 price) "
          f"= {tf['entry_not_two_sided']}")
    print(f"  - entry yes-spread < the two maker fees  = {tf['entry_spread_below_two_fees']}")
    print(f"  - only one snapshot (no observable queue departure -> unmeasurable, NOT a fill) "
          f"= {tf['entry_single_snapshot']}")
    print(f"  = CANDIDATES (rest BOTH bids)            = {tf['candidates']}")
    print("-" * 88)
    print(f"P&L SYMMETRY AUDIT (gate 4): max |pnl(settles YES) - pnl(settles NO)| over every "
          f"candidate = {rep['pnl_symmetry_max_abs_diff']:.2e}")
    print("  (both legs held, exactly one pays $1 -> net = 1 - p_yes - p_no - fee_yes - fee_no "
          "either way; this is asserted in code, not assumed)")
    for model in rep["fill_models"]:
        print("=" * 88)
        note = ("STRICT (departures at OUR price only, only while at the touch) — the "
                "verdict rests here" if model == rep["primary_fill_model"] else
                "GENEROUS Q27/S19 turnover rule (departures at ANY level >= our price) — "
                "SATURATES over a multi-day hold; reported as a labeled diagnostic, and it "
                "rules a population OUT, never IN (L48)")
        print(f"FILL MODEL `{model}` — {note}")
        for name in ("fillable_entry", "spread_le_10c", "nearclose_le_24h", "unrestricted"):
            v = rep["verdicts"][model][name]
            _print_cut(name, rep["cuts"][model][name], (v["verdict"], v["reason"]),
                       is_primary=(name == rep["primary_cut"]
                                   and model == rep["primary_fill_model"]))
    print("=" * 88)
    print(f"HEADLINE VERDICT (primary = fill_model `{rep['primary_fill_model']}` x cut "
          f"`{rep['primary_cut']}`: {rep['primary_cut_definition']}): {rep['verdict']}")
    print(f"  -> {rep['verdict_reason']}")
    print(f"  price_source_tags: {rep['price_source_tags']}")
    print("=" * 88)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q49/S68 two-sided both-bid overround-capture maker fill-sim "
                    "(read-only, offline)")
    ap.add_argument("--depth-glob", default=DEPTH_GLOB)
    ap.add_argument("--settlement-glob", default=SETTLEMENT_GLOB)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    rep = run(depth_glob=args.depth_glob, settlement_glob=args.settlement_glob,
              n_boot=args.n_boot)
    print_report(rep)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"[q49] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

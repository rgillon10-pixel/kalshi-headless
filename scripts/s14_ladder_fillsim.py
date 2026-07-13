#!/usr/bin/env python3
"""s14_ladder_fillsim.py — S14: maker-side "ladder overround underwriting" fill-sim.

LOOP-QUEUE.md Q13. The idea (registry S14): stand as the underwriter of a complete
mutually-exclusive Kalshi strike ladder — rest a short-YES offer on EVERY member at once,
collect the bracket overround as premium, and pay $1 only on the single member that settles
YES. The dream is `bracket_sum - Sigma_fees - 1 = overround - Sigma_maker_fees` per hour.
This script papers that strategy: read-only over already-captured tape plus read-only,
cached Kalshi candlestick pulls. NO orders, NO auth, NO credentials, NO execution code.

SCOPING DECISION (made by the research-lead, implemented here, NOT relitigated):
Use crypto_hourly tape, NOT sports_pairs. A sports moneyline group has only 2-3 outcomes
(member_count 2-3) — that is not a strike ladder. crypto_hourly's BTC/ETH hourly brackets
ARE a genuine MECE strike ladder (KXBTC ~188 members, KXETH ~75, exactly one strike settles
YES). "Ladder underwriting" is an honest reading of the crypto hourly ladder, not scope creep.

The trade simulated (maker short-YES on the complete ladder):
  - At the EARLIEST capture of each settled event-hour (maximizes horizon H = capture_time
    -> close_time), post a resting short-YES offer at each member's current `yes_ask`
    (real_ask) on EVERY strike simultaneously.
  - FILL of member k within H = a buyer lifts your offer = a trade prints at price >= your
    posted ask during [capture_time, close_time]. This is the MIRROR of s13's resting-bid
    `low <= bid`: a resting SELLER is filled when the realized trade HIGH crosses UP to/through
    the ask (`price.high_dollars >= ask` AND volume > 0). Same optimism class as s13 (a
    candlestick "fill" ignores queue position -> optimistic).
  - PREMIUM collected on a filled strike = ask minus `fee_per_contract(ask, MAKER_FEE_RATE)`
    (never hand-roll a fee — L5/L18; maker rate 0.0175, NOT taker 0.07). Unfilled -> 0.
  - PAYOUT leg (the loss): if the winner strike was among your FILLED strikes you are short
    1 YES settling at $1 -> pay $1 (no settlement fee). Winner unfilled -> no payout.
  - P&L per event-hour = Sigma premium_k(filled) - (1.0 if winner filled else 0.0).

THE structural point (L30 fee-annihilation): Kalshi's maker fee is a FLAT $0.01/contract at
every interior price (`fee_per_contract(P, MAKER_FEE_RATE) == 0.01` for all 0<P<1). So a member with
`yes_ask == 0.01` nets `0.01 - 0.01 = $0.00` whether it fills or not — the entire far-wing
overround (the ~180 1c-floor bands that make bracket_sum ~4-10) is UN-COLLECTABLE by
construction. We report the fraction of each ladder's bracket_sum that sits on 1c-floor asks.

Fetch-budget bound (stated explicitly): a member with `yes_ask <= 0.01` that is NOT the
winner nets exactly $0 whether filled or not (premium 0, no payout), so its fill status
cannot change P&L and we do NOT fetch it. We fetch candlesticks only for members with
`yes_ask >= 0.02` (net-positive premium if filled) PLUS the winner (its fill drives the $1
payout regardless of its ask). This cuts ~130 members/hour to ~15.

Adverse-selection descriptive (the direct measurement): for a small sample of event-hours we
ALSO fetch the FULL ladder and report the fill rate of wings vs near-money vs the winner
strike. The hypothesis being tested is "the winning strike fills eagerly, the wings never do".

Gate (the verdict): E[P&L per event-hour] > 0, 95% block-bootstrap CI, bootstrapped BY
EVENT-HOUR (the independent unit — one settlement determines all winners within an hour, so
strikes within an hour are NOT independent draws; same non-independence logic as S7c-by-game /
L6). Uses `core.bootstrap.block_bootstrap` (not hand-rolled — L33/L34) and
`core.bootstrap.clears_tick_magnitude` (L27 magnitude gate).

Run:
    python scripts/s14_ladder_fillsim.py
    python scripts/s14_ladder_fillsim.py --n-boot 10000 --json-out /tmp/s14.json
    python scripts/s14_ladder_fillsim.py --max-events 50 --full-ladder-sample 8
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import block_bootstrap, clears_tick_magnitude  # noqa: E402
from core.canonical import canonical_json, sha256_hex  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE,
    TAKER_FEE_RATE,
    bracket_sum,
    fee_per_contract,
    infer_strike_spacing,
    overround,
)

TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly"
CACHE_DIR = REPO_ROOT / "tape" / "s14_ladder_fillsim"
FLOOR_ASK = 0.01          # Kalshi 1c minimum; an ask at/below this nets $0 after the flat fee
MIN_PRICED_ASK = 0.02     # smallest ask that nets a positive premium after the flat 1c maker fee
NEARMONEY_STEPS = 3       # near-money band = within this many strike-spacings of the winner


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only — lessons L25/L29)
# --------------------------------------------------------------------------- #
def load_records(tape_dir: Path = TAPE_DIR) -> List[Dict[str, Any]]:
    """Every crypto_hourly record from the canonical *.jsonl day-files. A stray `dt=<date>`
    DIRECTORY of raw blobs (the 2026-07-08 regression, L25/L29) is skipped by the is_file
    guard — never mutates tape."""
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def build_settlement_map(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{settled_event_ticker: {winner_ticker, expiration_value, results}}` from every
    record's `previous_settlement` (broker_truth). Exactly one member has result "yes"."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in records:
        ps = r.get("previous_settlement")
        if not ps:
            continue
        et = ps.get("event_ticker")
        results = ps.get("results")
        if not et or not results:
            continue
        winners = [k for k, v in results.items() if v == "yes"]
        if len(winners) != 1:
            continue  # a valid MECE settlement has exactly one YES
        out[et] = {
            "winner_ticker": winners[0],
            "expiration_value": ps.get("expiration_value"),
            "n_results": len(results),
            "price_source_tag": ps.get("price_source_tag", "broker_truth"),
        }
    return out


def build_earliest_captures(records: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """`{event_ticker: {captured_at, series, current}}` keeping the EARLIEST captured_at per
    event-hour (maximizes horizon to close). Skips null/incomplete current blocks (L15: the
    20-UTC hour lists no crypto group)."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in records:
        cur = r.get("current")
        if not cur or not cur.get("event_ticker") or not cur.get("outcomes"):
            continue
        if not cur.get("close_time"):
            continue
        et = cur["event_ticker"]
        cap = r.get("captured_at")
        if not cap:
            continue
        if et not in out or cap < out[et]["captured_at"]:
            out[et] = {"captured_at": cap, "series": r.get("series"), "current": cur}
    return out


# --------------------------------------------------------------------------- #
# pure ladder arithmetic
# --------------------------------------------------------------------------- #
def _asks(outcomes: List[Dict[str, Any]]) -> List[float]:
    return [float(o["yes_ask"]) for o in outcomes]


def frac_overround_on_1c_floor(outcomes: List[Dict[str, Any]], floor: float = FLOOR_ASK
                                ) -> float:
    """Fraction of the ladder's bracket_sum that sits on 1c-floor asks (ask <= floor) —
    exactly the part of the overround that nets $0 after the flat $0.01 maker fee (L30).
    0.0 on an empty/zero-sum ladder."""
    bsum = bracket_sum(_asks(outcomes))
    if bsum <= 0:
        return 0.0
    floor_sum = bracket_sum([float(o["yes_ask"]) for o in outcomes
                             if float(o["yes_ask"]) <= floor])
    return floor_sum / bsum


def member_premium(ask: float, rate: float = MAKER_FEE_RATE) -> float:
    """Premium a filled short-YES maker offer nets: the ask minus the flat maker fee. `ask`
    is a plain local float here (NOT the raw `yes_ask` dict field) so this stays honest about
    what it is — the collectible income on one filled strike, net of L30's flat 1c fee."""
    return ask - fee_per_contract(ask, rate=rate)


def member_coord(o: Dict[str, Any]) -> Optional[float]:
    """A single strike coordinate for a member, for distance-from-winner binning: the
    midpoint for a `between` band, else whichever of floor/cap strike exists (edge `less`/
    `greater` members). None if neither is present."""
    st = o.get("strike_type")
    fs = o.get("floor_strike")
    cs = o.get("cap_strike")
    if st == "between" and fs is not None and cs is not None:
        return (float(fs) + float(cs)) / 2.0
    if fs is not None:
        return float(fs)
    if cs is not None:
        return float(cs)
    return None


# --------------------------------------------------------------------------- #
# candlestick fill detection — live (cached) Kalshi candlesticks
# --------------------------------------------------------------------------- #
_CLIENT_SINGLETON: Any = None


def _client() -> Any:
    """One throttled read-only client per process (the Kalshi wrapper already rate-limits and
    retries 429/5xx internally). Lazily built so tests never import the network client."""
    global _CLIENT_SINGLETON
    if _CLIENT_SINGLETON is None:
        from validation.v3_market import Kalshi, _load_venue_cfg
        cfg = _load_venue_cfg()
        _CLIENT_SINGLETON = Kalshi(cfg["api_base"], min_interval=0.2)
    return _CLIENT_SINGLETON


def fetch_candles_default(series: str, ticker: str, start_ts: int, end_ts: int,
                          conn_retries: int = 4) -> Dict[str, Any]:
    """Live GET of hourly candlesticks (read-only market data, no auth). Isolated so tests
    inject a fake and never hit the network. The Kalshi wrapper retries 429/5xx; we add a
    small extra retry for transient transport-level resets (ConnectionError) so a single
    reset-by-peer over a ~5k-fetch run does not abort it (the cache is resumable, but a clean
    retry avoids a manual rerun)."""
    import time as _time

    import requests

    client = _client()
    path = f"/series/{series}/markets/{ticker}/candlesticks"
    last_exc: Optional[Exception] = None
    for attempt in range(conn_retries + 1):
        try:
            text = client.get_text(path, start_ts=start_ts, end_ts=end_ts, period_interval=60)
            candles = json.loads(text).get("candlesticks") or []
            return {"candles": candles, "raw_sha256": sha256_hex(text)}
        except requests.exceptions.ConnectionError as exc:  # transient transport reset
            last_exc = exc
            _time.sleep(min(2 ** attempt, 16))
    raise last_exc if last_exc else RuntimeError("unreachable")


def summarize_candles(candles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Reduce raw candles to what a resting SELLER's fill needs: the maximum realized trade
    HIGH (`price.high_dollars`) over the window and the total traded volume. A resting short
    offer fills only if the trade price ever rose to/through it, so the seller mirror of
    s13's `min_low` is `max_high` — keeping full OHLC/ask/bid per candle would balloon the
    cache for no analytical benefit."""
    best_high: Optional[float] = None
    total_vol = 0.0
    for c in candles:
        vol = c.get("volume_fp")
        if vol is not None:
            try:
                total_vol += float(vol)
            except (TypeError, ValueError):
                pass
        high = (c.get("price") or {}).get("high_dollars")
        if high is None:
            continue
        high = float(high)
        if best_high is None or high > best_high:
            best_high = high
    return {"max_high_dollars": best_high, "total_volume": total_vol,
            "n_candles": len(candles)}


def detect_seller_fill(summary: Dict[str, Any], ask: float) -> bool:
    """Filled = the window's maximum realized trade HIGH reached at or above the posted ask
    AND at least one contract traded (volume > 0). The `high >= ask` mirror of s13's resting-
    bid `low <= bid`: a trade at/above your offer is what crosses UP into a resting seller."""
    high = summary.get("max_high_dollars")
    if high is None:
        return False
    if summary.get("total_volume", 0.0) <= 0.0:
        return False
    return high >= ask - 1e-9


def load_candle_summary_cache(cache_dir: Path = CACHE_DIR) -> Dict[str, Dict[str, Any]]:
    """Read the whole cache ONCE per run (keyed by ticker); a rerun over a resolved event is
    a dict lookup, not an API hit."""
    cached: Dict[str, Dict[str, Any]] = {}
    if cache_dir.exists():
        for path in sorted(cache_dir.glob("dt=*.jsonl")):
            if not path.is_file():
                continue
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        rec = json.loads(line)
                        cached[rec["ticker"]] = rec
    return cached


def get_or_fetch_candle_summary(
    ticker: str, series: str, start_ts: int, end_ts: int,
    cache: Dict[str, Dict[str, Any]], cache_dir: Path = CACHE_DIR,
    fetcher: Callable[[str, str, int, int], Dict[str, Any]] = fetch_candles_default,
) -> Dict[str, Any]:
    """One cached, summarized candlestick pull per ticker. `cache` is loaded ONCE by the
    caller and passed in; a miss appends one summary line to disk (resumable across reruns)."""
    if ticker in cache:
        return cache[ticker]
    fetched = fetcher(series, ticker, start_ts, end_ts)
    summary = summarize_candles(fetched["candles"])
    rec = {
        "schema_version": "s14_ladder_fillsim_candle_summary.v1",
        "ticker": ticker, "series": series, "start_ts": start_ts, "end_ts": end_ts,
        **summary, "raw_sha256": fetched["raw_sha256"], "price_source_tag": "real_ask",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    cache[ticker] = rec
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        f.write(canonical_json(rec) + "\n")
    return rec


# --------------------------------------------------------------------------- #
# per-event-hour simulation
# --------------------------------------------------------------------------- #
def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


FillFn = Callable[[str, str, float, int, int], bool]
"""(series, ticker, ask, start_ts, end_ts) -> filled? — injected so tests never hit network."""


def simulate_event(
    event_ticker: str,
    entry: Dict[str, Any],
    settlement: Dict[str, Any],
    fill_fn: FillFn,
    min_priced_ask: float = MIN_PRICED_ASK,
) -> Optional[Dict[str, Any]]:
    """One P&L row per settled event-hour. Fetches a member's fill only when its status can
    change P&L (ask >= min_priced_ask, or it is the winner); all other members are 1c-floor
    wings that net exactly $0 whether filled or not (L30) and are skipped without a fetch."""
    cur = entry["current"]
    series = entry.get("series") or cur.get("series")
    outs = cur["outcomes"]
    close_time = cur.get("close_time")
    if not close_time:
        return None
    try:
        start_ts = int(_parse_iso(entry["captured_at"]).timestamp())
        end_ts = int(_parse_iso(close_time).timestamp())
    except (ValueError, KeyError):
        return None
    if end_ts <= start_ts:
        return None

    winner_ticker = settlement["winner_ticker"]
    asks = _asks(outs)
    bsum = bracket_sum(asks)
    ovr = overround(asks)

    premium_total = 0.0
    n_filled = 0
    n_priced_relevant = 0
    winner_filled = False
    winner_ask: Optional[float] = None
    for o in outs:
        ask = float(o["yes_ask"])
        ticker = o["ticker"]
        is_winner = ticker == winner_ticker
        if is_winner:
            winner_ask = ask
        if ask < min_priced_ask and not is_winner:
            continue  # 1c-floor wing, nets $0 either way — no fetch (L30 fee annihilation)
        n_priced_relevant += 1
        filled = fill_fn(series, ticker, ask, start_ts, end_ts)
        if filled:
            n_filled += 1
            premium_total += member_premium(ask)
            if is_winner:
                winner_filled = True

    payout = 1.0 if winner_filled else 0.0
    pnl = premium_total - payout
    return {
        "event_ticker": event_ticker,
        "series": series,
        "captured_at": entry["captured_at"],
        "close_time": close_time,
        "horizon_min": (end_ts - start_ts) / 60.0,
        "n_members": len(outs),
        "bracket_sum": bsum,
        "overround": ovr,
        "frac_overround_on_1c_floor": frac_overround_on_1c_floor(outs),
        "n_priced_relevant": n_priced_relevant,
        "n_filled": n_filled,
        "premium_collected": premium_total,
        "winner_ticker": winner_ticker,
        "winner_ask": winner_ask,
        "winner_filled": winner_filled,
        "payout": payout,
        "pnl": pnl,
        "price_source_tag": "real_ask+broker_truth",
    }


def pnl_by_event(rows: List[Dict[str, Any]]) -> Dict[str, List[float]]:
    """Block-bootstrap unit = event-hour (L6): one settlement fixes all winners within an
    hour, so each event-hour contributes exactly one independent P&L draw."""
    return {r["event_ticker"]: [r["pnl"]] for r in rows}


# --------------------------------------------------------------------------- #
# full-ladder adverse-selection descriptive (wing vs near-money vs winner fill rates)
# --------------------------------------------------------------------------- #
def classify_members(outs: List[Dict[str, Any]], winner_ticker: str,
                     nearmoney_steps: int = NEARMONEY_STEPS) -> Dict[str, str]:
    """`{ticker: bin}` with bin in {winner, near_money, wing}. near_money = a non-winner
    within `nearmoney_steps` strike-spacings of the winner's coordinate; spacing is read off
    the ladder's OWN between-band floor strikes (`core.pricing.infer_strike_spacing`, L7 —
    never a hardcoded width). wing = everything else."""
    spacing = infer_strike_spacing(
        [o["floor_strike"] for o in outs
         if o.get("strike_type") == "between" and o.get("floor_strike") is not None])
    winner_coord: Optional[float] = None
    for o in outs:
        if o["ticker"] == winner_ticker:
            winner_coord = member_coord(o)
            break
    out: Dict[str, str] = {}
    for o in outs:
        tk = o["ticker"]
        if tk == winner_ticker:
            out[tk] = "winner"
            continue
        coord = member_coord(o)
        if (spacing and spacing > 0 and winner_coord is not None and coord is not None
                and abs(coord - winner_coord) <= nearmoney_steps * spacing):
            out[tk] = "near_money"
        else:
            out[tk] = "wing"
    return out


def full_ladder_fill_rates(
    sample_events: List[Tuple[str, Dict[str, Any], Dict[str, Any]]],
    fill_fn: FillFn,
    nearmoney_steps: int = NEARMONEY_STEPS,
) -> Dict[str, Any]:
    """Over a small sample of event-hours, fetch EVERY member and report fill rate by bin —
    the direct adverse-selection measurement ('winner fills eagerly, wings never do') plus
    the complete-fill rate (every member filled)."""
    counts = {"winner": [0, 0], "near_money": [0, 0], "wing": [0, 0]}  # [filled, total]
    n_complete = 0
    n_sample = 0
    for event_ticker, entry, settlement in sample_events:
        cur = entry["current"]
        series = entry.get("series") or cur.get("series")
        outs = cur["outcomes"]
        close_time = cur.get("close_time")
        try:
            start_ts = int(_parse_iso(entry["captured_at"]).timestamp())
            end_ts = int(_parse_iso(close_time).timestamp())
        except (ValueError, KeyError, TypeError):
            continue
        if end_ts <= start_ts:
            continue
        n_sample += 1
        bins = classify_members(outs, settlement["winner_ticker"], nearmoney_steps)
        all_filled = True
        for o in outs:
            ask = float(o["yes_ask"])
            filled = fill_fn(series, o["ticker"], ask, start_ts, end_ts)
            b = bins[o["ticker"]]
            counts[b][1] += 1
            if filled:
                counts[b][0] += 1
            else:
                all_filled = False
        if all_filled:
            n_complete += 1
    rates = {b: (c[0] / c[1] if c[1] else float("nan")) for b, c in counts.items()}
    return {
        "n_sample_events": n_sample,
        "fill_counts": counts,
        "fill_rates": rates,
        "complete_fill_rate": (n_complete / n_sample) if n_sample else float("nan"),
        "n_complete": n_complete,
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S14 ladder overround underwriting fill-sim "
                                             "(read-only, paper)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--cache-dir", default=str(CACHE_DIR))
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--min-priced-ask", type=float, default=MIN_PRICED_ASK)
    ap.add_argument("--nearmoney-steps", type=int, default=NEARMONEY_STEPS)
    ap.add_argument("--max-events", type=int, default=None,
                    help="cap simulated event-hours (default: all settled)")
    ap.add_argument("--full-ladder-sample", type=int, default=12,
                    help="event-hours to fetch the FULL ladder for (adverse-selection cut)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    tape_dir = Path(args.tape_dir)
    cache_dir = Path(args.cache_dir)
    records = load_records(tape_dir)
    settle = build_settlement_map(records)
    earliest = build_earliest_captures(records)

    sim_events = sorted(et for et in earliest if et in settle)
    if args.max_events is not None:
        sim_events = sim_events[: args.max_events]

    cache = load_candle_summary_cache(cache_dir)

    def fill_fn(series: str, ticker: str, ask: float, start_ts: int, end_ts: int) -> bool:
        summary = get_or_fetch_candle_summary(ticker, series, start_ts, end_ts,
                                              cache=cache, cache_dir=cache_dir)
        return detect_seller_fill(summary, ask)

    rows: List[Dict[str, Any]] = []
    for et in sim_events:
        row = simulate_event(et, earliest[et], settle[et], fill_fn,
                             min_priced_ask=args.min_priced_ask)
        if row is not None:
            rows.append(row)

    # full-ladder adverse-selection sample (first N by sorted event ticker, deterministic)
    sample_keys = sim_events[: args.full_ladder_sample]
    sample = [(et, earliest[et], settle[et]) for et in sample_keys]
    ladder = full_ladder_fill_rates(sample, fill_fn, nearmoney_steps=args.nearmoney_steps)

    # bootstrap E[P&L] by event-hour
    blocks = pnl_by_event(rows)
    boot = block_bootstrap(blocks, n_boot=args.n_boot)
    ci = boot["ci95"]
    mean_pnl = boot["mean"]
    lo, hi = ci[0], ci[1]
    n_events = boot["n_units"]

    clears_mag = clears_tick_magnitude(ci, tick=0.01, min_ticks=1.0)
    if lo is None:
        verdict = "INCONCLUSIVE_DATA_ADEQUACY"
    elif lo > 0.0 and clears_mag:
        verdict = "EDGE"
    else:
        verdict = "DEAD"

    # descriptive decomposition per registry: E[overround x P(complete fill)] - E[loss|partial]
    complete_rate = ladder["complete_fill_rate"]
    mean_overround = (sum(r["overround"] for r in rows) / len(rows)) if rows else float("nan")
    partial_rows = [r for r in rows if not (r["n_filled"] == r["n_members"])]
    mean_loss_partial = (sum(r["pnl"] for r in partial_rows) / len(partial_rows)
                         if partial_rows else float("nan"))
    mean_frac_floor = (sum(r["frac_overround_on_1c_floor"] for r in rows) / len(rows)
                       if rows else float("nan"))
    mean_fill_relevant = (sum(r["n_filled"] for r in rows) / sum(r["n_priced_relevant"]
                          for r in rows)) if any(r["n_priced_relevant"] for r in rows) else float("nan")
    winner_fill_rate = (sum(1 for r in rows if r["winner_filled"]) / len(rows)
                        if rows else float("nan"))

    print("=" * 78)
    print("S14 LADDER OVERROUND UNDERWRITING FILL-SIM (read-only, paper) — crypto_hourly")
    print("=" * 78)
    print(f"records loaded: {len(records)}  settled event-hours: {len(settle)}  "
          f"simulated: {n_events}")
    print(f"proxy: cached Kalshi hourly candlesticks; fill = max(price.high) >= posted ask "
          f"AND volume>0 (seller mirror of s13's low<=bid); optimistic (ignores queue pos)")
    print("-" * 78)
    print("STRUCTURAL (L30 fee annihilation):")
    print(f"  mean bracket_sum={sum(r['bracket_sum'] for r in rows)/len(rows):.3f}  "
          f"mean overround={mean_overround:.3f}  mean members={sum(r['n_members'] for r in rows)/len(rows):.1f}")
    print(f"  mean fraction of bracket_sum on 1c-floor asks (nets $0 after flat 1c fee) "
          f"= {mean_frac_floor:.1%}")
    print("-" * 78)
    print("ADVERSE SELECTION (full-ladder sample, n_events="
          f"{ladder['n_sample_events']}):")
    for b in ("winner", "near_money", "wing"):
        f, t = ladder["fill_counts"][b]
        print(f"  {b:>10} fill rate = {ladder['fill_rates'][b]:.1%} ({f}/{t})")
    print(f"  complete-fill rate (every member filled) = {complete_rate:.1%} "
          f"({ladder['n_complete']}/{ladder['n_sample_events']})")
    print(f"  winner-filled rate (main sim, n={n_events}) = {winner_fill_rate:.1%}")
    print(f"  fill rate among P&L-relevant fetched members = {mean_fill_relevant:.1%}")
    print("-" * 78)
    print("GATE DECOMPOSITION (registry text):")
    print(f"  E[overround x P(complete fill)] ~ {mean_overround:.3f} x {complete_rate:.3f} "
          f"= {mean_overround * (complete_rate if complete_rate==complete_rate else 0):.4f}")
    print(f"  E[P&L | partial set] = {mean_loss_partial:+.4f} (n_partial={len(partial_rows)})")
    print("-" * 78)
    print(f"E[P&L per event-hour] = {mean_pnl:+.4f}  95% CI=[{lo:+.4f}, {hi:+.4f}]  "
          f"n_events={n_events}  (block-bootstrap BY EVENT-HOUR, n_boot={args.n_boot})")
    print(f"magnitude gate (L27, lower bound >= 1 tick $0.01): "
          f"{'CLEARS' if clears_mag else 'does NOT clear'}")
    print(f"VERDICT: {verdict}")
    if verdict == "DEAD":
        print("  -> CI does not clear zero net of the flat maker fee; the winner strike fills "
              "and costs $1 while the collectable premium is a few cents. Falsified.")
    print("=" * 78)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scoping": "crypto_hourly BTC/ETH hourly MECE strike ladder (NOT sports_pairs)",
        "n_records": len(records), "n_settled": len(settle), "n_events": n_events,
        "fill_proxy": "kalshi_hourly_candlestick_max_high_ge_ask_and_volume_gt_0",
        "mean_bracket_sum": (sum(r["bracket_sum"] for r in rows) / len(rows)) if rows else None,
        "mean_overround": mean_overround,
        "mean_frac_overround_on_1c_floor": mean_frac_floor,
        "adverse_selection_full_ladder": ladder,
        "winner_fill_rate": winner_fill_rate,
        "fill_rate_priced_relevant": mean_fill_relevant,
        "gate_decomposition": {
            "mean_overround": mean_overround, "complete_fill_rate": complete_rate,
            "mean_pnl_partial": mean_loss_partial, "n_partial": len(partial_rows),
        },
        "epnl_per_event": {"mean": mean_pnl, "ci95_lo": lo, "ci95_hi": hi,
                           "n_events": n_events, "n_boot": args.n_boot,
                           "clears_tick_magnitude": clears_mag},
        "verdict": verdict,
        "price_source_tag": "real_ask+broker_truth",  # premiums real_ask, settlement broker_truth
        "rows": rows,
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2))
        print(f"[s14_ladder_fillsim] wrote {args.json_out}")
    # keep TAKER_FEE_RATE referenced so the maker/taker contrast is importable in tests
    _ = TAKER_FEE_RATE
    return 0


if __name__ == "__main__":
    sys.exit(main())

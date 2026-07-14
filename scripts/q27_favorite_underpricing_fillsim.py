"""Q27 / S23 — favorite-side settlement-underpricing MAKER fill-sim (favorite-longshot bias).

Falsifiable milestone (LOOP-QUEUE.md Q27; kb/strategies/00-index.md S23): the favorite-
longshot bias (kb/quant-finance/favorite-longshot-bias.md) leaves FAVORITES underbet — retail
longshot-lovers overbet the underdog and leave the favorite cheap. This probe rests a MAKER
BID to BUY the favorite YES (the two-sided-book outcome whose normalized price, the ask over
bracket_sum, is ≥ ~0.65, Hard Rule #3 — never a raw ask as a probability) in Q25's high-turnover
two-sided sports cells, and collects $1 on settlement if the favorite wins.

THE FAIR TEST IS REALIZED SETTLEMENT (Kalshi's own settled result, broker_truth) — NOT a
devig anchor. That design choice sidesteps S21's L43/L9 join-emptiness death: no `sports_clv`
tape, no odds-api key. The join's second leg (settlement) is retrieved ex-post from Kalshi's
free settled endpoint over the depth tape's OWN window, within the ~60-day L11 retention (L50).

Net per FILLED contract (maker BUY favorite YES, held to settlement):
  - favorite WINS  (settles YES) -> +$1 payout: net  1 − fill_price − $0.01 maker fee.
  - favorite LOSES (settles NO)  ->  $0 payout: net  0 − fill_price − $0.01 maker fee  (≈−$0.65+,
    the CATASTROPHIC leg). Fully in the P&L, NEVER conditioned away or dropped (G2 / L41 / Q24
    gate-2). The fill model is outcome-blind, so favorite-loses fills are included by construction.

Queue-aware fill-sim (L39 — NOT a candlestick print). We rest at the favorite's `best_yes_bid`
at ENTRY (the market's earliest pre-close snapshot). queue_ahead = the `yes_bids` size resting
at price ≥ our bid at entry (price-time priority — every bid at/above our price fills first).
Fills are then measured from the tape's OWN observed queue departures across later snapshots
(the L48 turnover proxy: reductions at price levels ≥ our bid). This is deliberately GENEROUS
(cancels ahead count as advancing us; new bids jumping ahead are ignored) — so a fill rate that
is STILL below the S19 0.45% floor is a robust dead-thin OUT, never a fill guarantee (L48: a
turnover proxy rules a cell OUT, never IN). fill_price is `real_bid`; settlement `broker_truth`.

GATES (verifier-mandated, do NOT weaken):
  G1  same factor slot as S14/S21 (short-the-overpriced-tail / favorite-longshot — one
      Hard-Rule-#6 ρ allocation, NOT diversification). Stated in the finding.
  G2  the favorite-LOSES leg is fully in the P&L (never filtered to favorite-wins).
  G3  KILL if fill rate ≤ the S19 0.45% floor.
  G4  settlement-join ≥10 distinct joinable GAMES before ANY CI, else DEAD-by-adequacy (not a
      CI falsification). Bootstrap by GAME (L6) through bootstrap_verdict_admissible (≥10 units
      AND ≥1 opposing-sign cluster, L41) AND clears_tick_magnitude (tick 0.01, L27) — a CI
      failing EITHER gate is NOT a positive verdict.

KILL CONDITIONS (any ⇒ DEAD): favorite win-rate ≤ mean fill_price + $0.01 fee (bias too small /
L30 fee-death) · fill rate ≤ S19 0.45% floor · settlement-join < 10 games (DEAD-by-adequacy) ·
bootstrap CI fails admissibility or the tick-magnitude gate.

READ-ONLY over `tape/orderbook_depth/` (a probe never mutates tape). Sizes are FLOATS and can be
fractional (L47) — never int-coerce. An empty ladder on a wing is VALID data (L23). Fees ONLY
from core.pricing.fee_per_contract at MAKER_FEE_RATE (flat $0.01 interior, L18/L30).

Run (live settlement pull, then full analysis):
    python scripts/q27_favorite_underpricing_fillsim.py --refresh-cache
Run (offline, against the committed cache — verifier mode):
    python scripts/q27_favorite_underpricing_fillsim.py
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,  # noqa: E402
                            clears_tick_magnitude)
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (MAKER_FEE_RATE, bracket_sum, fee_per_contract,  # noqa: E402
                          normalized_ask)

# The two-sided, low-frozen, high-turnover sports cells Q25 flagged — NOT one-sided crypto
# wings. Same set Q26 used; present in the 2026-07-07..07-14 depth window.
TARGET_SERIES = ("KXKBOGAME", "KXNPBGAME", "KXWNBAGAME", "KXMLBGAME",
                 "KXUCLGAME", "KXUECLGAME", "KXUELGAME")

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
CACHE_PATH = REPO_ROOT / "tape" / "q27_settlement_cache" / "settlement.json"

FAVORITE_MIN_FAIR = 0.65    # favorite = normalized ask over bracket_sum ≥ this (Hard Rule #3)
S19_FILL_FLOOR = 0.0045     # the S19-class queue-aware fill-rate kill floor (G3)
MIN_CI_UNITS = 10           # fewer joined/filled GAMES than this = data-adequacy, not a CI (G4)
PRICE_TICK = 0.01           # Kalshi price tick (L27 magnitude gate)
_EPS = 1e-9


# --------------------------------------------------------------------------- #
# Pure ticker / time helpers (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def series_of(market_ticker: str) -> str:
    """Series prefix, e.g. 'KXKBOGAME-26JUL09ABCDEF-ABC' -> 'KXKBOGAME'."""
    return market_ticker.split("-", 1)[0]


def event_ticker_of(market_ticker: str) -> str:
    """The GAME key (bootstrap unit, L6): strip the trailing outcome-code segment,
    e.g. 'KXKBOGAME-26JUL09ABCDEF-ABC' -> 'KXKBOGAME-26JUL09ABCDEF'. A ticker with no
    trailing '-<code>' returns itself unchanged."""
    return market_ticker.rsplit("-", 1)[0]


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (with 'Z' or explicit offset) to a tz-aware UTC datetime.
    None on a missing/blank/unparseable input rather than raising."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# --------------------------------------------------------------------------- #
# Pure ladder / favorite / queue helpers (sizes are FLOATS, L47; empty is VALID, L23)
# --------------------------------------------------------------------------- #
def bid_size_at_or_above(yes_bids: Optional[Sequence[Sequence[float]]], price: float,
                         tick: float = PRICE_TICK) -> float:
    """Sum of `yes_bids` resting sizes at price ≥ `price` (price priority — everyone at or
    above our bid fills before us). Sizes are FLOATS (L47), summed as floats, never int-
    coerced. An empty/None ladder sums to 0.0 (valid one-sided book, L23)."""
    if not yes_bids:
        return 0.0
    total = 0.0
    for level in yes_bids:
        if level is None or len(level) < 2 or level[0] is None or level[1] is None:
            continue
        if float(level[0]) >= price - tick / 2.0:
            total += float(level[1])
    return total


def bid_price_map(yes_bids: Optional[Sequence[Sequence[float]]], price: float,
                  tick: float = PRICE_TICK) -> Dict[float, float]:
    """price -> size map of the `yes_bids` levels at price ≥ `price` (the levels ahead of
    or at our resting bid). Floats throughout (L47). Empty ladder -> empty map (L23)."""
    out: Dict[float, float] = {}
    if not yes_bids:
        return out
    for level in yes_bids:
        if level is None or len(level) < 2 or level[0] is None or level[1] is None:
            continue
        p = float(level[0])
        if p >= price - tick / 2.0:
            out[p] = out.get(p, 0.0) + float(level[1])
    return out


def departures_between(prev_bids: Optional[Sequence[Sequence[float]]],
                       now_bids: Optional[Sequence[Sequence[float]]], price: float,
                       tick: float = PRICE_TICK) -> float:
    """Observed queue DEPARTURES at price levels ≥ our bid between two consecutive snapshots
    (the L48 turnover measure): for each price level ≥ `price` present in `prev`, the size
    reduction `max(0, size_prev − size_now)` (fills + cancels ahead of us). New levels
    appearing (size increase, or a level absent in prev) are IGNORED — that makes the fill
    model GENEROUS (a new bid jumping ahead of us is not charged), so a below-floor fill rate
    under this rule is a robust dead-thin OUT (L48: a turnover proxy rules OUT, never IN)."""
    pm = bid_price_map(prev_bids, price, tick)
    nm = bid_price_map(now_bids, price, tick)
    dep = 0.0
    for p, size_prev in pm.items():
        size_now = nm.get(p, 0.0)
        if size_prev > size_now:
            dep += size_prev - size_now
    return dep


def favorite_normalized_fair(self_yes_ask: Optional[float],
                             sibling_yes_asks: Sequence[Optional[float]]
                             ) -> Optional[float]:
    """Normalized implied P(this outcome wins) = ask over bracket_sum (Hard Rule #3 —
    NEVER the raw ask alone). `sibling_yes_asks` is every market's best_yes_ask in the event
    INCLUDING this one. None if this market's ask is missing or the bracket doesn't sum > 0
    (can't normalize). Uses core.pricing.bracket_sum / normalized_ask (the sanctioned site)."""
    if self_yes_ask is None:
        return None
    asks = [a for a in sibling_yes_asks if a is not None]
    if not asks:
        return None
    bsum = bracket_sum(asks)
    if bsum <= 0:
        return None
    return normalized_ask(float(self_yes_ask), bsum)


def maker_fee(fill_price: float) -> float:
    """The flat maker fee on a fill (L18/L30): fee_per_contract at MAKER_FEE_RATE on the
    fill price — a flat $0.01 at every interior price. Sanctioned helper, never hand-rolled."""
    return fee_per_contract(float(fill_price), rate=MAKER_FEE_RATE)


def favorite_pnl(fill_price: float, favorite_settles_yes: bool) -> float:
    """P&L of one FILLED maker BUY of the favorite YES, held to settlement, net of fee:
      favorite WINS  (settles YES) -> +1 payout: 1 − fill_price − fee.
      favorite LOSES (settles NO)  ->  0 payout: 0 − fill_price − fee  (catastrophic leg, G2).
    The favorite-loses leg is modeled here explicitly — never conditioned away (L41)."""
    fee = maker_fee(fill_price)
    payoff = 1.0 if favorite_settles_yes else 0.0
    return payoff - float(fill_price) - fee


def simulate_fill(snapshots: Sequence[dict], bid_price: float, queue_ahead: float) -> bool:
    """Queue-aware fill decision (L39, NOT a candle print) over a favorite market's ordered
    pre-close snapshots (entry first). We rest at `bid_price`; `queue_ahead` contracts sit
    ahead of us at entry. Accumulate observed departures at price ≥ bid_price across each
    consecutive snapshot pair (`departures_between`); FILLED once cumulative departures have
    cleared the queue ahead of us AND at least one departure was observed (a frozen queue
    that never moves is a NO-FILL, L32/L48). queue_ahead ≤ 0 (front-of-queue) fills on the
    first observed departure."""
    cumulative = 0.0
    for prev, now in zip(snapshots, snapshots[1:]):
        cumulative += departures_between(prev["record"].get("yes_bids"),
                                         now["record"].get("yes_bids"), bid_price)
    if cumulative <= 0.0:
        return False
    return cumulative >= queue_ahead - _EPS


# --------------------------------------------------------------------------- #
# Settlement cache (live pull, cached to disk; verifier re-runs offline)
# --------------------------------------------------------------------------- #
def depth_event_tickers(depth_glob: str) -> Dict[str, set]:
    """Scan the depth tape once and collect, per target series, the set of event_tickers
    actually present — so the live settlement pull fetches /markets ONLY for joinable games,
    not every settled event in retention. Read-only."""
    by_series: Dict[str, set] = {s: set() for s in TARGET_SERIES}
    for fp in sorted(glob.glob(depth_glob)):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                mt = json.loads(line).get("ticker", "")
                s = series_of(mt)
                if s in by_series:
                    by_series[s].add(event_ticker_of(mt))
    return by_series


def build_settlement_cache(series_list: Sequence[str], cache_path: Path,
                           limit: int = 500, min_interval: float = 0.25,
                           depth_glob: str = DEPTH_GLOB) -> Dict[str, dict]:
    """Pull settled events for each target series, then each depth-window event's markets, and
    cache a flat map market_ticker -> {result, close_time, event_ticker, series}. Only fetches
    /markets for event_tickers present in the depth tape (the joinable universe). Live network;
    self-wraps a ConnectionError retry (L40). Writes JSON so a verifier can re-run OFFLINE.
    NOTE L52: results can be 'scalar', not just yes/no — cached verbatim and filtered downstream."""
    import time

    import requests

    from collection.sports_history import fetch_settled_events
    from validation.v3_market import Kalshi, _load_venue_cfg

    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"], min_interval=min_interval)

    def _get_text_retry(path: str, **params) -> str:
        for attempt in range(4):
            try:
                return client.get_text(path, **params)
            except (requests.ConnectionError, ConnectionError):  # L40
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("unreachable")

    def _fetch_events_retry(series: str) -> list:
        for attempt in range(4):
            try:
                events, _raw = fetch_settled_events(client, series, limit=limit)
                return events
            except (requests.ConnectionError, ConnectionError):  # L40
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        return []

    wanted = depth_event_tickers(depth_glob)

    out: Dict[str, dict] = {}
    per_series: Dict[str, int] = {}
    for series in series_list:
        events = _fetch_events_retry(series)
        want = wanted.get(series, set())
        n_markets = 0
        n_events_hit = 0
        for e in events:
            event_ticker = e.get("event_ticker", "")
            if not event_ticker or event_ticker not in want:
                continue
            n_events_hit += 1
            text = _get_text_retry("/markets", event_ticker=event_ticker)
            markets = json.loads(text).get("markets") or []
            for m in markets:
                mt = m.get("ticker")
                if not mt:
                    continue
                out[mt] = {
                    "result": m.get("result"),
                    "close_time": m.get("close_time"),
                    "event_ticker": m.get("event_ticker") or event_ticker,
                    "series": series,
                }
                n_markets += 1
        per_series[series] = n_markets
        print(f"[q27:cache] {series}: {len(events)} settled events, "
              f"{n_events_hit}/{len(want)} depth-window events joined, {n_markets} markets")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "q27_settlement_cache.v1",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "series": list(series_list),
        "per_series_market_count": per_series,
        "markets": out,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"[q27:cache] wrote {len(out)} settled markets -> {cache_path}")
    return out


def load_settlement_cache(cache_path: Path) -> Dict[str, dict]:
    """Load the cached market_ticker -> settlement map (offline; verifier mode)."""
    if not cache_path.exists():
        return {}
    with open(cache_path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("markets") or {}


# --------------------------------------------------------------------------- #
# Depth tape loading (read-only) — ALL pre-close snapshots per market
# --------------------------------------------------------------------------- #
def load_preclose_snapshots(depth_glob: str, settlement: Dict[str, dict]
                            ) -> Tuple[Dict[str, List[dict]], dict]:
    """Scan the depth tape once. For every target-series market with a BINARY settlement
    (result ∈ {yes,no}, L52 — scalar dropped) and a close_time, collect ALL its snapshots with
    captured_at < close_time (genuine pre-close, ttc>0), each sorted ascending by captured_at.
    Returns (per_market_snapshot_list, funnel_counts).

    snapshot dict = {record, captured_at, close_time, ttc_seconds, event_ticker, series, result}
    """
    funnel = {
        "markets_in_depth": set(),
        "markets_settled_binary": set(),   # + a binary yes/no settlement (scalar dropped, L52)
        "markets_settled_scalar": set(),   # settled but result == scalar (L52 — dropped)
        "markets_with_preclose": set(),
    }
    per_market: Dict[str, List[dict]] = {}
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
                if not s:
                    continue
                result = s.get("result")
                if result == "scalar":
                    funnel["markets_settled_scalar"].add(mt)
                    continue
                if result not in ("yes", "no"):
                    continue
                funnel["markets_settled_binary"].add(mt)
                close_dt = parse_iso(s.get("close_time"))
                cap_dt = parse_iso(rec.get("captured_at"))
                if close_dt is None or cap_dt is None or cap_dt >= close_dt:
                    continue
                per_market.setdefault(mt, []).append({
                    "record": rec,
                    "captured_at": cap_dt,
                    "close_time": close_dt,
                    "ttc_seconds": (close_dt - cap_dt).total_seconds(),
                    "event_ticker": s.get("event_ticker") or event_ticker_of(mt),
                    "series": s.get("series") or series_of(mt),
                    "result": result,
                })
    for mt in per_market:
        per_market[mt].sort(key=lambda d: d["captured_at"])
    funnel["markets_with_preclose"] = set(per_market.keys())
    return per_market, funnel


# --------------------------------------------------------------------------- #
# Favorite identification + fill-sim over the event structure
# --------------------------------------------------------------------------- #
def _nearest_snapshot(snaps: Sequence[dict], t: datetime) -> Optional[dict]:
    """The snapshot whose captured_at is nearest to `t` (used to read a sibling market's ask
    at ~our entry time, so the bracket_sum is formed at ENTRY, no look-ahead)."""
    best = None
    for s in snaps:
        if best is None or abs((s["captured_at"] - t).total_seconds()) < \
                abs((best["captured_at"] - t).total_seconds()):
            best = s
    return best


def build_favorite_trades(per_market: Dict[str, List[dict]]) -> Tuple[List[dict], dict]:
    """One resting-maker trade per market that qualifies as its game's FAVORITE at ENTRY.

    Entry per market = its earliest pre-close snapshot. At that entry time, form the game's
    bracket_sum from every sibling market's best_yes_ask nearest to entry (Hard Rule #3), and
    classify this market a favorite iff its normalized fair ≥ FAVORITE_MIN_FAIR. Rest a maker
    BID at the favorite's entry best_yes_bid; queue_ahead = yes_bids size at price ≥ that bid.
    Markets with no entry best_yes_bid / empty yes_bids can't rest a bid (no two-sided quote on
    our side) and are counted, not traded.

    Returns (trade_rows, funnel). Each trade row carries the mandated fields with source tags."""
    # group markets by event
    by_event: Dict[str, List[str]] = {}
    for mt in per_market:
        by_event.setdefault(event_ticker_of(mt), []).append(mt)

    trades: List[dict] = []
    funnel = {
        "n_markets": len(per_market),
        "n_events": len(by_event),
        "n_favorite_markets": 0,
        "n_favorite_no_restable_bid": 0,
        "n_rested": 0,
    }
    for et, markets in by_event.items():
        for mt in markets:
            snaps = per_market[mt]
            entry = snaps[0]
            entry_rec = entry["record"]
            self_ask = entry_rec.get("best_yes_ask")
            sibling_asks: List[Optional[float]] = []
            for sib in markets:
                sib_near = _nearest_snapshot(per_market[sib], entry["captured_at"])
                sibling_asks.append(sib_near["record"].get("best_yes_ask") if sib_near else None)
            fair = favorite_normalized_fair(self_ask, sibling_asks)
            if fair is None or fair < FAVORITE_MIN_FAIR:
                continue
            funnel["n_favorite_markets"] += 1

            bid = entry_rec.get("best_yes_bid")
            if bid is None or not entry_rec.get("yes_bids"):
                funnel["n_favorite_no_restable_bid"] += 1
                continue
            bid = float(bid)
            queue_ahead = bid_size_at_or_above(entry_rec.get("yes_bids"), bid)
            filled = simulate_fill(snaps, bid, queue_ahead)
            settles_yes = (entry["result"] == "yes")
            asks_present = [a for a in sibling_asks if a is not None]
            bsum = bracket_sum(asks_present) if asks_present else None
            trades.append({
                "market_ticker": mt,
                "event_ticker": et,
                "series": entry["series"],
                "ttc_seconds_entry": entry["ttc_seconds"],
                "n_snapshots": len(snaps),
                "raw_favorite_yes_ask": self_ask,
                "bracket_sum": bsum,
                "normalized_fair": fair,
                "fill_price": bid,
                "queue_ahead": queue_ahead,
                "filled": filled,
                "favorite_settles_yes": settles_yes,
                "pnl": (favorite_pnl(bid, settles_yes) if filled else None),
                "price_source_tag": "real_bid(fill)+real_ask(fair)+broker_truth(settle)",
            })
            funnel["n_rested"] += 1
    return trades, funnel


def per_game_pnl(trades: Sequence[dict]) -> Dict[str, List[float]]:
    """Group FILLED-trade net P&L by GAME (event_ticker, L6 bootstrap unit). The favorite-
    loses leg is included by construction (fill model is outcome-blind, G2)."""
    out: Dict[str, List[float]] = {}
    for t in trades:
        if t["filled"] and t["pnl"] is not None:
            out.setdefault(t["event_ticker"], []).append(t["pnl"])
    return out


# --------------------------------------------------------------------------- #
# Analysis / verdict
# --------------------------------------------------------------------------- #
def _pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else float("nan")


def run(cache_path: Path = CACHE_PATH, depth_glob: str = DEPTH_GLOB,
        n_boot: int = 10000) -> dict:
    """Full offline analysis against the cached settlement + committed depth tape."""
    settlement = load_settlement_cache(cache_path)
    per_market, funnel_sets = load_preclose_snapshots(depth_glob, settlement)

    games_preclose = len({event_ticker_of(mt) for mt in per_market})
    report = {
        "n_settled_markets_cached": len(settlement),
        "funnel": {
            "markets_in_depth": len(funnel_sets["markets_in_depth"]),
            "markets_settled_binary": len(funnel_sets["markets_settled_binary"]),
            "markets_settled_scalar_dropped_L52": len(funnel_sets["markets_settled_scalar"]),
            "markets_with_preclose_snapshot": len(funnel_sets["markets_with_preclose"]),
            "distinct_games_with_preclose": games_preclose,
        },
    }

    trades, trade_funnel = build_favorite_trades(per_market)
    report["favorite_funnel"] = trade_funnel

    # distinct joinable GAMES = games that have ≥1 rested favorite trade (depth-favorite AND
    # binary settlement). G4 adequacy is measured on THIS number.
    rested = [t for t in trades if True]  # every trade row IS a rested favorite bid
    joinable_games = {t["event_ticker"] for t in rested}
    report["distinct_joinable_games"] = len(joinable_games)

    # G4 adequacy gate — BEFORE any CI (like S21: <10 games ⇒ DEAD-by-adequacy, not a CI kill).
    if len(joinable_games) < MIN_CI_UNITS:
        report["verdict"] = "DEAD-by-adequacy"
        report["verdict_reason"] = (
            f"only {len(joinable_games)} distinct games carry a depth-favorite resting bid "
            f"with a binary settlement (<{MIN_CI_UNITS}); untestable as collected (S21-class "
            "data-adequacy death, NOT a CI falsification)")
        return report

    # G3 — queue-aware fill rate vs the S19 floor.
    n_rested = len(rested)
    fills = [t for t in trades if t["filled"]]
    n_fill = len(fills)
    fill_rate = n_fill / n_rested if n_rested else 0.0
    fill_prices = [t["fill_price"] for t in fills]
    mean_fill_price = (sum(fill_prices) / len(fill_prices)) if fill_prices else None
    n_fav_win_fills = sum(1 for t in fills if t["favorite_settles_yes"])
    win_rate_fills = (n_fav_win_fills / n_fill) if n_fill else None
    # adverse-selection reference: favorite win-rate among ALL rested (unconditional).
    n_fav_win_rested = sum(1 for t in rested if t["favorite_settles_yes"])
    win_rate_rested = (n_fav_win_rested / n_rested) if n_rested else None

    report["fill"] = {
        "n_rested_favorite_bids": n_rested,
        "n_fill": n_fill,
        "fill_rate": fill_rate,
        "s19_floor": S19_FILL_FLOOR,
        "mean_fill_price_real_bid": mean_fill_price,
        "win_rate_among_fills": win_rate_fills,
        "win_rate_among_all_rested": win_rate_rested,
        "fills_favorite_win": n_fav_win_fills,
        "fills_favorite_lose": n_fill - n_fav_win_fills,
    }

    if fill_rate <= S19_FILL_FLOOR + _EPS:
        report["verdict"] = "DEAD-by-fill-rate"
        report["verdict_reason"] = (
            f"queue-aware fill rate {fill_rate:.4%} ≤ S19 floor {S19_FILL_FLOOR:.4%} "
            f"({n_fill}/{n_rested} rested favorite bids filled) — dead-thin (G3/L48)")
        return report

    # KILL: favorite win-rate ≤ mean fill_price + fee (bias too small to clear the price+fee).
    if mean_fill_price is not None and win_rate_fills is not None:
        breakeven = mean_fill_price + maker_fee(mean_fill_price)
        report["fill"]["breakeven_winrate"] = breakeven
        if win_rate_fills <= breakeven + _EPS:
            report["verdict"] = "DEAD-by-fee"
            report["verdict_reason"] = (
                f"favorite win-rate among fills {win_rate_fills:.4f} ≤ mean fill_price+fee "
                f"{breakeven:.4f} — the bias doesn't clear the price paid + $0.01 maker fee "
                "(L30 fee-death / S13-family)")
            # still compute the CI below for completeness, but the verdict stands.

    # G4 — block-bootstrap net P&L BY GAME (L6), through BOTH gates.
    unit_values = per_game_pnl(trades)
    boot = block_bootstrap(unit_values, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(unit_values, min_units=MIN_CI_UNITS)
    mag = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK, min_ticks=1.0)
    ci_lo = boot["ci95"][0]
    ci_positive = ci_lo is not None and ci_lo > 0.0
    report["bootstrap"] = {
        "mean": boot["mean"], "ci95": boot["ci95"],
        "n_units_games": boot["n_units"], "n_obs_fills": boot["n_obs"],
        "admissible": adm, "clears_tick_magnitude": mag,
        "ci_lower_positive": ci_positive,
    }

    if report.get("verdict") == "DEAD-by-fee":
        return report

    if boot["n_units"] < MIN_CI_UNITS:
        report["verdict"] = "DEAD-by-adequacy"
        report["verdict_reason"] = (
            f"only {boot['n_units']} games carry a FILLED favorite trade (<{MIN_CI_UNITS}) — "
            "data-adequacy dead even if the point estimate looks positive")
    elif not adm["admissible"]:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = f"bootstrap inadmissible (L41): {adm['reasons']}"
    elif not ci_positive:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = f"95% CI lower bound not > 0: ci95={boot['ci95']}"
    elif not mag:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = (
            f"CI>0 but fails the 1-tick economic-significance gate (L27): ci95={boot['ci95']}")
    else:
        report["verdict"] = "ALIVE-PROVISIONAL"
        report["verdict_reason"] = (
            "all gates pass — genuinely uncertain; needs verifier confirmation + shadow-paper "
            "before any capital (do NOT trade, do NOT flip the registry)")
    return report


def _print_report(rep: dict) -> None:
    print(json.dumps(rep, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q27/S23 favorite-underpricing maker fill-sim (read-only)")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="pull settlement live from Kalshi and rewrite the cache first")
    ap.add_argument("--cache", default=str(CACHE_PATH))
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--min-interval", type=float, default=0.25)
    ap.add_argument("--n-boot", type=int, default=10000)
    args = ap.parse_args(argv)

    cache_path = Path(args.cache)
    if args.refresh_cache:
        build_settlement_cache(TARGET_SERIES, cache_path, limit=args.limit,
                               min_interval=args.min_interval)
    rep = run(cache_path=cache_path, n_boot=args.n_boot)
    _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())

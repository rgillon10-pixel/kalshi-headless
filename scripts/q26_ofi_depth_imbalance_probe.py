"""Q26 / S22 — OFI / depth-imbalance settlement predictor on high-churn two-sided sports books.

Falsifiable milestone (LOOP-QUEUE.md Q26; kb/strategies/00-index.md S22): resting L2
book-imbalance (size on the `yes_bids` ladder vs the `no_bids` ladder) is claimed to carry
information that LEADS the mid and predicts the settlement outcome. At each game's last
pre-close (ttc>0) depth snapshot we form the imbalance signal; where it DISAGREES with the
mid we take the imbalance-favored side at the real taker ask (`best_yes_ask`/`best_no_ask`);
realized P&L = settlement − ask − taker fee; block-bootstrap by GAME (`event_ticker`, L6 —
a game's two team-outcome markets are the SAME bet mirrored, never independent).

READ-ONLY over `tape/orderbook_depth/` (a probe never mutates tape). Settlement (result +
close_time + event_ticker) is pulled ONCE from Kalshi's free settled-markets endpoint and
CACHED under `tape/q26_settlement_cache/` so the run is re-runnable and a verifier can
re-run OFFLINE against the cache (the depth window's cohort purges ~09-12 per L11, so the
cache is a fixed snapshot). Settlement is `broker_truth`; the imbalance signal and the mid
are derived from `real_ask`/`real_bid` book fields.

Build order (the two early gates are HARD STOPS that decide most outcomes cheaply):
  GATE 1  settlement-join adequacy  — ≥10 distinct joinable GAMES or DEAD-by-join.
  GATE 2  calibration precheck      — imbalance must beat the mid ON THE DISAGREEMENT
                                      SUBSET or DEAD-by-calibration (the mid IS the market
                                      price and is already a strong predictor).
  GATE 3  taker-lift P&L            — hold-to-settlement single taker lift on the
                                      disagreement subset (one taker fee, settlement free).
  GATE 4  block-bootstrap CI        — bootstrap_verdict_admissible (L41) AND block_bootstrap
                                      AND clears_tick_magnitude (L27), all by GAME.

Verdict is one of: DEAD-by-join / DEAD-by-calibration / DEAD-by-cadence (S9-family) /
DEAD-by-CI / ALIVE-PROVISIONAL. A DEAD verdict recorded cleanly is a full success.

Sizes are FLOATS and can be fractional (L47) — never int-coerce. A one-sided/empty ladder
is VALID data (L23); only BOTH sides empty means no signal (drop that market).

Run (live settlement pull, then full analysis):
    python scripts/q26_ofi_depth_imbalance_probe.py --refresh-cache
Run (offline, against the committed cache — verifier mode):
    python scripts/q26_ofi_depth_imbalance_probe.py
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,
                            clears_tick_magnitude)
from core.io import REPO_ROOT
from core.pricing import TAKER_FEE_RATE, fee_per_contract

# The two-sided, low-frozen, high-turnover sports cells Q25 flagged — NOT the one-sided
# crypto wings. Confirmed present in the 2026-07-07..07-14 depth window this session.
TARGET_SERIES = ("KXKBOGAME", "KXNPBGAME", "KXWNBAGAME", "KXMLBGAME",
                 "KXUCLGAME", "KXUECLGAME", "KXUELGAME")

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
CACHE_PATH = REPO_ROOT / "tape" / "q26_settlement_cache" / "settlement.json"


# --------------------------------------------------------------------------- #
# Pure signal helpers (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def series_of(market_ticker: str) -> str:
    """Series prefix, e.g. 'KXKBOGAME-26JUL09ABCDEF-ABC' -> 'KXKBOGAME'."""
    return market_ticker.split("-", 1)[0]


def event_ticker_of(market_ticker: str) -> str:
    """The GAME key (bootstrap unit, L6): strip the trailing outcome-code segment,
    e.g. 'KXKBOGAME-26JUL09ABCDEF-ABC' -> 'KXKBOGAME-26JUL09ABCDEF'. A market ticker with
    no trailing '-<code>' returns itself unchanged."""
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


def ladder_size_sum(ladder: Optional[Sequence[Sequence[float]]]) -> float:
    """Sum of resting sizes on one book-side ladder. Sizes are FLOATS (L47) — summed as
    floats, never int-coerced. An empty/None ladder sums to 0.0 (valid one-sided book, L23)."""
    if not ladder:
        return 0.0
    total = 0.0
    for level in ladder:
        # level is [price, size]; guard against a malformed short level.
        if level is None or len(level) < 2 or level[1] is None:
            continue
        total += float(level[1])
    return total


def imbalance_signal(yes_bid_size: float, no_bid_size: float) -> Optional[float]:
    """Depth imbalance in [-1, 1]: (yes_bid_size − no_bid_size)/(yes_bid_size + no_bid_size).
    Positive = net resting demand favors YES. None when BOTH sides are empty (no signal —
    drop that market, per gate-2 spec). A one-sided ladder is valid data (±1.0), not a drop."""
    denom = yes_bid_size + no_bid_size
    if denom <= 0:
        return None
    return (yes_bid_size - no_bid_size) / denom


def mid_yes(best_yes_bid: Optional[float], best_yes_ask: Optional[float]) -> Optional[float]:
    """The YES mid = (best_yes_bid + best_yes_ask)/2. None if either side of the BBO is
    missing (can't form a mid)."""
    if best_yes_bid is None or best_yes_ask is None:
        return None
    return (float(best_yes_bid) + float(best_yes_ask)) / 2.0


def side_of_imbalance(imb: Optional[float]) -> Optional[str]:
    """'yes' if imbalance>0, 'no' if <0, None at exactly 0 (no directional signal)."""
    if imb is None or imb == 0:
        return None
    return "yes" if imb > 0 else "no"


def side_of_mid(m: Optional[float]) -> Optional[str]:
    """'yes' if mid>0.5, 'no' if <0.5, None at exactly 0.5 (no directional lean)."""
    if m is None or m == 0.5:
        return None
    return "yes" if m > 0.5 else "no"


def taker_lift_pnl(favored_side: str, settled_yes: int,
                   best_yes_ask: Optional[float], best_no_ask: Optional[float]
                   ) -> Optional[float]:
    """Hold-to-settlement single taker lift P&L for the imbalance-favored side.
    favored='yes' -> buy YES at best_yes_ask, payoff 1 if settled YES else 0.
    favored='no'  -> buy NO  at best_no_ask,  payoff 1 if settled NO  else 0.
    Net = payoff − ask − taker fee (settlement is free; ONE taker fee, already netted).
    Returns None when the favored side has no fillable ask (missing, or a $1.00 mirror ask
    with no room, L26) — the caller excludes and counts those."""
    ask = best_yes_ask if favored_side == "yes" else best_no_ask
    if ask is None or ask >= 1.0 or ask <= 0.0:
        return None
    fee = fee_per_contract(ask, TAKER_FEE_RATE)
    if favored_side == "yes":
        payoff = 1.0 if settled_yes == 1 else 0.0
    else:
        payoff = 1.0 if settled_yes == 0 else 0.0
    return payoff - float(ask) - fee


# --------------------------------------------------------------------------- #
# Settlement cache (live pull, cached to disk; verifier re-runs offline)
# --------------------------------------------------------------------------- #
def build_settlement_cache(series_list: Sequence[str], cache_path: Path,
                           limit: int = 500, min_interval: float = 0.25) -> Dict[str, dict]:
    """Pull settled events for each target series, then each event's markets, and cache a
    flat map market_ticker -> {result, close_time, event_ticker, series}. Live network;
    self-wraps a ConnectionError retry (L40 — the client retries HTTP status codes but not
    transport drops). Writes JSON so a verifier can re-run everything else OFFLINE."""
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
            except (requests.ConnectionError, ConnectionError) as exc:  # L40
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise RuntimeError("unreachable")

    def _fetch_events_retry(series: str) -> list:
        for attempt in range(4):
            try:
                events, _raw = fetch_settled_events(client, series, limit=limit)
                return events
            except (requests.ConnectionError, ConnectionError) as exc:  # L40
                if attempt == 3:
                    raise
                time.sleep(min(2 ** attempt, 8))
        return []

    out: Dict[str, dict] = {}
    per_series: Dict[str, int] = {}
    for series in series_list:
        events = _fetch_events_retry(series)
        n_markets = 0
        for e in events:
            event_ticker = e.get("event_ticker", "")
            if not event_ticker:
                continue
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
        print(f"[q26:cache] {series}: {len(events)} settled events, {n_markets} markets")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "q26_settlement_cache.v1",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "series": list(series_list),
        "per_series_market_count": per_series,
        "markets": out,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"[q26:cache] wrote {len(out)} settled markets -> {cache_path}")
    return out


def load_settlement_cache(cache_path: Path) -> Dict[str, dict]:
    """Load the cached market_ticker -> settlement map (offline; verifier mode)."""
    if not cache_path.exists():
        return {}
    with open(cache_path, encoding="utf-8") as f:
        payload = json.load(f)
    return payload.get("markets") or {}


# --------------------------------------------------------------------------- #
# Depth tape loading (read-only)
# --------------------------------------------------------------------------- #
def load_last_preclose_snapshots(depth_glob: str, settlement: Dict[str, dict]
                                 ) -> Tuple[Dict[str, dict], dict]:
    """Scan the depth tape once. For every target-series market ticker that has a retrieved
    settlement WITH a close_time, keep its LAST snapshot with captured_at < close_time (a
    genuine pre-close snapshot, ttc>0). Returns (per_market_last_snapshot, funnel_counts).

    per_market_last_snapshot[market_ticker] = {
        record, captured_at, close_time, ttc_seconds, event_ticker, series, result }
    """
    funnel = {
        "markets_in_depth": set(),          # distinct target-series market tickers seen
        "markets_settled_joined": set(),    # + a settlement row exists (result present)
        "markets_with_preclose": set(),     # + a valid ttc>0 last snapshot
    }
    best: Dict[str, dict] = {}
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
                if not s or s.get("result") not in ("yes", "no"):
                    continue
                funnel["markets_settled_joined"].add(mt)
                close_dt = parse_iso(s.get("close_time"))
                cap_dt = parse_iso(rec.get("captured_at"))
                if close_dt is None or cap_dt is None:
                    continue
                if cap_dt >= close_dt:
                    continue  # not a pre-close snapshot (ttc <= 0)
                ttc = (close_dt - cap_dt).total_seconds()
                prev = best.get(mt)
                if prev is None or cap_dt > prev["captured_at"]:
                    best[mt] = {
                        "record": rec,
                        "captured_at": cap_dt,
                        "close_time": close_dt,
                        "ttc_seconds": ttc,
                        "event_ticker": s.get("event_ticker") or event_ticker_of(mt),
                        "series": s.get("series") or series_of(mt),
                        "result": s.get("result"),
                    }
    funnel["markets_with_preclose"] = set(best.keys())
    return best, funnel


# --------------------------------------------------------------------------- #
# Analysis
# --------------------------------------------------------------------------- #
def _pct(n: int, d: int) -> float:
    return 100.0 * n / d if d else float("nan")


def _quantiles(vals: List[float]) -> dict:
    if not vals:
        return {"n": 0}
    s = sorted(vals)
    n = len(s)

    def q(p):
        return s[min(n - 1, int(p * n))]
    return {"n": n, "min": s[0], "p10": q(0.10), "median": q(0.50),
            "p90": q(0.90), "max": s[-1], "mean": sum(s) / n}


def build_market_signals(best: Dict[str, dict]) -> List[dict]:
    """One row per market with a valid last pre-close snapshot AND a non-empty ladder signal.
    Drops markets whose BOTH ladders are empty (no signal). Sizes are floats (L47)."""
    rows: List[dict] = []
    for mt, info in best.items():
        rec = info["record"]
        y = ladder_size_sum(rec.get("yes_bids"))
        n = ladder_size_sum(rec.get("no_bids"))
        imb = imbalance_signal(y, n)
        if imb is None:
            continue  # both sides empty -> no signal
        m = mid_yes(rec.get("best_yes_bid"), rec.get("best_yes_ask"))
        settled_yes = 1 if info["result"] == "yes" else 0
        rows.append({
            "market_ticker": mt,
            "event_ticker": info["event_ticker"],
            "series": info["series"],
            "ttc_seconds": info["ttc_seconds"],
            "yes_bid_size": y,
            "no_bid_size": n,
            "imbalance": imb,
            "imb_side": side_of_imbalance(imb),
            "mid_yes": m,
            "mid_side": side_of_mid(m),
            "settled_yes": settled_yes,
            "best_yes_ask": rec.get("best_yes_ask"),
            "best_no_ask": rec.get("best_no_ask"),
        })
    return rows


def gate2_calibration(rows: List[dict]) -> dict:
    """Does sign(imbalance) beat sign(mid−0.5) at predicting settlement, especially on the
    DISAGREEMENT subset (the actual trade population)? Also Brier scores for color."""
    def hit(side: Optional[str], settled_yes: int) -> Optional[bool]:
        if side is None:
            return None
        return (side == "yes") == (settled_yes == 1)

    imb_hits = [hit(r["imb_side"], r["settled_yes"]) for r in rows]
    mid_hits = [hit(r["mid_side"], r["settled_yes"]) for r in rows]
    imb_valid = [h for h in imb_hits if h is not None]
    mid_valid = [h for h in mid_hits if h is not None]

    # Disagreement subset: both sides directional AND opposite.
    disagree = [r for r in rows
                if r["imb_side"] is not None and r["mid_side"] is not None
                and r["imb_side"] != r["mid_side"]]
    dis_imb_hits = [hit(r["imb_side"], r["settled_yes"]) for r in disagree]
    dis_mid_hits = [hit(r["mid_side"], r["settled_yes"]) for r in disagree]

    # Brier: prob(YES). imbalance-implied = (imb+1)/2; mid-implied = mid_yes clamped to [0,1].
    def brier(rs: List[dict]) -> Tuple[Optional[float], Optional[float], int]:
        ib, mb, n = 0.0, 0.0, 0
        for r in rs:
            if r["mid_yes"] is None:
                continue
            p_imb = (r["imbalance"] + 1.0) / 2.0
            p_mid = min(1.0, max(0.0, r["mid_yes"]))
            y = r["settled_yes"]
            ib += (p_imb - y) ** 2
            mb += (p_mid - y) ** 2
            n += 1
        if n == 0:
            return None, None, 0
        return ib / n, mb / n, n

    all_brier_imb, all_brier_mid, all_brier_n = brier(rows)
    dis_brier_imb, dis_brier_mid, dis_brier_n = brier(disagree)

    disagree_games = len({r["event_ticker"] for r in disagree})

    return {
        "n_rows": len(rows),
        "imb_hit_rate": (sum(imb_valid) / len(imb_valid)) if imb_valid else None,
        "imb_hit_n": len(imb_valid),
        "mid_hit_rate": (sum(mid_valid) / len(mid_valid)) if mid_valid else None,
        "mid_hit_n": len(mid_valid),
        "disagree_n": len(disagree),
        "disagree_games": disagree_games,
        "disagree_imb_hit_rate": (sum(dis_imb_hits) / len(dis_imb_hits)) if dis_imb_hits else None,
        "disagree_mid_hit_rate": (sum(dis_mid_hits) / len(dis_mid_hits)) if dis_mid_hits else None,
        "brier_all_imb": all_brier_imb, "brier_all_mid": all_brier_mid, "brier_all_n": all_brier_n,
        "brier_dis_imb": dis_brier_imb, "brier_dis_mid": dis_brier_mid, "brier_dis_n": dis_brier_n,
        "_disagree_rows": disagree,
    }


def gate3_pnl(disagree_rows: List[dict]) -> Tuple[Dict[str, List[float]], dict]:
    """Take the imbalance-favored side at the real taker ask on the disagreement subset.
    Returns (unit_values grouped by GAME/event_ticker, funnel counts)."""
    unit_values: Dict[str, List[float]] = {}
    n_excluded_no_ask = 0
    n_traded = 0
    all_pnl: List[float] = []
    for r in disagree_rows:
        pnl = taker_lift_pnl(r["imb_side"], r["settled_yes"],
                             r["best_yes_ask"], r["best_no_ask"])
        if pnl is None:
            n_excluded_no_ask += 1
            continue
        unit_values.setdefault(r["event_ticker"], []).append(pnl)
        all_pnl.append(pnl)
        n_traded += 1
    funnel = {
        "n_disagree": len(disagree_rows),
        "n_excluded_no_fillable_ask": n_excluded_no_ask,
        "n_traded": n_traded,
        "n_games_with_trade": len(unit_values),
        "mean_pnl": (sum(all_pnl) / len(all_pnl)) if all_pnl else None,
    }
    return unit_values, funnel


def run(cache_path: Path = CACHE_PATH, depth_glob: str = DEPTH_GLOB) -> dict:
    """Full offline analysis against the cached settlement + committed depth tape."""
    settlement = load_settlement_cache(cache_path)
    best, funnel_sets = load_last_preclose_snapshots(depth_glob, settlement)

    markets_in_depth = len(funnel_sets["markets_in_depth"])
    markets_joined = len(funnel_sets["markets_settled_joined"])
    markets_preclose = len(funnel_sets["markets_with_preclose"])
    games_preclose = len({info["event_ticker"] for info in best.values()})

    ttc_hours = [info["ttc_seconds"] / 3600.0 for info in best.values()]
    ttc_dist = _quantiles(ttc_hours)

    report = {
        "n_settled_markets_cached": len(settlement),
        "funnel": {
            "markets_in_depth": markets_in_depth,
            "markets_settled_joined": markets_joined,
            "markets_with_preclose_snapshot": markets_preclose,
            "distinct_games_joinable": games_preclose,
        },
        "ttc_hours_dist": ttc_dist,
    }

    # GATE 1
    if games_preclose < 10:
        report["verdict"] = "DEAD-by-join"
        report["verdict_reason"] = (
            f"only {games_preclose} distinct joinable games (<10); "
            "insufficient settlement-join to test a signal")
        return report

    rows = build_market_signals(best)
    cal = gate2_calibration(rows)
    report["gate2"] = {k: v for k, v in cal.items() if not k.startswith("_")}

    # GATE 2 kill: imbalance must beat the mid ON THE DISAGREEMENT SUBSET.
    dis_imb = cal["disagree_imb_hit_rate"]
    dis_mid = cal["disagree_mid_hit_rate"]
    if cal["disagree_n"] == 0:
        report["verdict"] = "DEAD-by-calibration"
        report["verdict_reason"] = "no disagreement observations — no trade population"
        return report
    if dis_imb is None or dis_imb <= 0.5 or (dis_mid is not None and dis_imb <= dis_mid):
        report["verdict"] = "DEAD-by-calibration"
        report["verdict_reason"] = (
            f"on the disagreement subset imbalance hit {dis_imb:.4f} vs mid "
            f"{dis_mid if dis_mid is None else round(dis_mid,4)} — imbalance adds nothing "
            "over the mid (must be >0.5 AND > mid's own accuracy there)")
        return report

    # GATE 3
    unit_values, pnl_funnel = gate3_pnl(cal["_disagree_rows"])
    report["gate3"] = pnl_funnel

    # GATE 4
    boot = block_bootstrap(unit_values)
    adm = bootstrap_verdict_admissible(unit_values, min_units=10)
    mag = clears_tick_magnitude(boot["ci95"], tick=0.01, min_ticks=1.0)
    report["gate4"] = {
        "bootstrap": boot,
        "admissible": adm,
        "clears_tick_magnitude": mag,
        "n_games_with_trade": pnl_funnel["n_games_with_trade"],
    }

    ci_positive = boot["ci95"][0] is not None and boot["ci95"][0] > 0
    if pnl_funnel["n_games_with_trade"] < 10:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = (
            f"only {pnl_funnel['n_games_with_trade']} games carry a disagreement trade "
            "(<10) — data-adequacy dead even if the point estimate looks positive")
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
            "all gates pass — genuinely uncertain; needs verifier confirmation + "
            "shadow-paper before any capital")
    return report


def _print_report(rep: dict) -> None:
    print(json.dumps(rep, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q26/S22 OFI depth-imbalance probe (read-only)")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="pull settlement live from Kalshi and rewrite the cache first")
    ap.add_argument("--cache", default=str(CACHE_PATH))
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--min-interval", type=float, default=0.25)
    args = ap.parse_args(argv)

    cache_path = Path(args.cache)
    if args.refresh_cache:
        build_settlement_cache(TARGET_SERIES, cache_path, limit=args.limit,
                               min_interval=args.min_interval)
    rep = run(cache_path=cache_path)
    _print_report(rep)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Q29 / S28 — Post-close settlement-lag taker on decided sports outcomes.

Falsifiable milestone (LOOP-QUEUE.md Q29; kb/strategies/00-index.md S28): in the post-close
window (game over, market not yet auto-settled/purged) a Kalshi sports book is claimed to
linger with real two-sided depth (Q25 reported baseball post_close n=2,478, median ask-queue
25,884). A taker who knows the public game result would lift the winner-side YES still offered
below ~$0.98 (or short the decided loser) and collect the near-certain $1 net of the 0.07
taker fee, against stale limit orders / MMs that haven't pulled quotes. This probe measures the
distribution of (settlement_value minus best fillable winner-side real_ask) net of the taker
fee, block-bootstrapped by GAME (L6).

READ-ONLY over `tape/orderbook_depth/` (a probe never mutates tape). Settlement (result +
close_time + event_ticker + retention_available) is pulled ONCE from Kalshi's free
settled-markets endpoint and CACHED under `tape/q29_settlement_cache/` so the run is
re-runnable and a verifier can re-run OFFLINE. Settlement is `broker_truth`; the winner-side
entry is a `real_ask`, the resting depth backing it is `real_bid` (Kalshi posts bids-only per
outcome, so the tradeable YES ask IS the complement of the resting NO bid — see
`collection/orderbook_depth.py`). The settlement value ($1 on the winner side) is `broker_truth`.

THE LOOKAHEAD FIREWALL IS THE WHOLE PROBE (verifier-mandated gate 1). Using the ex-post
settlement result to pick the winner side is legitimate ONLY if, at capture time, the game was
already over and the result public. Establishing that WITHOUT lookahead is the hard part:
  * The reliable game-end anchor is the market object's `close_time` (broker_truth UTC), which
    for sports clusters at game END (S7a). A capture is genuinely post-close iff
    captured_at >= close_time.
  * The sports ticker's own HHMM token is tz-AMBIGUOUS (L46 — league-local, not independently
    verifiable, up to ~13h off). Q25's "post_close" bucket was derived from that token as-UTC;
    this probe reproduces that count ONLY as a descriptive CONTRAST (`ticker_hhmm_as_utc`), and
    NEVER lets it drive a trade decision. The reliable settlement close_time governs.
  * Conservative margin (gate 1): to guarantee the game was decided at capture time even under
    the worst-case ~13h tz mis-statement PLUS a long game, the lookahead-clean population
    requires captured_at >= close_time + (TZ_UNCERTAINTY_HOURS + MAX_GAME_DURATION_HOURS).
  * Date-only / coarse-resolution close_times (a 23:59 / midnight UTC clamp — intra-day close
    unknowable) are EXCLUDED (gate 1).

Other binding gates (do NOT weaken):
  gate 2  FILLABILITY vs mirror artifact — the traded winner-side ask must be a genuine
          resting `real_ask` with real size on the traded side (the backing bid ladder), NOT
          the one-sided 1¢-floor $1.00 mirror / an empty book (L26/L31). Excluded + counted.
  gate 3  EXCLUDE postponed/rescheduled/voided/corrected — result must be in {yes,no}
          (drops scalar, L52) AND the market must be retention_available (sanity-check).
  gate 4  route any CI through core.bootstrap.bootstrap_verdict_admissible (>=10 GAMES,
          >=1 opposing-sign cluster, L41) AND clears_tick_magnitude vs the taker fee (L27).

Verdict is one of: DEAD-by-adequacy (lookahead-clean population < 10 games) /
DEAD-by-convergence (no fillable sub-$1 winner ask — book empty / mirror) / DEAD-by-CI /
ALIVE-PROVISIONAL. Honest expectation (LOOP-QUEUE): DEAD by convergence — Kalshi auto-settles
fast. A DEAD verdict recorded cleanly is a full success (CLAUDE.md Stop rules).

Sizes are FLOATS and can be fractional (L47) — never int-coerce. A one-sided/empty ladder is
VALID data (L23), it just means no fillable ask on that side. Fees ALWAYS from `core.pricing`
at TAKER_FEE_RATE — never hand-rolled (L18/L30).

Run (live settlement pull -> cache, then full analysis):
    python scripts/q29_settlement_lag_probe.py --refresh-cache
Run (offline, against the committed cache — verifier mode):
    python scripts/q29_settlement_lag_probe.py
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from core.bootstrap import (block_bootstrap, bootstrap_verdict_admissible,
                            clears_tick_magnitude)
from core.io import REPO_ROOT
from core.pricing import TAKER_FEE_RATE, fee_per_contract
from core.timeutil import is_coarse_close_time, parse_sports_ticker_hhmm_as_utc

# `core` is pip-installed (editable) but `scripts/` is not a declared package; make the repo
# root importable so the standalone run can reuse the sibling probe's parse helpers verbatim
# (series_of / event_ticker_of / parse_iso / load_settlement_cache — do NOT re-derive). Under
# pytest conftest.py already does this.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from scripts.q26_ofi_depth_imbalance_probe import (  # noqa: E402
    event_ticker_of, ladder_size_sum, load_settlement_cache, parse_iso, series_of)

# Same two-sided, high-turnover sports cells Q25/Q26 targeted (present in the 07-07..07-15
# depth window). NOT the one-sided crypto wings.
TARGET_SERIES = ("KXKBOGAME", "KXNPBGAME", "KXWNBAGAME", "KXMLBGAME",
                 "KXUCLGAME", "KXUECLGAME", "KXUELGAME")

DEPTH_GLOB = str(REPO_ROOT / "tape" / "orderbook_depth" / "dt=*.jsonl")
CACHE_PATH = REPO_ROOT / "tape" / "q29_settlement_cache" / "settlement.json"
# Offline fallback so a verifier can run even before the q29 cache is committed: Q26's cache
# carries result + close_time + event_ticker for the SAME series/window (it just lacks
# retention_available, so gate 3's retention sanity-check is skipped under the fallback).
FALLBACK_CACHE_PATH = REPO_ROOT / "tape" / "q26_settlement_cache" / "settlement.json"

# --- lookahead firewall constants (justified in the module docstring) ------------- #
TZ_UNCERTAINTY_HOURS = 13.0      # L46/Q25: sports-HHMM league-local tz ambiguity, up to ~13h
MAX_GAME_DURATION_HOURS = 6.0    # generous: long MLB extra innings / rain delay (soccer ET+pens ~2.75h)
LOOKAHEAD_MARGIN_HOURS = TZ_UNCERTAINTY_HOURS + MAX_GAME_DURATION_HOURS  # = 19.0

# --- fillability / convergence constants ------------------------------------------ #
CONVERGENCE_ASK = 0.98           # the mechanism's "still offered below ~$0.98" fillable-room line
GAME_FLOOR = 10                  # the L41/L55 minimum distinct-GAMES adequacy floor

# sports ticker mid segment: -YYMONDDHHMM<teams>-  e.g. 'KXNPBGAME-26JUL110500YOMYOK-YOK'
# parse_sports_ticker_hhmm_as_utc / is_coarse_close_time now live in core.timeutil (kb/lessons
# L64 escalation — shared home so future post-close-adjacent probes import them instead of
# re-deriving the tz-ambiguous-ticker discipline per script); re-exported above, zero behavior
# change (byte-identical regex/logic, this script's own tests still call them as `q29.<name>`).


# --------------------------------------------------------------------------- #
# Pure helpers (offline-testable; no clock, no network)
# --------------------------------------------------------------------------- #
def winner_side_ask_depth(settled_yes: int, rec: dict) -> Tuple[str, Optional[float], float]:
    """The winner side's fillable ask and the resting size backing it. Kalshi posts bids-only
    per outcome, so the tradeable YES ask is the complement of the best NO bid and its depth is
    the NO-bid ladder (and vice-versa). Returns (side, winner_ask, backing_depth):
      settled YES -> lift YES at best_yes_ask, backed by the no_bids ladder.
      settled NO  -> lift NO  at best_no_ask,  backed by the yes_bids ladder.
    winner_ask is `real_ask`; backing_depth sums `real_bid` sizes (floats, L47). A None ask /
    empty backing ladder means no fillable winner-side price (mirror or emptied book)."""
    if settled_yes == 1:
        return "yes", rec.get("best_yes_ask"), ladder_size_sum(rec.get("no_bids"))
    return "no", rec.get("best_no_ask"), ladder_size_sum(rec.get("yes_bids"))


def is_fillable_winner(winner_ask: Optional[float], backing_depth: float) -> bool:
    """Gate 2: a genuine resting winner-side ask with real size on the traded side — not the
    $1.00 mirror (L26) and not an emptied book. Requires 0 < ask < 1.0 AND backing_depth > 0."""
    if winner_ask is None or winner_ask >= 1.0 or winner_ask <= 0.0:
        return False
    return backing_depth > 0.0


def settlement_lag_edge(winner_ask: float) -> float:
    """The taker's realized edge lifting the winner side at its real_ask: the winner settles to
    $1 (broker_truth), so net = 1 - winner_ask - taker_fee(winner_ask). Only meaningful on a
    fillable winner_ask (0 < ask < 1); the caller has already gated fillability."""
    return 1.0 - float(winner_ask) - fee_per_contract(winner_ask, TAKER_FEE_RATE)


# --------------------------------------------------------------------------- #
# Settlement cache (live pull with retention_available; verifier re-runs offline)
# --------------------------------------------------------------------------- #
def depth_event_tickers(depth_glob: str) -> Dict[str, set]:
    """Per target series, the set of event_tickers actually present in the depth tape — so the
    live settlement pull only fetches /markets for games we can join (read-only)."""
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
    """Pull settled events per target series, then each depth-window event's markets, and cache
    market_ticker -> {result, close_time, event_ticker, series, retention_available}. Unlike
    Q26's cache this stores retention_available (gate 3 sanity-check). Live network; self-wraps
    a ConnectionError retry (L40). Writes JSON so a verifier re-runs everything else OFFLINE."""
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
            retention_available = bool(markets)  # markets still served -> within L11 retention
            for m in markets:
                mt = m.get("ticker")
                if not mt:
                    continue
                out[mt] = {
                    "result": m.get("result"),
                    "close_time": m.get("close_time"),
                    "event_ticker": m.get("event_ticker") or event_ticker,
                    "series": series,
                    "retention_available": retention_available,
                }
                n_markets += 1
        per_series[series] = n_markets
        print(f"[q29:cache] {series}: {len(events)} settled events, "
              f"{n_events_hit}/{len(want)} depth-window events joined, {n_markets} markets")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "q29_settlement_cache.v1",
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "series": list(series_list),
        "per_series_market_count": per_series,
        "markets": out,
    }
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, sort_keys=True)
    print(f"[q29:cache] wrote {len(out)} settled markets -> {cache_path}")
    return out


# --------------------------------------------------------------------------- #
# Depth tape scan — classify every settled-joined capture (read-only)
# --------------------------------------------------------------------------- #
def scan_captures(depth_glob: str, settlement: Dict[str, dict]) -> Tuple[List[dict], dict]:
    """Scan the depth tape once. For every target-series market ticker with a yes/no settlement
    (L52) that is retention_available (gate 3) and whose close_time is hour-resolved (gate 1),
    emit one classification row per capture. Returns (rows, funnel)."""
    funnel = {
        "markets_in_depth": set(),
        "markets_settled_joined": set(),     # + yes/no result present
        "markets_excluded_not_retained": set(),
        "markets_excluded_coarse_close": set(),
        "markets_kept": set(),
    }
    rows: List[dict] = []
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
                if not s or s.get("result") not in ("yes", "no"):  # L52 scalar/void filter
                    continue
                funnel["markets_settled_joined"].add(mt)
                # gate 3: retention_available sanity-check (absent in the Q26 fallback -> treat
                # as available, since a purged event would not have joined at all).
                if s.get("retention_available") is False:
                    funnel["markets_excluded_not_retained"].add(mt)
                    continue
                close_dt = parse_iso(s.get("close_time"))
                if is_coarse_close_time(close_dt):  # gate 1: date-only close excluded
                    funnel["markets_excluded_coarse_close"].add(mt)
                    continue
                cap_dt = parse_iso(rec.get("captured_at"))
                if cap_dt is None:
                    continue
                funnel["markets_kept"].add(mt)
                settled_yes = 1 if s.get("result") == "yes" else 0
                side, w_ask, depth = winner_side_ask_depth(settled_yes, rec)
                ttc_past_close = (cap_dt - close_dt).total_seconds() / 3600.0
                tick_close = parse_sports_ticker_hhmm_as_utc(mt)
                rows.append({
                    "market_ticker": mt,
                    "event_ticker": s.get("event_ticker") or event_ticker_of(mt),
                    "captured_at": cap_dt,
                    "hours_past_settlement_close": ttc_past_close,
                    "hours_past_ticker_hhmm_close": (
                        (cap_dt - tick_close).total_seconds() / 3600.0
                        if tick_close is not None else None),
                    "settled_yes": settled_yes,
                    "winner_side": side,
                    "winner_ask": w_ask,
                    "backing_depth": depth,
                    "fillable": is_fillable_winner(w_ask, depth),
                })
    return rows, funnel


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


def summarize_window(rows: List[dict]) -> dict:
    """Descriptive summary of a set of capture rows: n, distinct games, fillable count, mirror/
    empty count, and the winner_ask + edge distributions on the fillable subset."""
    games = {r["event_ticker"] for r in rows}
    fillable = [r for r in rows if r["fillable"]]
    fillable_games = {r["event_ticker"] for r in fillable}
    n_mirror_or_empty = sum(1 for r in rows if not r["fillable"])
    winner_asks = [r["winner_ask"] for r in fillable if r["winner_ask"] is not None]
    edges = [settlement_lag_edge(r["winner_ask"]) for r in fillable]
    below_conv = sum(1 for a in winner_asks if a < CONVERGENCE_ASK)
    return {
        "n_captures": len(rows),
        "n_distinct_games": len(games),
        "n_fillable": len(fillable),
        "n_fillable_games": len(fillable_games),
        "n_mirror_or_empty": n_mirror_or_empty,
        "n_winner_ask_below_conv": below_conv,
        "winner_ask_dist": _quantiles(winner_asks),
        "edge_net_fee_dist": _quantiles(edges),
    }


def tz_confound_contrast(rows: List[dict]) -> dict:
    """The load-bearing lookahead diagnostic: how many captures does Q25's tz-ambiguous
    ticker-HHMM-as-UTC method label 'post_close' vs the reliable settlement close_time, and
    how many of the ticker-post-close captures are ACTUALLY pre-close (lookahead-contaminated)?"""
    n = len(rows)
    tick_post = 0
    settle_post = 0
    tick_post_settle_pre = 0
    offsets = []
    seen_market = set()
    for r in rows:
        sp = r["hours_past_settlement_close"] >= 0.0
        tp = (r["hours_past_ticker_hhmm_close"] is not None
              and r["hours_past_ticker_hhmm_close"] >= 0.0)
        if sp:
            settle_post += 1
        if tp:
            tick_post += 1
        if tp and not sp:
            tick_post_settle_pre += 1
        # per-market offset settlement_close - ticker_hhmm_close (both anchored to the same cap)
        if (r["market_ticker"] not in seen_market
                and r["hours_past_ticker_hhmm_close"] is not None):
            seen_market.add(r["market_ticker"])
            offsets.append(r["hours_past_ticker_hhmm_close"] - r["hours_past_settlement_close"])
    return {
        "n_captures": n,
        "post_close_by_ticker_hhmm_as_utc": tick_post,
        "post_close_by_settlement_close_time": settle_post,
        "ticker_post_close_but_actually_pre_close": tick_post_settle_pre,
        "per_market_settlement_minus_ticker_close_hours": _quantiles(offsets),
    }


def _boot_block(unit_values: Dict[str, List[float]]) -> dict:
    boot = block_bootstrap(unit_values)
    adm = bootstrap_verdict_admissible(unit_values, min_units=GAME_FLOOR)
    mag = clears_tick_magnitude(boot["ci95"], tick=0.01, min_ticks=1.0)
    ci_lo = boot["ci95"][0]
    clears = (ci_lo is not None and ci_lo > 0 and adm["admissible"] and mag
              and len(unit_values) >= GAME_FLOOR)
    return {"bootstrap": boot, "admissible": adm, "clears_tick_magnitude": mag,
            "n_games": len(unit_values), "clears": clears}


def run(cache_path: Path = CACHE_PATH, depth_glob: str = DEPTH_GLOB) -> dict:
    """Full offline analysis against the cached settlement + committed depth tape."""
    used_cache = cache_path
    if not cache_path.exists() and FALLBACK_CACHE_PATH.exists():
        used_cache = FALLBACK_CACHE_PATH
    settlement = load_settlement_cache(used_cache)
    rows, funnel_sets = scan_captures(depth_glob, settlement)

    report = {
        "params": {
            "target_series": list(TARGET_SERIES),
            "tz_uncertainty_hours": TZ_UNCERTAINTY_HOURS,
            "max_game_duration_hours": MAX_GAME_DURATION_HOURS,
            "lookahead_margin_hours": LOOKAHEAD_MARGIN_HOURS,
            "convergence_ask": CONVERGENCE_ASK,
            "game_floor": GAME_FLOOR,
        },
        "cache_used": str(used_cache),
        "cache_is_fallback": used_cache == FALLBACK_CACHE_PATH,
        "n_settled_markets_cached": len(settlement),
        "price_source_tags": {"winner_entry": "real_ask", "backing_depth": "real_bid",
                              "settlement_value": "broker_truth"},
        "funnel": {
            "markets_in_depth": len(funnel_sets["markets_in_depth"]),
            "markets_settled_joined": len(funnel_sets["markets_settled_joined"]),
            "markets_excluded_not_retained": len(funnel_sets["markets_excluded_not_retained"]),
            "markets_excluded_coarse_close": len(funnel_sets["markets_excluded_coarse_close"]),
            "markets_kept": len(funnel_sets["markets_kept"]),
        },
    }

    # The lookahead diagnostic (why Q25's post_close was a mirage).
    report["tz_confound_contrast"] = tz_confound_contrast(rows)

    # Three nested capture windows, most-generous first.
    post_close_rows = [r for r in rows if r["hours_past_settlement_close"] >= 0.0]
    lookahead_clean_rows = [r for r in rows
                            if r["hours_past_settlement_close"] >= LOOKAHEAD_MARGIN_HOURS]
    report["window_all_settled_joined"] = summarize_window(rows)
    report["window_post_close_settlement_anchored"] = summarize_window(post_close_rows)
    report["window_lookahead_clean_margin"] = summarize_window(lookahead_clean_rows)

    # GATE 1 — lookahead-clean adequacy. The tradeable population is the fillable subset of the
    # lookahead-clean window. Fall back to the margin=0 post-close fillable window only to REPORT
    # how thin it is (still lookahead-suspect); the binding floor uses the conservative margin.
    la_fillable = [r for r in lookahead_clean_rows if r["fillable"]]
    la_fillable_games = {r["event_ticker"] for r in la_fillable}
    pc_fillable = [r for r in post_close_rows if r["fillable"]]
    pc_fillable_games = {r["event_ticker"] for r in pc_fillable}

    if len(la_fillable_games) < GAME_FLOOR:
        # Distinguish the two DEAD flavours honestly.
        if len(pc_fillable_games) == 0:
            report["verdict"] = "DEAD-by-convergence"
            report["verdict_reason"] = (
                f"ZERO fillable winner-side asks in ANY genuinely post-close (settlement-"
                f"anchored) capture across the tape: of "
                f"{report['window_post_close_settlement_anchored']['n_captures']} post-close "
                f"captures ({report['window_post_close_settlement_anchored']['n_distinct_games']} "
                f"games), all {report['window_post_close_settlement_anchored']['n_mirror_or_empty']} "
                "have an emptied book / $1.00 mirror on the winner side (L26/L31) — Kalshi "
                "empties and settles the book AT close, so no sub-$1 winner ask ever rests to be "
                "lifted. gate 2 fails outright; the CI gate (gate 4) is N/A (empty trade "
                "population). Q25's apparent post_close depth was a tz-confound: "
                f"{report['tz_confound_contrast']['ticker_post_close_but_actually_pre_close']} of "
                f"{report['tz_confound_contrast']['post_close_by_ticker_hhmm_as_utc']} "
                "'ticker-HHMM-as-UTC post_close' captures are actually PRE-close under the "
                "reliable settlement close_time (gate 1).")
        else:
            report["verdict"] = "DEAD-by-adequacy"
            report["verdict_reason"] = (
                f"lookahead-clean fillable population is {len(la_fillable_games)} games "
                f"(< {GAME_FLOOR} floor) at the conservative {LOOKAHEAD_MARGIN_HOURS:.0f}h margin; "
                f"even the (lookahead-suspect) margin=0 post-close fillable window has only "
                f"{len(pc_fillable_games)} games. Untestable as collected.")
        report["gate_status"] = {
            "gate1_lookahead": "FAIL (population below floor)",
            "gate2_fillability": ("FAIL (no fillable winner ask)"
                                  if len(pc_fillable_games) == 0 else "n/a"),
            "gate3_exclusions": "applied (scalar/void/coarse-close excluded)",
            "gate4_bootstrap": "N/A (empty fillable population)",
        }
        return report

    # GATE 2/3 already applied per-row (fillable + retention + result filters).
    # GATE 4 — bootstrap the settlement-lag edge by GAME on the lookahead-clean fillable pop.
    unit_values: Dict[str, List[float]] = defaultdict(list)
    for r in la_fillable:
        unit_values[r["event_ticker"]].append(settlement_lag_edge(r["winner_ask"]))
    boot = _boot_block(dict(unit_values))
    report["gate4_bootstrap"] = boot

    if boot["clears"]:
        report["verdict"] = "ALIVE-PROVISIONAL"
        report["verdict_reason"] = (
            "settlement-lag edge CI strictly >0, admissible (L41), clears the 1-tick magnitude "
            "gate (L27) on the lookahead-clean fillable population — needs verifier + shadow-paper.")
        report["gate_status"] = {"gate1_lookahead": "pass", "gate2_fillability": "pass",
                                 "gate3_exclusions": "applied", "gate4_bootstrap": "pass"}
    else:
        report["verdict"] = "DEAD-by-CI"
        report["verdict_reason"] = (
            f"lookahead-clean fillable population exists but the by-GAME CI fails a gate: "
            f"ci95={boot['bootstrap']['ci95']}, admissible={boot['admissible']['admissible']} "
            f"({boot['admissible']['reasons']}), clears_tick_magnitude="
            f"{boot['clears_tick_magnitude']}, n_games={boot['n_games']}.")
        report["gate_status"] = {"gate1_lookahead": "pass", "gate2_fillability": "pass",
                                 "gate3_exclusions": "applied", "gate4_bootstrap": "FAIL"}
    return report


def _print_report(rep: dict) -> None:
    print(json.dumps(rep, indent=2, default=str))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q29/S28 post-close settlement-lag taker probe (read-only)")
    ap.add_argument("--refresh-cache", action="store_true",
                    help="pull settlement live from Kalshi and rewrite the q29 cache first")
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

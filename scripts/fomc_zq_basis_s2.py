#!/usr/bin/env python3
"""fomc_zq_basis_s2.py — S2 FOMC x ZQ cross-venue basis, single-meeting FIRST CUT.

Dossier opportunity #3 (findings/2026-06-18-codebase-money-map.md; kb/strategies S2). The
structural thesis: a Kalshi KXFEDDECISION bracket prices a clean, mutually-exclusive set of
rate-decision outcomes with NO per-bracket weather overround (the ~10c structural cost that
ate pt1 / S1 / S5). CME's 30-day Fed Funds future (ZQ) prices the SAME event via the
month-average identity. If the two venues disagree by more than fees, there is a basis.

THIS IS A STRUCTURE CHECK, NOT A STATISTICAL EDGE. n = 1 meeting. One event can NEVER give a
bootstrapped CI, so this script makes NO edge claim. Its job is narrow and honest:
  (a) Is the FOMC bracket overround actually small (vs the ~10c weather overround)?  -> structure.
  (b) Does a tradeable Kalshi-vs-ZQ P(hold) basis plausibly exist net of fees?         -> magnitude.
  (c) Was THIS meeting informative, or a near-certain hold that tells us nothing?       -> caveat.
  (d) Is the structure clean enough to justify the CME tick-data spend the real test needs?

READ-ONLY. Pulls two FREE, unauthenticated sources; caches raw pulls under data/fomc_zq/.

================================================================================
DATA SOURCE 1 — Kalshi public historical candlesticks (unauthenticated, FREE)
================================================================================
  GET {api_base}/series/KXFEDDECISION/markets/{ticker}/candlesticks
      ?start_ts={unix}&end_ts={unix}&period_interval={1|60|1440}
Returns per-period candles, each carrying a yes_ask block and a yes_bid block as
{open/high/low/close}_dollars plus a `price` OHLC and volume.

The five June-2026 outcome markets (closed 2026-06-17T17:59:00Z = the 1:59pm-ET halt) form
the mutually-exclusive, exhaustive decision partition:
  KXFEDDECISION-26JUN-H0   "Fed maintains rate"  (HOLD)  -> settled YES  (the realized outcome)
  KXFEDDECISION-26JUN-H25  "Hike 25bps"                  -> settled NO
  KXFEDDECISION-26JUN-H26  "Hike >25bps"                 -> settled NO
  KXFEDDECISION-26JUN-C25  "Cut 25bps"                   -> settled NO
  KXFEDDECISION-26JUN-C26  "Cut >25bps"                  -> settled NO

We use `yes_ask.close_dollars` as the real BBO taker ask and tag it `real_ask`. CAVEAT
(stated honestly): this is the published top-of-book yes ask AT CANDLE CLOSE. It is a real,
published book price (not synthetic, not a midpoint) -> tag `real_ask` per core/source_tag.py.
But it is BBO-at-candle-close, NOT full depth and NOT a guaranteed fill: a real order could
walk the book or arrive between candles. So this is the right tag for "what was the published
taker ask" but it overstates fillable size. The full multi-meeting version needs depth ticks.

Degenerate post-settlement candles (yes_ask==1.0000 with yes_bid==0.0000 -> no NO liquidity
to lift) are DROPPED: an ask of exactly 1.0 means best_no_bid==0, i.e. nothing fillable.

================================================================================
DATA SOURCE 2 — ZQ (30-day Fed Funds futures), Yahoo chart API (FREE)
================================================================================
  GET https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d
We try the June/July contract months (ZQM26.CME / ZQN26.CME); both 404 on Yahoo, so we fall
back to the FRONT-MONTH continuous `ZQ=F` (url-encoded ZQ%3DF), daily close. In June 2026 the
front month IS the June contract, so ZQ=F prices exactly the meeting month. ZQ price P implies
an average daily EFFR over the contract month of (100 - P) percent.

================================================================================
ZQ -> P(hold) — the CME-FedWatch month-average identity (FORMULA, documented)
================================================================================
A 30-day Fed Funds future settles to  100 - (simple average of the daily EFFR over the
contract calendar MONTH). For the meeting month, split the month at the date the decision
takes effect (the FOMC decides 2026-06-17, effective the next business day -> June 18):

    implied_avg_rate = (N_pre * r_pre + N_post * r_post) / N_days

  N_days = 30 (June).  Split at the effective date d_eff = 2026-06-18:
    N_pre  = days the OLD rate is in effect within June  = 17  (June 1..17)
    N_post = days the NEW rate is in effect within June  = 13  (June 18..30)
  r_pre  = the EFFR in effect BEFORE the meeting  (the current target-range midpoint)
  r_post = the EFFR the market expects AFTER the meeting  (what we solve for)

Solve for the market-expected post-meeting rate:
    r_post = (implied_avg_rate * N_days - N_pre * r_pre) / N_post

Map r_post to P(hold). The current target range (3.50-3.75%, midpoint 3.625%) and the
adjacent +/-25bp ranges give expected post-meeting rates under each outcome:
    hold      -> 3.625%   (midpoint of 3.50-3.75)
    +25bp hike-> 3.875%
    -25bp cut -> 3.375%
We place r_post on the nearest-two-outcomes line and read off the implied weight on HOLD.
If r_post is at/above the hold midpoint we interpolate hold-vs-hike; if below, hold-vs-cut.
This is the standard two-step FedWatch decomposition for a single-move grid. Bigger moves
(>25bp) are negligible here and folded into the nearest 25bp node.

ASSUMPTIONS (every one stated, none hidden):
  A1. EFFR == target-range MIDPOINT (EFFR floats a few bp inside the band; we use the
      midpoint as the canonical settlement proxy, the FedWatch convention).
  A2. Current target range = 3.50-3.75% (Fed's last move, 2025-12-11; midpoint 3.625%).
      Confirmed externally and internally: ZQ June implied avg sits ~3.625% = this midpoint,
      i.e. the market priced ~no change across the whole month.
  A3. June has 30 days; the decision is effective the day AFTER the meeting (June 18), so the
      pre/post day split is 17/13.
  A4. Only a single 25bp grid {cut25, hold, hike25} carries meaningful weight (the >25bp
      Kalshi legs priced ~1c each — confirmed in the candles).

================================================================================
EFFR LOOK-AHEAD LEAK SCREEN  (peer-review flag — how we avoid it)
================================================================================
A naive backout uses the REALIZED average daily EFFR over June to infer r_post. But for a
PRE-meeting probability on date t < 2026-06-17 you must use ONLY information available on t.
The realized June EFFR average includes POST-meeting days whose EFFR is exactly the answer we
are trying to infer -> using it would leak the outcome.

How we avoid it:
  * r_pre is NOT a realized future daily-EFFR average. It is the CURRENT target-range midpoint
    (3.625%), a contemporaneous, on-date-t known constant (the rate already in effect).
  * implied_avg_rate comes from the ZQ PRICE ON DATE t (100 - close_t), a market price quoted
    on t. It embeds the market's forward-looking expectation, not realized post-meeting EFFR.
  * We NEVER read realized post-2026-06-17 EFFR prints. The only "post" quantity, r_post, is
    SOLVED from the on-date-t ZQ price. So every input to P(hold)[t] is known on t. No leak.
  (The full multi-meeting version must apply the same screen per meeting: r_pre = the target
   midpoint in effect on t, implied_avg = ZQ price on t, never the realized monthly EFFR.)

================================================================================
BASIS + FEE MODEL
================================================================================
  basis[t] = Kalshi_P(hold)[t] - ZQ_P(hold)[t]          (over the pre-halt window)
A positive basis means Kalshi prices HOLD richer than ZQ -> the directional trade is SELL the
Kalshi hold (or buy a move) / take the ZQ side; negative -> the reverse. We do NOT model a
"hedge": Kalshi halts at 1:59pm and settles at ~2:05pm, so the Kalshi leg is a FROZEN
directional pre-position with unbounded per-event downside (dossier caveat). We mark the
Kalshi leg to SETTLEMENT (H0 = YES -> $1.00).

Net-of-fee per 1 contract ($1 notional):
  * Kalshi taker fee = ceil(fee_coeff * p * (1-p) * contracts) cents, where fee_coeff is
    core.pricing.TAKER_FEE_RATE (p = normalized hold prob). Charged in CENTS, rounded UP -> $.
  * ZQ commission: ZQ_COMMISSION per contract (round-turn retail futures, conservative).
  * ZQ slippage: 1 ZQ tick. ZQ tick = 0.0025 price pts = $10.4175 per contract; on a $1-notional
    per-contract basis we charge ZQ_TICK_BP_AS_PROB as a probability-space haircut (1 tick of
    rate ~ a fraction of a 25bp move -> a few tenths of a cent of implied-prob slippage). Stated
    as a constant; the real test prices it off live ZQ depth.

The headline net basis = |basis| minus (Kalshi taker fee + ZQ commission + 1 ZQ tick), in
cents per contract. If that is <= 0 across the window, there is no tradeable gap on THIS event.

================================================================================
PER-OBS PROVENANCE (persisted to data/fomc_zq/, gitignored)
================================================================================
Per period we persist: raw_yes_ask (H0), bracket_sum, overround_absorbed,
price_source_tag="real_ask", plus the ZQ inputs (zq_close, implied_avg_rate, r_pre, r_post,
n_pre, n_post). Raw API pulls are cached with a sha256 (core.canonical.sha256_hex) for
provenance / byte-identical re-run.

Run:
  ./.venv/bin/python scripts/fomc_zq_basis_s2.py                       # June 2026, hourly
  ./.venv/bin/python scripts/fomc_zq_basis_s2.py --period-interval 1440 # daily
  ./.venv/bin/python scripts/fomc_zq_basis_s2.py --meeting 26JUN        # explicit meeting
  ./.venv/bin/python scripts/fomc_zq_basis_s2.py --meeting 25JUL        # an illustrative prior meeting
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Make the substrate importable however this script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.canonical import sha256_hex  # noqa: E402
from core.pricing import bracket_sum, normalized_ask, overround, TAKER_FEE_RATE  # noqa: E402
from core.source_tag import tag_or_synthetic  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "fomc_zq"

KALSHI_API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXFEDDECISION"
UA = {"User-Agent": "Mozilla/5.0"}

# The five outcome legs of a KXFEDDECISION meeting bracket (suffix -> meaning).
OUTCOME_SUFFIXES = ["H0", "H25", "H26", "C25", "C26"]
HOLD_SUFFIX = "H0"

# ── fee / cost model constants (see docstring; all stated assumptions) ──────────
KALSHI_FEE_COEFF = TAKER_FEE_RATE  # core.pricing single fee source (L5): ceil(coeff*p*(1-p)) cents
ZQ_COMMISSION_USD = 0.012       # conservative retail round-turn commission per ZQ contract ($)
# 1 ZQ tick = 0.0025 rate pts. As an implied-prob haircut over a 25bp decision grid, one tick
# of rate is 0.0025/0.25 = 0.01 of the move's probability weight -> ~1c of prob slippage,
# halved because basis trades typically need only a partial tick of adverse selection.
ZQ_TICK_PROB_HAIRCUT = 0.005    # ~0.5c of implied-prob slippage per the basis leg

# ── ZQ month-average identity constants (June 2026; A1-A4) ──────────────────────
CURRENT_TARGET_MID = 3.625      # midpoint of the 3.50-3.75% range in effect (A2)
HOLD_RATE = 3.625               # post-meeting EFFR if hold (A1: EFFR == midpoint)
HIKE25_RATE = 3.875             # post-meeting EFFR if +25bp
CUT25_RATE = 3.375              # post-meeting EFFR if -25bp


# ─── HTTP + cache ───────────────────────────────────────────────────────────────
def _get_json(url: str, timeout: int = 30, retries: int = 4) -> dict:
    """GET JSON with exponential backoff on transient 429/5xx (Kalshi rate-limits hard).
    The prior attempt at this probe DIED on a transient API error; this makes it
    re-runnable rather than fragile. Raises after exhausting retries."""
    delay = 2.0
    last: Optional[Exception] = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:       # noqa: PERF203
            last = e
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(delay)
                delay *= 2.0
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(delay)
            delay *= 2.0
    raise RuntimeError(f"GET failed after {retries} attempts: {url} :: {last!r}")


def _cache_write(name: str, obj: dict) -> str:
    """Cache a raw pull and return its sha256 (provenance / byte-identical re-run)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"))
    (CACHE_DIR / name).write_text(text)
    return sha256_hex(text)


def _cache_read(name: str) -> Optional[dict]:
    """Return a previously cached raw pull, or None. Lets a re-run survive a transient
    rate-limit by reusing the last good pull (the cache IS the provenance record)."""
    p = CACHE_DIR / name
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:                          # noqa: BLE001
            return None
    return None


# ─── Kalshi candlesticks ────────────────────────────────────────────────────────
def fetch_candles(ticker: str, start_ts: int, end_ts: int, period_interval: int) -> List[dict]:
    """Pull candlesticks for one market over [start_ts, end_ts]. Cached raw with a sha256.
    On a transient fetch failure, falls back to the last good cached pull if one exists."""
    name = f"kalshi_{ticker}_pi{period_interval}.json"
    url = (f"{KALSHI_API_BASE}/series/{SERIES}/markets/{ticker}/candlesticks"
           f"?start_ts={start_ts}&end_ts={end_ts}&period_interval={period_interval}")
    try:
        d = _get_json(url)
        _cache_write(name, d)
    except Exception as e:                         # noqa: BLE001
        cached = _cache_read(name)
        if cached is None:
            raise
        print(f"[cache] fresh pull failed for {ticker} ({e!r}); using cached pull")
        d = cached
    return d.get("candlesticks", []) or []


def _yes_ask_close(candle: dict) -> Optional[float]:
    """The published BBO yes ask at candle close, in dollars. None if missing/degenerate."""
    ya = candle.get("yes_ask") or {}
    yb = candle.get("yes_bid") or {}
    try:
        ask = float(ya["close_dollars"])
        bid = float(yb["close_dollars"])
    except (KeyError, TypeError, ValueError):
        return None
    # Degenerate post-settlement book: ask==1.0 with bid==0.0 -> no NO liquidity to lift.
    if ask >= 0.9999 and bid <= 1e-9:
        return None
    return ask


def build_kalshi_series(meeting: str, start_ts: int, end_ts: int, period_interval: int
                        ) -> Tuple[Dict[int, dict], dict]:
    """Per-period Kalshi P(hold) from the real BBO yes_ask of all 5 outcome legs.

    Returns ({end_period_ts: row}, drop_stats). A period is USABLE only if ALL 5 legs have a
    non-degenerate yes_ask at that period (complete partition for bracket_sum). Hard Rule #3:
    every ask->prob goes through core.pricing.normalized_ask.
    """
    legs: Dict[str, Dict[int, float]] = {}
    for suf in OUTCOME_SUFFIXES:
        ticker = f"{SERIES}-{meeting}-{suf}"
        cs = fetch_candles(ticker, start_ts, end_ts, period_interval)
        by_ts: Dict[int, float] = {}
        for c in cs:
            t = c.get("end_period_ts")
            ask = _yes_ask_close(c)
            if t is not None and ask is not None:
                by_ts[int(t)] = ask
        legs[suf] = by_ts

    # Periods where every leg has a non-degenerate ask.
    common = set.intersection(*[set(v.keys()) for v in legs.values()]) if legs else set()
    drops = {
        "periods_per_leg": {suf: len(v) for suf, v in legs.items()},
        "periods_complete": len(common),
        "periods_dropped_incomplete": (
            len(set.union(*[set(v.keys()) for v in legs.values()])) - len(common)
            if legs else 0),
    }

    rows: Dict[int, dict] = {}
    for t in sorted(common):
        asks = [legs[suf][t] for suf in OUTCOME_SUFFIXES]
        bs = bracket_sum(asks)
        ov = overround(asks)
        ya_hold = legs[HOLD_SUFFIX][t]
        p_hold = normalized_ask(ya_hold, bs)  # Hard Rule #3
        rows[t] = {
            "end_period_ts": t,
            "ts_iso": datetime.fromtimestamp(t, tz=timezone.utc).isoformat(),
            "raw_yes_ask": round(ya_hold, 4),          # H0 (hold) BBO yes ask
            "bracket_sum": round(bs, 4),
            "overround_absorbed": round(ov, 4),
            "member_count": len(OUTCOME_SUFFIXES),
            "kalshi_p_hold": round(p_hold, 6),
            "leg_asks": {suf: round(legs[suf][t], 4) for suf in OUTCOME_SUFFIXES},
            "price_source_tag": tag_or_synthetic("real_ask"),  # published BBO ask
        }
    return rows, drops


# ─── ZQ side ────────────────────────────────────────────────────────────────────
def fetch_zq_daily() -> Tuple[Dict[str, float], str]:
    """Daily ZQ close keyed by UTC date 'YYYY-MM-DD'. Tries month contracts, falls back to
    the front-month continuous ZQ=F. Returns ({date: close}, symbol_used)."""
    syms = ["ZQM26.CME", "ZQN26.CME", "ZQ%3DF"]
    last_err: Optional[Exception] = None
    for sym in syms:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=3mo&interval=1d"
        try:
            d = _get_json(url)
        except Exception as e:                    # noqa: BLE001 - try next contract
            last_err = e
            continue
        try:
            res = d["chart"]["result"][0]
            ts = res["timestamp"]
            closes = res["indicators"]["quote"][0]["close"]
        except (KeyError, TypeError, IndexError) as e:
            last_err = e
            continue
        _cache_write(f"zq_{sym.replace('%3D', '_').replace('.', '_')}.json", d)
        out: Dict[str, float] = {}
        for t, c in zip(ts, closes):
            if c is None:
                continue
            day = datetime.fromtimestamp(t, tz=timezone.utc).date().isoformat()
            out[day] = float(c)
        if out:
            return out, sym
    raise RuntimeError(f"all ZQ symbols failed; last error: {last_err!r}")


def zq_p_hold_from_close(close: float, n_pre: int, n_post: int,
                         r_pre: float = CURRENT_TARGET_MID) -> dict:
    """ZQ-implied P(hold) for one daily close, via the month-average identity.

    LEAK-FREE: r_pre is the current target midpoint (known on date t); implied_avg is the ZQ
    price on t (forward-looking). We never read realized post-meeting EFFR. Returns a dict with
    the full decomposition for provenance.
    """
    n_days = n_pre + n_post
    implied_avg = 100.0 - close                                  # = average daily EFFR over month
    r_post = (implied_avg * n_days - n_pre * r_pre) / n_post     # solve for expected post rate

    # Map r_post to P(hold) on the nearest 25bp grid (two-node interpolation).
    if r_post >= HOLD_RATE:
        # interpolate hold (3.625) <-> hike25 (3.875)
        w_move = (r_post - HOLD_RATE) / (HIKE25_RATE - HOLD_RATE)
        move_side = "hike25"
    else:
        # interpolate hold (3.625) <-> cut25 (3.375)
        w_move = (HOLD_RATE - r_post) / (HOLD_RATE - CUT25_RATE)
        move_side = "cut25"
    w_move = max(0.0, min(1.0, w_move))     # clamp to [0,1]
    p_hold = 1.0 - w_move
    return {
        "zq_close": round(close, 4),
        "implied_avg_rate": round(implied_avg, 4),
        "r_pre": r_pre,
        "r_post": round(r_post, 4),
        "n_pre": n_pre,
        "n_post": n_post,
        "move_side": move_side,
        "zq_p_hold": round(p_hold, 6),
        "price_source_tag": tag_or_synthetic("synthetic"),  # a DERIVED probability, not a fill
    }


# ─── fee model ──────────────────────────────────────────────────────────────────
def kalshi_taker_fee_usd(p: float, contracts: int = 1) -> float:
    """Kalshi taker fee in DOLLARS: ceil(fee_coeff * p*(1-p) * contracts) cents -> dollars.
    fee_coeff is core.pricing.TAKER_FEE_RATE. p is the normalized hold probability (trade price)."""
    cents = math.ceil(KALSHI_FEE_COEFF * p * (1.0 - p) * contracts * 100.0)
    return cents / 100.0


def net_basis_usd(kalshi_p: float, zq_p: float) -> dict:
    """The net-of-fee tradeable basis on ONE period, in dollars per contract.
    gross = |kalshi_p - zq_p|; subtract Kalshi taker fee + ZQ commission + 1 ZQ tick."""
    gross = abs(kalshi_p - zq_p)
    k_fee = kalshi_taker_fee_usd(kalshi_p)
    total_cost = k_fee + ZQ_COMMISSION_USD + ZQ_TICK_PROB_HAIRCUT
    net = gross - total_cost
    return {
        "gross_basis": round(kalshi_p - zq_p, 6),
        "gross_abs": round(gross, 6),
        "kalshi_taker_fee": round(k_fee, 4),
        "zq_commission": ZQ_COMMISSION_USD,
        "zq_tick_haircut": ZQ_TICK_PROB_HAIRCUT,
        "total_cost": round(total_cost, 4),
        "net_basis": round(net, 6),
    }


# ─── meeting window ─────────────────────────────────────────────────────────────
def meeting_window(meeting: str) -> Tuple[int, int, int, int, int]:
    """(start_ts, end_ts, n_pre, n_post, n_days) for a known meeting code.

    n_pre/n_post = month-day split at the decision EFFECTIVE date (day after the meeting).
    Only June-2026 (26JUN) is fully parameterized for the ZQ identity; other meetings are
    supported for the Kalshi-side pull (illustrative) with a best-effort month split.
    """
    table = {
        # meeting: (start, end, n_pre, n_post, n_days)   -- ZQ split is meeting-specific
        "26JUN": (datetime(2026, 6, 3, tzinfo=timezone.utc),
                  datetime(2026, 6, 18, tzinfo=timezone.utc), 17, 13, 30),
        # 25JUL meeting 2025-07-30; July has 31 days, decision effective 2025-07-31 -> 30/1.
        "25JUL": (datetime(2025, 7, 16, tzinfo=timezone.utc),
                  datetime(2025, 7, 31, tzinfo=timezone.utc), 30, 1, 31),
    }
    if meeting not in table:
        raise ValueError(f"meeting {meeting!r} not parameterized; known: {sorted(table)}")
    s, e, n_pre, n_post, n_days = table[meeting]
    return int(s.timestamp()), int(e.timestamp()), n_pre, n_post, n_days


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S2 FOMC x ZQ single-meeting basis (structure check)")
    ap.add_argument("--meeting", default="26JUN", help="meeting code (e.g. 26JUN, 25JUL)")
    ap.add_argument("--period-interval", type=int, default=60, choices=[1, 60, 1440],
                    help="Kalshi candle period: 1=minute, 60=hourly, 1440=daily")
    ap.add_argument("--json-out", default=None, help="optional path to dump full result JSON")
    args = ap.parse_args(argv)

    start_ts, end_ts, n_pre, n_post, n_days = meeting_window(args.meeting)

    # ── Kalshi side (with hourly->daily fallback if hourly is empty) ──
    pi = args.period_interval
    kalshi_rows, kdrops = build_kalshi_series(args.meeting, start_ts, end_ts, pi)
    if not kalshi_rows and pi == 60:
        print("[fallback] hourly returned no complete periods -> retrying daily (1440)")
        pi = 1440
        kalshi_rows, kdrops = build_kalshi_series(args.meeting, start_ts, end_ts, pi)

    # ── ZQ side ──
    zq_daily, zq_sym = fetch_zq_daily()

    # ── join Kalshi periods to the ZQ close of that UTC date ──
    joined: List[dict] = []
    for t in sorted(kalshi_rows):
        krow = kalshi_rows[t]
        day = krow["ts_iso"][:10]
        if day not in zq_daily:
            continue
        zrow = zq_p_hold_from_close(zq_daily[day], n_pre, n_post)
        fees = net_basis_usd(krow["kalshi_p_hold"], zrow["zq_p_hold"])
        # Merge ZQ fields without clobbering the Kalshi real_ask provenance: the ZQ-derived
        # probability carries its own (synthetic) tag under a distinct key.
        zrow_merge = dict(zrow)
        zrow_merge["zq_price_source_tag"] = zrow_merge.pop("price_source_tag")
        joined.append({**krow, **zrow_merge, **fees, "zq_symbol": zq_sym, "zq_date": day})

    # ── report ──
    print("=" * 80)
    print(f"S2 FOMC x ZQ BASIS — meeting={args.meeting}  period_interval={pi}  "
          f"(STRUCTURE CHECK, n=1, NO EDGE CLAIM)")
    print("=" * 80)
    print(f"Kalshi legs: {OUTCOME_SUFFIXES}  (H0=HOLD settled YES, rest settled NO)")
    print(f"  periods/leg: {kdrops['periods_per_leg']}")
    print(f"  complete periods (all 5 legs priced): {kdrops['periods_complete']}  "
          f"dropped(incomplete/degenerate): {kdrops['periods_dropped_incomplete']}")
    print(f"ZQ symbol used: {zq_sym}  (month split n_pre={n_pre}/n_post={n_post} of {n_days}d)")
    print(f"joined periods (Kalshi period x ZQ daily close): {len(joined)}")

    if not joined:
        print("\nNO joined periods — cannot compute basis. (Check the meeting window / ZQ dates.)")
        return 0

    ov = np.array([r["overround_absorbed"] for r in joined])
    kp = np.array([r["kalshi_p_hold"] for r in joined])
    zp = np.array([r["zq_p_hold"] for r in joined])
    gross = np.array([r["gross_basis"] for r in joined])
    net = np.array([r["net_basis"] for r in joined])

    print("\n--- FOMC BRACKET OVERROUND (the structural thesis) ---")
    print(f"  overround_absorbed: mean={ov.mean():+.4f}  median={np.median(ov):+.4f}  "
          f"min={ov.min():+.4f}  max={ov.max():+.4f}  (price_source_tag=real_ask)")
    print(f"  compare: weather KXHIGH overround was ~+0.10 (the pt1/S1/S5 killer).")

    print("\n--- Kalshi P(hold) vs ZQ P(hold) ---")
    print(f"  Kalshi P(hold): mean={kp.mean():.4f}  min={kp.min():.4f}  max={kp.max():.4f}")
    print(f"  ZQ     P(hold): mean={zp.mean():.4f}  min={zp.min():.4f}  max={zp.max():.4f}")

    print("\n--- BASIS = Kalshi P(hold) - ZQ P(hold) ---")
    print(f"  gross basis: mean={gross.mean():+.4f}  min={gross.min():+.4f}  max={gross.max():+.4f}")
    print(f"  |gross|:     mean={np.abs(gross).mean():.4f}  max={np.abs(gross).max():.4f}")
    print(f"  net-of-fee basis: mean={net.mean():+.4f}  max={net.max():+.4f}  "
          f"(>0 periods: {(net > 0).sum()}/{len(net)})")
    print(f"  fee model: Kalshi taker ceil(0.07*p*(1-p)) + ZQ comm ${ZQ_COMMISSION_USD} "
          f"+ 1 tick ${ZQ_TICK_PROB_HAIRCUT}")

    # a small periodic table (head + tail)
    print("\n  period (UTC)         k_p_hold  zq_p_hold  gross   net     ovr")
    show = joined if len(joined) <= 14 else joined[:7] + joined[-7:]
    for r in show:
        print(f"  {r['ts_iso'][:16]}   {r['kalshi_p_hold']:.4f}    {r['zq_p_hold']:.4f}   "
              f"{r['gross_basis']:+.4f} {r['net_basis']:+.4f} {r['overround_absorbed']:+.4f}")

    # ── verdict ──
    # "Low information" = HOLD stayed near-certain the whole window. A meeting where P(hold)
    # never fell below ~0.92 on either venue was never genuinely in doubt -> the basis on it
    # cannot teach us much about a contested-meeting edge. (0.92 is deliberately generous:
    # even a 0.94 floor means the move legs collectively never bid past ~6c.)
    LOW_INFO_FLOOR = 0.92
    kalshi_certain = kp.min() >= LOW_INFO_FLOOR
    zq_certain = zp.min() >= LOW_INFO_FLOOR
    any_net_positive = bool((net > 0).any())
    print("\n" + "=" * 80)
    print("VERDICT (honest, n=1 — this is a STRUCTURE check, not an edge):")
    print("=" * 80)
    print(f"  (a) n=1 meeting -> NO statistical claim, NO bootstrapped CI possible. Period.")
    print(f"  (b) Was June informative? Kalshi P(hold) range [{kp.min():.3f},{kp.max():.3f}], "
          f"ZQ [{zp.min():.3f},{zp.max():.3f}].")
    if kalshi_certain and zq_certain:
        print(f"      -> BOTH venues priced HOLD as near-certain (P(hold) never < {LOW_INFO_FLOOR}) "
              f"throughout. This was a LOW-INFORMATION meeting; the basis here is "
              f"UNINFORMATIVE about a contested-meeting edge.")
    else:
        print(f"      -> at least one venue dropped P(hold) below {LOW_INFO_FLOOR} -> some genuine "
              f"hold uncertainty was priced.")
    print(f"  (c) FOMC bracket overround mean={ov.mean():+.4f} vs ~+0.10 weather -> "
          f"{'MUCH smaller (clean prob-to-prob), structural thesis HOLDS' if ov.mean() < 0.05 else 'NOT as clean as hoped'}.")
    print(f"  (d) Net-of-fee basis: {'some period(s) net-positive' if any_net_positive else 'NO period nets positive'} "
          f"on this single event. {'But see (b)/(a): one event proves nothing.' if any_net_positive else ''}")

    if args.json_out:
        payload = {
            "meeting": args.meeting, "period_interval": pi, "zq_symbol": zq_sym,
            "n_pre": n_pre, "n_post": n_post, "n_days": n_days,
            "kalshi_drops": kdrops, "n_joined": len(joined),
            "fee_model": {"kalshi_fee_coeff": KALSHI_FEE_COEFF,
                          "zq_commission_usd": ZQ_COMMISSION_USD,
                          "zq_tick_prob_haircut": ZQ_TICK_PROB_HAIRCUT},
            "summary": {
                "overround_mean": float(ov.mean()), "overround_max": float(ov.max()),
                "kalshi_p_hold_min": float(kp.min()), "kalshi_p_hold_max": float(kp.max()),
                "zq_p_hold_min": float(zp.min()), "zq_p_hold_max": float(zp.max()),
                "gross_basis_mean": float(gross.mean()), "gross_basis_max_abs": float(np.abs(gross).max()),
                "net_basis_mean": float(net.mean()), "net_basis_max": float(net.max()),
                "any_net_positive": any_net_positive,
                "low_information_meeting": bool(kalshi_certain and zq_certain),
            },
            "rows": joined,
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2, default=str))
        print(f"\nwrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

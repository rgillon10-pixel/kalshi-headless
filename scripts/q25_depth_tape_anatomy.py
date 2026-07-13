#!/usr/bin/env python3
"""q25_depth_tape_anatomy.py — Q25: depth-tape anatomy scan (READ-ONLY, DISCOVERY-CLASS).

LOOP-QUEUE.md Q25. `tape/orderbook_depth/` is the largest tape family (~1,100-1,280 lines/hour
since 07-07, 3-4x everything else combined, L38), yet it has only ever been read as a fill GATE
*after* an idea existed (S14's queue-aware sim, S19, Q24) — never as a discovery scan. This is
that scan: a fill-plausibility MAP to seed future idea-gen rounds.

DESCRIPTIVE STATISTICS ONLY. NO bootstrap, NO CI, NO verdict, NO P&L, NO registry flip. The
precedent is `scripts/s20_ladder_overround_anatomy.py` (same read-only shape, same source-tag
hygiene, same offline-unit-test discipline). Nothing here mutates, reorders, or deletes tape.

It tabulates, by (family, category, time-to-close bucket):
  (a) queue depth at best bid/ask  — per capture: yes-bid-side size = `yes_bids[0][1]`;
      yes-ask-side size = the MIRROR = top of the `no_bids` ladder (a YES offer at p is a NO bid
      at 1-p, so the size resting AT the best YES ask is `no_bids[0][1]`, exactly as s20's
      `_ask_side_depth`). Reports median + p25/p75 of each side.
  (b) staleness / quote age — per ticker, captures ordered by `captured_at` across ALL days;
      a consecutive pair whose full BBO tuple (best_yes_bid, best_yes_ask, best_no_bid,
      best_no_ask) is UNCHANGED is "frozen" (L32's frozen-pair notion, here as a DISTRIBUTION:
      per-cell frozen fraction + a family/category streak-length distribution).
  (c) one-sidedness incidence — per capture: `yes_side_empty` (no yes_bids), `no_side_empty`
      (no no_bids => no tradeable YES ask), `any_side_empty` (L31's wing shape, measured
      OUTSIDE crypto too).
  (d) observed resting-order turnover — THE fill-plausibility signal. NOT a canonical formula;
      DEFINED here (see TURNOVER_FORMULA_DOC) and caveated hard: for a consecutive same-ticker
      pair where the best PRICE on a side is UNCHANGED, turnover = max(0, size_prev - size_now)
      / size_prev — contracts that left the queue at a stable price (a proxy for fills+cancels
      ahead). SNAPSHOT-SAMPLED at hourly cadence, so intra-hour round-trips are invisible
      (undercount) and a price move resets the pair (excluded) — a coarse order-of-magnitude
      observable, NOT a fill guarantee. Oriented against the two named fill-rate anchors:
      S19's 0.45% queue-aware fill rate (DEAD) and S14's 2.5% incidental-wing benchmark — cited
      for orientation only, NOT recomputed.

Honest-accounting (BINDING): every number carries its denominator (n_captures for capture-based
metrics; n_pairs for pair-based). Any cell with <20 captures (or <20 pairs) is the string
sentinel "insufficient" — never extrapolated/imputed. Source tags: asks=real_ask, bids=real_bid
(both real/fillable, per the depth collector). No synthetic numbers, no P&L, no CI here.

Run:
    python scripts/q25_depth_tape_anatomy.py
    python scripts/q25_depth_tape_anatomy.py --json-out findings/depth_anatomy.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.io import REPO_ROOT  # noqa: E402

DEPTH_DIR = REPO_ROOT / "tape" / "orderbook_depth"
DEFAULT_JSON_OUT = REPO_ROOT / "findings" / "depth_anatomy.json"

MIN_N = 20  # honest-accounting: fewer than this many captures/pairs => "insufficient"

# --- fill-rate anchors (cited for orientation ONLY; NOT recomputed here) -------------------- #
# S19's queue-aware fill rate (DEAD) and S14's incidental-wing benchmark. Turnover is a looser
# observability proxy, NOT the fill rate itself — it can only rule a cell OUT (dead-thin), never
# rule one IN as fillable.
ANCHOR_S19_FILL = 0.0045   # findings/2026-07-13-s19-wing-fade-fillsim-q23-verdict.md (4/? = 0.45%)
ANCHOR_S14_WING = 0.025    # S14 incidental wing fill 55/2172 = 2.5%

# --- crypto uses ET for its hour token (confirmed against tape + collection/crypto_hourly.py) - #
# The milestone spec's example ("KXBTC-26JUL1221 -> close 21:00 UTC") is OFF BY THE ET OFFSET:
# empirically token hour 21 (KXBTC-26JUL0621) is captured at 00:57:50 UTC on 2026-07-07, i.e.
# 20:57 EDT on 07-06, closing at 21:00 EDT = 01:00 UTC 07-07. So the crypto hour token is ET,
# matching crypto_hourly.py's docstring ("HH in ET"). We localize to America/New_York (EDT in
# July, UTC-4) then convert to UTC. Sports HHMM is treated as UTC per the spec's contract (its
# true timezone is league-local and not independently verifiable from the tape because settled
# markets linger in the depth feed — see the timezone caveat in the findings doc).
ET_ZONE = ZoneInfo("America/New_York")
UTC = timezone.utc

_MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
           "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}

CRYPTO_FAMILIES = ("KXBTC", "KXETH")

# category rollup (documented; the FAMILY axis carries the fine detail). Anything unmapped falls
# to "sports_other" — NEVER silently dropped. Crypto families -> "crypto".
SUBCATEGORY_MAP: Dict[str, str] = {
    # soccer
    "KXBRASILEIROGAME": "soccer", "KXBRASILEIROBGAME": "soccer", "KXBRASILEIROCGAME": "soccer",
    "KXUCLGAME": "soccer", "KXUELGAME": "soccer", "KXUECLGAME": "soccer", "KXECULPGAME": "soccer",
    "KXMLSGAME": "soccer", "KXCHNSLGAME": "soccer", "KXUSLGAME": "soccer", "KXUSLCUPGAME": "soccer",
    "KXNWSLGAME": "soccer", "KXURYPDGAME": "soccer", "KXELITESERIENGAME": "soccer",
    "KXALLSVENSKANGAME": "soccer", "KXLIGAMXGAME": "soccer", "KXWCGAME": "soccer",
    "KXKLEAGUEGAME": "soccer",
    # baseball
    "KXMLBGAME": "baseball", "KXNPBGAME": "baseball", "KXKBOGAME": "baseball",
    # basketball
    "KXWNBAGAME": "basketball", "KXBIG3GAME": "basketball", "KXNZNBLGAME": "basketball",
    "KXBSNGAME": "basketball", "KXFIBAGAME": "basketball",
    # other (Aussie rules / volleyball / lacrosse etc.)
    "KXAFLGAME": "sports_other", "KXVBAGAME": "sports_other", "KXPLLGAME": "sports_other",
}

# ttc bucket edges (in seconds), documented for the verifier verbatim. ttc = close - captured.
TTC_BUCKETS = (">24h", "6-24h", "1-6h", "15-60m", "<15m", "post_close", "unparsed")
_FINE_ORDER = (">24h", "6-24h", "1-6h", "15-60m", "<15m")  # order for coarse-clamp reference

TURNOVER_FORMULA_DOC = (
    "For a consecutive same-ticker capture pair where the best PRICE on a side is UNCHANGED and "
    "size_prev>0: turnover = max(0, size_prev - size_now) / size_prev. Per side (yes_bid_side = "
    "top yes_bid; yes_ask_side = mirror = top no_bid). Snapshot-sampled at hourly cadence: "
    "intra-hour round-trips invisible (undercount); a best-price move resets/excludes the pair. "
    "A coarse observability proxy, NOT a fill rate. Anchors for orientation: 0.45% (S19 DEAD), "
    "2.5% (S14 wing)."
)


# --------------------------------------------------------------------------- #
# ticker close-time parser (the three confirmed grammars + honest 'unparsed')
# --------------------------------------------------------------------------- #
def family_of(ticker: str) -> str:
    """Series prefix = the family (e.g. KXBTC, KXAFLGAME)."""
    return ticker.split("-", 1)[0]


def category_of(family: str) -> str:
    """Domain rollup: crypto for KXBTC/KXETH; else the documented SUBCATEGORY_MAP; any unmapped
    sports family falls to 'sports_other' (never silently dropped)."""
    if family in CRYPTO_FAMILIES:
        return "crypto"
    return SUBCATEGORY_MAP.get(family, "sports_other")


def _parse_date_prefix(mid: str) -> Optional[Tuple[int, int, int]]:
    """`26JUL06` -> (2026, 7, 6). None if the leading 7 chars are not YYMMMDD."""
    m = re.match(r"^(\d{2})([A-Z]{3})(\d{2})", mid)
    if not m:
        return None
    yy, mon, dd = m.group(1), m.group(2), m.group(3)
    if mon not in _MONTHS:
        return None
    return (2000 + int(yy), _MONTHS[mon], int(dd))


def parse_ticker_close(ticker: str) -> Dict[str, Any]:
    """Parse a Kalshi depth ticker's close time from its grammar.

    Returns {"close_utc": datetime|None, "resolution": "fine"|"coarse"|"unparsed",
             "family": str, "is_crypto": bool}.

    Grammars (middle segment = ticker.split('-')[1]):
      crypto  KXBTC-26JUL0621-B71750 -> mid '26JUL0621' = YYMMMDD + HH(ET). close = D@HH:00 ET.
      sports  KXAFLGAME-26JUL160530SKSGEE-GEE -> mid = YYMMMDD + HHMM(UTC) + letters.
      sports  KXWCGAME-26JUL06USABEL-USA -> mid = YYMMMDD + letters (NO HHMM) => DAY-resolved
              only: resolution 'coarse', close = end-of-day D (23:59:59 UTC).
    A middle segment that fails the date regex (or crypto without exactly-2 trailing hour digits,
    or a sports segment whose leading 4 digits are not a valid HHMM) => resolution 'unparsed'."""
    family = family_of(ticker)
    is_crypto = family in CRYPTO_FAMILIES
    parts = ticker.split("-")
    if len(parts) < 2:
        return {"close_utc": None, "resolution": "unparsed", "family": family,
                "is_crypto": is_crypto}
    mid = parts[1]
    ymd = _parse_date_prefix(mid)
    if ymd is None:
        return {"close_utc": None, "resolution": "unparsed", "family": family,
                "is_crypto": is_crypto}
    year, month, day = ymd
    rest = mid[7:]

    if is_crypto:
        # exactly two trailing digits = settlement hour, interpreted in ET (see ET_ZONE note).
        if re.fullmatch(r"\d{2}", rest):
            hour = int(rest)
            if hour > 23:
                return {"close_utc": None, "resolution": "unparsed", "family": family,
                        "is_crypto": is_crypto}
            local = datetime(year, month, day, hour, 0, tzinfo=ET_ZONE)
            return {"close_utc": local.astimezone(UTC), "resolution": "fine",
                    "family": family, "is_crypto": is_crypto}
        return {"close_utc": None, "resolution": "unparsed", "family": family,
                "is_crypto": is_crypto}

    # sports: optional 4-digit HHMM (UTC per spec) immediately after date, before matchup letters
    m = re.match(r"^(\d{4})(?=[A-Z])", rest)
    if m:
        hhmm = m.group(1)
        hh, mm = int(hhmm[:2]), int(hhmm[2:])
        if hh <= 23 and mm <= 59:
            close = datetime(year, month, day, hh, mm, tzinfo=UTC)
            return {"close_utc": close, "resolution": "fine", "family": family,
                    "is_crypto": is_crypto}
        # 4 leading digits but not a valid HHMM -> fall back to day-resolved coarse
    # date-only (matchup letters follow the date, or empty rest): day-resolved => coarse
    close = datetime.combine(datetime(year, month, day).date(), time(23, 59, 59), tzinfo=UTC)
    return {"close_utc": close, "resolution": "coarse", "family": family, "is_crypto": is_crypto}


def ttc_bucket(close_utc: Optional[datetime], captured_utc: datetime,
               resolution: str) -> str:
    """Bucket ttc = close - captured. 'unparsed' if no close. Coarse (day-resolved) captures are
    clamped: they are NEVER placed in a sub-hour bucket they cannot honestly earn (<15m/15-60m
    are promoted to '1-6h'), because the true intra-day close time is unknown."""
    if resolution == "unparsed" or close_utc is None:
        return "unparsed"
    ttc = (close_utc - captured_utc).total_seconds()
    if ttc < 0:
        return "post_close"
    if ttc < 15 * 60:
        bucket = "<15m"
    elif ttc < 60 * 60:
        bucket = "15-60m"
    elif ttc < 6 * 3600:
        bucket = "1-6h"
    elif ttc < 24 * 3600:
        bucket = "6-24h"
    else:
        bucket = ">24h"
    if resolution == "coarse" and bucket in ("<15m", "15-60m"):
        return "1-6h"  # coarse-clamp: cannot claim sub-hour precision on a day-resolved close
    return bucket


# --------------------------------------------------------------------------- #
# per-capture primitives
# --------------------------------------------------------------------------- #
def ask_side_size(rec: Dict[str, Any]) -> float:
    """Contracts resting AT the best YES ask = top of the NO-bid ladder (mirror: a YES offer at
    p is a NO bid at 1-p). 0.0 when the no-bid side is empty (a one-sided wing, L23 — empty !=
    drop). Same primitive as s20's `_ask_side_depth`."""
    nb = rec.get("no_bids") or []
    if not nb:
        return 0.0
    try:
        return float(nb[0][1])
    except (IndexError, TypeError, ValueError):
        return 0.0


def bid_side_size(rec: Dict[str, Any]) -> float:
    """Contracts resting at the best YES bid = top of the yes-bid ladder. 0.0 if empty."""
    yb = rec.get("yes_bids") or []
    if not yb:
        return 0.0
    try:
        return float(yb[0][1])
    except (IndexError, TypeError, ValueError):
        return 0.0


def _top_price(ladder: Any) -> Optional[float]:
    if not ladder:
        return None
    try:
        return float(ladder[0][0])
    except (IndexError, TypeError, ValueError):
        return None


def bbo_tuple(rec: Dict[str, Any]) -> Tuple[Any, Any, Any, Any]:
    """The full BBO 4-tuple whose invariance across a consecutive pair defines 'frozen' (L32)."""
    return (rec.get("best_yes_bid"), rec.get("best_yes_ask"),
            rec.get("best_no_bid"), rec.get("best_no_ask"))


def one_sided_flags(rec: Dict[str, Any]) -> Tuple[bool, bool]:
    """(yes_side_empty, no_side_empty). yes_side_empty: no resting YES bid (no yes_bids, or
    best_yes_bid None/0). no_side_empty: no resting mirror for the YES ask (no no_bids, or
    best_no_bid None/0) => no tradeable YES ask on that book."""
    yb = rec.get("yes_bids") or []
    nb = rec.get("no_bids") or []
    byb = rec.get("best_yes_bid")
    bnb = rec.get("best_no_bid")
    yes_empty = (not yb) or byb is None or byb == 0
    no_empty = (not nb) or bnb is None or bnb == 0
    return (bool(yes_empty), bool(no_empty))


# --------------------------------------------------------------------------- #
# small stats helpers (pure; no numpy)
# --------------------------------------------------------------------------- #
def _percentile(xs: List[float], q: float) -> float:
    """Linear-interpolation percentile (q in [0,1]) over a non-empty list."""
    s = sorted(xs)
    if not s:
        return float("nan")
    if len(s) == 1:
        return float(s[0])
    idx = q * (len(s) - 1)
    lo = int(idx)
    frac = idx - lo
    if lo + 1 >= len(s):
        return float(s[-1])
    return float(s[lo] + (s[lo + 1] - s[lo]) * frac)


def _median(xs: List[float]) -> float:
    return _percentile(xs, 0.5)


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only — L25/L29 skip stray dt=<date> DIRECTORIES)
# --------------------------------------------------------------------------- #
def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def iter_depth_records(depth_dir: Path):
    """Yield every depth record. FILES only — a stray `dt=<date>` DIRECTORY (L25/L29 regression)
    is skipped by the is_file guard, never crashed on. Never mutates tape."""
    for path in sorted(depth_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


# --------------------------------------------------------------------------- #
# accumulation
# --------------------------------------------------------------------------- #
class CellAgg:
    """Per-cell accumulator (a cell is one (scope, name, ttc_bucket) key)."""
    __slots__ = ("bid_sizes", "ask_sizes", "n_cap", "yes_empty", "no_empty", "any_empty",
                 "frozen", "n_pairs", "turn_bid", "turn_ask")

    def __init__(self) -> None:
        self.bid_sizes: List[float] = []
        self.ask_sizes: List[float] = []
        self.n_cap = 0
        self.yes_empty = 0
        self.no_empty = 0
        self.any_empty = 0
        self.frozen = 0
        self.n_pairs = 0
        self.turn_bid: List[float] = []
        self.turn_ask: List[float] = []


def _cell_summary(c: CellAgg) -> Dict[str, Any]:
    """Reduce one accumulator to its reported cell payload, honoring the MIN_N insufficient gate
    separately for capture-based (n_cap) and pair-based (n_pairs) metrics."""
    out: Dict[str, Any] = {"n_captures": c.n_cap, "n_pairs": c.n_pairs}
    if c.n_cap >= MIN_N:
        out["queue_depth"] = {
            "yes_bid_side": {"median": _median(c.bid_sizes), "p25": _percentile(c.bid_sizes, 0.25),
                             "p75": _percentile(c.bid_sizes, 0.75)},
            "yes_ask_side_mirror": {"median": _median(c.ask_sizes),
                                    "p25": _percentile(c.ask_sizes, 0.25),
                                    "p75": _percentile(c.ask_sizes, 0.75)},
        }
        out["one_sided"] = {
            "yes_side_empty": c.yes_empty / c.n_cap,
            "no_side_empty": c.no_empty / c.n_cap,
            "any_side_empty": c.any_empty / c.n_cap,
        }
    else:
        out["queue_depth"] = "insufficient"
        out["one_sided"] = "insufficient"

    if c.n_pairs >= MIN_N:
        out["staleness"] = {"frozen_pair_fraction": c.frozen / c.n_pairs, "n_pairs": c.n_pairs}
    else:
        out["staleness"] = "insufficient"

    n_tb, n_ta = len(c.turn_bid), len(c.turn_ask)
    pooled = c.turn_bid + c.turn_ask
    turnover: Dict[str, Any] = {}
    turnover["yes_bid_side"] = ({"mean_turnover": _mean(c.turn_bid), "n_pairs": n_tb}
                                if n_tb >= MIN_N else "insufficient")
    turnover["yes_ask_side_mirror"] = ({"mean_turnover": _mean(c.turn_ask), "n_pairs": n_ta}
                                       if n_ta >= MIN_N else "insufficient")
    turnover["pooled"] = ({"mean_turnover": _mean(pooled), "n_pairs": len(pooled)}
                          if len(pooled) >= MIN_N else "insufficient")
    out["turnover"] = turnover
    return out


def scan(depth_dir: Path = DEPTH_DIR) -> Dict[str, Any]:
    """Single read-only pass. Accumulates capture-based metrics directly and buffers per-ticker
    ordered records for the pair-based (staleness/turnover) and streak metrics."""
    # cells keyed by (scope, name, ttc): scope in {"family","category"}; plus per-scope "_ALL".
    cells: Dict[Tuple[str, str, str], CellAgg] = defaultdict(CellAgg)
    # per-ticker buffer for pair/streak passes
    by_ticker: Dict[str, List[Tuple[float, Tuple, float, float, Optional[float],
                                     Optional[float], str, str, str]]] = defaultdict(list)
    # streak length lists per family / per category
    streaks_family: Dict[str, List[int]] = defaultdict(list)
    streaks_category: Dict[str, List[int]] = defaultdict(list)

    n_records = 0
    family_ncap: Dict[str, int] = defaultdict(int)
    category_ncap: Dict[str, int] = defaultdict(int)
    family_ntickers: Dict[str, set] = defaultdict(set)
    unparsed_tickers: set = set()

    for rec in iter_depth_records(depth_dir):
        tk = rec.get("ticker", "")
        cap = rec.get("captured_at")
        if not tk or not cap:
            continue
        n_records += 1
        parsed = parse_ticker_close(tk)
        fam = parsed["family"]
        cat = category_of(fam)
        captured_dt = _parse_ts(cap)
        bucket = ttc_bucket(parsed["close_utc"], captured_dt, parsed["resolution"])
        if bucket == "unparsed":
            unparsed_tickers.add(fam)

        bsz = bid_side_size(rec)
        asz = ask_side_size(rec)
        yes_e, no_e = one_sided_flags(rec)
        any_e = yes_e or no_e

        for scope, name in (("family", fam), ("category", cat)):
            for key in ((scope, name, bucket), (scope, name, "_ALL")):
                c = cells[key]
                c.bid_sizes.append(bsz)
                c.ask_sizes.append(asz)
                c.n_cap += 1
                c.yes_empty += int(yes_e)
                c.no_empty += int(no_e)
                c.any_empty += int(any_e)

        family_ncap[fam] += 1
        category_ncap[cat] += 1
        family_ntickers[fam].add(tk)

        bid_price = _top_price(rec.get("yes_bids"))
        ask_price = _top_price(rec.get("no_bids"))
        by_ticker[tk].append((captured_dt.timestamp(), bbo_tuple(rec), bsz, asz,
                              bid_price, ask_price, fam, cat, bucket))

    # ---- pair-based + streak pass (per ticker, ordered by captured_at across ALL days) ------- #
    for tk, obs in by_ticker.items():
        obs.sort(key=lambda t: t[0])
        # streak runs of unchanged BBO
        run_len = 1
        for i in range(1, len(obs)):
            prev, cur = obs[i - 1], obs[i]
            frozen = (prev[1] == cur[1])
            # assign the pair to the EARLIER capture's cell (the resting state we ask 'did it
            # move?'); documented choice.
            fam, cat, bucket = prev[6], prev[7], prev[8]
            for scope, name in (("family", fam), ("category", cat)):
                for key in ((scope, name, bucket), (scope, name, "_ALL")):
                    c = cells[key]
                    c.n_pairs += 1
                    if frozen:
                        c.frozen += 1
            # turnover per side, only where the best PRICE on that side is unchanged & size_prev>0
            # yes_bid side
            if prev[4] is not None and cur[4] is not None and prev[4] == cur[4] and prev[2] > 0:
                tb = max(0.0, prev[2] - cur[2]) / prev[2]
                for scope, name in (("family", fam), ("category", cat)):
                    for key in ((scope, name, bucket), (scope, name, "_ALL")):
                        cells[key].turn_bid.append(tb)
            # yes_ask side (mirror)
            if prev[5] is not None and cur[5] is not None and prev[5] == cur[5] and prev[3] > 0:
                ta = max(0.0, prev[3] - cur[3]) / prev[3]
                for scope, name in (("family", fam), ("category", cat)):
                    for key in ((scope, name, bucket), (scope, name, "_ALL")):
                        cells[key].turn_ask.append(ta)
            # streak accounting
            if frozen:
                run_len += 1
            else:
                streaks_family[obs[i - 1][6]].append(run_len)
                streaks_category[obs[i - 1][7]].append(run_len)
                run_len = 1
        if obs:
            streaks_family[obs[-1][6]].append(run_len)
            streaks_category[obs[-1][7]].append(run_len)

    return {
        "cells": cells,
        "streaks_family": streaks_family,
        "streaks_category": streaks_category,
        "n_records": n_records,
        "family_ncap": dict(family_ncap),
        "category_ncap": dict(category_ncap),
        "family_ntickers": {f: len(s) for f, s in family_ntickers.items()},
        "unparsed_tickers": sorted(unparsed_tickers),
    }


def _streak_summary(runs: List[int]) -> Any:
    if len(runs) < MIN_N:
        return "insufficient"
    return {"n_runs": len(runs), "median_run": _median([float(x) for x in runs]),
            "p90_run": _percentile([float(x) for x in runs], 0.90), "max_run": max(runs)}


def build_report(scan_out: Dict[str, Any]) -> Dict[str, Any]:
    cells: Dict[Tuple[str, str, str], CellAgg] = scan_out["cells"]
    # organize into family cells and category cells
    by_family: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"category": None, "n_captures": 0, "n_tickers": 0, "cells": {},
                 "streak_distribution": None})
    by_category: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {"n_captures": 0, "cells": {}, "streak_distribution": None})

    for (scope, name, bucket), agg in cells.items():
        summ = _cell_summary(agg)
        if scope == "family":
            fam = by_family[name]
            fam["category"] = category_of(name)
            if bucket == "_ALL":
                fam["n_captures"] = agg.n_cap
                fam["n_tickers"] = scan_out["family_ntickers"].get(name, 0)
                fam["all_ttc"] = summ
            else:
                fam["cells"][bucket] = summ
        else:
            cat = by_category[name]
            if bucket == "_ALL":
                cat["n_captures"] = agg.n_cap
                cat["all_ttc"] = summ
            else:
                cat["cells"][bucket] = summ

    for fam, d in by_family.items():
        d["streak_distribution"] = _streak_summary(scan_out["streaks_family"].get(fam, []))
    for cat, d in by_category.items():
        d["streak_distribution"] = _streak_summary(scan_out["streaks_category"].get(cat, []))

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "scope": "READ-ONLY discovery-class depth-tape anatomy (Q25). Descriptive only — "
                 "NO bootstrap, NO CI, NO verdict, NO P&L, NO registry flip.",
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
        "n_records": scan_out["n_records"],
        "min_n_insufficient_threshold": MIN_N,
        "anchors": {"s19_queue_aware_fill_rate": ANCHOR_S19_FILL,
                    "s14_incidental_wing_fill_rate": ANCHOR_S14_WING,
                    "note": "fill-rate anchors cited for orientation ONLY; turnover is a looser "
                            "observability proxy, not the fill rate — it can rule a cell OUT "
                            "(dead-thin), never rule one IN as fillable."},
        "definitions": {
            "family": "series prefix, ticker.split('-')[0]",
            "category": "crypto (KXBTC/KXETH) | soccer | baseball | basketball | sports_other "
                        "(any unmapped sports family). See SUBCATEGORY_MAP.",
            "ttc_buckets": {
                ">24h": "ttc >= 24h", "6-24h": "6h <= ttc < 24h", "1-6h": "1h <= ttc < 6h",
                "15-60m": "15m <= ttc < 60m", "<15m": "0 <= ttc < 15m",
                "post_close": "ttc < 0 (late capture of a settled/closing market)",
                "unparsed": "middle segment failed the grammar",
                "coarse_clamp": "day-resolved (date-only) closes are never placed in <15m or "
                                "15-60m; those are promoted to 1-6h (unknown intra-day time).",
                "crypto_timezone": "crypto hour token is ET (EDT/UTC-4 in July), confirmed "
                                   "against tape + crypto_hourly.py; sports HHMM treated as UTC "
                                   "per spec (true tz is league-local, unverifiable from tape).",
            },
            "queue_depth": "per capture: yes_bid_side = yes_bids[0][1]; yes_ask_side_mirror = "
                           "no_bids[0][1] (a YES offer at p is a NO bid at 1-p). Median+p25/p75.",
            "staleness": "consecutive same-ticker pair (ordered by captured_at across all days) "
                         "with UNCHANGED BBO 4-tuple = frozen (L32). frozen_pair_fraction + a "
                         "family/category streak-length distribution. Hourly-cadence caveat: a "
                         "frozen hourly pair is not proof of no intra-hour movement.",
            "one_sided": "yes_side_empty (no yes_bids), no_side_empty (no no_bids => no "
                         "tradeable YES ask), any_side_empty (L31 wing shape).",
            "turnover_formula": TURNOVER_FORMULA_DOC,
            "pair_assignment": "staleness/turnover pairs assigned to the EARLIER capture's cell.",
        },
        "families": dict(sorted(by_family.items(), key=lambda kv: -kv[1]["n_captures"])),
        "categories": dict(sorted(by_category.items(), key=lambda kv: -kv[1]["n_captures"])),
        "coverage": {
            "families_with_unparsed_captures": scan_out["unparsed_tickers"],
            "n_families": len(by_family),
        },
    }


# --------------------------------------------------------------------------- #
# printing
# --------------------------------------------------------------------------- #
def _fmt_depth(cell: Any, side: str) -> str:
    if cell == "insufficient" or not isinstance(cell, dict):
        return "insuf"
    qd = cell.get("queue_depth")
    if qd == "insufficient" or not isinstance(qd, dict):
        return "insuf"
    return f"{qd[side]['median']:.0f}"


def _fmt_frozen(cell: Any) -> str:
    if not isinstance(cell, dict):
        return "insuf"
    s = cell.get("staleness")
    if s == "insufficient" or not isinstance(s, dict):
        return "insuf"
    return f"{s['frozen_pair_fraction']:.0%}"


def _fmt_turn(cell: Any) -> str:
    if not isinstance(cell, dict):
        return "insuf"
    t = cell.get("turnover", {}).get("pooled")
    if t == "insufficient" or not isinstance(t, dict):
        return "insuf"
    return f"{t['mean_turnover']:.2%}"


def _fmt_empty(cell: Any) -> str:
    if not isinstance(cell, dict):
        return "insuf"
    o = cell.get("one_sided")
    if o == "insufficient" or not isinstance(o, dict):
        return "insuf"
    return f"{o['any_side_empty']:.0%}"


def print_summary(report: Dict[str, Any]) -> None:
    print("=" * 100)
    print("Q25 — DEPTH-TAPE ANATOMY (read-only, discovery-class; descriptive only, NO verdict)")
    print("=" * 100)
    print(f"records scanned: {report['n_records']}   families: {report['coverage']['n_families']}"
          f"   insufficient threshold: <{report['min_n_insufficient_threshold']} captures/pairs")
    print(f"source tags: asks=real_ask bids=real_bid   anchors: S19 fill 0.45%  S14 wing 2.5%")
    print(f"crypto hour token = ET (confirmed); sports HHMM = UTC (spec, league-tz caveat)")

    # per-family table (all-ttc pooled)
    print("-" * 100)
    print("PER FAMILY (all ttc pooled):")
    print(f"  {'family':<20}{'cat':<12}{'n_cap':>7}{'n_tk':>6}  "
          f"{'bidQ':>9}{'askQ':>9}  {'frozen':>7}{'turn':>7}{'empty':>7}  streak(med/p90/max)")
    for fam, d in report["families"].items():
        allc = d.get("all_ttc", {})
        sk = d.get("streak_distribution")
        skf = (f"{sk['median_run']:.0f}/{sk['p90_run']:.0f}/{sk['max_run']}"
               if isinstance(sk, dict) else "insuf")
        print(f"  {fam:<20}{str(d['category']):<12}{d['n_captures']:>7}{d['n_tickers']:>6}  "
              f"{_fmt_depth(allc,'yes_bid_side'):>9}{_fmt_depth(allc,'yes_ask_side_mirror'):>9}  "
              f"{_fmt_frozen(allc):>7}{_fmt_turn(allc):>7}{_fmt_empty(allc):>7}  {skf}")

    # category x ttc
    print("-" * 100)
    print("CATEGORY x TTC-BUCKET (bidQ/askQ median, frozen%, turnover pooled, any-empty%):")
    order = [b for b in TTC_BUCKETS]
    for cat, d in report["categories"].items():
        print(f"  [{cat}]  n_captures(all)={d['n_captures']}")
        print(f"    {'ttc':<12}{'n_cap':>7}{'bidQ':>9}{'askQ':>9}{'frozen':>8}"
              f"{'turn':>8}{'empty':>8}")
        for b in order:
            cell = d["cells"].get(b)
            if cell is None:
                continue
            print(f"    {b:<12}{cell['n_captures']:>7}{_fmt_depth(cell,'yes_bid_side'):>9}"
                  f"{_fmt_depth(cell,'yes_ask_side_mirror'):>9}{_fmt_frozen(cell):>8}"
                  f"{_fmt_turn(cell):>8}{_fmt_empty(cell):>8}")
    print("-" * 100)
    print("READING: turnover < 0.45% (S19-dead anchor) => dead-thin; > 2.5% (S14 wing) => "
          "plausibly-fillable churn. Turnover only rules cells OUT, never IN. Descriptive map "
          "to seed idea-gen; NOT a verdict, NOT a registry flip.")
    print("=" * 100)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Q25 depth-tape anatomy (read-only, descriptive)")
    ap.add_argument("--depth-dir", default=str(DEPTH_DIR))
    ap.add_argument("--json-out", default=str(DEFAULT_JSON_OUT))
    ap.add_argument("--no-json", action="store_true", help="skip writing the JSON artifact")
    args = ap.parse_args(argv)

    scan_out = scan(Path(args.depth_dir))
    report = build_report(scan_out)
    print_summary(report)

    if not args.no_json:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"[q25] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

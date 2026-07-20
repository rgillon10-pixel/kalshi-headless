#!/usr/bin/env python3
"""q43_perp_binary_consistency_probe.py — Q43: same-venue crypto binary-vs-perp consistency /
lead-lag (read-only, PREP infrastructure — NOT a verdict).

LOOP-QUEUE.md Q43 (added 2026-07-17). Kalshi's crypto PERP is a delta-1, deep (2-4bps spread),
same-venue, near-same-benchmark real-time price for exactly the underlying that Kalshi's crypto
BINARY ladders (`tape/crypto_hourly/`) settle on. Same-venue kills the two objections that made
the old external crypto latency arb DEAD (offshore fee + oracle basis): the reference leg now
lives ON Kalshi against the same CF-benchmark family, its BBO is on our own tape. IF the binary
ladders are priced by retail while the perp is priced by flow-arbitrageurs, the perp is a free
fair-value oracle for the binaries.

── STATUS: PROBE-PREP, NOT A VERDICT (idle-run policy (b), mirrors q32/q36) ────────────────────
Q43 is GATED on >=7 days of `tape/perp_tape/` forward coverage. As of 2026-07-20 only 4
file-shaped days exist (dt=2026-07-17..2026-07-20), so the live analysis MUST NOT run yet. This
script is built + offline-tested now so it fires the day the gate opens. Below the gate it prints
an honest INSUFFICIENT DATA banner (with the current day count) and exits 0 — it NEVER fabricates
a bootstrap / CI / verdict from too-few days, writes NO findings/ entry, and touches NO registry.
The two analysis legs run live only when `_perp_days_available() >= PERP_DAYS_REQUIRED`; until
then they are exercised solely by the offline tests against injected synthetic fixtures.

── THE TWO ANALYSIS LEGS ──────────────────────────────────────────────────────────────────────
(1) LEAD-LAG. At the shared (hourly-ish) capture cadence, per MARKET-HOUR (== binary
    `event_ticker`, the L6 block unit), build the consecutive-diff series of the PERP-implied
    underlying level (perp BBO mid / contract_size — a `real_ask`/`real_bid` mid, a derived
    fair, never quoted as a fill) and the BINARY-implied underlying level (a probability-weighted
    mean of the ladder's `between` member coords, `synthetic`). Cross-correlate: contemporaneous
    rho, perp-leads (perp change[t-1] vs binary change[t]) and binary-leads (binary change[t-1]
    vs perp change[t]). MANDATORY per L57: alongside every raw rho, report the LEAVE-ONE-OUT
    recompute (drop the single lag-pair that most reduces |rho|) so a single-shock tick cannot
    masquerade as a persistent lead. Block-bootstrap by market-hour IF/when a CI is ever computed
    (not here — this is prep).

(2) COHERENCE AT REAL ASKS. Near-expiry (ttc <= NEAR_EXPIRY_SECONDS) binary members whose
    `real_ask` is inconsistent with the perp-implied distance-to-strike: a member the perp says
    is near-CERTAIN (perp-implied underlying strictly inside a `between` bracket by >= one strike
    spacing) whose YES `real_ask` is cheap enough that 1 - ask - fee > 0, or a member the perp
    says is near-IMPOSSIBLE (implied strictly outside by >= one spacing) whose NO `real_ask` is
    similarly cheap. Counted ONLY when the violation clears BOTH (a) the full fee floor
    (`core.pricing.fee_per_contract` — NEVER a hand-rolled rate) AND (b) the 10-contract depth
    floor at the touched price. The BINDING test is the DEPTH x DURATION joint distribution in
    WALL-CLOCK SECONDS (L76/L93), via `core.bootstrap.collapse_duration_gated_runs`: a large but
    sub-second dislocation is NOT fillable. NB: `tape/crypto_hourly/` carries NO at-touch size,
    so binary depth must be joined from `tape/orderbook_depth/` when the gate opens; until a
    member carries a numeric `yes_ask_depth`/`no_ask_depth`, its violation is DEPTH-UNMEASURABLE
    and EXCLUDED (never assumed fillable) — the honest pt1 discipline (Hard Rule #1/#3).

── HARD DISCIPLINE ────────────────────────────────────────────────────────────────────────────
Read-only over tape. `real_ask`/`real_bid` tags only for fillable prices; `broker_truth` for the
perp mark/settlement. A synthetic/derived number (perp-implied underlying, binary-implied level,
a perp-implied fair) is NEVER quoted as a fill. Fees ONLY from `core.pricing.fee_per_contract`.
The joinable underlying set is the intersection of the perp's 13 symbols and the binaries'
{BTC, ETH}. Crypto hour token is ET — `core.timeutil.parse_crypto_hour_token_close_utc`, never
re-derived (L45/L49). Strike spacing off the ladder via `core.pricing.ladder_spacing` (L7/L36).

Run:
    python scripts/q43_perp_binary_consistency_probe.py
    python scripts/q43_perp_binary_consistency_probe.py --perp-dir tape/perp_tape \
        --crypto-dir tape/crypto_hourly --json-out /tmp/q43.json
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import collapse_duration_gated_runs  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import fee_per_contract, ladder_spacing, normalized_ask  # noqa: E402
from core.timeutil import parse_crypto_hour_token_close_utc  # noqa: E402

PERP_GLOB = str(REPO_ROOT / "tape" / "perp_tape" / "dt=*.jsonl")
CRYPTO_GLOB = str(REPO_ROOT / "tape" / "crypto_hourly" / "dt=*.jsonl")

# ── the self-activation gate: Q43 is GATED on >=7 forward days of perp_tape coverage ──
PERP_DAYS_REQUIRED = 7

# ── binaries settle on BTC/ETH; the perp covers 13 symbols. Joinable set = the intersection. ──
BINARY_SYMBOLS = ("BTC", "ETH")

# ── modeling choices (documented; re-settle against the real leg when the gate opens) ──
MAX_JOIN_SKEW_SECONDS = 300.0     # a perp BBO within +/-5min counts as contemporaneous with a snap
NEAR_EXPIRY_SECONDS = 1800.0      # "near-expiry" = within 30min of the binary's close
MARGIN_SPACING_MULT = 1.0         # perp must be >= 1 strike spacing inside/outside to call certain
DEPTH_FLOOR = 10.0                # the 10-contract at-touch depth floor (contracts, float — L47)
DURATION_FLOOR_SECONDS = 60.0     # a dislocation must persist >= 60s wall-clock to be fillable
PRICE_TICK = 0.01


# --------------------------------------------------------------------------- #
# self-activation gate
# --------------------------------------------------------------------------- #
def _perp_days_available(perp_glob: str = PERP_GLOB) -> int:
    """Count of `dt=*.jsonl` day-files under the perp tape family. The whole live path is gated
    behind `>= PERP_DAYS_REQUIRED` of these — below it the probe prints INSUFFICIENT DATA and
    exits 0 rather than fabricate a bootstrap from too few days."""
    return len(glob.glob(perp_glob))


# --------------------------------------------------------------------------- #
# small parse helpers
# --------------------------------------------------------------------------- #
def _parse_iso(v: Any) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def perp_symbol_from_ticker(ticker: Any) -> Optional[str]:
    """`KXBTCPERP` -> `BTC`. None if the ticker doesn't match the `KX<SYM>PERP` grammar."""
    if not isinstance(ticker, str):
        return None
    if ticker.startswith("KX") and ticker.endswith("PERP") and len(ticker) > 6:
        return ticker[2:-4]
    return None


def hour_token_from_event(event_ticker: Any) -> Optional[str]:
    """Middle segment of a crypto-hourly event ticker (`KXBTC-26JUL1921` -> `26JUL1921`). None
    if there is no `-`-delimited middle segment."""
    if not isinstance(event_ticker, str):
        return None
    parts = event_ticker.split("-")
    if len(parts) < 2 or not parts[1]:
        return None
    return parts[1]


# --------------------------------------------------------------------------- #
# loaders (read-only)
# --------------------------------------------------------------------------- #
def load_perp_bbo(perp_glob: str = PERP_GLOB) -> List[Dict[str, Any]]:
    """Read every perp `markets` record's `contracts` list and emit one entry per joinable
    (BTC/ETH) symbol per capture: the BBO mid (`real_ask`/`real_bid`) and the perp-implied
    underlying level (mid / contract_size — a derived fair, NEVER a fill). Skips inactive /
    zero-quoted contracts. `mark` carries the `broker_truth` settlement mark for reference."""
    out: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(perp_glob)):
        for line in _iter_lines(path):
            rec = _loads(line)
            if rec is None or rec.get("record_type") != "markets":
                continue
            captured_at = _parse_iso(rec.get("captured_at"))
            for c in rec.get("contracts", []) or []:
                sym = perp_symbol_from_ticker(c.get("ticker"))
                if sym not in BINARY_SYMBOLS:
                    continue
                bid = _f(c.get("bid"))
                ask = _f(c.get("ask"))
                csize = _f(c.get("contract_size"))
                if bid is None or ask is None or csize in (None, 0.0):
                    continue
                if bid <= 0.0 or ask <= 0.0:  # inactive / one-sided placeholder
                    continue
                mid = (bid + ask) / 2.0
                mark = None
                smp = c.get("settlement_mark_price")
                if isinstance(smp, dict):
                    mark = _f(smp.get("price"))
                out.append({
                    "captured_at": captured_at,
                    "capture_id": rec.get("capture_id"),
                    "symbol": sym,
                    "bid": bid, "ask": ask, "mid": mid,
                    "contract_size": csize,
                    "implied_underlying": mid / csize,   # synthetic/derived — NOT a fill
                    "mark": mark,                        # broker_truth mark, reference only
                })
    return out


def _member_records(outcomes: Sequence[dict]) -> List[Dict[str, Any]]:
    """Normalize the ladder's `outcomes` into the fields this probe consumes, carrying optional
    at-touch depths (`yes_ask_depth`/`no_ask_depth`) if a future orderbook_depth join populated
    them. Absent depth stays None — a depth-unmeasurable member, never assumed fillable."""
    members: List[Dict[str, Any]] = []
    for o in outcomes or []:
        members.append({
            "ticker": o.get("ticker"),
            "strike_type": o.get("strike_type"),
            "floor_strike": _f(o.get("floor_strike")),
            "cap_strike": _f(o.get("cap_strike")),
            "yes_ask": _f(o.get("yes_ask")),
            "no_ask": _f(o.get("no_ask")),
            "yes_ask_depth": _f(o.get("yes_ask_depth")),
            "no_ask_depth": _f(o.get("no_ask_depth")),
        })
    return members


def load_binary_snapshots(crypto_glob: str = CRYPTO_GLOB) -> List[Dict[str, Any]]:
    """Read every crypto_hourly snapshot's `current` ladder and emit one record per capture with
    the BTC/ETH symbol, event_ticker, ET-correct UTC close (via
    `parse_crypto_hour_token_close_utc`, never re-derived), the `real_ask` member books, the
    ladder spacing (read off the ladder, never hardcoded), and the binary-implied underlying
    level (a probability-weighted `between`-coord mean, `synthetic`)."""
    out: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(crypto_glob)):
        for line in _iter_lines(path):
            rec = _loads(line)
            if rec is None:
                continue
            sym = rec.get("symbol")
            if sym not in BINARY_SYMBOLS:
                continue
            cur = rec.get("current") or {}
            event_ticker = cur.get("event_ticker")
            token = hour_token_from_event(event_ticker)
            close_utc = parse_crypto_hour_token_close_utc(token) if token else None
            members = _member_records(cur.get("outcomes") or [])
            spacing = ladder_spacing(cur.get("outcomes") or [])
            bracket_sum = _f(cur.get("bracket_sum"))
            out.append({
                "captured_at": _parse_iso(rec.get("captured_at")),
                "capture_id": rec.get("capture_id"),
                "symbol": sym,
                "event_ticker": event_ticker,
                "close_utc": close_utc,
                "bracket_sum": bracket_sum,
                "spacing": spacing,
                "members": members,
                "implied_level": binary_implied_level(members, bracket_sum),
            })
    return out


def _iter_lines(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line
    except OSError:
        return


def _loads(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


# --------------------------------------------------------------------------- #
# derived level (synthetic — never a fill)
# --------------------------------------------------------------------------- #
def binary_implied_level(members: Sequence[dict], bracket_sum: Optional[float]) -> Optional[float]:
    """Probability-weighted mean of the ladder's `between` member coordinates, weighting each
    member by its overround-normalized implied probability via `core.pricing.normalized_ask`
    (the sanctioned ask/bracket_sum divisor, Hard Rule #3 — never a raw ask). A `synthetic`
    estimate of where the ladder implies the underlying sits — NEVER a fill price. None if there
    is no usable `between` member with a positive normalized weight."""
    if not bracket_sum or bracket_sum <= 0:
        return None
    num = 0.0
    den = 0.0
    for m in members:
        if m.get("strike_type") != "between":
            continue
        fs, cs, ya = m.get("floor_strike"), m.get("cap_strike"), m.get("yes_ask")
        if fs is None or cs is None or ya is None:
            continue
        coord = (fs + cs) / 2.0
        w = normalized_ask(ya, bracket_sum)   # Hard Rule #3 — overround-normalized weight
        if w <= 0:
            continue
        num += w * coord
        den += w
    if den <= 0:
        return None
    return num / den


# --------------------------------------------------------------------------- #
# join — perp BBO <-> binary snapshot, nearest-in-time within skew, {BTC,ETH} intersection
# --------------------------------------------------------------------------- #
def join_snapshots(perp_bbo: List[Dict[str, Any]], binary_snaps: List[Dict[str, Any]], *,
                   max_skew_seconds: float = MAX_JOIN_SKEW_SECONDS
                   ) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Join each binary snapshot to the nearest perp BBO of the SAME symbol within
    `max_skew_seconds`. Returns (`joined_by_event`, meta). Only symbols present in BOTH families
    (the {BTC,ETH} intersection) can produce a joined record — a perp-only symbol (SOL, XRP, ...)
    has no binary ladder to join and is dropped, counted in meta."""
    perp_by_symbol: Dict[str, List[Dict[str, Any]]] = {}
    for p in perp_bbo:
        if p["captured_at"] is None:
            continue
        perp_by_symbol.setdefault(p["symbol"], []).append(p)
    for lst in perp_by_symbol.values():
        lst.sort(key=lambda r: r["captured_at"])

    perp_symbols = set(perp_by_symbol.keys())
    binary_symbols = {b["symbol"] for b in binary_snaps}
    joinable = perp_symbols & binary_symbols

    joined_by_event: Dict[str, List[Dict[str, Any]]] = {}
    n_joined = 0
    n_no_perp_symbol = 0
    n_no_perp_in_window = 0
    for b in binary_snaps:
        sym = b["symbol"]
        if sym not in joinable or b["captured_at"] is None:
            n_no_perp_symbol += 1
            continue
        match = _nearest_perp(perp_by_symbol.get(sym, []), b["captured_at"], max_skew_seconds)
        if match is None:
            n_no_perp_in_window += 1
            continue
        perp, skew = match
        ttc = None
        if b["close_utc"] is not None:
            ttc = (b["close_utc"] - b["captured_at"]).total_seconds()
        rec = {
            "symbol": sym,
            "event_ticker": b["event_ticker"],
            "captured_at": b["captured_at"],
            "close_utc": b["close_utc"],
            "ttc_seconds": ttc,
            "perp_implied": perp["implied_underlying"],
            "perp_skew_seconds": skew,
            "binary_level": b["implied_level"],
            "spacing": b["spacing"],
            "members": b["members"],
        }
        joined_by_event.setdefault(b["event_ticker"] or "?", []).append(rec)
        n_joined += 1
    for lst in joined_by_event.values():
        lst.sort(key=lambda r: r["captured_at"])
    meta = {
        "perp_symbols": sorted(perp_symbols),
        "binary_symbols": sorted(binary_symbols),
        "joinable_symbols": sorted(joinable),
        "n_joined": n_joined,
        "n_events": len(joined_by_event),
        "n_dropped_no_perp_symbol": n_no_perp_symbol,
        "n_dropped_no_perp_in_window": n_no_perp_in_window,
    }
    return joined_by_event, meta


def _nearest_perp(perps: List[Dict[str, Any]], target: datetime, max_skew: float
                  ) -> Optional[Tuple[Dict[str, Any], float]]:
    if not perps:
        return None
    best = min(perps, key=lambda p: abs((p["captured_at"] - target).total_seconds()))
    skew = abs((best["captured_at"] - target).total_seconds())
    if skew > max_skew:
        return None
    return best, skew


# --------------------------------------------------------------------------- #
# leg (1): lead-lag with mandatory leave-one-out (L57)
# --------------------------------------------------------------------------- #
def pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Pearson rho. None if < 3 points or either series has zero variance (an undefined
    correlation is honestly None, never a fabricated 0.0)."""
    n = len(xs)
    if n < 3 or len(ys) != n:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


def loo_min_abs_rho(xs: Sequence[float], ys: Sequence[float]) -> Tuple[Optional[int], Optional[float]]:
    """The L57 leave-one-out: drop each single pair, recompute rho, and return the
    (dropped_index, rho) that MINIMIZES |rho| — the recompute after removing the single most
    influential lag-pair. If dropping one point collapses rho toward 0, the "correlation" was a
    single-shock tick, not a persistent relationship. (None, None) if < 4 points (LOO would
    leave < 3, below pearson's floor)."""
    n = len(xs)
    if n < 4 or len(ys) != n:
        return None, None
    best_idx: Optional[int] = None
    best_rho: Optional[float] = None
    for i in range(n):
        rx = xs[:i] + xs[i + 1:] if isinstance(xs, list) else list(xs[:i]) + list(xs[i + 1:])
        ry = ys[:i] + ys[i + 1:] if isinstance(ys, list) else list(ys[:i]) + list(ys[i + 1:])
        r = pearson(rx, ry)
        if r is None:
            continue
        if best_rho is None or abs(r) < abs(best_rho):
            best_rho = r
            best_idx = i
    return best_idx, best_rho


def _change_pairs(joined_by_event: Dict[str, List[Dict[str, Any]]]
                  ) -> Dict[str, List[Tuple[float, float]]]:
    """Per event (== market-hour, the L6 block unit), consecutive-diff (perp_change,
    binary_change) pairs. Only consecutive snapshots where BOTH levels are present contribute."""
    pairs_by_event: Dict[str, List[Tuple[float, float]]] = {}
    for event, snaps in joined_by_event.items():
        seq: List[Tuple[float, float]] = []
        for a, b in zip(snaps, snaps[1:]):
            if (a["perp_implied"] is None or b["perp_implied"] is None
                    or a["binary_level"] is None or b["binary_level"] is None):
                continue
            seq.append((b["perp_implied"] - a["perp_implied"],
                        b["binary_level"] - a["binary_level"]))
        if seq:
            pairs_by_event[event] = seq
    return pairs_by_event


def lead_lag(joined_by_event: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Contemporaneous + lag±1 cross-correlation of perp vs binary level changes, each reported
    WITH its L57 leave-one-out recompute. `perp_leads` correlates perp change[t-1] with binary
    change[t] within an event's ordered sequence; `binary_leads` the mirror. All series pool
    across events (each event's own consecutive pairs); a within-event lag never spans two
    different market-hours."""
    pairs_by_event = _change_pairs(joined_by_event)

    contemp_x: List[float] = []
    contemp_y: List[float] = []
    perp_lead_x: List[float] = []   # perp change[t-1]
    perp_lead_y: List[float] = []   # binary change[t]
    bin_lead_x: List[float] = []    # binary change[t-1]
    bin_lead_y: List[float] = []    # perp change[t]
    for seq in pairs_by_event.values():
        for (pc, bc) in seq:
            contemp_x.append(pc)
            contemp_y.append(bc)
        for (a, b) in zip(seq, seq[1:]):
            perp_lead_x.append(a[0])   # perp change earlier
            perp_lead_y.append(b[1])   # binary change later
            bin_lead_x.append(a[1])    # binary change earlier
            bin_lead_y.append(b[0])    # perp change later

    def _dir(xs: List[float], ys: List[float]) -> Dict[str, Any]:
        rho = pearson(xs, ys)
        loo_idx, loo_rho = loo_min_abs_rho(xs, ys)
        return {"n": len(xs), "rho": rho, "loo_dropped_index": loo_idx, "loo_rho": loo_rho}

    contemp = _dir(contemp_x, contemp_y)
    perp_leads = _dir(perp_lead_x, perp_lead_y)
    binary_leads = _dir(bin_lead_x, bin_lead_y)

    # Which lead direction dominates on |rho| (headline only — both recomputes are always shown).
    def _abs(d: Dict[str, Any]) -> float:
        return abs(d["rho"]) if d["rho"] is not None else -1.0
    dominant = "perp_leads" if _abs(perp_leads) >= _abs(binary_leads) else "binary_leads"

    return {
        "n_events": len(pairs_by_event),
        "contemporaneous": contemp,
        "perp_leads": perp_leads,
        "binary_leads": binary_leads,
        "dominant_lead_direction": dominant,
    }


# --------------------------------------------------------------------------- #
# leg (2): coherence at real asks — fee floor + depth floor + DEPTH x DURATION gate
# --------------------------------------------------------------------------- #
def classify_member(member: Dict[str, Any], perp_implied: Optional[float],
                    spacing: Optional[float]) -> Optional[Dict[str, Any]]:
    """Classify one `between` member against the perp-implied underlying. Returns the fillable
    dislocation dict `{direction, price, depth, edge_after_fee}` when the perp says the member is
    near-CERTAIN (implied strictly inside the bracket by >= one spacing) and its YES `real_ask`
    is cheap enough that `1 - ask - fee > 0`, OR near-IMPOSSIBLE (implied strictly outside by >=
    one spacing) and its NO `real_ask` is similarly cheap. None otherwise. Edge is measured
    against the FEE FLOOR only here; the depth and duration gates are applied downstream. Fee is
    ALWAYS `core.pricing.fee_per_contract` (Hard Rule / no hand-rolled rate)."""
    if perp_implied is None or spacing is None or spacing <= 0:
        return None
    if member.get("strike_type") != "between":
        return None
    fs, cs = member.get("floor_strike"), member.get("cap_strike")
    if fs is None or cs is None:
        return None
    margin = MARGIN_SPACING_MULT * spacing
    inside = (perp_implied > fs + margin) and (perp_implied < cs - margin)
    outside = (perp_implied < fs - margin) or (perp_implied > cs + margin)

    if inside:
        ask = member.get("yes_ask")
        depth = member.get("yes_ask_depth")
        direction = "yes_in"
    elif outside:
        ask = member.get("no_ask")
        depth = member.get("no_ask_depth")
        direction = "no_out"
    else:
        return None
    if ask is None or not (0.0 < ask < 1.0):
        return None
    edge = 1.0 - ask - fee_per_contract(ask)
    if edge <= 0.0:   # fails the fee floor — not a violation
        return None
    return {"direction": direction, "price": ask, "depth": depth, "edge_after_fee": edge}


def build_coherence_runs(joined_by_event: Dict[str, List[Dict[str, Any]]], *,
                         near_expiry_seconds: float = NEAR_EXPIRY_SECONDS,
                         depth_floor: float = DEPTH_FLOOR,
                         duration_floor_seconds: float = DURATION_FLOOR_SECONDS
                         ) -> Dict[str, Any]:
    """Build the coherence dislocation runs and apply the binding DEPTH x DURATION gate in
    WALL-CLOCK SECONDS (L76/L93) via `core.bootstrap.collapse_duration_gated_runs`.

    For each event, restrict to near-expiry snapshots (ttc <= near_expiry_seconds), classify every
    member per snapshot, and build — per (event, member_ticker) — a time-ordered series of:
      is_hit  : a fee-clearing dislocation whose at-touch depth is measurable AND >= depth_floor
      seconds : wall-clock elapsed to the next near-expiry snapshot (0.0 for the last)
      depth   : the at-touch depth (a fee-clearing but depth-unmeasurable member is NOT a hit —
                depth None cannot clear the floor, never assumed fillable)
    then collapse into maximal runs; a run is `executable` only when its summed wall-clock
    duration >= duration_floor_seconds AND its min depth >= depth_floor. A sub-second burst,
    however large, is rejected. Returns counts + the executable run list."""
    n_snaps = 0
    n_fee_clearing = 0            # dislocations clearing the fee floor (pre depth/duration)
    n_depth_unmeasurable = 0     # fee-clearing but no at-touch size (crypto_hourly has none)
    n_depth_ok = 0               # fee-clearing AND depth >= floor
    # per (event, member_ticker): time-ordered snapshot rows
    series: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for event, snaps in joined_by_event.items():
        near = [s for s in snaps if s["ttc_seconds"] is not None
                and 0.0 <= s["ttc_seconds"] <= near_expiry_seconds]
        near.sort(key=lambda s: s["captured_at"])
        for idx, snap in enumerate(near):
            # wall-clock seconds attributed to this snapshot = gap to the next near-expiry snap
            if idx + 1 < len(near):
                secs = (near[idx + 1]["captured_at"] - snap["captured_at"]).total_seconds()
            else:
                secs = 0.0
            for m in snap["members"]:
                tkr = m.get("ticker")
                if tkr is None:
                    continue
                disloc = classify_member(m, snap["perp_implied"], snap["spacing"])
                key = (event, tkr)
                if disloc is None:
                    # a non-violating snapshot still advances the member's time series (a gap
                    # between two hits, so a run doesn't silently bridge a non-hit snapshot)
                    series.setdefault(key, []).append(
                        {"is_hit": False, "seconds": secs, "depth": 0.0})
                    continue
                n_snaps += 1
                n_fee_clearing += 1
                depth = disloc["depth"]
                if depth is None:
                    n_depth_unmeasurable += 1
                    is_hit = False
                    depth_val = 0.0
                elif depth >= depth_floor:
                    n_depth_ok += 1
                    is_hit = True
                    depth_val = depth
                else:
                    is_hit = False
                    depth_val = depth
                series.setdefault(key, []).append(
                    {"is_hit": is_hit, "seconds": secs, "depth": depth_val})

    executable_runs: List[Dict[str, Any]] = []
    n_runs_total = 0
    for (event, tkr), rows in series.items():
        runs = collapse_duration_gated_runs(
            [r["is_hit"] for r in rows],
            [r["seconds"] for r in rows],
            [r["depth"] for r in rows],
            min_duration_seconds=duration_floor_seconds,
            min_depth=depth_floor,
        )
        for run in runs:
            n_runs_total += 1
            if run["executable"]:
                executable_runs.append({"event": event, "member": tkr, **run})

    return {
        "n_fee_clearing_dislocations": n_fee_clearing,
        "n_depth_unmeasurable": n_depth_unmeasurable,
        "n_depth_ok": n_depth_ok,
        "n_runs_total": n_runs_total,
        "n_executable_runs": len(executable_runs),
        "executable_runs": executable_runs,
        "depth_floor": depth_floor,
        "duration_floor_seconds": duration_floor_seconds,
        "near_expiry_seconds": near_expiry_seconds,
    }


# --------------------------------------------------------------------------- #
# orchestration (gated)
# --------------------------------------------------------------------------- #
def run_probe(perp_glob: str = PERP_GLOB, crypto_glob: str = CRYPTO_GLOB) -> Dict[str, Any]:
    """End-to-end, read-only. Gated: below `PERP_DAYS_REQUIRED` forward days of perp_tape it
    returns an INSUFFICIENT DATA status and runs NO analysis (no bootstrap, no CI, no verdict)."""
    perp_days = _perp_days_available(perp_glob)
    report: Dict[str, Any] = {
        "perp_days_available": perp_days,
        "perp_days_required": PERP_DAYS_REQUIRED,
    }
    if perp_days < PERP_DAYS_REQUIRED:
        report["status"] = "INSUFFICIENT DATA"
        report["reason"] = (
            f"Q43 is gated on >= {PERP_DAYS_REQUIRED} forward days of tape/perp_tape/ coverage; "
            f"only {perp_days} day-file(s) present. Prep script — no analysis run, no verdict.")
        return report

    perp_bbo = load_perp_bbo(perp_glob)
    binary_snaps = load_binary_snapshots(crypto_glob)
    joined_by_event, join_meta = join_snapshots(perp_bbo, binary_snaps)

    report["status"] = "ANALYSIS"
    report["note"] = (
        "PREP-class descriptive analysis, NOT a verdict: lead-lag rho + coherence run counts are "
        "reported; a positive/negative call requires the block-bootstrap-by-market-hour CI, the "
        "tick-magnitude + admissibility gates, and the two-agent rule — none run here.")
    report["n_perp_bbo"] = len(perp_bbo)
    report["n_binary_snaps"] = len(binary_snaps)
    report["join_meta"] = join_meta
    report["lead_lag"] = lead_lag(joined_by_event)
    report["coherence"] = build_coherence_runs(joined_by_event)
    return report


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _fmt_rho(d: Dict[str, Any]) -> str:
    r = "None" if d["rho"] is None else f"{d['rho']:+.4f}"
    lr = "None" if d["loo_rho"] is None else f"{d['loo_rho']:+.4f}"
    return f"rho={r:>8}  LOO(drop-1)={lr:>8}  n={d['n']}"


def print_report(rep: Dict[str, Any]) -> None:
    print("=" * 90)
    print("Q43 SAME-VENUE CRYPTO BINARY-vs-PERP CONSISTENCY / LEAD-LAG  (prep; read-only)")
    print("=" * 90)
    print(f"perp_tape forward days: {rep['perp_days_available']} "
          f"(gate opens at {rep['perp_days_required']})")

    if rep.get("status") == "INSUFFICIENT DATA":
        print("\nINSUFFICIENT DATA — " + rep["reason"])
        print("Self-activating prep: this script fires the two analysis legs automatically the "
              "day the perp_tape gate opens. NO verdict, NO findings, NO registry change.")
        return

    jm = rep["join_meta"]
    print(f"\n{rep['note']}")
    print(f"perp BBO rows: {rep['n_perp_bbo']}   binary snapshots: {rep['n_binary_snaps']}")
    print(f"joinable symbols (perp ∩ binary): {jm['joinable_symbols']}  "
          f"(perp={jm['perp_symbols']}, binary={jm['binary_symbols']})")
    print(f"joined snapshots: {jm['n_joined']} across {jm['n_events']} market-hours  "
          f"(dropped: {jm['n_dropped_no_perp_symbol']} no-perp-symbol, "
          f"{jm['n_dropped_no_perp_in_window']} no-perp-in-window)")

    ll = rep["lead_lag"]
    print(f"\nLEAD-LAG (per market-hour, {ll['n_events']} events; L57 leave-one-out beside each rho)")
    print(f"  contemporaneous : {_fmt_rho(ll['contemporaneous'])}")
    print(f"  perp_leads      : {_fmt_rho(ll['perp_leads'])}")
    print(f"  binary_leads    : {_fmt_rho(ll['binary_leads'])}")
    print(f"  dominant lead direction (by |rho|): {ll['dominant_lead_direction']}")

    co = rep["coherence"]
    print(f"\nCOHERENCE (near-expiry <= {co['near_expiry_seconds']:.0f}s; depth floor "
          f"{co['depth_floor']:.0f}, duration floor {co['duration_floor_seconds']:.0f}s wall-clock)")
    print(f"  fee-clearing dislocations : {co['n_fee_clearing_dislocations']}")
    print(f"  depth-unmeasurable        : {co['n_depth_unmeasurable']} "
          f"(no at-touch size — needs orderbook_depth join)")
    print(f"  depth>=floor              : {co['n_depth_ok']}")
    print(f"  runs collapsed            : {co['n_runs_total']}")
    print(f"  EXECUTABLE (depth x duration cleared): {co['n_executable_runs']}")
    print("\n(prep only — no bootstrap CI, no tick/admissibility gate, no verdict here)")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q43 same-venue crypto binary-vs-perp consistency probe (prep; read-only)")
    ap.add_argument("--perp-dir", default=None,
                    help="dir holding tape/perp_tape dt=*.jsonl (default: committed tape)")
    ap.add_argument("--crypto-dir", default=None,
                    help="dir holding tape/crypto_hourly dt=*.jsonl (default: committed tape)")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    perp_glob = str(Path(args.perp_dir) / "dt=*.jsonl") if args.perp_dir else PERP_GLOB
    crypto_glob = str(Path(args.crypto_dir) / "dt=*.jsonl") if args.crypto_dir else CRYPTO_GLOB

    rep = run_probe(perp_glob, crypto_glob)
    print_report(rep)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"[q43] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

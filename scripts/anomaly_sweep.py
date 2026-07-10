#!/usr/bin/env python3
"""anomaly_sweep.py — LOOP-QUEUE.md Q6 (+ Q11): daily anomaly sweep over ALL active Kalshi
markets.

Three real-ask checks, mirroring capture_orderbooks/sports_pairs/crypto_hourly discipline
(bitemporal `captured_at`, raw-bytes sha256 provenance, honest completeness — a discovery
failure lowers `completeness_ok`, it never silently drops markets). All three checks flag
ONLY violations that clear the taker fee floor (core.pricing.fee_per_contract) — an
implied-probability curiosity is not the same as a real fillable arb, and this project's
prime directive is "prove edge at real asks", not at raw quotes.

  1. **bracket_arb** — a COMPLETE, mutually-exclusive-and-exhaustive strike ladder under one
     event_ticker (a "less" catch-all + contiguous "between" bands + a "greater" catch-all,
     the same shape Q2 found on KXBTC/KXETH) whose yes_asks sum to less than $1 net of the
     fee to buy every member: buying the whole ladder is then a guaranteed $1 payout for
     less than $1 (core.pricing.true_arb_edge). Only scored when the sorted segments
     bookend the full real line (-inf..+inf) with no gap/overlap wider than
     `_CONTIGUITY_TOL` — an event without both open-ended tails, or with a gap (a market
     already closed while its siblings are still open), can't prove exhaustiveness, so it's
     skipped, not guessed at. Binary yes/no markets and non-strike-typed groups (e.g. sports
     moneylines, which are exhaustive by construction without floor/cap fields) are out of
     scope for this check.
  2. **cross_strike_monotonicity** (S3) — for threshold-type ("greater"/"less") markets
     sharing an event_ticker, a narrower strike's YES-region is a subset of a wider strike's
     (e.g. temp>=80 subset of temp>=70), so P(narrower) can never exceed P(wider). The real
     (not just implied) arb needs both legs REAL-ask fillable: buy YES(wider) + NO(narrower)
     pays a guaranteed >=$1 (core.pricing.monotonicity_crossing_edge) whenever that costs
     less than $1 net of both legs' fees — an ask-vs-ask gap alone can be closed by an
     unfilled quote, a real cost-under-$1 hedge cannot.
  3. **cross_event_implication** (S15, Q11) — the same nested-subset idea as check 2, but
     across DIFFERENT event_tickers, per a hand-curated implication graph
     (`config/implication_pairs.yaml`, each family audited against both markets' actual
     settlement rules text before being added — a cross-event pair can't lean on "same
     event_ticker" the way check 2 does to prove nesting). A ⇒ B (A narrower/harder, B
     wider/easier, e.g. "reach FINAL" ⇒ "reach QUARTERFINALS" for the same World Cup team):
     buy YES(B) + NO(A), same `core.pricing.monotonicity_crossing_edge` fee-floor math as
     check 2.

Discovers via `/markets?status=open` with NO series/category filter — every active market
on the platform, per Q6's own wording. Confirmed live 2026-07-04: Kalshi's open-market
count runs into the tens of thousands (10,000+ inside the first 10 pages alone, cursor
still unexhausted) — a genuinely unbounded pass runs this sandbox out of memory before it
finishes, so `main()` defaults to `--limit DEFAULT_LIVE_LIMIT` (20,000 markets, a real
resource bound, not a scope judgment call) and every record honestly carries
`markets_truncated` so a capped pass never masquerades as full coverage. Pass `--limit 0`
for a genuinely unbounded run (e.g. from the VPS collector, more headroom).

Run one pass:
    python scripts/anomaly_sweep.py                # capped at DEFAULT_LIVE_LIMIT markets
    python scripts/anomaly_sweep.py --limit 0       # unbounded (needs more memory/time)
    python scripts/anomaly_sweep.py --limit 500     # offline/dev use
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum, fee_per_contract, monotonicity_crossing_edge, true_arb_edge
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "anomalies"
IMPLICATION_PAIRS_CONFIG = REPO_ROOT / "config" / "implication_pairs.yaml"

# Empirically observed Kalshi between-band tick gap (e.g. crypto's 50799.99 -> 50800.00,
# or an exact touch like 69299.99 -> 69299.99 between a "between" cap and a "greater"
# floor). A gap wider than this is treated as a real hole in the ladder, not a rounding
# artifact — erring toward skipping a group rather than trusting a false "complete" sum.
_CONTIGUITY_TOL = 0.02


# --------------------------------------------------------------------------- #
# discovery — every open market, platform-wide, one paginated raw-provenance pull
# --------------------------------------------------------------------------- #
def _fetch_all_open_markets_raw(client: Kalshi, limit: Optional[int] = None
                                ) -> Tuple[List[Dict[str, Any]], List[str], bool]:
    """Paginate every open market platform-wide. Kalshi's open-market count runs into the
    tens of thousands+ (confirmed live 2026-07-04: 10,000 markets inside the first 10 pages
    alone, cursor still unexhausted) — `limit` is a real memory/time bound for this sandbox,
    not an arbitrary cap, and its use is always reported (`markets_truncated`), never
    silently absorbed into a false "swept everything" claim."""
    markets: List[Dict[str, Any]] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    truncated = False
    while True:
        params: Dict[str, Any] = {"status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        text = client.get_text("/markets", **params)
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("markets") or []
        markets.extend(items)
        cursor = j.get("cursor")
        if not cursor or not items:
            break
        if limit and len(markets) >= limit:
            truncated = cursor is not None
            break
    if limit:
        markets = markets[:limit]
    return markets, raw_pages, truncated


def _group_by_event(markets: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for m in markets:
        et = m.get("event_ticker") or ""
        if et:
            groups[et].append(m)
    return groups


def _f(m: Dict[str, Any], key: str) -> Optional[float]:
    v = m.get(key)
    return float(v) if v is not None else None


# --------------------------------------------------------------------------- #
# check 1 — complete-ladder true arb (bracket sum vs $1 + fees)
# --------------------------------------------------------------------------- #
def _segment_bounds(m: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    st = m.get("strike_type")
    if st == "less":
        cap = _f(m, "cap_strike")
        return (float("-inf"), cap) if cap is not None else None
    if st == "greater":
        floor = _f(m, "floor_strike")
        return (floor, float("inf")) if floor is not None else None
    if st == "between":
        floor, cap = _f(m, "floor_strike"), _f(m, "cap_strike")
        return (floor, cap) if floor is not None and cap is not None else None
    return None


def check_bracket_arb(event_ticker: str, members: List[Dict[str, Any]]
                      ) -> Optional[Dict[str, Any]]:
    """None if the ladder can't be proven complete (missing bounds, no open-ended tails,
    or a gap/overlap past `_CONTIGUITY_TOL`) or shows no arb; else the flagged anomaly."""
    rows: List[Tuple[float, float, float, str]] = []
    for m in members:
        bounds = _segment_bounds(m)
        ask = _f(m, "yes_ask_dollars")
        if bounds is None or ask is None:
            return None
        rows.append((bounds[0], bounds[1], ask, m.get("ticker", "")))

    rows.sort(key=lambda r: r[0])
    if rows[0][0] != float("-inf") or rows[-1][1] != float("inf"):
        return None  # doesn't bookend the full real line -> can't prove exhaustive
    for (_, hi0, _, _), (lo1, _, _, _) in zip(rows, rows[1:]):
        if abs(hi0 - lo1) > _CONTIGUITY_TOL:
            return None  # gap or overlap -> not a provably complete partition

    asks = [r[2] for r in rows]
    bsum = bracket_sum(asks)
    total_fees = sum(fee_per_contract(a) for a in asks)
    edge = true_arb_edge(bsum, total_fees)
    if edge <= 0:
        return None
    return {
        "kind": "bracket_arb",
        "event_ticker": event_ticker,
        "member_count": len(rows),
        "bracket_sum": bsum,
        "total_fees": total_fees,
        "edge": edge,
        "tickers": [r[3] for r in rows],
        "price_source_tag": "real_ask",
    }


# --------------------------------------------------------------------------- #
# check 2 — cross-strike monotonicity (S3): real bid/ask-crossing arb only
# --------------------------------------------------------------------------- #
def check_monotonicity(event_ticker: str, members: List[Dict[str, Any]], strike_type: str
                       ) -> List[Dict[str, Any]]:
    rows: List[Tuple[float, float, float, str]] = []  # (order_key, yes_ask, no_ask, ticker)
    for m in members:
        key = _f(m, "floor_strike") if strike_type == "greater" else _f(m, "cap_strike")
        ask, no_ask = _f(m, "yes_ask_dollars"), _f(m, "no_ask_dollars")
        if key is None or ask is None or no_ask is None:
            continue
        rows.append((key, ask, no_ask, m.get("ticker", "")))
    if len(rows) < 2:
        return []
    rows.sort(key=lambda r: r[0])

    anomalies: List[Dict[str, Any]] = []
    n = len(rows)
    for i in range(n):
        for j in range(i + 1, n):
            if strike_type == "greater":
                # lower floor_strike = wider YES-region (outer); higher = narrower (inner)
                outer, inner = rows[i], rows[j]
            else:  # "less": lower cap_strike = narrower (inner); higher = wider (outer)
                inner, outer = rows[i], rows[j]
            outer_ask, inner_no_ask = outer[1], inner[2]
            edge = monotonicity_crossing_edge(outer_ask, inner_no_ask)
            if edge > 0:
                anomalies.append({
                    "kind": "cross_strike_monotonicity",
                    "event_ticker": event_ticker,
                    "strike_type": strike_type,
                    "outer_ticker": outer[3], "inner_ticker": inner[3],
                    "outer_ask": outer_ask, "inner_no_ask": inner_no_ask,
                    "edge": edge,
                    "price_source_tag": "real_ask",
                })
    return anomalies


# --------------------------------------------------------------------------- #
# check 3 — cross-event logical implication (S15, Q11): hand-curated graph
# --------------------------------------------------------------------------- #
def load_implication_families(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load `config/implication_pairs.yaml`'s `families` list. Missing file/key -> no
    families (the check simply finds nothing to do, never an error — this config is
    additive curation, not a required input)."""
    path = path or IMPLICATION_PAIRS_CONFIG
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    return doc.get("families") or []


def _round_progression_pairs(markets: List[Dict[str, Any]], family: Dict[str, Any]
                             ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """From the currently discovered open markets, generate (market_a, market_b) pairs for
    one `kind: round_progression` family: A = harder/higher-rank round, B = easier/
    lower-rank round, same entity, per `family`'s audited round ordering. Ticker parse
    misses (wrong series, unknown round suffix) are skipped, not guessed at."""
    regex = re.compile(family["ticker_regex"])
    rank_map = family["round_order_raw_suffix_to_rank"]
    series = family["series"]

    entity_rounds: Dict[str, Dict[int, Dict[str, Any]]] = defaultdict(dict)
    for m in markets:
        ticker = m.get("ticker") or ""
        match = regex.match(ticker)
        if not match:
            continue
        fields = match.groupdict()
        if fields.get("series") != series:
            continue
        round_raw = fields.get("round_raw", "")
        suffix = re.sub(r"^\d+", "", round_raw)
        rank = rank_map.get(suffix)
        if rank is None:
            continue
        entity_rounds[fields["entity"]][rank] = m

    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for entity, by_rank in entity_rounds.items():
        ranks = sorted(by_rank)
        for i in range(len(ranks)):
            for j in range(i + 1, len(ranks)):
                rank_b, rank_a = ranks[i], ranks[j]  # b = easier/lower rank, a = harder
                pairs.append((by_rank[rank_a], by_rank[rank_b]))
    return pairs


def check_cross_event_implication(markets: List[Dict[str, Any]],
                                  families: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Check every family's generated (A, B) pairs, A ⇒ B, for a fee-clearing arb: buy
    YES(B) + NO(A) (core.pricing.monotonicity_crossing_edge — identical fee-floor math to
    check 2, just across two different event_tickers instead of one)."""
    anomalies: List[Dict[str, Any]] = []
    for family in families:
        if family.get("kind") != "round_progression":
            continue  # only kind implemented so far; unknown kinds skipped, not guessed at
        for market_a, market_b in _round_progression_pairs(markets, family):
            a_no_ask = _f(market_a, "no_ask_dollars")
            b_ask = _f(market_b, "yes_ask_dollars")
            if a_no_ask is None or b_ask is None:
                continue
            edge = monotonicity_crossing_edge(b_ask, a_no_ask)
            if edge > 0:
                anomalies.append({
                    "kind": "cross_event_implication",
                    "family_id": family.get("id"),
                    "a_ticker": market_a.get("ticker", ""),
                    "a_event_ticker": market_a.get("event_ticker", ""),
                    "b_ticker": market_b.get("ticker", ""),
                    "b_event_ticker": market_b.get("event_ticker", ""),
                    "a_no_ask": a_no_ask,
                    "b_ask": b_ask,
                    "edge": edge,
                    "price_source_tag": "real_ask",
                })
    return anomalies


# --------------------------------------------------------------------------- #
# sweep — one pass over every open event group
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, tape_dir: Optional[Path] = None,
        implication_families: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """One read-only anomaly sweep. `client`/`tape_dir`/`implication_families` injectable
    for offline testing."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if implication_families is None:
        implication_families = load_implication_families()
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    fetch_error: Optional[str] = None
    markets_truncated = False
    try:
        markets, raw_pages, markets_truncated = _fetch_all_open_markets_raw(client, limit=limit)
    except Exception as exc:
        markets, raw_pages, fetch_error = [], [], str(exc)

    groups = _group_by_event(markets)
    anomalies: List[Dict[str, Any]] = []
    n_bracket_groups_checked = 0
    n_monotonicity_groups_checked = 0

    for et, members in sorted(groups.items()):
        if len(members) < 2:
            continue
        by_type: Dict[Optional[str], List[Dict[str, Any]]] = defaultdict(list)
        for m in members:
            by_type[m.get("strike_type")].append(m)

        strike_typed = by_type.get("less", []) + by_type.get("between", []) + by_type.get("greater", [])
        if len(strike_typed) >= 2:
            n_bracket_groups_checked += 1
            hit = check_bracket_arb(et, strike_typed)
            if hit:
                anomalies.append(hit)

        for st in ("greater", "less"):
            grp = by_type.get(st, [])
            if len(grp) >= 2:
                n_monotonicity_groups_checked += 1
                anomalies.extend(check_monotonicity(et, grp, st))

    n_implication_pairs_checked = sum(
        len(_round_progression_pairs(markets, fam))
        for fam in implication_families if fam.get("kind") == "round_progression"
    )
    anomalies.extend(check_cross_event_implication(markets, implication_families))

    # fetch success (no exception) and full-coverage (no truncation) are DISTINCT honest
    # signals — a capped sweep isn't a fetch failure, but it isn't "swept everything"
    # either; both surface, neither is silently absorbed into the other.
    completeness_ok = fetch_error is None
    record = {
        "schema_version": "anomaly_sweep.v1",
        "capture_id": capture_id, "captured_at": captured_at, "venue": "kalshi",
        "n_markets_scanned": len(markets),
        "n_event_groups": len(groups),
        "n_bracket_groups_checked": n_bracket_groups_checked,
        "n_monotonicity_groups_checked": n_monotonicity_groups_checked,
        "n_implication_pairs_checked": n_implication_pairs_checked,
        "n_anomalies": len(anomalies),
        "anomalies": anomalies,
        "fetch_error": fetch_error,
        "markets_truncated": markets_truncated,
        "completeness_ok": completeness_ok,
        "raw_sha256": sha256_hex("".join(raw_pages).encode("utf-8")) if raw_pages else None,
    }

    tape_dir.mkdir(parents=True, exist_ok=True)
    out_path = tape_dir / f"dt={day}.jsonl"
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(canonical_json(record) + "\n")

    if markets_truncated:
        print(f"[anomaly_sweep] WARN swept only the first {len(markets)} open markets "
              f"(limit={limit}) — more were available (cursor unexhausted)", file=sys.stderr)
    print(f"[anomaly_sweep] {capture_id}: {len(markets)} markets scanned, "
          f"{len(groups)} event groups, {len(anomalies)} anomalies flagged, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}")

    return {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_markets_scanned": len(markets), "n_anomalies": len(anomalies),
        "markets_truncated": markets_truncated,
        "completeness_ok": completeness_ok, "path": str(out_path),
    }


# Kalshi's open-market count is far larger than a single research-loop pass can hold
# comfortably (confirmed live 2026-07-04: 10,000+ markets within the first 10 pages,
# cursor still unexhausted, RSS climbing unbounded past 3GB before this cap was added).
# This is a real memory/time bound for the cloud sandbox, not a scope judgment call —
# `markets_truncated` in every record says plainly when a pass didn't see everything.
# A larger/unbounded run (e.g. from the VPS collector, more headroom) can pass a bigger
# --limit or 0 (unlimited) explicitly.
DEFAULT_LIVE_LIMIT = 20000


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Daily anomaly sweep over all active markets (read-only)")
    ap.add_argument("--limit", type=int, default=DEFAULT_LIVE_LIMIT,
                    help=f"cap total markets fetched (default {DEFAULT_LIVE_LIMIT}; 0 = unlimited)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    limit = None if not args.limit else args.limit
    summary = run(limit=limit, min_interval=args.min_interval)
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

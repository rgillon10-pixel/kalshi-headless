"""V3 — Kalshi market-data validator.

Two subcommands:
  discover   enumerate live daily high/low temperature series + their settlement
             sources/fees, write the authoritative config/cities.yaml.
  validate   (default) parse every active temp-market ticker with a 100%-coverage
             gate, reconcile the parsed bucket against the API's structured strike
             fields, validate timestamp parsing, and capture FULL orderbook depth
             into the venue-agnostic schema with coherence checks.

The ticker grammar and orderbook shape here were derived empirically from the live
API (not assumed): tickers are `<SERIES>-<YYMMMDD>-<T|B><n>`; the orderbook arrives
under key `orderbook_fp` with fractional dollar-string prices/sizes. An old parser
keying on `orderbook`/integer-cents silently returns nothing — the 100%-coverage
gate is what catches that regression.

Run:
    python -m validation.v3_market discover
    python -m validation.v3_market validate
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import yaml

from core.io import CONFIG, REPO_ROOT, cache_path, utcnow_iso, write_report
from core.schema import BookLevel, MarketSpec, OrderbookSnapshot
from core.timeutil import parse_kalshi_ts

UA = {"User-Agent": "kalshi-weather-edge/0.0 (research-validation)"}
WEATHER_CATEGORY = "Climate and Weather"

# Empirically-derived modern grammar. Kept strict so drift FAILS loudly.
TICKER_RE = re.compile(r"^(?P<series>[A-Z0-9]+)-(?P<date>\d{2}[A-Z]{3}\d{2})-(?P<bucket>[TB]\d+(?:\.\d+)?)$")

# Series classification (daily high/low temperature ladders only).
_EXCLUDE = re.compile(r"hourly|directional|monthly|range|increase|united states|"
                      r"in cities|death valley|global", re.I)

# Kalshi temp tickers are KX(HIGH|LOW)T?<code>; codes are non-standard width and a
# city can appear under >1 code (NY and NYC are both New York). Derive a clean city
# from the code rather than Kalshi's inconsistent settlement_source strings.
CODE_TO_CITY = {
    "NY": "New York", "NYC": "New York", "LAX": "Los Angeles", "DEN": "Denver",
    "PHIL": "Philadelphia", "MIA": "Miami", "AUS": "Austin", "CHI": "Chicago",
    "ATL": "Atlanta", "BOS": "Boston", "DAL": "Dallas", "DC": "Washington DC",
    "HOU": "Houston", "LV": "Las Vegas", "MIN": "Minneapolis", "NOLA": "New Orleans",
    "OKC": "Oklahoma City", "PHX": "Phoenix", "SATX": "San Antonio",
    "SFO": "San Francisco", "SEA": "Seattle",
}


def _code_of(ticker: str) -> str:
    t = ticker.upper()
    if t.startswith("KX"):
        t = t[2:]
    if t.startswith("HIGH"):
        t = t[4:]
    elif t.startswith("LOW"):
        t = t[3:]
    if t.startswith("T"):        # the temperature 'T' infix (KXHIGHT.../KXLOWT...)
        t = t[1:]
    return t

# CANDIDATE station mappings — UNVERIFIED hypotheses, NOT ground truth. V1 reconciles
# CLI/METAR/GHCN to confirm siting and will flag any wrong mapping. Only mappings we
# are highly confident about are filled; everything else is left 'unresolved' on
# purpose (guessing a settlement station is precisely how a false edge is born).
_CANDIDATE_STATIONS: List[Tuple[List[str], Dict[str, Any]]] = [
    (["york", "nyc", "central park"],
     {"label": "New York (Central Park)", "cli_pil": "CLINYC", "icao": "KNYC",
      "ghcn_id": "USW00094728", "tz": "America/New_York"}),
]


def _load_venue_cfg() -> Dict[str, Any]:
    with open(CONFIG / "venues.yaml") as f:
        return yaml.safe_load(f)["kalshi"]


class Kalshi:
    def __init__(self, base: str, min_interval: float = 0.25, max_retries: int = 5):
        self.base = base.rstrip("/")
        self.s = requests.Session()
        self.s.headers.update(UA)
        self._min_interval = min_interval   # throttle: >= this many seconds between calls
        self._max_retries = max_retries
        self._last = 0.0

    def get(self, path: str, **params) -> Any:
        last_exc = None
        for attempt in range(self._max_retries + 1):
            gap = time.time() - self._last
            if gap < self._min_interval:
                time.sleep(self._min_interval - gap)
            r = self.s.get(self.base + path, params=params, timeout=30)
            self._last = time.time()
            if r.status_code == 429 or r.status_code >= 500:
                wait = max(float(r.headers.get("Retry-After") or 0), min(2 ** attempt, 16))
                last_exc = requests.HTTPError(f"{r.status_code} on {path}")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        raise last_exc or requests.HTTPError(f"exhausted retries on {path}")

    def get_text(self, path: str, **params) -> str:
        """Same throttled, retrying READ-ONLY GET as get(), but return verbatim
        response text (the exact bytes received). Used by capture paths that must
        content-hash what arrived on the wire, before any JSON re-serialization."""
        last_exc = None
        for attempt in range(self._max_retries + 1):
            gap = time.time() - self._last
            if gap < self._min_interval:
                time.sleep(self._min_interval - gap)
            r = self.s.get(self.base + path, params=params, timeout=30)
            self._last = time.time()
            if r.status_code == 429 or r.status_code >= 500:
                wait = max(float(r.headers.get("Retry-After") or 0), min(2 ** attempt, 16))
                last_exc = requests.HTTPError(f"{r.status_code} on {path}")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.text
        raise last_exc or requests.HTTPError(f"exhausted retries on {path}")

    def paginate(self, path: str, key: str, *, max_items: int = 20000, **params) -> List[dict]:
        out: List[dict] = []
        cursor: Optional[str] = None
        while True:
            p = dict(params)
            if cursor:
                p["cursor"] = cursor
            j = self.get(path, **p)
            items = j.get(key) or []
            out.extend(items)
            cursor = j.get("cursor")
            if not cursor or not items or len(out) >= max_items:
                return out

    def series_by_category(self, category: str) -> List[dict]:
        return self.get("/series/", category=category).get("series", []) or []

    def series_detail(self, ticker: str) -> dict:
        j = self.get(f"/series/{ticker}")
        return j.get("series", j)

    def markets(self, series_ticker: str, status: str, limit: int = 1000) -> List[dict]:
        return self.paginate("/markets", "markets", series_ticker=series_ticker,
                             status=status, limit=limit)

    def open_markets(self, series_ticker: str) -> List[dict]:
        return self.markets(series_ticker, status="open", limit=1000)

    def events(self, series_ticker: str, status: str, limit: int = 200,
               with_nested_markets: bool = True, max_items: int = 20000) -> List[dict]:
        return self.paginate("/events", "events", max_items=max_items,
                             series_ticker=series_ticker, status=status, limit=limit,
                             with_nested_markets=str(with_nested_markets).lower())

    def candlesticks(self, series_ticker: str, ticker: str, period_interval: int,
                     start_ts: int, end_ts: int) -> List[dict]:
        j = self.get(f"/series/{series_ticker}/markets/{ticker}/candlesticks",
                    period_interval=period_interval, start_ts=start_ts, end_ts=end_ts)
        return j.get("candlesticks", []) or []

    def orderbook(self, ticker: str) -> Dict[str, Any]:
        # Full depth: omit the depth param. Modern key is 'orderbook_fp'.
        return self.get(f"/markets/{ticker}/orderbook").get("orderbook_fp") or {}

    def trades(self, ticker: str, limit: int = 20) -> List[dict]:
        return self.get("/markets/trades", ticker=ticker, limit=limit).get("trades", []) or []


# --------------------------------------------------------------------------- #
# ticker parsing + strike reconciliation
# --------------------------------------------------------------------------- #
def parse_ticker(ticker: str, *, strike_type: Optional[str] = None,
                 floor_strike=None, cap_strike=None) -> Tuple[Optional[MarketSpec], Optional[str]]:
    """Parse a market ticker into a venue-agnostic MarketSpec.

    Returns (spec, error). error is None on success. When strike fields from the API
    are supplied, the parsed bucket is RECONCILED against them — a mismatch is an
    error even if the regex matched, because it means the parser and the venue
    disagree about what the contract pays on.
    """
    m = TICKER_RE.match(ticker)
    if not m:
        return None, "no_regex_match"
    bucket = m.group("bucket")
    try:
        target = datetime.strptime(m.group("date"), "%y%b%d").date()
    except ValueError:
        return None, f"bad_date_token:{m.group('date')}"

    spec = MarketSpec(venue="kalshi", ticker=ticker, series=m.group("series"),
                      target_date=target)
    num = float(bucket[1:])
    if bucket[0] == "T":
        if strike_type == "greater":
            spec.bucket_type, spec.lo, spec.hi = "threshold_above", num, None
            exp_floor, exp_cap = num, None
        elif strike_type == "less":
            spec.bucket_type, spec.lo, spec.hi = "threshold_below", None, num
            exp_floor, exp_cap = None, num
        else:
            return None, f"T_bucket_needs_strike_type(got {strike_type!r})"
    else:  # 'B' — 2 degF band labelled by its half-degree midpoint
        floor = num - 0.5
        spec.bucket_type, spec.lo, spec.hi = "band", floor, floor + 1
        exp_floor, exp_cap = floor, floor + 1

    mism = []
    if floor_strike is not None and exp_floor is not None and float(floor_strike) != float(exp_floor):
        mism.append(f"floor {floor_strike}!={exp_floor}")
    if cap_strike is not None and exp_cap is not None and float(cap_strike) != float(exp_cap):
        mism.append(f"cap {cap_strike}!={exp_cap}")
    if mism:
        return spec, "strike_reconcile_mismatch:" + ",".join(mism)
    return spec, None


def _classify(series: dict) -> Optional[str]:
    title = series.get("title") or ""
    if _EXCLUDE.search(title):
        return None
    up = (series.get("ticker") or "").upper()
    if "LOW" in up or re.search(r"low|lowest|\bmin", title, re.I):
        return "low"
    if "HIGH" in up or re.search(r"high|highest|\bmax", title, re.I):
        return "high"
    return None


def _city_of(detail: dict) -> Tuple[str, str]:
    for s in (detail.get("settlement_sources") or []):
        name = s.get("name") or ""
        if "Report" in name:
            return re.sub(r".*Report[:\s\-]+", "", name).strip(), name
    title = detail.get("title") or ""
    m = re.search(r"\bin ([A-Za-z .]+)$", title)
    return (m.group(1).strip() if m else title.strip()), ""


def _candidate_station(city: str) -> Dict[str, Any]:
    low = city.lower()
    for tokens, station in _CANDIDATE_STATIONS:
        if any(t in low for t in tokens):
            return {"status": "candidate", **station}
    return {"status": "unresolved"}


_ISSUEDBY = re.compile(r"issuedby=(\w+)", re.I)
_SITE = re.compile(r"[?&]site=(\w+)", re.I)


def _settlement_station(detail: dict) -> Optional[Dict[str, Any]]:
    """Authoritative settlement station from Kalshi's settlement_sources URL.

    The CLI product URL carries issuedby=<station> (e.g. NYC, LAX, HOU, DCA) and
    site=<WFO>. This is Kalshi's own settlement spec, so we take the station from
    here rather than guessing (it resolves non-obvious siting: LA->LAX, Houston->HOU).
    """
    for s in (detail.get("settlement_sources") or []):
        url = s.get("url") or ""
        m = _ISSUEDBY.search(url)
        if m:
            by = m.group(1).upper()
            site = _SITE.search(url)
            return {"status": "kalshi_authoritative", "issuedby": by, "icao": "K" + by,
                    "wfo": site.group(1).upper() if site else None, "settlement_url": url}
    return None


# --------------------------------------------------------------------------- #
# discover
# --------------------------------------------------------------------------- #
def discover(client: Kalshi) -> dict:
    series = client.series_by_category(WEATHER_CATEGORY)
    by_city: Dict[str, Dict[str, Any]] = {}
    active_series = []
    skipped = []
    for s in series:
        kind = _classify(s)
        if not kind:
            continue
        try:
            if not client.open_markets(s["ticker"]):
                continue
            active_series.append(s["ticker"])
            detail = client.series_detail(s["ticker"])
        except requests.RequestException as e:
            skipped.append({"series": s["ticker"], "error": str(e)})
            continue
        src_city, src = _city_of(detail)
        code = _code_of(s["ticker"])
        city = CODE_TO_CITY.get(code, src_city or code)
        rec = by_city.setdefault(city, {
            "city": city, "high_series": [], "low_series": [],
            "settlement_source": src, "station": None,
            "fee_type": detail.get("fee_type"), "fee_multiplier": detail.get("fee_multiplier"),
        })
        rec[f"{kind}_series"].append(s["ticker"])
        if src and not rec["settlement_source"]:
            rec["settlement_source"] = src
        st = _settlement_station(detail)
        if st and rec["station"] is None:
            rec["station"] = st
        elif st and rec["station"] and rec["station"]["icao"] != st["icao"]:
            rec["station"]["conflict"] = f"series disagree: also {st['icao']}"

    cities = []
    for city, rec in sorted(by_city.items()):
        cities.append({
            "city": city,
            "kalshi": {k: rec[k] for k in ("high_series", "low_series",
                                            "settlement_source", "fee_type", "fee_multiplier")},
            "station": rec["station"] or {"status": "unresolved"},
        })

    doc = {
        "generated_by": "validation.v3_market discover",
        "generated_at": utcnow_iso(),
        "note": ("Authoritative Kalshi-derived discovery. Station mappings with "
                 "status 'candidate' are UNVERIFIED hypotheses; V1 reconciles them. "
                 "status 'unresolved' = settlement station not yet mapped (excluded "
                 "from V1 gate until resolved)."),
        "n_active_series": len(active_series),
        "n_skipped_series": len(skipped),
        "cities": cities,
    }
    (CONFIG / "cities.yaml").write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    cache_path("kalshi", "discovered_series.json").write_text(json.dumps(active_series, indent=2))
    n_resolved = sum(1 for c in cities if c["station"]["status"] != "unresolved")
    print(f"[V3 discover] {len(active_series)} active temp series across {len(cities)} cities; "
          f"{n_resolved} station-resolved. Wrote config/cities.yaml")
    return doc


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def _normalize_orderbook(client: Kalshi, ticker: str) -> Tuple[OrderbookSnapshot, dict]:
    ob = client.orderbook(ticker)

    def levels(side: str) -> List[BookLevel]:
        return [BookLevel(price=float(p), size=float(s)) for p, s in (ob.get(side) or [])]

    yb = sorted(levels("yes_dollars"), key=lambda l: -l.price)
    nb = sorted(levels("no_dollars"), key=lambda l: -l.price)
    snap = OrderbookSnapshot(venue="kalshi", ticker=ticker,
                             ts_utc=datetime.now(timezone.utc),
                             yes_bids=yb, no_bids=nb, raw=ob)
    return snap, ob


def _coherence(snap: OrderbookSnapshot) -> Dict[str, Any]:
    flags = {"price_oob": 0, "nonpos_size": 0, "unsorted": 0, "crossed_locked": 0}
    for side in (snap.yes_bids, snap.no_bids):
        prev = None
        for lv in side:
            if not (0.0 < lv.price < 1.0):
                flags["price_oob"] += 1
            if lv.size <= 0:
                flags["nonpos_size"] += 1
            if prev is not None and lv.price >= prev:
                flags["unsorted"] += 1
            prev = lv.price
    byb = snap.best("yes_bids")
    nbb = snap.best("no_bids")
    # YES bid + NO bid > 1 => buying YES@(1-no_bid) and NO@(1-yes_bid) costs < $1 for a
    # guaranteed $1 => locked/crossed (a real but rare arb state, flagged not failed).
    if byb and nbb and (byb.price + nbb.price) > 1.0 + 1e-9:
        flags["crossed_locked"] = 1
    flags["depth"] = len(snap.yes_bids) + len(snap.no_bids)
    return flags


def validate(client: Kalshi, *, ob_sample: int = 24, trades_sample: int = 8) -> dict:
    series = [s for s in client.series_by_category(WEATHER_CATEGORY) if _classify(s)]

    parsed_tickers: List[str] = []
    unparsed: List[Dict[str, str]] = []
    mismatches: List[Dict[str, str]] = []
    sample_markets: List[str] = []
    n_markets = 0
    active_series = 0
    skipped_series: List[Dict[str, str]] = []

    for s in series:
        try:
            mk = client.open_markets(s["ticker"])
        except requests.RequestException as e:
            skipped_series.append({"series": s["ticker"], "error": str(e)})
            continue
        if not mk:
            continue
        active_series += 1
        for m in mk:
            n_markets += 1
            spec, err = parse_ticker(m["ticker"], strike_type=m.get("strike_type"),
                                     floor_strike=m.get("floor_strike"),
                                     cap_strike=m.get("cap_strike"))
            if err == "no_regex_match" or (spec is None):
                unparsed.append({"ticker": m["ticker"], "error": err})
            elif err:
                mismatches.append({"ticker": m["ticker"], "error": err})
            else:
                parsed_tickers.append(m["ticker"])
            if len(sample_markets) < max(ob_sample, trades_sample):
                sample_markets.append(m["ticker"])

    coverage = (100.0 * len(parsed_tickers) / n_markets) if n_markets else 0.0

    # timestamp validation on real trade timestamps (Kalshi REST = ISO-8601)
    ts_units: Dict[str, int] = {}
    ts_parse_failures = 0
    ts_monotonic_ok = True
    n_trades_checked = 0
    for t in sample_markets[:trades_sample]:
        try:
            trades = client.trades(t, limit=20)
        except requests.RequestException:
            continue
        prev = None
        for tr in trades:
            n_trades_checked += 1
            try:
                dt, unit = parse_kalshi_ts(tr["created_time"])
                ts_units[unit] = ts_units.get(unit, 0) + 1
                if dt.tzinfo is None:
                    ts_parse_failures += 1
                if prev is not None and dt > prev:  # API returns newest-first
                    ts_monotonic_ok = False
                prev = dt
            except Exception:
                ts_parse_failures += 1

    # full-depth orderbook coherence on a sample
    ob_agg = {"sampled": 0, "with_book": 0, "total_levels": 0, "max_depth": 0,
              "price_oob": 0, "nonpos_size": 0, "unsorted": 0, "crossed_locked": 0}
    ob_examples = []
    for t in sample_markets[:ob_sample]:
        try:
            snap, raw = _normalize_orderbook(client, t)
        except requests.RequestException:
            continue
        ob_agg["sampled"] += 1
        f = _coherence(snap)
        if f["depth"] > 0:
            ob_agg["with_book"] += 1
        ob_agg["total_levels"] += f["depth"]
        ob_agg["max_depth"] = max(ob_agg["max_depth"], f["depth"])
        for k in ("price_oob", "nonpos_size", "unsorted", "crossed_locked"):
            ob_agg[k] += f[k]
        if len(ob_examples) < 3 and f["depth"] > 0:
            ob_examples.append({
                "ticker": t, "depth": f["depth"],
                "best_yes_bid": snap.best("yes_bids").price if snap.best("yes_bids") else None,
                "best_no_bid": snap.best("no_bids").price if snap.best("no_bids") else None,
            })

    # persist a ticker fixture for the regression test
    if parsed_tickers:
        (REPO_ROOT / "tests" / "fixtures" / "kalshi_tickers_sample.json").write_text(
            json.dumps(sorted(set(parsed_tickers))[:400], indent=2))

    gate_reasons = []
    if coverage < 100.0:
        gate_reasons.append(f"parse coverage {coverage:.2f}% < 100% ({len(unparsed)} unparsed)")
    if mismatches:
        gate_reasons.append(f"{len(mismatches)} strike-reconcile mismatches")
    if ts_parse_failures:
        gate_reasons.append(f"{ts_parse_failures} timestamp parse failures")
    if not ts_monotonic_ok:
        gate_reasons.append("trade timestamps not monotonic")
    if ob_agg["price_oob"] or ob_agg["nonpos_size"] or ob_agg["unsorted"]:
        gate_reasons.append("malformed orderbook levels")
    if ob_agg["with_book"] == 0:
        gate_reasons.append("no orderbook depth captured on sample")
    if skipped_series:
        gate_reasons.append(f"{len(skipped_series)} series skipped (incomplete coverage)")
    gate = "PASS" if not gate_reasons else "FAIL"

    payload = {
        "validator": "V3_market", "venue": "kalshi", "generated_at": utcnow_iso(),
        "parse": {
            "active_series": active_series, "n_markets": n_markets,
            "parse_coverage_pct": round(coverage, 4),
            "n_unparsed": len(unparsed), "unparsed_examples": unparsed[:10],
            "n_strike_mismatch": len(mismatches), "mismatch_examples": mismatches[:10],
            "n_skipped_series": len(skipped_series), "skipped_examples": skipped_series[:5],
        },
        "timestamps": {
            "n_trades_checked": n_trades_checked, "units_seen": ts_units,
            "parse_failures": ts_parse_failures, "monotonic_ok": ts_monotonic_ok,
            "note": "REST uses ISO-8601; numeric epoch s-vs-ms covered by tests/test_timeutil.py",
        },
        "orderbook": {**ob_agg, "depth_captured": ob_agg["with_book"] > 0,
                      "full_depth": True, "examples": ob_examples,
                      "crossed_locked_note": "flagged, not failed: a crossed book is a "
                                             "real (rare) arb state, not corrupt data"},
        "schema": {"venue_agnostic": True, "normalized_into": "core.schema.OrderbookSnapshot"},
        "gate": gate, "gate_reasons": gate_reasons,
    }
    md = _md_summary(payload)
    write_report("validation/v3_market", payload, md_summary=md)
    print(f"[V3 validate] coverage={coverage:.2f}% markets={n_markets} "
          f"ob_sampled={ob_agg['sampled']} depth_captured={payload['orderbook']['depth_captured']} "
          f"GATE={gate}")
    if gate_reasons:
        print("  reasons:", "; ".join(gate_reasons))
    return payload


def _md_summary(p: dict) -> str:
    pr, ts, ob = p["parse"], p["timestamps"], p["orderbook"]
    return (
        f"# V3 — Kalshi market-data validator\n\n"
        f"_generated {p['generated_at']}_\n\n"
        f"**GATE: {p['gate']}**"
        + ("" if p["gate"] == "PASS" else "  \nreasons: " + "; ".join(p["gate_reasons"]))
        + f"\n\n## Ticker parse\n"
        f"- active series: {pr['active_series']}, markets: {pr['n_markets']}\n"
        f"- **coverage: {pr['parse_coverage_pct']}%** (unparsed {pr['n_unparsed']}, "
        f"strike-mismatch {pr['n_strike_mismatch']})\n"
        f"\n## Timestamps\n"
        f"- trades checked: {ts['n_trades_checked']}, units: {ts['units_seen']}, "
        f"parse failures: {ts['parse_failures']}, monotonic: {ts['monotonic_ok']}\n"
        f"\n## Orderbook (full depth)\n"
        f"- sampled {ob['sampled']} markets, {ob['with_book']} with depth, "
        f"max depth {ob['max_depth']} levels, total {ob['total_levels']}\n"
        f"- malformed: price_oob={ob['price_oob']} nonpos_size={ob['nonpos_size']} "
        f"unsorted={ob['unsorted']}; crossed/locked (flagged): {ob['crossed_locked']}\n"
        f"- depth_captured: {ob['depth_captured']}\n"
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="V3 Kalshi market-data validator")
    ap.add_argument("cmd", nargs="?", default="validate", choices=["discover", "validate"])
    ap.add_argument("--ob-sample", type=int, default=24)
    ap.add_argument("--trades-sample", type=int, default=8)
    args = ap.parse_args(argv)

    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"])
    if args.cmd == "discover":
        discover(client)
    else:
        payload = validate(client, ob_sample=args.ob_sample, trades_sample=args.trades_sample)
        return 0 if payload["gate"] == "PASS" else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

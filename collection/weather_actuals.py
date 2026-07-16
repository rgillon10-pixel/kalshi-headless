"""collection.weather_actuals — daily settlement-truth actuals + Kalshi settled-market join
for the just-closed UTC day (READ-ONLY, FREE/unauthenticated for the truth legs).

LOOP-QUEUE.md Q38 (weather revival, 2026-07-16): Q37's future EMOS weather-signal probe needs
two things nobody is collecting on a recurring cadence — a forecast tape (the sibling
`collection/forecast_collector.py` leg, now wired daily) and, the other side of the ledger,
the REALIZED settlement truth to score those forecasts against. `validation/v1_actuals.py`
already has battle-tested fetchers for that truth (NWS Climatological Report via IEM, and the
IEM METAR daily-summary derived from ASOS observations) plus a reconciliation with a fixed
`TOL_F=1.0` disagreement threshold — but only as an on-demand validator over a fixed sample
window, never as a recurring collector feeding tape. This module is that collector. It REUSES
v1_actuals' fetchers and `reconcile_day` verbatim (importing them, not reimplementing the HTTP
calls or the tolerance) so there is exactly one definition of "do these sources agree".

One pass, once per UTC day, for the previous UTC day (yesterday — the day just closed), over the
20 verified cities in `config/station_candidates.yaml` (their `cli_station` / `iem_station` /
`iem_network` fields). KNYC / Central Park — the station Q36 cares about — is already one of the
20 (city "New York", cli_station KNYC), so no extra explicit fetch is needed; the whole set is
the same city set `collection/weather_books.py` targets.

Provenance / trust tags (CLAUDE.md trust-default; Hard Rule #4):
  * A high or low value is tagged `broker_truth` ONLY when it is cross-confirmed by >=2
    independent sources (CLI and METAR both present) that AGREE within v1_actuals' own
    `TOL_F=1.0` degF tolerance — the identical spread/threshold `reconcile_day` uses, never a
    reinvented one. A value with a single source, sources disagreeing beyond tolerance, or a
    `dirty` day (impossible value / max<min / >=2degF disagreement) is tagged `unverifiable`
    (v1_actuals' own `clean`/`dirty`/`unverifiable` vocabulary) — it is NEVER silently upgraded
    to `broker_truth`. `broker_truth` and `synthetic` are the only tags here that live in the
    canonical enum; `unverifiable` is a tape-only verdict tag (JSONL, not a DB `price_source_tag`
    column) in the same spirit as `real_bid` (lesson L24) — it names an honest *absence* of
    confirmation, not a fill price.
  * The SETTLED Kalshi ladder join is the exchange's own reported result + `expiration_value`
    (the settled temperature) — Kalshi-reported fact, so `broker_truth`, mirroring
    `collection/econ_prints.py::fetch_recent_settlement`. The settled-events fetch follows the
    established `collection/sports_history.py::fetch_kalshi_settled` pattern (settled markets ->
    group by event -> per-market result), bounded by a per-series scan cap (lesson L10: Kalshi's
    open universe is 10k+ and an unbounded pull once blew 3GB RSS) with an honest `truncated`
    flag; the daily weather ladders purge in ~60 days so yesterday's event is well within the
    retention window.

Join key (structural, not a ticker-suffix hack — house rule / lesson L16): a daily weather
event ticker embeds its own weather day as `<SERIES>-<YYMMMDD>` (the documented grammar in
`validation/v3_market.TICKER_RE`, e.g. `KXHIGHTNYC-26JUL15`). We parse that date token to
identify which settled event belongs to the target day, rather than trusting `close_time` (which
sits in the NEXT UTC day for many US settlement instants). The city -> series map comes from the
authoritative `config/cities.yaml` (`kalshi.high_series` / `low_series`), so a city with no
Kalshi ladder configured is an honest `no_series_configured`, and a day with no matching settled
event is an honest `no_settled_market` note — never a fabricated join.

Honest completeness (same discipline as every collection/ module): the full station list is the
EXPECTED set. A city whose actuals fetch/parse RAISES is a recorded DROP (lowers completeness,
never silently skipped). A source that simply has not posted yet (NWS CLI for a just-closed day
often lags) is NOT a drop — the city is captured with `sources_present` flags and an
`unverifiable` verdict, exactly as `weather_books` treats an off-season empty series (lesson L23:
empty != drop). A Kalshi settled-fetch EXCEPTION or a scan truncation lowers completeness too (an
unexpected fetch failure is a failure); a benign `no_settled_market` does not.

Persists one JSONL line per city-day to `tape/weather_actuals/dt=<capture-day>.jsonl` (append-
only; the filename uses the CAPTURE day like every sibling family, and each record carries its
`target_day` explicitly). Bitemporal: `captured_at` (fetch instant) + `target_day` (the day the
data is about). Raw-bytes sha256 binds the Kalshi settled pages where applicable.

Run one pass:
    python -m collection.weather_actuals
    python -m collection.weather_actuals --limit 3   # first 3 cities only (offline/dev use)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.canonical import canonical_json, sha256_hex
from core.io import CONFIG, REPO_ROOT
# REUSE v1_actuals' fetchers + reconciliation + tolerance verbatim — one definition of "agree".
from validation.v1_actuals import TOL_F, fetch_cli, fetch_metar, reconcile_day
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "weather_actuals"

# Defensive per-series scan cap on settled markets (lesson L10). A daily weather series purges
# in ~60 days (~60 events x ~15 strikes ~= 900 markets), well under this; the cap is a guardrail
# that flags honestly via `truncated` rather than an expected bite.
MAX_SETTLED_MARKETS = 5000

# A daily weather event ticker's own weather-day token: `<SERIES>-<YYMMMDD>` (v3_market grammar).
# Anchored to a delimited segment so it reads the day off an event ticker (`...-26JUL15`) OR a
# full market ticker (`...-26JUL15-T70`) alike.
_EVENT_DATE_RE = re.compile(r"-(\d{2}[A-Z]{3}\d{2})(?=-|$)")


# --------------------------------------------------------------------------- #
# config loaders (injectable in run() for offline tests)
# --------------------------------------------------------------------------- #
def _load_stations(config_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """The verified cities in config/station_candidates.yaml (cli_station/iem_station/
    iem_network). Same authoritative set v1_actuals.load_curated reads."""
    path = Path(config_path) if config_path is not None else (CONFIG / "station_candidates.yaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return doc.get("cities", []) or []


def _load_city_series(config_path: Optional[Path] = None) -> Dict[str, List[str]]:
    """city -> [high_series + low_series tickers] from config/cities.yaml (authoritative Kalshi
    discovery). A city absent here maps to an empty list -> honest `no_series_configured`."""
    path = Path(config_path) if config_path is not None else (CONFIG / "cities.yaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: Dict[str, List[str]] = {}
    for c in doc.get("cities") or []:
        k = c.get("kalshi") or {}
        series = sorted({s for key in ("high_series", "low_series")
                         for s in (k.get(key) or []) if s})
        out[c.get("city")] = series
    return out


# --------------------------------------------------------------------------- #
# actuals truth — fetch + reconcile (v1_actuals fetchers reused)
# --------------------------------------------------------------------------- #
def fetch_city_actuals(http, cli_station: str, network: str, iem_station: str,
                       target_day: date) -> Dict[str, Any]:
    """CLI + METAR daily truth for a SINGLE target day, via v1_actuals' own fetchers (called
    over a one-day s..e range). Returns {"cli": {high,low,...}|None, "metar": {max,min}|None}.
    Raises on transport/HTTP failure so the caller records the city as a drop."""
    cli = fetch_cli(http, cli_station, target_day, target_day)
    metar = fetch_metar(http, network, iem_station, target_day, target_day)
    return {"cli": cli.get(target_day), "metar": metar.get(target_day)}


def _field_tag(verdict: str, cli_val: Optional[float], other_val: Optional[float],
               spread: Optional[float]) -> Dict[str, Any]:
    """Per-field (high or low) settlement value + honest source tag. `broker_truth` ONLY when
    >=2 sources are present AND agree within TOL_F AND the day is not `dirty` — the same
    threshold `reconcile_day` uses (spread already computed there). Otherwise `unverifiable`,
    never silently upgraded. Settlement value prefers CLI (the settlement truth); with only one
    source the value is that source's, tagged `unverifiable`."""
    present = [v for v in (cli_val, other_val) if v is not None]
    n = len(present)
    value = cli_val if cli_val is not None else (present[0] if present else None)
    confirmed = (verdict != "dirty" and n >= 2 and spread is not None and spread <= TOL_F)
    return {
        "cli": cli_val, "metar": other_val, "value": value,
        "n_sources": n, "spread": spread,
        "source_tag": "broker_truth" if confirmed else "unverifiable",
    }


def reconcile_actuals(cli_day: Optional[Dict[str, Any]],
                      metar_day: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Reconcile CLI vs METAR for one day, REUSING v1_actuals.reconcile_day (verdict + spreads),
    then derive per-field (high/low) settlement values + honest source tags."""
    verdict, flags, detail = reconcile_day(cli_day, metar_day, None)
    maxes, mins = detail["max"], detail["min"]
    return {
        "verdict": verdict,
        "flags": flags,
        "tolerance_F": TOL_F,
        "spread_max": detail["spread_max"],
        "spread_min": detail["spread_min"],
        "sources_present": {"cli": cli_day is not None, "metar": metar_day is not None},
        "high": _field_tag(verdict, maxes["cli"], maxes["metar"], detail["spread_max"]),
        "low": _field_tag(verdict, mins["cli"], mins["metar"], detail["spread_min"]),
    }


# --------------------------------------------------------------------------- #
# Kalshi settled-ladder join (sports_history / econ_prints settled pattern, bounded)
# --------------------------------------------------------------------------- #
def _event_date_from_ticker(event_ticker: str) -> Optional[date]:
    m = _EVENT_DATE_RE.search(event_ticker or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%y%b%d").date()
    except ValueError:
        return None


def _fetch_settled_markets(client: Kalshi, series: str, max_markets: int
                           ) -> Tuple[List[Dict], List[str], bool]:
    """Bounded pagination of /markets?series_ticker=...&status=settled (get_text so the sha256
    binds to the bytes received). Stops at `max_markets` with a `truncated` flag (lesson L10)."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    truncated = False
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"series_ticker": series, "status": "settled", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        text = client.get_text("/markets", **params)
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("markets") or []
        markets.extend(items)
        if len(markets) >= max_markets:
            markets = markets[:max_markets]
            truncated = True
            break
        cursor = j.get("cursor")
        if not cursor or not items:
            break
    return markets, raw_pages, truncated


def fetch_settled_for_series(client: Kalshi, series: str, target_day: date,
                             max_markets: int = MAX_SETTLED_MARKETS) -> Dict[str, Any]:
    """Settled events of `series` whose OWN weather-day token equals `target_day`. Each event's
    per-market `result` + `expiration_value` (the settled temperature) is Kalshi-reported fact
    -> `broker_truth`. A fetch exception is honest (`status: fetch_error`), never a fabricated
    join."""
    try:
        markets, raw_pages, truncated = _fetch_settled_markets(client, series, max_markets)
    except Exception as exc:
        return {"series": series, "status": "fetch_error", "error": str(exc), "events": []}

    raw_sha256 = sha256_hex("".join(raw_pages)) if raw_pages else None
    by_event: Dict[str, List[Dict]] = {}
    for m in markets:
        by_event.setdefault(m.get("event_ticker", ""), []).append(m)

    events: List[Dict[str, Any]] = []
    for et, ms in sorted(by_event.items()):
        if not et:
            continue
        if _event_date_from_ticker(et) != target_day:
            continue
        values = sorted({m.get("expiration_value") for m in ms if m.get("expiration_value")})
        events.append({
            "series": series,
            "event_ticker": et,
            "event_date": target_day.isoformat(),
            "close_time": ms[0].get("close_time"),
            "n_markets": len(ms),
            "expiration_value": values[0] if len(values) == 1 else None,
            "expiration_values_disagree": values if len(values) > 1 else None,
            "results": {m.get("ticker"): m.get("result") for m in ms},
            "price_source_tag": "broker_truth",
        })
    return {"series": series, "status": "ok", "truncated": truncated,
            "events": events, "raw_sha256": raw_sha256}


def join_settled_for_city(client: Kalshi, series_list: List[str], target_day: date,
                          max_markets: int = MAX_SETTLED_MARKETS) -> Dict[str, Any]:
    """Join a city's configured KXHIGH*/KXLOWT* series to the settled events closing on
    `target_day`. Statuses: `joined` (>=1 event), `no_settled_market` (series configured, none
    matched), `no_series_configured` (city has no Kalshi ladder), `series_error` (>=1 series
    raised — every sibling still attempted)."""
    per_series: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    truncated = False
    for series in series_list:
        r = fetch_settled_for_series(client, series, target_day, max_markets)
        per_series.append({"series": series, "status": r["status"],
                           "n_events": len(r["events"])})
        if r["status"] != "ok":
            errors.append({"series": series, "error": r.get("error")})
            continue
        truncated = truncated or bool(r.get("truncated"))
        events.extend(r["events"])

    if errors:
        status = "series_error"
    elif not series_list:
        status = "no_series_configured"
    elif not events:
        status = "no_settled_market"
    else:
        status = "joined"
    return {"status": status, "series": series_list, "events": events,
            "per_series": per_series, "errors": errors, "truncated": truncated}


# --------------------------------------------------------------------------- #
# capture — one JSONL line per city-day per pass
# --------------------------------------------------------------------------- #
def run(min_interval: float = 0.25, http=None, client: Optional[Kalshi] = None,
        store: Optional[Path] = None, stations: Optional[List[Dict[str, Any]]] = None,
        city_series: Optional[Dict[str, List[str]]] = None,
        target_day: Optional[date] = None, max_markets: int = MAX_SETTLED_MARKETS,
        limit: Optional[int] = None, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """One read-only daily actuals + settled-join pass for the previous UTC day.

    `http`/`client`/`store`/`stations`/`city_series`/`target_day` are injectable for fully
    offline testing; in production they default to the throttled live clients, the real tape
    store, and the config-driven station/series maps. `limit` caps cities (dev use). Returns a
    summary (`n_expected`/`n_captured`/`n_dropped`/`completeness_ok`/`truncated`/verdict tallies)
    — hourly_pass reads `completeness_ok`.
    """
    store = Path(store) if store is not None else TAPE
    if stations is None:
        stations = _load_stations(config_path)
    if city_series is None:
        city_series = _load_city_series()
    if http is None:
        from validation._http import Http
        http = Http(min_interval=min_interval)
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    if limit is not None:
        stations = stations[:limit]

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")                        # capture day -> filename
    target = target_day if target_day is not None else (cap_ts.date() - timedelta(days=1))

    expected = len(stations)
    lines: List[str] = []
    captured: List[str] = []
    drops: List[Dict[str, str]] = []
    kalshi_errors: List[Dict[str, Any]] = []
    truncated_any = False
    tally = {"broker_truth_high": 0, "broker_truth_low": 0,
             "verdict_clean": 0, "verdict_dirty": 0, "verdict_unverifiable": 0,
             "settled_joined": 0, "settled_none": 0}

    for city in stations:
        name = city.get("city")
        try:
            act = fetch_city_actuals(http, city["cli_station"], city["iem_network"],
                                     city["iem_station"], target)
        except Exception as exc:            # transport/parse failure -> honest DROP, never hidden
            drops.append({"city": name, "reason": f"actuals_fetch_failed: {exc}"})
            print(f"[weather_actuals] DROP {name}: actuals fetch failed ({exc})", file=sys.stderr)
            continue

        actuals = reconcile_actuals(act["cli"], act["metar"])
        series_list = city_series.get(name, [])
        join = join_settled_for_city(client, series_list, target, max_markets)
        if join["errors"]:
            kalshi_errors.extend({"city": name, **e} for e in join["errors"])
        truncated_any = truncated_any or bool(join.get("truncated"))

        record = {
            "schema_version": "weather_actuals.v1",
            "capture_id": capture_id,
            "captured_at": captured_at,
            "target_day": target.isoformat(),
            "venue": "kalshi",
            "city": name,
            "cli_station": city.get("cli_station"),
            "iem_station": city.get("iem_station"),
            "iem_network": city.get("iem_network"),
            "actuals": actuals,
            "settled_markets": join,
        }
        lines.append(canonical_json(record))
        captured.append(name)

        tally[f"verdict_{actuals['verdict']}"] += 1
        tally["broker_truth_high"] += int(actuals["high"]["source_tag"] == "broker_truth")
        tally["broker_truth_low"] += int(actuals["low"]["source_tag"] == "broker_truth")
        tally["settled_joined"] += int(join["status"] == "joined")
        tally["settled_none"] += int(join["status"] == "no_settled_market")

    # honest completeness: an actuals drop, a Kalshi settled-fetch exception, or a scan
    # truncation lowers it; a not-yet-posted source or a benign no_settled_market does not.
    completeness_ok = (not drops) and (not kalshi_errors) and (not truncated_any)

    path: Optional[str] = None
    if lines:
        store.mkdir(parents=True, exist_ok=True)
        out_path = store / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        path = str(out_path)

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "target_day": target.isoformat(),
        "n_expected": expected, "n_captured": len(captured), "n_lines": len(lines),
        "n_dropped": len(drops), "drops": drops,
        "n_kalshi_errors": len(kalshi_errors), "kalshi_errors": kalshi_errors,
        "truncated": truncated_any,
        "completeness_ok": completeness_ok,
        "tally": tally,
        "path": path,
    }
    print(f"[weather_actuals] {capture_id}: target {target.isoformat()} — "
          f"{len(captured)}/{expected} cities captured, {len(drops)} dropped, "
          f"broker_truth high/low {tally['broker_truth_high']}/{tally['broker_truth_low']}, "
          f"settled joined {tally['settled_joined']}, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}"
          + (" (TRUNCATED)" if truncated_any else ""))
    if drops:
        print(f"[weather_actuals] WARN {len(drops)} city actuals fetch(es) dropped "
              f"-> completeness_ok=False", file=sys.stderr)
    if kalshi_errors:
        print(f"[weather_actuals] WARN {len(kalshi_errors)} Kalshi settled-fetch error(s) "
              f"-> completeness_ok=False", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Daily weather actuals + Kalshi settled-market join (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap number of cities this pass")
    ap.add_argument("--min-interval", type=float, default=0.25,
                    help="min seconds between live fetches (politeness)")
    args = ap.parse_args(argv)
    run(min_interval=args.min_interval, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())

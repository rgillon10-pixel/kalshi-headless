"""Forward, single-pass forecast-tape collector (READ-ONLY, FREE/unauthenticated).

The single most-reused MISSING input across every prior Kalshi repo is forecast tape:
there is *zero* of it anywhere (audited 2026-06-18). Its absence blocks the latency edge,
the settle-time pin, and any forward ensemble-vs-market study (see
kb/quant-finance/01-weather-forecasting-alpha.md — "the forecast tape is the missing
input"). This script starts accumulating it.

What it does (one pass): for each curated tradeable city, fetch Open-Meteo's daily Tmax
(temperature_2m_max, Fahrenheit) from MULTIPLE models in a single request, and append one
JSONL line per (city, model, fetch) to data/forecast_tape/. Each line is bitemporal-ish:
it carries a millisecond-precision UTC `fetch_ts`, the sha256 of the raw response bytes
(provenance — the same byte-binding discipline as collection/capture_orderbooks.py), the
API's own `generationtime_ms`, and the per-model run metadata Open-Meteo returns.

  HARD RULE #1: the model list does NOT include `ncep_gefs025` — it is byte-identical to
  `gfs_seamless`, so collecting both is duplicate tape with a false sense of breadth. The
  invariant engine (scripts/invariants.py, inv_no_gefs) blocks it.

A forecast is a MODELED number — never a fillable price. Every line is tagged
`source_tag = "synthetic"` (core/source_tag.py: the trust=FALSE default). It must never
reach a fill / P&L decision (prime directive #1; Hard Rule #4).

Honest completeness (D3, same property as the orderbook capture): the curated (city, model)
set is the EXPECTED set; a fetch or parse that fails is recorded as a DROP in the pass
summary, lowering the completeness count below expected. A throttled/truncated/missing
response can therefore never masquerade as a complete pass by being silently skipped.

SCHEDULING IS DEFERRED — do NOT add cron / launchd here. This is a STANDING HOLD decision:
a sleeping laptop yields gappy tape (and gappy tape is worse than none — it silently biases
any latency or settle-time study). Scheduling belongs to a future always-on daemon, not to
a script run from a laptop. This file is the single-pass collector ONLY.

Run one pass:
    python -m collection.forecast_collector            # all curated cities, all models
    python -m collection.forecast_collector --limit 2  # first 2 cities only
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.source_tag import DEFAULT_TAG  # "synthetic" — a forecast is never a fill price

# --------------------------------------------------------------------------- #
# Open-Meteo: a FREE, UNAUTHENTICATED forecast API.
# --------------------------------------------------------------------------- #
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# Multi-model ensemble. HARD RULE #1: ncep_gefs025 is DELIBERATELY ABSENT (byte-identical to
# gfs_seamless). Adding it would trip scripts/invariants.py:inv_no_gefs. Do not add it.
MODELS: List[str] = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_global"]

# Curated tradeable-city lat/lon. cities.yaml carries Kalshi series + NWS station mappings but
# NO coordinates, so the tradeable subset is pinned here (settlement-station metro centroids;
# good enough for a city-level daily Tmax forecast). Keep this list small and tradeable.
CITY_COORDS: Dict[str, Dict[str, float]] = {
    "New York":     {"lat": 40.7790, "lon": -73.9690},   # KNYC (Central Park)
    "Austin":       {"lat": 30.1830, "lon": -97.6800},   # KAUS
    "Miami":        {"lat": 25.7959, "lon": -80.2870},   # KMIA
    "Chicago":      {"lat": 41.7860, "lon": -87.7520},   # KMDW (Midway, Kalshi settlement)
    "Denver":       {"lat": 39.8470, "lon": -104.6560},  # KDEN
    "Los Angeles":  {"lat": 33.9380, "lon": -118.3890},  # KLAX
    "Houston":      {"lat": 29.6450, "lon": -95.2780},   # KHOU (Hobby)
    "Philadelphia": {"lat": 39.8730, "lon": -75.2270},   # KPHL
}

STORE = REPO_ROOT / "data" / "forecast_tape"


def _utcnow_us_iso() -> str:
    """UTC ISO-8601 with microsecond precision and explicit offset (millisecond+ resolution
    is what a latency/settle-time study needs — second resolution would erase the signal)."""
    return datetime.now(timezone.utc).isoformat()


def _parse_models(raw: Dict, expected_models: List[str]) -> Dict[str, Dict]:
    """Split Open-Meteo's flat multi-model response into per-model records.

    With `models=a,b,c`, Open-Meteo suffixes every model-specific field with `_<model>`
    (e.g. `temperature_2m_max_gfs_seamless`) and keeps shared fields (`daily.time`,
    `generationtime_ms`) unsuffixed. We pull, per expected model, that model's daily Tmax
    series aligned to the shared date axis. A model present in the request but absent from the
    response (a partial Open-Meteo result) yields no record here -> it surfaces as a DROP.
    """
    out: Dict[str, Dict] = {}
    daily = raw.get("daily") or {}
    target_dates = list(daily.get("time") or [])
    daily_units = raw.get("daily_units") or {}

    for model in expected_models:
        key = f"temperature_2m_max_{model}"
        if key not in daily:
            continue  # model missing from response -> treated as a drop by the caller
        values = list(daily.get(key) or [])
        out[model] = {
            "target_dates": target_dates,
            "tmax_f": values,
            "unit": daily_units.get(key) or daily_units.get("temperature_2m_max"),
            # run metadata Open-Meteo returns (best-effort; not every model exposes all of these)
            "generationtime_ms": raw.get("generationtime_ms"),
            "utc_offset_seconds": raw.get("utc_offset_seconds"),
            "timezone": raw.get("timezone"),
            "elevation": raw.get("elevation"),
            "latitude": raw.get("latitude"),
            "longitude": raw.get("longitude"),
        }
    return out


def _fetch_city(http, city: str, coords: Dict[str, float], models: List[str]) -> str:
    """One polite GET for all models of one city. Returns the raw response TEXT (so the
    sha256 binds to the exact bytes received). Raises on transport/HTTP failure (caller
    records the failure as a drop)."""
    return http.text(
        OPEN_METEO_URL,
        latitude=coords["lat"],
        longitude=coords["lon"],
        daily="temperature_2m_max",
        temperature_unit="fahrenheit",
        timezone="auto",
        forecast_days=7,
        models=",".join(models),
    )


def run(limit: Optional[int] = None, min_interval: float = 0.5,
        http=None, store: Optional[Path] = None,
        models: Optional[List[str]] = None,
        city_coords: Optional[Dict[str, Dict[str, float]]] = None) -> Dict:
    """One read-only forecast-collection pass. `http`/`store`/`models`/`city_coords` are
    injectable for fully-offline testing; in production they default to the throttled live
    Http client, the real tape store, the curated MODELS list, and CITY_COORDS.

    Appends one JSONL line per (city, model, fetch) to <store>/forecast.jsonl. Returns a pass
    summary whose `n_complete` / `n_dropped` honestly reflect every (city, model) the pass
    set out to collect.
    """
    store = Path(store) if store is not None else STORE
    models = list(models) if models is not None else list(MODELS)
    city_coords = dict(city_coords) if city_coords is not None else dict(CITY_COORDS)

    # HARD RULE #1 enforced at runtime too (not only by the static invariant) — a forecast
    # tape that quietly doubled gfs_seamless under another name would be subtly corrupt.
    if "ncep_gefs025" in models:  # inv-pattern-def
        raise ValueError("ncep_gefs025 is byte-identical to gfs_seamless (Hard Rule #1); "
                         "remove it from the model list.")

    if http is None:
        from validation._http import Http
        http = Http(min_interval=min_interval)

    cities = list(city_coords.items())
    if limit is not None:
        cities = cities[:limit]

    expected = len(cities) * len(models)
    n_written = 0
    drops: List[Dict] = []
    city_summaries: List[Dict] = []

    store.mkdir(parents=True, exist_ok=True)
    tape_path = store / "forecast.jsonl"

    for city, coords in cities:
        # one wall-clock read per city fetch, frozen into every line from that response
        fetch_ts = _utcnow_us_iso()
        try:
            raw_text = _fetch_city(http, city, coords, models)
        except Exception as exc:  # transport/HTTP failure -> every model for this city drops
            for model in models:
                drops.append({"city": city, "model": model, "reason": f"fetch_failed: {exc}"})
            city_summaries.append({"city": city, "fetched": False, "models_parsed": 0,
                                   "error": str(exc)})
            print(f"[forecast] DROP {city}: fetch failed -> {len(models)} model drops ({exc})",
                  file=sys.stderr)
            continue

        raw_sha256 = sha256_hex(raw_text)
        try:
            import json as _json
            raw = _json.loads(raw_text)
        except Exception as exc:
            for model in models:
                drops.append({"city": city, "model": model, "reason": f"parse_failed: {exc}"})
            city_summaries.append({"city": city, "fetched": True, "models_parsed": 0,
                                   "error": f"json: {exc}"})
            print(f"[forecast] DROP {city}: response not JSON -> {len(models)} model drops",
                  file=sys.stderr)
            continue

        per_model = _parse_models(raw, models)
        lines: List[str] = []
        for model in models:
            rec = per_model.get(model)
            if rec is None or not rec.get("target_dates") or not rec.get("tmax_f"):
                drops.append({"city": city, "model": model,
                              "reason": "model_absent_or_empty_in_response"})
                continue
            line = {
                "city": city,
                "latitude": coords["lat"],
                "longitude": coords["lon"],
                "model": model,
                "variable": "temperature_2m_max",
                "target_dates": rec["target_dates"],
                "tmax_f": rec["tmax_f"],
                "unit": rec.get("unit"),
                "fetch_ts": fetch_ts,                     # ms+-precision receipt instant
                "generationtime_ms": rec.get("generationtime_ms"),
                "utc_offset_seconds": rec.get("utc_offset_seconds"),
                "timezone": rec.get("timezone"),
                "elevation": rec.get("elevation"),
                "source": "open-meteo",
                "source_endpoint": OPEN_METEO_URL,
                "raw_sha256": raw_sha256,                 # provenance: binds to the bytes received
                "source_tag": DEFAULT_TAG,                # "synthetic" — a forecast is never a fill
            }
            lines.append(canonical_json(line))

        if lines:
            with open(tape_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            n_written += len(lines)
        city_summaries.append({"city": city, "fetched": True, "models_parsed": len(lines)})
        print(f"[forecast] {city}: {len(lines)}/{len(models)} models persisted")

    summary = {
        "pass_ts": _utcnow_us_iso(),
        "store": str(tape_path),
        "n_cities": len(cities),
        "models": models,
        "n_expected": expected,             # cities x models the pass set out to collect
        "n_complete": n_written,            # lines actually persisted
        "n_dropped": len(drops),            # honest: failures, never silently skipped
        "drops": drops,
        "cities": city_summaries,
    }
    print(f"[forecast] pass: {n_written}/{expected} (city,model) records persisted, "
          f"{len(drops)} dropped -> {tape_path}")
    if drops:
        print(f"[forecast] WARN {len(drops)} (city,model) fetch(es) dropped "
              f"(recorded in summary, NOT silently skipped)", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Single-pass Open-Meteo forecast-tape collector (read-only, free). "
                    "SCHEDULING IS DEFERRED — no cron/launchd here.")
    ap.add_argument("--limit", type=int, default=None, help="cap number of cities this pass")
    ap.add_argument("--min-interval", type=float, default=0.5,
                    help="min seconds between live fetches (politeness)")
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())

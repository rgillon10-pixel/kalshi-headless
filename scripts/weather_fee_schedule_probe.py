#!/usr/bin/env python3
"""weather_fee_schedule_probe.py — pin the ACTUAL weather-series fee schedule (LOOP-QUEUE.md
Q37's "runnable NOW" sub-task; closes the Open item in kb/kalshi-api/03-fees-and-breakeven.md).

Q37 (summer maker-side re-test of the S1/S5 weather family) needs the real fee schedule
before sizing: is the maker fee still the standard 0.0175, or does the weather category
carry a series-level override / a standing Liquidity Incentive Program (LIP) rebate window
that would change the economics? This is a ONE-TIME confirmation probe, not a recurring
collector — it queries three READ-ONLY, unauthenticated Kalshi endpoints:

  1. `/series?category=Climate+and+Weather` — per-series `fee_type`/`fee_multiplier`
     (confirms/denies a special weather rate; core.pricing's MAKER_FEE_RATE/TAKER_FEE_RATE
     only apply at `fee_multiplier == 1`, `fee_type == "quadratic"`).
  2. `/series/fee_changes` and `/events/fee_changes` (per series, `show_historical=True`) —
     any scheduled or historical override layered on top of the base rate.
  3. `/incentive_programs` (`type=liquidity`) — the standing LIP: per-market maker-fee
     discount windows, paginated and filtered to the weather series ticker set.

Series-ticker universe is NOT hand-maintained here — it reuses the exact discovery logic
`collection.weather_books` already uses live (config `high_series`/`low_series` union the
live "Climate and Weather" category sweep's hourly-directional title match), so this probe
never drifts from what the committed collector actually captures.

Every number below is `broker_truth` (Kalshi's own API, read at probe time) or a direct
docs citation — never a modeled/synthetic fee. The incentive-program payout MECHANICS
(exactly how `discount_factor_bps` and `period_reward` combine) are NOT publicly documented
beyond field names; this script reports the fields observed and states that gap explicitly
rather than guessing at a formula.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collection.weather_books import (  # noqa: E402
    HOURLY_SEED_SERIES,
    _config_daily_series,
    _is_hourly_directional,
)
from validation.v3_market import WEATHER_CATEGORY, Kalshi, _load_venue_cfg  # noqa: E402

MAX_INCENTIVE_PAGES = 40  # bounded pull (lesson L10); ~1000/page -> 40k programs max


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def weather_series_universe(client: Kalshi, config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Reuse collection.weather_books' own discovery so the ticker set matches the live
    collector exactly. Returns {"daily": [...], "hourly": [...], "catalog": {ticker: series}}.
    """
    config_daily = _config_daily_series(config_path)
    catalog_list = client.series_by_category(WEATHER_CATEGORY)
    catalog = {s.get("ticker"): s for s in catalog_list if s.get("ticker")}
    sweep_hourly = sorted({t for t, s in catalog.items() if _is_hourly_directional(s)})
    hourly = sorted(set(sweep_hourly) | set(HOURLY_SEED_SERIES))
    daily = sorted(set(config_daily) & set(catalog))  # only series the live catalog confirms
    return {"daily": daily, "hourly": hourly, "catalog": catalog}


def series_fee_facts(client: Kalshi, tickers: List[str], catalog: Dict[str, Any]
                      ) -> Dict[str, Any]:
    """Per-series base fee_type/fee_multiplier (from the catalog sweep) + any historical/
    scheduled series- or event-level fee override."""
    facts: Dict[str, Any] = {}
    for t in tickers:
        s = catalog.get(t) or client.series_detail(t)
        series_changes = client.get("/series/fee_changes", series_ticker=t,
                                    show_historical=True).get("series_fee_change_arr") or []
        event_changes = client.get("/events/fee_changes", series_ticker=t
                                   ).get("event_fee_changes") or []
        facts[t] = {
            "fee_type": s.get("fee_type"),
            "fee_multiplier": s.get("fee_multiplier"),
            "n_series_fee_changes": len(series_changes),
            "n_event_fee_changes": len(event_changes),
        }
    return facts


def fetch_liquidity_incentives(client: Kalshi, max_pages: int = MAX_INCENTIVE_PAGES
                               ) -> Dict[str, Any]:
    """Paginate /incentive_programs?type=liquidity. Bounded (lesson L10) — reports
    truncation honestly rather than claiming full coverage."""
    programs: List[Dict[str, Any]] = []
    cursor = None
    pages = 0
    for pages in range(1, max_pages + 1):
        params: Dict[str, Any] = {"status": "all", "type": "liquidity", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        j = client.get("/incentive_programs", **params)
        batch = j.get("incentive_programs") or []
        programs.extend(batch)
        cursor = j.get("next_cursor")
        if not cursor or not batch:
            break
    truncated = bool(cursor) and pages >= max_pages
    return {"programs": programs, "n_pages": pages, "truncated": truncated}


def summarize_weather_incentives(programs: List[Dict[str, Any]], tickers: List[str]
                                 ) -> Dict[str, Any]:
    prefixes = tuple(f"{t}-" for t in tickers)
    weather = [p for p in programs if p.get("market_ticker", "").startswith(prefixes)]
    if not weather:
        return {"n_programs": 0}

    durations_min = []
    for p in weather:
        try:
            d = (_parse_iso(p["end_date"]) - _parse_iso(p["start_date"])).total_seconds() / 60.0
            durations_min.append(round(d, 1))
        except (KeyError, ValueError):
            continue

    return {
        "n_programs": len(weather),
        "series_covered": sorted({p["market_ticker"].split("-", 1)[0] for p in weather}),
        "incentive_type": sorted({p.get("incentive_type") for p in weather}),
        "incentive_description": dict(Counter(p.get("incentive_description") for p in weather)),
        "discount_factor_bps": dict(Counter(p.get("discount_factor_bps") for p in weather)),
        "target_size_fp": sorted({p.get("target_size_fp") for p in weather}),
        "period_reward_centicents": {
            "min": min(p["period_reward"] for p in weather),
            "max": max(p["period_reward"] for p in weather),
        },
        "duration_minutes": {
            "min": min(durations_min) if durations_min else None,
            "max": max(durations_min) if durations_min else None,
        },
        "earliest_start": min(p["start_date"] for p in weather),
        "latest_end": max(p["end_date"] for p in weather),
        "paid_out_values": sorted({p.get("paid_out") for p in weather}),
    }


def run(client: Kalshi, config_path: Optional[Path] = None) -> Dict[str, Any]:
    universe = weather_series_universe(client, config_path)
    all_tickers = sorted(set(universe["daily"]) | set(universe["hourly"]))
    fee_facts = series_fee_facts(client, all_tickers, universe["catalog"])
    incentives = fetch_liquidity_incentives(client)
    weather_incentive_summary = summarize_weather_incentives(incentives["programs"], all_tickers)

    n_nonstandard = sum(
        1 for f in fee_facts.values()
        if f["fee_type"] != "quadratic" or f["fee_multiplier"] != 1
    )
    n_overrides = sum(
        1 for f in fee_facts.values()
        if f["n_series_fee_changes"] or f["n_event_fee_changes"]
    )

    return {
        "probed_at": datetime.now(timezone.utc).isoformat(),
        "n_series": len(all_tickers),
        "series": all_tickers,
        "fee_facts": fee_facts,
        "n_series_nonstandard_base_rate": n_nonstandard,
        "n_series_with_fee_overrides": n_overrides,
        "incentive_pull": {"n_pages": incentives["n_pages"], "truncated": incentives["truncated"],
                            "n_programs_total": len(incentives["programs"])},
        "weather_liquidity_incentives": weather_incentive_summary,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print machine-readable JSON only")
    args = ap.parse_args()

    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"])
    result = run(client)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
        return

    print(f"Weather fee-schedule probe — {result['probed_at']}")
    print(f"Series checked: {result['n_series']}")
    print(f"Non-standard base rate (fee_type!=quadratic or fee_multiplier!=1): "
          f"{result['n_series_nonstandard_base_rate']}")
    print(f"Series with any historical/scheduled fee override: "
          f"{result['n_series_with_fee_overrides']}")
    ip = result["incentive_pull"]
    print(f"\nIncentive-programs pull: {ip['n_programs_total']} programs / {ip['n_pages']} pages"
          f"{' (TRUNCATED — raise MAX_INCENTIVE_PAGES)' if ip['truncated'] else ''}")
    wi = result["weather_liquidity_incentives"]
    if wi.get("n_programs", 0) == 0:
        print("No active/historical liquidity-incentive programs found on weather series.")
    else:
        print(f"Weather liquidity-incentive programs: {wi['n_programs']}")
        print(f"  series covered: {wi['series_covered']}")
        print(f"  discount_factor_bps: {wi['discount_factor_bps']}")
        print(f"  incentive_description: {wi['incentive_description']}")
        print(f"  duration (min): {wi['duration_minutes']}")
        print(f"  target_size_fp: {wi['target_size_fp']}")
        print(f"  window: {wi['earliest_start']} .. {wi['latest_end']}")


if __name__ == "__main__":
    main()

"""scripts.weather_fee_schedule_probe — offline tests.

Fully offline: a FakeKalshi serves the three endpoints the probe reads
(`/series?category=...`, `/series/fee_changes`, `/events/fee_changes`,
`/incentive_programs`) from in-memory fixtures. No live network.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import weather_fee_schedule_probe as probe  # noqa: E402


class FakeKalshi:
    def __init__(self, catalog, incentive_pages, fee_changes=None, event_changes=None):
        self._catalog = catalog
        self._incentive_pages = incentive_pages  # list of (programs, next_cursor)
        self._fee_changes = fee_changes or {}
        self._event_changes = event_changes or {}
        self.calls = []

    def series_by_category(self, category):
        assert category == "Climate and Weather"
        return self._catalog

    def series_detail(self, ticker):
        for s in self._catalog:
            if s["ticker"] == ticker:
                return s
        return {"ticker": ticker}

    def get(self, path, **params):
        self.calls.append((path, params))
        if path == "/series/fee_changes":
            arr = self._fee_changes.get(params["series_ticker"], [])
            return {"series_fee_change_arr": arr}
        if path == "/events/fee_changes":
            arr = self._event_changes.get(params["series_ticker"], [])
            return {"event_fee_changes": arr}
        if path == "/incentive_programs":
            idx = 0
            cursor = params.get("cursor")
            if cursor:
                idx = int(cursor)
            programs, nxt = self._incentive_pages[idx]
            return {"incentive_programs": programs, "next_cursor": nxt}
        raise AssertionError(f"unexpected path {path}")


def _series(ticker, title, fee_type="quadratic", fee_multiplier=1):
    return {"ticker": ticker, "title": title, "fee_type": fee_type,
            "fee_multiplier": fee_multiplier}


def _incentive(ticker, *, description="new_event", bps=5000, start="2026-07-17T18:00:00Z",
               end="2026-07-17T19:00:00Z", reward=200000, target="1000.00", paid_out=False):
    return {"market_ticker": ticker, "incentive_type": "liquidity",
            "incentive_description": description, "discount_factor_bps": bps,
            "start_date": start, "end_date": end, "period_reward": reward,
            "target_size_fp": target, "paid_out": paid_out}


def _cities_yaml(tmp_path):
    p = tmp_path / "cities.yaml"
    p.write_text(
        "cities:\n"
        "- city: New York\n"
        "  kalshi:\n"
        "    high_series: [KXHIGHNY]\n"
        "    low_series: [KXLOWTNYC]\n",
        encoding="utf-8",
    )
    return p


# --------------------------------------------------------------------------- #
# series discovery reuses collection.weather_books — just confirm it matches
# --------------------------------------------------------------------------- #
def test_weather_series_universe_unions_config_and_hourly_sweep(tmp_path):
    catalog = [
        _series("KXHIGHNY", "Highest temperature in NYC"),
        _series("KXLOWTNYC", "Lowest temperature in NYC"),
        _series("KXTEMPNYCH", "Hourly Directional NYC Temperature"),
        _series("KXHURRICANE", "Some hurricane series"),  # not temp-related, must be excluded
    ]
    client = FakeKalshi(catalog, incentive_pages=[([], None)])
    universe = probe.weather_series_universe(client, config_path=_cities_yaml(tmp_path))
    assert universe["daily"] == ["KXHIGHNY", "KXLOWTNYC"]
    assert universe["hourly"] == ["KXTEMPNYCH"]  # seeded + sweep both hit it, deduped


def test_weather_series_universe_seeds_kxtempnych_even_if_title_sweep_misses_it(tmp_path):
    # sweep-only catalog, no hourly-directional title match at all
    catalog = [_series("KXHIGHNY", "Highest temperature in NYC")]
    client = FakeKalshi(catalog, incentive_pages=[([], None)])
    universe = probe.weather_series_universe(client, config_path=_cities_yaml(tmp_path))
    assert "KXTEMPNYCH" in universe["hourly"]  # HOURLY_SEED_SERIES, never silently dropped


# --------------------------------------------------------------------------- #
# fee facts
# --------------------------------------------------------------------------- #
def test_series_fee_facts_reads_base_rate_and_override_counts():
    catalog = {"KXHIGHNY": _series("KXHIGHNY", "Highest temperature in NYC"),
               "KXTEMPNYCH": _series("KXTEMPNYCH", "Hourly Directional NYC Temperature")}
    client = FakeKalshi(
        list(catalog.values()), incentive_pages=[([], None)],
        fee_changes={"KXTEMPNYCH": [{"fee_type": "flat"}]},
        event_changes={},
    )
    facts = probe.series_fee_facts(client, ["KXHIGHNY", "KXTEMPNYCH"], catalog)
    assert facts["KXHIGHNY"] == {"fee_type": "quadratic", "fee_multiplier": 1,
                                  "n_series_fee_changes": 0, "n_event_fee_changes": 0}
    assert facts["KXTEMPNYCH"]["n_series_fee_changes"] == 1


def test_series_fee_facts_falls_back_to_series_detail_when_not_in_catalog():
    client = FakeKalshi([_series("KXHIGHNY", "Highest temperature in NYC", fee_multiplier=2)],
                        incentive_pages=[([], None)])
    facts = probe.series_fee_facts(client, ["KXHIGHNY"], catalog={})
    assert facts["KXHIGHNY"]["fee_multiplier"] == 2


# --------------------------------------------------------------------------- #
# incentive-program pagination + weather filter
# --------------------------------------------------------------------------- #
def test_fetch_liquidity_incentives_follows_cursor_and_reports_truncation():
    pages = [([_incentive("KXTEMPNYCH-26JUL1715-T88.99")], "1"),
              ([_incentive("KXHIGHNY-26JUL17-B70.5")], None)]
    client = FakeKalshi([], incentive_pages=pages)
    out = probe.fetch_liquidity_incentives(client, max_pages=10)
    assert len(out["programs"]) == 2
    assert out["n_pages"] == 2
    assert out["truncated"] is False


def test_fetch_liquidity_incentives_reports_truncation_when_cap_hit():
    pages = [([_incentive("KXTEMPNYCH-26JUL1715-T88.99")], "1"),
              ([_incentive("KXTEMPNYCH-26JUL1716-T88.99")], "2")]
    client = FakeKalshi([], incentive_pages=pages)
    out = probe.fetch_liquidity_incentives(client, max_pages=2)
    assert out["truncated"] is True
    assert out["n_pages"] == 2


def test_summarize_weather_incentives_filters_by_ticker_prefix_and_matches_ticker_boundary():
    programs = [
        _incentive("KXTEMPNYCH-26JUL1715-T88.99"),
        _incentive("KXHIGHNY-26JUL17-B70.5", bps=5000),
        _incentive("KXTEMPNYCHFAKE-26JUL1715-T88.99"),  # prefix collision, must NOT match
        _incentive("GOVPARTYCA-27-R", description="long_dated"),  # unrelated series
    ]
    summary = probe.summarize_weather_incentives(programs, ["KXTEMPNYCH", "KXHIGHNY"])
    assert summary["n_programs"] == 2
    assert summary["series_covered"] == ["KXHIGHNY", "KXTEMPNYCH"]
    assert summary["discount_factor_bps"] == {5000: 2}
    assert summary["duration_minutes"]["min"] == 60.0


def test_summarize_weather_incentives_empty_is_honest_not_fabricated():
    summary = probe.summarize_weather_incentives([], ["KXTEMPNYCH"])
    assert summary == {"n_programs": 0}


# --------------------------------------------------------------------------- #
# end-to-end run()
# --------------------------------------------------------------------------- #
def test_run_end_to_end_summarizes_nonstandard_rates_and_overrides(tmp_path):
    catalog = [
        _series("KXHIGHNY", "Highest temperature in NYC"),
        _series("KXLOWTNYC", "Lowest temperature in NYC"),
        _series("KXTEMPNYCH", "Hourly Directional NYC Temperature", fee_multiplier=2),
    ]
    pages = [([_incentive("KXTEMPNYCH-26JUL1715-T88.99")], None)]
    client = FakeKalshi(catalog, incentive_pages=pages,
                        fee_changes={"KXHIGHNY": [{"fee_type": "flat"}]})
    result = probe.run(client, config_path=_cities_yaml(tmp_path))
    assert result["n_series"] == 3
    assert result["n_series_nonstandard_base_rate"] == 1  # KXTEMPNYCH fee_multiplier=2
    assert result["n_series_with_fee_overrides"] == 1  # KXHIGHNY
    assert result["weather_liquidity_incentives"]["n_programs"] == 1

"""collection.econ_prints — open-ladder discovery, most-recent-settlement pick, the
not-built nowcast stub, and a fully offline capture pass (FakeClient, no network) with
honest completeness."""
from __future__ import annotations

import json

from collection import econ_prints as ep


def _mk_market(ticker, event_ticker, close_time, floor_strike, yes_ask=0.10,
               yes_bid=None, no_ask=None, no_bid=None, result=None, expiration_value=None):
    return {
        "ticker": ticker, "event_ticker": event_ticker,
        "title": "CPI print", "close_time": close_time,
        "floor_strike": floor_strike, "strike_type": "greater",
        "yes_ask_dollars": f"{yes_ask:.4f}" if yes_ask is not None else None,
        "yes_bid_dollars": f"{yes_bid:.4f}" if yes_bid is not None else None,
        "no_ask_dollars": f"{no_ask:.4f}" if no_ask is not None else None,
        "no_bid_dollars": f"{no_bid:.4f}" if no_bid is not None else None,
        "result": result, "expiration_value": expiration_value,
    }


class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only get_text, served from
    in-memory fixtures keyed by (series_ticker, status). No network, no clock."""

    base = "https://fake.test"

    def __init__(self, markets_by_series_status=None, fail=()):
        self.markets_by_series_status = markets_by_series_status or {}
        self.fail = set(fail)

    def get_text(self, path, **params):
        assert path == "/markets"
        key = (params["series_ticker"], params["status"])
        if key in self.fail:
            raise RuntimeError(f"simulated fetch failure: {key}")
        return json.dumps({"markets": self.markets_by_series_status.get(key, [])})


# --------------------------------------------------------------------------- #
# open-ladder discovery
# --------------------------------------------------------------------------- #
def test_discover_open_events_groups_by_event_and_drops_missing_ask():
    markets = [
        _mk_market("KXCPI-26JUL-T0.3", "KXCPI-26JUL", "2026-08-12T12:25:00Z", 0.3, yes_ask=0.40),
        _mk_market("KXCPI-26JUL-T0.4", "KXCPI-26JUL", "2026-08-12T12:25:00Z", 0.4, yes_ask=None),
        _mk_market("KXCPI-26AUG-T0.3", "KXCPI-26AUG", "2026-09-11T12:25:00Z", 0.3, yes_ask=0.55),
    ]
    client = FakeClient(markets_by_series_status={("KXCPI", "open"): markets})
    result = ep.discover_open_events(client, "KXCPI")
    assert result["status"] == "ok"
    events = {e["event_ticker"]: e for e in result["events"]}
    assert set(events) == {"KXCPI-26JUL", "KXCPI-26AUG"}
    jul = events["KXCPI-26JUL"]
    assert jul["expected_strikes"] == 2 and jul["captured_strikes"] == 1
    assert jul["completeness_ok"] is False
    aug = events["KXCPI-26AUG"]
    assert aug["completeness_ok"] is True
    assert aug["strikes"][0]["price_source_tag"] == "real_ask"


def test_discover_open_events_fetch_error():
    client = FakeClient(fail=[("KXCPI", "open")])
    result = ep.discover_open_events(client, "KXCPI")
    assert result["status"] == "fetch_error" and result["events"] == []


def test_discover_open_events_empty():
    client = FakeClient(markets_by_series_status={("KXCPI", "open"): []})
    result = ep.discover_open_events(client, "KXCPI")
    assert result["status"] == "ok" and result["events"] == []


# --------------------------------------------------------------------------- #
# most-recent settlement
# --------------------------------------------------------------------------- #
def test_fetch_recent_settlement_picks_newest_close_time():
    older = [_mk_market("KXCPI-26MAY-T0.3", "KXCPI-26MAY", "2026-06-10T12:25:00Z", 0.3,
                        result="yes", expiration_value="0.5")]
    newer = [_mk_market("KXCPI-26JUN-T0.3", "KXCPI-26JUN", "2026-07-10T12:25:00Z", 0.3,
                        result="no", expiration_value="0.2"),
             _mk_market("KXCPI-26JUN-T0.1", "KXCPI-26JUN", "2026-07-10T12:25:00Z", 0.1,
                        result="yes", expiration_value="0.2")]
    client = FakeClient(markets_by_series_status={("KXCPI", "settled"): older + newer})
    rec = ep.fetch_recent_settlement(client, "KXCPI")
    assert rec["status"] == "settled"
    assert rec["event_ticker"] == "KXCPI-26JUN"
    assert rec["expiration_value"] == "0.2"
    assert rec["price_source_tag"] == "broker_truth"
    assert rec["results"] == {"KXCPI-26JUN-T0.3": "no", "KXCPI-26JUN-T0.1": "yes"}


def test_fetch_recent_settlement_no_settled_events_yet():
    client = FakeClient(markets_by_series_status={("KXCPI", "settled"): []})
    rec = ep.fetch_recent_settlement(client, "KXCPI")
    assert rec["status"] == "no_settled_events"


def test_fetch_recent_settlement_fetch_error():
    client = FakeClient(fail=[("KXCPI", "settled")])
    rec = ep.fetch_recent_settlement(client, "KXCPI")
    assert rec["status"] == "fetch_error"


def test_fetch_recent_settlement_pending_not_fully_resolved():
    markets = [
        _mk_market("A", "EVT", "2026-07-10T12:25:00Z", 0.3, result="yes", expiration_value="0.2"),
        _mk_market("B", "EVT", "2026-07-10T12:25:00Z", 0.1, result=None, expiration_value=None),
    ]
    client = FakeClient(markets_by_series_status={("KXCPI", "settled"): markets})
    rec = ep.fetch_recent_settlement(client, "KXCPI")
    assert rec["status"] == "pending"


def test_fetch_recent_settlement_disagreeing_expiration_values_surfaced_not_hidden():
    markets = [
        _mk_market("A", "EVT", "2026-07-10T12:25:00Z", 0.3, result="yes", expiration_value="0.2"),
        _mk_market("B", "EVT", "2026-07-10T12:25:00Z", 0.1, result="yes", expiration_value="0.3"),
    ]
    client = FakeClient(markets_by_series_status={("KXCPI", "settled"): markets})
    rec = ep.fetch_recent_settlement(client, "KXCPI")
    assert rec["expiration_value"] is None
    assert rec["expiration_values_disagree"] == ["0.2", "0.3"]


# --------------------------------------------------------------------------- #
# nowcast — cpi/payrolls stay an honest not_built stub; gdp routes to GDPNow
# --------------------------------------------------------------------------- #
def test_fetch_nowcast_not_built_for_non_gdp_series():
    assert ep.fetch_nowcast("cpi_mom") == {"status": "not_built"}
    assert ep.fetch_nowcast("payrolls") == {"status": "not_built"}


def test_fetch_nowcast_routes_gdp_to_injected_fetcher():
    sentinel = {"status": "ok", "value_pct": 1.19}
    assert ep.fetch_nowcast("gdp", gdp_fetcher=lambda: sentinel) is sentinel


def _mk_gdpnow_html(quarters_dates_vals):
    """Build a minimal page fragment with the three parallel JS arrays GDPNow embeds,
    in the real page's block order (newest quarter first, each block date-ascending)."""
    quarters = ",".join(f'"{q}"' for q, _, _ in quarters_dates_vals)
    dates = ",".join(f'"{d}"' for _, d, _ in quarters_dates_vals)
    vals = ",".join("null" if v is None else str(v) for _, _, v in quarters_dates_vals)
    return (
        f"var forecastDatesArray = [], gdpForecastArray = [];\n"
        f"forecastDates = [{dates}];\n"
        f"forecastQuarters = [{quarters}];\n"
        f"gdpForecast = [{vals}];\n"
    )


def test_parse_gdpnow_nowcast_picks_last_entry_of_newest_quarter_block():
    html = _mk_gdpnow_html([
        ("6/30/2026", "6/1/2026", 3.0),
        ("6/30/2026", "6/15/2026", 2.5),
        ("6/30/2026", "7/1/2026", 1.19),
        ("3/31/2026", "3/1/2026", 4.0),
        ("3/31/2026", "3/28/2026", 2.2),
    ])
    rec = ep.parse_gdpnow_nowcast(html)
    assert rec["status"] == "ok"
    assert rec["target_quarter_end"] == "6/30/2026"
    assert rec["as_of"] == "7/1/2026"
    assert rec["value_pct"] == 1.19
    assert rec["n_updates_this_quarter"] == 3
    assert rec["price_source_tag"] == "synthetic"


def test_parse_gdpnow_nowcast_missing_array_is_parse_error():
    html = "forecastDates = [\"6/1/2026\"]; forecastQuarters = [\"6/30/2026\"];"
    rec = ep.parse_gdpnow_nowcast(html)
    assert rec["status"] == "parse_error"


def test_parse_gdpnow_nowcast_mismatched_lengths_is_parse_error():
    html = _mk_gdpnow_html([("6/30/2026", "6/1/2026", 3.0)])
    html = html.replace('gdpForecast = [3.0]', 'gdpForecast = [3.0,4.0]')
    rec = ep.parse_gdpnow_nowcast(html)
    assert rec["status"] == "parse_error"


def test_parse_gdpnow_nowcast_null_latest_entry_is_parse_error():
    html = _mk_gdpnow_html([("6/30/2026", "6/1/2026", None)])
    rec = ep.parse_gdpnow_nowcast(html)
    assert rec["status"] == "parse_error"


def test_fetch_nowcast_gdp_ok_end_to_end():
    html = _mk_gdpnow_html([("6/30/2026", "7/1/2026", 1.19)])
    rec = ep.fetch_nowcast_gdp(html_fetcher=lambda: html)
    assert rec["status"] == "ok" and rec["value_pct"] == 1.19


def test_fetch_nowcast_gdp_fetch_error_never_fabricates():
    def boom():
        raise RuntimeError("network down")
    rec = ep.fetch_nowcast_gdp(html_fetcher=boom)
    assert rec == {"status": "fetch_error", "error": "network down"}


# --------------------------------------------------------------------------- #
# fully offline capture pass
# --------------------------------------------------------------------------- #
def test_run_captures_open_and_settlement_end_to_end(tmp_path):
    open_markets = [
        _mk_market("KXCPI-26JUL-T0.3", "KXCPI-26JUL", "2026-08-12T12:25:00Z", 0.3, yes_ask=0.40),
    ]
    settled_markets = [
        _mk_market("KXCPI-26MAY-T0.3", "KXCPI-26MAY", "2026-06-10T12:25:00Z", 0.3,
                   result="yes", expiration_value="0.5"),
    ]
    client = FakeClient(markets_by_series_status={
        ("KXCPI", "open"): open_markets,
        ("KXCPI", "settled"): settled_markets,
    })
    summary = ep.run(client=client, tape_dir=tmp_path, series={"cpi_mom": "KXCPI"})
    assert summary["n_series"] == 1 and summary["n_complete"] == 1

    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    rec = json.loads(out_path.read_text().splitlines()[0])
    assert rec["series_key"] == "cpi_mom"
    assert rec["open_events"]["events"][0]["completeness_ok"] is True
    assert rec["recent_settlement"]["status"] == "settled"
    assert rec["recent_settlement"]["expiration_value"] == "0.5"
    assert rec["nowcast"] == {"status": "not_built"}
    assert rec["pass_complete"] is True
    assert "bracket_sum" not in rec["open_events"]["events"][0]


def test_run_marks_incomplete_when_no_open_events(tmp_path):
    client = FakeClient(markets_by_series_status={
        ("KXCPI", "open"): [],
        ("KXCPI", "settled"): [],
    })
    summary = ep.run(client=client, tape_dir=tmp_path, series={"cpi_mom": "KXCPI"})
    assert summary["n_complete"] == 0
    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    rec = json.loads(out_path.read_text().splitlines()[0])
    assert rec["pass_complete"] is False


def test_run_two_series_independent(tmp_path):
    cpi = [_mk_market("KXCPI-26JUL-T0.3", "KXCPI-26JUL", "2026-08-12T12:25:00Z", 0.3, yes_ask=0.40)]
    gdp = [_mk_market("KXGDP-26JUL30-T2.0", "KXGDP-26JUL30", "2026-07-30T12:29:00Z", 2.0, yes_ask=0.61)]
    client = FakeClient(markets_by_series_status={
        ("KXCPI", "open"): cpi, ("KXCPI", "settled"): [],
        ("KXGDP", "open"): gdp, ("KXGDP", "settled"): [],
    })
    gdp_nowcast = {"status": "ok", "value_pct": 1.19}
    summary = ep.run(client=client, tape_dir=tmp_path,
                     series={"cpi_mom": "KXCPI", "gdp": "KXGDP"},
                     gdp_nowcast_fetcher=lambda: gdp_nowcast)
    assert summary["n_series"] == 2
    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    recs = [json.loads(ln) for ln in out_path.read_text().splitlines()]
    assert {r["series_key"] for r in recs} == {"cpi_mom", "gdp"}
    by_key = {r["series_key"]: r for r in recs}
    assert by_key["cpi_mom"]["nowcast"] == {"status": "not_built"}
    assert by_key["gdp"]["nowcast"] == gdp_nowcast

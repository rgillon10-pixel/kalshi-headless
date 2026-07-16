"""collection.weather_actuals — cross-confirmation tagging (agree/disagree/single-source),
the structural settled-market join (hit/miss/error), and honest completeness/drop accounting.
Fully offline: an injected FakeHttp serves CLI/METAR fixtures and a FakeKalshi serves settled
markets — no live network, no clock injection needed beyond the injectable target_day."""
from __future__ import annotations

import json
from datetime import date

from collection import weather_actuals as wa

TARGET = date(2026, 7, 15)


# --------------------------------------------------------------------------- #
# fakes — only the methods the collector uses, served from in-memory fixtures
# --------------------------------------------------------------------------- #
class FakeHttp:
    """Stand-in for validation._http.Http. `.json` serves IEM CLI, `.text` serves the IEM
    METAR daily-summary CSV — the exact shapes v1_actuals.fetch_cli / fetch_metar parse."""

    def __init__(self, cli_by_station=None, metar_by_station=None,
                 fail_cli=(), fail_metar=()):
        self.cli_by_station = cli_by_station or {}       # station -> [{valid,high,low,name}]
        self.metar_by_station = metar_by_station or {}   # station -> [{day,max,min}]
        self.fail_cli = set(fail_cli)
        self.fail_metar = set(fail_metar)

    def json(self, url, **params):
        station = params["station"]
        if station in self.fail_cli:
            raise RuntimeError(f"simulated CLI failure: {station}")
        return {"results": self.cli_by_station.get(station, [])}

    def text(self, url, **params):
        station = params["stations"]
        if station in self.fail_metar:
            raise RuntimeError(f"simulated METAR failure: {station}")
        rows = self.metar_by_station.get(station, [])
        out = ["station,day,max_temp_f,min_temp_f"]
        for r in rows:
            out.append(f"{station},{r['day']},{r['max']},{r['min']}")
        return "\n".join(out)


class FakeKalshi:
    base = "https://fake.test"

    def __init__(self, markets_by_series=None, fail_series=()):
        self.markets_by_series = markets_by_series or {}
        self.fail_series = set(fail_series)

    def get_text(self, path, **params):
        assert path == "/markets"
        assert params["status"] == "settled"
        series = params["series_ticker"]
        if series in self.fail_series:
            raise RuntimeError(f"simulated settled fetch failure: {series}")
        return json.dumps({"markets": self.markets_by_series.get(series, [])})


def _cli(high, low, valid="2026-07-15", name="CENTRAL PARK"):
    return {"valid": valid, "high": high, "low": low, "name": name, "wfo": "OKX"}


def _metar(mx, mn, day="2026-07-15"):
    return {"day": day, "max": mx, "min": mn}


def _settled_market(ticker, event_ticker, result, expiration_value, close_time="2026-07-16T04:00:00Z"):
    return {"ticker": ticker, "event_ticker": event_ticker, "result": result,
            "expiration_value": expiration_value, "close_time": close_time}


# --------------------------------------------------------------------------- #
# cross-confirmation tagging — the core trust rule
# --------------------------------------------------------------------------- #
def test_reconcile_agree_within_tolerance_is_broker_truth():
    # cli high 90 vs metar max 90 (spread 0); cli low 70 vs metar min 71 (spread 1 == TOL_F)
    rec = wa.reconcile_actuals(_cli(90.0, 70.0), _metar(90.0, 71.0))
    assert rec["verdict"] == "clean"
    assert rec["high"]["source_tag"] == "broker_truth"
    assert rec["high"]["value"] == 90.0          # CLI is the settlement truth
    assert rec["low"]["source_tag"] == "broker_truth"
    assert rec["low"]["n_sources"] == 2


def test_reconcile_disagree_beyond_tolerance_is_unverifiable_never_upgraded():
    # cli high 90 vs metar max 94 -> spread 4 >= 2 -> dirty; NEVER broker_truth
    rec = wa.reconcile_actuals(_cli(90.0, 70.0), _metar(94.0, 70.0))
    assert rec["verdict"] == "dirty"
    assert rec["high"]["source_tag"] == "unverifiable"
    # a dirty day must not upgrade the (coincidentally-agreeing) low either
    assert rec["low"]["source_tag"] == "unverifiable"


def test_reconcile_single_source_is_unverifiable():
    # only CLI present (METAR did not post) -> one source -> unverifiable, value still recorded
    rec = wa.reconcile_actuals(_cli(88.0, 66.0), None)
    assert rec["verdict"] == "unverifiable"
    assert rec["high"]["source_tag"] == "unverifiable"
    assert rec["high"]["value"] == 88.0
    assert rec["high"]["n_sources"] == 1
    assert rec["sources_present"] == {"cli": True, "metar": False}


def test_reconcile_metar_only_value_falls_back_but_stays_unverifiable():
    rec = wa.reconcile_actuals(None, _metar(85.0, 60.0))
    assert rec["high"]["value"] == 85.0          # falls back to the single available source
    assert rec["high"]["source_tag"] == "unverifiable"
    assert rec["sources_present"]["cli"] is False


# --------------------------------------------------------------------------- #
# structural settled-market join — matches on the event ticker's own weather-day token
# --------------------------------------------------------------------------- #
def test_event_date_parsed_from_ticker_token():
    assert wa._event_date_from_ticker("KXHIGHTNYC-26JUL15") == date(2026, 7, 15)
    assert wa._event_date_from_ticker("KXLOWTNYC-26JUL15-T70") == date(2026, 7, 15)
    assert wa._event_date_from_ticker("garbage") is None


def test_fetch_settled_for_series_hit_only_target_day():
    markets = [
        _settled_market("KXHIGHTNYC-26JUL15-T88", "KXHIGHTNYC-26JUL15", "yes", "89"),
        _settled_market("KXHIGHTNYC-26JUL15-T90", "KXHIGHTNYC-26JUL15", "no", "89"),
        # a different day's settled event must be excluded
        _settled_market("KXHIGHTNYC-26JUL14-T80", "KXHIGHTNYC-26JUL14", "yes", "81"),
    ]
    client = FakeKalshi(markets_by_series={"KXHIGHTNYC": markets})
    r = wa.fetch_settled_for_series(client, "KXHIGHTNYC", TARGET)
    assert r["status"] == "ok"
    assert len(r["events"]) == 1
    ev = r["events"][0]
    assert ev["event_ticker"] == "KXHIGHTNYC-26JUL15"
    assert ev["expiration_value"] == "89"
    assert ev["price_source_tag"] == "broker_truth"
    assert ev["results"] == {"KXHIGHTNYC-26JUL15-T88": "yes", "KXHIGHTNYC-26JUL15-T90": "no"}


def test_fetch_settled_for_series_miss_returns_no_events():
    client = FakeKalshi(markets_by_series={"KXHIGHTNYC": [
        _settled_market("KXHIGHTNYC-26JUL14-T80", "KXHIGHTNYC-26JUL14", "yes", "81"),
    ]})
    r = wa.fetch_settled_for_series(client, "KXHIGHTNYC", TARGET)
    assert r["status"] == "ok" and r["events"] == []


def test_fetch_settled_for_series_fetch_error_is_honest():
    client = FakeKalshi(fail_series=["KXHIGHTNYC"])
    r = wa.fetch_settled_for_series(client, "KXHIGHTNYC", TARGET)
    assert r["status"] == "fetch_error" and r["events"] == []


def test_join_city_statuses():
    client = FakeKalshi(markets_by_series={
        "KXHIGHTNYC": [_settled_market("KXHIGHTNYC-26JUL15-T88", "KXHIGHTNYC-26JUL15", "yes", "89")],
        "KXLOWTNYC": [],
    })
    joined = wa.join_settled_for_city(client, ["KXHIGHTNYC", "KXLOWTNYC"], TARGET)
    assert joined["status"] == "joined" and len(joined["events"]) == 1

    none = wa.join_settled_for_city(client, ["KXLOWTNYC"], TARGET)
    assert none["status"] == "no_settled_market"

    empty = wa.join_settled_for_city(client, [], TARGET)
    assert empty["status"] == "no_series_configured"

    err_client = FakeKalshi(fail_series=["KXHIGHTNYC"])
    errd = wa.join_settled_for_city(err_client, ["KXHIGHTNYC"], TARGET)
    assert errd["status"] == "series_error" and errd["errors"]


# --------------------------------------------------------------------------- #
# end-to-end offline pass — completeness, drop accounting, tape shape
# --------------------------------------------------------------------------- #
_STATIONS = [
    {"city": "New York", "cli_station": "KNYC", "iem_station": "NYC", "iem_network": "NY_ASOS"},
    {"city": "Chicago", "cli_station": "KMDW", "iem_station": "MDW", "iem_network": "IL_ASOS"},
]
_CITY_SERIES = {"New York": ["KXHIGHTNYC", "KXLOWTNYC"], "Chicago": ["KXHIGHCHI", "KXLOWTCHI"]}


def _happy_http():
    return FakeHttp(
        cli_by_station={"KNYC": [_cli(90.0, 70.0)], "KMDW": [_cli(88.0, 66.0)]},
        metar_by_station={"NYC": [_metar(90.0, 71.0)], "MDW": [_metar(88.0, 66.0)]},
    )


def _happy_kalshi():
    return FakeKalshi(markets_by_series={
        "KXHIGHTNYC": [_settled_market("KXHIGHTNYC-26JUL15-T88", "KXHIGHTNYC-26JUL15", "yes", "89")],
        "KXLOWTNYC": [_settled_market("KXLOWTNYC-26JUL15-T70", "KXLOWTNYC-26JUL15", "yes", "70")],
        "KXHIGHCHI": [], "KXLOWTCHI": [],
    })


def test_run_end_to_end_offline(tmp_path):
    summary = wa.run(http=_happy_http(), client=_happy_kalshi(), store=tmp_path,
                     stations=_STATIONS, city_series=_CITY_SERIES, target_day=TARGET)
    assert summary["n_expected"] == 2
    assert summary["n_captured"] == 2
    assert summary["n_dropped"] == 0
    assert summary["completeness_ok"] is True
    assert summary["target_day"] == "2026-07-15"
    assert summary["tally"]["broker_truth_high"] == 2

    out_path = tmp_path / f"dt={summary['day']}.jsonl"
    recs = [json.loads(ln) for ln in out_path.read_text().splitlines()]
    assert {r["city"] for r in recs} == {"New York", "Chicago"}
    ny = next(r for r in recs if r["city"] == "New York")
    assert ny["schema_version"] == "weather_actuals.v1"
    assert ny["target_day"] == "2026-07-15"
    assert ny["actuals"]["high"]["source_tag"] == "broker_truth"
    assert ny["settled_markets"]["status"] == "joined"
    assert ny["settled_markets"]["events"][0]["expiration_value"] == "89"
    chi = next(r for r in recs if r["city"] == "Chicago")
    assert chi["settled_markets"]["status"] == "no_settled_market"


def test_run_actuals_fetch_failure_is_a_drop_not_silent(tmp_path):
    http = FakeHttp(
        cli_by_station={"KNYC": [_cli(90.0, 70.0)], "KMDW": [_cli(88.0, 66.0)]},
        metar_by_station={"NYC": [_metar(90.0, 71.0)], "MDW": [_metar(88.0, 66.0)]},
        fail_cli={"KMDW"},   # Chicago's CLI fetch raises -> Chicago is a drop
    )
    summary = wa.run(http=http, client=_happy_kalshi(), store=tmp_path,
                     stations=_STATIONS, city_series=_CITY_SERIES, target_day=TARGET)
    assert summary["n_captured"] == 1            # only New York persisted
    assert summary["n_dropped"] == 1
    assert summary["completeness_ok"] is False
    assert summary["drops"][0]["city"] == "Chicago"
    cities_in_tape = {json.loads(ln)["city"]
                      for ln in (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()}
    assert cities_in_tape == {"New York"}


def test_run_kalshi_settled_error_lowers_completeness(tmp_path):
    client = FakeKalshi(markets_by_series={"KXLOWTNYC": [], "KXHIGHCHI": [], "KXLOWTCHI": []},
                        fail_series=["KXHIGHTNYC"])
    summary = wa.run(http=_happy_http(), client=client, store=tmp_path,
                     stations=_STATIONS, city_series=_CITY_SERIES, target_day=TARGET)
    # the actuals still captured for every city (fault isolation), but the settled-fetch
    # exception is recorded and lowers completeness — never silently absorbed
    assert summary["n_captured"] == 2
    assert summary["n_kalshi_errors"] == 1
    assert summary["completeness_ok"] is False


def test_run_no_settled_market_does_not_gate_completeness(tmp_path):
    # every series returns empty (no event that day) -> honest no_settled_market, still complete
    client = FakeKalshi(markets_by_series={s: [] for s in
                                           ["KXHIGHTNYC", "KXLOWTNYC", "KXHIGHCHI", "KXLOWTCHI"]})
    summary = wa.run(http=_happy_http(), client=client, store=tmp_path,
                     stations=_STATIONS, city_series=_CITY_SERIES, target_day=TARGET)
    assert summary["completeness_ok"] is True
    assert summary["tally"]["settled_joined"] == 0


def test_run_defaults_target_day_to_yesterday(tmp_path):
    # no target_day -> previous UTC day; just assert it is strictly before the capture day
    summary = wa.run(http=_happy_http(), client=_happy_kalshi(), store=tmp_path,
                     stations=_STATIONS[:1], city_series=_CITY_SERIES)
    assert summary["target_day"] < summary["day"]


def test_run_limit_caps_cities(tmp_path):
    summary = wa.run(http=_happy_http(), client=_happy_kalshi(), store=tmp_path,
                     stations=_STATIONS, city_series=_CITY_SERIES, target_day=TARGET, limit=1)
    assert summary["n_expected"] == 1
    cities = {json.loads(ln)["city"]
              for ln in (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()}
    assert cities == {"New York"}


# --------------------------------------------------------------------------- #
# config loaders read the real repo config without raising
# --------------------------------------------------------------------------- #
def test_load_stations_includes_knyc_central_park():
    stations = wa._load_stations()
    ny = [s for s in stations if s.get("city") == "New York"]
    assert ny and ny[0]["cli_station"] == "KNYC"     # Central Park already covered


def test_load_city_series_maps_cities_to_kalshi_ladders():
    m = wa._load_city_series()
    assert "New York" in m
    assert all(isinstance(v, list) for v in m.values())

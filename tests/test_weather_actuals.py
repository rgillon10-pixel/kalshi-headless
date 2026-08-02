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


# --------------------------------------------------------------------------- #
# gap backfill (2026-08-02) — the scheduled leg is yesterday-only and its holes do not
# self-heal; `run()` always accepted `target_day` but nothing could reach it.
# Fully offline: the same FakeHttp/FakeKalshi fixtures, extended to several days.
# --------------------------------------------------------------------------- #
from datetime import datetime, timedelta, timezone   # noqa: E402

import pytest                                        # noqa: E402

_D15, _D16, _D17 = date(2026, 7, 15), date(2026, 7, 16), date(2026, 7, 17)
_NOW = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)      # so 07-15..07-17 are all CLOSED


def _multiday_http():
    """CLI + METAR rows for 07-15, 07-16 and 07-17 at both stations."""
    days = ["2026-07-15", "2026-07-16", "2026-07-17"]
    return FakeHttp(
        cli_by_station={
            "KNYC": [_cli(90.0, 70.0, valid=d) for d in days],
            "KMDW": [_cli(88.0, 66.0, valid=d) for d in days],
        },
        metar_by_station={
            "NYC": [_metar(90.0, 71.0, day=d) for d in days],
            "MDW": [_metar(88.0, 66.0, day=d) for d in days],
        },
    )


def _multiday_kalshi():
    return FakeKalshi(markets_by_series={
        "KXHIGHTNYC": [_settled_market(f"KXHIGHTNYC-26JUL{d}-T88",
                                       f"KXHIGHTNYC-26JUL{d}", "yes", "89")
                       for d in ("15", "16", "17")],
        "KXLOWTNYC": [], "KXHIGHCHI": [], "KXLOWTCHI": [],
    })


def _write_tape(tmp_path, records):
    """Seed the family's tape with pre-existing lines; `dt=` filename is deliberately NOT the
    target_day, so a coverage reader keyed on the filename would get the wrong answer."""
    path = tmp_path / "dt=2026-07-18.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        for target_day, city in records:
            f.write(json.dumps({"schema_version": "weather_actuals.v1",
                                "target_day": target_day, "city": city}) + "\n")
    return path


# ---- coverage reader ------------------------------------------------------- #
def test_covered_city_days_keys_on_target_day_not_filename(tmp_path):
    _write_tape(tmp_path, [("2026-07-15", "New York"), ("2026-07-16", "Chicago")])
    cov = wa.covered_city_days(store=tmp_path)
    assert cov == {"2026-07-15": {"New York"}, "2026-07-16": {"Chicago"}}
    assert "2026-07-18" not in cov            # the CAPTURE day is not a coverage key


def test_covered_city_days_malformed_line_is_not_coverage(tmp_path):
    p = _write_tape(tmp_path, [("2026-07-15", "New York")])
    with open(p, "a", encoding="utf-8") as f:
        f.write("{not json at all\n")
        f.write("\n")
    # conservative direction: an unparsable line can only cause a re-fetch, never hide a gap
    assert wa.covered_city_days(store=tmp_path) == {"2026-07-15": {"New York"}}


def test_covered_city_days_missing_dir_is_empty(tmp_path):
    assert wa.covered_city_days(store=tmp_path / "nope") == {}


# ---- gap enumeration ------------------------------------------------------- #
def test_missing_city_days_omits_complete_days_and_names_partial_ones(tmp_path):
    _write_tape(tmp_path, [("2026-07-15", "New York"), ("2026-07-15", "Chicago"),
                           ("2026-07-16", "New York")])
    gaps = wa.missing_city_days(_D15, _D17, stations=_STATIONS, store=tmp_path)
    assert [d for d, _c in gaps] == [_D16, _D17]          # 07-15 complete -> omitted
    assert dict((d, c) for d, c in gaps)[_D16] == ["Chicago"]     # partial -> only the hole
    assert dict((d, c) for d, c in gaps)[_D17] == ["New York", "Chicago"]


def test_missing_city_days_empty_window_is_empty(tmp_path):
    assert wa.missing_city_days(_D17, _D15, stations=_STATIONS, store=tmp_path) == []


# ---- closed-day guard ------------------------------------------------------ #
def test_require_closed_day_refuses_today_and_future():
    for bad in (_NOW.date(), _NOW.date() + timedelta(days=1)):
        with pytest.raises(ValueError, match="CLOSED"):
            wa._require_closed_day(bad, now=_NOW)
    assert wa._require_closed_day(_D17, now=_NOW) == _D17


def test_backfill_refuses_a_window_that_is_not_closed(tmp_path):
    with pytest.raises(ValueError, match="CLOSED"):
        wa.backfill(since=_D15, until=_NOW.date(), now=_NOW, store=tmp_path,
                    stations=_STATIONS, city_series=_CITY_SERIES,
                    http=_multiday_http(), client=_multiday_kalshi())


# ---- backfill behaviour ---------------------------------------------------- #
def test_backfill_fills_only_the_missing_city_days(tmp_path):
    _write_tape(tmp_path, [("2026-07-15", "New York"), ("2026-07-15", "Chicago"),
                           ("2026-07-16", "New York")])
    out = wa.backfill(since=_D15, until=_D17, now=_NOW, store=tmp_path,
                      stations=_STATIONS, city_series=_CITY_SERIES,
                      http=_multiday_http(), client=_multiday_kalshi())
    assert out["mode"] == "backfill"
    assert out["n_days_with_gaps"] == 2 and out["n_days_attempted"] == 2
    assert out["n_days_deferred"] == 0 and out["deferred_days"] == []
    # 07-16 was missing ONE city, 07-17 both -> 3 city-days, not 6
    assert out["n_city_days_expected"] == 3
    assert out["n_city_days_captured"] == 3
    assert out["completeness_ok"] is True

    written = [json.loads(ln) for p in sorted(tmp_path.glob("dt=*.jsonl"))
               for ln in p.read_text().splitlines() if "capture_id" in ln]
    got = sorted((r["target_day"], r["city"]) for r in written)
    assert got == [("2026-07-16", "Chicago"),
                   ("2026-07-17", "Chicago"), ("2026-07-17", "New York")]
    assert all(r["schema_version"] == "weather_actuals.v1" for r in written)
    # a backfilled line is shaped exactly like a scheduled one and needs NO new field:
    # target_day != capture_day - 1 is what distinguishes it (L222 write-path stays shut)
    assert all(r["target_day"] < r["captured_at"][:10] for r in written)


def test_backfill_is_idempotent_second_pass_finds_no_gaps(tmp_path):
    first = wa.backfill(since=_D15, until=_D17, now=_NOW, store=tmp_path,
                        stations=_STATIONS, city_series=_CITY_SERIES,
                        http=_multiday_http(), client=_multiday_kalshi())
    assert first["n_city_days_captured"] == 6
    second = wa.backfill(since=_D15, until=_D17, now=_NOW, store=tmp_path,
                         stations=_STATIONS, city_series=_CITY_SERIES,
                         http=_multiday_http(), client=_multiday_kalshi())
    assert second["n_days_with_gaps"] == 0
    assert second["n_days_attempted"] == 0
    assert second["n_city_days_captured"] == 0
    assert second["completeness_ok"] is True     # nothing to do is complete, not a failure


def test_backfill_max_days_defers_the_rest_and_says_so(tmp_path):
    out = wa.backfill(since=_D15, until=_D17, now=_NOW, max_days=1, store=tmp_path,
                      stations=_STATIONS, city_series=_CITY_SERIES,
                      http=_multiday_http(), client=_multiday_kalshi())
    assert out["n_days_with_gaps"] == 3
    assert out["n_days_attempted"] == 1
    assert out["n_days_deferred"] == 2
    assert out["deferred_days"] == ["2026-07-16", "2026-07-17"]   # oldest-first, none dropped
    assert {json.loads(ln)["target_day"]
            for p in tmp_path.glob("dt=*.jsonl")
            for ln in p.read_text().splitlines()} == {"2026-07-15"}


def test_backfill_default_until_is_yesterday(tmp_path):
    out = wa.backfill(since=_D17, now=_NOW, store=tmp_path,
                      stations=_STATIONS, city_series=_CITY_SERIES,
                      http=_multiday_http(), client=_multiday_kalshi())
    assert out["until"] == "2026-07-17"           # _NOW is 07-18


def test_backfill_drop_lowers_completeness_and_is_named(tmp_path):
    http = _multiday_http()
    http.fail_cli = {"KMDW"}                      # Chicago's CLI fetch raises on every day
    out = wa.backfill(since=_D17, until=_D17, now=_NOW, store=tmp_path,
                      stations=_STATIONS, city_series=_CITY_SERIES,
                      http=http, client=_multiday_kalshi())
    assert out["completeness_ok"] is False
    assert out["n_days_incomplete"] == 1
    assert out["n_city_days_dropped"] == 1
    assert out["days"][0]["drops"][0]["city"] == "Chicago"


# ---- CLI surface ----------------------------------------------------------- #
def test_cli_default_path_is_unchanged(monkeypatch):
    seen = {}

    def _fake_run(**kw):
        seen.update(kw)
        return {"completeness_ok": True}

    monkeypatch.setattr(wa, "run", _fake_run)
    assert wa.main([]) == 0
    assert "target_day" not in seen               # default stays yesterday-relative
    assert seen == {"min_interval": 0.25, "limit": None}


def test_cli_target_day_is_passed_through_and_gates_exit_code(monkeypatch):
    seen = {}

    def _fake_run(**kw):
        seen.update(kw)
        return {"completeness_ok": False}

    monkeypatch.setattr(wa, "run", _fake_run)
    assert wa.main(["--target-day", "2026-07-15"]) == 1      # incomplete -> non-zero
    assert seen["target_day"] == _D15


def test_cli_refuses_a_future_target_day(monkeypatch, capsys):
    monkeypatch.setattr(wa, "run", lambda **kw: pytest.fail("run must not be reached"))
    future = (datetime.now(timezone.utc).date() + timedelta(days=2)).isoformat()
    assert wa.main(["--target-day", future]) == 2
    assert "REFUSED" in capsys.readouterr().err


def test_cli_backfill_requires_since_and_rejects_mixed_flags(monkeypatch):
    monkeypatch.setattr(wa, "backfill", lambda **kw: pytest.fail("backfill must not be reached"))
    for argv in (["--backfill-missing"],
                 ["--backfill-missing", "--target-day", "2026-07-15"],
                 ["--since", "2026-07-15"],
                 ["--until", "2026-07-15"]):
        with pytest.raises(SystemExit) as exc:
            wa.main(argv)
        assert exc.value.code == 2


def test_cli_backfill_passes_window_through(monkeypatch):
    seen = {}

    def _fake_backfill(**kw):
        seen.update(kw)
        return {"completeness_ok": True}

    monkeypatch.setattr(wa, "backfill", _fake_backfill)
    assert wa.main(["--backfill-missing", "--since", "2026-07-15",
                    "--until", "2026-07-17", "--max-days", "3"]) == 0
    assert seen["since"] == _D15 and seen["until"] == _D17 and seen["max_days"] == 3


# ---- hollow days: records exist, settlement truth does not ----------------- #
# Discovered by the 2026-08-02 backfill itself: its 2026-08-01 pass captured 20/20 cities with
# broker_truth actuals and joined ZERO settled markets (Kalshi had not settled the daily ladders
# at 09:24Z). `covered_city_days` marks that day complete forever; this reader does not.
def _tape_line(target_day, city, joined):
    rec = {"schema_version": "weather_actuals.v1", "target_day": target_day, "city": city,
           "settled_markets": {"status": "joined" if joined else "no_settled_market",
                               "events": [{"event_ticker": "KXHIGHTNYC-26JUL15"}] if joined
                               else []}}
    return json.dumps(rec)


def _write_join_tape(tmp_path, rows):
    with open(tmp_path / "dt=2026-08-02.jsonl", "a", encoding="utf-8") as f:
        for target_day, city, joined in rows:
            f.write(_tape_line(target_day, city, joined) + "\n")


def test_settlement_join_by_day_separates_records_from_truth(tmp_path):
    _write_join_tape(tmp_path, [("2026-07-15", "New York", True),
                                ("2026-07-15", "Chicago", False),
                                ("2026-08-01", "New York", False),
                                ("2026-08-01", "Chicago", False)])
    joins = wa.settlement_join_by_day(store=tmp_path)
    assert joins["2026-07-15"] == {"n_records": 2, "n_joined": 1}
    assert joins["2026-08-01"] == {"n_records": 2, "n_joined": 0}


def test_unsettled_days_flags_the_hollow_day_only(tmp_path):
    _write_join_tape(tmp_path, [("2026-07-15", "New York", True),
                                ("2026-08-01", "New York", False)])
    assert wa.unsettled_days(_D15, date(2026, 8, 1), store=tmp_path) == ["2026-08-01"]
    # a day with no records at all is a `missing_city_days` question, not a hollow-day one
    assert wa.unsettled_days(date(2026, 7, 10), date(2026, 7, 14), store=tmp_path) == []


def test_backfill_reports_hollow_days_it_just_wrote(tmp_path, capsys):
    # every series empty -> honest no_settled_market for both cities on both days
    client = FakeKalshi(markets_by_series={s: [] for s in
                                           ["KXHIGHTNYC", "KXLOWTNYC", "KXHIGHCHI", "KXLOWTCHI"]})
    out = wa.backfill(since=_D16, until=_D17, now=_NOW, store=tmp_path,
                      stations=_STATIONS, city_series=_CITY_SERIES,
                      http=_multiday_http(), client=client)
    assert out["completeness_ok"] is True          # a genuine absence is not a failure (L23)
    assert out["n_unsettled_days"] == 2
    assert out["unsettled_days"] == ["2026-07-16", "2026-07-17"]
    assert "ZERO settled-market joins" in capsys.readouterr().err


def test_backfill_with_settlement_reports_no_hollow_days(tmp_path):
    out = wa.backfill(since=_D15, until=_D15, now=_NOW, store=tmp_path,
                      stations=_STATIONS[:1], city_series=_CITY_SERIES,
                      http=_multiday_http(), client=_multiday_kalshi())
    assert out["n_unsettled_days"] == 0 and out["unsettled_days"] == []

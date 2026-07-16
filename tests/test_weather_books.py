"""collection.weather_books — fully offline (FakeClient, no network, injected config).

Covers: two-group discovery (config+sweep union, sweep-only detection so a new series can't
silently drop, hourly-directional classification + KXTEMPNYCH seed, exclusion of hourly/US
titles from the daily group), full capture completeness, both orderbook shapes (modern
`orderbook_fp` string-dollars AND legacy integer-cents `orderbook`), the derived best-ask
math, source tags, dropped-ticker + series-enumeration completeness lowering, empty-book !=
drop (L23), the truncation cap (L10), a config series with zero open markets NOT being a
failure, and once-per-(series,day) metadata dedup."""
from __future__ import annotations

import json

import pytest
import yaml

from collection import weather_books as wb


# --------------------------------------------------------------------------- #
# fixtures / FakeClient
# --------------------------------------------------------------------------- #
def _cfg(tmp_path):
    doc = {
        "cities": [
            {"city": "New York",
             "kalshi": {"high_series": ["KXHIGHNY"], "low_series": ["KXLOWTNYC"]}},
            {"city": "Boston",
             "kalshi": {"high_series": ["KXHIGHTBOS"], "low_series": ["KXLOWTBOS"]}},
            # a config series with NO live open markets this pass (off-season / renamed)
            {"city": "Ghost", "kalshi": {"high_series": ["KXHIGHGONE"], "low_series": []}},
        ]
    }
    p = tmp_path / "cities.yaml"
    p.write_text(yaml.safe_dump(doc))
    return p


# category sweep series (ticker, title). Daily = HIGH/LOW temp; excludes US + hourly.
_CATALOG = [
    {"ticker": "KXHIGHNY", "title": "Highest temperature in NYC"},
    {"ticker": "KXLOWTNYC", "title": "Lowest temperature in NYC"},
    {"ticker": "KXHIGHTBOS", "title": "Boston Maximum Daily Temperature"},
    {"ticker": "KXLOWTBOS", "title": "Low Temperature Boston"},
    {"ticker": "KXHIGHTDAL", "title": "Dallas Maximum Temperature"},   # sweep-only (not in cfg)
    {"ticker": "KXHIGHUS", "title": "High temp in United States"},     # excluded (US)
    {"ticker": "KXHIGHNYD", "title": "Hourly Directional NYC Temperature"},  # hourly (not daily)
    {"ticker": "KXTEMPNYCH", "title": "Hourly Directional NYC Temperature"},  # hourly
    {"ticker": "KXGTEMP", "title": "Hottest year ever"},              # neither
]


def _mkt(ticker, close="2026-07-17T04:59:00Z", strike_type="greater", floor=90, cap=None):
    return {"ticker": ticker, "close_time": close, "strike_type": strike_type,
            "floor_strike": floor, "cap_strike": cap, "yes_sub_title": f"{floor}° or above",
            "rules_primary": f"rules for {ticker}", "rules_secondary": "settles on X"}


def _ob_fp(yes_levels, no_levels):
    """Modern orderbook_fp: yes_dollars / no_dollars are [[price_str, size_str], ...] (bids)."""
    return {"orderbook_fp": {
        "yes_dollars": [[str(p), str(s)] for p, s in yes_levels],
        "no_dollars": [[str(p), str(s)] for p, s in no_levels]}}


def _ob_legacy(yes_cents, no_cents):
    """Legacy integer-cents orderbook: {"orderbook": {"yes": [[cents, size], ...], "no": ...}}."""
    return {"orderbook": {"yes": [[c, s] for c, s in yes_cents],
                          "no": [[c, s] for c, s in no_cents]}}


class FakeClient:
    base = "https://fake.test"

    def __init__(self, catalog=None, markets_by_series=None, books=None, details=None,
                 fail_series=(), fail_tickers=(), catalog_raises=False):
        self.catalog = _CATALOG if catalog is None else catalog
        self.markets_by_series = markets_by_series or {}
        self.books = books or {}
        self.details = details or {}
        self.fail_series = set(fail_series)
        self.fail_tickers = set(fail_tickers)
        self.catalog_raises = catalog_raises
        self.detail_calls = []

    def series_by_category(self, category):
        assert category == wb.WEATHER_CATEGORY
        if self.catalog_raises:
            raise RuntimeError("category sweep failed")
        return list(self.catalog)

    def open_markets(self, series_ticker):
        if series_ticker in self.fail_series:
            raise RuntimeError(f"enumeration failure: {series_ticker}")
        return list(self.markets_by_series.get(series_ticker, []))

    def get_text(self, path, **params):
        assert path.startswith("/markets/") and path.endswith("/orderbook")
        ticker = path[len("/markets/"):-len("/orderbook")]
        if ticker in self.fail_tickers:
            raise RuntimeError(f"orderbook fetch failure: {ticker}")
        return json.dumps(self.books.get(ticker, {}))

    def series_detail(self, ticker):
        self.detail_calls.append(ticker)
        return self.details.get(ticker, {"title": ticker, "settlement_sources": [],
                                         "fee_type": "quadratic", "fee_multiplier": 1,
                                         "frequency": "daily", "contract_url": None})


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def test_discovery_union_and_sweep_only(tmp_path):
    client = FakeClient(markets_by_series={})   # discovery only, no markets needed
    by_group, report, series_errors = wb.discover(client, config_path=_cfg(tmp_path))

    # daily = config series UNION sweep-classified daily series
    assert set(report["daily_series_captured"]) == {
        "KXHIGHNY", "KXLOWTNYC", "KXHIGHTBOS", "KXLOWTBOS", "KXHIGHTDAL", "KXHIGHGONE"}
    # the sweep found a daily series NOT in config -> surfaced, never silently dropped
    assert report["sweep_only_daily"] == ["KXHIGHTDAL"]
    # a config series absent from the live sweep is surfaced too
    assert report["config_only_daily"] == ["KXHIGHGONE"]
    # US + hourly + non-temp titles are excluded from daily
    for junk in ("KXHIGHUS", "KXHIGHNYD", "KXTEMPNYCH", "KXGTEMP"):
        assert junk not in report["daily_series_captured"]


def test_discovery_hourly_seed_and_classification(tmp_path):
    client = FakeClient(markets_by_series={})
    _, report, _ = wb.discover(client, config_path=_cfg(tmp_path))
    # hourly-directional-temperature titles, plus the KXTEMPNYCH seed guarantee
    assert set(report["hourly_series_captured"]) == {"KXHIGHNYD", "KXTEMPNYCH"}


def test_discovery_hourly_seed_survives_empty_sweep(tmp_path):
    client = FakeClient(catalog=[], markets_by_series={})
    _, report, _ = wb.discover(client, config_path=_cfg(tmp_path))
    # even with zero sweep hits, the seed keeps KXTEMPNYCH from dropping
    assert report["hourly_series_captured"] == ["KXTEMPNYCH"]


def test_discovery_catalog_failure_is_a_series_error(tmp_path):
    client = FakeClient(catalog_raises=True, markets_by_series={})
    _, report, series_errors = wb.discover(client, config_path=_cfg(tmp_path))
    assert any(e["group"] == "catalog" for e in series_errors)
    # config-seeded daily series still discovered despite the sweep failing
    assert "KXHIGHNY" in report["daily_series_captured"]


# --------------------------------------------------------------------------- #
# capture: full pass, record shape, derived asks
# --------------------------------------------------------------------------- #
def _full_client(tmp_path_books=None):
    markets = {
        "KXHIGHNY": [_mkt("KXHIGHNY-26JUL16-T96", floor=96)],
        "KXLOWTNYC": [_mkt("KXLOWTNYC-26JUL16-T70", floor=70)],
        "KXHIGHTBOS": [_mkt("KXHIGHTBOS-26JUL16-T92", floor=92)],
        "KXLOWTBOS": [_mkt("KXLOWTBOS-26JUL16-T65", floor=65)],
        "KXHIGHTDAL": [_mkt("KXHIGHTDAL-26JUL16-T100", floor=100)],
        "KXTEMPNYCH": [_mkt("KXTEMPNYCH-26JUL1522-T80.99", floor=80.99,
                            close="2026-07-16T02:00:00Z")],
        "KXHIGHNYD": [_mkt("KXHIGHNYD-26JUL1522-T80", floor=80)],
        # KXHIGHGONE: config series, no open markets -> NOT a failure
    }
    books = {m[0]["ticker"]: _ob_fp([[0.40, 100], [0.39, 250]], [[0.58, 80]])
             for m in markets.values()}
    return FakeClient(markets_by_series=markets, books=books)


def test_run_full_capture_completeness_ok(tmp_path):
    client = _full_client()
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    assert summary["n_expected"] == 7      # 5 daily open + 2 hourly open
    assert summary["n_captured"] == 7
    assert summary["n_lines"] == 7
    assert summary["completeness_ok"] is True
    assert summary["truncated"] is False
    assert summary["n_series_errors"] == 0
    # KXHIGHGONE (config, zero open markets) must NOT count as a failure
    assert summary["completeness_ok"] is True
    recs = [json.loads(ln) for ln in
            (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()]
    assert {r["group"] for r in recs} == {"daily", "hourly"}


def test_run_record_shape_and_derived_asks(tmp_path):
    client = _full_client()
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    recs = {json.loads(ln)["ticker"]: json.loads(ln) for ln in
            (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()}
    r = recs["KXHIGHNY-26JUL16-T96"]
    assert r["schema_version"] == "weather_books.v1"
    assert r["venue"] == "kalshi" and r["series"] == "KXHIGHNY" and r["group"] == "daily"
    assert r["close_time"] == "2026-07-17T04:59:00Z"
    assert r["book_shape"] == "orderbook_fp"
    assert r["yes_bids"] == [[0.40, 100], [0.39, 250]]
    assert r["no_bids"] == [[0.58, 80]]
    assert r["best_yes_bid"] == 0.40 and r["best_no_bid"] == 0.58
    # derived ask = 1 - opposite best bid
    assert r["best_yes_ask"] == pytest.approx(1 - 0.58)
    assert r["best_no_ask"] == pytest.approx(1 - 0.40)
    assert r["depth"] == 3
    assert "raw_orderbook" in r and "raw_sha256" in r


def test_source_tags_are_real_ask(tmp_path):
    client = _full_client()
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["price_source_tag"] == "real_ask"
    assert rec["price_source_tags"] == {"asks": "real_ask", "bids": "real_bid"}


# --------------------------------------------------------------------------- #
# both orderbook shapes parse identically through normalize
# --------------------------------------------------------------------------- #
def test_legacy_integer_cents_orderbook_shape(tmp_path):
    markets = {"KXHIGHNY": [_mkt("KXHIGHNY-26JUL16-T96", floor=96)]}
    books = {"KXHIGHNY-26JUL16-T96": _ob_legacy([[40, 100], [39, 250]], [[58, 80]])}
    client = FakeClient(catalog=[{"ticker": "KXHIGHNY", "title": "Highest temperature in NYC"}],
                        markets_by_series=markets, books=books)
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    rec = [json.loads(ln) for ln in
           (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
           if json.loads(ln)["ticker"] == "KXHIGHNY-26JUL16-T96"][0]
    assert rec["book_shape"] == "orderbook_legacy"
    # cents -> dollars, same downstream math as the modern shape
    assert rec["yes_bids"] == [[0.40, 100], [0.39, 250]]
    assert rec["no_bids"] == [[0.58, 80]]
    assert rec["best_yes_ask"] == pytest.approx(1 - 0.58)
    assert summary["book_shapes"].get("orderbook_legacy", 0) >= 1


def test_empty_book_is_captured_not_dropped(tmp_path):
    markets = {"KXHIGHNY": [_mkt("KXHIGHNY-26JUL16-T96", floor=96)]}
    books = {"KXHIGHNY-26JUL16-T96": {}}   # empty payload -> valid empty book (L23)
    client = FakeClient(catalog=[{"ticker": "KXHIGHNY", "title": "Highest temperature in NYC"}],
                        markets_by_series=markets, books=books)
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    assert summary["n_captured"] == 1
    assert summary["completeness_ok"] is True
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["yes_bids"] == [] and rec["no_bids"] == []
    assert rec["depth"] == 0
    assert rec["best_yes_ask"] is None and rec["best_no_ask"] is None
    assert rec["book_shape"] == "empty"


# --------------------------------------------------------------------------- #
# honest completeness: drops and enumeration errors lower it
# --------------------------------------------------------------------------- #
def test_dropped_ticker_lowers_completeness(tmp_path):
    client = _full_client()
    client.fail_tickers.add("KXTEMPNYCH-26JUL1522-T80.99")
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    assert summary["n_captured"] == 6
    assert summary["completeness_ok"] is False
    assert summary["dropped"] == ["KXTEMPNYCH-26JUL1522-T80.99"]


def test_series_enumeration_error_lowers_completeness(tmp_path):
    client = _full_client()
    client.fail_series.add("KXHIGHTBOS")
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    assert summary["n_series_errors"] == 1
    assert summary["completeness_ok"] is False


def test_config_series_zero_markets_is_not_a_failure(tmp_path):
    # KXHIGHGONE is a config series with no open markets; everything else captures cleanly
    client = _full_client()
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path))
    assert "KXHIGHGONE" in summary["discovery"]["daily_series_captured"]
    assert summary["completeness_ok"] is True   # zero-market series never gated it


# --------------------------------------------------------------------------- #
# memory cap (L10)
# --------------------------------------------------------------------------- #
def test_truncation_flag(tmp_path):
    client = _full_client()
    summary = wb.run(client=client, store=tmp_path, config_path=_cfg(tmp_path), limit=3)
    assert summary["truncated"] is True
    assert summary["n_expected"] == 3
    assert summary["completeness_ok"] is False   # truncation is honest incompleteness


# --------------------------------------------------------------------------- #
# metadata once per (series, day), deduped across passes
# --------------------------------------------------------------------------- #
def test_meta_written_once_per_series_day(tmp_path):
    client = _full_client()
    cfg = _cfg(tmp_path)
    s1 = wb.run(client=client, store=tmp_path, config_path=cfg)
    meta_path = tmp_path / "meta" / f"dt={s1['day']}.jsonl"
    metas = [json.loads(ln) for ln in meta_path.read_text().splitlines()]
    # one meta per series that had an open market (7 markets across these series)
    series_with_markets = {"KXHIGHNY", "KXLOWTNYC", "KXHIGHTBOS", "KXLOWTBOS",
                           "KXHIGHTDAL", "KXTEMPNYCH", "KXHIGHNYD"}
    assert {m["series"] for m in metas} == series_with_markets
    assert all(m["schema_version"] == "weather_series_meta.v1" for m in metas)
    assert all("settlement_sources" in m and "rules_primary" in m for m in metas)

    # second pass same day writes NO new meta lines (deduped)
    s2 = wb.run(client=client, store=tmp_path, config_path=cfg)
    assert s2["n_meta_written"] == 0
    metas2 = meta_path.read_text().splitlines()
    assert len(metas2) == len(metas)

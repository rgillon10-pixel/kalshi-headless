"""Offline tests for the OBS-1 Observatory pilot (analysis/observatory/).

All synthetic — no network, no reads of the real committed tape. Fixture tape is
authored inline per-test so every expectation is visible next to its input.
"""
import json

import pytest

from analysis.observatory import features, graveyard, ledger, screens


# ── helpers ────────────────────────────────────────────────────────────────────


def _write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _us_row(ticker, yes_bid, yes_ask, captured_at="2026-07-20T01:00:00+00:00",
            vol=10.0, tag="real_ask"):
    return {"ticker": ticker, "yes_bid": yes_bid, "yes_ask": yes_ask,
            "volume_24h": vol, "captured_at": captured_at, "price_source_tag": tag}


def _series_rows(series, n=5, spread=0.02, mid=0.50, tag="real_ask"):
    return [_us_row("{}-26JUL20-M{}".format(series, i),
                    round(mid - spread / 2, 4), round(mid + spread / 2, 4), tag=tag)
            for i in range(n)]


# ── features ───────────────────────────────────────────────────────────────────


def test_universe_extractor_last_capture_dedupe_and_two_sided(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    _write_jsonl(p, [
        # same ticker twice — later capture (wider spread) must win
        _us_row("KXAAA-26JUL20-T1", 0.40, 0.44, "2026-07-20T00:00:00+00:00"),
        _us_row("KXAAA-26JUL20-T1", 0.40, 0.50, "2026-07-20T02:00:00+00:00"),
        # one-sided market: counted, excluded from spread median
        _us_row("KXAAA-26JUL20-T2", 0.0, 0.99),
        "not-a-dict-will-be-bad",  # malformed line must be COUNTED, not dropped silently
    ][:3] + [{"garbage": True}])  # dict with no ticker -> also a bad line
    rows = features.extract_universe_sweep(p)
    assert len(rows) == 1
    r = rows[0]
    assert r["series"] == "KXAAA"
    assert r["n_markets"] == 2
    assert r["n_two_sided"] == 1
    assert r["median_spread"] == pytest.approx(0.10)
    assert r["n_bad_lines"] == 1
    assert r["price_source_tags"] == ["real_ask"]


def test_universe_extractor_untagged_defaults_synthetic(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    row = _us_row("KXBBB-26JUL20-T1", 0.4, 0.5)
    del row["price_source_tag"]
    _write_jsonl(p, [row])
    rows = features.extract_universe_sweep(p)
    assert rows[0]["price_source_tags"] == ["synthetic"]  # trust=FALSE default


def test_orderbook_depth_extractor(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    _write_jsonl(p, [{
        "ticker": "KXCCC-26JUL20-T1", "captured_at": "2026-07-20T01:00:00+00:00",
        "best_yes_ask": 0.55, "best_yes_bid": 0.45, "depth": 12,
        "no_bids": [[0.45, 300.0], [0.40, 10.0]], "yes_bids": [],
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
    }])
    r = features.extract_orderbook_depth(p)[0]
    assert r["median_spread"] == pytest.approx(0.10)
    assert r["median_touch_queue"] == pytest.approx(300.0)
    assert r["price_source_tags"] == ["real_ask", "real_bid"]


def test_sports_pairs_extractor(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    _write_jsonl(p, [
        {"event_ticker": "KXDDD-E1", "sport_series": "KXDDD", "overround": 0.05,
         "completeness_ok": True, "captured_at": "t1", "price_source_tag": "real_ask"},
        {"event_ticker": "KXDDD-E2", "sport_series": "KXDDD", "overround": 0.15,
         "completeness_ok": False, "captured_at": "t1", "price_source_tag": "real_ask"},
    ])
    r = features.extract_sports_pairs(p)[0]
    assert r["n_events"] == 2
    assert r["median_overround"] == pytest.approx(0.10)
    assert r["completeness_rate"] == pytest.approx(0.5)


# ── screens ────────────────────────────────────────────────────────────────────


def _cross_section(outlier_spread=0.40):
    """9 normal series (2c spread) + 1 planted wide-spread outlier."""
    rows = []
    for i in range(9):
        rows.extend(_series_rows("KXN{:02d}".format(i)))
    rows.extend(_series_rows("KXOUT", spread=outlier_spread))
    return rows


def test_outlier_screen_flags_planted_outlier(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    _write_jsonl(p, _cross_section())
    agg = features.extract_universe_sweep(p)
    out = screens.outlier_screen("universe_sweep", "2026-07-20", agg)
    flagged = [f for f in out["flags"] if f["metric"] == "median_spread"]
    assert len(flagged) == 1
    f = flagged[0]
    assert f["series"] == "KXOUT" and f["direction"] == "high"
    assert abs(f["robust_z"]) >= screens.Z_MIN
    assert ["universe_sweep", "median_spread"] in out["screened"]
    # graveyard: wide-spread maker capture is the DEAD S6/S13 family -> blocked
    assert f["factor_family"] == "naive-maker-spread"
    assert f["graveyard_blocked"] is True
    # fee floor: half of 40c spread >> maker fee at mid -> cleared
    assert f["fee_floor_cleared"] is True


def test_outlier_screen_thin_cross_section_skips(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    _write_jsonl(p, _series_rows("KXA") + _series_rows("KXB", spread=0.4))
    agg = features.extract_universe_sweep(p)
    out = screens.outlier_screen("universe_sweep", "2026-07-20", agg)
    assert out["flags"] == []
    assert ["universe_sweep", "median_spread"] not in out["screened"]


def test_fee_floor_requires_fillable_tags(tmp_path):
    p = tmp_path / "dt=2026-07-20.jsonl"
    rows = _cross_section()
    _write_jsonl(p, rows)
    agg = features.extract_universe_sweep(p)
    # poison the outlier row's provenance -> fee claim must vanish, flag remains
    for r in agg:
        if r["series"] == "KXOUT":
            r["price_source_tags"] = ["midpoint"]
    out = screens.outlier_screen("universe_sweep", "2026-07-20", agg)
    f = [x for x in out["flags"] if x["series"] == "KXOUT"][0]
    assert f["fee_floor"] is None and f["fee_floor_cleared"] is None


def test_fee_floor_spread_math():
    row = {"median_spread": 0.02, "median_mid": 0.50, "n_markets": 10,
           "price_source_tags": ["real_ask"]}
    fee = screens._fee_check("median_spread", "high", row)
    # half-spread 1c == maker fee 1c (round-up) -> margin 0, NOT cleared
    assert fee["cleared"] is False and fee["margin"] == pytest.approx(0.0)


def test_graveyard_unmapped_blocked_by_default():
    c = graveyard.classify("brand_new_metric", "high")
    assert c["graveyard_blocked"] is True  # trust=FALSE default


# ── ledger ─────────────────────────────────────────────────────────────────────


def _flag(dt, series="KXOUT", fee=True, metric="median_spread", direction="high",
          family="universe_sweep", blocked=False):
    return {"family": family, "series": series, "metric": metric,
            "direction": direction, "dt": dt, "value": 0.4, "robust_z": 6.0,
            "cross_section_n": 10, "row_n": 5, "price_source_tags": ["real_ask"],
            "factor_family": "tight-spread-regime", "nearest_dead_cousin": None,
            "graveyard_blocked": blocked, "fee_floor": {"cleared": fee},
            "fee_floor_cleared": fee}


SCREENED = {("universe_sweep", "median_spread")}


def test_ledger_persistence_and_candidate(tmp_path):
    lp = tmp_path / "patterns.jsonl"
    for i, dt in enumerate(["2026-07-18", "2026-07-19", "2026-07-20"]):
        res = ledger.reconcile([_flag(dt)], dt, SCREENED, ledger_path=lp)
    state = list(res["state"].values())
    assert len(state) == 1
    p = state[0]
    assert len(p["hit_days"]) == 3
    # 3 distinct hit days + fee cleared + not blocked -> candidate
    assert p["status"] == "candidate"


def test_ledger_blocked_family_never_auto_promotes(tmp_path):
    lp = tmp_path / "patterns.jsonl"
    for dt in ["2026-07-18", "2026-07-19", "2026-07-20"]:
        res = ledger.reconcile([_flag(dt, blocked=True)], dt, SCREENED, ledger_path=lp)
    p = list(res["state"].values())[0]
    assert p["status"] == "persistent"  # NOT candidate — graveyard gate holds
    # a human-authored rationale unblocks it
    ledger.append_events([{"event": "annotate", "pattern_id": p["pattern_id"],
                           "survival_rationale": "different fill mechanism than S6"}],
                         ledger_path=lp)
    state = ledger.replay(ledger.read_events(ledger_path=lp))
    assert state[p["pattern_id"]]["status"] == "candidate"


def test_ledger_miss_accrual_and_expiry(tmp_path):
    lp = tmp_path / "patterns.jsonl"
    ledger.reconcile([_flag("2026-07-10")], "2026-07-10", SCREENED, ledger_path=lp)
    # 5 screened days with no flag for this key -> expired
    for i in range(5):
        dt = "2026-07-1{}".format(i + 1)
        res = ledger.reconcile([], dt, SCREENED, ledger_path=lp)
    p = list(res["state"].values())[0]
    assert p["consecutive_misses"] == 5
    assert p["status"] == "expired"


def test_ledger_unscreened_metric_records_nothing(tmp_path):
    lp = tmp_path / "patterns.jsonl"
    ledger.reconcile([_flag("2026-07-10")], "2026-07-10", SCREENED, ledger_path=lp)
    # next day this family/metric was NOT screened (thin cross-section) -> no miss
    res = ledger.reconcile([], "2026-07-11", set(), ledger_path=lp)
    p = list(res["state"].values())[0]
    assert p["consecutive_misses"] == 0 and res["appended"] == 0


def test_ledger_duplicate_day_is_noop(tmp_path):
    lp = tmp_path / "patterns.jsonl"
    ledger.reconcile([_flag("2026-07-10")], "2026-07-10", SCREENED, ledger_path=lp)
    n_before = len(ledger.read_events(ledger_path=lp))
    # replaying the same day (e.g. --rebuild) appends nothing
    res = ledger.reconcile([_flag("2026-07-10")], "2026-07-10", SCREENED, ledger_path=lp)
    assert res["appended"] == 0
    assert len(ledger.read_events(ledger_path=lp)) == n_before


def test_ledger_append_only(tmp_path):
    lp = tmp_path / "patterns.jsonl"
    ledger.reconcile([_flag("2026-07-10")], "2026-07-10", SCREENED, ledger_path=lp)
    first = lp.read_text()
    ledger.reconcile([_flag("2026-07-11")], "2026-07-11", SCREENED, ledger_path=lp)
    assert lp.read_text().startswith(first)  # earlier lines byte-identical

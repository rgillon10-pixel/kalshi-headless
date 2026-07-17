"""Offline unit tests for q36_kxtemp_hourly_probe.

Q36 is PROBE-PREP: the tape gate (>=7 dt-days of `tape/weather_books/` hourly coverage) is not
open (day 1 committed) and the settlement leg (TWC value + ASOS obs) is NOT captured in any tape
family — it is INJECTED via `--settlement-dir`. So the probe is written + tested against FIXTURES
so it fires the moment both land. These tests pin the load-bearing logic: (1) strike + ET-hour
parsing off the ticker; (2) the derived fillable ask = 1 − best_no_bid; (3) the INSUFFICIENT-DATA
exit on <7 days AND on a missing settlement leg (both paths); (4) a synthetic >=7-day fixture with
an injected settlement leg exercising the block-bootstrap-by-market-hour path end to end (routed
through the admissibility + tick-magnitude gates without crashing); (5) the mandatory depth×duration
joint distribution; (6) wall-clock-seconds (not snapshot-count) staleness. No network, no tape
mutation — every input is a synthetic in-memory / tmp fixture.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pricing import TAKER_FEE_RATE, fee_per_contract
from scripts.q36_kxtemp_hourly_probe import (
    MIN_CI_UNITS,
    MIN_DAYS,
    depth_duration_joint,
    derived_no_ask,
    derived_yes_ask,
    load_hourly_snapshots,
    load_settlement_leg,
    microstructure_analysis,
    parse_hourly_ticker,
    run_probe,
    settlement_basis_analysis,
    stale_lift_pnl,
    winning_side_depth,
)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _book_rec(ticker, captured_at, *, best_yes_ask=0.30, best_no_bid=0.70,
              best_yes_bid=0.29, best_no_ask=0.71, no_bid_size=50.0, yes_bid_size=40.0,
              capture_id="20260722T130000Z"):
    """A minimal weather_books.v1 hourly record."""
    return {
        "schema_version": "weather_books.v1",
        "group": "hourly",
        "series": ticker.split("-")[0],
        "ticker": ticker,
        "capture_id": capture_id,
        "captured_at": captured_at,
        "close_time": "2026-07-23T02:00:00Z",
        "best_yes_ask": best_yes_ask,
        "best_no_bid": best_no_bid,
        "best_yes_bid": best_yes_bid,
        "best_no_ask": best_no_ask,
        "no_bids": [[best_no_bid, no_bid_size]],
        "yes_bids": [[best_yes_bid, yes_bid_size]],
        "depth": 2,
        "strike_type": "greater",
        "floor_strike": float(ticker.split("-T")[1]),
        "cap_strike": None,
        "price_source_tag": "real_ask",
    }


def _settle_rec(ticker, settled_result, *, expiration_value=82.0, twc_value=81.7,
                signal_known_at=None, asos_obs=None, capture_id="20260722T140000Z"):
    rec = {
        "schema_version": "weather_settlement.v0",
        "capture_id": capture_id,
        "ticker": ticker,
        "expiration_value": expiration_value,
        "settled_result": settled_result,
        "twc_value": twc_value,
    }
    if signal_known_at is not None:
        rec["signal_known_at"] = signal_known_at
    if asos_obs is not None:
        rec["asos_obs"] = asos_obs
    return rec


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# --------------------------------------------------------------------------- #
# (1) strike + ET-hour parsing
# --------------------------------------------------------------------------- #
def test_parse_hourly_ticker_strike_and_et_hour():
    p = parse_hourly_ticker("KXTEMPNYCH-26JUL1522-T81.99")
    assert p is not None
    assert p["series"] == "KXTEMPNYCH"
    assert p["strike"] == 81.99
    assert p["et_hour"] == 22
    assert p["market_hour"] == "KXTEMPNYCH-26JUL1522"
    # hour 22 ET on JUL 15 2026 (EDT) == 02:00 UTC JUL 16 — the ticker's own close, not UTC-read.
    assert p["close_utc"].isoformat() == "2026-07-16T02:00:00+00:00"


def test_parse_hourly_ticker_negative_and_integer_strikes():
    assert parse_hourly_ticker("KXTEMPNYCH-26JUL1600-T-5")["strike"] == -5.0
    assert parse_hourly_ticker("KXTEMPNYCH-26JUL1600-T90")["strike"] == 90.0


def test_parse_hourly_ticker_rejects_bad_grammar():
    assert parse_hourly_ticker("KXTEMPNYCH-26JUL1522") is None       # no strike segment
    assert parse_hourly_ticker("KXTEMPNYCH-NOTATOKEN-T80") is None   # bad date/hour token
    assert parse_hourly_ticker("KXTEMPNYCH-26JUL1522-X80") is None   # strike not T<float>
    assert parse_hourly_ticker("") is None


# --------------------------------------------------------------------------- #
# (2) derived fillable ask = 1 − best_no_bid (and NO side mirror)
# --------------------------------------------------------------------------- #
def test_derived_yes_ask_is_one_minus_no_bid():
    rec = _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00",
                    best_no_bid=0.95, best_yes_ask=0.06)
    # derived ask prefers 1 − best_no_bid (fillable derived_ask), NOT the raw best_yes_ask.
    assert derived_yes_ask(rec) == 0.05
    assert derived_no_ask(rec) == round(1.0 - 0.29, 6)


def test_derived_yes_ask_falls_back_to_best_yes_ask():
    rec = _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00")
    rec["best_no_bid"] = None
    rec["best_yes_ask"] = 0.33
    assert derived_yes_ask(rec) == 0.33


def test_winning_side_depth_reads_touch_size():
    rec = _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00",
                    best_no_bid=0.70, no_bid_size=123.0, best_yes_bid=0.29, yes_bid_size=44.0)
    # buying YES lifts the mirror of the best NO bid -> depth is the top no_bids size.
    assert winning_side_depth(rec, "yes") == 123.0
    assert winning_side_depth(rec, "no") == 44.0


# --------------------------------------------------------------------------- #
# (3) INSUFFICIENT-DATA exits — both the <7-day path and the missing-settlement path
# --------------------------------------------------------------------------- #
def test_run_probe_too_few_days_exits_clean(tmp_path):
    # 3 days of hourly coverage (< MIN_DAYS) — even WITH a settlement leg, the gate is unmet.
    tape = tmp_path / "tape"
    for day in ("2026-07-16", "2026-07-17", "2026-07-18"):
        _write_jsonl(tape / f"dt={day}.jsonl",
                     [_book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00")])
    sd = tmp_path / "settle"
    _write_jsonl(sd / "dt=2026-07-22.jsonl",
                 [_settle_rec("KXTEMPNYCH-26JUL1522-T81.99", "yes")])
    rep = run_probe(str(tape / "dt=*.jsonl"), str(sd), n_boot=100)
    assert rep["data_adequate"] is False
    assert f"need >={MIN_DAYS}" in rep["insufficient_reason"]
    assert "settlement_leg_present=True" in rep["insufficient_reason"]
    assert "microstructure" not in rep


def test_run_probe_missing_settlement_exits_clean(tmp_path):
    # 8 days of coverage (gate met on days) but NO settlement leg injected.
    tape = tmp_path / "tape"
    for i in range(8):
        _write_jsonl(tape / f"dt=2026-07-{16 + i:02d}.jsonl",
                     [_book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00")])
    rep = run_probe(str(tape / "dt=*.jsonl"), None, n_boot=100)
    assert rep["data_adequate"] is False
    assert "settlement_leg_present=False" in rep["insufficient_reason"]
    assert "microstructure" not in rep


def test_run_probe_real_tape_shape_insufficient(tmp_path):
    # one committed-shaped day, no settlement — the exact posture of today's real tape.
    tape = tmp_path / "tape"
    _write_jsonl(tape / "dt=2026-07-16.jsonl",
                 [_book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00")])
    rep = run_probe(str(tape / "dt=*.jsonl"), str(tmp_path / "nope"), n_boot=100)
    assert rep["data_adequate"] is False
    assert rep["book_meta"]["n_days"] == 1


# --------------------------------------------------------------------------- #
# (6) wall-clock-seconds (not snapshot-count) staleness measurement
# --------------------------------------------------------------------------- #
def test_pairs_use_wall_clock_seconds_not_snapshot_count():
    # two snapshots 1800s apart -> the pair's duration is 1800.0 seconds, never "1 pair-count".
    recs = [
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00", best_no_bid=0.60),
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:30:00+00:00", best_no_bid=0.60),
    ]
    by_mh = {"KXTEMPNYCH-26JUL1522": recs}
    settlement = {"KXTEMPNYCH-26JUL1522-T81.99": _settle_rec(
        "KXTEMPNYCH-26JUL1522-T81.99", "yes")}
    j = depth_duration_joint(by_mh, settlement)
    assert j["n_pairs"] == 1
    assert j["max_duration_s"] == 1800.0


# --------------------------------------------------------------------------- #
# (5) mandatory depth×duration joint distribution
# --------------------------------------------------------------------------- #
def test_depth_duration_joint_counts_cells():
    # a deep (100 contracts), long (3600s) pair clears every cell in the grid.
    recs = [
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00",
                  best_no_bid=0.60, no_bid_size=100.0),
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T22:00:00+00:00",
                  best_no_bid=0.60, no_bid_size=100.0),
    ]
    by_mh = {"KXTEMPNYCH-26JUL1522": recs}
    settlement = {"KXTEMPNYCH-26JUL1522-T81.99": _settle_rec(
        "KXTEMPNYCH-26JUL1522-T81.99", "yes")}
    j = depth_duration_joint(by_mh, settlement)
    assert j["grid_counts"]["depth>=10&dur>=60s"] == 1
    assert j["grid_counts"]["depth>=5&dur>=60s"] == 1
    assert j["grid_counts"]["depth>=20&dur>=10s"] == 1
    assert j["max_depth"] == 100.0


def test_depth_duration_joint_thin_pair_clears_no_cell():
    # 2 contracts, 5 seconds apart -> no cell clears (the W-D-style anti-correlated kill shape).
    recs = [
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00",
                  best_no_bid=0.60, no_bid_size=2.0),
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:05+00:00",
                  best_no_bid=0.60, no_bid_size=2.0),
    ]
    by_mh = {"KXTEMPNYCH-26JUL1522": recs}
    settlement = {"KXTEMPNYCH-26JUL1522-T81.99": _settle_rec(
        "KXTEMPNYCH-26JUL1522-T81.99", "yes")}
    j = depth_duration_joint(by_mh, settlement)
    assert all(c == 0 for c in j["grid_counts"].values())


# --------------------------------------------------------------------------- #
# settlement-basis half (descriptive, needs the ob leg)
# --------------------------------------------------------------------------- #
def test_settlement_basis_disagreement_and_residual():
    settlement = {
        "T1": _settle_rec("KXTEMPNYCH-26JUL1522-T81.99", "yes", expiration_value=82.0,
                          asos_obs=[{"ts": "2026-07-22T21:35:00+00:00", "temp_f": 81.6}]),
        "T2": _settle_rec("KXTEMPNYCH-26JUL1523-T80.99", "no", expiration_value=79.0,
                          asos_obs=[{"ts": "2026-07-22T22:35:00+00:00", "temp_f": 76.0}]),
    }
    sb = settlement_basis_analysis(settlement)
    assert sb["ob_leg_present"] is True
    assert sb["n_tickers_with_basis"] == 2
    # T1 residual +0.4 (within 1°F), T2 residual +3.0 (disagrees) -> 1/2 disagreement.
    assert sb["disagreement_rate"] == 0.5


def test_settlement_basis_empty_without_ob_leg():
    settlement = {"T1": _settle_rec("KXTEMPNYCH-26JUL1522-T81.99", "yes")}  # no asos_obs
    sb = settlement_basis_analysis(settlement)
    assert sb["ob_leg_present"] is False
    assert sb["n_tickers_with_basis"] == 0


# --------------------------------------------------------------------------- #
# stale-ask-lift P&L + (4) end-to-end block-bootstrap-by-market-hour path
# --------------------------------------------------------------------------- #
def test_stale_lift_requires_signal_known_at():
    recs = [
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00"),
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:30:00+00:00"),
    ]
    by_mh = {"KXTEMPNYCH-26JUL1522": recs}
    # no signal_known_at -> no stale window can be isolated -> 0 opportunities.
    settlement = {"KXTEMPNYCH-26JUL1522-T81.99": _settle_rec(
        "KXTEMPNYCH-26JUL1522-T81.99", "yes")}
    incl, moved, meta = stale_lift_pnl(by_mh, settlement)
    assert incl == {}
    assert meta["n_opportunities"] == 0


def test_stale_lift_edge_value_net_of_taker_fee():
    # earlier snapshot at 21:00 is AFTER signal_known_at 20:59 -> a stale-window opportunity.
    recs = [
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00", best_no_bid=0.60),
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:30:00+00:00", best_no_bid=0.60),
    ]
    by_mh = {"KXTEMPNYCH-26JUL1522": recs}
    settlement = {"KXTEMPNYCH-26JUL1522-T81.99": _settle_rec(
        "KXTEMPNYCH-26JUL1522-T81.99", "yes",
        signal_known_at="2026-07-22T20:59:00+00:00")}
    incl, moved, meta = stale_lift_pnl(by_mh, settlement)
    ask = 1.0 - 0.60  # derived yes ask
    expected = 1.0 - ask - fee_per_contract(ask, TAKER_FEE_RATE)
    assert incl["KXTEMPNYCH-26JUL1522"] == [round(expected, 10)] or \
        abs(incl["KXTEMPNYCH-26JUL1522"][0] - expected) < 1e-12
    # BBO unchanged across the pair -> frozen -> excluded from the movement-conditioned cut (L32).
    assert meta["frac_frozen"] == 1.0
    assert moved == {}


def _build_adequate_tree(tmp_path, *, n_market_hours=12, one_opposing=True):
    """A >=7-day tape with `n_market_hours` distinct hourly markets, each with a post-signal
    stale-window pair, plus an injected settlement leg. Returns (tape_glob, settlement_dir)."""
    tape = tmp_path / "tape"
    sd = tmp_path / "settle"
    # 8 dt-days so the day-gate is met (each just needs >=1 hourly NYC record).
    settle_recs = []
    day_recs = {f"2026-07-{16 + i:02d}": [] for i in range(8)}
    for h in range(n_market_hours):
        token = f"26JUL15{h:02d}"  # distinct ET hours -> distinct market-hours
        ticker = f"KXTEMPNYCH-{token}-T81.99"
        # a rich (cheap) winning ask so most units are positive; unit h==0 made a loser if opposing.
        no_bid = 0.60 if not (one_opposing and h == 0) else 0.005  # h0: ask ~0.995 -> net < 0
        recs = [
            _book_rec(ticker, "2026-07-22T21:00:00+00:00", best_no_bid=no_bid, best_yes_bid=0.10,
                      no_bid_size=200.0),
            # move the BBO so the pair is NON-frozen (movement-conditioned cut is non-empty).
            _book_rec(ticker, "2026-07-22T21:20:00+00:00", best_no_bid=no_bid + 0.01,
                      best_yes_bid=0.11, no_bid_size=200.0),
        ]
        # spread the market-hours across the 8 day-files so every day has coverage.
        day = f"2026-07-{16 + (h % 8):02d}"
        day_recs[day].extend(recs)
        settle_recs.append(_settle_rec(ticker, "yes",
                                        signal_known_at="2026-07-22T20:59:00+00:00"))
    for day, recs in day_recs.items():
        _write_jsonl(tape / f"dt={day}.jsonl", recs or [
            _book_rec("KXTEMPNYCH-26JUL1599-T99", "2026-07-22T21:00:00+00:00")])
    _write_jsonl(sd / "dt=2026-07-22.jsonl", settle_recs)
    return str(tape / "dt=*.jsonl"), str(sd)


def test_run_probe_end_to_end_bootstrap_by_market_hour(tmp_path):
    tape_glob, sd = _build_adequate_tree(tmp_path, n_market_hours=12, one_opposing=True)
    rep = run_probe(tape_glob, sd, n_boot=500)
    assert rep["data_adequate"] is True
    ms = rep["microstructure"]
    # depth×duration is always produced (mandatory, L78)
    assert "depth_duration_joint" in ms
    assert ms["pnl_testable"] is True
    # both L32 cuts computed and routed through the gates without crashing
    fi = ms["frozen_inclusive"]
    mc = ms["movement_conditioned"]
    assert fi["n_units"] >= MIN_CI_UNITS
    assert set(fi.keys()) >= {"mean", "ci95", "admissible", "clears_tick_magnitude",
                              "ci_strictly_positive", "alive"}
    # one opposing (losing) unit -> the CI is admissible (L41 gate satisfied, not degenerate)
    assert fi["admissible"] is True
    assert mc["n_units"] >= 1


def test_run_probe_all_same_sign_is_inadmissible(tmp_path):
    # every market-hour a winner -> no opposing unit -> inadmissible by L41, never "alive".
    tape_glob, sd = _build_adequate_tree(tmp_path, n_market_hours=12, one_opposing=False)
    rep = run_probe(tape_glob, sd, n_boot=500)
    ms = rep["microstructure"]
    assert ms["pnl_testable"] is True
    assert ms["frozen_inclusive"]["admissible"] is False
    assert ms["frozen_inclusive"]["alive"] is False
    assert "no_opposing_unit" in ms["frozen_inclusive"]["admissibility"]["reasons"]


# --------------------------------------------------------------------------- #
# loaders
# --------------------------------------------------------------------------- #
def test_load_hourly_snapshots_groups_by_market_hour_and_counts_days(tmp_path):
    tape = tmp_path / "tape"
    _write_jsonl(tape / "dt=2026-07-16.jsonl", [
        _book_rec("KXTEMPNYCH-26JUL1522-T81.99", "2026-07-22T21:00:00+00:00"),
        _book_rec("KXTEMPNYCH-26JUL1522-T82.99", "2026-07-22T21:00:00+00:00"),  # same market-hour
        _book_rec("KXTEMPNYCH-26JUL1523-T81.99", "2026-07-22T22:00:00+00:00"),  # different hour
        # a non-hourly / other-series record must be ignored:
        {"group": "daily", "series": "KXHIGHNY", "ticker": "KXHIGHNY-26JUL16-T90"},
    ])
    by_mh, meta = load_hourly_snapshots(str(tape / "dt=*.jsonl"))
    assert set(by_mh) == {"KXTEMPNYCH-26JUL1522", "KXTEMPNYCH-26JUL1523"}
    assert meta["n_market_hours"] == 2
    assert meta["n_days"] == 1
    assert meta["n_records"] == 3


def test_load_settlement_leg_missing_is_empty(tmp_path):
    settlement, meta = load_settlement_leg(str(tmp_path / "nope"))
    assert settlement == {}
    assert meta["n_settlement_tickers"] == 0
    settlement2, meta2 = load_settlement_leg(None)
    assert settlement2 == {}
    assert meta2["n_settlement_lines"] == 0


def test_load_settlement_leg_dedupes_latest_capture(tmp_path):
    sd = tmp_path / "settle"
    _write_jsonl(sd / "dt=2026-07-22.jsonl", [
        _settle_rec("T1", "yes", expiration_value=80.0, capture_id="20260722T130000Z"),
        _settle_rec("T1", "no", expiration_value=79.0, capture_id="20260722T150000Z"),
    ])
    settlement, meta = load_settlement_leg(str(sd))
    assert settlement["T1"]["settled_result"] == "no"  # latest capture wins
    assert meta["n_settlement_tickers"] == 1

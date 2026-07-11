"""scripts.s10_reachability_probe — offline unit tests for the S10 reachability-decay probe.

Covers the load nontrivial-parsing pieces: the settlement JOIN arithmetic (round-trip with
the collector's `previous_hour_event_ticker`), the settlement-map / current-group builders,
far-bracket detection, the fee-aware NO-buy edge (via core.pricing, incl. the $1.00 tick-floor
cap), candidate-trade assembly, and the block-bootstrap-by-hour independent-unit choice. No
network, no tape mutation — synthetic fixtures only.
"""
from __future__ import annotations

import pytest

from collection.crypto_hourly import previous_hour_event_ticker
from core.pricing import fee_per_contract
from scripts import s10_reachability_probe as probe


# --------------------------------------------------------------------------- #
# join arithmetic
# --------------------------------------------------------------------------- #
def test_next_hour_event_ticker_basic():
    assert probe.next_hour_event_ticker("KXBTC-26JUL0420") == "KXBTC-26JUL0421"


def test_next_hour_event_ticker_day_rollover():
    assert probe.next_hour_event_ticker("KXBTC-26JUL0423") == "KXBTC-26JUL0500"


def test_next_hour_roundtrips_with_collector_previous_hour():
    # The identity that makes the settlement join sound: settlement of X is reported in the
    # pass whose current event is next_hour(X), and that pass' previous_settlement is X.
    for et in ("KXBTC-26JUL0400", "KXETH-26JUL0523", "KXBTC-26JUL0117"):
        nxt = probe.next_hour_event_ticker(et)
        assert previous_hour_event_ticker(nxt) == et


def test_next_hour_event_ticker_bad_grammar():
    assert probe.next_hour_event_ticker("NOSEP") is None
    assert probe.next_hour_event_ticker("KXBTC-GARBAGE") is None


# --------------------------------------------------------------------------- #
# fixture: two captures (early/late) of one BTC hour + its settlement record
# --------------------------------------------------------------------------- #
def _outcome(ticker, yes_ask, no_ask, yes_bid=0.0):
    return {"ticker": ticker, "yes_ask": yes_ask, "no_ask": no_ask, "yes_bid": yes_bid,
            "price_source_tag": "real_ask"}


def _capture(event, captured_at, outcomes):
    return {
        "symbol": "BTC", "captured_at": captured_at,
        "current": {"status": "ok", "event_ticker": event, "outcomes": outcomes},
        "previous_settlement": {"status": "not_found"},
    }


def _settlement_record(settled_event, results):
    # A pass whose PREVIOUS-hour settlement is `settled_event` (broker_truth).
    return {
        "symbol": "BTC", "captured_at": "2026-07-05T01:05:00+00:00",
        "current": {"status": "ok", "event_ticker": probe.next_hour_event_ticker(settled_event),
                    "outcomes": []},
        "previous_settlement": {"status": "settled", "event_ticker": settled_event,
                                "expiration_value": 63000.0, "results": results,
                                "price_source_tag": "broker_truth"},
    }


FAR = "KXBTC-26JUL0420-B51750"   # floor-pinned far bracket
NEAR = "KXBTC-26JUL0420-B63050"  # in-the-money-ish bracket
EVENT = "KXBTC-26JUL0420"


def _records():
    early = _capture(EVENT, "2026-07-05T00:12:00+00:00",
                     [_outcome(FAR, 0.01, 1.00), _outcome(NEAR, 0.40, 0.61, yes_bid=0.39)])
    late = _capture(EVENT, "2026-07-05T00:55:00+00:00",
                    [_outcome(FAR, 0.01, 1.00), _outcome(NEAR, 0.35, 0.66, yes_bid=0.34)])
    settle = _settlement_record(EVENT, {FAR: "no", NEAR: "yes"})
    return [early, late, settle]


# --------------------------------------------------------------------------- #
# map / group builders
# --------------------------------------------------------------------------- #
def test_build_settlement_map_keys_by_settled_event():
    m = probe.build_settlement_map(_records())
    assert ("BTC", EVENT) in m
    assert m[("BTC", EVENT)]["results"][FAR] == "no"


def test_group_current_captures_collects_both_captures():
    g = probe.group_current_captures(_records())
    # settlement record's current event is the NEXT hour; the two EVENT captures group together
    assert len(g[("BTC", EVENT)]) == 2


# --------------------------------------------------------------------------- #
# far-bracket detection
# --------------------------------------------------------------------------- #
def test_far_bracket_detection_floor_only():
    early = _records()[0]
    assert probe.far_bracket_tickers(early, threshold=0.01) == [FAR]


def test_far_bracket_detection_wider_threshold_pulls_in_near():
    early = _records()[0]
    got = set(probe.far_bracket_tickers(early, threshold=0.50))
    assert got == {FAR, NEAR}


# --------------------------------------------------------------------------- #
# fee-aware NO-buy edge (the $1.00 tick-floor cap)
# --------------------------------------------------------------------------- #
def test_no_buy_edge_floor_pinned_is_capped_at_zero():
    # A genuinely-far bracket: no_ask pinned at $1.00, settles NO. fee(1.00)=0, so pnl=exactly 0.
    assert fee_per_contract(1.00) == 0.0
    assert probe.no_buy_edge(1.00, settled_no=True) == 0.0


def test_no_buy_edge_with_room_settles_no_positive():
    # no_ask 0.90 -> fee ceil(.07*.9*.1*100)/100 = 0.01; pnl = 1 - 0.90 - 0.01 = 0.09
    assert probe.no_buy_edge(0.90, settled_no=True) == pytest.approx(1.0 - 0.90 - fee_per_contract(0.90))
    assert probe.no_buy_edge(0.90, settled_no=True) > 0


def test_no_buy_edge_hit_is_catastrophic():
    # Bracket actually hit (settled YES): lose the whole stake + fee.
    pnl = probe.no_buy_edge(0.90, settled_no=False)
    assert pnl == pytest.approx(0.0 - 0.90 - fee_per_contract(0.90))
    assert pnl < -0.9


# --------------------------------------------------------------------------- #
# candidate-trade assembly + source tags
# --------------------------------------------------------------------------- #
def test_candidate_trades_books_far_bracket_no_buy():
    recs = _records()
    settle_map = probe.build_settlement_map(recs)
    groups = probe.group_current_captures(recs)
    trades = probe.candidate_trades(groups, settle_map, threshold=0.01)
    assert len(trades) == 1
    t = trades[0]
    assert t.bracket_ticker == FAR
    assert t.entry_no_ask == 1.00        # LATE capture's no_ask
    assert t.settled_result == "no"
    assert t.realized_pnl == 0.0         # capped by the tick floor
    assert t.price_source_tag == "real_ask"
    assert t.settlement_source_tag == "broker_truth"
    assert t.hour_key == f"BTC|{EVENT}"


def test_candidate_trades_skips_single_capture_group():
    recs = _records()[:1] + [_records()[2]]  # one capture + settlement only
    settle_map = probe.build_settlement_map(recs)
    groups = probe.group_current_captures(recs)
    assert probe.candidate_trades(groups, settle_map, threshold=0.01) == []


def test_candidate_trades_skips_unresolved_settlement():
    recs = _records()[:2]  # no settlement record
    settle_map = probe.build_settlement_map(recs)
    groups = probe.group_current_captures(recs)
    assert probe.candidate_trades(groups, settle_map, threshold=0.01) == []


# --------------------------------------------------------------------------- #
# bootstrap: independent unit is the HOUR, not the bracket (lesson L6)
# --------------------------------------------------------------------------- #
def test_bootstrap_unit_is_hour_not_bracket():
    # Two hours, each with several brackets; a hooked bootstrap that resampled brackets would
    # report a different n_hours. We assert it counts HOURS as the block unit.
    trades = [
        probe.Trade("BTC|H1", "BTC", "H1", "b1", 0.01, 0.01, 1.0, 0.0, "no", True, 0.0, False),
        probe.Trade("BTC|H1", "BTC", "H1", "b2", 0.01, 0.01, 1.0, 0.0, "no", True, 0.0, False),
        probe.Trade("BTC|H2", "BTC", "H2", "b3", 0.01, 0.01, 0.90, 0.01, "no", True, 0.09, True),
    ]
    out = probe.block_bootstrap_by_hour(trades, n_boot=500, seed=1)
    assert out["n_hours"] == 2
    assert out["n_trades"] == 3
    assert out["ci95"][0] is not None and out["ci95"][1] is not None


def test_bootstrap_empty_is_safe():
    out = probe.block_bootstrap_by_hour([], n_boot=100)
    assert out["n_hours"] == 0 and out["mean"] is None

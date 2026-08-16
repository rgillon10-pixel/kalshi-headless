"""Tests for `core.close_time_mutation` — the paired-observation primitives.

Every assertion is a HARD one over an explicit fixture (L201/L207): a test that only checks
"the function returned a dict" would have passed on every draft of this module, including the
ones that quietly coerced a missing close_time to a zero delta.
"""
from __future__ import annotations

import pytest

from core.close_time_mutation import (
    OPEN_TO_OPEN, OPEN_TO_SETTLED, REGIMES, SETTLED_TO_OPEN, SETTLED_TO_SETTLED,
    classify_pair, close_date, is_settled_row, parse_close_time, result_conflict, summarize,
)

OPEN = {"close_time": "2026-08-20T09:30:00Z", "result": "", "status": "active"}
SETTLED = {"close_time": "2026-08-06T12:09:30Z", "result": "no", "status": "finalized"}


class TestIsSettledRow:
    def test_non_empty_result_is_settled(self):
        assert is_settled_row({"result": "yes"}) is True

    def test_empty_result_string_is_the_exchange_saying_not_yet(self):
        assert is_settled_row({"result": "", "status": "active"}) is False

    def test_whitespace_only_result_is_not_a_label(self):
        assert is_settled_row({"result": "   "}) is False

    @pytest.mark.parametrize("status", ["settled", "finalized", "determined", "FINALIZED"])
    def test_terminal_statuses_are_settled(self, status):
        assert is_settled_row({"result": "", "status": status}) is True

    def test_closed_is_NOT_settled_trading_stopped_is_not_an_outcome(self):
        # The distinction the whole audit rests on: universe_sweep has seen `closed` 1,807
        # times and `finalized` zero times. Calling `closed` settled would have turned that
        # famine into a fake population.
        assert is_settled_row({"result": "", "status": "closed"}) is False

    def test_scalar_result_is_still_settled_even_though_it_is_not_binary(self):
        # Binary-ness (L52) is a separate question from settled-ness; conflating them would
        # classify a scalar settlement as "still open" and put it in the wrong regime.
        assert is_settled_row({"result": "scalar"}) is True

    def test_a_non_mapping_row_carries_no_evidence(self):
        assert is_settled_row(None) is False
        assert is_settled_row("finalized") is False


class TestParsing:
    def test_bare_z_and_offset_spellings_parse_to_the_same_instant(self):
        assert parse_close_time("2026-08-06T12:09:30Z") == \
            parse_close_time("2026-08-06T12:09:30+00:00")

    def test_unparseable_returns_none_never_a_sentinel_instant(self):
        # L357: a helper that invents a value for an undefined quantity hands the caller a
        # fabricated answer that `!=` cannot distinguish from a real one.
        for bad in ("", "   ", "not-a-time", None, 12345, "2026-13-99T00:00:00Z"):
            assert parse_close_time(bad) is None

    def test_close_date_is_the_utc_calendar_date(self):
        assert close_date("2026-08-06T12:09:30Z") == "2026-08-06"

    def test_close_date_of_an_unparseable_value_is_none_not_the_empty_string(self):
        assert close_date("garbage") is None


class TestClassifyPair:
    def test_the_measured_q51_shape_is_open_to_settled_moved_earlier(self):
        p = classify_pair("KXAFLGAME-26AUG060530NMKBUL-BUL", OPEN, SETTLED)
        assert p.regime == OPEN_TO_SETTLED
        assert p.instant_changed is True
        assert p.date_changed is True
        assert p.delta_hours == pytest.approx(-333.34166666, abs=1e-5)

    def test_both_open_is_open_to_open(self):
        assert classify_pair("T", OPEN, dict(OPEN)).regime == OPEN_TO_OPEN

    def test_both_settled_is_settled_to_settled(self):
        assert classify_pair("T", SETTLED, dict(SETTLED)).regime == SETTLED_TO_SETTLED

    def test_a_backwards_pair_is_reported_never_silently_reordered(self):
        # The whole question is whether close_time is trustworthy, so the function must never
        # infer pull order from the timestamps it is testing.
        assert classify_pair("T", SETTLED, OPEN).regime == SETTLED_TO_OPEN

    def test_formatting_only_change_is_text_changed_but_not_instant_changed(self):
        a = {"close_time": "2026-08-06T12:09:30Z", "result": "no"}
        b = {"close_time": "2026-08-06T12:09:30+00:00", "result": "no"}
        p = classify_pair("T", a, b)
        assert p.text_changed is True
        assert p.instant_changed is False
        assert p.delta_hours == 0.0

    def test_a_missing_close_time_yields_undated_not_a_zero_delta(self):
        p = classify_pair("T", {"result": "no"}, SETTLED)
        assert p.undated is True
        assert p.delta_hours is None
        assert p.instant_changed is False

    def test_an_intraday_move_changes_the_instant_but_not_the_date(self):
        a = {"close_time": "2026-08-06T23:00:00Z", "result": "", "status": "active"}
        b = {"close_time": "2026-08-06T21:00:00Z", "result": "no"}
        p = classify_pair("T", a, b)
        assert p.instant_changed is True
        assert p.date_changed is False
        assert p.delta_hours == pytest.approx(-2.0)


class TestResultConflict:
    def test_settlement_lag_is_not_a_conflict(self):
        # An unsettled row's empty result versus a later settled one is L262 lag. Counting it
        # would bury the real signal under 96 expected-noise rows.
        assert result_conflict(OPEN, SETTLED) is False

    def test_two_settled_rows_disagreeing_is_a_conflict(self):
        assert result_conflict({"result": "yes"}, {"result": "no"}) is True

    def test_scalar_versus_binary_is_also_a_conflict(self):
        assert result_conflict({"result": "scalar"}, {"result": "yes"}) is True

    def test_casing_and_padding_are_not_a_conflict(self):
        assert result_conflict({"result": "YES"}, {"result": " yes "}) is False

    def test_a_terminal_status_with_no_result_string_cannot_conflict(self):
        assert result_conflict({"status": "finalized"}, {"result": "no"}) is False


class TestSummarize:
    def test_every_regime_key_is_always_present_even_at_zero(self):
        s = summarize([])
        assert set(s["by_regime"]) == set(REGIMES)
        assert s["n_pairs"] == 0
        for r in REGIMES:
            assert s["by_regime"][r]["n"] == 0
            assert s["by_regime"][r]["delta_hours_median"] is None

    def test_direction_counts_and_median_over_a_known_set(self):
        pairs = [
            classify_pair("A", OPEN, SETTLED),
            classify_pair("B", {"close_time": "2026-08-10T00:00:00Z", "status": "active"},
                          {"close_time": "2026-08-09T00:00:00Z", "result": "yes"}),
            classify_pair("C", SETTLED, dict(SETTLED)),
        ]
        s = summarize(pairs)
        ots = s["by_regime"][OPEN_TO_SETTLED]
        assert ots["n"] == 2
        assert ots["moved_earlier"] == 2
        assert ots["moved_later"] == 0
        assert s["by_regime"][SETTLED_TO_SETTLED]["instant_changed"] == 0

    def test_an_undated_pair_is_counted_and_never_folded_into_the_deltas(self):
        s = summarize([classify_pair("A", {"result": "no"}, SETTLED)])
        assert s["by_regime"][SETTLED_TO_SETTLED]["undated"] == 1
        assert s["by_regime"][SETTLED_TO_SETTLED]["delta_hours_mean"] is None

"""Unit tests for `core.result_evidence` — the field-level outcome detector.

The load-bearing properties are: (1) an EMPTY `result` is never evidence, (2) `closed` is
never terminal, (3) a label is attributed only when the record supplies a ticker, (4) the
byte prefilter can never skip a line `scan_record` would have flagged.
"""
from __future__ import annotations

import json

import pytest

from core.result_evidence import (
    CLOSED_NOT_SETTLED_STATUSES,
    PREFILTER_TOKENS,
    TERMINAL_STATUSES,
    _looks_like_ticker,
    line_may_carry_evidence,
    scan_record,
)


class TestExplicitResult:
    def test_populated_result_with_own_ticker_is_an_attributed_binary_label(self):
        ev = scan_record({"ticker": "KXWCGAME-26JUL02SUIDZA-SUI", "result": "yes"})
        assert ev["labels"] == [{
            "ticker": "KXWCGAME-26JUL02SUIDZA-SUI", "result": "yes",
            "binary": True, "detector": "explicit_result"}]
        assert ev["schema_only_result"] == 0

    def test_EMPTY_result_is_schema_only_and_never_a_label(self):
        """Kalshi writes `result: ""` on an unsettled market — the exchange's own 'not yet'."""
        ev = scan_record({"ticker": "KXAFLGAME-X-Y", "result": "", "status": "active"})
        assert ev["labels"] == []
        assert ev["schema_only_result"] == 1

    def test_whitespace_only_result_is_also_schema_only(self):
        ev = scan_record({"ticker": "KXAFLGAME-X-Y", "result": "   "})
        assert ev["labels"] == []
        assert ev["schema_only_result"] == 1

    def test_scalar_result_is_carried_but_flagged_non_binary_L52(self):
        ev = scan_record({"ticker": "KXTEMP-A-B", "result": "scalar"})
        assert len(ev["labels"]) == 1
        assert ev["labels"][0]["binary"] is False

    def test_a_result_with_no_ticker_in_reach_is_unattributed_not_dropped(self):
        ev = scan_record({"some_wrapper": {"result": "yes"}})
        assert ev["labels"] == []
        assert ev["unattributed_results"] == ["yes"]

    def test_map_key_shaped_like_a_ticker_attributes_the_label(self):
        ev = scan_record({"KXBTC-26JUL1012-B53250": {"result": "no"}})
        assert ev["labels"][0]["ticker"] == "KXBTC-26JUL1012-B53250"

    def test_nested_outcome_list_entries_are_reached(self):
        rec = {"event_ticker": "E", "outcomes": [
            {"ticker": "A-B-C", "result": "yes"}, {"ticker": "A-B-D", "result": "no"}]}
        ev = scan_record(rec)
        assert sorted(l["ticker"] for l in ev["labels"]) == ["A-B-C", "A-B-D"]

    def test_result_normalisation_goes_through_core_settlement(self):
        ev = scan_record({"ticker": "A-B-C", "result": "YES"})
        assert ev["labels"][0]["result"] == "yes"


class TestStatus:
    @pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
    def test_terminal_statuses_are_evidence(self, status):
        ev = scan_record({"ticker": "A-B-C", "status": status})
        assert ev["terminal_status"] == [{"ticker": "A-B-C", "status": status}]
        assert ev["closed_not_settled"] == 0

    @pytest.mark.parametrize("status", sorted(CLOSED_NOT_SETTLED_STATUSES))
    def test_closed_is_NOT_terminal_trading_stopped_is_not_an_outcome(self, status):
        ev = scan_record({"ticker": "A-B-C", "status": status})
        assert ev["terminal_status"] == []
        assert ev["closed_not_settled"] == 1

    def test_active_is_neither(self):
        ev = scan_record({"ticker": "A-B-C", "status": "active"})
        assert ev["terminal_status"] == [] and ev["closed_not_settled"] == 0

    def test_closed_never_leaks_into_terminal_statuses(self):
        assert not (TERMINAL_STATUSES & CLOSED_NOT_SETTLED_STATUSES)


class TestTickerShape:
    @pytest.mark.parametrize("key", ["KXWCGAME-26JUL02SUIDZA-SUI", "KXBTC-26JUL1012-B53250"])
    def test_real_tickers_pass(self, key):
        assert _looks_like_ticker(key)

    @pytest.mark.parametrize("key", ["result", "RESULT", "A-B", "", None, 42,
                                     "KX GAME-A-B", "kxwcgame-26jul02-sui"])
    def test_non_tickers_fail(self, key):
        assert not _looks_like_ticker(key)


class TestPrefilter:
    def test_prefilter_never_skips_a_line_scan_would_flag(self):
        """The prefilter is a SPEED device with a correctness obligation: every key name
        `scan_record` can fire on must appear as a token."""
        firing_records = [
            {"ticker": "A-B-C", "result": "yes"},
            {"ticker": "A-B-C", "status": "settled"},
            {"ticker": "A-B-C", "status": "closed"},
            {"ticker": "A-B-C", "result": ""},
            {"wrap": {"deep": {"ticker": "A-B-C", "result": "no"}}},
        ]
        for rec in firing_records:
            raw = json.dumps(rec).encode()
            ev = scan_record(rec)
            fires = bool(ev["labels"] or ev["unattributed_results"] or ev["terminal_status"]
                         or ev["closed_not_settled"] or ev["schema_only_result"])
            assert fires, rec
            assert line_may_carry_evidence(raw), rec

    def test_a_line_with_no_evidence_key_is_skipped(self):
        raw = json.dumps({"ticker": "A-B-C", "yes_bid": 41, "yes_ask": 43}).encode()
        assert not line_may_carry_evidence(raw)

    def test_every_prefilter_token_is_a_key_name_scan_record_reads(self):
        assert set(PREFILTER_TOKENS) == {b'"result"', b'"status"'}


class TestBounds:
    def test_depth_bound_terminates_on_a_deeply_nested_record(self):
        rec = cur = {}
        for _ in range(200):
            cur["n"] = {}
            cur = cur["n"]
        cur["ticker"], cur["result"] = "A-B-C", "yes"
        ev = scan_record(rec)          # must not recurse to death
        assert ev["labels"] == []      # and must not claim a label it never reached

    def test_non_dict_input_is_inert(self):
        for junk in ([], "x", 3, None):
            ev = scan_record(junk)
            assert ev["labels"] == [] and ev["schema_only_result"] == 0

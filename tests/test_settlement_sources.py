"""core.settlement_sources — L300's "scan EVERY settlement family" rule, made mechanical.

The lesson: on 2026-08-06 the S79 registration recorded its data-gate as "no settlement
coverage of the 2026-08-03 trade day (`tape/settlement_ledger/` is 07-07 -> 07-22 only)".
`tape/q51_settlement_cache/settlement.json` covered it. The acceptance test at the bottom of
this file is that exact case pinned against real committed tape: a one-family scan says 0, a
whole-registry scan says 9, and 9 is under the L41 10-unit floor — so the gate survives but
its REASON changes from "collector missing" to "population one game short".
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.settlement_sources import (
    CACHE_MARKETS_MAP,
    EMBEDDED_RESULT_FAMILIES,
    EVENT_LIST_RESULTS,
    LEDGER_ROWS,
    MARKET_RESULT,
    RECORD_RESULTS,
    SETTLEMENT_SOURCES,
    UNDECLARED_SCAN_RECALL_NOTE,
    SettlementSource,
    declared_source_names,
    iter_source_results,
    resolve_market_results,
    source_files_present,
    undeclared_settlement_dirs,
)

TRADE_DAY_TAPE = Path("tape/kalshi_trades/dt=2026-08-03.jsonl")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def fake_root(tmp_path) -> Path:
    root = tmp_path / "tape"
    _write(root / "settlement_ledger/dt=2026-07-17.jsonl",
           json.dumps({"ticker": "LEDGER-A", "result": "yes",
                       "price_source_tag": "broker_truth"}) + "\n"
           + json.dumps({"ticker": "LEDGER-B", "result": "no"}) + "\n"
           + "not json at all\n")
    _write(root / "q51_settlement_cache/settlement.json",
           json.dumps({"day": "2026-08-03", "price_source_tag": "broker_truth",
                       "markets": {
                           "CACHE-FINAL": {"status": "finalized", "result": "no"},
                           "CACHE-ACTIVE": {"status": "active", "result": ""},
                           "CACHE-SCALAR": {"status": "finalized", "result": "scalar"}}}))
    _write(root / "crypto_hourly/dt=2026-08-03.jsonl",
           json.dumps({"previous_settlement": {
               "event_ticker": "KXBTC-26AUG0220", "price_source_tag": "broker_truth",
               "results": {"CRYPTO-A": "yes", "CRYPTO-B": "no"}}}) + "\n")
    _write(root / "weather_actuals/dt=2026-08-02.jsonl",
           json.dumps({"settled_markets": {"events": [
               {"event_ticker": "KXHIGHTBOS-26JUL15", "price_source_tag": "broker_truth",
                "results": {"WX-A": "no"}}]}}) + "\n")
    _write(root / "econ_prints/dt=2026-08-04.jsonl",
           json.dumps({"recent_settlement": {"event_ticker": "KXCPICORE-26JUN",
                                             "price_source_tag": "broker_truth",
                                             "results": {"ECON-A": "yes"}}}) + "\n")
    return root


# --------------------------------------------------------------------------- #
# registry hygiene
# --------------------------------------------------------------------------- #
class TestRegistryShape:
    def test_names_are_unique(self):
        names = declared_source_names()
        assert len(names) == len(set(names))

    def test_every_source_declares_a_known_reader_kind(self):
        known = {LEDGER_ROWS, CACHE_MARKETS_MAP, RECORD_RESULTS, EVENT_LIST_RESULTS}
        for s in SETTLEMENT_SOURCES:
            assert s.kind in known, s.name

    def test_embedded_kinds_and_only_those_name_a_reader_field(self):
        for s in SETTLEMENT_SOURCES:
            embedded = s.kind in (RECORD_RESULTS, EVENT_LIST_RESULTS)
            assert bool(s.reader_field) is embedded, s.name

    def test_every_source_is_broker_truth(self):
        """A settled result read back from the exchange IS broker truth; anything weaker
        would be a settlement source that cannot settle anything."""
        for s in SETTLEMENT_SOURCES:
            assert s.declared_tag == "broker_truth", s.name
            assert s.resolves == MARKET_RESULT, s.name

    def test_the_three_embedded_families_are_named(self):
        """The recall limit is only enumerable because these are written down."""
        assert set(EMBEDDED_RESULT_FAMILIES) == {"crypto_hourly", "weather_actuals",
                                                 "econ_prints"}

    def test_registry_covers_every_settlement_named_dir_in_the_real_tape_tree(self):
        assert undeclared_settlement_dirs("tape") == ()

    def test_recall_limit_is_published_not_merely_true(self):
        assert "precision evidence, never recall" in UNDECLARED_SCAN_RECALL_NOTE
        assert "L300" in UNDECLARED_SCAN_RECALL_NOTE


# --------------------------------------------------------------------------- #
# readers
# --------------------------------------------------------------------------- #
class TestReaders:
    @pytest.mark.parametrize("ticker,expected", [
        ("LEDGER-A", "yes"), ("LEDGER-B", "no"),
        ("CACHE-FINAL", "no"), ("CACHE-SCALAR", "scalar"), ("CACHE-ACTIVE", ""),
        ("CRYPTO-A", "yes"), ("WX-A", "no"), ("ECON-A", "yes"),
    ])
    def test_every_reader_kind_finds_its_own_rows(self, fake_root, ticker, expected):
        hits = {}
        for s in SETTLEMENT_SOURCES:
            for m in iter_source_results(s, [ticker], root=str(fake_root)):
                hits[m.ticker] = m.result
        assert hits.get(ticker) == expected

    def test_a_malformed_jsonl_line_is_skipped_not_fatal(self, fake_root):
        src = next(s for s in SETTLEMENT_SOURCES if s.name == "settlement_ledger")
        got = list(iter_source_results(src, None, root=str(fake_root)))
        assert sorted(m.ticker for m in got) == ["LEDGER-A", "LEDGER-B"]

    def test_a_family_with_no_files_yields_nothing_and_never_raises(self, tmp_path):
        for s in SETTLEMENT_SOURCES:
            assert list(iter_source_results(s, ["X"], root=str(tmp_path))) == []
            assert source_files_present(s, str(tmp_path)) == []

    def test_row_tag_is_propagated_not_overwritten_by_the_declared_default(self, tmp_path):
        root = tmp_path / "tape"
        _write(root / "settlement_ledger/dt=2026-07-17.jsonl",
               json.dumps({"ticker": "T", "result": "yes",
                           "price_source_tag": "synthetic"}) + "\n")
        src = next(s for s in SETTLEMENT_SOURCES if s.name == "settlement_ledger")
        got = list(iter_source_results(src, None, root=str(root)))
        assert got[0].price_source_tag == "synthetic"


# --------------------------------------------------------------------------- #
# resolution semantics
# --------------------------------------------------------------------------- #
class TestResolution:
    def test_binary_results_resolve_and_are_attributed_to_their_source(self, fake_root):
        rep = resolve_market_results(["LEDGER-A", "CACHE-FINAL", "CRYPTO-A"],
                                     root=str(fake_root))
        assert set(rep.resolved) == {"LEDGER-A", "CACHE-FINAL", "CRYPTO-A"}
        assert rep.per_source_hits["settlement_ledger"] == 1
        assert rep.per_source_hits["q51_settlement_cache"] == 1
        assert rep.per_source_hits["crypto_hourly"] == 1
        assert rep.unresolved == ()

    def test_a_scalar_result_is_never_scored_as_a_loss(self, fake_root):
        """L52: `result == 'scalar'` is not 'no'."""
        rep = resolve_market_results(["CACHE-SCALAR"], root=str(fake_root))
        assert rep.resolved == {}
        assert "CACHE-SCALAR" in rep.non_binary
        assert rep.unresolved == ("CACHE-SCALAR",)

    def test_listed_but_unsettled_is_reported_as_its_own_class(self, fake_root):
        """A market Kalshi still lists as `active` is LISTED, not SETTLED — conflating the
        two would turn this module into the opposite lie from the one it exists to stop."""
        rep = resolve_market_results(["CACHE-ACTIVE"], root=str(fake_root))
        assert rep.resolved == {}
        assert "CACHE-ACTIVE" in rep.listed_unsettled
        assert rep.unresolved == ("CACHE-ACTIVE",)

    def test_an_unknown_ticker_is_unresolved_not_an_error(self, fake_root):
        rep = resolve_market_results(["NOPE"], root=str(fake_root))
        assert rep.unresolved == ("NOPE",)
        assert rep.requested == 1

    def test_absent_families_are_named_not_silently_treated_as_empty(self, tmp_path):
        root = tmp_path / "tape"
        _write(root / "settlement_ledger/dt=2026-07-17.jsonl",
               json.dumps({"ticker": "T", "result": "yes"}) + "\n")
        rep = resolve_market_results(["T"], root=str(root))
        assert rep.sources_scanned == declared_source_names()
        assert "q51_settlement_cache" in rep.sources_absent_on_disk
        assert "settlement_ledger" not in rep.sources_absent_on_disk

    def test_restricting_the_source_list_reproduces_the_single_family_blind_spot(
            self, fake_root):
        """The S79 shape in miniature: scanning one family answers 0 while the registry
        answers 1 — same tape, different question."""
        ledger_only = [s for s in SETTLEMENT_SOURCES if s.name == "settlement_ledger"]
        one = resolve_market_results(["CACHE-FINAL"], root=str(fake_root),
                                     sources=ledger_only)
        allf = resolve_market_results(["CACHE-FINAL"], root=str(fake_root))
        assert one.n_resolved == 0 and allf.n_resolved == 1

    def test_coverage_summary_is_one_quotable_line(self, fake_root):
        rep = resolve_market_results(["LEDGER-A", "NOPE"], root=str(fake_root))
        line = rep.coverage_summary()
        assert "2 requested / 1 resolved" in line
        assert "settlement_ledger=1" in line
        assert "\n" not in line

    def test_json_obj_round_trips_and_carries_the_recall_note(self, fake_root):
        rep = resolve_market_results(["LEDGER-A"], root=str(fake_root))
        obj = rep.to_json_obj()
        assert json.loads(json.dumps(obj))["n_resolved"] == 1
        assert obj["recall_note"] == UNDECLARED_SCAN_RECALL_NOTE


class TestUndeclaredDirDetector:
    def test_a_new_settlement_named_cache_dir_is_flagged(self, fake_root):
        (fake_root / "q99_settlement_cache").mkdir()
        assert undeclared_settlement_dirs(str(fake_root)) == ("q99_settlement_cache",)

    def test_a_non_settlement_dir_is_not_flagged(self, fake_root):
        (fake_root / "orderbook_depth").mkdir()
        assert undeclared_settlement_dirs(str(fake_root)) == ()

    def test_a_missing_root_is_empty_not_an_exception(self, tmp_path):
        assert undeclared_settlement_dirs(str(tmp_path / "nope")) == ()

    def test_it_cannot_see_an_embedded_family_and_that_limit_is_the_point(self, tmp_path):
        """HARD: prove the blind spot exists rather than asserting the note's prose. A new
        family that hides results inside another schema is invisible to a name scan."""
        root = tmp_path / "tape"
        _write(root / "some_new_family/dt=2026-08-07.jsonl",
               json.dumps({"previous_settlement": {"results": {"X": "yes"}}}) + "\n")
        assert undeclared_settlement_dirs(str(root)) == ()
        assert resolve_market_results(["X"], root=str(root)).n_resolved == 0


# --------------------------------------------------------------------------- #
# real committed tape — the L300 acceptance pin
# --------------------------------------------------------------------------- #
def _frozen_m2_sources():
    """The declared registry with `q51_settlement_cache` repointed at its FROZEN milestone-2
    snapshot, so L300's published counts stay reproducible after any later re-pull (L325)."""
    import dataclasses
    return tuple(
        dataclasses.replace(
            src, path_glob="q51_settlement_cache/settlement-m2-2026-08-04.json")
        if src.name == "q51_settlement_cache" else src
        for src in SETTLEMENT_SOURCES)


@pytest.mark.skipif(not TRADE_DAY_TAPE.exists(), reason="kalshi_trades tape absent")
class TestAcceptanceRealTapeS79DataGate:
    @pytest.fixture(scope="class")
    def traded_tickers(self):
        return sorted({json.loads(l)["ticker"] for l in
                       TRADE_DAY_TAPE.read_text().splitlines() if l.strip()})

    def test_the_trade_day_has_42_distinct_tickers(self, traded_tickers):
        assert len(traded_tickers) == 42

    def test_settlement_ledger_alone_resolves_zero_of_them(self, traded_tickers):
        """The measurement that produced S79's WRONG data-gate reason."""
        ledger_only = [s for s in SETTLEMENT_SOURCES if s.name == "settlement_ledger"]
        rep = resolve_market_results(traded_tickers, sources=ledger_only)
        assert rep.n_resolved == 0

    def test_the_full_registry_resolves_nine_and_names_the_family(self, traded_tickers):
        """L300's pin, now read through the FROZEN milestone-2 cache (L325).

        `q51_settlement_cache`'s live `settlement.json` is rewritten by
        `q51_maker_fillsim.py --build-cache`; milestone 3 fired that command on 2026-08-10 and
        this count moved 9 -> 32, turning L300's acceptance pin red for a reason that has
        nothing to do with the property under test. Substituting the frozen snapshot into the
        registry reproduces the pin EXACTLY (9/9) and re-anchors it to a slice that cannot
        grow (L191). The post-firing live state is measured in its own case below rather than
        being silently absorbed into this one."""
        rep = resolve_market_results(traded_tickers, sources=_frozen_m2_sources())
        assert rep.n_resolved == 9
        assert rep.per_source_hits["q51_settlement_cache"] == 9
        assert sum(v for k, v in rep.per_source_hits.items()
                   if k != "q51_settlement_cache") == 0
        assert all(m.price_source_tag == "broker_truth" for m in rep.resolved.values())

    def test_nine_is_below_the_l41_ten_unit_floor(self, traded_tickers):
        """Why S79 still does not become runnable: the gate holds, on a different reason.
        The bootstrap unit is the GAME (L6), so count distinct event_tickers, not tickers.
        FROZEN input (L325) — see the note on the previous case."""
        rep = resolve_market_results(traded_tickers, sources=_frozen_m2_sources())
        events = {t.rsplit("-", 1)[0] for t in rep.resolved}
        assert len(events) == 9
        assert len(events) < 10

    def test_four_traded_tickers_are_not_listed_by_any_source(self, traded_tickers):
        """Honest residue: the crypto hourly brackets that traded are absent from every
        settlement family on committed tape — unresolved AND unlisted, a third state."""
        rep = resolve_market_results(traded_tickers)
        never_seen = [t for t in rep.unresolved
                      if t not in rep.listed_unsettled and t not in rep.non_binary]
        assert len(never_seen) == 4
        assert all(t.startswith(("KXBTC-", "KXETH-")) for t in never_seen)

    def test_the_m3_repull_moved_this_surface_above_the_l41_floor(self, traded_tickers):
        """MEASURED side-effect of Q51 milestone 3's settlement re-pull (2026-08-10).

        The re-pull resolved 49 more of the 60 sampled markets, so this surface now resolves
        32 of the 42 traded tickers = 32 distinct GAME units, above the L41 floor of 10 that
        L300 recorded it as failing. DIRECTIONAL (`>=`): a settlement cache only ever gains
        finalized results, so a later sweep can raise this and must not turn it red.

        What it does NOT mean: S79 already fired on 2026-08-09 (verdict DEAD-by-CI,
        verifier-CONFIRMED, 24 units off the trade-print backfill). This is a
        settlement-RESOLVABILITY measurement on one surface, not a strategy result, and it
        revives nothing."""
        rep = resolve_market_results(traded_tickers)
        assert rep.n_resolved >= 32
        assert rep.per_source_hits["q51_settlement_cache"] >= 32
        events = {t.rsplit("-", 1)[0] for t in rep.resolved}
        assert len(events) >= 32 > 10
        assert all(m.price_source_tag == "broker_truth" for m in rep.resolved.values())

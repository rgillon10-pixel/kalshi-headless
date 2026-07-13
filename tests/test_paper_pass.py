"""scripts.paper_pass — end-to-end paper pass over a SYNTHETIC crypto_hourly
fixture + synthetic candle cache, all in tmp_path. No network, no real tape.

The KEY test is the reconciliation: for the processed events, the ledger's
per-event realized P&L equals scripts.s14_ladder_fillsim.simulate_event's `pnl`
for the same event, cent-for-cent — an executable proof that the buy-NO
representation of S14's short-YES underwriting is economically identical.
"""
from __future__ import annotations

import json
from collections import defaultdict

import pytest

from execution.schema import Fill, Settlement, line_to_record
from scripts import paper_pass
from scripts.s14_ladder_fillsim import (build_earliest_captures,
                                       build_settlement_map, detect_seller_fill,
                                       load_candle_summary_cache, simulate_event)

NOW = "2026-07-13T00:00:00+00:00"


# --------------------------------------------------------------------------- #
# fixture builders
# --------------------------------------------------------------------------- #
def _record(event_ticker, series, members, winner,
            captured_at="2026-07-11T05:00:00Z", close_time="2026-07-11T06:00:00Z"):
    outcomes = []
    for i, (tk, ask) in enumerate(members):
        outcomes.append({
            "ticker": tk, "yes_ask": ask, "no_ask": round(1.0 - ask, 2),
            "yes_bid": 0.0, "no_bid": round(1.0 - ask, 2), "strike_type": "between",
            "floor_strike": 50000 + i * 100, "cap_strike": 50000 + i * 100 + 99.99,
            "price_source_tag": "real_ask", "title": "t",
        })
    results = {tk: ("yes" if tk == winner else "no") for tk, _ in members}
    return {
        "captured_at": captured_at, "series": series,
        "current": {"event_ticker": event_ticker, "close_time": close_time,
                    "open_time": captured_at, "outcomes": outcomes, "bracket_sum": 1.0},
        "previous_settlement": {"event_ticker": event_ticker, "results": results,
                                "expiration_value": "1", "price_source_tag": "broker_truth"},
    }


def _write_tape(tape_dir, records, day="2026-07-11"):
    tape_dir.mkdir(parents=True, exist_ok=True)
    with open(tape_dir / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def _write_cache(cache_dir, summaries, day="2026-07-11"):
    """summaries: {ticker: (max_high_dollars, total_volume)}"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    with open(cache_dir / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for tk, (high, vol) in summaries.items():
            f.write(json.dumps({
                "ticker": tk, "series": "KXBTC", "start_ts": 0, "end_ts": 1,
                "max_high_dollars": high, "total_volume": vol, "n_candles": 1,
                "price_source_tag": "real_ask",
                "schema_version": "s14_ladder_fillsim_candle_summary.v1",
            }) + "\n")


def _read_ledger(ledger_dir):
    recs = []
    for path in sorted(ledger_dir.glob("dt=*.jsonl")):
        with open(path, encoding="utf-8") as f:
            for line in f:
                rec = line_to_record(line)
                if rec is not None:
                    recs.append(rec)
    return recs


def _ledger_pnl_by_event(ledger_dir):
    """Reconstruct per-event realized P&L from the ledger, mirroring broker
    accounting: a buy-NO fill sets avg_cost = price + fee (qty 1); its settlement
    realizes (settle_value - avg_cost). Keyed to the event via the settlement's
    event_ticker."""
    avg_cost = {}
    pnl = defaultdict(float)
    for rec in _read_ledger(ledger_dir):
        if isinstance(rec, Fill):
            avg_cost[(rec.ticker, rec.side)] = rec.price + rec.fee
        elif isinstance(rec, Settlement):
            ac = avg_cost[(rec.ticker, rec.side)]
            pnl[rec.event_ticker] += (rec.settle_value - ac) * rec.qty
    return dict(pnl)


# --------------------------------------------------------------------------- #
# the two-event reconciliation fixture (both P&L signs)
# --------------------------------------------------------------------------- #
def _two_event_fixture(tmp_path):
    tape_dir = tmp_path / "tape" / "crypto_hourly"
    cache_dir = tmp_path / "tape" / "s14_ladder_fillsim"
    ledger_dir = tmp_path / "paper" / "ledger"
    records = [
        # EVA: winner (M1) fills -> net LOSS leg; income leg M2 also fills.
        _record("KXBTC-EVA", "KXBTC",
                [("KXBTC-EVA-M1", 0.30), ("KXBTC-EVA-M2", 0.20)], winner="KXBTC-EVA-M1"),
        # EVB: winner (N1) does NOT fill (no payout); income leg N2 fills -> net GAIN.
        _record("KXBTC-EVB", "KXBTC",
                [("KXBTC-EVB-N1", 0.10), ("KXBTC-EVB-N2", 0.40)], winner="KXBTC-EVB-N1"),
    ]
    _write_tape(tape_dir, records)
    _write_cache(cache_dir, {
        "KXBTC-EVA-M1": (0.95, 100.0),  # winner filled
        "KXBTC-EVA-M2": (0.95, 100.0),  # income filled
        "KXBTC-EVB-N1": (0.05, 100.0),  # winner NOT filled (high 0.05 < ask 0.10)
        "KXBTC-EVB-N2": (0.95, 100.0),  # income filled
    })
    return tape_dir, cache_dir, ledger_dir, records


def test_processes_both_events_and_books_realized_pnl(tmp_path):
    tape_dir, cache_dir, ledger_dir, _ = _two_event_fixture(tmp_path)
    res = paper_pass.run_pass(tape_dir, cache_dir, ledger_dir, now_ts=NOW)
    s = res["per_strategy"][0]
    assert s["n_processed"] == 2
    assert s["n_deferred_caps"] == 0
    assert s["n_deferred_coverage"] == 0
    # EVA pnl -0.52, EVB pnl +0.39 -> total -0.13
    assert res["realized_pnl"] == pytest.approx(-0.13)


def test_reconciliation_ledger_pnl_equals_simulate_event(tmp_path):
    """THE proof: ledger per-event realized P&L == simulate_event pnl, cent-for-cent."""
    tape_dir, cache_dir, ledger_dir, records = _two_event_fixture(tmp_path)
    paper_pass.run_pass(tape_dir, cache_dir, ledger_dir, now_ts=NOW)

    earliest = build_earliest_captures(records)
    settle = build_settlement_map(records)
    cache = load_candle_summary_cache(cache_dir)

    def fill_fn(series, ticker, ask, start_ts, end_ts):
        return detect_seller_fill(cache[ticker], ask)

    ledger_pnl = _ledger_pnl_by_event(ledger_dir)
    for et in ("KXBTC-EVA", "KXBTC-EVB"):
        row = simulate_event(et, earliest[et], settle[et], fill_fn)
        assert ledger_pnl[et] == pytest.approx(row["pnl"]), et
    # and both signs are actually exercised
    assert ledger_pnl["KXBTC-EVA"] < 0
    assert ledger_pnl["KXBTC-EVB"] > 0


def test_pass_is_idempotent_second_run_adds_nothing(tmp_path):
    tape_dir, cache_dir, ledger_dir, _ = _two_event_fixture(tmp_path)
    paper_pass.run_pass(tape_dir, cache_dir, ledger_dir, now_ts=NOW)
    lines_after_first = sum(len(p.read_text().splitlines())
                            for p in ledger_dir.glob("dt=*.jsonl"))
    res2 = paper_pass.run_pass(tape_dir, cache_dir, ledger_dir, now_ts=NOW)
    lines_after_second = sum(len(p.read_text().splitlines())
                             for p in ledger_dir.glob("dt=*.jsonl"))
    assert lines_after_second == lines_after_first  # nothing new written
    s = res2["per_strategy"][0]
    assert s["n_processed"] == 0
    assert s["n_already"] == 2


# --------------------------------------------------------------------------- #
# cap deferral (real caps from execution.limits, read-only)
# --------------------------------------------------------------------------- #
def test_cap_defer_counts_events_that_do_not_fit(tmp_path):
    from execution.limits import MAX_DAILY_ORDERS
    tape_dir = tmp_path / "tape" / "crypto_hourly"
    cache_dir = tmp_path / "tape" / "s14_ladder_fillsim"
    ledger_dir = tmp_path / "paper" / "ledger"

    # two events, each with 120 priced members: 120 <= 200 fits, then 120+120 > 200.
    n = 120
    records, summaries = [], {}
    for ev in ("A", "B"):
        members = [(f"KXBTC-EV{ev}-M{i}", 0.03) for i in range(n)]
        winner = f"KXBTC-EV{ev}-M0"
        records.append(_record(f"KXBTC-EV{ev}", "KXBTC", members, winner=winner))
        for tk, _ in members:
            summaries[tk] = (0.95, 100.0)  # all fill -> settle -> release notional
    _write_tape(tape_dir, records)
    _write_cache(cache_dir, summaries)

    res = paper_pass.run_pass(tape_dir, cache_dir, ledger_dir, now_ts=NOW)
    s = res["per_strategy"][0]
    assert n <= MAX_DAILY_ORDERS  # sanity: one event fits
    assert 2 * n > MAX_DAILY_ORDERS  # sanity: two do not
    assert s["n_processed"] == 1
    assert s["n_deferred_caps"] == 1


def test_coverage_defer_counts_events_missing_a_candle(tmp_path):
    tape_dir = tmp_path / "tape" / "crypto_hourly"
    cache_dir = tmp_path / "tape" / "s14_ladder_fillsim"
    ledger_dir = tmp_path / "paper" / "ledger"
    records = [_record("KXBTC-EVC", "KXBTC",
                       [("KXBTC-EVC-M1", 0.30), ("KXBTC-EVC-M2", 0.20)],
                       winner="KXBTC-EVC-M1")]
    _write_tape(tape_dir, records)
    # cache is MISSING KXBTC-EVC-M2 -> incomplete coverage, deferred (never fetched)
    _write_cache(cache_dir, {"KXBTC-EVC-M1": (0.95, 100.0)})

    res = paper_pass.run_pass(tape_dir, cache_dir, ledger_dir, now_ts=NOW)
    s = res["per_strategy"][0]
    assert s["n_processed"] == 0
    assert s["n_deferred_coverage"] == 1
    assert not list(ledger_dir.glob("dt=*.jsonl"))  # nothing written

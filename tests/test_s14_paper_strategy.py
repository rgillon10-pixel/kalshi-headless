"""execution.strategies.s14_ladder_underwriting — the S14 shadow proposer.
Offline: synthetic crypto_hourly records, no network, no clock beyond an injected
now_ts."""
from __future__ import annotations

import subprocess
import sys

from execution.strategies.s14_ladder_underwriting import S14LadderUnderwriting
from execution.strategy_api import TapeContext


def _record(event_ticker="KXBTC-EVA", series="KXBTC", winner="KXBTC-EVA-M1",
            members=None, captured_at="2026-07-11T05:00:00Z",
            close_time="2026-07-11T06:00:00Z"):
    members = members if members is not None else [("KXBTC-EVA-M1", 0.30)]
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


def _context(records, now_ts="2026-07-13T00:00:00+00:00"):
    return TapeContext(records_by_family={"crypto_hourly": records}, now_ts=now_ts)


def test_proposes_buy_no_at_one_minus_ask_for_priced_and_winner():
    members = [
        ("KXBTC-EVA-M1", 0.01),  # winner @ 1c floor -> INCLUDED (drives the loss leg)
        ("KXBTC-EVA-M2", 0.01),  # non-winner @ 1c floor -> OMITTED (nets $0 either way)
        ("KXBTC-EVA-M3", 0.30),  # priced non-winner -> INCLUDED
    ]
    recs = [_record(members=members, winner="KXBTC-EVA-M1")]
    orders = S14LadderUnderwriting().propose_orders(_context(recs))
    by_ticker = {o.ticker: o for o in orders}
    assert set(by_ticker) == {"KXBTC-EVA-M1", "KXBTC-EVA-M3"}  # M2 omitted
    m1, m3 = by_ticker["KXBTC-EVA-M1"], by_ticker["KXBTC-EVA-M3"]
    # buy NO at round(1 - A, 2)
    assert (m1.side, m1.action, m1.tif, m1.qty) == ("no", "buy", "rest", 1)
    assert m1.limit_price == 0.99   # 1 - 0.01
    assert m3.limit_price == 0.70   # 1 - 0.30
    assert m1.strategy == "s14_ladder_underwriting"


def test_order_id_and_event_ticker_are_deterministic():
    recs = [_record(members=[("KXBTC-EVA-M1", 0.30)], winner="KXBTC-EVA-M1")]
    a = S14LadderUnderwriting().propose_orders(_context(recs))
    b = S14LadderUnderwriting().propose_orders(_context(recs))
    assert [o.order_id for o in a] == [o.order_id for o in b]
    assert a[0].order_id == "s14_ladder_underwriting:KXBTC-EVA:KXBTC-EVA-M1"
    assert a[0].event_ticker == "KXBTC-EVA"
    assert a[0].ts == "2026-07-13T00:00:00+00:00"  # from context.now_ts only


def test_no_orders_for_event_without_settlement():
    rec = _record(members=[("KXBTC-EVA-M1", 0.30)], winner="KXBTC-EVA-M1")
    rec.pop("previous_settlement")  # no broker-truth winner
    assert S14LadderUnderwriting().propose_orders(_context([rec])) == []


def test_proposed_orders_all_validate_clean():
    members = [("KXBTC-EVA-M1", 0.01), ("KXBTC-EVA-M2", 0.99), ("KXBTC-EVA-M3", 0.50)]
    recs = [_record(members=members, winner="KXBTC-EVA-M1")]
    for o in S14LadderUnderwriting().propose_orders(_context(recs)):
        assert o.validate() == []  # every limit_price in [0.01, 0.99]


def test_strategy_import_is_network_free():
    """Importing the strategy module must NOT import the network client
    (validation.v3_market). Checked in a fresh subprocess so a prior test's import
    cannot mask a regression."""
    code = (
        "import sys;"
        "import execution.strategies.s14_ladder_underwriting;"
        "assert 'validation.v3_market' not in sys.modules, 'network client imported!';"
        "print('ok')"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ok" in r.stdout

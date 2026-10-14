"""Tests for S90 (Probe C) — the frozen weather-favorite-taker rule and its paper pass.
No network anywhere: records are synthetic monitor_poll-shaped dicts, results are injected."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from execution.strategies import s90_weather_favorite_taker as s90
from execution.strategy_api import TapeContext
from scripts import s90_daily_pass as pass_

NOW = datetime(2026, 10, 15, 0, 35, tzinfo=timezone.utc)


def rec(ticker, ask, bid=None, size=25.0, hours=29.0, tag="real_ask"):
    close = NOW + timedelta(hours=hours)
    return {"ticker": ticker, "yes_ask": ask, "yes_bid": bid if bid is not None else round(ask - 0.03, 2),
            "yes_ask_size": size, "close_time": close.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "captured_at": NOW.isoformat(), "price_source_tag": tag, "event_ticker": "-".join(ticker.split("-")[:2])}


def test_daily_ticker_shape():
    assert s90.is_daily_ticker("KXHIGHTDAL-26OCT15-B72")
    assert s90.is_daily_ticker("KXHIGHNY-26OCT15-T70")
    assert s90.is_daily_ticker("KXLOWTNYC-26OCT15-B45")
    assert not s90.is_daily_ticker("KXHIGHNYD-26OCT15-H14-T70")   # hourly/directional shape
    assert not s90.is_daily_ticker("KXTEMPNYCH-26OCT15-T70")       # not a daily series prefix
    assert not s90.is_daily_ticker("KXMVECROSSCATEGORY-S2026-ABC")


def test_frozen_rule_selects_band_horizon_and_real_ask_only():
    recs = [
        rec("KXHIGHTDAL-26OCT15-B72", 0.62),                   # in band → yes
        rec("KXHIGHMIA-26OCT15-B88", 0.50),                    # lower edge inclusive → yes
        rec("KXHIGHAUS-26OCT15-B80", 0.80),                    # upper edge exclusive → no
        rec("KXHIGHDEN-26OCT15-B60", 0.45),                    # below band → no
        rec("KXHIGHLAX-26OCT15-B75", 0.65, hours=10.0),         # too close to close → no
        rec("KXHIGHPHIL-26OCT15-B70", 0.65, hours=50.0),        # too far → no
        rec("KXHIGHSEA-26OCT15-B64", 0.65, size=0.0),           # nothing showing at the ask → no
        rec("KXHIGHCHI-26OCT15-B66", 0.65, bid=0.20),           # spread 0.45 > MAX_SPREAD → no
        rec("KXHIGHNY-26OCT15-T70", 0.70, tag="synthetic"),     # modeled price → no
    ]
    chosen = [r["ticker"] for r in s90.select_candidates(recs, NOW)]
    assert chosen == ["KXHIGHMIA-26OCT15-B88", "KXHIGHTDAL-26OCT15-B72"]


def test_cap_prefers_deeper_books_and_is_deterministic():
    recs = [rec(f"KXHIGHT{c:03d}-26OCT15-B70", 0.60, size=float(i + 1)) for i, c in enumerate(range(20))]
    chosen = s90.select_candidates(recs, NOW)
    assert len(chosen) == s90.MAX_MARKETS_PER_PASS
    assert min(float(r["yes_ask_size"]) for r in chosen) == 20 - s90.MAX_MARKETS_PER_PASS + 1
    assert [r["ticker"] for r in chosen] == sorted(r["ticker"] for r in chosen)


def test_orders_are_taker_yes_buys_sized_by_visible_ask():
    recs = [rec("KXHIGHTDAL-26OCT15-B72", 0.62, size=7.0), rec("KXHIGHMIA-26OCT15-B88", 0.55, size=500.0)]
    orders = s90.S90WeatherFavoriteTaker().propose_orders(
        TapeContext(records_by_family={s90.FAMILY: recs}, now_ts=NOW.isoformat()))
    assert [(o.ticker, o.side, o.action, o.tif, o.limit_price, o.qty) for o in orders] == [
        ("KXHIGHMIA-26OCT15-B88", "yes", "buy", "ioc", 0.55, s90.QTY_PER_MARKET),
        ("KXHIGHTDAL-26OCT15-B72", "yes", "buy", "ioc", 0.62, 7),
    ]
    assert all(not o.validate() for o in orders)
    assert all(o.event_ticker == "-".join(o.ticker.split("-")[:2]) for o in orders)


def test_paper_pass_books_fills_settles_and_reports(tmp_path: Path):
    ledger = tmp_path / "ledger"
    tape = tmp_path / "tape"
    markets = [
        {"ticker": "KXHIGHTDAL-26OCT15-B72", "event_ticker": "KXHIGHTDAL-26OCT15",
         "yes_bid_dollars": "0.5900", "no_bid_dollars": "0.3800", "yes_ask_size_fp": "30.00",
         "yes_bid_size_fp": "10.00", "close_time": (NOW + timedelta(hours=29)).strftime("%Y-%m-%dT%H:%M:%SZ")},
        {"ticker": "KXHIGHMIA-26OCT15-B88", "event_ticker": "KXHIGHMIA-26OCT15",
         "yes_bid_dollars": "0.1000", "no_bid_dollars": "0.8800", "yes_ask_size_fp": "30.00",
         "yes_bid_size_fp": "10.00", "close_time": (NOW + timedelta(hours=29)).strftime("%Y-%m-%dT%H:%M:%SZ")},
    ]
    s = pass_.run_propose(now=NOW, markets=markets, ledger_dir=ledger, tape_dir=tape)
    assert s["n_markets"] == 2 and s["n_orders"] == 1 and s["n_fills"] == 1
    assert (tape / "dt=2026-10-15.jsonl").exists()
    # re-running the same day never double-books (idempotency from ledger content)
    s2 = pass_.run_propose(now=NOW + timedelta(minutes=5), markets=markets, ledger_dir=ledger, tape_dir=tape)
    assert s2["n_accepted"] == 0
    # settle: the favorite wins → +$1 per contract on 20 contracts bought at 0.62
    later = NOW + timedelta(hours=40)
    st = pass_.run_settle(now=later, ledger_dir=ledger, results={"KXHIGHTDAL-26OCT15-B72": "yes"})
    assert st["n_settled"] == 1
    rep = pass_.run_report(ledger_dir=ledger)
    assert rep["settled_contracts"] == 20 and rep["hit_rate"] == 1.0
    # P&L = (1 - 0.62) * 20 - fee ; fee = roundup_cent(0.07 * 0.62 * 0.38) * 20 = 0.02 * 20
    assert rep["realized_pnl"] == pytest.approx(0.38 * 20 - 0.40, abs=0.01)


def test_live_gate_blocks_without_auth_and_credentials(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    monkeypatch.setattr(pass_, "LIVE_AUTH", tmp_path / "LIVE-AUTH-S90.md")
    errs = pass_.live_gate_errors()
    assert any("missing" in e for e in errs) and any("KALSHI_API_KEY_ID" in e for e in errs)
    markets = [{"ticker": "KXHIGHTDAL-26OCT15-B72", "event_ticker": "KXHIGHTDAL-26OCT15",
                "yes_bid_dollars": "0.5900", "no_bid_dollars": "0.3800", "yes_ask_size_fp": "30.00",
                "close_time": (NOW + timedelta(hours=29)).strftime("%Y-%m-%dT%H:%M:%SZ")}]
    s = pass_.run_propose(now=NOW, markets=markets, live=True, ledger_dir=tmp_path / "l", tape_dir=tmp_path / "t")
    assert s["live_blocked"] and "n_fills" not in s

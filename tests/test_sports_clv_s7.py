"""Q4/S7b CLV trade-set construction — pure offline post-processing of S7a's tape,
no network. Exercises decision-time candle selection, outcome->side mapping, the
edge/trade rule, fee application, and the game-drop reasons."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from core.timeutil import _parse_iso
from scripts import sports_clv_s7 as clv
from core.pricing import TAKER_FEE_RATE
from scripts.fee_breakeven import fee_per_contract

CLOSE_TIME = "2026-01-10T22:00:00Z"
CLOSE_TS = int(_parse_iso(CLOSE_TIME).timestamp())
DECISION_TS = CLOSE_TS - int(clv.DECISION_OFFSET_HOURS * 3600)  # 2026-01-10T18:00:00Z


def _candle(end_period_ts, ask_close):
    return {
        "end_period_ts": end_period_ts,
        "yes_ask": {"close_dollars": f"{ask_close:.4f}"},
        "yes_bid": {"close_dollars": "0.0000"},
    }


def _outcome(ticker, sub_title, ask_at_decision, result="yes",
            close_time=CLOSE_TIME, extra_candles=True):
    candles = [_candle(DECISION_TS, ask_at_decision)]
    if extra_candles:
        candles = [_candle(DECISION_TS - 6 * 3600, ask_at_decision + 0.5)] + candles + \
                  [_candle(DECISION_TS + 3 * 3600, 0.99)]
    return {
        "market_ticker": ticker,
        "yes_sub_title": sub_title,
        "result": result,
        "close_time": close_time,
        "candles": candles,
    }


def _game_record(event_ticker="KXTEST-26JAN10ALPBET", run_id="20260110T000000Z",
                 matched=True, home_ask=0.40, away_ask=0.35, tie_ask=0.20,
                 home_result="yes", away_result="no", tie_result="no",
                 fair_home=0.50, fair_away=0.30, fair_draw=0.20,
                 home_team="Alpha", away_team="Beta"):
    odds_match = {"matched": matched}
    if matched:
        odds_match.update({"fair_home": fair_home, "fair_away": fair_away, "fair_draw": fair_draw})
    return {
        "kalshi_event_ticker": event_ticker,
        "run_id": run_id,
        "home_team": home_team, "away_team": away_team,
        "odds_match": odds_match,
        "outcomes": [
            _outcome(f"{event_ticker}-HOME", f"Reg Time: {home_team}", home_ask, home_result),
            _outcome(f"{event_ticker}-AWAY", f"Reg Time: {away_team}", away_ask, away_result),
            _outcome(f"{event_ticker}-TIE", "Reg Time: Tie", tie_ask, tie_result),
        ],
    }


# --------------------------------------------------------------------------- #
# map_outcome_side
# --------------------------------------------------------------------------- #
def test_map_outcome_side_matches_home_away_tie():
    assert clv.map_outcome_side("Reg Time: Alpha", "Alpha", "Beta") == "home"
    assert clv.map_outcome_side("Reg Time: Beta", "Alpha", "Beta") == "away"
    assert clv.map_outcome_side("Reg Time: Tie", "Alpha", "Beta") == "tie"


def test_map_outcome_side_applies_team_aliases():
    assert clv.map_outcome_side("Reg Time: Iran", "IR Iran", "Beta") == "home"


def test_map_outcome_side_none_when_unrecognized():
    assert clv.map_outcome_side("Reg Time: Gamma", "Alpha", "Beta") is None


# --------------------------------------------------------------------------- #
# decision_candle
# --------------------------------------------------------------------------- #
def test_decision_candle_picks_latest_at_or_before():
    candles = [_candle(DECISION_TS - 3600, 0.10), _candle(DECISION_TS, 0.20),
              _candle(DECISION_TS + 3600, 0.30)]
    c = clv.decision_candle(candles, DECISION_TS)
    assert c["end_period_ts"] == DECISION_TS
    assert c["yes_ask"]["close_dollars"] == "0.2000"


def test_decision_candle_none_when_all_candles_after():
    candles = [_candle(DECISION_TS + 3600, 0.30)]
    assert clv.decision_candle(candles, DECISION_TS) is None


# --------------------------------------------------------------------------- #
# dedupe_latest
# --------------------------------------------------------------------------- #
def test_dedupe_latest_keeps_the_max_run_id_per_event():
    older = _game_record(run_id="20260110T000000Z", home_ask=0.10)
    newer = _game_record(run_id="20260111T000000Z", home_ask=0.99)
    out = clv.dedupe_latest([older, newer])
    assert len(out) == 1
    assert out[0]["outcomes"][0]["candles"][1]["yes_ask"]["close_dollars"] == "0.9900"


# --------------------------------------------------------------------------- #
# build_game_trades
# --------------------------------------------------------------------------- #
def test_build_game_trades_only_positive_edge_side_trades():
    rec = _game_record()
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert drop_reason is None
    assert len(trades) == 1
    t = trades[0]
    assert t["side"] == "home"
    assert t["raw_yes_ask"] == pytest.approx(0.40)
    bsum = 0.40 + 0.35 + 0.20
    assert t["bracket_sum"] == pytest.approx(bsum)
    assert t["normalized_ask"] == pytest.approx(0.40 / bsum)
    assert t["nominal_edge"] == pytest.approx(0.50 - 0.40 / bsum)
    expected_fee = fee_per_contract(0.40, TAKER_FEE_RATE)
    assert t["fee"] == pytest.approx(expected_fee)
    assert t["gross_pnl"] == pytest.approx(1.0 - 0.40)
    assert t["net_pnl"] == pytest.approx(1.0 - 0.40 - expected_fee)
    assert t["price_source_tag_kalshi"] == "real_ask"
    assert t["price_source_tag_odds"] == "synthetic"
    assert t["member_count"] == 3


def test_build_game_trades_losing_trade_is_still_included():
    rec = _game_record(home_result="no")
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert drop_reason is None
    assert len(trades) == 1
    assert trades[0]["gross_pnl"] == pytest.approx(0.0 - 0.40)


def test_build_game_trades_min_edge_filters_out_marginal_edge():
    rec = _game_record()
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.10)
    assert drop_reason is None
    assert trades == []  # home's ~7.9c edge doesn't clear a 10c bar


def test_build_game_trades_drops_on_unmatched_odds():
    rec = _game_record(matched=False)
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert trades == []
    assert drop_reason == "odds_unmatched"


def test_build_game_trades_drops_on_missing_decision_candle():
    rec = _game_record()
    rec["outcomes"][0]["candles"] = [_candle(DECISION_TS + 3600, 0.40)]  # only a post-decision candle
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert trades == []
    assert drop_reason.startswith("missing_decision_candle")


def test_build_game_trades_drops_on_unmapped_outcome_side():
    rec = _game_record()
    rec["outcomes"][1]["yes_sub_title"] = "Reg Time: Nonexistent"
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert trades == []
    assert drop_reason.startswith("unmapped_outcome_side")


def test_build_game_trades_drops_on_wrong_outcome_count():
    rec = _game_record()
    rec["outcomes"] = rec["outcomes"][:2]
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert trades == []
    assert drop_reason.startswith("unexpected_outcome_count")


def test_build_game_trades_drops_on_inconsistent_close_time():
    rec = _game_record()
    rec["outcomes"][0]["close_time"] = "2026-01-11T22:00:00Z"
    trades, drop_reason = clv.build_game_trades(rec, min_edge=0.0)
    assert trades == []
    assert drop_reason == "inconsistent_close_time"


# --------------------------------------------------------------------------- #
# run() end-to-end
# --------------------------------------------------------------------------- #
def test_run_end_to_end_writes_trades_and_summary(tmp_path):
    in_path = tmp_path / "worldcup2026.jsonl"
    usable = _game_record(event_ticker="KXTEST-26JAN10ALPBET")
    unmatched = _game_record(event_ticker="KXTEST-26JAN11GAMDEL", matched=False)
    with open(in_path, "w") as f:
        f.write(json.dumps(usable) + "\n")
        f.write(json.dumps(unmatched) + "\n")

    out_dir = tmp_path / "out"
    summary = clv.run(in_path=in_path, store=out_dir, min_edge=0.0)

    assert summary["n_games_in_tape"] == 2
    assert summary["n_games_usable"] == 1
    assert summary["n_games_dropped"] == 1
    assert summary["drop_reasons"] == {"odds_unmatched": 1}
    assert summary["n_trades"] == 1
    assert summary["mean_net_pnl"] is not None

    trades_path = out_dir / "trades.jsonl"
    assert trades_path.exists()
    lines = [json.loads(l) for l in trades_path.read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["kalshi_event_ticker"] == "KXTEST-26JAN10ALPBET"
    assert (out_dir / "summary.json").exists()


def test_run_on_missing_input_file_returns_zero_games(tmp_path):
    summary = clv.run(in_path=tmp_path / "does-not-exist.jsonl", store=tmp_path / "out")
    assert summary["n_games_in_tape"] == 0
    assert summary["n_trades"] == 0
    assert summary["mean_net_pnl"] is None

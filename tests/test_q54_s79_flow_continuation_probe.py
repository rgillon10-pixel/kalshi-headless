"""Offline tests for `scripts/q54_s79_flow_continuation_probe.py` (Q54 / S79).

Two jobs, and the second one is the unusual one:

  1. the ordinary unit tests — signal, entry, band, unit, fee, verdict wiring;
  2. THE SEAL. This probe was committed before its data gate opened, so the tests must pin
     that it CANNOT peek: that the pre-registration is hash-locked, that the sealed report
     carries no outcome-derived field, and that the outcome-reading functions are never
     reached while the gate is shut. A probe built early with a peek-hole would have already
     spent the pre-registration it exists to protect.

Every test is offline: synthetic fixtures, or the committed tape pinned to a FIXED day file
rather than the live glob (a test that globs an open-ended live family red-lines the moment
the collector lands a new day — the exact hygiene failure the Q42 pins hit).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import q54_s79_flow_continuation_probe as Q  # noqa: E402

LIVE_TRADE_DAY = REPO / "tape" / "kalshi_trades" / "dt=2026-08-03.jsonl"
_real_tape = pytest.mark.skipif(not LIVE_TRADE_DAY.exists(),
                                reason="committed trade tape day not present")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _print(ts, yes_price, side, count=100.0, trade_id="t"):
    return {"ts": float(ts), "yes_price": float(yes_price), "taker_book_side": side,
            "count": float(count), "trade_id": trade_id}


def _write_day(tmp_path, records, day="2026-08-03"):
    d = tmp_path / "trades"
    d.mkdir(exist_ok=True)
    p = d / f"dt={day}.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return d


def _raw(ticker, created_time, yes_price, side, count=100.0, trade_id="x"):
    return {"ticker": ticker, "created_time": created_time, "yes_price": yes_price,
            "no_price": round(1.0 - yes_price, 2), "taker_book_side": side,
            "count": count, "trade_id": trade_id, "price_source_tag": "broker_truth",
            "schema_version": "kalshi_trades.v1"}


def _settlement_root(tmp_path, results):
    """A minimal settlement source `core.settlement_sources` can read: the Q51 cache shape."""
    root = tmp_path / "tape"
    d = root / "q51_settlement_cache"
    d.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": "q51_settlement_cache.v1", "price_source_tag": "broker_truth",
               "day": "2026-08-03",
               "markets": {t: {"result": r, "status": "finalized", "close_time": None,
                               "event_ticker": None} for t, r in results.items()}}
    (d / "settlement.json").write_text(json.dumps(payload), encoding="utf-8")
    return str(root)


# --------------------------------------------------------------------------- #
# THE SEAL
# --------------------------------------------------------------------------- #
def test_preregistration_hash_is_sealed():
    """The sealed spec's digest. If this fails, a spec constant moved — which after the gate
    opens means the design was tuned with outcomes visible. Re-pinning it is a declaration,
    not a fix."""
    assert Q.PREREG_SHA256 == (
        "3f56818136b97206e2915af55728cf044735abba6f00754d4d5c3849a280205c")


def test_preregistration_hash_tracks_values_not_ordering():
    spec = dict(Q.PREREGISTRATION)
    reordered = {k: spec[k] for k in sorted(spec, reverse=True)}
    assert Q.preregistration_sha256(reordered) == Q.PREREG_SHA256
    spec["lookback_minutes"] = 31
    assert Q.preregistration_sha256(spec) != Q.PREREG_SHA256


def test_sealed_report_carries_no_outcome_field(tmp_path):
    tape = _write_day(tmp_path, [_raw("KXAGAME-26AUG03AB-A", "2026-08-03T01:00:00Z", 0.5,
                                      Q.TAKER_BUYS)])
    rep = Q.run(tape_dir=tape, settlement_root=str(tmp_path / "empty"))
    assert rep["verdict"] == "GATED-by-adequacy"
    assert Q.sealed_report_key_violations(rep) == []


def test_sealed_run_never_reads_an_outcome_value(tmp_path, monkeypatch):
    """The refusal is structural: with the gate shut, the only function that reads a result's
    VALUE must not be reached. Monkeypatched to explode if it ever is."""
    def _boom(*a, **k):
        raise AssertionError("outcome_map() reached while the adequacy gate was shut")

    monkeypatch.setattr(Q, "outcome_map", _boom)
    monkeypatch.setattr(Q, "score_rows", _boom)
    tape = _write_day(tmp_path, [
        _raw("KXAGAME-26AUG03AB-A", "2026-08-03T01:00:00Z", 0.5, Q.TAKER_BUYS),
        _raw("KXAGAME-26AUG03AB-A", "2026-08-03T02:00:00Z", 0.5, Q.TAKER_BUYS),
    ])
    root = _settlement_root(tmp_path, {"KXAGAME-26AUG03AB-A": "yes"})
    rep = Q.run(tape_dir=tape, settlement_root=root)
    assert rep["status"] == "INSUFFICIENT DATA"


def test_sealed_key_violation_detector_actually_fires():
    """A guard that cannot fail is not a guard (the vacuous-pass attack)."""
    assert Q.sealed_report_key_violations({"population": {"mean_pnl": 1.0}}) == ["mean_pnl"]


# --------------------------------------------------------------------------- #
# signal
# --------------------------------------------------------------------------- #
def test_signed_flow_signs_by_the_L279_orientation():
    prints = [_print(100, 0.5, Q.TAKER_BUYS, 7.0), _print(200, 0.5, Q.TAKER_SELLS, 3.0)]
    assert Q.signed_flow(prints, 300) == pytest.approx(4.0)


def test_signed_flow_respects_the_lookback_window():
    prints = [_print(0, 0.5, Q.TAKER_BUYS, 50.0), _print(1000, 0.5, Q.TAKER_BUYS, 5.0)]
    assert Q.signed_flow(prints, 1000, lookback_s=100.0) == pytest.approx(5.0)


def test_signed_flow_keeps_fractional_counts():
    """Sizes are FLOATS (L47) — int-coercion would silently drop a fractional count."""
    prints = [_print(10, 0.5, Q.TAKER_BUYS, 0.5)]
    assert Q.signed_flow(prints, 100) == pytest.approx(0.5)


def test_signed_flow_ignores_a_print_with_an_unusable_count():
    prints = [_print(10, 0.5, Q.TAKER_BUYS, 5.0), dict(_print(20, 0.5, Q.TAKER_BUYS),
                                                       count=None)]
    assert Q.signed_flow(prints, 100) == pytest.approx(5.0)


def test_signed_flow_ignores_an_unknown_side():
    prints = [_print(10, 0.5, "elsewhere", 9.0)]
    assert Q.signed_flow(prints, 100) == 0.0


def test_decision_instants_start_a_full_lookback_after_the_first_print():
    prints = [_print(0, 0.5, Q.TAKER_BUYS), _print(10 * 3600, 0.5, Q.TAKER_BUYS)]
    ts = Q.decision_instants(prints)
    assert ts and ts[0] >= Q.LOOKBACK_S
    assert all(t % Q.GRID_S == 0 for t in ts)


def test_decision_instants_empty_on_a_short_span():
    prints = [_print(0, 0.5, Q.TAKER_BUYS), _print(60, 0.5, Q.TAKER_BUYS)]
    assert Q.decision_instants(prints) == []


def test_first_agreeing_print_matches_direction_and_lag():
    prints = [_print(100, 0.5, Q.TAKER_SELLS), _print(150, 0.6, Q.TAKER_BUYS, trade_id="hit")]
    assert Q.first_agreeing_print(prints, 100, 1)["trade_id"] == "hit"
    assert Q.first_agreeing_print(prints, 100, 1, max_lag_s=10.0) is None


def test_first_agreeing_print_for_a_selling_signal():
    prints = [_print(100, 0.5, Q.TAKER_SELLS, trade_id="sell")]
    assert Q.first_agreeing_print(prints, 100, -1)["trade_id"] == "sell"


# --------------------------------------------------------------------------- #
# entry enumeration
# --------------------------------------------------------------------------- #
def _game_records(ticker, side, yes_price=0.5, entry_id="entry"):
    """One game's prints: an early seed print (so the 30-min lookback is complete by the
    01:00 grid instant), three flow prints INSIDE that lookback, and an entry print just
    after the instant."""
    recs = [_raw(ticker, "2026-08-03T00:00:00Z", yes_price, side, 1.0, f"{entry_id}-seed")]
    recs += [_raw(ticker, f"2026-08-03T00:{m:02d}:00Z", yes_price, side, 200.0)
             for m in (35, 40, 45)]
    recs.append(_raw(ticker, "2026-08-03T01:00:30Z", yes_price, side, 200.0, entry_id))
    return recs


def _flow_tape(tmp_path, side, yes_price=0.5, ticker="KXAGAME-26AUG03AB-A"):
    return _write_day(tmp_path, _game_records(ticker, side, yes_price))


def test_entry_candidate_takes_the_yes_side_on_positive_flow(tmp_path):
    prints = Q.load_all_prints(_flow_tape(tmp_path, Q.TAKER_BUYS))
    rows = Q.entry_candidates(prints, Q.eligible_tickers(prints))
    assert [r["side"] for r in rows] == [Q.SIDE_YES]
    assert rows[0]["entry_price"] == pytest.approx(0.5)
    assert rows[0]["entry_trade_id"] == "entry"
    assert rows[0]["price_source_tag"] == "broker_truth"


def test_entry_candidate_takes_the_no_side_on_negative_flow(tmp_path):
    prints = Q.load_all_prints(_flow_tape(tmp_path, Q.TAKER_SELLS, yes_price=0.7))
    rows = Q.entry_candidates(prints, Q.eligible_tickers(prints))
    assert [r["side"] for r in rows] == [Q.SIDE_NO]
    assert rows[0]["entry_price"] == pytest.approx(0.3)


def test_entry_candidate_dropped_outside_the_price_band(tmp_path):
    prints = Q.load_all_prints(_flow_tape(tmp_path, Q.TAKER_BUYS, yes_price=0.99))
    assert Q.entry_candidates(prints, Q.eligible_tickers(prints)) == []


def test_entry_candidate_dropped_below_the_flow_threshold(tmp_path):
    recs = [_raw("KXAGAME-26AUG03AB-A", "2026-08-03T00:00:00Z", 0.5, Q.TAKER_BUYS, 1.0),
            _raw("KXAGAME-26AUG03AB-A", "2026-08-03T00:40:00Z", 0.5, Q.TAKER_BUYS, 1.0),
            _raw("KXAGAME-26AUG03AB-A", "2026-08-03T01:00:30Z", 0.5, Q.TAKER_BUYS, 1.0)]
    prints = Q.load_all_prints(_write_day(tmp_path, recs))
    assert Q.entry_candidates(prints, Q.eligible_tickers(prints)) == []


def test_entry_candidate_dropped_when_no_agreeing_print_arrives_in_time(tmp_path):
    recs = [_raw("KXAGAME-26AUG03AB-A", "2026-08-03T00:00:00Z", 0.5, Q.TAKER_BUYS, 1.0)]
    recs += [_raw("KXAGAME-26AUG03AB-A", f"2026-08-03T00:{m:02d}:00Z", 0.5, Q.TAKER_BUYS, 200.0)
             for m in (35, 40, 45)]
    recs.append(_raw("KXAGAME-26AUG03AB-A", "2026-08-03T01:30:00Z", 0.5, Q.TAKER_BUYS, 200.0))
    prints = Q.load_all_prints(_write_day(tmp_path, recs))
    assert Q.entry_candidates(prints, Q.eligible_tickers(prints)) == []


def test_eligible_tickers_excludes_non_game_and_kxmve(tmp_path):
    recs = [_raw("KXBTCD-26AUG03-B", "2026-08-03T00:05:00Z", 0.5, Q.TAKER_BUYS),
            _raw("KXMVEGAME-26AUG03AB-A", "2026-08-03T00:05:00Z", 0.5, Q.TAKER_BUYS),
            _raw("KXAGAME-26AUG03AB-A", "2026-08-03T00:05:00Z", 0.5, Q.TAKER_BUYS)]
    prints = Q.load_all_prints(_write_day(tmp_path, recs))
    assert Q.eligible_tickers(prints) == ["KXAGAME-26AUG03AB-A"]


def test_load_all_prints_rejects_a_non_broker_truth_line(tmp_path):
    bad = _raw("KXAGAME-26AUG03AB-A", "2026-08-03T00:05:00Z", 0.5, Q.TAKER_BUYS)
    bad["price_source_tag"] = "midpoint"
    assert Q.load_all_prints(_write_day(tmp_path, [bad])) == {}


def test_unit_is_the_game_not_the_outcome_leg():
    assert Q.M.game_of("KXMLBGAME-26AUG032005LADCHC-LAD") == "KXMLBGAME-26AUG032005LADCHC"


# --------------------------------------------------------------------------- #
# adequacy gates
# --------------------------------------------------------------------------- #
def _rows(n_units, side=Q.SIDE_YES):
    return [{"ticker": f"T{i}", "unit": f"G{i}", "side": side, "entry_price": 0.5}
            for i in range(n_units)]


def test_population_gate_shut_below_the_unit_floor():
    rows = _rows(9)
    pop = Q.population_report(rows, frozenset(r["ticker"] for r in rows), {})
    assert pop["admissible"] is False
    assert "below_min_units" in pop["gate_reasons"]
    assert pop["units_short_of_floor"] == 1


def test_population_gate_shut_without_sign_variation():
    rows = _rows(12)
    pop = Q.population_report(rows, frozenset(r["ticker"] for r in rows), {})
    assert pop["gate_reasons"] == ["no_sign_variation"]
    assert pop["sign_variation"]["units_per_side"] == {"no": 0, "yes": 12}


def test_population_gate_shut_when_the_minority_side_is_a_single_game():
    rows = _rows(12)
    rows[0]["side"] = Q.SIDE_NO
    pop = Q.population_report(rows, frozenset(r["ticker"] for r in rows), {})
    assert pop["sign_variation"]["minority_side_units"] == 1
    assert pop["admissible"] is False


def test_population_gate_open_with_units_and_sign_variation():
    rows = _rows(12)
    rows[0]["side"] = Q.SIDE_NO
    rows[1]["side"] = Q.SIDE_NO
    pop = Q.population_report(rows, frozenset(r["ticker"] for r in rows), {})
    assert pop["gate_reasons"] == []
    assert pop["admissible"] is True


def test_population_counts_only_settled_markets():
    rows = _rows(12)
    pop = Q.population_report(rows, frozenset({"T0"}), {})
    assert pop["n_entry_candidates_all"] == 12
    assert pop["n_entry_candidates_settled"] == 1
    assert pop["n_units"] == 1


def test_settled_ticker_set_returns_no_outcome_value(tmp_path):
    root = _settlement_root(tmp_path, {"KXAGAME-26AUG03AB-A": "yes",
                                       "KXAGAME-26AUG03CD-C": "scalar"})
    settled, coverage = Q.settled_ticker_set(["KXAGAME-26AUG03AB-A", "KXAGAME-26AUG03CD-C"],
                                             root=root)
    assert settled == frozenset({"KXAGAME-26AUG03AB-A"})
    blob = json.dumps(coverage).lower()
    assert "yes" not in blob and "scalar" not in blob


# --------------------------------------------------------------------------- #
# scoring (reachable only past the gate)
# --------------------------------------------------------------------------- #
def test_score_rows_pays_one_taker_fee_on_a_winning_yes():
    from core.pricing import TAKER_FEE_RATE, fee_per_contract
    row = {"ticker": "T", "unit": "G", "side": Q.SIDE_YES, "entry_price": 0.40}
    out = Q.score_rows([row], {"T": 1})
    assert out[0]["pnl"] == pytest.approx(1.0 - 0.40 - fee_per_contract(0.40, TAKER_FEE_RATE))
    assert out[0]["won"] is True


def test_score_rows_no_side_wins_when_the_market_resolves_no():
    out = Q.score_rows([{"ticker": "T", "unit": "G", "side": Q.SIDE_NO,
                         "entry_price": 0.30}], {"T": 0})
    assert out[0]["won"] is True
    assert out[0]["pnl"] > 0


def test_score_rows_drops_an_unscoreable_ticker_rather_than_calling_it_a_loss():
    """L52: a missing/scalar result must never be booked as a loss."""
    assert Q.score_rows([{"ticker": "T", "unit": "G", "side": Q.SIDE_YES,
                          "entry_price": 0.5}], {}) == []


def test_unit_values_group_by_game():
    scored = [{"unit": "G1", "pnl": 1.0}, {"unit": "G1", "pnl": -1.0}, {"unit": "G2", "pnl": 0.5}]
    assert Q.unit_values(scored) == {"G1": [1.0, -1.0], "G2": [0.5]}


def test_fee_rate_is_the_taker_rate_from_core_pricing():
    from core.pricing import TAKER_FEE_RATE
    assert Q.FEE_RATE == TAKER_FEE_RATE
    assert Q.PREREGISTRATION["fee_legs"] == 1


# --------------------------------------------------------------------------- #
# end-to-end past the gate (synthetic tape)
# --------------------------------------------------------------------------- #
def _many_game_tape(tmp_path, n_games=12, n_no=3):
    recs = []
    results = {}
    for i in range(n_games):
        tk = f"KXAGAME-26AUG03G{i:02d}-A"
        side = Q.TAKER_SELLS if i < n_no else Q.TAKER_BUYS
        recs += _game_records(tk, side, 0.50, entry_id=f"e{i}")
        results[tk] = "yes" if i % 2 == 0 else "no"
    return _write_day(tmp_path, recs), _settlement_root(tmp_path, results)


def test_end_to_end_reaches_a_verdict_once_both_gates_open(tmp_path):
    tape, root = _many_game_tape(tmp_path)
    rep = Q.run(tape_dir=tape, settlement_root=root)
    assert rep["population"]["admissible"] is True
    assert rep["verdict"] in {"DEAD-by-CI", "DEAD-by-adequacy", "ALIVE-PROVISIONAL"}
    assert rep["bootstrap"]["n_units"] == 12
    assert rep["price_source_tag"] == "broker_truth"


def test_alive_is_only_ever_provisional(tmp_path):
    tape, root = _many_game_tape(tmp_path)
    rep = Q.run(tape_dir=tape, settlement_root=root)
    assert "ALIVE" not in str(rep["verdict"]) or rep["verdict"] == "ALIVE-PROVISIONAL"
    assert "verifier" in str(rep["verdict_note"])


def test_end_to_end_still_refuses_when_only_the_sign_gate_is_shut(tmp_path):
    tape, root = _many_game_tape(tmp_path, n_no=0)
    rep = Q.run(tape_dir=tape, settlement_root=root)
    assert rep["gate_reasons"] == ["no_sign_variation"]
    assert Q.sealed_report_key_violations(rep) == []


def test_report_is_json_serializable(tmp_path):
    tape, root = _many_game_tape(tmp_path)
    json.dumps(Q.run(tape_dir=tape, settlement_root=root))


def test_main_runs_without_writing(tmp_path, capsys):
    assert Q.main(["--no-write"]) == 0
    assert "Q54 / S79" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# committed tape — pinned to ONE fixed day file, never the live glob
# --------------------------------------------------------------------------- #
@_real_tape
def test_committed_day_population_is_pinned(tmp_path):
    d = tmp_path / "one_day"
    d.mkdir()
    (d / LIVE_TRADE_DAY.name).symlink_to(LIVE_TRADE_DAY)
    prints = Q.load_all_prints(d)
    tickers = Q.eligible_tickers(prints)
    rows = Q.entry_candidates(prints, tickers)
    assert len(prints) == 42
    assert len(tickers) == 38
    assert len(rows) == 82
    assert sum(1 for r in rows if r["side"] == Q.SIDE_NO) == 5


@_real_tape
def test_committed_tape_gate_is_shut_and_no_outcome_leaks():
    """The live end-to-end. Settlement coverage only ever grows, so the unit count is
    asserted as a FLOOR — a pinned equality here would red-line on the next settled game,
    which is exactly the event this probe is waiting for."""
    rep = Q.run()
    pop = rep["population"]
    assert pop["n_units"] >= 8
    if not pop["admissible"]:
        assert rep["verdict"] == "GATED-by-adequacy"
        assert Q.sealed_report_key_violations(rep) == []


@_real_tape
def test_committed_day_reproduces_on_an_independent_code_path():
    """REDUNDANCY, not verification (no `verifier` subagent is dispatchable in this harness).

    Re-derives the entry population from the raw JSONL on a separate code path — integer
    cents instead of floats, its own window arithmetic, orientation constants passed in as
    locals rather than imported — and requires exact agreement. Zero disagreement cannot
    catch an error the two paths SHARE (the L279 failure mode), but it does catch the
    ordinary transcription and off-by-one class.
    """
    from core.timeutil import parse_iso_utc

    buy, sell = "bid", "ask"
    look, grid, lag, min_flow, lo, hi = 1800, 3600, 300, 10.0, 2, 98
    by = {}
    with open(LIVE_TRADE_DAY, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("price_source_tag") != "broker_truth":
                continue
            tk = r["ticker"]
            series = tk.split("-", 1)[0]
            if not series.endswith("GAME") or series.startswith("KXMVE"):
                continue
            ts = parse_iso_utc(r["created_time"]).timestamp()
            by.setdefault(tk, []).append(
                (ts, int(round(r["yes_price"] * 100)), r["taker_book_side"], float(r["count"])))
    for v in by.values():
        v.sort()

    cands = []
    for tk, seq in by.items():
        start = seq[0][0] + look
        k = 0
        while k * grid < start:
            k += 1
        while k * grid <= seq[-1][0]:
            inst = k * grid
            net = sum(c if s == buy else -c for (ts, _, s, c) in seq if inst - look < ts <= inst)
            if abs(net) >= min_flow:
                want = buy if net > 0 else sell
                for (ts, cents, s, _c) in seq:
                    if ts < inst:
                        continue
                    if ts > inst + lag:
                        break
                    if s == want:
                        px = cents if net > 0 else 100 - cents
                        if lo <= px <= hi:
                            cands.append((tk, "yes" if net > 0 else "no"))
                        break
            k += 1

    d = Path(LIVE_TRADE_DAY).parent
    prints = Q.load_all_prints(d) if len(list(d.glob("dt=*.jsonl"))) == 1 else None
    if prints is None:  # more days committed since: compare on the pinned day only
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / LIVE_TRADE_DAY.name).symlink_to(LIVE_TRADE_DAY)
            prints = Q.load_all_prints(Path(td))
    rows = Q.entry_candidates(prints, Q.eligible_tickers(prints))
    assert len(rows) == len(cands)
    assert sorted((r["ticker"], r["side"]) for r in rows) == sorted(cands)

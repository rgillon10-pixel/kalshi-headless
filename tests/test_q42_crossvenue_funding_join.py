"""scripts.q42_crossvenue_funding_join — fully offline over injected fixture records.

Covers: ISO->ms + nearest-hour rounding (jitter tolerant), per-leg collection (ticker/mode
filter, dedup, None-skip), the 8h window join (clean vs partial-excluded, jitter-tolerant
hour matching, differential arithmetic), compounding, and the end-to-end per-asset
characterization incl. the join-sanity anchor. No network, no tape files touched."""
from __future__ import annotations

import importlib.util
import math
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "q42_crossvenue_funding_join",
    Path(__file__).resolve().parents[1] / "scripts" / "q42_crossvenue_funding_join.py")
J = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(J)

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# fixture builders
# --------------------------------------------------------------------------- #
def _kalshi_record(prints, mode="backfill"):
    return {"record_type": "funding_rates", "mode": mode, "price_source_tag": "broker_truth",
            "prints": prints}


def _kprint(ticker, funding_time, rate):
    return {"market_ticker": ticker, "funding_time": funding_time, "funding_rate": rate,
            "mark_price": 1.0}


def _hl_record(coin, prints):
    return {"record_type": "funding_history", "coin": coin, "mode": "backfill",
            "price_source_tag": "broker_truth", "prints": prints}


def _hlprint(coin, time_ms, rate):
    return {"coin": coin, "time_ms": time_ms, "funding_rate": rate,
            "funding_time": J._iso_from_ms(time_ms) if hasattr(J, "_iso_from_ms") else None}


def _hours_for(funding_time, rates, jitter_ms=17):
    """Build the 8 HL hourly prints (hT-7…hT) matching a Kalshi print, with ms jitter."""
    t_ms = J._iso_to_ms(funding_time)
    out = []
    for i, r in enumerate(reversed(rates)):        # rates given oldest->newest
        h = t_ms - i * J.HOUR_MS + jitter_ms
        out.append({"coin": "BTC", "time_ms": h, "funding_rate": r})
    return out


# --------------------------------------------------------------------------- #
# time helpers
# --------------------------------------------------------------------------- #
def test_iso_to_ms_and_hour_index_round_jitter():
    ms = J._iso_to_ms("2026-06-03T20:00:00Z")
    assert ms is not None
    # a few ms past :00 rounds to the SAME hour index (jitter must not shift the bucket)
    assert J._hour_index(ms + 17) == J._hour_index(ms)
    assert J._hour_index(ms) == ms // J.HOUR_MS


def test_iso_to_ms_bad_grammar_none():
    assert J._iso_to_ms("") is None
    assert J._iso_to_ms("not-a-time") is None


def test_compound_matches_product():
    rates = [0.0000125] * 8
    assert math.isclose(J._compound(rates), math.prod(1 + r for r in rates) - 1, rel_tol=1e-12)


# --------------------------------------------------------------------------- #
# collection
# --------------------------------------------------------------------------- #
def test_collect_kalshi_filters_dedups():
    recs = [_kalshi_record([
        _kprint("KXBTCPERP", "2026-06-03T20:00:00Z", 0.0),
        _kprint("KXBTCPERP", "2026-06-03T20:00:00Z", 0.0),   # dup -> dropped
        _kprint("KXETHPERP", "2026-06-03T20:00:00Z", 0.0001),
        _kprint("KXSOLPERP", "2026-06-03T20:00:00Z", 0.0002),  # not requested
    ]),
        _kalshi_record([_kprint("KXBTCPERP", "2026-06-04T04:00:00Z", 0.0005)], mode="recent")]
    out = J.collect_kalshi_prints(recs, ["KXBTCPERP", "KXETHPERP"], mode="backfill")
    tks = [p["ticker"] for p in out]
    assert tks.count("KXBTCPERP") == 1 and tks.count("KXETHPERP") == 1
    assert "KXSOLPERP" not in tks               # unrequested ticker excluded
    assert len(out) == 2                        # the recent-mode 0.0005 print is excluded


def test_collect_kalshi_both_modes_included_and_cross_mode_dedup():
    """L137: the real run must read BOTH backfill (one-shot dump) AND recent (ongoing
    finalized prints); a (ticker, funding_time) seen in BOTH modes is deduped once."""
    recs = [
        _kalshi_record([_kprint("KXBTCPERP", "2026-06-03T20:00:00Z", 0.0)], mode="backfill"),
        _kalshi_record([
            _kprint("KXBTCPERP", "2026-06-03T20:00:00Z", 0.0),        # cross-mode dup -> dropped
            _kprint("KXBTCPERP", "2026-07-22T04:00:00Z", 0.0005),     # NEW recent-only window
        ], mode="recent"),
    ]
    out = J.collect_kalshi_prints(recs, ["KXBTCPERP"], mode=("backfill", "recent"))
    fts = sorted(p["funding_time"] for p in out)
    assert fts == ["2026-06-03T20:00:00Z", "2026-07-22T04:00:00Z"]   # both modes, dup deduped
    # backfill-only would have frozen the join at the single 06-03 window:
    bf_only = J.collect_kalshi_prints(recs, ["KXBTCPERP"], mode="backfill")
    assert [p["funding_time"] for p in bf_only] == ["2026-06-03T20:00:00Z"]


def test_collect_hl_dedups_and_skips_none():
    recs = [_hl_record("BTC", [
        {"coin": "BTC", "time_ms": 1780444800000, "funding_rate": 0.0000125},
        {"coin": "BTC", "time_ms": 1780444800017, "funding_rate": 0.0000200},  # same hour -> dup
        {"coin": "BTC", "time_ms": 1780448400000, "funding_rate": None},        # None -> skipped
    ])]
    table = J.collect_hl_hourly(recs, ["BTC"])
    assert len(table["BTC"]) == 1              # dedup on hour index
    hi = J._hour_index(1780444800000)
    assert table["BTC"][hi] == 0.0000125       # first wins


def test_collect_hl_dedups_cross_branch_duplicate_records():
    """kb/lessons/00-lessons.md L170 / findings/2026-07-26-hyperliquid-funding-tape-audit.md:
    `collection.hyperliquid_funding._committed_time_ms` dedups against the LOCAL working
    tree only, so two collector passes racing on unmerged `tape/hourly-*` branches can each
    independently archive the SAME (coin, time_ms) print in TWO SEPARATE `funding_history`
    records (confirmed on real tape: `('BTC', 1784725200052)` written by both commit
    `d845dfb` and `2235aa3`). This pins that `collect_hl_hourly` — the only current
    consumer that aggregates raw `prints` rows — is robust to that: reading the two
    records back-to-back must still yield exactly one hour_index entry, not a double-count."""
    dup_ms = 1780444800000
    rec_a = _hl_record("BTC", [{"coin": "BTC", "time_ms": dup_ms, "funding_rate": 0.0000125}])
    rec_b = _hl_record("BTC", [{"coin": "BTC", "time_ms": dup_ms, "funding_rate": 0.0000125}])
    table = J.collect_hl_hourly([rec_a, rec_b], ["BTC"])
    assert len(table["BTC"]) == 1
    assert table["BTC"][J._hour_index(dup_ms)] == 0.0000125


# --------------------------------------------------------------------------- #
# join
# --------------------------------------------------------------------------- #
def test_join_clean_window_computes_differential():
    ft = "2026-06-03T20:00:00Z"
    kal = J.collect_kalshi_prints([_kalshi_record([_kprint("KXBTCPERP", ft, 0.0)])],
                                  ["KXBTCPERP"])
    hl = J.collect_hl_hourly([_hl_record("BTC", _hours_for(ft, [0.0000125] * 8))], ["BTC"])
    joined, n_partial = J.join_asset(kal, hl["BTC"])
    assert n_partial == 0 and len(joined) == 1
    w = joined[0]
    assert w["hl_n_hours"] == 8
    assert math.isclose(w["hl_8h_compound"], J._compound([0.0000125] * 8), rel_tol=1e-12)
    # differential = HL 8h-equiv - kalshi(0.0)
    assert math.isclose(w["differential"], w["hl_8h_compound"], rel_tol=1e-12)
    assert w["price_source_tag"] == "broker_truth"


def test_join_partial_window_excluded():
    ft = "2026-06-03T20:00:00Z"
    kal = J.collect_kalshi_prints([_kalshi_record([_kprint("KXBTCPERP", ft, 0.0)])],
                                  ["KXBTCPERP"])
    # only 7 of 8 hours present -> partial, excluded, not zero-filled
    hl = J.collect_hl_hourly([_hl_record("BTC", _hours_for(ft, [0.0000125] * 8)[:7])], ["BTC"])
    joined, n_partial = J.join_asset(kal, hl["BTC"])
    assert joined == [] and n_partial == 1


# --------------------------------------------------------------------------- #
# end-to-end characterization
# --------------------------------------------------------------------------- #
def test_analyze_end_to_end_sanity_and_zero_fractions():
    # two BTC windows: one clamped Kalshi (0.0) + one nonzero; HL never zero
    fts = ["2026-06-03T20:00:00Z", "2026-06-04T04:00:00Z"]
    kprints = [_kprint("KXBTCPERP", fts[0], 0.0), _kprint("KXBTCPERP", fts[1], 0.0002)]
    hlprints = _hours_for(fts[0], [0.0000125] * 8) + _hours_for(fts[1], [0.00002] * 8)
    perp = [_kalshi_record(kprints)]
    hlrecs = [_hl_record("BTC", hlprints)]
    rep = J.analyze(perp, hlrecs, asset_map={"BTC": {"kalshi_ticker": "KXBTCPERP",
                                                     "hl_coin": "BTC"}})
    a = rep["assets"]["BTC"]
    assert a["n_windows_joined"] == 2 and a["n_windows_partial_excluded"] == 0
    assert a["kalshi_zero_fraction"] == 0.5            # 1 of 2 clamped
    assert a["hl_zero_fraction"] == 0.0                # HL never zero
    # joined zero-fraction reproduces the full population (join dropped nothing)
    assert a["join_sanity"]["joined_matches_full_population"] is True
    assert a["differential_mean"] is not None
    assert a["price_source_tag"] == "broker_truth"


# --------------------------------------------------------------------------- #
# L320 — the part-1 BTC constant is a HISTORICAL PIN, not a live pass/fail gate
# --------------------------------------------------------------------------- #
def test_l320_historical_pin_drift_reports_sign_and_magnitude():
    d = J.historical_pin_drift(0.7222, 0.669, 0.05)
    assert d["pin"] == 0.669 and d["current"] == 0.7222
    assert round(d["drift"], 4) == 0.0532 and round(d["abs_drift"], 4) == 0.0532
    assert d["beyond_tolerance"] is True
    # the record must say, in itself, that it is not a gate — a reader cannot mistake
    # `beyond_tolerance: true` for a defect.
    assert d["is_live_gate"] is False
    assert "L320" in d["note"]


def test_l320_historical_pin_drift_signs_both_directions_and_respects_tolerance():
    below = J.historical_pin_drift(0.60, 0.669, 0.05)
    assert below["drift"] < 0 and below["beyond_tolerance"] is True
    inside = J.historical_pin_drift(0.7048, 0.669, 0.05)
    assert inside["drift"] > 0 and inside["beyond_tolerance"] is False
    # exactly at the tolerance is NOT beyond it (strict >)
    assert J.historical_pin_drift(0.719, 0.669, 0.05)["beyond_tolerance"] is False


def test_l320_historical_pin_drift_none_population_fabricates_nothing():
    assert J.historical_pin_drift(None, 0.669, 0.05) is None


def test_l320_report_carries_the_drift_record_and_keeps_the_legacy_keys():
    fts = ["2026-06-03T20:00:00Z", "2026-06-04T04:00:00Z"]
    kprints = [_kprint("KXBTCPERP", fts[0], 0.0), _kprint("KXBTCPERP", fts[1], 0.0002)]
    hlprints = _hours_for(fts[0], [0.0000125] * 8) + _hours_for(fts[1], [0.00002] * 8)
    rep = J.analyze([_kalshi_record(kprints)], [_hl_record("BTC", hlprints)],
                    asset_map={"BTC": {"kalshi_ticker": "KXBTCPERP", "hl_coin": "BTC"}})
    s = rep["assets"]["BTC"]["join_sanity"]
    # legacy keys retained verbatim (append-only report shape)
    assert s["expected_part1_btc"] == J.PART1_BTC_ZERO_FRACTION
    assert "within_tolerance_of_part1_btc" in s
    # and the new record declares the disposition
    pin = s["part1_btc_historical_pin"]
    assert pin["is_live_gate"] is False
    assert pin["current"] == rep["assets"]["BTC"]["kalshi_zero_fraction"]
    # the LIVE gate is the re-derived full-population one, and it is unaffected
    assert s["joined_matches_full_population"] is True


def test_l320_the_pin_is_declared_in_the_modules_own_registry():
    """The L320 invariant's site-local escape hatch must actually name this constant —
    a declaration that drifts out of sync silently re-arms the false alarm."""
    assert "PART1_BTC_ZERO_FRACTION" in J.HISTORICAL_POPULATION_PINS
    assert "NOT A GATE" in J.HISTORICAL_POPULATION_PINS["PART1_BTC_ZERO_FRACTION"]


def test_l320_acceptance_real_tape_pin_drift_is_reported_not_gated():
    """HARD acceptance test over REAL committed tape (L191), written growth-safe (L320's own
    lesson: a floor/direction property, never an equality on a growing population).

    The point is NOT the value of the drift — it moved from +0.0532 (2026-08-09, 198
    windows/asset) to +0.0358 (2026-08-12, 210 windows/asset) with no code change, which is
    exactly why it may not be a gate. The pinned properties are structural: the join is
    healthy against the CURRENT population, and the historical pin is reported as drift."""
    perp = J.load_records(str(ROOT / "tape" / "perp_tape" / "dt=*.jsonl"))
    hl = J.load_records(str(ROOT / "tape" / "hyperliquid_funding" / "dt=*.jsonl"))
    if not perp or not hl:
        return  # tape absent in this checkout: nothing to pin, never a fabricated pass
    rep = J.analyze(perp, hl)
    btc = rep["assets"]["BTC"]
    if not btc["n_windows_joined"]:
        return
    s = btc["join_sanity"]
    # 1. the LIVE gate — re-derived from the current population — passes.
    assert s["joined_matches_full_population"] is True
    # 2. the population only grows (floor, not equality).
    assert btc["n_windows_joined"] >= 198
    # 3. the historical pin is a drift record, never a pass/fail.
    pin = s["part1_btc_historical_pin"]
    assert pin["is_live_gate"] is False
    assert pin["pin"] == 0.669
    assert isinstance(pin["beyond_tolerance"], bool)
    # 4. and the drift is real: today's reading is NOT the frozen number.
    assert pin["current"] != pin["pin"]

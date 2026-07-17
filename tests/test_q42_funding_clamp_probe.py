"""tests for scripts/q42_funding_clamp_probe — fully offline, fixture-based.

Covers: zero-fraction/total-count math, dedup on (market_ticker, funding_time), None
funding_rate excluded (never treated as zero), nonzero distribution stats, the
clamp-vs-rounding discriminator (clear-gap vs one-tick-from-zero fixtures), hour-of-day
bucketing, the data-adequacy path for too-few-nonzero contracts, and load-path injectability
via a record list and a tmp_path .jsonl file."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import q42_funding_clamp_probe as q42  # noqa: E402


def _pr(ticker, ft, rate, mark=1.0):
    return {"market_ticker": ticker, "funding_time": ft, "funding_rate": rate, "mark_price": mark}


def _fr_record(prints, mode="backfill"):
    return {"record_type": "funding_rates", "mode": mode,
            "price_source_tag": "broker_truth", "prints": prints}


# --------------------------------------------------------------------------- #
# load-path injectability
# --------------------------------------------------------------------------- #
def test_load_records_accepts_record_list():
    recs = [{"record_type": "funding_rates", "mode": "backfill", "prints": []}]
    assert q42.load_records(recs) == recs


def test_load_records_reads_jsonl_file(tmp_path):
    p = tmp_path / "dt=2026-07-17.jsonl"
    rec = _fr_record([_pr("KXBTCPERP", "2026-06-03T20:00:00Z", 0.0)])
    p.write_text(json.dumps(rec) + "\n")
    out = q42.load_records(str(p))
    assert len(out) == 1 and out[0]["record_type"] == "funding_rates"


def test_collect_only_matching_mode():
    recs = [_fr_record([_pr("A", "t1", 0.0)], mode="backfill"),
            _fr_record([_pr("B", "t2", 0.0)], mode="recent")]
    prints, meta = q42.collect_funding_prints(recs, mode="backfill")
    assert meta["n_records_matched"] == 1 and meta["n_prints_read"] == 1
    assert prints[0]["market_ticker"] == "A"
    assert meta["source_tags_seen"] == ["broker_truth"]


# --------------------------------------------------------------------------- #
# zero-fraction / total-count
# --------------------------------------------------------------------------- #
def test_zero_fraction_and_total_count():
    prints = [_pr("X", "2026-06-03T20:00:00Z", 0.0),
              _pr("X", "2026-06-04T04:00:00Z", 0.0),
              _pr("X", "2026-06-04T12:00:00Z", 0.0003),
              _pr("X", "2026-06-04T20:00:00Z", -0.0005)]
    cs = q42.contract_stats(prints)
    assert cs["n_prints_total"] == 4
    assert cs["n_zero"] == 2
    assert cs["zero_fraction"] == 0.5
    assert cs["price_source_tag"] == "broker_truth"


# --------------------------------------------------------------------------- #
# dedup
# --------------------------------------------------------------------------- #
def test_dedup_drops_duplicate_ticker_time_pairs():
    prints = [_pr("X", "t1", 0.0), _pr("X", "t1", 0.0),  # dup key
              _pr("X", "t2", 0.0002), _pr("Y", "t1", 0.0)]
    deduped, dropped = q42.dedup_prints(prints)
    assert dropped == 1
    assert len(deduped) == 3
    keys = {(p["market_ticker"], p["funding_time"]) for p in deduped}
    assert keys == {("X", "t1"), ("X", "t2"), ("Y", "t1")}


# --------------------------------------------------------------------------- #
# None excluded, never zero
# --------------------------------------------------------------------------- #
def test_none_rate_excluded_and_counted_not_zero():
    prints = [_pr("X", "t1", None), _pr("X", "t2", 0.0), _pr("X", "t3", 0.0004)]
    cs = q42.contract_stats(prints)
    assert cs["n_none_excluded"] == 1
    assert cs["n_prints_total"] == 2          # None NOT in denominator
    assert cs["n_zero"] == 1
    assert cs["zero_fraction"] == 0.5
    assert cs["nonzero_distribution"]["n"] == 1


# --------------------------------------------------------------------------- #
# nonzero distribution stats
# --------------------------------------------------------------------------- #
def test_nonzero_distribution_stats():
    nz = [0.0004, -0.0002, 0.0006, -0.0008]
    d = q42.nonzero_distribution(nz)
    assert d["n"] == 4
    assert d["min"] == -0.0008
    assert d["max"] == 0.0006
    assert abs(d["mean"] - (0.0004 - 0.0002 + 0.0006 - 0.0008) / 4) < 1e-12
    assert d["min_abs"] == 0.0002
    assert d["max_abs"] == 0.0008
    assert d["n_positive"] == 2
    assert d["n_negative"] == 2
    assert d["std"] is not None


def test_infer_tick_smallest_gap():
    # distinct |values| 0.0002, 0.0004, 0.0005 -> gaps 0.0002, 0.0001 -> min 0.0001
    assert abs(q42.infer_tick([0.0002, 0.0004, 0.0005, 0.0002]) - 0.0001) < 1e-12
    assert q42.infer_tick([0.0003]) is None   # single distinct -> undefined


# --------------------------------------------------------------------------- #
# clamp vs rounding discriminator
# --------------------------------------------------------------------------- #
def test_clamp_signature_clear_gap():
    # zeros + only large-magnitude nonzeros with near-duplicate values -> tiny inferred tick,
    # min_abs far from 0 -> many ticks_from_zero -> CLAMP.
    prints = ([_pr("C", f"2026-06-{d:02d}T20:00:00Z", 0.0) for d in range(3, 13)]
              + [_pr("C", "2026-06-14T20:00:00Z", 0.0010),
                 _pr("C", "2026-06-15T20:00:00Z", 0.0010001),  # near-dup -> tiny gap
                 _pr("C", "2026-06-16T20:00:00Z", 0.0011),
                 _pr("C", "2026-06-17T20:00:00Z", -0.0012)])
    cs = q42.contract_stats(prints)
    cvr = cs["clamp_vs_rounding"]
    assert cvr["verdict_code"] == "clamp"
    assert cvr["ticks_from_zero"] >= q42.CLAMP_TICK_RATIO_HIGH


def test_rounding_signature_one_tick_from_zero():
    # nonzeros are exact integer multiples of a tick, smallest == one tick -> ROUNDING.
    prints = ([_pr("R", f"2026-06-{d:02d}T20:00:00Z", 0.0) for d in range(3, 8)]
              + [_pr("R", "2026-06-09T20:00:00Z", 0.0001),   # == one tick
                 _pr("R", "2026-06-10T20:00:00Z", 0.0002),
                 _pr("R", "2026-06-11T20:00:00Z", -0.0003)])
    cs = q42.contract_stats(prints)
    cvr = cs["clamp_vs_rounding"]
    assert cvr["verdict_code"] == "rounding"
    assert cvr["ticks_from_zero"] <= q42.CLAMP_TICK_RATIO_LOW


def test_data_adequacy_too_few_nonzero():
    # one nonzero print -> cannot infer a tick / characterize -> data-adequacy, no fabrication.
    prints = ([_pr("L", f"2026-06-{d:02d}T20:00:00Z", 0.0) for d in range(3, 20)]
              + [_pr("L", "2026-06-20T20:00:00Z", 0.00014)])
    cs = q42.contract_stats(prints)
    cvr = cs["clamp_vs_rounding"]
    assert cvr["verdict_code"] == "data_adequacy"
    assert cvr["ticks_from_zero"] is None


# --------------------------------------------------------------------------- #
# hour-of-day bucketing
# --------------------------------------------------------------------------- #
def test_hour_of_day_buckets_and_zero_fraction():
    prints = [_pr("X", "2026-06-03T20:00:00Z", 0.0),
              _pr("X", "2026-06-04T20:00:00Z", 0.0005),
              _pr("X", "2026-06-04T04:00:00Z", 0.0),
              _pr("X", "2026-06-05T04:00:00Z", 0.0),
              _pr("X", "2026-06-04T99:00:00Z", 0.0)]   # bad hour -> skipped
    hod = q42.hour_of_day_zero_fraction(prints)
    assert set(hod) == {20, 4}
    assert hod[20]["n"] == 2 and hod[20]["zeros"] == 1 and hod[20]["zero_fraction"] == 0.5
    assert hod[4]["n"] == 2 and hod[4]["zeros"] == 2 and hod[4]["zero_fraction"] == 1.0


def test_hour_of_day_excludes_none_rate():
    prints = [_pr("X", "2026-06-03T20:00:00Z", None),
              _pr("X", "2026-06-04T20:00:00Z", 0.0)]
    hod = q42.hour_of_day_zero_fraction(prints)
    assert hod[20]["n"] == 1 and hod[20]["zeros"] == 1


def test_parse_hour_grammar_mismatch_returns_none():
    assert q42._hour_of_day("") is None
    assert q42._hour_of_day("2026-06-03 20:00:00") is None   # no 'T'
    assert q42._hour_of_day("2026-06-03T20:00:00Z") == 20


# --------------------------------------------------------------------------- #
# end-to-end analyze
# --------------------------------------------------------------------------- #
def test_analyze_end_to_end_dedup_and_pooled():
    recs = [_fr_record([
        _pr("A", "2026-06-03T20:00:00Z", 0.0),
        _pr("A", "2026-06-03T20:00:00Z", 0.0),   # dup dropped
        _pr("A", "2026-06-04T04:00:00Z", 0.0006),
        _pr("B", "2026-06-03T20:00:00Z", 0.0),
    ], mode="backfill")]
    rep = q42.analyze(recs, mode="backfill")
    assert rep["price_source_tag"] == "broker_truth"
    assert rep["load"]["n_dedup_dropped"] == 1
    assert rep["load"]["n_prints_after_dedup"] == 3
    assert rep["n_contracts"] == 2
    assert rep["pooled"]["n_prints_total"] == 3
    assert rep["pooled"]["n_zero"] == 2

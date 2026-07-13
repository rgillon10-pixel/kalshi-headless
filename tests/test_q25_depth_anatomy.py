"""scripts.q25_depth_tape_anatomy — Q25 depth-tape anatomy (read-only, discovery-class).
Offline: no network, no tape reads — every fixture is injected/synthetic (s20 precedent)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from scripts import q25_depth_tape_anatomy as q25

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# ticker close-time parser — the three confirmed grammars + unparsed
# --------------------------------------------------------------------------- #
def test_parse_crypto_hour_is_ET():
    # KXBTC-26JUL0621-...: hour 21 ET (EDT, UTC-4 in July) => 2026-07-07 01:00 UTC
    p = q25.parse_ticker_close("KXBTC-26JUL0621-B71750")
    assert p["is_crypto"] is True
    assert p["resolution"] == "fine"
    assert p["close_utc"] == datetime(2026, 7, 7, 1, 0, tzinfo=UTC)


def test_parse_eth_hour_is_ET():
    p = q25.parse_ticker_close("KXETH-26JUL0622-B1080")
    # hour 22 ET => 2026-07-07 02:00 UTC
    assert p["close_utc"] == datetime(2026, 7, 7, 2, 0, tzinfo=UTC)
    assert p["family"] == "KXETH"


def test_parse_sports_hhmm_is_utc():
    # KXAFLGAME-26JUL160530SKSGEE-GEE: date 26JUL16 + HHMM 0530 (UTC) + letters
    p = q25.parse_ticker_close("KXAFLGAME-26JUL160530SKSGEE-GEE")
    assert p["is_crypto"] is False
    assert p["resolution"] == "fine"
    assert p["close_utc"] == datetime(2026, 7, 16, 5, 30, tzinfo=UTC)


def test_parse_sports_hhmm_four_digit_boundary():
    # KXMLBGAME-26JUL061845HOUWSH-WSH: HHMM 1845
    p = q25.parse_ticker_close("KXMLBGAME-26JUL061845HOUWSH-WSH")
    assert p["close_utc"] == datetime(2026, 7, 6, 18, 45, tzinfo=UTC)
    assert p["resolution"] == "fine"


def test_parse_sports_date_only_is_coarse_end_of_day():
    p = q25.parse_ticker_close("KXWCGAME-26JUL06USABEL-USA")
    assert p["resolution"] == "coarse"
    assert p["close_utc"] == datetime(2026, 7, 6, 23, 59, 59, tzinfo=UTC)


def test_parse_wnba_date_only_coarse():
    p = q25.parse_ticker_close("KXWNBAGAME-26JUL12CHIDAL-CHI")
    assert p["resolution"] == "coarse"
    assert p["close_utc"] == datetime(2026, 7, 12, 23, 59, 59, tzinfo=UTC)


def test_parse_unparseable_middle():
    p = q25.parse_ticker_close("KXWEIRD-NOTADATE-XYZ")
    assert p["resolution"] == "unparsed"
    assert p["close_utc"] is None
    assert p["family"] == "KXWEIRD"


def test_parse_crypto_bad_hour_unparsed():
    # hour 99 is not a valid hour => unparsed (never guessed)
    p = q25.parse_ticker_close("KXBTC-26JUL0699-B1")
    assert p["resolution"] == "unparsed"


def test_parse_invalid_month_unparsed():
    p = q25.parse_ticker_close("KXMLBGAME-26XXX061845HOUWSH-WSH")
    assert p["resolution"] == "unparsed"


def test_parse_no_middle_segment_unparsed():
    p = q25.parse_ticker_close("KXBTC")
    assert p["resolution"] == "unparsed"


# --------------------------------------------------------------------------- #
# ttc bucketing (incl. coarse-clamp + post_close + unparsed)
# --------------------------------------------------------------------------- #
def test_ttc_buckets_edges():
    close = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    mk = lambda mins: close - q25.timedelta(minutes=mins)
    assert q25.ttc_bucket(close, mk(5), "fine") == "<15m"
    assert q25.ttc_bucket(close, mk(30), "fine") == "15-60m"
    assert q25.ttc_bucket(close, mk(180), "fine") == "1-6h"
    assert q25.ttc_bucket(close, mk(600), "fine") == "6-24h"
    assert q25.ttc_bucket(close, mk(2000), "fine") == ">24h"


def test_ttc_post_close_when_captured_after_close():
    close = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
    after = datetime(2026, 7, 10, 13, 0, tzinfo=UTC)
    assert q25.ttc_bucket(close, after, "fine") == "post_close"


def test_ttc_coarse_clamps_out_of_subhour_buckets():
    close = datetime(2026, 7, 10, 23, 59, 59, tzinfo=UTC)
    # captured 5 min before an end-of-day coarse close -> would be <15m, clamped to 1-6h
    cap = datetime(2026, 7, 10, 23, 55, 0, tzinfo=UTC)
    assert q25.ttc_bucket(close, cap, "coarse") == "1-6h"
    # a coarse capture genuinely 10h out stays 6-24h (not clamped)
    cap2 = datetime(2026, 7, 10, 14, 0, 0, tzinfo=UTC)
    assert q25.ttc_bucket(close, cap2, "coarse") == "6-24h"


def test_ttc_unparsed_resolution():
    assert q25.ttc_bucket(None, datetime(2026, 7, 10, tzinfo=UTC), "unparsed") == "unparsed"


# --------------------------------------------------------------------------- #
# mirror ask-size + bid-size extraction (incl. empty -> 0)
# --------------------------------------------------------------------------- #
def test_ask_side_size_is_top_no_bid():
    rec = {"no_bids": [[0.34, 1500.0], [0.33, 472.0]]}
    assert q25.ask_side_size(rec) == pytest.approx(1500.0)


def test_ask_side_size_empty_is_zero():
    assert q25.ask_side_size({"no_bids": []}) == 0.0
    assert q25.ask_side_size({}) == 0.0


def test_bid_side_size_is_top_yes_bid():
    rec = {"yes_bids": [[0.62, 1500.0]]}
    assert q25.bid_side_size(rec) == pytest.approx(1500.0)


def test_bid_side_size_empty_is_zero():
    assert q25.bid_side_size({"yes_bids": []}) == 0.0
    assert q25.bid_side_size({}) == 0.0


# --------------------------------------------------------------------------- #
# one-sidedness flags
# --------------------------------------------------------------------------- #
def test_one_sided_flags_two_sided():
    rec = {"yes_bids": [[0.5, 10]], "no_bids": [[0.5, 10]], "best_yes_bid": 0.5,
           "best_no_bid": 0.5}
    assert q25.one_sided_flags(rec) == (False, False)


def test_one_sided_flags_empty_no_side():
    rec = {"yes_bids": [[0.5, 10]], "no_bids": [], "best_yes_bid": 0.5, "best_no_bid": None}
    assert q25.one_sided_flags(rec) == (False, True)


def test_one_sided_flags_zero_best_counts_empty():
    rec = {"yes_bids": [[0.0, 10]], "no_bids": [[0.5, 10]], "best_yes_bid": 0, "best_no_bid": 0.5}
    assert q25.one_sided_flags(rec) == (True, False)


# --------------------------------------------------------------------------- #
# frozen streak computation on hand-built sequences
# --------------------------------------------------------------------------- #
def _rec(ts, byb, bya, bnb, bna, yb_sz=100.0, nb_sz=100.0, yb_px=0.5, nb_px=0.5):
    return {
        "ticker": "KXWCGAME-26JUL06USABEL-USA", "captured_at": ts,
        "best_yes_bid": byb, "best_yes_ask": bya, "best_no_bid": bnb, "best_no_ask": bna,
        "yes_bids": [[yb_px, yb_sz]], "no_bids": [[nb_px, nb_sz]],
    }


def test_frozen_all_unchanged(monkeypatch):
    # three identical BBO captures -> 2 pairs, both frozen; one run of length 3
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5),
            _rec("2026-07-06T11:00:00+00:00", 0.5, 0.55, 0.45, 0.5),
            _rec("2026-07-06T12:00:00+00:00", 0.5, 0.55, 0.45, 0.5)]
    out = _scan_records(monkeypatch, recs)
    cat = out["streaks_category"]["soccer"]
    assert cat == [3]  # one run of 3 unchanged captures
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.n_pairs == 2 and cell.frozen == 2


def test_frozen_none_unchanged(monkeypatch):
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5),
            _rec("2026-07-06T11:00:00+00:00", 0.4, 0.55, 0.45, 0.5),
            _rec("2026-07-06T12:00:00+00:00", 0.3, 0.55, 0.45, 0.5)]
    out = _scan_records(monkeypatch, recs)
    assert sorted(out["streaks_category"]["soccer"]) == [1, 1, 1]
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.n_pairs == 2 and cell.frozen == 0


def test_frozen_partial(monkeypatch):
    # frozen, then move: runs [2, 1]
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5),
            _rec("2026-07-06T11:00:00+00:00", 0.5, 0.55, 0.45, 0.5),
            _rec("2026-07-06T12:00:00+00:00", 0.4, 0.55, 0.45, 0.5)]
    out = _scan_records(monkeypatch, recs)
    assert sorted(out["streaks_category"]["soccer"]) == [1, 2]
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.n_pairs == 2 and cell.frozen == 1


def test_frozen_single_capture_no_pairs(monkeypatch):
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5)]
    out = _scan_records(monkeypatch, recs)
    assert out["streaks_category"]["soccer"] == [1]  # a run of length 1, zero pairs
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.n_pairs == 0


# --------------------------------------------------------------------------- #
# turnover formula
# --------------------------------------------------------------------------- #
def test_turnover_size_drop_positive(monkeypatch):
    # ask side (no_bid) price stable, size drops 100 -> 60 => turnover 0.4
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=100.0, nb_px=0.45),
            _rec("2026-07-06T11:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=60.0, nb_px=0.45)]
    out = _scan_records(monkeypatch, recs)
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.turn_ask == [pytest.approx(0.4)]


def test_turnover_size_increase_is_zero(monkeypatch):
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=60.0, nb_px=0.45),
            _rec("2026-07-06T11:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=100.0, nb_px=0.45)]
    out = _scan_records(monkeypatch, recs)
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.turn_ask == [pytest.approx(0.0)]


def test_turnover_price_change_excluded(monkeypatch):
    # ask-side best price moved 0.45 -> 0.40 => pair excluded from ask turnover
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=100.0, nb_px=0.45),
            _rec("2026-07-06T11:00:00+00:00", 0.5, 0.55, 0.40, 0.5, nb_sz=60.0, nb_px=0.40)]
    out = _scan_records(monkeypatch, recs)
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.turn_ask == []


def test_turnover_zero_prev_size_skipped(monkeypatch):
    recs = [_rec("2026-07-06T10:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=0.0, nb_px=0.45),
            _rec("2026-07-06T11:00:00+00:00", 0.5, 0.55, 0.45, 0.5, nb_sz=0.0, nb_px=0.45)]
    out = _scan_records(monkeypatch, recs)
    cell = out["cells"][("category", "soccer", "_ALL")]
    assert cell.turn_ask == []


# --------------------------------------------------------------------------- #
# <20 insufficient sentinel + category rollup
# --------------------------------------------------------------------------- #
def test_cell_summary_insufficient_below_min_n():
    c = q25.CellAgg()
    for _ in range(5):  # below MIN_N=20
        c.bid_sizes.append(10.0)
        c.ask_sizes.append(20.0)
        c.n_cap += 1
    summ = q25._cell_summary(c)
    assert summ["queue_depth"] == "insufficient"
    assert summ["one_sided"] == "insufficient"
    assert summ["staleness"] == "insufficient"
    assert summ["turnover"]["pooled"] == "insufficient"


def test_cell_summary_present_at_or_above_min_n():
    c = q25.CellAgg()
    for i in range(20):
        c.bid_sizes.append(float(i))
        c.ask_sizes.append(float(i))
        c.n_cap += 1
        c.yes_empty += (1 if i < 5 else 0)
    summ = q25._cell_summary(c)
    assert summ["queue_depth"] != "insufficient"
    assert summ["one_sided"]["yes_side_empty"] == pytest.approx(5 / 20)


def test_category_rollup_mapping():
    assert q25.category_of("KXBTC") == "crypto"
    assert q25.category_of("KXETH") == "crypto"
    assert q25.category_of("KXMLBGAME") == "baseball"
    assert q25.category_of("KXWCGAME") == "soccer"
    assert q25.category_of("KXWNBAGAME") == "basketball"
    assert q25.category_of("KXAFLGAME") == "sports_other"
    # an unmapped sports family falls to sports_other, never dropped
    assert q25.category_of("KXTOTALLYNEWGAME") == "sports_other"


# --------------------------------------------------------------------------- #
# percentile / mean helpers
# --------------------------------------------------------------------------- #
def test_percentile_and_median():
    assert q25._median([3.0, 1.0, 2.0]) == 2.0
    assert q25._median([4.0, 1.0, 2.0, 3.0]) == pytest.approx(2.5)
    assert q25._percentile([1.0, 2.0, 3.0, 4.0], 0.25) == pytest.approx(1.75)
    assert q25._percentile([5.0], 0.9) == 5.0


# --------------------------------------------------------------------------- #
# helper: run scan() over in-memory records (monkeypatch the file reader — no tape/network)
# --------------------------------------------------------------------------- #
def _scan_records(monkeypatch, recs):
    monkeypatch.setattr(q25, "iter_depth_records", lambda _dir: iter(recs))
    return q25.scan()

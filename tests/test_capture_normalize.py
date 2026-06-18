"""Guards the bid->opposite-ask complement in capture (the price H1 trades on)."""
from collection.capture_orderbooks import normalize_snapshot


def test_normalize_derives_opposite_side_and_depth():
    ob = {"yes_dollars": [["0.30", "100"], ["0.29", "50"]],
          "no_dollars": [["0.68", "200"], ["0.67", "20"]]}
    s = normalize_snapshot("KXHIGHTLV-26JUN06-B99.5", ob)
    assert s["best_yes_bid"] == 0.30 and s["best_no_bid"] == 0.68
    # YES ask = 1 - best NO bid; NO ask = 1 - best YES bid
    assert s["best_yes_ask"] == 0.32
    assert s["best_no_ask"] == 0.70
    assert s["depth"] == 4


def test_normalize_sorts_bids_descending():
    ob = {"yes_dollars": [["0.10", "5"], ["0.40", "5"], ["0.25", "5"]], "no_dollars": []}
    s = normalize_snapshot("X-26JUN06-T70", ob)
    assert s["best_yes_bid"] == 0.40
    assert [lvl[0] for lvl in s["yes_bids"]] == [0.40, 0.25, 0.10]


def test_normalize_empty_book():
    s = normalize_snapshot("X-26JUN06-T70", {})
    assert s["depth"] == 0
    assert s["best_yes_bid"] is None and s["best_yes_ask"] is None

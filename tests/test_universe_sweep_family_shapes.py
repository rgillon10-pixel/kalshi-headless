"""Offline unit tests for scripts/universe_sweep_family_shapes.py (read-only breadth idea-gen).

No network, no committed-tape dependency: every test builds synthetic records / a tmp tape dir.
Pins the two enabling findings (schema defect A: no-side sizes dropped; mirror B) and the
two-sided / classification logic so a future reader can trust the memo's shortlist.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import universe_sweep_family_shapes as fs  # noqa: E402


def _rec(**kw):
    base = {
        "series": "KXWTIH", "event_ticker": "KXWTIH-26JUL23", "price_source_tag": "real_ask",
        "yes_ask": 0.60, "yes_ask_size": 5.0, "yes_bid": 0.55, "yes_bid_size": 4.0,
        "no_ask_size": 0.0, "no_bid_size": 0.0,  # collector drops these (schema defect A)
        "volume": 10.0, "open_interest": 20.0,
    }
    base.update(kw)
    # default the NO side to the exact Kalshi mirror (finding B) unless a test overrides it,
    # so fixtures are mirror-consistent by construction and reflect real tape.
    base.setdefault("no_ask", round(1.0 - base["yes_bid"], 6))
    base.setdefault("no_bid", round(1.0 - base["yes_ask"], 6))
    return base


def test_as_float_no_int_truncation_and_bool_guard():
    assert fs._as_float("91316.82") == 91316.82   # L47: never int-truncate a size
    assert fs._as_float(True) is None             # bool is an int subclass; not a size
    assert fs._as_float(None) is None
    assert fs._as_float("nan") != fs._as_float("nan") or fs._as_float("x") is None  # non-numeric


def test_classify_series():
    assert fs.classify_series("KXHIGHTATL") == "tested"
    assert fs.classify_series("KXBTC-...") == "tested"
    assert fs.classify_series("KXWCGAME-...") == "tested"      # via GAME
    assert fs.classify_series("KXBTCPERP") == "tested"          # via PERP
    assert fs.classify_series("KXMVESPORTSMULTIGAMEEXTENDED") == "deadtail"
    assert fs.classify_series("KXWTIH") == "untested"
    assert fs.classify_series("KXGOLDH") == "untested"


def test_mirror_holds():
    # exact mirror: no_ask == 1 - yes_bid, no_bid == 1  minus yes_ask
    assert fs.mirror_holds(_rec(yes_ask=0.60, yes_bid=0.55, no_ask=0.45, no_bid=0.40)) is True
    # broken mirror
    assert fs.mirror_holds(_rec(no_ask=0.99)) is False
    # untestable: no YES bid
    assert fs.mirror_holds(_rec(yes_bid=0.0)) is None


def test_two_sided_uses_yes_bid_not_dropped_no_ask_size():
    # a genuine two-sided book: fillable YES ask AND fillable YES bid, even though no_ask_size==0
    r = _rec(no_ask_size=0.0)
    assert fs.yes_ask_fillable(r) is True
    assert fs.yes_bid_fillable(r) is True     # uses yes_bid_size, not the dropped no_ask_size
    assert fs.is_two_sided(r) is True
    # one-sided: YES bid has no size -> not two-sided (mirror NO ask has no size either)
    r1 = _rec(yes_bid=0.0, yes_bid_size=0.0)
    assert fs.is_two_sided(r1) is False
    # a yes_ask==0 (no offer) is never fillable (L105)
    r2 = _rec(yes_ask=0.0, yes_ask_size=0.0)
    assert fs.yes_ask_fillable(r2) is False


def test_size_field_population_flags_dropped_no_side():
    recs = [_rec(), _rec(yes_bid_size=0.0, yes_bid=0.0)]
    pop = fs.size_field_population(recs)
    assert pop["n_lines"] == 2
    assert pop["nonzero"]["yes_ask_size"] == 2
    assert pop["nonzero"]["no_ask_size"] == 0   # schema defect A
    assert pop["nonzero"]["no_bid_size"] == 0


def test_analyze_on_tmp_tape(tmp_path):
    d = tmp_path / "universe_sweep"
    d.mkdir()
    lines = [
        _rec(series="KXWTIH", yes_ask=0.60, yes_bid=0.55, volume=10.0, open_interest=5.0),
        _rec(series="KXWTIH", yes_ask=0.30, yes_bid=0.29, volume=0.0, open_interest=0.0),
        _rec(series="KXMVEX", yes_ask=0.0, yes_ask_size=0.0, no_ask=1.0, volume=0.0,
             open_interest=0.0),  # deadtail no-offer
        _rec(series="KXHIGHTATL", yes_ask=0.5, yes_bid=0.49),  # tested
    ]
    (d / "dt=2026-07-23.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    rep = fs.analyze(d)
    assert rep["n_lines"] == 4
    assert rep["n_malformed"] == 0
    assert rep["mirror_check"]["frac_holds"] == 1.0
    # schema defect A visible
    assert rep["size_field_population"]["nonzero"]["no_ask_size"] == 0
    # KXWTIH is the only untested two-sided family here
    fams = {r["series"]: r for r in rep["untested_two_sided_families"]}
    assert "KXWTIH" in fams
    assert fams["KXWTIH"]["n_two_sided"] == 2
    assert fams["KXWTIH"]["n_active"] == 1
    # class totals partition all lines
    ct = rep["class_totals"]
    assert ct["untested"]["lines"] == 2
    assert ct["deadtail"]["lines"] == 1
    assert ct["tested"]["lines"] == 1


def test_malformed_line_counted_not_dropped(tmp_path):
    d = tmp_path / "universe_sweep"
    d.mkdir()
    (d / "dt=2026-07-23.jsonl").write_text(
        json.dumps(_rec()) + "\n" + "{not json\n" + "[]\n")
    rep = fs.analyze(d)
    assert rep["n_lines"] == 1
    assert rep["n_malformed"] == 2   # bad-json line + non-dict line both counted

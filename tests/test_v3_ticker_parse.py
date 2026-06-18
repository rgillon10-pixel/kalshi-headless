"""Guards the contract's named regression: a parser that silently matches ZERO
modern tickers. Two layers — a live-captured corpus (when present) and frozen
shape examples that fail loudly on drift."""
import json
from pathlib import Path

import pytest

from validation.v3_market import TICKER_RE, parse_ticker

FIX = Path(__file__).parent / "fixtures" / "kalshi_tickers_sample.json"


@pytest.mark.skipif(
    not FIX.exists(),
    reason="run `python -m validation.v3_market validate` to capture a live corpus",
)
def test_live_modern_tickers_parse_100pct():
    tickers = json.loads(FIX.read_text())
    assert tickers, "fixture is empty — capture would have written nothing"
    bad = [t for t in tickers if not TICKER_RE.match(t)]
    assert not bad, f"{len(bad)} modern tickers failed the regex: {bad[:5]}"


def test_known_modern_ticker_shapes():
    spec, err = parse_ticker("KXHIGHTLV-26JUN06-B99.5", strike_type="between",
                             floor_strike=99, cap_strike=100)
    assert err is None and spec.bucket_type == "band"
    assert spec.lo == 99.0 and spec.hi == 100.0

    spec, err = parse_ticker("KXLOWTLV-26JUN06-T78", strike_type="greater", floor_strike=78)
    assert err is None and spec.bucket_type == "threshold_above" and spec.lo == 78.0

    spec, err = parse_ticker("KXHIGHTLV-26JUN06-T99", strike_type="less", cap_strike=99)
    assert err is None and spec.bucket_type == "threshold_below" and spec.hi == 99.0


def test_strike_reconcile_mismatch_is_caught():
    # parser-derived band (99-100) vs API floor 50 must be flagged, not silently passed
    spec, err = parse_ticker("KXHIGHTLV-26JUN06-B99.5", strike_type="between",
                             floor_strike=50, cap_strike=51)
    assert err and "strike_reconcile_mismatch" in err


def test_legacy_style_ticker_fails_loudly():
    # an old cents-style bucket ('-50', no T/B prefix) must NOT silently parse
    spec, err = parse_ticker("HIGHNY-23NOV09-50")
    assert spec is None and err == "no_regex_match"

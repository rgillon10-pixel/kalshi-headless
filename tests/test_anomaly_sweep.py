"""scripts.anomaly_sweep — LOOP-QUEUE.md Q6. Both real-ask checks (complete-ladder true
arb, cross-strike monotonicity) plus a fully offline capture pass (FakeClient, no network)
with honest completeness. Mirrors tests/test_crypto_hourly.py's fixture style."""
from __future__ import annotations

import json

import pytest

from scripts import anomaly_sweep as sweep


def _mk_market(ticker, event_ticker, strike_type, yes_ask, no_ask=None,
              floor_strike=None, cap_strike=None):
    return {
        "ticker": ticker, "event_ticker": event_ticker, "strike_type": strike_type,
        "floor_strike": floor_strike, "cap_strike": cap_strike,
        "yes_ask_dollars": f"{yes_ask:.4f}" if yes_ask is not None else None,
        "no_ask_dollars": f"{no_ask:.4f}" if no_ask is not None else None,
    }


class FakeClient:
    """Minimal stand-in for validation.v3_market.Kalshi — only get_text('/markets', ...),
    served from an in-memory page list. No network, no clock."""

    base = "https://fake.test"

    def __init__(self, pages=None, fail=False):
        self.pages = pages if pages is not None else [[]]
        self.fail = fail
        self._calls = 0

    def get_text(self, path, **params):
        assert path == "/markets"
        if self.fail:
            raise RuntimeError("simulated discovery failure")
        idx = self._calls
        self._calls += 1
        items = self.pages[idx] if idx < len(self.pages) else []
        cursor = f"page{idx + 1}" if idx + 1 < len(self.pages) else None
        return json.dumps({"markets": items, "cursor": cursor})


# --------------------------------------------------------------------------- #
# check 1 — complete-ladder true arb
# --------------------------------------------------------------------------- #
def _complete_ladder(yes_asks):
    """less(cap=50) + between(50,60) + between(60,70) + greater(floor=70), contiguous."""
    lo, b1, b2, hi = yes_asks
    return [
        _mk_market("E-L", "E", "less", lo, cap_strike=50),
        _mk_market("E-B1", "E", "between", b1, floor_strike=50, cap_strike=60),
        _mk_market("E-B2", "E", "between", b2, floor_strike=60, cap_strike=70),
        _mk_market("E-H", "E", "greater", hi, floor_strike=70),
    ]


def test_bracket_arb_flags_underpriced_complete_ladder():
    members = _complete_ladder([0.05, 0.30, 0.30, 0.05])  # sum 0.70, well under $1
    hit = sweep.check_bracket_arb("E", members)
    assert hit is not None
    assert hit["kind"] == "bracket_arb"
    assert hit["member_count"] == 4
    assert hit["bracket_sum"] == pytest.approx(0.70)
    assert hit["edge"] > 0
    assert hit["price_source_tag"] == "real_ask"


def test_bracket_arb_not_flagged_when_overround_normal():
    members = _complete_ladder([0.30, 0.30, 0.30, 0.20])  # sum 1.10, ordinary overround
    assert sweep.check_bracket_arb("E", members) is None


def test_bracket_arb_skips_gapped_ladder_even_if_sum_low():
    members = [
        _mk_market("E-L", "E", "less", 0.05, cap_strike=50),
        _mk_market("E-B1", "E", "between", 0.20, floor_strike=50, cap_strike=60),
        # gap: next band starts at 75, not 60 -> not a provably complete partition
        _mk_market("E-B2", "E", "between", 0.20, floor_strike=75, cap_strike=85),
        _mk_market("E-H", "E", "greater", 0.05, floor_strike=85),
    ]
    assert sweep.check_bracket_arb("E", members) is None


def test_bracket_arb_skips_missing_open_ended_tail():
    # only "between" bands, no "less"/"greater" -> can't prove the full real line is covered
    members = [
        _mk_market("E-B1", "E", "between", 0.05, floor_strike=50, cap_strike=60),
        _mk_market("E-B2", "E", "between", 0.05, floor_strike=60, cap_strike=70),
    ]
    assert sweep.check_bracket_arb("E", members) is None


def test_bracket_arb_skips_missing_price():
    members = _complete_ladder([0.05, 0.30, 0.30, 0.05])
    members[1]["yes_ask_dollars"] = None
    assert sweep.check_bracket_arb("E", members) is None


def test_bracket_arb_tolerates_observed_tick_gap():
    # crypto's real convention: between cap 50799.99 -> next floor 50800.00 (1-cent tick)
    members = [
        _mk_market("E-L", "E", "less", 0.05, cap_strike=50799.99),
        _mk_market("E-B1", "E", "between", 0.20, floor_strike=50800.00, cap_strike=50899.99),
        _mk_market("E-H", "E", "greater", 0.05, floor_strike=50899.99),
    ]
    hit = sweep.check_bracket_arb("E", members)
    assert hit is not None  # sum 0.30, tick gaps within tolerance


# --------------------------------------------------------------------------- #
# check 2 — cross-strike monotonicity (S3)
# --------------------------------------------------------------------------- #
def test_monotonicity_flags_real_crossing_greater():
    # temp>=70 (outer, wider) vs temp>=80 (inner, narrower): inner overpriced (no_ask cheap)
    members = [
        _mk_market("E-70", "E", "greater", 0.40, no_ask=0.61, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.55, no_ask=0.45, floor_strike=80),
    ]
    hits = sweep.check_monotonicity("E", members, "greater")
    assert len(hits) == 1
    hit = hits[0]
    assert hit["kind"] == "cross_strike_monotonicity"
    assert hit["outer_ticker"] == "E-70" and hit["inner_ticker"] == "E-80"
    assert hit["edge"] > 0
    assert hit["price_source_tag"] == "real_ask"


def test_monotonicity_not_flagged_when_normally_priced():
    members = [
        _mk_market("E-70", "E", "greater", 0.60, no_ask=0.41, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.30, no_ask=0.71, floor_strike=80),
    ]
    assert sweep.check_monotonicity("E", members, "greater") == []


def test_monotonicity_flags_real_crossing_less():
    # temp<=60 (inner, narrower) vs temp<=80 (outer, wider): inner overpriced
    members = [
        _mk_market("E-60", "E", "less", 0.55, no_ask=0.46, cap_strike=60),
        _mk_market("E-80", "E", "less", 0.40, no_ask=0.61, cap_strike=80),
    ]
    hits = sweep.check_monotonicity("E", members, "less")
    assert len(hits) == 1
    assert hits[0]["outer_ticker"] == "E-80" and hits[0]["inner_ticker"] == "E-60"


def test_monotonicity_needs_at_least_two_members():
    members = [_mk_market("E-70", "E", "greater", 0.40, no_ask=0.61, floor_strike=70)]
    assert sweep.check_monotonicity("E", members, "greater") == []


def test_monotonicity_skips_missing_no_ask():
    members = [
        _mk_market("E-70", "E", "greater", 0.40, no_ask=None, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.55, no_ask=0.45, floor_strike=80),
    ]
    assert sweep.check_monotonicity("E", members, "greater") == []


# --------------------------------------------------------------------------- #
# fully offline sweep pass
# --------------------------------------------------------------------------- #
def test_run_flags_a_true_arb_end_to_end(tmp_path):
    members = _complete_ladder([0.05, 0.30, 0.30, 0.05])
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path)
    assert summary["completeness_ok"] is True
    assert summary["n_markets_scanned"] == 4
    assert summary["n_anomalies"] == 1

    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["n_event_groups"] == 1
    assert rec["n_bracket_groups_checked"] == 1
    assert rec["anomalies"][0]["kind"] == "bracket_arb"
    assert rec["completeness_ok"] is True
    assert rec["raw_sha256"]


def test_run_paginates_across_multiple_pages(tmp_path):
    page1 = [_mk_market("A-1", "A", "greater", 0.5, no_ask=0.5, floor_strike=10)]
    page2 = [_mk_market("A-2", "A", "greater", 0.3, no_ask=0.7, floor_strike=20)]
    client = FakeClient(pages=[page1, page2])
    summary = sweep.run(client=client, tape_dir=tmp_path)
    assert summary["n_markets_scanned"] == 2
    assert summary["markets_truncated"] is False


def test_run_honestly_flags_truncation_when_limit_caps_a_live_cursor(tmp_path):
    page1 = [_mk_market("A-1", "A", "greater", 0.5, no_ask=0.5, floor_strike=10)]
    page2 = [_mk_market("A-2", "A", "greater", 0.3, no_ask=0.7, floor_strike=20)]
    client = FakeClient(pages=[page1, page2])  # a 3rd page would exist past the cap
    summary = sweep.run(client=client, tape_dir=tmp_path, limit=1)
    assert summary["n_markets_scanned"] == 1
    assert summary["markets_truncated"] is True
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["markets_truncated"] is True
    # truncation is not a fetch failure -- it's a distinct, separately-honest signal
    assert rec["completeness_ok"] is True


def test_run_records_fetch_error_not_fake_success(tmp_path):
    client = FakeClient(fail=True)
    summary = sweep.run(client=client, tape_dir=tmp_path)
    assert summary["completeness_ok"] is False
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["fetch_error"] and "simulated" in rec["fetch_error"]
    assert rec["n_markets_scanned"] == 0


def test_run_skips_singleton_event_groups(tmp_path):
    # one lone market under its own event_ticker -> not a ladder, not a pair, no checks run
    members = [_mk_market("SOLO", "SOLO-EVT", "greater", 0.5, no_ask=0.5, floor_strike=10)]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path)
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["n_bracket_groups_checked"] == 0
    assert rec["n_monotonicity_groups_checked"] == 0
    assert rec["n_anomalies"] == 0


def test_main_returns_nonzero_on_incomplete_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(sweep, "TAPE", tmp_path)
    monkeypatch.setattr(sweep, "_load_venue_cfg", lambda: {"api_base": "https://fake.test"})

    class _AlwaysFailClient:
        base = "https://fake.test"

        def __init__(self, *a, **kw):
            pass

        def get_text(self, path, **params):
            raise RuntimeError("simulated")

    monkeypatch.setattr(sweep, "Kalshi", _AlwaysFailClient)
    rc = sweep.main([])
    assert rc == 1

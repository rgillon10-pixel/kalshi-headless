"""scripts.anomaly_sweep — LOOP-QUEUE.md Q6. Both real-ask checks (complete-ladder true
arb, cross-strike monotonicity) plus a fully offline capture pass (FakeClient, no network)
with honest completeness. Mirrors tests/test_crypto_hourly.py's fixture style.

Q53/L291 (2026-08-06): every fixture market now carries a `title`, because the scanner now
requires the nesting premise to be PROVEN from the market's own descriptive text
(`core.subject_identity`). `_mk_market`'s default title is a single-subject threshold ladder
rung whose label IS its own strike, so the default fixtures exercise the real
strike-attribution path rather than a degenerate "identical text" shortcut; the cross-subject
fixtures below pass explicit titles copied from committed `tape/universe_sweep/`.
"""
from __future__ import annotations

import json

import pytest

from core.io import REPO_ROOT
from core.pricing import is_fillable_ask, is_material_arb_edge, monotonicity_crossing_edge
from core.subject_identity import SUBJECT_PROVEN_SAME, SUBJECT_UNVERIFIABLE, same_subject
from scripts import anomaly_sweep as sweep


def _mk_market(ticker, event_ticker, strike_type, yes_ask, no_ask=None,
              floor_strike=None, cap_strike=None, title=None):
    strike = floor_strike if floor_strike is not None else cap_strike
    if title is None:
        title = (f"What will the value be above {strike}?" if strike is not None
                 else "What will the value be?")
    return {
        "ticker": ticker, "event_ticker": event_ticker, "strike_type": strike_type,
        "floor_strike": floor_strike, "cap_strike": cap_strike, "title": title,
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
# check 3 — cross-event logical implication (S15, Q11)
# --------------------------------------------------------------------------- #
_WC_FAMILY = {
    "id": "test_kxwcround_progression",
    "kind": "round_progression",
    "series": "KXWCROUND",
    "ticker_regex": r"^(?P<series>[A-Z0-9]+)-(?P<round_raw>\d{2}[A-Z]+)-(?P<entity>[A-Z]+)$",
    "round_order_raw_suffix_to_rank": {"QUAR": 1, "SEMI": 2, "FINAL": 3},
}


def test_implication_flags_real_crossing():
    # FINAL (harder, A) mispriced ABOVE QUARTERFINALS (easier, B) -> P(A) > P(B), impossible
    markets = [
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 0.55, no_ask=0.45),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    hits = sweep.check_cross_event_implication(markets, [_WC_FAMILY])
    assert len(hits) == 1
    hit = hits[0]
    assert hit["kind"] == "cross_event_implication"
    assert hit["family_id"] == "test_kxwcround_progression"
    assert hit["a_ticker"] == "KXWCROUND-26FINAL-USA"
    assert hit["b_ticker"] == "KXWCROUND-26QUAR-USA"
    assert hit["edge"] > 0
    assert hit["price_source_tag"] == "real_ask"


def test_implication_not_flagged_when_normally_priced():
    # ordinary case: harder round priced lower than easier round, as expected
    markets = [
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 0.10, no_ask=0.92),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    assert sweep.check_cross_event_implication(markets, [_WC_FAMILY]) == []


def test_implication_skips_missing_price():
    markets = [
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 0.55, no_ask=None),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    assert sweep.check_cross_event_implication(markets, [_WC_FAMILY]) == []


def test_implication_generates_every_round_pair_for_one_entity():
    # 3 rounds -> C(3,2) = 3 ordered (harder, easier) pairs for one team
    markets = [
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
        _mk_market("KXWCROUND-26SEMI-USA", "KXWCROUND-26SEMI", None, 0.20, no_ask=0.81),
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 0.10, no_ask=0.92),
    ]
    pairs = sweep._round_progression_pairs(markets, _WC_FAMILY)
    assert len(pairs) == 3
    seen = {(a["ticker"], b["ticker"]) for a, b in pairs}
    assert ("KXWCROUND-26SEMI-USA", "KXWCROUND-26QUAR-USA") in seen
    assert ("KXWCROUND-26FINAL-USA", "KXWCROUND-26QUAR-USA") in seen
    assert ("KXWCROUND-26FINAL-USA", "KXWCROUND-26SEMI-USA") in seen


def test_implication_ignores_non_matching_series():
    markets = [
        _mk_market("OTHERSERIES-26FINAL-USA", "OTHERSERIES-26FINAL", None, 0.55, no_ask=0.45),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    assert sweep.check_cross_event_implication(markets, [_WC_FAMILY]) == []


def test_implication_unknown_family_kind_skipped():
    markets = [
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 0.55, no_ask=0.45),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    unknown = dict(_WC_FAMILY, kind="explicit_pair")
    assert sweep.check_cross_event_implication(markets, [unknown]) == []


def test_load_implication_families_reads_config_yaml(tmp_path):
    cfg = tmp_path / "implication_pairs.yaml"
    cfg.write_text(
        "families:\n"
        "  - id: fam1\n"
        "    kind: round_progression\n"
        "    series: KXTEST\n"
        "    ticker_regex: '^(?P<series>[A-Z]+)-(?P<round_raw>\\d{2}[A-Z]+)-(?P<entity>[A-Z]+)$'\n"
        "    round_order_raw_suffix_to_rank:\n"
        "      A: 1\n"
        "      B: 2\n",
        encoding="utf-8",
    )
    families = sweep.load_implication_families(cfg)
    assert len(families) == 1
    assert families[0]["id"] == "fam1"


def test_load_implication_families_missing_file_returns_empty(tmp_path):
    assert sweep.load_implication_families(tmp_path / "nope.yaml") == []


# --------------------------------------------------------------------------- #
# the REAL committed config/implication_pairs.yaml (Q55 milestone 2, 2026-08-06):
# kxmarmadround_progression is the first LIVE (non-time-boxed-closed) family added
# alongside kxwcround_progression -- these tests exercise the real file, not a
# synthetic fixture, so a future edit to the yaml that breaks its own regex or rank
# map fails CI instead of surfacing silently on the next live pass.
# --------------------------------------------------------------------------- #
def test_real_config_loads_both_families_with_compilable_regexes():
    import re as _re
    families = sweep.load_implication_families()
    ids = {f["id"] for f in families}
    assert {"kxwcround_progression", "kxmarmadround_progression"} <= ids
    for fam in families:
        assert fam["kind"] == "round_progression"
        _re.compile(fam["ticker_regex"])  # raises if malformed
        assert fam["round_order_raw_suffix_to_rank"]


def test_kxmarmadround_family_regex_handles_alphanumeric_round_and_hyphenated_entity():
    fam = next(f for f in sweep.load_implication_families()
               if f["id"] == "kxmarmadround_progression")
    import re as _re
    regex = _re.compile(fam["ticker_regex"])
    m = regex.match("KXMARMADROUND-27R32-DUKE")
    assert m and m.group("round_raw") == "27R32" and m.group("entity") == "DUKE"
    # the one hyphenated entity code observed live (Loyola Chicago)
    m2 = regex.match("KXMARMADROUND-27T2-L-IL")
    assert m2 and m2.group("entity") == "L-IL"


def test_kxmarmadround_family_generates_full_pair_count_for_two_entities():
    fam = next(f for f in sweep.load_implication_families()
               if f["id"] == "kxmarmadround_progression")
    rounds = ["R32", "R16", "R8", "F4", "T2"]
    entities = ["DUKE", "L-IL"]
    markets = [
        _mk_market(f"KXMARMADROUND-27{r}-{e}", f"KXMARMADROUND-27{r}", None, 0.5, no_ask=0.5)
        for e in entities for r in rounds
    ]
    pairs = sweep._round_progression_pairs(markets, fam)
    # C(5,2) = 10 ordered (harder, easier) pairs per entity, 2 entities -> 20
    assert len(pairs) == 20
    assert ("KXMARMADROUND-27T2-DUKE", "KXMARMADROUND-27R32-DUKE") in {
        (a["ticker"], b["ticker"]) for a, b in pairs
    }


def test_kxmarmadround_family_flags_a_real_crossing_from_the_committed_config():
    fam = next(f for f in sweep.load_implication_families()
               if f["id"] == "kxmarmadround_progression")
    # T2 (Championship Game, harder) mispriced ABOVE R32 (Round of 32, easier) -> impossible
    markets = [
        _mk_market("KXMARMADROUND-27T2-DUKE", "KXMARMADROUND-27T2", None, 0.55, no_ask=0.45),
        _mk_market("KXMARMADROUND-27R32-DUKE", "KXMARMADROUND-27R32", None, 0.40, no_ask=0.61),
    ]
    hits = sweep.check_cross_event_implication(markets, [fam])
    assert len(hits) == 1
    assert hits[0]["family_id"] == "kxmarmadround_progression"
    assert hits[0]["a_ticker"] == "KXMARMADROUND-27T2-DUKE"
    assert hits[0]["b_ticker"] == "KXMARMADROUND-27R32-DUKE"


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


def test_run_flags_cross_event_implication_end_to_end(tmp_path):
    # each market is its own singleton event_ticker -> checks 1/2 find nothing, only the
    # cross-event implication family (check 3) sees the mispricing across the two events
    members = [
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 0.55, no_ask=0.45),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path, implication_families=[_WC_FAMILY])
    assert summary["n_anomalies"] == 1
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["n_bracket_groups_checked"] == 0
    assert rec["n_monotonicity_groups_checked"] == 0
    assert rec["n_implication_pairs_checked"] == 1
    assert rec["anomalies"][0]["kind"] == "cross_event_implication"


def test_run_defaults_to_config_file_implication_families(tmp_path, monkeypatch):
    # no implication_families passed -> run() loads config/implication_pairs.yaml itself;
    # point it at an empty family list so this stays a pure offline unit test
    monkeypatch.setattr(sweep, "load_implication_families", lambda: [])
    members = [_mk_market("SOLO", "SOLO-EVT", "greater", 0.5, no_ask=0.5, floor_strike=10)]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path)
    assert summary["n_anomalies"] == 0


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


# --------------------------------------------------------------------------- #
# the L105/L288 fillability + residue guards (built 2026-08-06, idle-run policy a)
#
# A $0.00 ask is the ABSENCE of a resting offer, not a free contract, and a bare `edge > 0`
# test admits binary-float residue as profit. Before this guard, 43,025 of the 43,038
# anomalies this scanner had ever recorded priced a $0.00 leg while carrying
# `price_source_tag: "real_ask"`. Both guards live in core.pricing (one shared site for all
# three checks); these tests pin the SCANNER's behaviour on top of them.
# --------------------------------------------------------------------------- #
def test_monotonicity_refuses_the_committed_modal_row_shape():
    """The literal modal row from `tape/anomalies/` (L288): outer ask $0.00 (nothing offered)
    against a $0.03 inner NO ask, previously flagged as a ~$0.96 'edge'."""
    members = [
        _mk_market("KXCOPPERD-T5.60", "E", "greater", 0.00, no_ask=1.00, floor_strike=5.60),
        _mk_market("KXCOPPERD-T5.86", "E", "greater", 0.97, no_ask=0.03, floor_strike=5.86),
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_monotonicity("E", members, "greater", refusals=refusals) == []
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 1
    assert refusals[sweep.REFUSAL_RESIDUE_EDGE] == 0


def test_monotonicity_refuses_a_zero_inner_no_ask_too():
    """Symmetric: the NO leg has to exist as well. Kept explicit because committed tape
    happens to contain zero of this direction — absence of evidence, not a proof of safety."""
    members = [
        _mk_market("E-70", "E", "greater", 0.40, no_ask=0.61, floor_strike=70),
        _mk_market("E-80", "E", "greater", 1.00, no_ask=0.00, floor_strike=80),
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_monotonicity("E", members, "greater", refusals=refusals) == []
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 1


def test_monotonicity_refuses_a_quoted_pair_whose_edge_is_exactly_zero():
    """The residue guard is NOT redundant with the fillability guard: both legs here are
    genuinely quoted (>= 1c) and the pair still nets exactly $0.00, surfacing as 1.73e-17."""
    members = [
        _mk_market("E-70", "E", "greater", 0.01, no_ask=0.99, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.03, no_ask=0.97, floor_strike=80),
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_monotonicity("E", members, "greater", refusals=refusals) == []
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 0
    assert refusals[sweep.REFUSAL_RESIDUE_EDGE] == 1


def test_monotonicity_still_flags_a_genuine_fillable_crossing_and_refuses_nothing():
    """Over-refusal check — the guard must cost no real arb (a leg with no resting offer
    cannot be bought at any price, so nothing buyable is lost)."""
    members = [
        _mk_market("E-70", "E", "greater", 0.40, no_ask=0.61, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.55, no_ask=0.45, floor_strike=80),
    ]
    refusals = sweep.new_refusal_ledger()
    hits = sweep.check_monotonicity("E", members, "greater", refusals=refusals)
    assert len(hits) == 1 and hits[0]["edge"] > 0.01
    assert refusals == sweep.new_refusal_ledger()   # every reason still at zero


def test_monotonicity_guard_is_per_pair_not_per_member():
    """A market whose NO ask is unquoted can still be the OUTER (YES) leg of a real pair;
    dropping such members wholesale would refuse arbs that do exist. Outer E-70 has no NO
    offer, inner E-80 does -> the pair is still scored."""
    members = [
        _mk_market("E-70", "E", "greater", 0.40, no_ask=0.00, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.55, no_ask=0.45, floor_strike=80),
    ]
    refusals = sweep.new_refusal_ledger()
    hits = sweep.check_monotonicity("E", members, "greater", refusals=refusals)
    assert len(hits) == 1 and hits[0]["outer_ticker"] == "E-70"
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 0


def test_bracket_arb_refuses_a_ladder_with_one_unquoted_leg():
    """L105's shape: one $0.00 member drags the bracket_sum under $1 while making the basket
    unbuyable — an underflow artifact, not an arb."""
    members = _complete_ladder([0.05, 0.30, 0.30, 0.05])
    members[1]["yes_ask_dollars"] = "0.0000"
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_bracket_arb("E", members, refusals=refusals) is None
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 1


def test_bracket_arb_still_flags_a_fully_quoted_underpriced_ladder():
    members = _complete_ladder([0.05, 0.30, 0.30, 0.05])
    refusals = sweep.new_refusal_ledger()
    hit = sweep.check_bracket_arb("E", members, refusals=refusals)
    assert hit is not None and hit["edge"] > 0.01
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 0


def test_implication_refuses_an_unquoted_leg():
    # A = FINAL (harder) with NO offer resting on its NO side; B = QUAR (easier), quoted.
    markets = [
        _mk_market("KXWCROUND-26FINAL-USA", "KXWCROUND-26FINAL", None, 1.00, no_ask=0.00),
        _mk_market("KXWCROUND-26QUAR-USA", "KXWCROUND-26QUAR", None, 0.40, no_ask=0.61),
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_cross_event_implication(markets, [_WC_FAMILY], refusals=refusals) == []
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 1


def test_every_check_works_without_a_refusal_ledger():
    """Back-compat: `refusals` is keyword-only with a default, so existing callers (and the
    repo's own probe scripts) keep working unchanged."""
    members = [
        _mk_market("E-70", "E", "greater", 0.00, no_ask=1.00, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.97, no_ask=0.03, floor_strike=80),
    ]
    assert sweep.check_monotonicity("E", members, "greater") == []
    ladder = _complete_ladder([0.05, 0.30, 0.30, 0.05])
    ladder[1]["yes_ask_dollars"] = "0.0000"
    assert sweep.check_bracket_arb("E", ladder) is None
    assert sweep.check_cross_event_implication([], [_WC_FAMILY]) == []


def test_run_persists_refusal_counts_beside_a_zero_anomaly_pass(tmp_path):
    """The honest-reporting half: `n_anomalies: 0` alone cannot distinguish 'the market was
    clean' from 'every candidate leg was unquoted'. The record now says which."""
    members = [
        _mk_market("E-70", "E", "greater", 0.00, no_ask=1.00, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.97, no_ask=0.03, floor_strike=80),
    ]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path, implication_families=[])
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().strip())
    assert rec["schema_version"] == "anomaly_sweep.v1"   # additive fields, no schema break
    assert rec["n_anomalies"] == 0
    # 2, not 1: this event group is scored by BOTH the bracket check (the $0.00 member makes
    # the whole basket unbuyable) and the monotonicity check (the pair). The ledger counts
    # refusals per CHECK, which is the honest unit — the same market can be unbuyable in two
    # different candidate trades.
    assert rec["n_unfillable_leg_refusals"] == 2
    assert rec["n_residue_edge_refusals"] == 0
    assert rec["completeness_ok"] is True                # a refusal is not a failure
    assert summary["n_unfillable_leg_refusals"] == 2


def test_run_reports_zero_refusals_on_a_clean_pass(tmp_path):
    members = [
        _mk_market("E-70", "E", "greater", 0.60, no_ask=0.41, floor_strike=70),
        _mk_market("E-80", "E", "greater", 0.30, no_ask=0.71, floor_strike=80),
    ]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path, implication_families=[])
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().strip())
    assert rec["n_anomalies"] == 0
    assert rec["n_unfillable_leg_refusals"] == 0
    assert rec["n_residue_edge_refusals"] == 0


# --------------------------------------------------------------------------- #
# L291 / Q53 — the nesting premise: a shared event_ticker is not a strike ladder
# --------------------------------------------------------------------------- #
# Titles copied verbatim from committed `tape/universe_sweep/` so a Kalshi wording change
# reds these on purpose rather than silently weakening the guard.
_NAVONE = "Will Mariano Navone win at least 2.5 more games than Jan-Lennard Struff?"
_STRUFF = "Will Jan-Lennard Struff win at least 1.5 more games than Mariano Navone?"
_NAVONE_DEEP = "Will Mariano Navone win at least 5.5 more games than Jan-Lennard Struff?"


def test_monotonicity_refuses_two_subjects_packed_into_one_event():
    """THE Q53 repair. Both legs are fillable and the crossing clears the fee floor, so every
    pre-L291 guard passes it — and it is still not an arb, because YES(Navone by >= 2.5) +
    NO(Struff by >= 1.5) pays nothing guaranteed. Refused, and counted as a CROSS-SUBJECT
    refusal rather than an unverifiable one: the scanner proved they are different subjects."""
    members = [
        _mk_market("KXATPGSPREAD-26JUL22STRNAV-STR2", "KXATPGSPREAD-26JUL22STRNAV", "greater",
                   0.40, no_ask=0.55, floor_strike=1.5, title=_STRUFF),
        _mk_market("KXATPGSPREAD-26JUL22STRNAV-NAV3", "KXATPGSPREAD-26JUL22STRNAV", "greater",
                   0.30, no_ask=0.55, floor_strike=2.5, title=_NAVONE),
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_monotonicity("KXATPGSPREAD-26JUL22STRNAV", members, "greater",
                                    refusals=refusals) == []
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 1
    assert refusals[sweep.REFUSAL_SUBJECT_UNVERIFIABLE] == 0
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 0    # both legs were real, buyable asks


def test_monotonicity_still_flags_the_genuine_ladder_inside_that_same_event():
    """The guard must not be a blanket refusal of hard events: the SAME event holds a real
    nested pair on ONE player (Navone by >= 5.5 implies Navone by >= 2.5). Anything that
    refuses this deletes a real arb, which is the other half of the error budget."""
    members = [
        _mk_market("KXATPGSPREAD-26JUL22STRNAV-NAV3", "KXATPGSPREAD-26JUL22STRNAV", "greater",
                   0.30, no_ask=0.55, floor_strike=2.5, title=_NAVONE),
        _mk_market("KXATPGSPREAD-26JUL22STRNAV-NAV6", "KXATPGSPREAD-26JUL22STRNAV", "greater",
                   0.10, no_ask=0.55, floor_strike=5.5, title=_NAVONE_DEEP),
    ]
    refusals = sweep.new_refusal_ledger()
    hits = sweep.check_monotonicity("KXATPGSPREAD-26JUL22STRNAV", members, "greater",
                                    refusals=refusals)
    assert len(hits) == 1
    assert hits[0]["outer_ticker"] == "KXATPGSPREAD-26JUL22STRNAV-NAV3"
    assert hits[0]["subject_identity_reason"] == "numeric_difference_is_strike_attributable"
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 0


def test_monotonicity_subject_guard_is_per_pair_not_per_event():
    """A three-market event holding one player's two rungs plus a second player: exactly one
    pair survives, two are refused. A per-EVENT guard would throw away the real pair too."""
    et = "KXATPGSPREAD-26JUL22STRNAV"
    members = [
        _mk_market(et + "-STR2", et, "greater", 0.40, no_ask=0.55,
                   floor_strike=1.5, title=_STRUFF),
        _mk_market(et + "-NAV3", et, "greater", 0.30, no_ask=0.55,
                   floor_strike=2.5, title=_NAVONE),
        _mk_market(et + "-NAV6", et, "greater", 0.10, no_ask=0.55,
                   floor_strike=5.5, title=_NAVONE_DEEP),
    ]
    refusals = sweep.new_refusal_ledger()
    hits = sweep.check_monotonicity(et, members, "greater", refusals=refusals)
    assert len(hits) == 1
    assert (hits[0]["outer_ticker"], hits[0]["inner_ticker"]) == (et + "-NAV3", et + "-NAV6")
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 2


def test_monotonicity_refuses_an_untitled_pair_as_UNVERIFIABLE_not_as_an_arb():
    """A market that publishes no descriptive text cannot prove its own nesting. Refused,
    and counted in the ignorance bucket — never silently promoted to a flagged arb."""
    members = [
        {"ticker": "E-70", "event_ticker": "E", "strike_type": "greater", "floor_strike": 70,
         "cap_strike": None, "yes_ask_dollars": "0.4000", "no_ask_dollars": "0.6100"},
        {"ticker": "E-80", "event_ticker": "E", "strike_type": "greater", "floor_strike": 80,
         "cap_strike": None, "yes_ask_dollars": "0.5500", "no_ask_dollars": "0.4500"},
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_monotonicity("E", members, "greater", refusals=refusals) == []
    assert refusals[sweep.REFUSAL_SUBJECT_UNVERIFIABLE] == 1
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 0


def test_bracket_arb_refuses_a_ladder_assembled_from_two_subjects():
    """Check 1's half of the same premise: a partition that bookends the real line and prices
    under $1 is still not a guaranteed $1 payout if its rungs describe two different cities."""
    members = _complete_ladder([0.05, 0.30, 0.30, 0.05])
    members[2]["title"] = "What will the value in Denver be above 60?"
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_bracket_arb("E", members, refusals=refusals) is None
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 1


def test_bracket_arb_admits_a_real_ladder_whose_rung_labels_move_with_the_strike():
    """And must NOT refuse the ordinary case, where every rung's label is its own strike."""
    refusals = sweep.new_refusal_ledger()
    hit = sweep.check_bracket_arb("E", _complete_ladder([0.05, 0.30, 0.30, 0.05]),
                                  refusals=refusals)
    assert hit is not None and hit["edge"] > 0.01
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 0
    assert refusals[sweep.REFUSAL_SUBJECT_UNVERIFIABLE] == 0


def test_subject_guard_runs_after_fillability_so_the_funnel_matches_the_replay():
    """Ordering is deliberate (see check_monotonicity's docstring): a pair that is BOTH
    unbuyable and cross-subject is counted once, as unbuyable. That keeps the live ledger's
    funnel identical to the committed-tape replay's (43,038 -> 43,025 -> 13 -> 0) instead of
    two decompositions of the same population that never reconcile."""
    et = "KXATPGSPREAD-26JUL22STRNAV"
    members = [
        _mk_market(et + "-STR2", et, "greater", 0.00, no_ask=1.00,
                   floor_strike=1.5, title=_STRUFF),
        _mk_market(et + "-NAV3", et, "greater", 0.30, no_ask=0.55,
                   floor_strike=2.5, title=_NAVONE),
    ]
    refusals = sweep.new_refusal_ledger()
    assert sweep.check_monotonicity(et, members, "greater", refusals=refusals) == []
    assert refusals[sweep.REFUSAL_UNFILLABLE_LEG] == 1
    assert refusals[sweep.REFUSAL_CROSS_SUBJECT_PAIR] == 0


def test_run_persists_the_two_subject_refusal_counters(tmp_path):
    et = "KXATPGSPREAD-26JUL22STRNAV"
    members = [
        _mk_market(et + "-STR2", et, "greater", 0.40, no_ask=0.55,
                   floor_strike=1.5, title=_STRUFF),
        _mk_market(et + "-NAV3", et, "greater", 0.30, no_ask=0.55,
                   floor_strike=2.5, title=_NAVONE),
    ]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path, implication_families=[])
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().strip())
    assert rec["schema_version"] == "anomaly_sweep.v1"      # additive, no schema break
    assert rec["n_anomalies"] == 0
    assert rec["n_cross_subject_pair_refusals"] == 1
    assert rec["n_subject_unverifiable_refusals"] == 0
    assert rec["completeness_ok"] is True                   # a refusal is not a failure
    assert summary["n_cross_subject_pair_refusals"] == 1
    assert summary["n_subject_unverifiable_refusals"] == 0
    # every pre-existing field still present and unchanged in meaning
    for field in ("n_markets_scanned", "n_event_groups", "n_bracket_groups_checked",
                  "n_monotonicity_groups_checked", "n_implication_pairs_checked",
                  "n_unfillable_leg_refusals", "n_residue_edge_refusals", "anomalies",
                  "fetch_error", "markets_truncated", "completeness_ok", "raw_sha256"):
        assert field in rec


def test_scanned_tickers_digest_dedupes_and_ignores_order():
    a = [_mk_market("X-1", "E", "greater", 0.5, floor_strike=1),
         _mk_market("X-2", "E", "greater", 0.5, floor_strike=2)]
    b = list(reversed(a)) + [_mk_market("X-1", "E", "greater", 0.5, floor_strike=1)]  # dup
    n_a, digest_a = sweep.scanned_tickers_digest(a)
    n_b, digest_b = sweep.scanned_tickers_digest(b)
    assert n_a == n_b == 2
    assert digest_a == digest_b


def test_scanned_tickers_digest_changes_with_the_population():
    a = [_mk_market("X-1", "E", "greater", 0.5, floor_strike=1)]
    b = [_mk_market("X-2", "E", "greater", 0.5, floor_strike=1)]
    _, digest_a = sweep.scanned_tickers_digest(a)
    _, digest_b = sweep.scanned_tickers_digest(b)
    assert digest_a != digest_b


def test_scanned_tickers_digest_of_empty_pass_is_deterministic():
    n, digest = sweep.scanned_tickers_digest([])
    assert n == 0
    assert digest == sweep.scanned_tickers_digest([])[1]


def test_run_persists_the_scanned_tickers_coverage_digest(tmp_path):
    members = [_mk_market("A-1", "A", "greater", 0.5, no_ask=0.5, floor_strike=10),
               _mk_market("A-2", "A", "greater", 0.3, no_ask=0.7, floor_strike=20)]
    client = FakeClient(pages=[members])
    summary = sweep.run(client=client, tape_dir=tmp_path)
    expect_n, expect_digest = sweep.scanned_tickers_digest(members)
    assert summary["n_distinct_tickers_scanned"] == expect_n == 2
    assert summary["scanned_tickers_sha256"] == expect_digest
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["n_distinct_tickers_scanned"] == expect_n
    assert rec["scanned_tickers_sha256"] == expect_digest
    # pre-existing fields untouched by the addition
    assert rec["n_markets_scanned"] == 2


def test_run_two_passes_over_the_same_population_share_a_digest(tmp_path):
    """The honest denominator finding this milestone unblocks: if a capped pass keeps
    re-scanning the SAME population pass after pass, the digest says so directly instead of
    requiring a future analyst to assume it from equal `n_markets_scanned` counts alone —
    and a differently-populated pass (next test) proves the digest actually discriminates."""
    members = [_mk_market("A-1", "A", "greater", 0.5, no_ask=0.5, floor_strike=10),
               _mk_market("A-2", "A", "greater", 0.3, no_ask=0.7, floor_strike=20)]
    s1 = sweep.run(client=FakeClient(pages=[members]), tape_dir=tmp_path)
    s2 = sweep.run(client=FakeClient(pages=[members]), tape_dir=tmp_path)
    assert s1["scanned_tickers_sha256"] == s2["scanned_tickers_sha256"]


def test_run_digest_differs_when_the_scanned_population_differs(tmp_path):
    m1 = [_mk_market("A-1", "A", "greater", 0.5, no_ask=0.5, floor_strike=10)]
    m2 = [_mk_market("A-2", "A", "greater", 0.5, no_ask=0.5, floor_strike=10)]
    s1 = sweep.run(client=FakeClient(pages=[m1]), tape_dir=tmp_path)
    s2 = sweep.run(client=FakeClient(pages=[m2]), tape_dir=tmp_path)
    assert s1["scanned_tickers_sha256"] != s2["scanned_tickers_sha256"]


def test_new_refusal_ledger_carries_all_four_reasons():
    assert sweep.new_refusal_ledger() == {
        sweep.REFUSAL_UNFILLABLE_LEG: 0, sweep.REFUSAL_RESIDUE_EDGE: 0,
        sweep.REFUSAL_CROSS_SUBJECT_PAIR: 0, sweep.REFUSAL_SUBJECT_UNVERIFIABLE: 0,
    }


def test_checks_still_work_without_a_refusal_ledger():
    """Back-compat: `refusals` stays optional, so an external caller that predates the ledger
    keeps working (it just cannot see why nothing was flagged)."""
    et = "KXATPGSPREAD-26JUL22STRNAV"
    members = [
        _mk_market(et + "-STR2", et, "greater", 0.40, no_ask=0.55,
                   floor_strike=1.5, title=_STRUFF),
        _mk_market(et + "-NAV3", et, "greater", 0.30, no_ask=0.55,
                   floor_strike=2.5, title=_NAVONE),
    ]
    assert sweep.check_monotonicity(et, members, "greater") == []


# --------------------------------------------------------------------------- #
# acceptance — replay of ALL committed `tape/anomalies/` through the new guards
#
# HARD assertions over a CLOSED window (ACCEPTANCE_MAX_DAY), which is what makes them
# pinnable: without the cap, tomorrow's collector pass moves today's headline (L191). The
# window matches tests/test_econ_prints_ladder_fillability_audit.py::MAX_DAY so the two
# files' numbers are directly comparable. These replay COMMITTED records — tape is
# append-only and is never rewritten by this run.
# --------------------------------------------------------------------------- #
ACCEPTANCE_MAX_DAY = "2026-08-04"
_ANOMALIES_DIR = REPO_ROOT / "tape" / "anomalies"


def _replay_committed_monotonicity_anomalies():
    """Every committed `cross_strike_monotonicity` record, re-scored by today's guards, in
    the SAME funnel order the live scanner uses: fillability -> edge materiality -> subject
    identity. `survivors` is the population after the two PRICE guards (L290's published 13);
    `final_survivors` is what is left after the L291 nesting guard (Q53)."""
    total = n_unfillable = n_residue = n_recompute_disagreements = 0
    n_subject_cross = n_subject_unverifiable = 0
    survivors = []
    final_survivors = []
    for path in sorted(_ANOMALIES_DIR.glob("dt=*.jsonl")):
        if path.name[len("dt="):-len(".jsonl")] > ACCEPTANCE_MAX_DAY:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            for an in json.loads(line).get("anomalies") or []:
                if an.get("kind") != "cross_strike_monotonicity":
                    continue
                total += 1
                outer, inner = float(an["outer_ask"]), float(an["inner_no_ask"])
                persisted = float(an["edge"])
                if abs(monotonicity_crossing_edge(outer, inner) - persisted) > 1e-12:
                    n_recompute_disagreements += 1
                if not (is_fillable_ask(outer) and is_fillable_ask(inner)):
                    n_unfillable += 1
                    continue
                if not is_material_arb_edge(persisted):
                    n_residue += 1
                    continue
                survivors.append((an["outer_ticker"], an["inner_ticker"], outer, inner))
                # The persisted record carries ONLY tickers — no title, no strike bounds —
                # because the scanner did not record why it believed the pair was nested.
                # Replaying it therefore cannot prove subject identity, and the honest
                # verdict is UNVERIFIABLE, not a retroactive guess either way.
                verdict, _ = same_subject({"ticker": an["outer_ticker"]},
                                          {"ticker": an["inner_ticker"]})
                if verdict == SUBJECT_UNVERIFIABLE:
                    n_subject_unverifiable += 1
                elif verdict != SUBJECT_PROVEN_SAME:
                    n_subject_cross += 1
                else:
                    final_survivors.append(
                        (an["outer_ticker"], an["inner_ticker"], outer, inner))
    return {"total": total, "n_unfillable": n_unfillable, "n_residue": n_residue,
            "n_recompute_disagreements": n_recompute_disagreements, "survivors": survivors,
            "n_subject_cross_subject": n_subject_cross,
            "n_subject_unverifiable": n_subject_unverifiable,
            "final_survivors": final_survivors}


@pytest.fixture(scope="module")
def replay():
    if not _ANOMALIES_DIR.exists():
        pytest.skip("committed anomalies tape not present")
    return _replay_committed_monotonicity_anomalies()


def test_acceptance_the_persisted_edge_is_reproducible(replay):
    """Precondition for everything below: the tape's own `edge` field recomputes exactly
    from its own two persisted legs, so the replay is scoring real recorded prices."""
    assert replay["total"] == 43038
    assert replay["n_recompute_disagreements"] == 0


def test_acceptance_the_guard_refuses_9997_percent_of_recorded_history(replay):
    """L288's headline, now enforced rather than described: 43,025 of 43,038 recorded
    anomalies price a leg that does not exist. Nothing buyable is lost — a $0.00 ask is the
    absence of an offer, so no real arb is among the refused."""
    assert replay["n_unfillable"] == 43025
    assert round(replay["n_unfillable"] / replay["total"], 6) == 0.999698


def test_acceptance_the_residue_guard_adds_nothing_on_this_tape_but_is_not_redundant(replay):
    """All 1,480 exactly-$0.00 float-residue rows (L288's second defect) also carry a $0.00
    leg, so on THIS tape the fillability guard subsumes them and the residue counter reads 0
    after it. The residue guard still matters going forward — 87 fully-quoted cent-grid pairs
    net exactly $0.00 (see tests/test_pricing_fillable_ask.py)."""
    assert replay["n_residue"] == 0


def test_acceptance_only_thirteen_records_survive_both_guards(replay):
    assert len(replay["survivors"]) == 13
    assert len({s[:2] for s in replay["survivors"]}) == 6    # distinct ticker pairs
    assert len(set(replay["survivors"])) == 7                # distinct (pair, price) rows


def test_acceptance_no_survivor_remains_once_the_nesting_premise_is_ENFORCED(replay):
    """Q53's regression target, now at ZERO. Before this commit, 13 records / 6 ticker pairs
    survived both price guards, and 100% of them paired two DIFFERENT SUBJECTS under one
    `event_ticker` (L291): two tennis players' game spreads, three batters' props, three
    cities' rain markets. `check_monotonicity` sorted them by floor/cap strike as if they
    were rungs of one ladder, so buying YES(subject A) + NO(subject B) was recorded as a
    guaranteed >= $1 payout when it is a naked directional bet.

    Read the mechanism honestly, because it is not "the guard proved these 6 pairs are
    cross-subject": a committed anomaly record persists only `outer_ticker`/`inner_ticker`,
    with no title and no strike bounds, so the replay CANNOT prove or disprove subject
    identity from the tape. All 13 are therefore refused as UNVERIFIABLE — absence of
    evidence, recorded as such. That is the correct verdict for a record that never wrote
    down why it believed its own premise, and it is why every anomaly flagged from now on
    carries a `subject_identity_reason` field. The proof that the guard genuinely SEPARATES
    these classes is fixture-side (`test_monotonicity_refuses_two_subjects_packed_into_one_event`
    admits the real within-player ladder in the same event) and corpus-side
    (`tests/test_subject_identity.py`: 0 false admits over 2,364 labeled cross-subject pairs,
    0 false refusals over 34,334 genuine-ladder pairs).
    """
    assert replay["final_survivors"] == []
    assert replay["n_subject_unverifiable"] == 13
    assert replay["n_subject_cross_subject"] == 0     # unprovable from tickers alone, not 0-by-luck
    assert (replay["n_subject_unverifiable"] + replay["n_subject_cross_subject"]
            + len(replay["final_survivors"])) == len(replay["survivors"])


def test_acceptance_the_pre_repair_survivor_population_is_still_six_cross_subject_pairs(replay):
    """The historical population L291 measured, kept as a named record of WHAT the premise
    failure looked like. These six pairs are the reason `core/subject_identity.py` exists;
    the test above is the reason they no longer reach the tape."""
    pairs = sorted({s[:2] for s in replay["survivors"]})
    assert pairs == sorted([
        # two different tennis players' game-spread markets in one event
        ("KXATPGSPREAD-26JUL17COLVAC-VAC2", "KXATPGSPREAD-26JUL17COLVAC-COL2"),
        # three different batters' prop markets in one MLB event
        ("KXMLBHIT-26JUL181610SDKC-KCVPASQUANTINO9-2",
         "KXMLBHIT-26JUL181610SDKC-KCBWITT7-2"),
        ("KXMLBHRR-26JUL181610SDKC-KCVPASQUANTINO9-3",
         "KXMLBHRR-26JUL181610SDKC-KCBWITT7-3"),
        ("KXMLBTB-26JUL181610SDKC-KCVPASQUANTINO9-2",
         "KXMLBTB-26JUL181610SDKC-KCBWITT7-2"),
        # three different CITIES' rain markets in one weather event
        ("KXRAIN-26JUL23-NYC", "KXRAIN-26JUL23-NOLA"),
        ("KXRAIN-26JUL23-NYC", "KXRAIN-26JUL23-DEN"),
    ])
    for outer, inner in pairs:
        assert outer != inner


def test_acceptance_the_scanner_has_never_recorded_a_verified_fillable_arb(replay):
    """The honest summary for S3, DESCRIPTIVE and deliberately NOT a registry flip (a kill
    needs the two-agent rule): 43,038 recorded anomalies over 26 committed capture-days ->
    43,025 unbuyable legs -> 13 cross-subject false positives -> ZERO verified fillable
    arbs."""
    assert replay["total"] == 43038
    assert replay["n_unfillable"] == 43025
    assert len(replay["survivors"]) == 13
    assert replay["final_survivors"] == []    # nothing survives all three guards

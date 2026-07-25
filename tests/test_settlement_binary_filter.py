"""core/settlement.py — binary-settlement classification (L52: "settled" != "yes/no").

L52: Q26's live pull of `fetch_kalshi_settled` over 458 settled markets in 7 sports series
returned 8 with `result: "scalar"`. Everything here defends the one property that matters —
a non-binary result must be EXCLUDED, never silently scored as a `no`.
"""
from __future__ import annotations

import glob
import json
import os

import pytest

from core.settlement import (BINARY_RESULTS, KNOWN_NON_BINARY_RESULTS, MISSING_SENTINEL,
                             VALID_BINARY_RESULTS, BinaryFilterReport, binary_outcome,
                             filter_binary_results_map, filter_binary_settlements,
                             is_binary_result, normalize_result, require_binary_result)

_TAPE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "tape", "settlement_ledger")


# ─── constants ──────────────────────────────────────────────────────────────

def test_constants_are_an_allowlist_not_a_denylist():
    assert BINARY_RESULTS == ("yes", "no")
    assert VALID_BINARY_RESULTS == frozenset({"yes", "no"})
    # KNOWN_NON_BINARY_RESULTS is documentation only; it must not be the thing that decides.
    assert "scalar" in KNOWN_NON_BINARY_RESULTS
    assert not (KNOWN_NON_BINARY_RESULTS & VALID_BINARY_RESULTS)


def test_unknown_future_result_value_is_non_binary_by_default():
    # The allow-list property: a value Kalshi has not shipped yet must NOT pass.
    assert is_binary_result("range") is False
    assert binary_outcome("range") is None


# ─── normalize_result ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("yes", "yes"), ("no", "no"), ("YES", "yes"), (" yes ", "yes"), ("No", "no"),
    ("scalar", "scalar"), ("void", "void"),
    ("", None), ("   ", None), (None, None), (0, None), (1, None), (True, None),
    ({}, None), ({"result": "yes"}, None), ([], None), (["yes"], None),
])
def test_normalize_result(raw, expected):
    assert normalize_result(raw) == expected


# ─── is_binary_result ───────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("yes", True), ("no", True), ("YES", True), (" yes ", True),
    ("scalar", False), ("void", False), ("", False), (None, False),
    (0, False), (1, False), ({}, False), ([], False),
])
def test_is_binary_result(raw, expected):
    assert is_binary_result(raw) is expected


# ─── binary_outcome ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("yes", 1), ("YES", 1), (" yes ", 1), ("no", 0), ("No", 0),
    ("scalar", None), ("void", None), ("", None), (None, None),
    (0, None), (1, None), ({}, None), ([], None),
])
def test_binary_outcome(raw, expected):
    assert binary_outcome(raw) == expected


def test_binary_outcome_scalar_is_none_not_zero():
    """THE anti-fabrication case (L52).

    A naive `1 if result == "yes" else 0` scores a scalar-settled market as a LOSS. It is
    not a loss — it is not a yes/no market at all. None forces the caller to decide.
    """
    assert binary_outcome("scalar") is None
    assert binary_outcome("scalar") != 0
    # int 1 is likewise not a "yes": no numeric coercion sneaks the assumption back in.
    assert binary_outcome(1) is None


# ─── require_binary_result ──────────────────────────────────────────────────

def test_require_binary_result_returns_normalized():
    assert require_binary_result("yes") == "yes"
    assert require_binary_result(" NO ") == "no"


def test_require_binary_result_raises_on_scalar_naming_raw_value():
    with pytest.raises(ValueError) as exc:
        require_binary_result("scalar", context="q26 hit-rate join")
    msg = str(exc.value)
    assert "'scalar'" in msg
    assert "q26 hit-rate join" in msg


def test_require_binary_result_raises_on_none_and_on_unknown():
    with pytest.raises(ValueError) as exc:
        require_binary_result(None)
    assert "None" in str(exc.value)
    with pytest.raises(ValueError):
        require_binary_result("range")


# ─── filter_binary_settlements ──────────────────────────────────────────────

def _rows():
    return [
        {"ticker": "A", "result": "yes"},
        {"ticker": "B", "result": "no"},
        {"ticker": "C", "result": "scalar"},
        {"ticker": "D", "result": "SCALAR"},   # raw value reported verbatim, still dropped
        {"ticker": "E", "result": None},
        {"ticker": "F"},                        # key absent entirely
        {"ticker": "G", "result": " Yes "},     # normalizes into binary -> kept
    ]


def test_filter_binary_settlements_keeps_only_binary_rows():
    kept, rep = filter_binary_settlements(_rows())
    assert [r["ticker"] for r in kept] == ["A", "B", "G"]
    assert isinstance(rep, BinaryFilterReport)
    assert rep.total == 7
    assert rep.kept == 3
    assert rep.dropped == 4
    assert rep.total == rep.kept + rep.dropped
    assert rep.kept_fraction == pytest.approx(3 / 7)


def test_filter_binary_settlements_counts_dropped_by_raw_value():
    _, rep = filter_binary_settlements(_rows())
    assert rep.dropped_by_result == {"scalar": 1, "SCALAR": 1, MISSING_SENTINEL: 2}


def test_filter_binary_settlements_labels_non_str_results():
    _, rep = filter_binary_settlements([{"result": 1}, {"result": []}, {"result": {}}])
    assert rep.dropped_by_result == {"<non-str:int>": 1, "<non-str:list>": 1,
                                     "<non-str:dict>": 1}


def test_filter_binary_settlements_custom_result_key():
    kept, rep = filter_binary_settlements(
        [{"settlement_result": "yes"}, {"settlement_result": "scalar"}],
        result_key="settlement_result")
    assert len(kept) == 1 and rep.dropped == 1


def test_filter_binary_settlements_empty_input_is_not_a_crash():
    kept, rep = filter_binary_settlements([])
    assert kept == []
    assert (rep.total, rep.kept, rep.dropped) == (0, 0, 0)
    assert rep.kept_fraction == 0.0     # 0/0 -> 0.0, never ZeroDivisionError
    assert rep.dropped_by_result == {}


def test_filter_binary_settlements_returns_rows_unmodified():
    row = {"ticker": "A", "result": "YES", "extra": 7}
    kept, _ = filter_binary_settlements([row])
    assert kept[0] is row and kept[0]["result"] == "YES"


def test_report_is_frozen():
    rep = BinaryFilterReport(total=1, kept=1, dropped=0)
    with pytest.raises(Exception):
        rep.total = 2  # type: ignore[misc]


def test_report_summary_mentions_counts():
    _, rep = filter_binary_settlements(_rows())
    s = rep.summary()
    assert "total 7" in s and "kept 3" in s and "scalar=1" in s


# ─── filter_binary_results_map ──────────────────────────────────────────────

def test_filter_binary_results_map_drops_scalar_member_of_a_mece_ladder():
    ladder = {"KX-T1": "no", "KX-T2": "YES", "KX-T3": "scalar", "KX-T4": "no"}
    kept, rep = filter_binary_results_map(ladder)
    assert kept == {"KX-T1": "no", "KX-T2": "yes", "KX-T4": "no"}   # normalized
    assert rep.total == 4 and rep.kept == 3 and rep.dropped == 1
    assert rep.dropped_by_result == {"scalar": 1}
    assert rep.kept_fraction == pytest.approx(0.75)


def test_filter_binary_results_map_empty():
    kept, rep = filter_binary_results_map({})
    assert kept == {} and rep.total == 0 and rep.kept_fraction == 0.0


def test_filter_binary_results_map_none_and_non_str_values():
    kept, rep = filter_binary_results_map({"A": None, "B": 1, "C": "yes"})
    assert kept == {"C": "yes"}
    assert rep.dropped_by_result == {MISSING_SENTINEL: 1, "<non-str:int>": 1}


# ─── the L52 bug shape, reproduced ──────────────────────────────────────────

def test_regression_l52_unfiltered_hit_rate_differs_from_filtered():
    """L52's silent-injection bug, shown numerically.

    Four settled markets: 2 yes, 1 no, 1 scalar. The unfiltered `== "yes"` hit-rate scores
    the scalar row as a miss and reports 2/4 = 0.50. The filtered hit-rate correctly uses a
    denominator of 3 binary rows and reports 2/3 = 0.667. The unfiltered number is not
    merely imprecise, it is biased DOWNWARD by construction — every non-binary row lands in
    the loss bucket.
    """
    rows = [
        {"ticker": "A", "result": "yes"},
        {"ticker": "B", "result": "yes"},
        {"ticker": "C", "result": "no"},
        {"ticker": "D", "result": "scalar"},
    ]

    unfiltered = sum(1 for r in rows if r["result"] == "yes") / len(rows)

    kept, rep = filter_binary_settlements(rows)
    filtered = sum(binary_outcome(r["result"]) for r in kept) / len(kept)

    assert unfiltered == pytest.approx(0.50)
    assert filtered == pytest.approx(2 / 3)
    assert unfiltered != pytest.approx(filtered)
    # ...and the report tells the caller exactly why the denominators differ.
    assert rep.total == 4 and rep.kept == 3 and rep.dropped_by_result == {"scalar": 1}


# ─── acceptance: the REAL committed tape ────────────────────────────────────

def test_acceptance_1_l52_real_settlement_ledger_tape_is_all_binary():
    """Anchored to the real committed `tape/settlement_ledger/`, not a fixture.

    Measured 2026-07-25 with::

        python - <<'EOF'
        import json, glob, collections
        c = collections.Counter(); n = 0
        for f in sorted(glob.glob('tape/settlement_ledger/*.jsonl')):
            for line in open(f):
                line = line.strip()
                if not line: continue
                n += 1; c[json.loads(line).get('result')] += 1
        print(n, dict(c))
        EOF

    -> ``10605 {'no': 8235, 'yes': 2370}`` across 2 files.

    kept_fraction is 1.0 **because `collection/settlement_ledger.py` already drops
    `result == "scalar"` (and any other non-binary label) at collection time** — run() at
    ~L250/L256 and migrate_caches() at ~L381/L385. This test therefore asserts that the
    UPSTREAM pre-filter still holds: if the collector ever stopped filtering, scalar rows
    would reach this tape and this test would go red with the exact count in
    `dropped_by_result`. It is not asserting that Kalshi has no scalars — L52's upstream
    rate is 8 of 458.
    """
    if not os.path.isdir(_TAPE_DIR):
        pytest.skip("tape/settlement_ledger/ absent (bare checkout)")
    paths = sorted(glob.glob(os.path.join(_TAPE_DIR, "*.jsonl")))
    if not paths:
        pytest.skip("tape/settlement_ledger/ has no jsonl files")

    rows = []
    for p in paths:
        with open(p, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))

    kept, rep = filter_binary_settlements(rows)

    assert rep.total > 0, "real tape should not be empty"
    assert rep.kept + rep.dropped == rep.total
    assert len(kept) == rep.kept
    assert all(is_binary_result(r["result"]) for r in kept)
    assert all(binary_outcome(r["result"]) in (0, 1) for r in kept)
    assert rep.kept_fraction == 1.0, rep.summary()
    assert rep.dropped_by_result == {}, rep.summary()

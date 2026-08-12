"""L321 — the minority-side exclusivity audit over Q54/S79's sealed population.

The audit is a MEASUREMENT: it re-derives the sealed probe's population through the probe's
own outcome-blind path and reports both the TOUCHING and the EXCLUSIVE minority-unit counts.
It repairs nothing (the probe is sealed, L311) and produces no CI, P&L or verdict.

Real-tape assertions here are GROWTH-SAFE (L320): `tape/kalshi_trades/` is append-only and
still backfilling, and this population has already moved 24 -> 45 units since 2026-08-09, so
they are floors and structural relations, never frozen equalities.
"""
from __future__ import annotations

import json

import pytest

from scripts import q54_minority_exclusivity_audit as A
from scripts import q54_s79_flow_continuation_probe as P


@pytest.fixture(scope="module")
def report():
    return A.build_report()


# ─── structural: the audit cannot read an outcome ───────────────────────────

def test_outcome_paths_are_sealed_inside_the_context_and_restored_after():
    original = (P.outcome_map, P.score_rows)
    with A.sealed_outcome_paths(P):
        with pytest.raises(A.OutcomeReadForbidden):
            P.outcome_map(["KXMLBGAME-26AUG032005LADCHC"])
        with pytest.raises(A.OutcomeReadForbidden):
            P.score_rows([], {})
    assert (P.outcome_map, P.score_rows) == original


def test_the_seal_is_restored_even_when_the_body_raises():
    original = (P.outcome_map, P.score_rows)
    with pytest.raises(ValueError):
        with A.sealed_outcome_paths(P):
            raise ValueError("boom")
    assert (P.outcome_map, P.score_rows) == original


def test_report_carries_no_outcome_or_pnl_field(report):
    """Key-level, not a substring scan of the blob — the probe's own L311 discipline."""
    forbidden = ("pnl", "won", "profit", "ci95", "outcome", "settle_result")
    keys = set()

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                keys.add(str(k).lower())
                walk(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                walk(v)

    walk(report)
    # `outcome_paths_sealed` is the ONE allowed key carrying the token: it is a boolean
    # META flag asserting the seal, never an outcome VALUE. Named explicitly so the
    # exemption is visible rather than hidden in a looser matcher (L155).
    offenders = [k for k in keys for tok in forbidden if tok in k]
    assert offenders == ["outcome_paths_sealed"]
    assert report["outcome_paths_sealed"] is True


def test_audit_makes_no_network_calls(report):
    assert report["network_calls"] == 0
    assert report["outcome_paths_sealed"] is True
    assert report["price_source_tag"] == "broker_truth"


def test_audit_does_not_edit_or_reseal_the_probe(report):
    # The audit must observe the sealed spec, never restate it: the digest it reports has to
    # be the probe's own live value, so an edit to the probe reds this and the probe's pin.
    assert report["probe_preregistration_sha256"] == P.PREREG_SHA256
    assert report["probe"] == "scripts/q54_s79_flow_continuation_probe.py"


# ─── the unit_sides reduction ───────────────────────────────────────────────

def test_unit_sides_keeps_only_scoreable_entries_and_preserves_every_label():
    rows = [
        {"ticker": "A", "unit": "g1", "side": "yes"},
        {"ticker": "A", "unit": "g1", "side": "no"},
        {"ticker": "B", "unit": "g2", "side": "yes"},
        {"ticker": "C", "unit": "g3", "side": "no"},      # unsettled -> excluded
    ]
    out = A.unit_sides(rows, frozenset({"A", "B"}))
    assert out == {"g1": ["yes", "no"], "g2": ["yes"]}


def test_unit_sides_on_an_empty_settled_set_is_empty_not_a_crash():
    assert A.unit_sides([{"ticker": "A", "unit": "g1", "side": "yes"}], frozenset()) == {}


# ─── real-tape acceptance (growth-safe: floors and relations, L320) ─────────

def test_acceptance_touching_count_reproduces_the_sealed_probes_own_number(report):
    """If the audit's population disagreed with the probe's, it would be auditing a
    different gate (L280 — measure the join from both sides)."""
    assert report["reproduces_probe_units_per_side"] is True
    assert (report["census"]["units_per_side"]
            == report["probe_sign_variation"]["units_per_side"])


def test_acceptance_exclusive_count_never_exceeds_the_touching_count(report):
    c = report["census"]
    for side, n_excl in c["exclusive_units_per_side"].items():
        assert n_excl <= c["units_per_side"][side]
    assert (sum(c["exclusive_units_per_side"].values()) + c["n_mixed_units"]
            == c["n_units"])


def test_acceptance_l321_the_defect_is_live_on_todays_tape(report):
    """The recorded finding: the gate as coded is OPEN while zero units are exclusively
    minority-side. Stated as a floor on the population (>= 24 units, the 2026-08-09 size)
    so tape growth cannot silently void the pin, and as an equality only on the count the
    lesson is about."""
    assert report["n_units"] >= 24
    assert report["min_minority_side_units"] == 2
    assert report["census"]["minority_side"] == "no"
    assert report["census"]["minority_side_units_touching"] >= 2
    assert report["census"]["minority_side_units_exclusive"] == 0
    assert report["gate_touching_ok"] is True                      # the sealed probe's gate
    assert report["gate_exclusive"]["admissible"] is False         # L321's rule
    assert report["gate_exclusive"]["reasons"] == [
        "below_min_exclusive_minority_units"]


def test_acceptance_every_minority_unit_is_a_mixed_unit(report):
    """The mechanism, not just the count: all minority-touching units also carry majority
    entries, so no block-bootstrap resample can be minority-only."""
    c = report["census"]
    assert c["n_mixed_units"] >= c["minority_side_units_touching"]
    assert c["minority_side_units_exclusive"] == 0


# ─── CLI ────────────────────────────────────────────────────────────────────

def test_cli_writes_json_only_when_asked(tmp_path, capsys):
    out = tmp_path / "sub" / "l321.json"
    assert A.main(["--json", str(out)]) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["schema_version"] == A.SCHEMA_VERSION
    assert payload["lesson"] == "L321"
    captured = capsys.readouterr().out
    assert "minority side" in captured


def test_cli_writes_nothing_by_default(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert A.main([]) == 0
    assert list(tmp_path.iterdir()) == []

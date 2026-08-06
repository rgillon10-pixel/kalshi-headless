"""core.detector_evidence — L296's reading rule, made mechanical.

Every fixture below is written to prove the predicate FIRES on the thing it exists to catch
(L191: a detector that never fires isn't proven). The load-bearing case is
`test_a_zero_over_an_empty_denominator_is_not_evidence_of_absence`: that is the exact record
shape S15 produced 243 times while its registry row was read as "0 hits".
"""
from __future__ import annotations

import pytest

from core.detector_evidence import (ALL_EVIDENCE_CLASSES, EVIDENCE_COUNTER_ABSENT,
                                    EVIDENCE_EMPTY_DENOMINATOR, EVIDENCE_HITS,
                                    EVIDENCE_INCOHERENT, EVIDENCE_INFORMATIVE_ZERO,
                                    classify_detector_evidence, classify_record_evidence,
                                    evidence_block, summarize_evidence, zero_is_informative)


# --------------------------------------------------------------------------- #
# the four classes
# --------------------------------------------------------------------------- #
def test_a_zero_over_an_empty_denominator_is_not_evidence_of_absence():
    """L296's exact failure: 0 hits because 0 candidates were ever checked."""
    assert classify_detector_evidence(0, 0) == EVIDENCE_EMPTY_DENOMINATOR
    assert zero_is_informative(EVIDENCE_EMPTY_DENOMINATOR) is False


def test_a_zero_over_a_real_denominator_is_the_only_readable_zero():
    assert classify_detector_evidence(38, 0) == EVIDENCE_INFORMATIVE_ZERO
    assert zero_is_informative(EVIDENCE_INFORMATIVE_ZERO) is True


def test_one_candidate_is_enough_to_make_a_zero_readable():
    """The boundary the whole rule turns on: 1 checked, not 0."""
    assert classify_detector_evidence(1, 0) == EVIDENCE_INFORMATIVE_ZERO


def test_hits_are_not_a_zero_and_are_not_readable_as_absence():
    assert classify_detector_evidence(38, 2) == EVIDENCE_HITS
    assert zero_is_informative(EVIDENCE_HITS) is False


def test_hits_over_an_empty_denominator_are_incoherent_not_silently_absorbed():
    """A record claiming hits it never had candidates for contradicts itself. It must not be
    roundable to either neighbouring class."""
    klass = classify_detector_evidence(0, 1)
    assert klass == EVIDENCE_INCOHERENT
    assert klass not in (EVIDENCE_EMPTY_DENOMINATOR, EVIDENCE_INFORMATIVE_ZERO, EVIDENCE_HITS)
    assert zero_is_informative(klass) is False


def test_unknown_class_names_refuse_by_default():
    assert zero_is_informative("probably_fine") is False
    assert zero_is_informative("") is False


def test_every_returned_class_is_a_declared_class():
    for checked, hits in ((0, 0), (0, 3), (1, 0), (5, 5)):
        assert classify_detector_evidence(checked, hits) in ALL_EVIDENCE_CLASSES


# --------------------------------------------------------------------------- #
# malformed INPUT raises — a different class from an incoherent CLAIM
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("checked,hits", [(-1, 0), (0, -1), (-3, -2)])
def test_negative_counts_raise(checked, hits):
    with pytest.raises(ValueError):
        classify_detector_evidence(checked, hits)


@pytest.mark.parametrize("checked,hits", [(1.5, 0), (0, 2.0), ("3", 0), (None, 0), (True, 0)])
def test_non_integer_counts_raise(checked, hits):
    with pytest.raises(TypeError):
        classify_detector_evidence(checked, hits)


# --------------------------------------------------------------------------- #
# an ABSENT counter is not a zero counter (L289)
# --------------------------------------------------------------------------- #
def test_a_missing_counter_field_is_its_own_class_not_a_zero():
    assert classify_record_evidence({"n_anomalies": 0}, "n_pairs_checked") == EVIDENCE_COUNTER_ABSENT


def test_a_present_zero_counter_is_an_empty_denominator_not_an_absent_one():
    rec = {"n_pairs_checked": 0}
    assert classify_record_evidence(rec, "n_pairs_checked") == EVIDENCE_EMPTY_DENOMINATOR


def test_record_classification_can_read_hits_from_a_named_field():
    rec = {"n_pairs_checked": 4, "n_hits": 2}
    assert classify_record_evidence(rec, "n_pairs_checked", hits_field="n_hits") == EVIDENCE_HITS
    rec2 = {"n_pairs_checked": 4}
    assert classify_record_evidence(rec2, "n_pairs_checked",
                                    hits_field="n_hits") == EVIDENCE_INFORMATIVE_ZERO


# --------------------------------------------------------------------------- #
# the persisted block
# --------------------------------------------------------------------------- #
def test_evidence_block_keeps_the_denominator_beside_the_numerator():
    """The whole point: a hit count can never be persisted without its denominator."""
    blk = evidence_block(0, 0)
    assert blk == {"n_candidates_checked": 0, "n_hits": 0,
                   "evidence": EVIDENCE_EMPTY_DENOMINATOR}
    assert set(blk) == {"n_candidates_checked", "n_hits", "evidence"}


def test_evidence_block_rejects_a_negative_count():
    with pytest.raises(ValueError):
        evidence_block(-1, 0)


# --------------------------------------------------------------------------- #
# the loud summary line
# --------------------------------------------------------------------------- #
def test_summary_names_every_unreadable_check():
    blocks = {"a": evidence_block(0, 0), "b": evidence_block(3, 0), "c": evidence_block(0, 2)}
    line = summarize_evidence(blocks)
    assert "EMPTY DENOMINATOR" in line
    assert "a" in line and "c" in line
    assert " b," not in line and not line.endswith(" b")


def test_summary_is_quiet_when_every_denominator_is_real():
    blocks = {"a": evidence_block(3, 0), "b": evidence_block(3, 1)}
    line = summarize_evidence(blocks)
    assert "EMPTY DENOMINATOR" not in line
    assert "readable" in line

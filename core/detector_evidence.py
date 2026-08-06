"""core.detector_evidence — is a detector's ZERO evidence of absence, or evidence of nothing?

Lesson **L296**: *"`n_hits == 0` and `n_candidates_checked == 0` are different claims, and
S15 has been reporting the second while its registry row was read as the first for a month."*

`scripts/anomaly_sweep.py`'s third check (`check_cross_event_implication`, S15/Q11) has
recorded `n_implication_pairs_checked: 0` on **243 of 243** committed passes that carry the
counter — i.e. it has no recorded evidence of ever having evaluated a single candidate pair.
Its own kill clause ("kill if 0 fee-clearing hits in 60 days") was therefore silently
unfireable for weeks: a zero over an empty denominator cannot falsify anything. Nobody
noticed, because nothing in the pipeline distinguished the two zeros. This module is the
distinction, made mechanical and put at the WRITE PATH so a future reader cannot re-make the
mistake by reading a number without its denominator.

The rule, stated once so no caller re-derives it:

    A zero may be read as evidence of ABSENCE only when the detector is on record as having
    evaluated at least one candidate. Every other zero is evidence of NOTHING.

## The four values, and why there are four rather than three

| value | meaning | may a consumer read "absence"? |
|---|---|---|
| `EVIDENCE_HITS`              | the detector fired at least once      | n/a — not a zero |
| `EVIDENCE_INFORMATIVE_ZERO`  | >= 1 candidate checked, 0 hits        | **yes** — this is the only readable zero |
| `EVIDENCE_EMPTY_DENOMINATOR` | 0 candidates checked, 0 hits          | **no** — L296's exact failure |
| `EVIDENCE_INCOHERENT`        | hits > 0 over 0 candidates checked    | **no** — the record contradicts itself |

`EVIDENCE_INCOHERENT` is a returned VALUE rather than a raised exception on purpose, and the
choice is load-bearing. This predicate runs in two places with opposite needs: (1) live,
inside a collector's write path, where raising would abort a capture and DESTROY the pass's
tape over a bookkeeping contradiction — the L86 rule (an honest marker, never a fabricated
number, and never a lost capture); and (2) in replay over already-committed history, where an
exception would make the audit script unable to even COUNT how many self-contradictory records
exist, which is the one number that matters when you find one. A distinct fourth value cannot
be silently absorbed by a consumer the way a coerced `EMPTY_DENOMINATOR` or a swallowed
exception could: it is not equal to any other constant, `zero_is_informative()` returns False
for it, and it sorts into its own bucket in every count. Genuinely malformed INPUT (negative
counts, non-integers) is a different class and DOES raise — that is a programming error in the
caller, not a claim about the market.

Sibling to `core.pricing.is_fillable_ask` (a $0.00 ask is the ABSENCE of an offer, not a free
fill — L105/L288) and `core.subject_identity.same_subject` (nesting must be PROVEN, not merely
un-disproven — L291/L295). Same shape every time: the ambiguous case is named, counted, and
refused rather than rounded to the convenient reading.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# The detector fired: `n_hits >= 1` over a non-empty denominator.
EVIDENCE_HITS = "hits"

# The ONLY zero that carries information: candidates were evaluated and none was a hit.
EVIDENCE_INFORMATIVE_ZERO = "informative_zero"

# L296's failure mode: zero hits because zero candidates were ever evaluated.
EVIDENCE_EMPTY_DENOMINATOR = "empty_denominator"

# Self-contradiction: hits reported over an empty denominator. Never silently absorbed.
EVIDENCE_INCOHERENT = "incoherent"

# A record that predates the counter's existence. Distinct from a present-and-zero counter:
# an ABSENT key and an EMPTY key are different claims, and only the collector's source tells
# you which one you are looking at (L289, the `previous_settlement` false alarm). Consumers
# get this from `classify_record_evidence` when the field is missing; `classify_detector_evidence`
# itself never returns it, because it is a property of the RECORD, not of the counts.
EVIDENCE_COUNTER_ABSENT = "counter_absent"

ALL_EVIDENCE_CLASSES = (
    EVIDENCE_HITS,
    EVIDENCE_INFORMATIVE_ZERO,
    EVIDENCE_EMPTY_DENOMINATOR,
    EVIDENCE_INCOHERENT,
    EVIDENCE_COUNTER_ABSENT,
)


def _as_count(value: Any, name: str) -> int:
    """Coerce a candidate/hit count, raising on anything that is not a non-negative integer.

    Deliberately strict: a float count means the caller computed it wrong, and a negative
    count is meaningless. Both are programming errors, so they raise here rather than being
    classified — unlike the INCOHERENT case, which is a real claim a real record can make.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value).__name__}: {value!r}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value


def classify_detector_evidence(n_candidates_checked: int, n_hits: int) -> str:
    """Return the evidence class of a detector's (denominator, numerator) pair.

    >>> classify_detector_evidence(0, 0)
    'empty_denominator'
    >>> classify_detector_evidence(38, 0)
    'informative_zero'
    >>> classify_detector_evidence(38, 2)
    'hits'
    >>> classify_detector_evidence(0, 1)
    'incoherent'
    """
    checked = _as_count(n_candidates_checked, "n_candidates_checked")
    hits = _as_count(n_hits, "n_hits")
    if checked == 0:
        return EVIDENCE_INCOHERENT if hits > 0 else EVIDENCE_EMPTY_DENOMINATOR
    return EVIDENCE_HITS if hits > 0 else EVIDENCE_INFORMATIVE_ZERO


def zero_is_informative(evidence_class: str) -> bool:
    """True iff a consumer may read this detector's zero as evidence of ABSENCE.

    The single question every consumer of a scanner's zero should be asking. False for
    `EVIDENCE_HITS` too — a detector that fired has no zero to interpret, so "may I read the
    zero as absence?" is not a question that applies, and answering True would be an invitation
    to misuse. Unknown class names return False: this predicate refuses by default, like every
    other burden-of-proof gate in the repo.
    """
    return evidence_class == EVIDENCE_INFORMATIVE_ZERO


def classify_record_evidence(record: Dict[str, Any], counter_field: str,
                             n_hits: Optional[int] = None,
                             hits_field: Optional[str] = None) -> str:
    """Evidence class for one check inside one persisted record.

    Returns `EVIDENCE_COUNTER_ABSENT` when `counter_field` is not a key of `record` — which is
    NOT the same as the counter being zero (L289). Supply the hit count either directly
    (`n_hits`) or by naming a field (`hits_field`, absent => 0 hits recorded).
    """
    if counter_field not in record:
        return EVIDENCE_COUNTER_ABSENT
    if n_hits is None:
        n_hits = int(record.get(hits_field, 0)) if hits_field else 0
    return classify_detector_evidence(int(record[counter_field]), int(n_hits))


def evidence_block(n_candidates_checked: int, n_hits: int) -> Dict[str, Any]:
    """The persisted shape: the denominator, the numerator, and the class, together.

    Kept as one dict so a record can never carry a hit count without the denominator that
    makes it readable — which is exactly how L296 happened. Additive by construction; it does
    not touch, rename, or reinterpret any field a caller already persists.
    """
    return {
        "n_candidates_checked": _as_count(n_candidates_checked, "n_candidates_checked"),
        "n_hits": _as_count(n_hits, "n_hits"),
        "evidence": classify_detector_evidence(n_candidates_checked, n_hits),
    }


def summarize_evidence(blocks: Dict[str, Dict[str, Any]]) -> str:
    """One human-readable line naming every check whose zero is NOT readable.

    Used by the sweep's own console summary so an empty denominator is loud at run time — the
    failure L296 records went unnoticed for a month precisely because nothing said it out loud.
    """
    unreadable = [name for name, b in sorted(blocks.items())
                  if b.get("evidence") in (EVIDENCE_EMPTY_DENOMINATOR, EVIDENCE_INCOHERENT)]
    if not unreadable:
        return "all checks evaluated >= 1 candidate (every zero is readable)"
    return ("EMPTY DENOMINATOR — zero is NOT evidence of absence for: " + ", ".join(unreadable))

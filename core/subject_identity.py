"""core.subject_identity — does a candidate "nested strike pair" actually describe ONE subject?

LOOP-QUEUE.md **Q53**, lesson **L291**. `scripts/anomaly_sweep.py::check_monotonicity` (the
repo's oldest live scanner) assumed that two markets sharing an `event_ticker` and a
`strike_type` are rungs of ONE strike ladder on ONE underlying, so that a narrower strike's
YES-region is a SUBSET of a wider one's and `buy YES(outer) + NO(inner)` pays a guaranteed
>= $1. **Kalshi also packs MULTIPLE SUBJECTS under a single `event_ticker`**, and sorting
those by `floor_strike`/`cap_strike` manufactures a "nested pair" that is really a naked
directional bet on two different things. Measured (L291): after the L290 fillability guard,
13 of the 43,038 anomalies this scanner has ever recorded survive, and **100% of them** pair
two different subjects — two tennis players' game spreads, two batters' props, three cities'
rain markets.

The burden of proof runs the same way as everywhere else in this repo: nesting must be
**PROVEN**, never merely un-disproven. So the verdict is three-valued and the caller must
refuse on two of the three.

## What this module uses as evidence — and what it deliberately does NOT

**It uses the market's own descriptive text (`title` / `subtitle` / `yes_sub_title`),
anchored to the market's own strike bounds.** It does **NOT** parse ticker suffixes. A
ticker-suffix heuristic is the shortcut Q1's build note and the collector house rule both
warn against ("structural confirmation, not ticker suffixes" — the KXFEDDECISION ">25bps as
26" quirk is the canonical trap): suffix grammar is a Kalshi presentation detail that varies
by series and changes without notice, while the title is the claim the contract actually
settles on. The only ticker use anywhere in this module is `event_ticker` grouping, which is
the caller's, not ours.

## The rule, in two parts

Split each market's descriptive text into an alternating sequence of TEXT CHUNKS and NUMERIC
TOKENS. Two markets are `PROVEN_SAME_SUBJECT` iff BOTH hold:

1. **Skeleton equality.** The text-chunk sequences are identical after normalization
   (case-folded, punctuation collapsed). This is what does the real discriminating work: two
   different subjects differ in ALPHABETIC content ("Will *Navone* win ... than *Struff*?" vs
   "Will *Struff* win ... than *Navone*?", "*Wilyer Abreu*: 4+ hits..." vs "*Tsung-Che
   Cheng*: 5+ hits..."), and no amount of numeric normalization can repair an alphabetic
   difference.
2. **Strike-attributable numeric differences.** Wherever the two numeric token sequences
   differ at the same index, that difference must be explainable by each market's OWN strike
   bounds under a SHARED offset — i.e. there is some `d` with `a_token == a_strike + d` and
   `b_token == b_strike + d`. On a genuine ladder the number that moves between rungs IS the
   strike label, so a single family-constant offset explains every rung.

Part 2 exists because Kalshi's strike LABEL is routinely offset from its strike VALUE, and
the offset is a per-family constant, not zero:

| family | `yes_sub_title` | `floor_strike` | offset |
|---|---|---|---|
| `KXHIGHNY` (daily temp) | `97° or above` | `96` | `+1` |
| `KXTEMPNYCH` (hourly temp) | `82° or above` | `81.99` | `+0.01` |
| `KXCPICORE` | `Will CPI Core rise more than 0.3% in August?` | `0.3` | `0` |

A naive "the number in the text must EQUAL the strike" rule would therefore refuse every
weather ladder in `tape/weather_books/` — which is exactly the KXFEDDECISION-class trap, one
family over. The shared-offset formulation absorbs it without inventing a per-series table.

Part 2 also explains why the numeric comparison is POSITIONAL rather than a global mask. If
this module simply blanked every number equal to the strike, then a `KXGDP` rung with
`floor_strike == 2.0` and title "...more than 2.0% in Q2 2026?" would also blank the `2` in
"Q2" while its sibling rung (`floor_strike == 0.3`) would not — a false refusal invented by
the normalizer. Comparing token-for-token at the same index cannot do that.

## Honest limits (read before trusting a verdict)

- **It proves SUBJECT identity, not NESTING.** Two markets can share a subject and still not
  be nested (e.g. two disjoint bands on one underlying). The caller still owes the
  strike-type/ordering argument; this module only removes the premise failure L291 found.
- **It cannot see a subject that lives in a field the caller did not pass.** If two markets
  carry byte-identical descriptive text but differ in some field not among
  `DESCRIPTIVE_FIELDS`, this returns `PROVEN_SAME_SUBJECT`. The corpus audit
  (`scripts/subject_identity_corpus_audit.py`) measures how large that bucket is rather than
  assuming it is empty.
- **`UNVERIFIABLE` is not a soft yes.** A market with no descriptive text, or a numeric
  difference with no strike to attribute it to, yields `UNVERIFIABLE` and MUST be refused by
  the caller. Historical `tape/anomalies/` records persist only tickers, so replaying them
  through this module correctly yields `UNVERIFIABLE` for every one — absence of evidence,
  recorded as such, never upgraded to evidence of absence.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, Optional, Sequence, Tuple

# --------------------------------------------------------------------------- #
# verdicts — three-valued on purpose (see module docstring)
# --------------------------------------------------------------------------- #
SUBJECT_PROVEN_SAME = "proven_same_subject"
SUBJECT_DIFFERENT = "different_subject"
SUBJECT_UNVERIFIABLE = "unverifiable"

#: Descriptive fields consulted, in a FIXED order so the joined text is deterministic.
#: `title` is what Kalshi's open `/markets` listing carries (verified live 2026-07-17, L90 —
#: `collection/universe_sweep.py` persists `m.get("title")` from that same payload), so the
#: live scanner always has at least this much. `yes_sub_title` is what the orderbook-side
#: collectors persist (`tape/weather_books/`), and `subtitle` is carried by some families.
#:
#: **Use this set only when the two markets share a `strike_type`** (i.e. `check_monotonicity`'s
#: shape). A sub-title describes the RUNG, not the subject, and its GRAMMAR changes with the
#: rung's type: one `KXHIGHNY` ladder carries `88° or below`, `95° to 96°` and `97° or above`
#: for one single city. Measured on committed `tape/weather_books/` (Q53 milestone 1,
#: `scripts/subject_identity_corpus_audit.py`): comparing whole cross-type ladders on this
#: field set refuses **880 of 1,591** genuine single-city ladders — a 55.3% FALSE-REFUSE rate,
#: entirely from rung grammar. That is why the cross-type shape gets its own field set below.
DESCRIPTIVE_FIELDS: Tuple[str, ...] = ("title", "subtitle", "yes_sub_title")

#: Fields for comparing markets ACROSS strike types (`check_bracket_arb`'s shape: a complete
#: MECE ladder is a `less` tail + `between` bands + a `greater` tail by construction). Only the
#: title survives a rung-type change unchanged, because it names the SUBJECT rather than the
#: band. Narrower evidence, so it refuses more often when a family does not publish a title —
#: which is the correct direction for an unprovable premise.
SUBJECT_FIELDS_CROSS_STRIKE_TYPE: Tuple[str, ...] = ("title",)

#: Field separator inside the joined descriptive text. Chosen to be punctuation so it
#: normalizes away into a chunk boundary rather than colliding with real words.
_FIELD_SEP = " | "

#: A numeric token: optional sign, digits with optional thousands separators, optional
#: fractional part. The lookbehind stops the regex from biting a digit that is glued to a
#: word ("Q1", "COVID-19", "G1"): those are part of the SUBJECT, not a strike label, and
#: splitting them would fabricate numeric differences between rungs that describe one thing.
_NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?")

#: Tolerance when comparing two numeric tokens, and when matching a token's offset against
#: the sibling's. Kalshi strike values are cent/degree-grid decimals; 1e-6 is far below any
#: real spacing and far above float noise on values up to ~1e6 (KXPAYROLLS runs to 1e5).
_NUM_TOL = 1e-6


def _norm_chunk(chunk: str) -> str:
    """Case-fold a text chunk and collapse every run of non-alphanumerics to one space.

    Deliberately keeps alphanumeric runs intact, so `Q1`, `G1`, `26JUL` and `COVID-19` stay
    part of the subject skeleton instead of dissolving into placeholders.
    """
    return re.sub(r"[^0-9a-z]+", " ", chunk.lower()).strip()


def _parse_number(raw: str) -> Optional[float]:
    try:
        return float(raw.replace(",", "").replace("+", ""))
    except (TypeError, ValueError):
        return None


def descriptive_text(market: Dict[str, Any],
                     fields: Sequence[str] = DESCRIPTIVE_FIELDS) -> str:
    """The market's own descriptive text: every present, non-empty `fields` value joined in
    fixed order. Empty string when the market carries none of them — which the caller must
    treat as `UNVERIFIABLE`, never as a match."""
    parts = []
    for field in fields:
        value = market.get(field)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    return _FIELD_SEP.join(parts)


def strike_values(market: Dict[str, Any]) -> Tuple[float, ...]:
    """The market's own strike bounds (`floor_strike`, `cap_strike`) as floats, skipping
    absent/unparseable ones. These are the ONLY values a numeric difference may be
    attributed to."""
    out = []
    for field in ("floor_strike", "cap_strike"):
        value = market.get(field)
        if value is None:
            continue
        try:
            fv = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isnan(fv):
            out.append(fv)
    return tuple(out)


def skeleton_and_numbers(text: str) -> Tuple[Tuple[str, ...], Tuple[float, ...]]:
    """Split descriptive text into (normalized text chunks, numeric token values).

    `len(chunks) == len(numbers) + 1` always, so two texts with the same chunk sequence are
    guaranteed to have the same number of numeric tokens and are index-comparable.
    """
    chunks = []
    numbers = []
    pos = 0
    for match in _NUM_RE.finditer(text):
        value = _parse_number(match.group())
        if value is None:              # unparseable -> leave it in the skeleton as text
            continue
        chunks.append(_norm_chunk(text[pos:match.start()]))
        numbers.append(value)
        pos = match.end()
    chunks.append(_norm_chunk(text[pos:]))
    return tuple(chunks), tuple(numbers)


def _offsets(token: float, strikes: Sequence[float]) -> Tuple[float, ...]:
    return tuple(token - s for s in strikes)


def _shares_offset(a_offsets: Sequence[float], b_offsets: Sequence[float]) -> bool:
    return any(abs(x - y) <= _NUM_TOL for x in a_offsets for y in b_offsets)


def same_subject(market_a: Dict[str, Any], market_b: Dict[str, Any],
                 fields: Sequence[str] = DESCRIPTIVE_FIELDS) -> Tuple[str, str]:
    """Do these two markets describe the SAME subject? Returns `(verdict, reason)`.

    Verdict is one of `SUBJECT_PROVEN_SAME` / `SUBJECT_DIFFERENT` / `SUBJECT_UNVERIFIABLE`.
    ONLY `SUBJECT_PROVEN_SAME` licenses the nesting premise; both other verdicts are
    refusals at the call site, counted separately because "we proved they are different
    things" and "we could not tell" are different claims and a scanner that conflates them
    reports a clean sweep it did not perform.

    `fields` selects the evidence: `DESCRIPTIVE_FIELDS` for same-`strike_type` pairs,
    `SUBJECT_FIELDS_CROSS_STRIKE_TYPE` when the two markets are different rung types (see
    those constants' notes — using the wrong one costs a measured 55.3% false-refuse rate on
    real weather ladders).
    """
    text_a = descriptive_text(market_a, fields)
    text_b = descriptive_text(market_b, fields)
    if not text_a or not text_b:
        return SUBJECT_UNVERIFIABLE, "no_descriptive_text"

    skel_a, nums_a = skeleton_and_numbers(text_a)
    skel_b, nums_b = skeleton_and_numbers(text_b)
    if skel_a != skel_b:
        # Different alphabetic content. No numeric normalization can repair this, which is
        # why the cross-subject corpus is decidable even where strikes are not persisted.
        return SUBJECT_DIFFERENT, "text_skeleton_differs"

    differing = [i for i, (x, y) in enumerate(zip(nums_a, nums_b)) if abs(x - y) > _NUM_TOL]
    if not differing:
        return SUBJECT_PROVEN_SAME, "identical_descriptive_text"

    strikes_a, strikes_b = strike_values(market_a), strike_values(market_b)
    if not strikes_a or not strikes_b:
        # Same words, different numbers, and nothing to attribute the difference to. Could
        # be two rungs of one ladder; could be two subjects distinguished only by a number.
        # Unknowable from what was passed -> refuse, do not guess.
        return SUBJECT_UNVERIFIABLE, "no_strike_to_attribute_numeric_difference"

    for i in differing:
        if not _shares_offset(_offsets(nums_a[i], strikes_a), _offsets(nums_b[i], strikes_b)):
            return SUBJECT_DIFFERENT, "numeric_difference_not_strike_attributable"
    return SUBJECT_PROVEN_SAME, "numeric_difference_is_strike_attributable"


def all_same_subject(markets: Sequence[Dict[str, Any]],
                     fields: Sequence[str] = SUBJECT_FIELDS_CROSS_STRIKE_TYPE
                     ) -> Tuple[str, str]:
    """Pairwise-against-the-first form for a whole ladder (`check_bracket_arb`'s members).

    Returns the FIRST non-`PROVEN_SAME` verdict encountered, so one cross-subject member
    condemns the basket — which is the honest reading: buying a "complete ladder" that is
    really two subjects' ladders interleaved is not a guaranteed $1 payout.
    A single market (or none) is vacuously one subject. Defaults to
    `SUBJECT_FIELDS_CROSS_STRIKE_TYPE` because a complete ladder spans rung types by
    construction.
    """
    if len(markets) < 2:
        return SUBJECT_PROVEN_SAME, "single_member"
    head = markets[0]
    for other in markets[1:]:
        verdict, reason = same_subject(head, other, fields)
        if verdict != SUBJECT_PROVEN_SAME:
            return verdict, reason
    return SUBJECT_PROVEN_SAME, "all_members_match_first"

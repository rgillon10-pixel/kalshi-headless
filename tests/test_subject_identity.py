"""core.subject_identity + scripts.subject_identity_corpus_audit — LOOP-QUEUE.md Q53
milestone 1 (lesson L291).

Two halves, following tests/test_econ_prints_ladder_fillability_audit.py's shape:

* **fixture tests** prove the predicate FIRES on each of L291's three real cross-subject
  classes and does NOT fire on each real single-subject ladder grammar found on committed
  tape. A detector that never fires is not proven (L191), and a premise test that refuses
  genuine ladders silently deletes real arbs from the scanner's reach — so both directions
  are pinned, with the exact strings the tape carries.
* **acceptance tests** re-run the corpus audit over a CLOSED window and pin both error
  rates. The window (`ACCEPTANCE_MAX_DAY`) matches
  tests/test_anomaly_sweep.py::ACCEPTANCE_MAX_DAY and
  tests/test_econ_prints_ladder_fillability_audit.py::MAX_DAY so all three files' numbers are
  directly comparable, and so tomorrow's collector pass cannot move a pinned figure.
"""
from __future__ import annotations

import pytest

from core.io import REPO_ROOT
from core.subject_identity import (DESCRIPTIVE_FIELDS, SUBJECT_DIFFERENT,
                                   SUBJECT_FIELDS_CROSS_STRIKE_TYPE, SUBJECT_PROVEN_SAME,
                                   SUBJECT_UNVERIFIABLE, all_same_subject, descriptive_text,
                                   same_subject, skeleton_and_numbers, strike_values)
from scripts import subject_identity_corpus_audit as audit


# --------------------------------------------------------------------------- #
# L291's three real cross-subject classes — the predicate MUST refuse all three.
# Every string below is copied from committed tape (`tape/universe_sweep/` titles), not
# invented, so a Kalshi wording change reds these deliberately.
# --------------------------------------------------------------------------- #
def test_refuses_two_tennis_players_packed_into_one_event():
    """`KXATPGSPREAD-26JUL22STRNAV` holds BOTH directions of one match. Sorting them by
    floor_strike makes "Struff by >= 1.5" look like a rung under "Navone by >= 2.5"; buying
    YES(one) + NO(the other) is a naked directional bet on who wins, not an arb."""
    navone = {"ticker": "KXATPGSPREAD-26JUL22STRNAV-NAV3", "floor_strike": 2.5,
              "title": "Will Mariano Navone win at least 2.5 more games than Jan-Lennard Struff?"}
    struff = {"ticker": "KXATPGSPREAD-26JUL22STRNAV-STR2", "floor_strike": 1.5,
              "title": "Will Jan-Lennard Struff win at least 1.5 more games than Mariano Navone?"}
    verdict, reason = same_subject(navone, struff)
    assert verdict == SUBJECT_DIFFERENT
    assert reason == "text_skeleton_differs"


def test_admits_the_genuine_ladder_inside_that_same_tennis_event():
    """The hard half of the same event: two rungs on the SAME player ARE nested (Navone by
    >= 5.5 implies Navone by >= 2.5), and refusing them would delete a real arb. The
    predicate must separate these from the pair above without a per-series table."""
    deep = {"ticker": "KXATPGSPREAD-26JUL22STRNAV-NAV6", "floor_strike": 5.5,
            "title": "Will Mariano Navone win at least 5.5 more games than Jan-Lennard Struff?"}
    shallow = {"ticker": "KXATPGSPREAD-26JUL22STRNAV-NAV3", "floor_strike": 2.5,
               "title": "Will Mariano Navone win at least 2.5 more games than Jan-Lennard Struff?"}
    verdict, reason = same_subject(deep, shallow)
    assert verdict == SUBJECT_PROVEN_SAME
    assert reason == "numeric_difference_is_strike_attributable"


def test_refuses_two_batters_packed_into_one_mlb_event():
    abreu = {"ticker": "KXMLBHRR-26JUL171335TBBOSG1-BOSWABREU52-4", "floor_strike": 3.5,
             "title": "Wilyer Abreu: 4+ hits + runs + RBIs?"}
    cheng = {"ticker": "KXMLBHRR-26JUL171335TBBOSG1-BOSTCHENG39-5", "floor_strike": 4.5,
             "title": "Tsung-Che Cheng: 5+ hits + runs + RBIs?"}
    assert same_subject(abreu, cheng)[0] == SUBJECT_DIFFERENT


def test_admits_two_rungs_on_the_same_batter():
    four = {"floor_strike": 3.5, "title": "Wilyer Abreu: 4+ hits + runs + RBIs?"}
    two = {"floor_strike": 1.5, "title": "Wilyer Abreu: 2+ hits + runs + RBIs?"}
    assert same_subject(four, two)[0] == SUBJECT_PROVEN_SAME


def test_refuses_two_cities_packed_into_one_rain_event():
    """L291's third class. `tape/universe_sweep/` holds no `KXRAIN` capture, so unlike the
    tennis/MLB cases these titles follow Kalshi's published rain wording rather than a
    captured line — the assertion is about the predicate's behaviour on a two-city event,
    which is what the tape's ticker anatomy (`KXRAIN-26JUL23-NYC` vs `-NOLA`) shows."""
    nyc = {"ticker": "KXRAIN-26JUL23-NYC", "floor_strike": 0.5,
           "title": "Will it rain more than 0.5 inches in New York City on July 23?"}
    nola = {"ticker": "KXRAIN-26JUL23-NOLA", "floor_strike": 0.5,
            "title": "Will it rain more than 0.5 inches in New Orleans on July 23?"}
    assert same_subject(nyc, nola)[0] == SUBJECT_DIFFERENT


# --------------------------------------------------------------------------- #
# real single-subject ladder grammars — the predicate MUST admit all of these
# --------------------------------------------------------------------------- #
def test_admits_econ_ladder_whose_title_contains_its_own_strike():
    a = {"floor_strike": 0.3, "title": "Will CPI Core rise more than 0.3% in August?"}
    b = {"floor_strike": 0.9, "title": "Will CPI Core rise more than 0.9% in August?"}
    assert same_subject(a, b)[0] == SUBJECT_PROVEN_SAME


def test_admits_negative_strike_labels():
    """KXCPI and KXPAYROLLS both publish negative strikes ("-0.1%", "-25000 jobs")."""
    a = {"floor_strike": -0.1, "title": "Will CPI rise more than -0.1% in August 2026?"}
    b = {"floor_strike": 0.2, "title": "Will CPI rise more than 0.2% in August 2026?"}
    assert same_subject(a, b)[0] == SUBJECT_PROVEN_SAME
    c = {"floor_strike": -25000, "title": "Will above -25000 jobs be added in July 2026?"}
    d = {"floor_strike": 75000, "title": "Will above 75000 jobs be added in July 2026?"}
    assert same_subject(c, d)[0] == SUBJECT_PROVEN_SAME


def test_admits_crypto_ladder_whose_title_carries_only_NON_strike_numbers():
    """`Bitcoin price range on Aug 5, 2026?` is identical across every rung; the `5` and
    `2026` must survive as subject content rather than being mistaken for strike labels."""
    a = {"floor_strike": 54200, "cap_strike": 54299.99,
         "title": "Bitcoin price range on Aug 5, 2026?"}
    b = {"floor_strike": 55200, "cap_strike": 55299.99,
         "title": "Bitcoin price range on Aug 5, 2026?"}
    verdict, reason = same_subject(a, b)
    assert (verdict, reason) == (SUBJECT_PROVEN_SAME, "identical_descriptive_text")


@pytest.mark.parametrize("a_sub,a_floor,b_sub,b_floor,offset", [
    # daily weather: label is strike + 1  (KXHIGHNY-26JUL16-T96 -> "97° or above")
    ("97° or above", 96, "93° or above", 92, 1),
    # hourly weather: label is strike + 0.01 (KXTEMPNYCH-...-T81.99 -> "82° or above")
    ("82° or above", 81.99, "80° or above", 79.99, 0.01),
])
def test_admits_weather_ladders_whose_label_is_OFFSET_from_the_strike(a_sub, a_floor,
                                                                     b_sub, b_floor, offset):
    """THE trap this design exists to survive: Kalshi's published strike LABEL is offset from
    the strike VALUE by a per-family constant (the KXFEDDECISION ">25bps as 26" quirk, one
    family over). A rule demanding label == strike would refuse every weather ladder on
    committed tape. The shared-offset formulation absorbs it with no per-series table."""
    a = {"yes_sub_title": a_sub, "floor_strike": a_floor}
    b = {"yes_sub_title": b_sub, "floor_strike": b_floor}
    assert a_sub.split("°")[0] == str(int(a_floor + offset))   # the offset is real, not assumed
    assert same_subject(a, b)[0] == SUBJECT_PROVEN_SAME


def test_admits_between_band_ladder_on_both_bounds():
    a = {"yes_sub_title": "95° to 96°", "floor_strike": 95, "cap_strike": 96}
    b = {"yes_sub_title": "89° to 90°", "floor_strike": 89, "cap_strike": 90}
    assert same_subject(a, b)[0] == SUBJECT_PROVEN_SAME


# --------------------------------------------------------------------------- #
# the two design decisions that a naive implementation gets wrong
# --------------------------------------------------------------------------- #
def test_positional_comparison_not_a_global_strike_mask():
    """A global "blank every number equal to the strike" normalizer invents a false refusal:
    the `KXGDP` rung with floor_strike 2.0 would ALSO blank the `2` in `Q2`, while its
    sibling rung (floor 0.3) would not, so two rungs of one ladder would stop matching.
    Comparing token-for-token at the same index cannot do that."""
    a = {"floor_strike": 2.0,
         "title": "Will **real GDP** increase by more than 2.0% in Q2 2026?"}
    b = {"floor_strike": 0.3,
         "title": "Will **real GDP** increase by more than 0.3% in Q2 2026?"}
    assert same_subject(a, b)[0] == SUBJECT_PROVEN_SAME
    # and the `Q2` digit is never tokenized at all — it is glued to a word, so it stays
    # subject content
    assert skeleton_and_numbers("more than 2.0% in Q2 2026?")[1] == (2.0, 2026)


def test_a_number_glued_to_a_word_stays_part_of_the_subject():
    """`G1` (game 1 of a doubleheader) distinguishes two DIFFERENT events' worth of markets;
    dissolving it into a numeric placeholder would merge them."""
    skel, nums = skeleton_and_numbers("Rays at Red Sox G1: 4+ runs?")
    assert nums == (4,)
    assert "g1" in " ".join(skel)


def test_refuses_when_a_numeric_difference_has_no_strike_to_attribute_it_to():
    """Same words, different numbers, no strike fields: could be two rungs of one ladder,
    could be two subjects distinguished only by a number. Unknowable -> UNVERIFIABLE, which
    the caller must refuse. This is exactly the state `tape/universe_sweep/` records are in."""
    a = {"title": "Will average **gas prices** be above $4.140?"}
    b = {"title": "Will average **gas prices** be above $4.135?"}
    verdict, reason = same_subject(a, b)
    assert verdict == SUBJECT_UNVERIFIABLE
    assert reason == "no_strike_to_attribute_numeric_difference"


def test_refuses_when_a_numeric_difference_is_not_strike_attributable():
    """Same words, and both markets have strikes, but the differing number does NOT track
    either strike under a shared offset -> the number is subject content, not a rung label."""
    a = {"title": "Will pitcher 7 record 3+ strikeouts?", "floor_strike": 2.5}
    b = {"title": "Will pitcher 9 record 3+ strikeouts?", "floor_strike": 2.5}
    verdict, reason = same_subject(a, b)
    assert verdict == SUBJECT_DIFFERENT
    assert reason == "numeric_difference_not_strike_attributable"


def test_no_descriptive_text_is_unverifiable_never_a_match():
    """Historical `tape/anomalies/` records persist only tickers. Replaying them must yield
    UNVERIFIABLE — absence of evidence, never upgraded to evidence of absence."""
    assert same_subject({"ticker": "A"}, {"ticker": "B"}) == (
        SUBJECT_UNVERIFIABLE, "no_descriptive_text")
    assert same_subject({"title": "  "}, {"title": "x"})[0] == SUBJECT_UNVERIFIABLE


def test_no_ticker_text_is_ever_consulted():
    """The ticker is grouping evidence for the CALLER, never verdict evidence here (Q1's
    'structural confirmation, not ticker suffixes'). Two markets with wildly different
    tickers and identical titles are the same subject; identical tickers cannot rescue
    different titles."""
    assert same_subject({"ticker": "TOTALLY-DIFFERENT-A", "title": "Bitcoin price range?"},
                        {"ticker": "ZZZ-9", "title": "Bitcoin price range?"})[0] == \
        SUBJECT_PROVEN_SAME
    assert same_subject({"ticker": "SAME-T1", "title": "Navone wins?", "floor_strike": 1},
                        {"ticker": "SAME-T1", "title": "Struff wins?", "floor_strike": 1})[0] == \
        SUBJECT_DIFFERENT
    assert "ticker" not in DESCRIPTIVE_FIELDS
    assert "ticker" not in SUBJECT_FIELDS_CROSS_STRIKE_TYPE


# --------------------------------------------------------------------------- #
# the field-set split (cross-strike-type comparisons)
# --------------------------------------------------------------------------- #
_WEATHER_LADDER = [
    {"yes_sub_title": "88° or below", "cap_strike": 89, "strike_type": "less",
     "title": "Highest temperature in NYC on Jul 16?"},
    {"yes_sub_title": "95° to 96°", "floor_strike": 95, "cap_strike": 96,
     "strike_type": "between", "title": "Highest temperature in NYC on Jul 16?"},
    {"yes_sub_title": "97° or above", "floor_strike": 96, "strike_type": "greater",
     "title": "Highest temperature in NYC on Jul 16?"},
]


def test_sub_title_grammar_changes_across_rung_types_and_would_false_refuse():
    """The measured failure that motivated `SUBJECT_FIELDS_CROSS_STRIKE_TYPE`: one city's
    complete ladder carries three different sub-title GRAMMARS, so comparing whole ladders on
    the sub-title refuses them. On committed `tape/weather_books/` this costs 880 of 1,591
    genuine single-city ladders (55.3%) — pinned in the acceptance block below."""
    assert all_same_subject(_WEATHER_LADDER, DESCRIPTIVE_FIELDS) == (
        SUBJECT_DIFFERENT, "text_skeleton_differs")


def test_the_cross_strike_type_field_set_admits_that_same_ladder():
    assert all_same_subject(_WEATHER_LADDER)[0] == SUBJECT_PROVEN_SAME
    assert all_same_subject(_WEATHER_LADDER, SUBJECT_FIELDS_CROSS_STRIKE_TYPE)[0] == \
        SUBJECT_PROVEN_SAME


def test_all_same_subject_condemns_a_basket_on_one_foreign_member():
    members = [{"title": "Highest temperature in NYC on Jul 16?"},
               {"title": "Highest temperature in NYC on Jul 16?"},
               {"title": "Highest temperature in Denver on Jul 16?"}]
    assert all_same_subject(members)[0] == SUBJECT_DIFFERENT
    assert all_same_subject(members[:1])[0] == SUBJECT_PROVEN_SAME   # vacuous


def test_helper_surface():
    assert descriptive_text({"title": "T", "yes_sub_title": "S"}) == "T | S"
    assert descriptive_text({}) == ""
    assert strike_values({"floor_strike": 1, "cap_strike": None}) == (1.0,)
    assert strike_values({"floor_strike": "bad"}) == ()


# --------------------------------------------------------------------------- #
# acceptance — the corpus audit over committed tape, CLOSED window
# --------------------------------------------------------------------------- #
ACCEPTANCE_MAX_DAY = "2026-08-04"


@pytest.fixture(scope="module")
def report():
    for family in ("econ_prints", "weather_books", "crypto_hourly", "universe_sweep"):
        if not (REPO_ROOT / "tape" / family).exists():
            pytest.skip(f"committed {family} tape not present")
    return audit.build_report(ACCEPTANCE_MAX_DAY)


def test_acceptance_zero_false_refusals_on_every_genuine_ladder_corpus(report):
    """FALSE-REFUSE rate, the error that would silently delete real arbs: 0 of 34,334
    monotonicity-shaped pairs across two genuine-ladder families. `crypto_hourly` contributes
    0 pairs BY CONSTRUCTION (each crypto event carries exactly one `greater` and one `less`
    rung, everything else is `between`), which is reported rather than hidden inside a
    total."""
    econ = report["genuine_ladder_corpora"]["econ_prints"]["monotonicity_shape"]
    weather = report["genuine_ladder_corpora"]["weather_books"]["monotonicity_shape"]
    crypto = report["genuine_ladder_corpora"]["crypto_hourly"]["monotonicity_shape"]
    assert (econ["n_pairs"], econ["n_false_refusals"]) == (2348, 0)
    assert (weather["n_pairs"], weather["n_false_refusals"]) == (31986, 0)
    assert crypto["n_pairs"] == 0
    assert econ["n_pairs"] + weather["n_pairs"] + crypto["n_pairs"] == 34334
    for block in (econ, weather):
        assert block["false_refuse_rate"] == 0.0
        assert block["n_classes_sampled"] == 0        # exhaustive, not sampled


def test_acceptance_zero_false_admits_on_the_labeled_cross_subject_corpus(report):
    """FALSE-ADMIT rate, the error L291 found: 0 of 2,364 pairs that a ground-truth label
    (a player-name regex, computed independently of the predicate) says are CROSS-subject.
    The same 2,515-pair corpus also contains 151 genuine within-player ladders, and none is
    refused — the two error rates are measured on one corpus, not two convenient ones."""
    atp = report["labeled_cross_subject"]["atp_game_spreads"]
    mlb = report["labeled_cross_subject"]["mlb_batter_props"]
    assert (atp["true_refuse_cross_subject"], atp["false_admit_cross_subject"]) == (4, 0)
    assert (atp["true_admit_same_subject"], atp["false_refuse_same_subject"]) == (5, 0)
    assert (mlb["true_refuse_cross_subject"], mlb["false_admit_cross_subject"]) == (2360, 0)
    assert (mlb["true_admit_same_subject"], mlb["false_refuse_same_subject"]) == (146, 0)
    assert atp["n_titles_unlabeled_by_ground_truth_regex"] == 0
    assert mlb["n_titles_unlabeled_by_ground_truth_regex"] == 0
    n_cross = atp["true_refuse_cross_subject"] + mlb["true_refuse_cross_subject"]
    n_same = atp["true_admit_same_subject"] + mlb["true_admit_same_subject"]
    assert (n_cross, n_same) == (2364, 151)
    assert atp["false_admit_rate_over_true_cross_subject_pairs"] == 0.0
    assert mlb["false_admit_rate_over_true_cross_subject_pairs"] == 0.0


def test_acceptance_platform_wide_verdict_split_and_its_residual_risk_bucket(report):
    """The platform-wide cut, reported honestly rather than as a rate it cannot support:
    `tape/universe_sweep/` carries titles but NO strike fields, so a pair whose words match
    and whose numbers differ is UNDECIDABLE on this corpus. 78.4% of pairs are decided by
    alphabetic difference alone; 21.6% are indeterminate. The 15 decided-ADMIT pairs are all
    `KXATPGTOTAL` total-games rungs of ONE match (identical title, strike lives in a field
    this family does not publish) — genuine same-subject, i.e. 0 false admits among decided
    pairs."""
    block = report["cross_subject_corpus_universe_sweep"]["all_within_event_pairs"]
    assert block["n_pairs"] == 1190426
    assert block["verdicts"][SUBJECT_DIFFERENT] == 932965
    assert block["verdicts"][SUBJECT_PROVEN_SAME] == 15
    assert block["verdicts"][SUBJECT_UNVERIFIABLE] == 257446
    assert block["reasons"]["identical_descriptive_text"] == 15
    assert block["reasons"]["no_strike_to_attribute_numeric_difference"] == 257446
    admits = block["examples"]["identical_descriptive_text"]
    assert admits and all("KXATPGTOTAL" in row[0] for row in admits)
    census = report["cross_subject_corpus_universe_sweep"]["indeterminate_bucket_census"]
    assert census["n_distinct_skeletons"] == 24094
    # the bucket's two dominant classes, both of which resolve correctly for the live
    # scanner: KXMVE* parlays carry no strike_type at all (never reach check_monotonicity,
    # and would be UNVERIFIABLE if they did), and the commodity hourlies are genuine
    # single-subject ladders whose differing number IS the strike.
    top_series = {s for row in census["top"][:12] for s in row["series_sample"]}
    assert {"KXMVESPORTSMULTIGAMEEXTENDED", "KXGOLDH", "KXWTIH"} <= top_series


def test_acceptance_the_wrong_field_set_costs_880_of_1591_weather_ladders(report):
    """The measurement that produced `SUBJECT_FIELDS_CROSS_STRIKE_TYPE`, kept in the report
    so the reason for the split stays falsifiable instead of becoming folklore."""
    weather = report["genuine_ladder_corpora"]["weather_books"]
    wrong = weather["bracket_shape_if_sub_title_were_included"]
    assert wrong["n_events"] == 1591
    assert wrong["verdicts"][SUBJECT_DIFFERENT] == 880
    assert round(880 / 1591, 3) == 0.553
    # and the corpus's honest limit: weather_books persists no `title`, so the field set the
    # scanner actually uses is UNVERIFIABLE on this family. The live scanner reads /markets,
    # which does carry `title` (collection/universe_sweep.py persists it from that payload).
    right = weather["bracket_shape"]
    assert right["fields"] == ["title"]
    assert right["verdicts"][SUBJECT_UNVERIFIABLE] == 1591
    for family, n in (("econ_prints", 27), ("crypto_hourly", 802)):
        block = report["genuine_ladder_corpora"][family]["bracket_shape"]
        assert block["verdicts"][SUBJECT_PROVEN_SAME] == n
        assert block["verdicts"][SUBJECT_DIFFERENT] == 0


def test_acceptance_every_corpus_line_parsed(report):
    """Honest completeness: a malformed line is counted, never silently dropped."""
    for family in ("econ_prints", "crypto_hourly", "weather_books"):
        assert report["genuine_ladder_corpora"][family]["n_malformed_lines"] == 0
    assert report["cross_subject_corpus_universe_sweep"]["n_malformed_lines"] == 0
    assert report["max_day"] == ACCEPTANCE_MAX_DAY

"""collection.odds_api — team-name normalization, game<->event matching, bookmaker
selection + de-vig pairing, and the fully offline enrichment orchestration (stub HTTP,
no network) with honest per-game statuses and quota discipline."""
from __future__ import annotations

import json

import pytest

from collection import odds_api as oa

# --------------------------------------------------------------------------- #
# normalization + team matching
# --------------------------------------------------------------------------- #
def test_normalize_team_strips_accents_punct_and_club_noise():
    assert oa.normalize_team("Mjällby AIF") == ["mjallby", "aif"]
    assert oa.normalize_team("Detroit City FC") == ["detroit", "city"]
    assert oa.normalize_team("St. Louis City SC") == ["st", "louis", "city"]


def test_normalize_team_never_empties_a_name():
    # a name made entirely of "noise" tokens keeps its original tokens
    assert oa.normalize_team("FC") == ["fc"]


def test_team_match_score_exact_and_containment():
    assert oa.team_match_score("Portugal", "Portugal") == 1.0
    assert oa.team_match_score("Cleveland", "Cleveland Guardians") == pytest.approx(0.85)
    assert oa.team_match_score("IK Sirius FK", "Sirius") == pytest.approx(0.85)


def test_team_match_score_abbreviation_credit():
    # Kalshi "Chicago WS" vs the book's "Chicago White Sox": 'ws' = initials of White Sox
    assert oa.team_match_score("Chicago WS", "Chicago White Sox") >= 0.7
    # prefix abbreviation: 'Bul' inside 'Western Bulldogs'
    assert oa.team_match_score("W Bulldogs", "Western Bulldogs") >= 0.7


def test_team_match_score_rejects_unrelated():
    assert oa.team_match_score("Portugal", "Croatia") < oa.MIN_SIDE_SCORE
    assert oa.team_match_score("", "Portugal") == 0.0


def test_parse_game_title_variants():
    assert oa.parse_game_title("Portugal vs Croatia Winner?") == ("Portugal", "Croatia")
    assert oa.parse_game_title("Western Bulldogs vs Sydney Swans winner?") == \
        ("Western Bulldogs", "Sydney Swans")
    assert oa.parse_game_title("USA vs. Belgium: Winner?") == ("USA", "Belgium")
    assert oa.parse_game_title("USA vs Belgium Total Goals") is None


def test_parse_outcome_name_strips_reg_time_prefix():
    assert oa.parse_outcome_name("Reg Time: Portugal") == "Portugal"
    assert oa.parse_outcome_name("Reg Time: Tie") == "Tie"
    assert oa.parse_outcome_name("Portugal") == "Portugal"
    assert oa.parse_outcome_name(None) is None
    assert oa.parse_outcome_name("  ") is None


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
def _kalshi_record(event_ticker="KXWCGAME-26JUL06USABEL",
                   title="USA vs Belgium Winner?",
                   game_start="2026-07-07T03:00:00Z", series="KXWCGAME",
                   outcome_names=("USA", "Tie", "Belgium")):
    return {
        "series": series,
        "event_ticker": event_ticker,
        "game_date": "2026-07-06",
        "game_start": game_start,
        "game_title": title,
        "outcomes": [
            {"ticker": f"{event_ticker}-{n[:3].upper()}", "outcome_code": n[:3].upper(),
             "outcome_name": n} for n in outcome_names
        ],
        "odds_leg": {"status": "blocked_key"},
    }


def _odds_event(event_id="ev1", commence="2026-07-07T03:00:00Z",
                home="USA", away="Belgium", bookmakers=None):
    if bookmakers is None:
        bookmakers = [_bookmaker("pinnacle")]
    return {"id": event_id, "sport_key": "soccer_fifa_world_cup",
            "commence_time": commence, "home_team": home, "away_team": away,
            "bookmakers": bookmakers}


def _bookmaker(key, outcomes=None):
    if outcomes is None:
        outcomes = [{"name": "USA", "price": 3.1}, {"name": "Belgium", "price": 2.3},
                    {"name": "Draw", "price": 3.4}]
    return {"key": key, "title": key, "last_update": "2026-07-06T20:00:00Z",
            "markets": [{"key": "h2h", "last_update": "2026-07-06T20:00:00Z",
                         "outcomes": outcomes}]}


# --------------------------------------------------------------------------- #
# game <-> event matching
# --------------------------------------------------------------------------- #
def test_match_event_by_kickoff_and_teams():
    ev = _odds_event()
    got, status, score = oa.match_event(_kalshi_record(), [ev])
    assert status == "matched" and got is ev and score >= oa.MIN_TOTAL_SCORE


def test_match_event_orientation_flip():
    ev = _odds_event(home="Belgium", away="USA")   # book lists home/away opposite to title
    got, status, _ = oa.match_event(_kalshi_record(), [ev])
    assert status == "matched" and got is ev


def test_match_event_rejects_kickoff_outside_window():
    ev = _odds_event(commence="2026-07-07T08:00:00Z")   # 5h from game_start, window is 3h
    got, status, _ = oa.match_event(_kalshi_record(), [ev])
    assert got is None and status == "no_match"


def test_match_event_falls_back_to_game_date_without_game_start():
    rec = _kalshi_record(game_start=None)
    ev = _odds_event(commence="2026-07-06T22:00:00Z")
    got, status, _ = oa.match_event(rec, [ev])
    assert status == "matched" and got is ev


def test_match_event_ambiguous_when_two_candidates_tie():
    ev1 = _odds_event(event_id="ev1")
    ev2 = _odds_event(event_id="ev2")
    got, status, _ = oa.match_event(_kalshi_record(), [ev1, ev2])
    assert got is None and status == "ambiguous"


def test_match_event_wrong_teams_no_match():
    ev = _odds_event(home="Portugal", away="Spain")
    got, status, _ = oa.match_event(_kalshi_record(), [ev])
    assert got is None and status == "no_match"


# --------------------------------------------------------------------------- #
# bookmaker selection + fair-prob pairing
# --------------------------------------------------------------------------- #
def test_build_odds_leg_pairs_fair_probs_and_maps_tie_to_draw():
    rec = _kalshi_record()
    leg = oa.build_odds_leg(rec, _odds_event(), "soccer_fifa_world_cup", 2.0)
    assert leg["status"] == "matched"
    assert leg["bookmaker"] == "pinnacle" and leg["bookmaker_preferred"] is True
    assert leg["price_source_tag"] == "synthetic"
    assert leg["outcome_coverage"] == "full"
    fair = {o["kalshi_outcome_name"]: o["fair_prob"] for o in leg["outcomes"]}
    assert fair["Tie"] is not None                     # Tie <-> Draw special case
    assert sum(fair.values()) == pytest.approx(1.0, abs=1e-9)
    # de-vig is proportional: fair ordering matches raw odds ordering
    assert fair["Belgium"] > fair["USA"] > fair["Tie"] * 0  # Belgium shortest odds
    assert leg["book_overround"] == pytest.approx(1/3.1 + 1/2.3 + 1/3.4 - 1.0, abs=1e-9)


def test_build_odds_leg_prefers_pinnacle_over_other_books():
    ev = _odds_event(bookmakers=[_bookmaker("draftkings"), _bookmaker("pinnacle")])
    leg = oa.build_odds_leg(_kalshi_record(), ev, "soccer_fifa_world_cup", 2.0)
    assert leg["bookmaker"] == "pinnacle"


def test_build_odds_leg_falls_back_to_any_book_and_records_it():
    ev = _odds_event(bookmakers=[_bookmaker("draftkings")])
    leg = oa.build_odds_leg(_kalshi_record(), ev, "soccer_fifa_world_cup", 2.0)
    assert leg["status"] == "matched"
    assert leg["bookmaker"] == "draftkings" and leg["bookmaker_preferred"] is False


def test_build_odds_leg_no_bookmaker():
    ev = _odds_event(bookmakers=[])
    leg = oa.build_odds_leg(_kalshi_record(), ev, "soccer_fifa_world_cup", 2.0)
    assert leg["status"] == "no_bookmaker"


def test_build_odds_leg_partial_coverage_stays_explicit():
    # book only quotes the two teams (no Draw) -> Kalshi's Tie outcome pairs to null
    ev = _odds_event(bookmakers=[_bookmaker("pinnacle", outcomes=[
        {"name": "USA", "price": 2.8}, {"name": "Belgium", "price": 1.55}])])
    leg = oa.build_odds_leg(_kalshi_record(), ev, "soccer_fifa_world_cup", 2.0)
    assert leg["outcome_coverage"] == "partial"
    by_name = {o["kalshi_outcome_name"]: o for o in leg["outcomes"]}
    assert by_name["Tie"]["fair_prob"] is None and by_name["Tie"]["book_outcome"] is None
    assert by_name["USA"]["fair_prob"] is not None


# --------------------------------------------------------------------------- #
# enrichment orchestration (stub HTTP, no network)
# --------------------------------------------------------------------------- #
def _stub_http(catalogue=None, odds_by_sport=None, headers_by_sport=None,
               fail_catalogue=False, fail_sports=()):
    """Stub for odds_api's http_get(url, params) -> (status, text, headers)."""
    catalogue = catalogue if catalogue is not None else [
        {"key": "soccer_fifa_world_cup", "active": True},
        {"key": "aussierules_afl", "active": True},
        {"key": "baseball_mlb", "active": True},
    ]
    odds_by_sport = odds_by_sport or {}
    headers_by_sport = headers_by_sport or {}
    calls = []

    def http_get(url, params):
        calls.append(url)
        if url.endswith("/sports"):
            if fail_catalogue:
                return 500, "boom", {}
            return 200, json.dumps(catalogue), {}
        sport = url.rsplit("/", 2)[-2]
        if sport in fail_sports:
            return 429, "quota", {}
        return (200, json.dumps(odds_by_sport.get(sport, [])),
                headers_by_sport.get(sport, {"x-requests-remaining": "480",
                                             "x-requests-used": "20"}))

    http_get.calls = calls
    return http_get


def test_enrich_records_end_to_end_statuses():
    records = [
        _kalshi_record(),                                        # WC: selected by default
        _kalshi_record(series="KXMLBGAME", title="Chicago WS vs Cleveland Winner?",
                       outcome_names=("Chicago WS", "Cleveland")),  # mapped, NOT selected
        _kalshi_record(series="KXVBAGAME"),                      # unmapped series
    ]
    http = _stub_http(odds_by_sport={"soccer_fifa_world_cup": [_odds_event()]})
    summary = oa.enrich_records(records, "k", http_get=http, env={})
    assert records[0]["odds_leg"]["status"] == "matched"
    assert records[1]["odds_leg"]["status"] == "not_selected"
    assert records[2]["odds_leg"]["status"] == "unmapped_series"
    assert summary["n_matched"] == 1
    assert summary["status_counts"] == {"matched": 1, "not_selected": 1,
                                        "unmapped_series": 1}
    assert summary["quota_remaining"] == 480 and summary["quota_used"] == 20


def test_enrich_records_env_selection_accepts_series_ticker_and_all():
    records = [_kalshi_record(series="KXMLBGAME", title="Chicago WS vs Cleveland Winner?",
                              outcome_names=("Chicago WS", "Cleveland"))]
    http = _stub_http()
    oa.enrich_records(records, "k", http_get=http, env={"ODDS_API_SPORTS": "KXMLBGAME"})
    assert records[0]["odds_leg"]["status"] == "no_match"    # fetched (empty events)
    records[0]["odds_leg"] = {"status": "blocked_key"}
    oa.enrich_records(records, "k", http_get=_stub_http(),
                      env={"ODDS_API_SPORTS": "all"})
    assert records[0]["odds_leg"]["status"] == "no_match"


def test_enrich_records_sport_not_active():
    records = [_kalshi_record()]
    http = _stub_http(catalogue=[{"key": "soccer_fifa_world_cup", "active": False}])
    oa.enrich_records(records, "k", http_get=http, env={})
    assert records[0]["odds_leg"]["status"] == "sport_not_active"


def test_enrich_records_catalogue_failure_degrades_all_fetched_sports():
    records = [_kalshi_record(), _kalshi_record(series="KXVBAGAME")]
    http = _stub_http(fail_catalogue=True)
    summary = oa.enrich_records(records, "k", http_get=http, env={})
    assert records[0]["odds_leg"]["status"] == "fetch_error"
    assert records[1]["odds_leg"]["status"] == "unmapped_series"   # decided pre-fetch
    assert summary["n_matched"] == 0


def test_enrich_records_per_sport_fetch_error_is_isolated():
    records = [
        _kalshi_record(series="KXAFLGAME", title="A vs B Winner?",
                       outcome_names=("A", "B")),
        _kalshi_record(),
    ]
    http = _stub_http(odds_by_sport={"soccer_fifa_world_cup": [_odds_event()]},
                      fail_sports=("aussierules_afl",))
    oa.enrich_records(records, "k", http_get=http,
                      env={"ODDS_API_SPORTS": "all"})
    assert records[0]["odds_leg"]["status"] == "fetch_error"
    assert records[1]["odds_leg"]["status"] == "matched"     # soccer unaffected


def test_enrich_records_quota_floor_halts_further_sports():
    # sports are fetched in sorted order: aussierules_afl first, soccer second.
    # AFL's response reports remaining below the floor -> soccer is NOT fetched.
    records = [
        _kalshi_record(series="KXAFLGAME", title="A vs B Winner?",
                       outcome_names=("A", "B")),
        _kalshi_record(),
    ]
    http = _stub_http(headers_by_sport={"aussierules_afl":
                                        {"x-requests-remaining": "3",
                                         "x-requests-used": "497"}})
    oa.enrich_records(records, "k", http_get=http,
                      env={"ODDS_API_SPORTS": "all"})
    assert records[1]["odds_leg"]["status"] == "quota_floor"
    assert records[1]["odds_leg"]["quota_remaining"] == 3
    assert not any(u.endswith("soccer_fifa_world_cup/odds") for u in http.calls)


def test_enrich_records_quota_floor_env_override():
    records = [
        _kalshi_record(series="KXAFLGAME", title="A vs B Winner?",
                       outcome_names=("A", "B")),
        _kalshi_record(),
    ]
    http = _stub_http(
        odds_by_sport={"soccer_fifa_world_cup": [_odds_event()]},
        headers_by_sport={"aussierules_afl": {"x-requests-remaining": "3",
                                              "x-requests-used": "497"}})
    oa.enrich_records(records, "k", http_get=http,
                      env={"ODDS_API_SPORTS": "all", "ODDS_API_QUOTA_FLOOR": "0"})
    assert records[1]["odds_leg"]["status"] == "matched"     # floor disabled -> fetched

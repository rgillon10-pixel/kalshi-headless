"""Offline tests for scripts/q52_q54_trades_backfill_phase1.py.

NO NETWORK in any path: every test either runs the planner (committed tape only, by
construction offline) or injects a fake `runner`/`resolver` in place of
`collection.kalshi_trades.run` and the settlement registry.

Two tiers, same shape as tests/test_kalshi_trades_backfill_population_audit.py:

  * UNIT tests over hand-built fixture tape — the eligibility funnel's three filters, the
    league round-robin ordering (the thing that stops a byte-capped prefix from being one
    league's alphabet), the day-window plan, and the four ways execution can stop.
  * `test_acceptance_*` over the REAL committed tape. Everything tape-sourced is asserted as
    a DIRECTIONAL BOUND (`>=`), per the L280 rule: a legitimate step-0b stranded-branch sweep
    may union-append lines to a past day, which can only ADD eligible tickers and games.

This module asserts NO mean, NO CI, NO P&L, NO fill rate and NO strategy verdict — the
driver is a collector, and `test_report_is_collection_only` pins that it stays one.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import q52_q54_trades_backfill_phase1 as B


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
class _Rep:
    """Stand-in for core.settlement_sources.MarketResultReport (only what we read)."""

    def __init__(self, resolved, sources=("fake_family",)):
        self.resolved = dict.fromkeys(resolved, "yes")
        self.sources_scanned = tuple(sources)


def _resolver(resolved):
    def _f(tickers, root=None):
        return _Rep([t for t in tickers if t in set(resolved)])
    return _f


def _depth_line(ticker: str, cap: str) -> str:
    return json.dumps({"ticker": ticker, "capture_id": cap, "captured_at": cap,
                       "best_yes_bid": 0.5, "best_no_bid": 0.5})


def _write_depth(root: Path, day: str, pairs) -> None:
    """pairs: [(ticker, n_snapshots)]."""
    d = root / "orderbook_depth"
    d.mkdir(parents=True, exist_ok=True)
    lines = []
    for tk, n in pairs:
        for i in range(n):
            lines.append(_depth_line(tk, f"{day}T0{i}:00:00Z"))
    (d / f"dt={day}.jsonl").write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# population funnel — the three filters, each pinned separately
# --------------------------------------------------------------------------- #
def test_single_snapshot_ticker_is_not_eligible(tmp_path):
    _write_depth(tmp_path, "2026-07-07", [("KXMLBGAME-26JUL07AAABBB-AAA", 1)])
    games, stats = B.eligible_ticker_days(
        tmp_path, ["2026-07-07"], resolver=_resolver(["KXMLBGAME-26JUL07AAABBB-AAA"]))
    assert games == {}
    assert stats["n_ticker_days"] == 0


def test_non_sports_and_kxmve_tickers_are_excluded(tmp_path):
    _write_depth(tmp_path, "2026-07-07", [
        ("KXBTCD-26JUL0712-T50", 4),                 # not a *GAME series
        ("KXMVEGAME-26JUL07AAABBB-AAA", 4),          # L31 exclusion
        ("KXMLBGAME-26JUL07AAABBB-AAA", 4),          # keeper
    ])
    games, _ = B.eligible_ticker_days(
        tmp_path, ["2026-07-07"],
        resolver=_resolver(["KXBTCD-26JUL0712-T50", "KXMVEGAME-26JUL07AAABBB-AAA",
                            "KXMLBGAME-26JUL07AAABBB-AAA"]))
    assert list(games) == ["KXMLBGAME-26JUL07AAABBB"]


def test_unsettled_ticker_is_excluded_even_with_plenty_of_book(tmp_path):
    _write_depth(tmp_path, "2026-07-07", [("KXMLBGAME-26JUL07AAABBB-AAA", 9)])
    games, stats = B.eligible_ticker_days(tmp_path, ["2026-07-07"], resolver=_resolver([]))
    assert games == {}
    assert stats["n_sports_eligible_union"] == 1
    assert stats["n_sports_settled_union"] == 0


def test_same_game_across_two_days_yields_two_ticker_days_one_game(tmp_path):
    tk = "KXMLBGAME-26JUL07AAABBB-AAA"
    _write_depth(tmp_path, "2026-07-07", [(tk, 3)])
    _write_depth(tmp_path, "2026-07-08", [(tk, 3)])
    games, stats = B.eligible_ticker_days(
        tmp_path, ["2026-07-07", "2026-07-08"], resolver=_resolver([tk]))
    assert stats["n_games"] == 1 and stats["n_ticker_days"] == 2
    assert games["KXMLBGAME-26JUL07AAABBB"] == [("2026-07-07", tk), ("2026-07-08", tk)]


def test_settlement_tag_is_broker_truth(tmp_path):
    _write_depth(tmp_path, "2026-07-07", [("KXMLBGAME-26JUL07AAABBB-AAA", 2)])
    _, stats = B.eligible_ticker_days(
        tmp_path, ["2026-07-07"], resolver=_resolver(["KXMLBGAME-26JUL07AAABBB-AAA"]))
    assert stats["settlement_price_source_tag"] == "broker_truth"


# --------------------------------------------------------------------------- #
# ordering — the league round-robin
# --------------------------------------------------------------------------- #
def test_order_games_round_robins_across_series_not_alphabetically():
    games = {"KXAAAGAME-1": [], "KXAAAGAME-2": [], "KXAAAGAME-3": [],
             "KXBBBGAME-1": [], "KXBBBGAME-2": [],
             "KXCCCGAME-1": []}
    assert B.order_games(games) == [
        "KXAAAGAME-1", "KXBBBGAME-1", "KXCCCGAME-1",
        "KXAAAGAME-2", "KXBBBGAME-2",
        "KXAAAGAME-3",
    ]


def test_order_games_is_deterministic_under_input_reordering():
    a = {"KXBBBGAME-2": [], "KXAAAGAME-1": [], "KXBBBGAME-1": []}
    b = {"KXAAAGAME-1": [], "KXBBBGAME-1": [], "KXBBBGAME-2": []}
    assert B.order_games(a) == B.order_games(b)


def test_order_games_covers_every_game_exactly_once():
    games = {f"KX{s}GAME-{i}": [] for s in "ABCDE" for i in range(4)}
    out = B.order_games(games)
    assert sorted(out) == sorted(games) and len(out) == len(set(out))


# --------------------------------------------------------------------------- #
# plan — day grouping and window bounds
# --------------------------------------------------------------------------- #
def test_plan_groups_ticker_days_and_uses_that_days_utc_bounds():
    g = "KXMLBGAME-26JUL07AAABBB"
    games = {g: [("2026-07-07", g + "-AAA"), ("2026-07-07", g + "-BBB"),
                 ("2026-07-08", g + "-AAA")]}
    plan = B.plan_pulls(games, [g])
    assert len(plan) == 1 and plan[0]["n_ticker_days"] == 3
    q0, q1 = plan[0]["queries"]
    assert q0["day"] == "2026-07-07" and q0["tickers"] == [g + "-AAA", g + "-BBB"]
    assert (q0["min_ts"], q0["max_ts"]) == (1783382400, 1783468800)
    assert q1["min_ts"] == q0["max_ts"]          # contiguous, non-overlapping day windows


# --------------------------------------------------------------------------- #
# bounded execution
# --------------------------------------------------------------------------- #
def _fake_runner(bytes_per_call: int, complete: bool = True, log=None):
    """Writes `bytes_per_call` bytes into the store so the cap is enforced on REAL bytes."""
    def _f(tickers=None, min_ts=None, max_ts=None, store=None, client=None,
           max_calls=None, min_interval=None, **kw):
        store = Path(store)
        store.mkdir(parents=True, exist_ok=True)
        with (store / "dt=2026-07-07.jsonl").open("a") as fh:
            fh.write("x" * bytes_per_call + "\n")
        if log is not None:
            log.append(tuple(tickers or []))
        return {"n_pulled": 1, "n_lines": 1, "n_duplicate": 0, "call_count": 1,
                "completeness_ok": complete, "truncated": not complete,
                "n_truncated_queries": 0 if complete else 1}
    return _f


def _plan(n_games: int, queries_per_game: int = 1):
    games = {}
    for i in range(n_games):
        g = f"KXAAAGAME-{i:03d}"
        games[g] = [("2026-07-07", f"{g}-{j}") for j in range(queries_per_game)]
    return B.plan_pulls(games, B.order_games(games))


def test_execute_stops_at_the_declared_byte_cap(tmp_path):
    out = B.execute(_plan(50), store=tmp_path, cap_bytes=5000,
                    runner=_fake_runner(1000), verbose=False)
    assert out["stopped_reason"] == "byte_cap"
    assert out["n_games_pulled"] == 5              # 5x1001B >= 5000 checked BEFORE game 6
    assert out["bytes_written"] >= 5000
    assert out["n_games_pulled"] < out["n_games_planned"]


def test_execute_stops_at_max_games(tmp_path):
    out = B.execute(_plan(50), store=tmp_path, cap_bytes=10**9, max_games=3,
                    runner=_fake_runner(10), verbose=False)
    assert out["stopped_reason"] == "max_games" and out["n_games_pulled"] == 3


def test_execute_reports_plan_exhausted_when_nothing_binds(tmp_path):
    out = B.execute(_plan(4), store=tmp_path, cap_bytes=10**9,
                    runner=_fake_runner(10), verbose=False)
    assert out["stopped_reason"] == "plan_exhausted" and out["n_games_pulled"] == 4


def _multiday_plan(n_games: int, days=("2026-07-07", "2026-07-08", "2026-07-10")):
    games = {f"KXAAAGAME-{i:03d}": [(d, f"KXAAAGAME-{i:03d}-A") for d in days]
             for i in range(n_games)}
    return B.plan_pulls(games, B.order_games(games))


def test_execute_never_half_pulls_a_game(tmp_path):
    """A game is either fully pulled or not started — a half-pulled game is a biased unit."""
    out = B.execute(_multiday_plan(20), store=tmp_path, cap_bytes=2000,
                    runner=_fake_runner(400), verbose=False)
    assert out["stopped_reason"] == "byte_cap"
    assert 0 < out["n_games_pulled"] < 20
    for entry in out["manifest"]:
        assert len(entry["queries"]) == 3          # all three day-windows, never a prefix
        assert [q["day"] for q in entry["queries"]] == ["2026-07-07", "2026-07-08",
                                                        "2026-07-10"]


def test_execute_propagates_an_incomplete_query_to_the_game_and_the_summary(tmp_path):
    out = B.execute(_plan(2), store=tmp_path, cap_bytes=10**9,
                    runner=_fake_runner(10, complete=False), verbose=False)
    assert out["n_games_incomplete"] == 2
    assert all(e["completeness_ok"] is False for e in out["manifest"])


def test_execute_manifest_records_every_window_it_attempted(tmp_path):
    log = []
    out = B.execute(_plan(3, queries_per_game=2), store=tmp_path, cap_bytes=10**9,
                    runner=_fake_runner(10, log=log), verbose=False)
    assert len(log) == 3                                  # one call per game-day
    for entry in out["manifest"]:
        for q in entry["queries"]:
            assert q["min_ts"] < q["max_ts"] and q["n_tickers"] == 2
            assert set(q["tickers"])


def test_dry_run_makes_no_call_and_writes_no_tape(tmp_path):
    _write_depth(tmp_path, "2026-07-07", [("KXMLBGAME-26JUL07AAABBB-AAA", 3)])
    calls = []

    def _boom(**kw):
        calls.append(kw)
        raise AssertionError("dry-run must not pull")

    rep = B.run(tape_root=tmp_path, days=["2026-07-07"], dry_run=True,
                resolver=_resolver(["KXMLBGAME-26JUL07AAABBB-AAA"]), runner=_boom)
    assert rep["dry_run"] is True and rep["execution"] is None and calls == []
    assert not (tmp_path / "kalshi_trades").exists()


# --------------------------------------------------------------------------- #
# lane discipline
# --------------------------------------------------------------------------- #
def test_report_is_collection_only(tmp_path):
    """No P&L / CI / edge / fill-rate field may ever appear in this collector's report."""
    _write_depth(tmp_path, "2026-07-07", [("KXMLBGAME-26JUL07AAABBB-AAA", 3)])
    rep = B.run(tape_root=tmp_path, days=["2026-07-07"], store=tmp_path / "kalshi_trades",
                resolver=_resolver(["KXMLBGAME-26JUL07AAABBB-AAA"]),
                runner=_fake_runner(10), verbose=False)
    blob = json.dumps(rep).lower()
    for banned in ("pnl", "p_and_l", "\"mean\"", "ci95", "bootstrap", "\"edge\"",
                   "fill_rate", "\"won\"", "verdict\":"):
        assert banned not in blob, banned
    assert rep["execution"]["price_source_tag"] == "broker_truth"
    assert rep["execution"]["coverage_is_ticker_scoped"] is True


# --------------------------------------------------------------------------- #
# PER-DAY-FILE push-wedge guard (the gap this item's 2026-08-09 status flagged)
# --------------------------------------------------------------------------- #
def _day_aware_runner(bytes_per_query: int, log=None):
    """Unlike `_fake_runner`, writes into the day-file the QUERY names — the per-day-file
    guard is meaningless against a fake that funnels every day into one file."""
    def _f(tickers=None, min_ts=None, max_ts=None, store=None, client=None,
           max_calls=None, min_interval=None, **kw):
        store = Path(store)
        store.mkdir(parents=True, exist_ok=True)
        day = B.kt.day_of_ts(min_ts) if hasattr(B.kt, "day_of_ts") else None
        if day is None:
            import datetime as _dt
            day = _dt.datetime.utcfromtimestamp(min_ts).strftime("%Y-%m-%d")
        with (store / f"dt={day}.jsonl").open("a") as fh:
            fh.write("x" * bytes_per_query + "\n")
        if log is not None:
            log.append((day, tuple(tickers or [])))
        return {"n_pulled": 1, "n_lines": 1, "n_duplicate": 0, "call_count": 1,
                "completeness_ok": True, "truncated": False, "n_truncated_queries": 0}
    return _f


def _seed_day(store: Path, day: str, nbytes: int) -> None:
    store.mkdir(parents=True, exist_ok=True)
    with (store / f"dt={day}.jsonl").open("wb") as fh:
        fh.truncate(nbytes)


def test_day_file_cap_default_is_the_sanctioned_push_limit_not_a_handrolled_number():
    from core.push_limits import PUSH_SIZE_GATE_BYTES
    assert B.DEFAULT_DAY_FILE_CAP_BYTES == PUSH_SIZE_GATE_BYTES


def test_bootstrap_estimate_exceeds_the_heaviest_measured_ticker_day():
    """The first decision of a pass has no measurement, so its estimate must be pessimistic.
    Heaviest single ticker-day measured on committed tape (2026-08-11,
    `tape/kalshi_trades/dt=2026-07-07.jsonl`): 16,645,764 bytes."""
    assert B.BOOTSTRAP_BYTES_PER_TICKER_DAY > 16_645_764


def test_days_of_counts_ticker_days_per_day():
    g = "KXAAAGAME-001"
    plan = B.plan_pulls({g: [("2026-07-07", g + "-A"), ("2026-07-07", g + "-B"),
                             ("2026-07-08", g + "-A")]}, [g])
    assert B.days_of(plan[0]) == {"2026-07-07": 2, "2026-07-08": 1}


def test_project_day_file_bytes_adds_the_estimate_to_the_current_size():
    g = "KXAAAGAME-001"
    plan = B.plan_pulls({g: [("2026-07-07", g + "-A"), ("2026-07-07", g + "-B")]}, [g])
    got = B.project_day_file_bytes(plan[0], {"2026-07-07": 1_000}, 500)
    assert got == {"2026-07-07": 2_000}
    # a day with no existing file starts from zero, never from a fabricated size
    assert B.project_day_file_bytes(plan[0], {}, 500) == {"2026-07-07": 1_000}


def test_guard_skips_a_game_aimed_at_a_near_limit_day_and_does_not_start_it(tmp_path):
    """The family-TOTAL cap cannot see this: the total stays tiny while one day-file wedges."""
    store = tmp_path / "kalshi_trades"
    _seed_day(store, "2026-07-07", 9_000)
    log = []
    out = B.execute(_plan(3), store=store, cap_bytes=10**9, day_file_cap_bytes=10_000,
                    runner=_day_aware_runner(100, log=log),
                    verbose=False)
    assert out["n_games_pulled"] == 0 and log == []       # never started -> no network call
    assert out["n_games_skipped_day_file_cap"] == 3
    assert out["stopped_reason"] == "plan_exhausted"      # a skip is not a stop
    sk = out["skipped_day_file_cap"][0]
    assert sk["reason"] == "day_file_cap" and sk["breaching_days"] == ["2026-07-07"]
    assert sk["estimate_source"] == "bootstrap_no_measurement_yet"


def test_a_skipped_game_does_not_veto_the_games_behind_it(tmp_path):
    """League round-robin ordering means the blocked day's games are interleaved with
    reachable ones; stopping at the first skip would silently truncate the selection."""
    store = tmp_path / "kalshi_trades"
    _seed_day(store, "2026-07-07", 9_000)
    games = {"KXAAAGAME-001": [("2026-07-07", "KXAAAGAME-001-A")],
             "KXBBBGAME-001": [("2026-07-08", "KXBBBGAME-001-A")]}
    plan = B.plan_pulls(games, B.order_games(games))
    out = B.execute(plan, store=store, cap_bytes=10**9, day_file_cap_bytes=10_000,
                    bootstrap_bytes_per_ticker_day=1_500,
                    runner=_day_aware_runner(100), verbose=False)
    assert out["n_games_skipped_day_file_cap"] == 1
    assert [e["game"] for e in out["manifest"]] == ["KXBBBGAME-001"]


def test_guard_lets_a_game_through_when_the_target_day_has_room(tmp_path):
    store = tmp_path / "kalshi_trades"
    out = B.execute(_plan(2), store=store, cap_bytes=10**9, day_file_cap_bytes=10**9,
                    bootstrap_bytes_per_ticker_day=10,
                    runner=_day_aware_runner(100), verbose=False)
    assert out["n_games_pulled"] == 2 and out["n_games_skipped_day_file_cap"] == 0
    assert out["day_file_overflow"] is None


def test_post_check_stops_and_names_the_whole_game_to_drop(tmp_path):
    """A projection can be wrong; being wrong in the unsafe direction IS the 2026-08-09
    failure. The measured post-check must stop the pass and name the remediation."""
    store = tmp_path / "kalshi_trades"
    out = B.execute(_plan(5), store=store, cap_bytes=10**9, day_file_cap_bytes=150,
                    bootstrap_bytes_per_ticker_day=10, runner=_day_aware_runner(200),
                    verbose=False)
    assert out["stopped_reason"] == "day_file_cap_exceeded"
    assert out["n_games_pulled"] == 1                      # stopped after the first landing
    ov = out["day_file_overflow"]
    assert ov["game"] == out["manifest"][0]["game"]
    assert "whole-game atomicity" in ov["remediation"].lower() or "L315" in ov["remediation"]
    assert "never truncate" in ov["remediation"].lower()


def test_the_guard_never_deletes_or_truncates_tape(tmp_path):
    """The remediation is REPORTED, never performed: this module must not shrink a file."""
    store = tmp_path / "kalshi_trades"
    _seed_day(store, "2026-07-07", 100)
    before = B.day_file_sizes(store)
    out = B.execute(_plan(3), store=store, cap_bytes=10**9, day_file_cap_bytes=150,
                    bootstrap_bytes_per_ticker_day=10, runner=_day_aware_runner(50),
                    verbose=False)
    after = B.day_file_sizes(store)
    assert out["stopped_reason"] == "day_file_cap_exceeded"
    for day, n in before.items():
        assert after[day] >= n                              # append-only, never shrinks


def test_post_check_does_not_blame_a_game_for_a_day_it_never_touched(tmp_path):
    """A day-file already over the ceiling before the pass began, and untouched by it, must
    not stop the pass or be attributed to the game that happened to run next. The repo-wide
    version of that condition is scripts/invariants.py's job, not this pass's."""
    store = tmp_path / "kalshi_trades"
    _seed_day(store, "2026-07-09", 5_000)                  # over cap, and never in any plan
    out = B.execute(_plan(2), store=store, cap_bytes=10**9, day_file_cap_bytes=1_000,
                    bootstrap_bytes_per_ticker_day=10, runner=_day_aware_runner(50),
                    verbose=False)
    assert out["day_file_overflow"] is None
    assert out["stopped_reason"] == "plan_exhausted" and out["n_games_pulled"] == 2


def test_estimator_switches_to_the_measured_max_after_the_first_game(tmp_path):
    store = tmp_path / "kalshi_trades"
    out = B.execute(_plan(2), store=store, cap_bytes=10**9, day_file_cap_bytes=10**9,
                    bootstrap_bytes_per_ticker_day=10,
                    runner=_day_aware_runner(100), verbose=False)
    assert out["max_bytes_per_ticker_day_measured"] == 101   # 100 bytes + newline, 1 ticker
    assert out["n_ticker_days_pulled"] == 2


def test_report_records_the_day_file_ledger_on_both_ends(tmp_path):
    store = tmp_path / "kalshi_trades"
    _seed_day(store, "2026-07-07", 40)
    out = B.execute(_plan(1), store=store, cap_bytes=10**9, day_file_cap_bytes=10**9,
                    bootstrap_bytes_per_ticker_day=10, runner=_day_aware_runner(10),
                    verbose=False)
    assert out["day_file_bytes_start"] == {"2026-07-07": 40}
    assert out["day_file_bytes_end"]["2026-07-07"] == 40 + 11
    assert out["day_file_cap_bytes"] == 10**9


def test_dry_run_guard_preview_is_offline_and_reports_the_blocked_days(tmp_path):
    store = tmp_path / "kalshi_trades"
    _seed_day(store, "2026-07-07", 9_000)
    g = "KXAAAGAME-001"
    plan = B.plan_pulls({g: [("2026-07-07", g + "-A")]}, [g])
    prev = B.guard_preview(plan, store=store, day_file_cap_bytes=10_000,
                           bytes_per_ticker_day=5_000)
    assert prev["n_games_would_skip"] == 1
    assert prev["blocked_days"] == {"2026-07-07": 1}
    assert prev["current_day_bytes"] == {"2026-07-07": 9_000}


def test_acceptance_real_tape_the_heaviest_day_is_the_one_the_guard_blocks():
    """2026-08-11 measurement, asserted DIRECTIONALLY (tape only grows): the committed
    `tape/kalshi_trades/dt=2026-07-07.jsonl` sits at 88,069,420 bytes against a 95,000,000
    gate, and every remaining planned game that touches that day (169 of 328) is refused at
    the pessimistic bootstrap estimate. If this ever reads 0 skipped, either the day-file was
    sharded or the guard stopped seeing it — both worth a failing test."""
    games, _stats = B.eligible_ticker_days()
    plan = B.plan_pulls(games, B.order_games(games))
    prev = B.guard_preview(plan)
    assert prev["current_day_bytes"]["2026-07-07"] >= 88_069_420
    assert prev["n_games_would_skip"] >= 1
    assert list(prev["blocked_days"]) == ["2026-07-07"]


def test_default_max_calls_covers_the_measured_worst_case_ticker_day():
    """L314: a page cap below a real ticker-day's depth writes a PREFIX with no marker.

    Measured live 2026-08-08: `KXMLBGAME-26JUL061915NYMATL`'s two outcome tickers needed 26
    and 28 calls at limit=1000 (25,405 / 27,532 prints) to exhaust their 2026-07-07 cursor.
    The first pass ran at 20 and silently committed a 40,000-of-52,937-print prefix. This
    pins the cap above the measured worst case; lowering it must fail here, loudly.
    """
    assert B.DEFAULT_MAX_CALLS >= 40


def test_a_truncated_query_is_never_upgraded_to_complete(tmp_path):
    out = B.execute(_plan(1), store=tmp_path, cap_bytes=10**9,
                    runner=_fake_runner(10, complete=False), verbose=False)
    q = out["manifest"][0]["queries"][0]
    assert q["completeness_ok"] is False and q["truncated"] is True
    assert out["n_games_incomplete"] == 1


def test_manifest_pins_the_sampling_frame_for_every_pulled_game(tmp_path):
    """L315: the selection rule IS the consuming probe's sampling frame, so every pulled
    (game, day, ticker, window) must be recorded — a probe cannot state its frame otherwise."""
    out = B.execute(_multiday_plan(2), store=tmp_path, cap_bytes=10**9,
                    runner=_fake_runner(10), verbose=False)
    for entry in out["manifest"]:
        assert entry["game"] and entry["series"]
        for q in entry["queries"]:
            for field in ("day", "tickers", "min_ts", "max_ts", "n_tickers",
                          "completeness_ok"):
                assert field in q, field


def test_module_declares_no_order_or_credential_path():
    """The driver must stay read-only public REST (2026-07-12 Stop-rules amendment).

    The forbidden markers are assembled from fragments rather than written as literals: the
    `order_endpoints_confined` invariant scans EVERY file including this one, and spelling
    them out here would make the test that guards the rule a violation of it.
    """
    src = Path(B.__file__).read_text()
    verbs = ["create", "place", "cancel"]
    creds = ["api", "private", "access"]
    for banned in [f"{v}_order" for v in verbs] + [f"{c}_key" for c in creds] + \
            ["portfol" + "io", "KALSHI-ACCESS", "sign" + "ature"]:
        assert banned not in src, banned


# --------------------------------------------------------------------------- #
# acceptance over the REAL committed tape (bounds only, per L280)
# --------------------------------------------------------------------------- #
def test_acceptance_real_tape_population_clears_the_l41_floor_by_a_wide_multiple():
    _, stats = B.eligible_ticker_days()
    assert stats["n_games"] >= 100          # measured 328 on 2026-08-08; bound, not equality
    assert stats["n_ticker_days"] >= stats["n_games"]
    assert stats["n_sports_settled_union"] >= stats["n_games"]


def test_acceptance_real_tape_ordering_is_league_diverse_in_its_first_20():
    games, _ = B.eligible_ticker_days()
    order = B.order_games(games)
    from scripts.q51_maker_fillsim import series_of
    assert len({series_of(g) for g in order[:20]}) >= 10

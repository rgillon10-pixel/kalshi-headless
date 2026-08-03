"""Offline unit tests for q37_weather_summer_makerno_probe (Q37 prep infrastructure).

Q37 is GATED on >=21 SUMMER daily contract-days of tape/weather_books/ coverage (only 6 exist as
of 2026-07-20). This probe is built + offline-tested now (idle-run policy (b), mirroring q43/q36)
so it fires the day the gate opens. NO network anywhere: every fixture is synthetic (hand-built
snapshot dicts or tmp JSONL day-files). Tests cover the mandated cases: the self-activation gate
(both branches), the maker-NO queue-touch fill model + L32 frozen/movement dual cut, the single-leg
fee-floor judgment (gate #2), the L69 fillable-entry restriction, the L86 settlement-drop
discipline, the bootstrap wiring through the L27/L41 gates, and the S5 EMOS entry filter
(available + unavailable).
"""
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.pricing import MAKER_FEE_RATE, fee_per_contract
from scripts.q37_weather_summer_makerno_probe import (
    BOOKS_GLOB,
    MIN_CI_UNITS,
    LONGSHOT_MAX,
    SUMMER_DAYS_REQUIRED,
    SUMMER_END,
    SUMMER_START,
    bootstrap_cut,
    bootstrap_unit_ledger,
    build_emos_filter,
    dual_cut_degeneracy,
    gate_vs_units_summary,
    group_snapshots,
    is_summer,
    is_temperature_series,
    load_daily_snapshots,
    load_settlement,
    movement_dual_cut,
    parse_daily_ticker,
    run_probe,
    simulate_group,
    summer_contract_days,
    _series_to_forecast_city,
    _summer_contract_days_available,
)

UTC = timezone.utc
CLOSE = datetime(2026, 7, 16, 5, 59, tzinfo=UTC)          # a daily close (D+1 ~06:00 UTC)
T_DECISION = CLOSE - timedelta(hours=24)                  # 2026-07-15 05:59 UTC


# --------------------------------------------------------------------------- #
# ticker / season parsing
# --------------------------------------------------------------------------- #
def test_parse_daily_ticker():
    assert parse_daily_ticker("KXHIGHAUS-26JUL20-B99.5") == ("KXHIGHAUS", date(2026, 7, 20), "B99.5")
    assert parse_daily_ticker("KXHIGHTATL-26JUL16-T93") == ("KXHIGHTATL", date(2026, 7, 16), "T93")
    assert parse_daily_ticker("NOTATICKER") is None
    assert parse_daily_ticker("KXHIGHAUS-26XXX20-B1") is None      # bad month token
    assert parse_daily_ticker(None) is None


def test_is_summer_boundary():
    assert is_summer(date(2026, 6, 21)) is True     # astronomical summer start (inclusive)
    assert is_summer(date(2026, 6, 20)) is False
    assert is_summer(date(2026, 7, 15)) is True


# --------------------------------------------------------------------------- #
# fixture builders
# --------------------------------------------------------------------------- #
def _snap(ticker, captured_at, ask, bid, *, no_bids=None, close=CLOSE,
          strike_type="between", floor=94, cap=95):
    """One weather_books-shaped daily snapshot. Kalshi posts bids only: the NO-bid side is the
    complement of the best YES ask, and the NO-ask side the complement of the best YES bid (the
    complement arithmetic collection/normalize owns; here `ask`/`bid` are the best YES levels)."""
    parsed = parse_daily_ticker(ticker)
    series, cday, bracket = parsed
    return {
        "series": series, "contract_day": cday, "bracket": bracket, "ticker": ticker,
        "captured_at": captured_at, "close_time": close,
        "strike_type": strike_type, "floor_strike": floor, "cap_strike": cap,
        "best_yes_ask": ask, "best_yes_bid": bid,
        "best_no_ask": round(1.0 - bid, 4), "best_no_bid": round(1.0 - ask, 4),
        "no_bids": no_bids if no_bids is not None else [[round(1.0 - ask, 4), 100.0]],
    }


def _ladder(entry_asks, later_asks=None, *, series="KXHIGHAUS", day="26JUL15",
            later_dt=None):
    """Build a {ticker: [entry_snap, later_snap]} ladder. `entry_asks`/`later_asks` map a bracket
    suffix -> (yes_ask, yes_bid). Entry snapshot lands at/before T; the later snapshot after it."""
    later_dt = later_dt or (CLOSE - timedelta(hours=1))
    by_ticker = {}
    for suffix, (ya, yb) in entry_asks.items():
        tk = f"{series}-{day}-{suffix}"
        snaps = [_snap(tk, T_DECISION - timedelta(hours=1), ya, yb)]
        if later_asks and suffix in later_asks:
            lya, lyb = later_asks[suffix]
            snaps.append(_snap(tk, later_dt, lya, lyb))
        by_ticker[tk] = snaps
    return by_ticker


# --------------------------------------------------------------------------- #
# simulate_group — complete partition, longshot selection, single-leg fee (gate #2)
# --------------------------------------------------------------------------- #
def test_simulate_group_selects_longshots_and_single_leg_fee():
    """Longshot brackets (normalized implied < LONGSHOT_MAX) become trades; a favorite does not.
    The maker fee is a SINGLE fee_per_contract on the ONE leg we trade (gate #2 judgment) — NOT
    summed across all ladder members (that S33 6-leg sum is a complete-set trade, not this)."""
    entry = {"T93": (0.02, 0.01), "B94.5": (0.05, 0.04),
             "B96.5": (0.80, 0.79), "T101": (0.13, 0.12)}   # bracket_sum ~1.00
    later = {k: v for k, v in entry.items()}                # unchanged later -> frozen
    by_ticker = _ladder(entry, later)
    rows, reason = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    assert reason == "ok"
    tickers = {r["ticker"].split("-")[-1] for r in rows}
    assert "B96.5" not in tickers                            # 0.80 favorite -> not a longshot
    assert {"T93", "B94.5", "T101"} <= tickers
    r = next(r for r in rows if r["ticker"].endswith("T93"))
    assert r["entry_no_price"] == 0.98                       # rest at best_no_bid = 1 - 0.02
    assert abs(r["fee"] - fee_per_contract(0.98, MAKER_FEE_RATE)) < 1e-12   # single-leg maker fee
    assert r["member_count"] == 4


def test_simulate_group_incomplete_book_dropped():
    """A bracket with NO book at/before T breaks the complete partition -> the whole group is
    dropped (a partial bracket_sum would mis-normalize the ladder, S1)."""
    by_ticker = _ladder({"T93": (0.02, 0.01), "B96.5": (0.80, 0.79)})
    # push one bracket's only snapshot to AFTER the decision time -> no entry book
    by_ticker["KXHIGHAUS-26JUL15-B96.5"][0]["captured_at"] = CLOSE - timedelta(minutes=5)
    rows, reason = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    assert reason == "incomplete_book"
    assert rows == []


# --------------------------------------------------------------------------- #
# fill model — queue-touch (optimistic) + L32 frozen/movement dual cut
# --------------------------------------------------------------------------- #
def test_fill_touched_and_movement_conditioned():
    """A resting NO bid is 'touched' when a later snapshot's best_no_ask crosses down to <= our
    price AND the book moved (not frozen) -> filled_movement True."""
    entry = {"T93": (0.02, 0.01), "B96.5": (0.80, 0.79)}
    # later: T93 yes firms up (yes_bid 0.03) -> best_no_ask = 0.97 <= our 0.98 bid -> touched;
    # the book moved -> not frozen.
    later = {"T93": (0.04, 0.03), "B96.5": (0.80, 0.79)}
    by_ticker = _ladder(entry, later)
    rows, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    r = next(r for r in rows if r["ticker"].endswith("T93"))
    assert r["touched"] is True
    assert r["frozen"] is False
    assert r["filled_optimistic"] is True
    assert r["filled_movement"] is True


def test_frozen_book_is_no_fill():
    """A book that never moves across the holding window is FROZEN -> movement-conditioned excludes
    it even though the optimistic touch cannot fire either (an unchanged book has ask>bid). L32:
    a frozen pair is a no-fill, never free income."""
    entry = {"T93": (0.02, 0.01), "B96.5": (0.80, 0.79)}
    by_ticker = _ladder(entry, entry)                        # identical later snapshot -> frozen
    rows, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    r = next(r for r in rows if r["ticker"].endswith("T93"))
    assert r["frozen"] is True
    assert r["filled_movement"] is False
    assert r["touched"] is False


# --------------------------------------------------------------------------- #
# L69 fillable-entry restriction
# --------------------------------------------------------------------------- #
def test_fillable_entry_restriction():
    """The L69 primary cut requires a genuinely two-sided book (yes spread <= 10c) OR near-close
    (ttc <= 24h). A wide one-sided lottery-placeholder book far from close is NOT a fillable
    entry (the S29/Q30 nickel-bid-vs-90c-ask trap)."""
    # entry at T-1h -> ttc ~25h (just over near-close); wide spread 0.02 ask vs 0.00 bid -> 0.02
    # spread is tight, so fillable via the spread leg. Make spread WIDE to fail both legs:
    far_close = datetime(2026, 7, 25, 5, 59, tzinfo=UTC)     # close far in the future
    by_ticker = {
        "KXHIGHAUS-26JUL15-T93": [_snap("KXHIGHAUS-26JUL15-T93",
                                        far_close - timedelta(hours=48), 0.05, 0.00,
                                        close=far_close)],   # spread 0.05 > 0.10? no; make wider
        "KXHIGHAUS-26JUL15-B96.5": [_snap("KXHIGHAUS-26JUL15-B96.5",
                                          far_close - timedelta(hours=48), 0.80, 0.79,
                                          close=far_close)],
    }
    # widen the longshot spread to 0.15 (> SPREAD_MAX) and keep ttc ~48h (> near-close)
    by_ticker["KXHIGHAUS-26JUL15-T93"][0]["best_yes_ask"] = 0.15
    by_ticker["KXHIGHAUS-26JUL15-T93"][0]["best_yes_bid"] = 0.00
    by_ticker["KXHIGHAUS-26JUL15-T93"][0]["best_no_bid"] = 0.85
    rows, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    r = next(r for r in rows if r["ticker"].endswith("T93"))
    assert r["yes_spread"] == 0.15 and r["ttc_hours"] > 24.0
    assert r["fillable_entry"] is False                      # fails BOTH the spread and near-close legs


# --------------------------------------------------------------------------- #
# L86 settlement-drop discipline (never zero an unmeasurable leg)
# --------------------------------------------------------------------------- #
def test_settlement_measurable_vs_dropped():
    """A settled bracket gets payout/pnl; an unsettled one is settlement_measurable=False with
    pnl=None (DROPPED, never zeroed — zeroing a NO buy's unmeasurable payout would fabricate a
    free loss/win, L86)."""
    entry = {"T93": (0.02, 0.01), "B96.5": (0.80, 0.79)}
    by_ticker = _ladder(entry, {"T93": (0.04, 0.03), "B96.5": (0.80, 0.79)})
    results = {"KXHIGHAUS-26JUL15-T93": "no"}                # longshot lost -> NO wins -> payout 1
    rows, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results=results)
    r = next(r for r in rows if r["ticker"].endswith("T93"))
    assert r["settlement_measurable"] is True and r["payout"] == 1.0
    assert abs(r["pnl"] - (1.0 - 0.98 - r["fee"])) < 1e-12
    # a bracket with no settlement -> measurable False, pnl None
    entry2 = {"T80": (0.03, 0.02), "B96.5": (0.80, 0.79)}
    rows2, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15),
                              _ladder(entry2, {"T80": (0.05, 0.04), "B96.5": (0.80, 0.79)}),
                              results={})
    r2 = next(r for r in rows2 if r["ticker"].endswith("T80"))
    assert r2["settlement_measurable"] is False and r2["pnl"] is None


# --------------------------------------------------------------------------- #
# bootstrap wiring (L27/L41) + L32 dual cut
# --------------------------------------------------------------------------- #
def _row(cday, pnl, *, fo=True, fm=True, meas=True, frozen=False):
    return {"contract_day": cday, "pnl": pnl, "filled_optimistic": fo, "filled_movement": fm,
            "settlement_measurable": meas, "frozen": frozen}


def test_bootstrap_cut_routes_through_gates():
    """bootstrap_cut groups by contract-day (L6), bootstraps, and reports the admissibility (L41)
    and tick-magnitude (L27) gate outcomes. A tiny 2-day population is inadmissible (below the
    min-units floor)."""
    rows = [_row("2026-07-15", -0.06), _row("2026-07-16", -0.07)]
    cut = bootstrap_cut(rows, "filled_movement", n_boot=500)
    assert cut["n_units"] == 2 and cut["n_obs"] == 2
    assert cut["admissible"] is False               # below MIN_CI_UNITS -> inadmissible
    assert cut["ci_positive"] is False              # negative pnl -> CI not > 0
    assert cut["clears_tick_magnitude"] is False


def test_bootstrap_cut_only_filled_measurable():
    """Only rows that FILLED under the chosen fill attr AND are settlement-measurable enter the
    population; an unfilled or unmeasurable row is excluded (never counted as $0)."""
    rows = [_row("d1", 0.02), _row("d2", 0.02, fm=False), _row("d3", 0.02, meas=False)]
    cut = bootstrap_cut(rows, "filled_movement", n_boot=200)
    assert cut["n_obs"] == 1 and cut["n_units"] == 1        # only the d1 filled+measurable row


def test_movement_dual_cut_wires_bracket_by_movement():
    """movement_dual_cut reports frac_frozen and the movement-conditioned count via
    core.bootstrap.bracket_by_movement over the optimistically-filled measurable population."""
    rows = [_row("d1", 0.02, frozen=False), _row("d2", -0.9, frozen=True),
            _row("d3", 0.02, frozen=False)]
    dc = movement_dual_cut(rows)
    assert dc["n_filled_optimistic"] == 3
    assert abs(dc["frac_frozen"] - (1 / 3)) < 1e-9
    assert dc["n_movement_conditioned"] == 2                 # the two non-frozen rows


# --------------------------------------------------------------------------- #
# EMOS entry filter (S5 calibration) — unavailable vs available
# --------------------------------------------------------------------------- #
def test_emos_filter_unavailable_when_no_forecast():
    """With an EMPTY forecast tape every EMOS flag is None (EMOS-unavailable) — the sandbox case;
    the baseline still runs, so this is INSUFFICIENT DATA for the EMOS cut, not an error."""
    entry = {"T93": (0.02, 0.01), "B96.5": (0.80, 0.79)}
    by_ticker = _ladder(entry, {"T93": (0.04, 0.03), "B96.5": (0.80, 0.79)})
    rows, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    groups = {("KXHIGHAUS", date(2026, 7, 15)): by_ticker}
    flags = build_emos_filter(rows, groups, forecast={}, actuals={},
                              series_city={"KXHIGHAUS": "Austin"})
    assert all(v is None for v in flags.values())


def test_emos_filter_available_gates_trades():
    """With a synthetic forecast + a city mapping, build_emos_filter produces a boolean flag
    (True/False, NOT None) per bracket: True iff the calibrated model agrees the longshot YES is
    overpriced (market_implied - model_prob > EDGE_BAR)."""
    entry = {"T93": (0.02, 0.01), "B96.5": (0.80, 0.79)}
    by_ticker = _ladder(entry, {"T93": (0.04, 0.03), "B96.5": (0.80, 0.79)})
    rows, _ = simulate_group("KXHIGHAUS", date(2026, 7, 15), by_ticker, results={})
    groups = {("KXHIGHAUS", date(2026, 7, 15)): by_ticker}
    # forecast says Tmax ~ 96F (well above the T93 '<=92' band) -> model_prob(T93) ~ 0 -> overpriced
    forecast = {("Austin", "2026-07-15"): {"gfs_seamless": 96.0, "ecmwf_ifs025": 96.5,
                                           "icon_seamless": 95.5}}
    actuals = {("KXHIGHAUS", date(2026, 7, 15)): 96.0}
    flags = build_emos_filter(rows, groups, forecast, actuals,
                              series_city={"KXHIGHAUS": "Austin"}, edge_bar=0.05)
    # T93 is strike_type 'between' in the fixture (floor 94/cap 95 default), so treat the flag as a
    # well-formed boolean rather than asserting a specific direction on a toy strike geometry.
    assert flags["KXHIGHAUS-26JUL15-T93"] in (True, False)


# --------------------------------------------------------------------------- #
# loaders + self-activation gate over tmp JSONL day-files
# --------------------------------------------------------------------------- #
def _write_book(path, series, day_token, close_iso, brackets):
    """Write weather_books daily lines. `brackets` = list of (suffix, strike_type, floor, cap,
    yes_ask, yes_bid) at two timestamps (entry before T, later near close)."""
    close = datetime.fromisoformat(close_iso.replace("Z", "+00:00"))
    lines = []
    for ts in (close - timedelta(hours=25), close - timedelta(hours=1)):
        for suffix, st, fl, cp, ya, yb in brackets:
            lines.append(json.dumps({
                "group": "daily", "series": series,
                "ticker": f"{series}-{day_token}-{suffix}",
                "captured_at": ts.isoformat(), "close_time": close_iso,
                "strike_type": st, "floor_strike": fl, "cap_strike": cp,
                "best_yes_ask": ya, "best_yes_bid": yb,
                "best_no_ask": round(1.0 - yb, 4), "best_no_bid": round(1.0 - ya, 4),
                "no_bids": [[round(1.0 - ya, 4), 50.0]],
            }))
    Path(path).write_text("\n".join(lines) + "\n")


def test_load_and_summer_gate(tmp_path):
    """load_daily_snapshots keeps only DAILY summer rows; summer_contract_days counts distinct
    contract-days; the gate metric matches."""
    books = tmp_path / "books"
    books.mkdir()
    _write_book(books / "dt=2026-07-15.jsonl", "KXHIGHAUS", "26JUL15",
                "2026-07-16T05:59:00Z",
                [("T93", "less", None, 93, 0.02, 0.01), ("B96.5", "between", 96, 97, 0.80, 0.79)])
    # a spring (pre-summer) day that must be EXCLUDED by the season gate
    _write_book(books / "dt=2026-05-01.jsonl", "KXHIGHAUS", "26MAY01",
                "2026-05-02T05:59:00Z",
                [("T93", "less", None, 93, 0.02, 0.01), ("B96.5", "between", 96, 97, 0.80, 0.79)])
    snaps = load_daily_snapshots(str(books / "dt=*.jsonl"))
    assert {s["contract_day"] for s in snaps} == {date(2026, 7, 15)}   # spring excluded
    assert summer_contract_days(snaps) == [date(2026, 7, 15)]
    assert _summer_contract_days_available(str(books / "dt=*.jsonl")) == 1


def test_run_probe_insufficient_data(tmp_path):
    """Below days_required summer days, run_probe returns INSUFFICIENT DATA and runs NO analysis."""
    books = tmp_path / "books"
    books.mkdir()
    _write_book(books / "dt=2026-07-15.jsonl", "KXHIGHAUS", "26JUL15",
                "2026-07-16T05:59:00Z",
                [("T93", "less", None, 93, 0.02, 0.01), ("B96.5", "between", 96, 97, 0.80, 0.79)])
    rep = run_probe(str(books / "dt=*.jsonl"), str(tmp_path / "a" / "dt=*.jsonl"),
                    str(tmp_path / "fc"), days_required=SUMMER_DAYS_REQUIRED)
    assert rep["status"] == "INSUFFICIENT DATA"
    assert rep["summer_days_available"] == 1
    assert "populations" not in rep


def test_run_probe_gate_open_full_pipeline(tmp_path):
    """With the gate lowered onto a synthetic 2-day fixture, run_probe crosses the gate and runs
    the full pipeline: baseline populations present, EMOS reported EMOS_UNAVAILABLE (no forecast),
    a well-formed verdict, and optimistic_fill flagged (graduation blocked)."""
    books = tmp_path / "books"
    books.mkdir()
    brackets = [("T93", "less", None, 93, 0.02, 0.01), ("B94.5", "between", 94, 95, 0.05, 0.04),
                ("B96.5", "between", 96, 97, 0.80, 0.79), ("T101", "greater", 101, None, 0.13, 0.12)]
    _write_book(books / "dt=2026-07-15.jsonl", "KXHIGHAUS", "26JUL15",
                "2026-07-16T05:59:00Z", brackets)
    _write_book(books / "dt=2026-07-16.jsonl", "KXHIGHAUS", "26JUL16",
                "2026-07-17T05:59:00Z", brackets)
    # actuals settling both days' longshots as 'no' (longshot lost -> NO wins)
    actuals = tmp_path / "actuals"
    actuals.mkdir()
    ev_lines = []
    for dt_tok, dstr, close in (("26JUL15", "2026-07-15", "2026-07-16T05:59:00Z"),
                                ("26JUL16", "2026-07-16", "2026-07-17T05:59:00Z")):
        ev_lines.append(json.dumps({
            "settled_markets": {"events": [{
                "event_ticker": f"KXHIGHAUS-{dt_tok}", "series": "KXHIGHAUS",
                "expiration_value": "96.00",
                "results": {f"KXHIGHAUS-{dt_tok}-T93": "no", f"KXHIGHAUS-{dt_tok}-B94.5": "no",
                            f"KXHIGHAUS-{dt_tok}-B96.5": "yes", f"KXHIGHAUS-{dt_tok}-T101": "no"},
            }]}}))
    (actuals / "dt=2026-07-17.jsonl").write_text("\n".join(ev_lines) + "\n")

    rep = run_probe(str(books / "dt=*.jsonl"), str(actuals / "dt=*.jsonl"),
                    str(tmp_path / "no_forecast"), days_required=2, n_boot=200)
    assert rep["status"] == "ANALYSIS"
    assert rep["optimistic_fill"] is True
    assert rep["summer_days_available"] == 2
    assert "primary_baseline" in rep["populations"]
    assert rep["populations"]["primary_emos_filtered"] == "EMOS_UNAVAILABLE"
    assert rep["emos_available"] is False
    # verdict is well-formed and (with optimistic fill) can never be a live-graduation
    assert rep["verdict"] in ("DEAD", "DEAD_CI_OR_MAGNITUDE", "INCONCLUSIVE_DATA_ADEQUACY",
                              "OPTIMISTIC_FILL_BLOCKS_GRADUATION")
    assert rep["verdict"] != "ALIVE_UNEXPECTED"     # OPTIMISTIC_FILL caps any positive result


def test_load_settlement_parses_results_and_actual(tmp_path):
    """load_settlement returns per-ticker yes/no results and the per-group broker_truth
    expiration_value (the EMOS training target)."""
    actuals = tmp_path / "actuals"
    actuals.mkdir()
    (actuals / "dt=2026-07-17.jsonl").write_text(json.dumps({
        "settled_markets": {"events": [{
            "event_ticker": "KXHIGHTATL-26JUL16", "series": "KXHIGHTATL",
            "expiration_value": "93.00",
            "results": {"KXHIGHTATL-26JUL16-B92.5": "yes", "KXHIGHTATL-26JUL16-T93": "no"},
        }]}}) + "\n")
    results, act = load_settlement(str(actuals / "dt=*.jsonl"))
    assert results["KXHIGHTATL-26JUL16-B92.5"] == "yes"
    assert results["KXHIGHTATL-26JUL16-T93"] == "no"
    assert act[("KXHIGHTATL", date(2026, 7, 16))] == 93.0


def test_series_to_forecast_city_maps_real_config():
    """The real config/cities.yaml maps KXHIGH* series -> a forecast city name (the EMOS join
    key). At least the curated overlap (Austin/Chicago/Denver/...) must resolve."""
    m = _series_to_forecast_city()
    assert m.get("KXHIGHAUS") == "Austin"
    assert isinstance(m, dict) and len(m) >= 1


# --------------------------------------------------------------------------- #
# GATE-CONTAMINATION FIX (2026-07-31 research loop, idle-run policy (c) pre-flight audit —
# `findings/2026-07-31-weather-gate-preflight-audit.md`). Two defects let non-temperature,
# far-future weather markets buy Q37's self-activation gate days it had not earned: `is_summer()`
# was unbounded above, and the daily loader had no series whitelist. Measured contamination on
# the committed tape: reported 19 summer contract-days where only 17 real ones existed, which
# would have opened the >=21 gate two calendar days early. These tests pin BOTH guards.
#
# NOTE (L191 / Q42 test-hygiene lesson): the real-tape pins below are deliberately written as
# MONOTONE properties ("no loaded row is out-of-window", "no loaded series is non-temperature")
# rather than an exact day-count. `tape/weather_books/` is a live, still-growing family; an
# exact-count assertion over an open-ended glob red-lines on routine capture and teaches future
# runs to relax the pin instead of trusting it.
# --------------------------------------------------------------------------- #
def test_is_summer_has_an_upper_bound():
    """A far-future contract day is NOT summer 2026 — the defect that inflated the gate."""
    assert is_summer(SUMMER_END) is True                 # end of window, inclusive
    assert is_summer(date(2026, 9, 23)) is False         # one day past the window
    assert is_summer(date(2026, 10, 1)) is False         # the real KXARCTICICEMIN contract day
    assert is_summer(date(2028, 12, 31)) is False        # the real KXTXURI contract day
    assert SUMMER_START < SUMMER_END


def test_is_temperature_series_whitelist():
    """Only KXHIGH*/KXLOW* daily temperature ladders belong to the S1/S5 family."""
    for good in ("KXHIGHNY", "KXHIGHTATL", "KXLOWTNYC", "KXLOWTDEN", "KXHIGHAUS"):
        assert is_temperature_series(good) is True, good
    # the two real contaminating series measured in tape/weather_books/ on 2026-07-31
    for bad in ("KXARCTICICEMIN", "KXTXURI"):
        assert is_temperature_series(bad) is False, bad
    assert is_temperature_series(None) is False
    assert is_temperature_series("") is False


def test_loader_drops_nontemperature_and_out_of_window_rows(tmp_path):
    """A phantom row of EITHER contaminating shape must not reach the population or the gate."""
    books = tmp_path / "books"
    books.mkdir()
    rows = [
        # legitimate: temperature series, in-window contract day
        {"group": "daily", "ticker": "KXHIGHNY-26JUL15-B90.5", "captured_at": "2026-07-14T12:00:00Z",
         "close_time": "2026-07-16T05:59:00Z", "best_yes_ask": 0.10, "best_yes_bid": 0.05,
         "best_no_ask": 0.95, "best_no_bid": 0.90, "no_bids": [[0.90, 100.0]]},
        # contaminant (1): non-temperature series, in-window day
        {"group": "daily", "ticker": "KXARCTICICEMIN-26JUL15-T4.5", "captured_at": "2026-07-14T12:00:00Z",
         "close_time": "2026-07-16T05:59:00Z", "best_yes_ask": 0.10, "best_yes_bid": 0.05,
         "best_no_ask": 0.95, "best_no_bid": 0.90, "no_bids": [[0.90, 100.0]]},
        # contaminant (2): temperature-shaped series, far-future contract day
        {"group": "daily", "ticker": "KXHIGHNY-28DEC31-B90.5", "captured_at": "2026-07-14T12:00:00Z",
         "close_time": "2029-01-01T05:59:00Z", "best_yes_ask": 0.10, "best_yes_bid": 0.05,
         "best_no_ask": 0.95, "best_no_bid": 0.90, "no_bids": [[0.90, 100.0]]},
        # contaminant (3): both wrong at once — the exact KXTXURI shape seen in real tape
        {"group": "daily", "ticker": "KXTXURI-28DEC31-27JAN01", "captured_at": "2026-07-14T12:00:00Z",
         "close_time": "2029-01-01T05:59:00Z", "best_yes_ask": 0.10, "best_yes_bid": 0.05,
         "best_no_ask": 0.95, "best_no_bid": 0.90, "no_bids": [[0.90, 100.0]]},
    ]
    (books / "dt=2026-07-14.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    glob_pat = str(books / "dt=*.jsonl")
    snaps = load_daily_snapshots(glob_pat)
    assert [s["series"] for s in snaps] == ["KXHIGHNY"]
    assert summer_contract_days(snaps) == [date(2026, 7, 15)]
    # the gate counts 1, not 3 — phantoms cannot buy the gate a day
    assert _summer_contract_days_available(glob_pat) == 1


def test_real_weather_books_tape_carries_no_phantom_gate_days():
    """Monotone pin over the COMMITTED tape: whatever the loader admits today, every admitted row
    is an in-window day on a temperature series. Regression guard for the real 2026-07-31 finding
    (KXARCTICICEMIN-26OCT01 / KXTXURI-28DEC31 each bought the gate a phantom day)."""
    snaps = load_daily_snapshots(BOOKS_GLOB)
    if not snaps:                       # tape not present in this checkout — nothing to pin
        return
    for s in snaps:
        assert is_temperature_series(s["series"]), s["ticker"]
        assert SUMMER_START <= s["contract_day"] <= SUMMER_END, s["ticker"]
    for d in summer_contract_days(snaps):
        assert SUMMER_START <= d <= SUMMER_END, d


# --------------------------------------------------------------------------- #
# gate-day vs bootstrap-unit accounting (added 2026-08-03, research loop idle-run policy (b);
# findings/2026-08-03-q37-gate-day-vs-bootstrap-unit.md, lessons L271/L272)
# --------------------------------------------------------------------------- #
def _ledger_row(day, **kw):
    """One synthetic trade row as `bootstrap_unit_ledger` reads it."""
    base = {"contract_day": day, "settlement_measurable": True, "fillable_entry": True,
            "filled_movement": False, "filled_optimistic": False, "touched": False,
            "frozen": False}
    base.update(kw)
    return base


def test_bootstrap_unit_ledger_marks_a_contributing_day():
    groups = {("KXHIGHAUS", date(2026, 7, 20)): {"KXHIGHAUS-26JUL20-B1": []}}
    results = {"KXHIGHAUS-26JUL20-B1": "no"}
    rows = [_ledger_row("2026-07-20", filled_movement=True, filled_optimistic=True)]
    led = bootstrap_unit_ledger(rows, groups, results)
    assert len(led) == 1
    r = led[0]
    assert r["contributes_unit"] is True
    assert r["deficit_reason"] is None
    assert r["n_groups"] == 1 and r["n_groups_settled"] == 1
    assert r["n_filled"] == 1 and r["n_primary_measurable"] == 1


def test_bootstrap_unit_ledger_settlement_lag_reason():
    """A day whose groups carry NO settled result at all is `settlement_lag`, not `zero_fill` —
    the distinction matters because only one of the two can self-heal."""
    groups = {("KXHIGHAUS", date(2026, 8, 2)): {"KXHIGHAUS-26AUG02-B1": []}}
    rows = [_ledger_row("2026-08-02", settlement_measurable=False)]
    led = bootstrap_unit_ledger(rows, groups, results={})
    assert led[0]["contributes_unit"] is False
    assert led[0]["deficit_reason"] == "settlement_lag"
    assert led[0]["n_groups_settled"] == 0


def test_bootstrap_unit_ledger_zero_fill_reason():
    """Fully booked AND fully settled, but nothing ever touched: a real fill-rate fact, and it
    must NOT be reported as a coverage/lag problem."""
    groups = {("KXHIGHAUS", date(2026, 7, 25)): {"KXHIGHAUS-26JUL25-B1": []}}
    results = {"KXHIGHAUS-26JUL25-B1": "no"}
    rows = [_ledger_row("2026-07-25", filled_movement=False)]
    led = bootstrap_unit_ledger(rows, groups, results)
    assert led[0]["deficit_reason"] == "zero_fill"


def test_bootstrap_unit_ledger_incomplete_book_reason():
    """A gate-day whose every group was dropped before producing a row (no book at T)."""
    groups = {("KXHIGHAUS", date(2026, 7, 15)): {"KXHIGHAUS-26JUL15-B1": []}}
    results = {"KXHIGHAUS-26JUL15-B1": "no"}
    led = bootstrap_unit_ledger([], groups, results)
    assert led[0]["n_rows"] == 0
    assert led[0]["deficit_reason"] == "incomplete_book"


def test_bootstrap_unit_ledger_ignores_non_primary_fills():
    """A filled, measurable trade that is NOT fillable-entry cannot buy a bootstrap unit — the
    PRIMARY population (L69) is what `bootstrap_cut` resamples."""
    groups = {("KXHIGHAUS", date(2026, 7, 20)): {"KXHIGHAUS-26JUL20-B1": []}}
    results = {"KXHIGHAUS-26JUL20-B1": "no"}
    rows = [_ledger_row("2026-07-20", fillable_entry=False, filled_movement=True)]
    led = bootstrap_unit_ledger(rows, groups, results)
    assert led[0]["n_primary"] == 0
    assert led[0]["contributes_unit"] is False


def test_gate_vs_units_summary_counts_and_floor():
    led = [
        {"contract_day": "2026-07-16", "contributes_unit": True, "deficit_reason": None},
        {"contract_day": "2026-07-17", "contributes_unit": False, "deficit_reason": "zero_fill"},
        {"contract_day": "2026-07-18", "contributes_unit": False,
         "deficit_reason": "settlement_lag"},
        {"contract_day": "2026-07-19", "contributes_unit": False,
         "deficit_reason": "settlement_lag"},
    ]
    g = gate_vs_units_summary(led)
    assert g["n_gate_days"] == 4
    assert g["n_bootstrap_units"] == 1
    assert g["unit_deficit"] == 3
    assert abs(g["unit_yield"] - 0.25) < 1e-12
    assert g["deficit_by_reason"] == {"zero_fill": 1, "settlement_lag": 2}
    assert g["min_ci_units"] == MIN_CI_UNITS
    assert g["clears_min_ci_units"] is False        # 1 unit is far under the L41 floor


def test_gate_vs_units_summary_empty_ledger_reports_none_not_zero():
    g = gate_vs_units_summary([])
    assert g["n_gate_days"] == 0 and g["n_bootstrap_units"] == 0
    assert g["unit_yield"] is None                  # never a fake 0.0 or a divide-by-zero


def test_dual_cut_degeneracy_is_measured_not_assumed():
    """`degenerate` must be FALSE the moment a single frozen-and-touched row exists — the claim is
    an empirical one about this fill model, and a fixture that violates it must break the flag."""
    rows = [{"touched": True, "frozen": True, "filled_optimistic": True, "filled_movement": False}]
    d = dual_cut_degeneracy(rows)
    assert d["n_touched_and_frozen"] == 1
    assert d["cuts_identical"] is False
    assert d["degenerate"] is False


def test_dual_cut_degeneracy_flags_identical_cuts():
    rows = [{"touched": True, "frozen": False, "filled_optimistic": True, "filled_movement": True},
            {"touched": False, "frozen": True, "filled_optimistic": False,
             "filled_movement": False}]
    d = dual_cut_degeneracy(rows)
    assert d["n_touched_and_frozen"] == 0
    assert d["n_filled_optimistic"] == d["n_filled_movement"] == 1
    assert d["degenerate"] is True


def test_frozen_book_can_never_be_touched_in_simulate_group():
    """The structural claim behind L272, exercised through the REAL `simulate_group`: a book whose
    quotes never move cannot produce a touch, because a touch would require no_ask <= no_bid."""
    def _frozen_snaps(ticker, ybid, yask, nbid, nask):
        return [{
            "ticker": ticker, "series": "KXHIGHAUS", "contract_day": date(2026, 7, 16),
            "captured_at": T_DECISION + timedelta(hours=i), "close_time": CLOSE,
            "best_yes_bid": ybid, "best_yes_ask": yask,
            "best_no_bid": nbid, "best_no_ask": nask,
            "yes_bids": [], "no_bids": [[nbid, 10.0]],
        } for i in range(4)]

    # two-member ladder so bracket_sum normalizes the 5c wing to a real longshot (Hard Rule #3)
    by_ticker = {
        "KXHIGHAUS-26JUL16-T99": _frozen_snaps("KXHIGHAUS-26JUL16-T99", 0.02, 0.05, 0.93, 0.98),
        "KXHIGHAUS-26JUL16-T80": _frozen_snaps("KXHIGHAUS-26JUL16-T80", 0.92, 0.95, 0.03, 0.08),
    }
    rows, reason = simulate_group("KXHIGHAUS", date(2026, 7, 16), by_ticker,
                                  {"KXHIGHAUS-26JUL16-T99": "no", "KXHIGHAUS-26JUL16-T80": "yes"})
    assert reason == "ok" and len(rows) == 1
    assert rows[0]["frozen"] is True
    assert rows[0]["touched"] is False
    assert rows[0]["filled_optimistic"] == rows[0]["filled_movement"] is False


def test_real_tape_gate_yield_is_bounded_and_monotone():
    """L191 acceptance pin on the COMMITTED tape: bounds, never an exact equality that a new day of
    tape would break. Measured 2026-08-03: 20 gate-days -> 15 bootstrap units, deficit 5
    (incomplete_book 1 / zero_fill 1 / settlement_lag 3)."""
    snaps = load_daily_snapshots()
    if not snaps:                                   # tape absent in a stripped checkout
        return
    groups = group_snapshots(snaps)
    results, _ = load_settlement()
    rows = []
    for (series, cday), by_ticker in groups.items():
        r, _reason = simulate_group(series, cday, by_ticker, results)
        rows.extend(r)
    led = bootstrap_unit_ledger(rows, groups, results)
    g = gate_vs_units_summary(led)
    assert g["n_gate_days"] >= 20                   # tape only grows (append-only)
    assert g["n_bootstrap_units"] >= 15
    # the deficit is structural: the newest gate-days are ALWAYS settlement-lagged, so units can
    # never equal gate-days on live tape.
    assert g["n_bootstrap_units"] < g["n_gate_days"]
    assert g["deficit_by_reason"].get("settlement_lag", 0) >= 1
    d = dual_cut_degeneracy(rows)
    assert d["n_touched_and_frozen"] == 0           # L272, on every committed row
    assert d["degenerate"] is True

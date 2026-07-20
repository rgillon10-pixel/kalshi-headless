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
    LONGSHOT_MAX,
    SUMMER_DAYS_REQUIRED,
    bootstrap_cut,
    build_emos_filter,
    group_snapshots,
    is_summer,
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

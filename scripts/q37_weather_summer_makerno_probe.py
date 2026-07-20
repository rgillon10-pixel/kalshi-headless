#!/usr/bin/env python3
"""q37_weather_summer_makerno_probe.py — Q37: summer maker-NO re-test of the S1/S5 weather
family, with the S5 EMOS-calibrated signal layered on as an entry filter (read-only, PREP
infrastructure — NOT a verdict this run).

LOOP-QUEUE.md Q37 (added 2026-07-15, Ryan interactive session — weather revival directive).
Every prior weather death was EXECUTION economics, not signal: S1's maker-NO variant printed
+$0.00448/trade with CI lower bound -$0.005 (n=654, spring, NO forecast input); S5's EMOS
calibration genuinely improved CRPS -7.9% but died to the 9.84c overround at TAKER prices. The
one untested cell of the matrix is SUMMER regime x MAKER execution (fee 0.0175 vs 0.07) x the
EMOS-calibrated signal that worked. This probe is that cell.

── STATUS: PROBE-PREP, NOT A VERDICT (idle-run policy (b), mirrors q43/q36/q32) ────────────────
Q37 is GATED on >=21 SUMMER (astronomical, 2026-06-21 onward) contract-days of DAILY-group
`tape/weather_books/` coverage (~2026-08-05 at the earliest; collector landed 2026-07-15). As of
2026-07-20 only 6 summer contract-days exist, so the live analysis MUST NOT run yet. This script
is built + offline-tested now so it fires the day the gate opens. Below the gate it prints an
honest INSUFFICIENT DATA banner (with the current day count) and exits 0 — it NEVER fabricates a
bootstrap / CI / verdict from too-few days, writes NO findings/ entry, and touches NO registry.
The full pipeline runs live only when `_summer_contract_days_available() >= SUMMER_DAYS_REQUIRED`;
until then it is exercised solely by the offline tests against injected synthetic fixtures (which
lower the gate with `days_required=` so the gate-open branch is proven too).

── THE TRADE (S1's maker-NO longshot fade, re-run on the NEW forward L2 tape) ───────────────────
Per (series, contract-day) daily temperature ladder — a clean 6-member partition {2 tails + 4
bands} (S1) — at a strictly-causal decision time T = close_time - DECISION_LEAD_HOURS: read every
bracket's REAL book (`best_yes_ask` = `real_ask`; `no_bids` ladder = `real_bid`). The ladder's own
`bracket_sum` (Hard Rule #3, `core.pricing.normalized_ask`) gives each bracket's overround-removed
implied probability. On every LONGSHOT bracket (implied prob < LONGSHOT_MAX) rest a MAKER NO buy
at the best NO bid, hold to settlement: NO pays $1 iff the longshot YES did NOT happen. Net edge =
payout - entry_no_price - MAKER fee.

── FILL MODEL — QUEUE-AWARE-STYLE BOOK TOUCH, EXPLICITLY `optimistic_fill` (binding gate #1) ─────
This tape is HOURLY resting-depth snapshots with NO trade/volume prints (L68) — a true
executed-volume-vs-queue fill (the S14/S19 mechanism) is UNCONSTRUCTIBLE here. So the fill is
modeled two honest ways and BOTH are reported (L32 dual cut via `core.bootstrap.bracket_by_movement`):
  * optimistic (frozen-inclusive): a resting NO bid is credited a fill when the best NO ASK ever
    crosses down to <= our resting price over the holding window (a real-book touch, NEVER a
    candlestick-through proxy — L39/Q34). This is the maker-fill primitive the depth tape CAN see.
  * movement-conditioned: the SAME touch, but only on brackets whose book actually MOVED during
    the window (a consecutive pair with an unchanged BBO is a no-fill, not free income — L32).
Because neither cut can PROVE our specific queue slot cleared without a trade tape, the whole
probe carries `OPTIMISTIC_FILL = True`: even a CI > 0 that clears every gate is capped at
`OPTIMISTIC_FILL_BLOCKS_GRADUATION` — it can never graduate to a live verdict on this tape alone
(the same posture S14's queue_fillsim enforces via its explicit caveat). `capturable_depth`
(L67) reports the at-touch queue size for context.

── THE "6-LEG FEE FLOOR" JUDGMENT CALL (binding gate #2) ────────────────────────────────────────
S33 (`scripts/probe_ladder_coherence.py`) summed `fee_per_contract` across ALL 6 brackets of a
ladder because its trade BOUGHT the complete set (a complete-set arb pays a fee on every one of
the 6 legs it transacts). This probe's trade is DIFFERENT: an isolated single-leg MAKER NO on ONE
longshot bracket. We transact exactly one contract on one bracket, so the fee floor is a SINGLE
maker fee `fee_per_contract(entry_no_price, MAKER_FEE_RATE)` on that one leg — summing 6 fees would
charge us for 5 legs we never trade and manufacture a false DEAD. The 6-member ladder is still
read in full (all 6 `yes_ask`s -> `bracket_sum`, Hard Rule #3, to normalize the implied prob and
require a complete partition), but the FEE is per-leg. Documented here, not silently chosen.

── THE EMOS SIGNAL LAYER (S5's calibration, layered as an entry FILTER) ─────────────────────────
S5's leave-one-day-out EMOS (Gneiting et al. 2005) is imported directly from
`scripts.weather_rehab_s5` (reused, never re-derived — L36). For each (series, contract-day) with
a forecast in `data/forecast_tape/` (the Q38 leg; `synthetic`, never a fill), fit EMOS on all
OTHER summer days' (ensemble mean, ensemble var, actual Tmax) and predict this day's calibrated
Gaussian; the actual Tmax training target is the `broker_truth` settled `expiration_value` from
`tape/weather_actuals/` (hindsight used ONLY on other days, never the traded day, never a price).
The EMOS filter TAKES the maker-NO trade only when the calibrated model agrees the longshot YES is
overpriced: market_implied - model_prob > EDGE_BAR. `data/forecast_tape/` is gitignored and may be
ABSENT (this sandbox) — handled as EMOS_UNAVAILABLE (the EMOS-filtered cut is skipped and reported
as such), NOT an error; the S1 no-signal baseline still runs so the probe is never fully dark.

── BOOTSTRAP + GATES (binding gate #3, #5) ──────────────────────────────────────────────────────
Block-bootstrap E[net pnl] BY CALENDAR CONTRACT-DAY (L6 — one weather realization drives all 6
brackets of a city-day, and same-date city-days share regimes; S1's block choice) through
`core.bootstrap.block_bootstrap`, then `bootstrap_verdict_admissible` (L41) AND
`clears_tick_magnitude` (L27). SUMMER-ONLY window stated up front (gate #5): NO season-mixing with
the old spring arb-bot-v2 SQLite tape — this reads ONLY the new committed `tape/weather_books/`
and only contract-days >= 2026-06-21. A settlement-unmeasurable bracket is DROPPED, never zeroed
(L86 — zeroing an unmeasurable catastrophic-loss leg fabricates a free win).

READ-ONLY, FULLY OFFLINE, NO NETWORK, NO ORDERS, NO AUTH, NO EXECUTION CODE.

Run:
    python scripts/q37_weather_summer_makerno_probe.py
    python scripts/q37_weather_summer_makerno_probe.py --books-dir tape/weather_books \
        --actuals-dir tape/weather_actuals --forecast-dir data/forecast_tape --json-out /tmp/q37.json
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    bracket_by_movement,
    clears_tick_magnitude,
)
from core.depth import capturable_depth  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE,
    bracket_sum as bracket_sum_fn,
    fee_per_contract,
    normalized_ask,
    overround as overround_fn,
)
# EMOS calibration layer REUSED from S5 (never re-derived — L36).
from scripts.weather_rehab_s5 import (  # noqa: E402
    MIN_TRAIN_DAYS,
    bracket_bounds,
    bracket_prob,
    fit_emos,
    predict,
)

BOOKS_GLOB = str(REPO_ROOT / "tape" / "weather_books" / "dt=*.jsonl")
ACTUALS_GLOB = str(REPO_ROOT / "tape" / "weather_actuals" / "dt=*.jsonl")
FORECAST_DIR = str(REPO_ROOT / "data" / "forecast_tape")
CITIES_YAML = REPO_ROOT / "config" / "cities.yaml"

# ── the self-activation gate: Q37 is GATED on >=21 SUMMER contract-days of daily coverage ──
SUMMER_START = date(2026, 6, 21)          # astronomical summer 2026 (gate #5: summer-only window)
SUMMER_DAYS_REQUIRED = 21

# ── modeling choices (documented; re-settle against the real leg when the gate opens) ──
DECISION_LEAD_HOURS = 24.0    # S1's T-24h strictly-causal decision time
LONGSHOT_MAX = 0.20           # implied prob below this defines a longshot (S1 default)
SPREAD_MAX = 0.10             # fillable two-sided book: best-yes ask-minus-bid <= 10c (L69 primary)
NEAR_CLOSE_HOURS = 24.0       # OR near-close: ttc <= 24h counts as a fillable entry (L69)
EDGE_BAR = 0.05               # EMOS filter: market_implied - model_prob must exceed this to trade
MIN_CI_UNITS = 10             # bootstrap_verdict_admissible floor (L41)
PRICE_TICK = 0.01
EPS = 1e-9

# The depth tape carries NO trade/volume prints (L68) so no fill can prove queue clearance — the
# whole probe is optimistic-fill by construction and can NEVER graduate to a live verdict here.
OPTIMISTIC_FILL = True

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
# <SERIES>-<YYMMMDD>-<bracket>, e.g. KXHIGHAUS-26JUL20-B99.5 / KXHIGHTATL-26JUL16-T93
_TICKER_RE = re.compile(r"^([A-Z0-9]+)-(\d{2})([A-Z]{3})(\d{2})-(.+)$")


# --------------------------------------------------------------------------- #
# ticker / time parsing
# --------------------------------------------------------------------------- #
def parse_daily_ticker(ticker: Any) -> Optional[Tuple[str, date, str]]:
    """(series, contract_day, bracket_code) from a daily weather ticker, or None on a grammar
    mismatch. The contract-day is parsed from the ticker's own `YYMMMDD` token (L16 discipline —
    NEVER from `close_time`, which lands in the next UTC day)."""
    if not isinstance(ticker, str):
        return None
    m = _TICKER_RE.match(ticker)
    if not m:
        return None
    try:
        d = date(2000 + int(m.group(2)), _MONTHS[m.group(3)], int(m.group(4)))
    except (KeyError, ValueError):
        return None
    return m.group(1), d, m.group(5)


def is_summer(d: date) -> bool:
    """Astronomical-summer gate (2026-06-21 onward) — the gate #5 season boundary."""
    return d >= SUMMER_START


def _parse_iso(v: Any) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _f(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# loaders (read-only)
# --------------------------------------------------------------------------- #
def _iter_lines(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield line
    except OSError:
        return


def _loads(line: str) -> Optional[dict]:
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None


def load_daily_snapshots(books_glob: str = BOOKS_GLOB) -> List[Dict[str, Any]]:
    """Every DAILY-group weather_books snapshot for a SUMMER contract-day, normalized to the
    fields this probe consumes. Sizes stay FLOAT (L47 — a real observed best-level size was
    91,316.82 contracts; int-coercion silently corrupts queue-depth reads). Non-daily rows,
    non-summer contract-days, and grammar-mismatched tickers are skipped."""
    out: List[Dict[str, Any]] = []
    for path in sorted(glob.glob(books_glob)):
        for line in _iter_lines(path):
            rec = _loads(line)
            if rec is None or rec.get("group") != "daily":
                continue
            parsed = parse_daily_ticker(rec.get("ticker"))
            if parsed is None:
                continue
            series, cday, bracket = parsed
            if not is_summer(cday):
                continue
            out.append({
                "series": series,
                "contract_day": cday,
                "bracket": bracket,
                "ticker": rec.get("ticker"),
                "captured_at": _parse_iso(rec.get("captured_at")),
                "close_time": _parse_iso(rec.get("close_time")),
                "strike_type": rec.get("strike_type"),
                "floor_strike": _f(rec.get("floor_strike")),
                "cap_strike": _f(rec.get("cap_strike")),
                "best_yes_ask": _f(rec.get("best_yes_ask")),
                "best_yes_bid": _f(rec.get("best_yes_bid")),
                "best_no_ask": _f(rec.get("best_no_ask")),
                "best_no_bid": _f(rec.get("best_no_bid")),
                # ladders are [price, size]; sizes summed as FLOAT (L47), never int-coerced
                "no_bids": rec.get("no_bids") or [],
            })
    return out


def group_snapshots(snaps: Sequence[Dict[str, Any]]
                    ) -> Dict[Tuple[str, date], Dict[str, List[Dict[str, Any]]]]:
    """{(series, contract_day): {bracket_ticker: [snapshot, ...] time-ordered}}."""
    groups: Dict[Tuple[str, date], Dict[str, List[Dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list))
    for s in snaps:
        if s["captured_at"] is None:
            continue
        groups[(s["series"], s["contract_day"])][s["ticker"]].append(s)
    for by_ticker in groups.values():
        for lst in by_ticker.values():
            lst.sort(key=lambda r: r["captured_at"])
    return groups


def summer_contract_days(snaps: Sequence[Dict[str, Any]]) -> List[date]:
    """Distinct SUMMER contract-day dates with daily-group coverage (the self-activation count)."""
    return sorted({s["contract_day"] for s in snaps})


def _summer_contract_days_available(books_glob: str = BOOKS_GLOB) -> int:
    """Count of distinct summer daily contract-days in the committed weather_books tape — the
    gate the whole live path hides behind. Below `SUMMER_DAYS_REQUIRED` the probe prints
    INSUFFICIENT DATA and exits 0 rather than fabricate a bootstrap from too few days."""
    return len(summer_contract_days(load_daily_snapshots(books_glob)))


def load_settlement(actuals_glob: str = ACTUALS_GLOB
                    ) -> Tuple[Dict[str, str], Dict[Tuple[str, date], float]]:
    """From `tape/weather_actuals/`: (results_by_ticker, actual_tmax_by_group).

      results_by_ticker[ticker] = "yes"/"no" (broker_truth settlement, exact ticker key)
      actual_tmax_by_group[(series, contract_day)] = realized high (broker_truth expiration_value)

    The `expiration_value` is used ONLY as the EMOS training target on OTHER days (never a price,
    never the traded day). A `broker_truth`-tagged event whose value can't be parsed is skipped."""
    results: Dict[str, str] = {}
    actuals: Dict[Tuple[str, date], float] = {}
    for path in sorted(glob.glob(actuals_glob)):
        for line in _iter_lines(path):
            rec = _loads(line)
            if rec is None:
                continue
            sm = rec.get("settled_markets") or {}
            for ev in sm.get("events", []) or []:
                for tk, res in (ev.get("results") or {}).items():
                    if isinstance(res, str):
                        results[tk] = res
                parsed = parse_daily_ticker((ev.get("event_ticker") or "") + "-x")
                exp = _f(ev.get("expiration_value"))
                if parsed is not None and exp is not None:
                    series, cday, _ = parsed
                    actuals[(series, cday)] = exp
    return results, actuals


def _series_to_forecast_city(cities_yaml: Path = CITIES_YAML) -> Dict[str, str]:
    """{high_series_ticker: forecast_city_name} from config/cities.yaml — the join key between a
    KXHIGH* ladder and its `data/forecast_tape/` city. Missing/malformed config -> {} (EMOS then
    simply unavailable, never an error)."""
    try:
        import yaml  # local import: the probe runs its baseline cut even without PyYAML present
        doc = yaml.safe_load(cities_yaml.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    out: Dict[str, str] = {}
    for c in doc.get("cities") or []:
        city = c.get("city")
        for s in (c.get("kalshi") or {}).get("high_series") or []:
            if city and s:
                out[s] = city
    return out


def load_forecast_tape(forecast_dir: str = FORECAST_DIR
                       ) -> Dict[Tuple[str, str], Dict[str, float]]:
    """{(forecast_city, target_date_iso): {model: tmax_f}} from `data/forecast_tape/` (Q38 leg,
    tag `synthetic` — a forecast is NEVER a fill). The dir is gitignored and may be ABSENT: a
    missing dir returns {} (EMOS unavailable), handled as INSUFFICIENT DATA for the EMOS cut, NOT
    an error (Hard Rule #1's `ncep_gefs025` never enters via S5's `MODELS`)."""
    out: Dict[Tuple[str, str], Dict[str, float]] = defaultdict(dict)
    d = Path(forecast_dir)
    if not d.exists():
        return {}
    for path in sorted(glob.glob(str(d / "**" / "*.jsonl"), recursive=True)) + \
            sorted(glob.glob(str(d / "*.jsonl"))):
        for line in _iter_lines(path):
            rec = _loads(line)
            if rec is None:
                continue
            city = rec.get("city")
            model = rec.get("model")
            dates = rec.get("target_dates") or []
            vals = rec.get("tmax_f") or []
            if not city or not model:
                continue
            for td, tv in zip(dates, vals):
                fv = _f(tv)
                if fv is not None:
                    out[(city, str(td))][model] = fv
    return {k: v for k, v in out.items()}


# --------------------------------------------------------------------------- #
# per-group fill simulation
# --------------------------------------------------------------------------- #
def _book_key(s: Dict[str, Any]) -> Tuple:
    return (s["best_yes_bid"], s["best_yes_ask"], s["best_no_bid"], s["best_no_ask"])


def _entry_index(snaps: List[Dict[str, Any]], t_decision: datetime) -> Optional[int]:
    """Index of the latest snapshot with captured_at <= t_decision (strictly causal, no
    look-ahead). None if the bracket has no book at/before the decision time."""
    idx = None
    for i, s in enumerate(snaps):
        if s["captured_at"] <= t_decision:
            idx = i
        else:
            break
    return idx


def simulate_group(series: str, contract_day: date,
                   by_ticker: Dict[str, List[Dict[str, Any]]],
                   results: Dict[str, str],
                   *, longshot_max: float = LONGSHOT_MAX,
                   decision_lead_hours: float = DECISION_LEAD_HOURS
                   ) -> Tuple[List[Dict[str, Any]], str]:
    """Simulate S1's maker-NO longshot fade over one (series, contract-day) daily ladder.

    Returns (trade_rows, skip_reason). A group is usable only if ALL its brackets carry a book at
    the decision time T = close - decision_lead_hours (a complete partition, so `bracket_sum`
    normalizes the ladder correctly — S1). Each longshot bracket becomes one trade row carrying
    the optimistic + movement-conditioned fill flags, the single-leg maker fee, and settlement.
    A settlement-unmeasurable bracket is DROPPED (measurable=False), never zeroed (L86)."""
    tickers = sorted(by_ticker)
    if not tickers:
        return [], "empty_group"
    # close_time shared across the ladder (take the first available)
    close_time = next((s["close_time"] for tk in tickers for s in by_ticker[tk]
                       if s["close_time"] is not None), None)
    if close_time is None:
        return [], "no_close_time"
    t_decision = close_time - timedelta(hours=decision_lead_hours)

    entry: Dict[str, Dict[str, Any]] = {}
    for tk in tickers:
        snaps = by_ticker[tk]
        ei = _entry_index(snaps, t_decision)
        if ei is None:
            return [], "incomplete_book"       # not a complete partition at T -> drop group
        e = snaps[ei]
        if e["best_yes_ask"] is None or not (0.0 < e["best_yes_ask"] < 1.0):
            return [], "bad_ask"
        entry[tk] = {"idx": ei, "snap": e, "window": snaps[ei:]}

    asks = [entry[tk]["snap"]["best_yes_ask"] for tk in tickers]
    bsum = bracket_sum_fn(asks)
    ovr = overround_fn(asks)
    if bsum <= 0:
        return [], "bad_bracket_sum"

    rows: List[Dict[str, Any]] = []
    for tk in tickers:
        e = entry[tk]["snap"]
        window = entry[tk]["window"]
        implied = normalized_ask(e["best_yes_ask"], bsum)   # Hard Rule #3
        if implied >= longshot_max:
            continue                                        # not a longshot — no trade
        no_bid = e["best_no_bid"]
        if no_bid is None or not (0.0 < no_bid < 1.0):
            continue                                        # no fillable NO bid to rest at
        entry_no_price = no_bid                             # rest the maker NO buy at best NO bid
        ttc_hours = (e["close_time"] - e["captured_at"]).total_seconds() / 3600.0 \
            if e["close_time"] else None
        yes_spread = (e["best_yes_ask"] - e["best_yes_bid"]) \
            if e["best_yes_bid"] is not None else None
        # L69 fillable-entry restriction (PRIMARY population): genuinely two-sided book OR near-close
        fillable_entry = ((yes_spread is not None and yes_spread <= SPREAD_MAX + EPS)
                          or (ttc_hours is not None and ttc_hours <= NEAR_CLOSE_HOURS + EPS))

        # queue position (L67) — the at-touch NO-bid size resting ahead of us (context; FLOAT L47)
        queue_ahead = capturable_depth(e["no_bids"], entry_no_price, band_cents=0.0)

        # fill detection over the holding window (real-book touch; NEVER a candle-through, L39/Q34)
        touched = any(s["best_no_ask"] is not None and s["best_no_ask"] <= entry_no_price + EPS
                      for s in window[1:])
        # frozen: the book never moved across the holding window (a no-fill, not free income — L32)
        frozen = len({_book_key(s) for s in window}) <= 1

        filled_optimistic = touched
        filled_movement = touched and not frozen

        # settlement (broker_truth) — DROP if unmeasurable, never zero the catastrophic leg (L86)
        res = results.get(tk)
        measurable = res in ("yes", "no")
        payout = (1.0 if res == "no" else 0.0) if measurable else None
        fee = fee_per_contract(entry_no_price, MAKER_FEE_RATE)   # SINGLE-LEG maker fee (gate #2)
        pnl = (payout - entry_no_price - fee) if measurable else None

        rows.append({
            "series": series,
            "contract_day": contract_day.isoformat(),
            "ticker": tk,
            "decision_T": t_decision.isoformat(),
            "entry_captured_at": e["captured_at"].isoformat(),
            "ttc_hours": ttc_hours,
            "yes_ask": e["best_yes_ask"],
            "yes_spread": yes_spread,
            "bracket_sum": bsum,
            "overround_absorbed": ovr,
            "member_count": len(tickers),
            "implied_prob": implied,
            "entry_no_price": entry_no_price,
            "queue_ahead": queue_ahead,
            "fillable_entry": fillable_entry,
            "touched": touched,
            "frozen": frozen,
            "filled_optimistic": filled_optimistic,
            "filled_movement": filled_movement,
            "settlement_measurable": measurable,
            "result": res,
            "payout": payout,
            "fee": fee,
            "pnl": pnl,
            "price_source_tag": "real_ask+real_bid+broker_truth",
        })
    return rows, "ok"


# --------------------------------------------------------------------------- #
# EMOS entry filter (S5 calibration reused; leave-one-day-out by contract-day)
# --------------------------------------------------------------------------- #
def _ens_mean_var(vals: Sequence[float]) -> Tuple[float, float]:
    """(mean, sample variance) of the available model Tmax values. Plain sample variance (n>=2)
    used ONLY as the EMOS spread regressor — never a sizing signal, so it does not route through
    core.stats.safe_pstdev's n>=4 guard (Hard Rule #2), mirroring S5's `_ens_stats`."""
    n = len(vals)
    m = sum(vals) / n
    var = sum((v - m) ** 2 for v in vals) / (n - 1) if n > 1 else 0.0
    return m, var


def build_emos_filter(rows: Sequence[Dict[str, Any]],
                      snaps_by_group: Dict[Tuple[str, date], Dict[str, List[Dict[str, Any]]]],
                      forecast: Dict[Tuple[str, str], Dict[str, float]],
                      actuals: Dict[Tuple[str, date], float],
                      series_city: Dict[str, str],
                      *, edge_bar: float = EDGE_BAR) -> Dict[str, Optional[bool]]:
    """Per-trade-row EMOS pass/fail flag keyed by ticker. leave-one-day-out over the summer
    contract-days: fit EMOS on all OTHER days' (ens_mean, ens_var, actual) and predict this day's
    calibrated (mu, sigma); a bracket passes iff market_implied - model_prob > edge_bar (the
    calibrated model AGREES the longshot YES is overpriced). Returns {ticker: True/False/None},
    None == EMOS-unavailable for that group (no forecast / no actual / unmapped city / too few
    training days). When `forecast` is empty (the sandbox case) EVERY flag is None."""
    # assemble per-group ensemble stats where a forecast exists
    group_ens: Dict[Tuple[str, date], Tuple[float, float]] = {}
    for (series, cday) in {(r["series"], date.fromisoformat(r["contract_day"])) for r in rows}:
        city = series_city.get(series)
        if city is None:
            continue
        fkey = (city, cday.isoformat())
        models = forecast.get(fkey) or {}
        vals = [v for v in models.values() if v is not None]
        if len(vals) < 2:
            continue
        group_ens[(series, cday)] = _ens_mean_var(vals)

    # training samples per contract-day (an ensemble AND a settled actual both required)
    samples_by_day: Dict[date, List[Tuple[float, float, float]]] = defaultdict(list)
    for (series, cday), (em, ev) in group_ens.items():
        act = actuals.get((series, cday))
        if act is not None:
            samples_by_day[cday].append((em, ev, act))

    flags: Dict[str, Optional[bool]] = {}
    for r in rows:
        series = r["series"]
        cday = date.fromisoformat(r["contract_day"])
        key = (series, cday)
        if key not in group_ens:
            flags[r["ticker"]] = None
            continue
        em, ev = group_ens[key]
        train = [s for d, lst in samples_by_day.items() if d != cday for s in lst]
        if len(train) >= MIN_TRAIN_DAYS:
            try:
                fit = fit_emos(train)
            except Exception:
                fit = None
        else:
            fit = None
        mu, sigma = predict(em, ev, fit)
        # locate this bracket's strike bounds off its own entry snapshot
        snap = _find_snap(snaps_by_group, key, r["ticker"])
        if snap is None:
            flags[r["ticker"]] = None
            continue
        lo, hi = bracket_bounds(snap["strike_type"], snap["floor_strike"], snap["cap_strike"])
        model_p = bracket_prob(mu, sigma, lo, hi)
        flags[r["ticker"]] = (r["implied_prob"] - model_p) > edge_bar
    return flags


def _find_snap(snaps_by_group, key, ticker) -> Optional[Dict[str, Any]]:
    by_ticker = snaps_by_group.get(key) or {}
    lst = by_ticker.get(ticker) or []
    return lst[0] if lst else None


# --------------------------------------------------------------------------- #
# bootstrap a filtered population, with the L32 dual cut and the L27/L41 gates
# --------------------------------------------------------------------------- #
def bootstrap_cut(rows: Sequence[Dict[str, Any]], fill_attr: str,
                  *, n_boot: int = 10000, min_units: int = MIN_CI_UNITS) -> Dict[str, Any]:
    """Block-bootstrap E[net pnl] BY CONTRACT-DAY (L6) over the rows that FILLED under `fill_attr`
    ("filled_optimistic" or "filled_movement") and whose settlement is measurable. Routes the CI
    through `bootstrap_verdict_admissible` (L41) AND `clears_tick_magnitude` (L27). Returns the
    full gate record; the caller decides the verdict (and OPTIMISTIC_FILL caps it)."""
    units: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        if r.get(fill_attr) and r.get("settlement_measurable") and r.get("pnl") is not None:
            units[r["contract_day"]].append(r["pnl"])
    unit_values = {k: v for k, v in units.items() if v}
    boot = block_bootstrap(unit_values, n_boot=n_boot)
    adm = bootstrap_verdict_admissible(unit_values, min_units=min_units)
    clears = clears_tick_magnitude(boot["ci95"], tick=PRICE_TICK, min_ticks=1.0)
    lo = boot["ci95"][0]
    positive = lo is not None and lo > 0.0
    return {
        "fill_attr": fill_attr,
        "n_units": boot["n_units"],
        "n_obs": boot["n_obs"],
        "mean": boot["mean"],
        "ci95": boot["ci95"],
        "admissible": adm["admissible"],
        "n_opposing_units": adm["n_opposing_units"],
        "admissible_reasons": adm["reasons"],
        "clears_tick_magnitude": clears,
        "ci_positive": positive,
    }


def movement_dual_cut(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """L32 dual cut over the OPTIMISTICALLY-filled, settlement-measurable population: report the
    fraction frozen and both the frozen-inclusive and movement-conditioned pnl populations, so a
    frozen (no-fill) pair can never be booked as free income. Uses
    `core.bootstrap.bracket_by_movement` on our own per-row frozen flags."""
    filled = [r for r in rows if r.get("filled_optimistic") and r.get("settlement_measurable")
              and r.get("pnl") is not None]
    frozen_flags = [bool(r["frozen"]) for r in filled]
    pnls = [r["pnl"] for r in filled]
    cut = bracket_by_movement(frozen_flags, pnls)
    return {"n_filled_optimistic": len(filled), "frac_frozen": cut["frac_frozen"],
            "n_movement_conditioned": len(cut["movement_conditioned"])}


# --------------------------------------------------------------------------- #
# orchestration (gated)
# --------------------------------------------------------------------------- #
def run_probe(books_glob: str = BOOKS_GLOB, actuals_glob: str = ACTUALS_GLOB,
              forecast_dir: str = FORECAST_DIR, *, days_required: int = SUMMER_DAYS_REQUIRED,
              n_boot: int = 10000, cities_yaml: Path = CITIES_YAML) -> Dict[str, Any]:
    """End-to-end, read-only. Gated: below `days_required` summer daily contract-days it returns
    an INSUFFICIENT DATA status and runs NO analysis (no bootstrap, no CI, no verdict).
    `days_required` is a parameter ONLY so the offline tests can open the gate on a synthetic
    fixture — the live default is `SUMMER_DAYS_REQUIRED`."""
    snaps = load_daily_snapshots(books_glob)
    days = summer_contract_days(snaps)
    report: Dict[str, Any] = {
        "summer_days_available": len(days),
        "summer_days_required": days_required,
        "summer_window_start": SUMMER_START.isoformat(),
        "optimistic_fill": OPTIMISTIC_FILL,
    }
    if len(days) < days_required:
        report["status"] = "INSUFFICIENT DATA"
        report["reason"] = (
            f"Q37 is gated on >= {days_required} SUMMER daily contract-days of "
            f"tape/weather_books/ coverage; only {len(days)} present "
            f"({[d.isoformat() for d in days]}). Prep script — no analysis, no verdict.")
        return report

    groups = group_snapshots(snaps)
    results, actuals = load_settlement(actuals_glob)
    forecast = load_forecast_tape(forecast_dir)
    series_city = _series_to_forecast_city(cities_yaml)

    all_rows: List[Dict[str, Any]] = []
    skips: Dict[str, int] = defaultdict(int)
    for (series, cday), by_ticker in groups.items():
        rows, reason = simulate_group(series, cday, by_ticker, results)
        if reason != "ok":
            skips[reason] += 1
        all_rows.extend(rows)

    # EMOS entry filter (S5 calibration) — None everywhere when forecast tape is absent
    emos_flags = build_emos_filter(all_rows, groups, forecast, actuals, series_city)
    for r in all_rows:
        r["emos_pass"] = emos_flags.get(r["ticker"])
    emos_available = any(v is not None for v in emos_flags.values())

    # populations (L69: fillable-entry restricted is PRIMARY; unrestricted is a labeled diagnostic)
    primary = [r for r in all_rows if r["fillable_entry"]]
    baseline_emos = [r for r in primary if r.get("emos_pass") is True]

    def _pop(rows: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "optimistic": bootstrap_cut(rows, "filled_optimistic", n_boot=n_boot),
            "movement_conditioned": bootstrap_cut(rows, "filled_movement", n_boot=n_boot),
            "dual_cut": movement_dual_cut(rows),
        }

    report["status"] = "ANALYSIS"
    report["n_groups"] = len(groups)
    report["n_longshot_trades"] = len(all_rows)
    report["skips"] = dict(skips)
    report["emos_available"] = emos_available
    report["fill_rate_optimistic"] = _rate(all_rows, "filled_optimistic")
    report["fill_rate_movement"] = _rate(all_rows, "filled_movement")
    report["populations"] = {
        # PRIMARY (L69): fillable two-sided / near-close entry, S1 no-signal baseline
        "primary_baseline": _pop(primary),
        # PRIMARY + S5 EMOS entry filter (None-reported if forecast tape absent)
        "primary_emos_filtered": (_pop(baseline_emos) if emos_available else "EMOS_UNAVAILABLE"),
        # DIAGNOSTIC ONLY (L69): unrestricted entry — never the headline
        "diagnostic_unrestricted_entry": _pop(all_rows),
    }
    report["verdict"] = _verdict(report)
    return report


def _rate(rows: Sequence[Dict[str, Any]], attr: str) -> Optional[float]:
    meas = [r for r in rows if r.get("settlement_measurable")]
    if not meas:
        return None
    return sum(1 for r in meas if r.get(attr)) / len(meas)


def _verdict(report: Dict[str, Any]) -> str:
    """Verdict on the PRIMARY population's MOVEMENT-CONDITIONED cut (the honest fill cut). Because
    the depth tape carries no trade prints, OPTIMISTIC_FILL caps ANY positive result at
    OPTIMISTIC_FILL_BLOCKS_GRADUATION — it can never graduate to a live verdict on this tape."""
    prim = report["populations"]["primary_baseline"]["movement_conditioned"]
    if prim["n_units"] == 0:
        return "INCONCLUSIVE_DATA_ADEQUACY"
    strong = prim["ci_positive"] and prim["admissible"] and prim["clears_tick_magnitude"]
    if strong:
        return "OPTIMISTIC_FILL_BLOCKS_GRADUATION" if OPTIMISTIC_FILL else "ALIVE_UNEXPECTED"
    if prim["ci_positive"]:
        return "DEAD_CI_OR_MAGNITUDE"    # lo>0 but fails admissibility or magnitude
    return "DEAD"                        # CI not strictly > 0 — the expected weather death


# --------------------------------------------------------------------------- #
# reporting
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: Sequence) -> str:
    if not ci or ci[0] is None:
        return "[None, None]"
    return f"[{ci[0]:+.5f}, {ci[1]:+.5f}]"


def _fmt_cut(name: str, cut: Dict[str, Any]) -> str:
    mean = "None" if cut["mean"] is None else f"{cut['mean']:+.5f}"
    return (f"    {name:<22} mean={mean:>10}  CI={_fmt_ci(cut['ci95'])}  "
            f"n_units={cut['n_units']}  n_obs={cut['n_obs']}  "
            f"adm={cut['admissible']}  mag={cut['clears_tick_magnitude']}")


def print_report(rep: Dict[str, Any]) -> None:
    print("=" * 92)
    print("Q37 WEATHER SUMMER MAKER-NO PROBE (S1 fade x S5 EMOS filter; prep; read-only, OFFLINE)")
    print("=" * 92)
    print(f"summer daily contract-days: {rep['summer_days_available']} "
          f"(gate opens at {rep['summer_days_required']}; window start "
          f"{rep['summer_window_start']})   optimistic_fill={rep['optimistic_fill']}")

    if rep.get("status") == "INSUFFICIENT DATA":
        print("\nINSUFFICIENT DATA — " + rep["reason"])
        print("Self-activating prep: this probe fires the full maker-NO + EMOS pipeline "
              "automatically the day the summer-day gate opens. NO verdict, NO findings, NO "
              "registry change.")
        return

    print(f"\ngroups={rep['n_groups']}  longshot trades={rep['n_longshot_trades']}  "
          f"skips={rep['skips']}  EMOS available={rep['emos_available']}")
    fro = rep["fill_rate_optimistic"]
    frm = rep["fill_rate_movement"]
    print(f"fill rate (optimistic touch)={_pct(fro)}  "
          f"(movement-conditioned)={_pct(frm)}  [S13/S19 base rate ~0.45%-2.5%]")

    for pname, pop in rep["populations"].items():
        label = {"primary_baseline": "PRIMARY (fillable-entry, S1 no-signal)",
                 "primary_emos_filtered": "PRIMARY + S5 EMOS filter",
                 "diagnostic_unrestricted_entry": "DIAGNOSTIC unrestricted-entry (NOT headline)"
                 }.get(pname, pname)
        print(f"\n{label}")
        if pop == "EMOS_UNAVAILABLE":
            print("    EMOS_UNAVAILABLE — data/forecast_tape/ absent/empty; EMOS cut skipped "
                  "(baseline still ran). Not an error (Hard Rule #1 forecast leg is optional here).")
            continue
        print(_fmt_cut("optimistic", pop["optimistic"]))
        print(_fmt_cut("movement-conditioned", pop["movement_conditioned"]))
        dc = pop["dual_cut"]
        print(f"    dual-cut (L32): filled_optimistic={dc['n_filled_optimistic']}  "
              f"frac_frozen={dc['frac_frozen']:.3f}  "
              f"movement_conditioned_n={dc['n_movement_conditioned']}")

    print(f"\nVERDICT: {rep['verdict']}")
    if rep["verdict"] == "OPTIMISTIC_FILL_BLOCKS_GRADUATION":
        print("  -> CI clears on the primary movement-conditioned cut, BUT this depth tape has no "
              "trade prints (L68): no fill can prove queue clearance, so graduation is blocked. "
              "Needs a maker-toxicity / trade tape before any live verdict.")
    elif rep["verdict"] == "DEAD":
        print("  -> primary movement-conditioned CI is not strictly > 0: the expected weather "
              "death (execution economics, as every S1/S5 sibling). Falsified on this sample.")
    elif rep["verdict"] == "DEAD_CI_OR_MAGNITUDE":
        print("  -> lo>0 but fails admissibility (L41) or the L27 magnitude gate — not verdict-grade.")
    else:
        print("  -> no measurable filled trades in the primary cut; untestable as collected, "
              "NOT a falsification.")
    print("\n(prep only — the gate-open branch above is exercised live once >=21 summer days exist;"
          " two-agent rule applies to any future LIVE verdict, NOT to this prep milestone)")


def _pct(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{100.0 * x:.2f}%"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Q37 summer weather maker-NO + EMOS probe (prep; read-only, OFFLINE)")
    ap.add_argument("--books-dir", default=None,
                    help="dir holding tape/weather_books dt=*.jsonl (default: committed tape)")
    ap.add_argument("--actuals-dir", default=None,
                    help="dir holding tape/weather_actuals dt=*.jsonl (default: committed tape)")
    ap.add_argument("--forecast-dir", default=None,
                    help="dir holding data/forecast_tape jsonl (default: gitignored store)")
    ap.add_argument("--days-required", type=int, default=SUMMER_DAYS_REQUIRED,
                    help="override the summer-day gate (TEST/dev use only)")
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    books_glob = str(Path(args.books_dir) / "dt=*.jsonl") if args.books_dir else BOOKS_GLOB
    actuals_glob = str(Path(args.actuals_dir) / "dt=*.jsonl") if args.actuals_dir else ACTUALS_GLOB
    forecast_dir = args.forecast_dir if args.forecast_dir else FORECAST_DIR

    rep = run_probe(books_glob, actuals_glob, forecast_dir,
                    days_required=args.days_required, n_boot=args.n_boot)
    print_report(rep)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(rep, indent=2, default=str))
        print(f"[q37] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

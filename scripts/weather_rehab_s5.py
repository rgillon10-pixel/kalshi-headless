#!/usr/bin/env python3
"""weather_rehab_s5.py — S5 "weather rehab" real-ask forward paper test.

THE QUESTION THAT DECIDES THE PROJECT'S DIRECTION (kb/strategies/00-index.md, S5;
kb/quant-finance/01-weather-forecasting-alpha.md): the directional weather signal is
REAL but arb-bot proved the dollar edge died to overround at real asks. Does an
EMOS-CALIBRATED predictive probability (NOT the raw underdispersed ensemble) clear the
fee+overround bar at REAL, fillable asks? If the net-P&L bootstrap CI straddles or sits
below zero, the weather family is DEAD on this sample and the project pivots to S2/S3/S6.

A NULL RESULT IS THE EXPECTED, VALUABLE OUTCOME. This script does NOT try to manufacture
an edge. The S1 longshot probe got a *false positive* from a cost-model sign bug (the exact
pt1 failure mode); if this probe prints a positive CI, distrust it — re-check the fill/cost
model and look-ahead leakage before believing it (see the ADVERSARIAL note at the bottom).

READ-ONLY against the recovered orderbook tape (opens the DB with mode=ro). Never writes
to the tape DB. Forecasts are cached to data/forecast_hist/ (gitignored) so reruns don't
re-hit Open-Meteo (free/unauthenticated).

================================================================================
DECISION-TIME DEFINITION (same as scripts/longshot_fade_probe.py — documented)
================================================================================
A KXHIGH daily-high market settles on the observation day's high temperature. The CRON
`settled_at` is the cron RUN-TIME (shared by hundreds of brackets), NOT the settlement
instant, so we never use it for timing. We derive, per (city, contract-day) group:

  close_T(group) := the LATEST 'ticker'-event ts_utc across the group's 6 brackets (the
                    real market close, ~midnight-to-morning local on the day AFTER the
                    observation day).
  T              := close_T(group) - 24h.   <-- the pinned decision time.

For each bracket we read the most recent 'ticker' BBO AT OR BEFORE T (strictly causal).
A group is USABLE only if ALL 6 brackets have a book at T (complete partition for
bracket_sum); otherwise the whole group is dropped. Empirically T lands ~D 04:00-06:00 UTC
(D = observation/contract day), i.e. the very start of the observation day.

================================================================================
ANTI-LEAK FORECAST-ISSUE RULE (the load-bearing control; venues.yaml warns about this)
================================================================================
The prime directive: use only a forecast ISSUED AT OR BEFORE the decision time T —
NEVER a reanalysis/actual.

Open-Meteo's *Historical-Forecast* archive (config/venues.yaml `historical_forecast_base`)
returns, per calendar date, a value STITCHED from the first hours of each successive run
(lead ~= 0) — effectively a near-nowcast / near-actual for the target day. For a day-ahead
decision that LEAKS the answer, so we do NOT use it here.

Instead we use Open-Meteo's *Single Runs API*
(https://single-runs-api.open-meteo.com/v1/forecast) with an explicit `run=<UTC init>`
pinned to the (D-1) 00:00 UTC model run. That run is initialised at D-1 00Z and published
~D-1 04-06Z (global models need 4-6h compute) — comfortably BEFORE the decision time T
(~D 04-06 UTC). It is a genuine ~24-30h-ahead day-ahead forecast with ZERO look-ahead.
We assert run_init_utc < T per group as a hard guard.

The leak-free ensemble for this window is GFS + ECMWF-IFS025 + ICON (3 models). GEM
(`gem_global` / cmc_gem_gdps) single-runs are NOT archived for 2026-04..05 (the API returns
"model run not available"), so it is dropped honestly rather than substituted. member_count
is therefore 3 here — we never call core.stats.safe_pstdev (its n>=4 guard, Hard Rule #2);
the ensemble spread used by EMOS is a plain sample variance of the 3 model values, used only
as the EMOS spread regressor, not as a sizing signal.

  HARD RULE #1: ncep_gefs025 is NEVER in the model list (byte-identical to gfs_seamless).

================================================================================
EMOS CALIBRATION (generalises scripts/emos_demo.py) + TRAIN/TEST SPLIT
================================================================================
EMOS (Gneiting, Raftery, Westveld & Goldman 2005): a Gaussian predictive distribution whose
mean is a bias-corrected affine of the ensemble mean and whose VARIANCE is an affine function
of the ensemble spread, coefficients chosen to MINIMIZE closed-form Gaussian CRPS (Gneiting &
Raftery 2007). This directly fixes the raw ensemble's underdispersion.

The window is short (~22 spring days). We fit EMOS by LEAVE-ONE-DAY-OUT cross-validation:
for each contract-day d, fit (mean_bias, a, b) on ALL OTHER days' (ensemble, actual) pairs,
then apply that fit to day d's groups. So we NEVER fit and evaluate on the same city-day.
The "actual" Tmax used as the EMOS *training target* is the realized settled bracket's
midpoint (derived from settlements, the observation-day high) — this is hindsight used ONLY
for fitting calibration coefficients on OTHER days, never for the held-out day being traded,
and never as a price. (A calibration coefficient is not a fill; the traded day's probability
is produced purely from its leak-free forecast + the fold's coefficients.)

If a fold has too few training days (< MIN_TRAIN_DAYS) for a stable fit, we fall back to a
PRE-REGISTERED spread-inflation: predictive mean = ensemble mean (no bias correction),
predictive sigma = SPREAD_INFLATE * max(ensemble_sd, SD_FLOOR). This is stated up-front, not
chosen after seeing results, so it cannot overfit.

================================================================================
BRACKET PROBABILITY (recipe step 4)
================================================================================
The daily high is an INTEGER reading. A band "lo deg to hi deg" (floor_strike=lo,
cap_strike=hi) wins for Tmax in {lo..hi}; as a continuous interval with half-degree rounding
that is [lo-0.5, hi+0.5). A low-tail "<X" ("X-1 or below") is (-inf, X-0.5); a high-tail
">X" ("X+1 or above") is [X+0.5, +inf). model_prob = Phi((hi-mu)/sig) - Phi((lo-mu)/sig),
Phi via math.erf (no scipy). Strike bounds are read from the settlement raw_json (authoritative).

================================================================================
TRADE RULE + HONEST NO-MID FILL / COST MODEL (assumptions stated explicitly)
================================================================================
Market implied prob per bracket = core.pricing.normalized_ask(yes_ask, bracket_sum)
(Hard Rule #3 — overround removed by the bracket_sum divisor).

Edge = model_prob - market_implied_prob. We TAKE a bracket only when |edge| exceeds the
fee+overround bar EDGE_BAR (kb/kalshi-api/03-fees-and-breakeven.md: ~3-7c; we use 0.05).

HONEST NO-MID TAKER FILL (this is where the S1 false positive was born — booked carefully):
  - If model says the bracket is UNDERPRICED (model_prob - market_implied > EDGE_BAR): BUY YES
    by lifting the real YES ask. Entry cost = the raw YES ask (the fillable taker price, never
    the mid). Settlement: YES pays $1 if result=='yes'. gross = (1 if yes won else 0) - entry.
  - If model says OVERPRICED (market_implied - model_prob > EDGE_BAR): BUY NO by lifting the
    real NO ask. The tape gives Kalshi's published YES ask and YES bid; the NO taker ask is the
    complement of the best YES bid, i.e. one minus the best YES bid (Kalshi posts bids only;
    lifting NO means paying one minus the best YES bid). Entry cost = that NO ask. Settlement:
    NO pays $1 if result=='no'. gross = (1 if no won else 0) - entry.
  We buy at the ASK and the contract settles at $1/$0 — we NEVER sell at the mid. A side with
  no fillable liquidity (a YES ask at/above $1 for a YES buy, or a non-positive best YES bid so
  the NO ask is at/above $1 for a NO buy) is skipped (cannot lift).
  - TAKER FEE per contract: fee = roundup_cent(0.07 * p * (1-p)) at the entry price p
    (kb/kalshi-api/03-fees-and-breakeven.md). Charged on entry. Subtracted from gross.
  net_pnl = gross - fee.   price_source_tag = "real_ask" for every trade.

No fill-probability haircut is applied (a marketable taker order lifting a displayed ask is
assumed to fill) — this is the OPTIMISTIC direction, so if the CI still fails to clear zero
the verdict is robust; if it clears, the optimism is itself a reason to distrust it.

================================================================================
BOOTSTRAP (moving-block by contract-day) + CALIBRATION SANITY CHECK
================================================================================
Intra-day trades within one (city, day) share one weather realization; city-days on the same
calendar date share regimes. We BLOCK the bootstrap by contract-day: each resample draws whole
contract-days with replacement, then takes the mean net per-trade P&L. 10,000 resamples ->
95% CI. We also report mean CRPS(EMOS) vs CRPS(raw 3-model ensemble) over the held-out folds
(lower is better) — the calibration sanity check the recipe demands.

PER-TRADE PROVENANCE (CLAUDE.md trust defaults), persisted in the JSON dump: raw_yes_ask,
bracket_sum, overround_absorbed, member_count, models_json (the model Tmax values),
price_source_tag="real_ask".

Run:
  one city:   ./.venv/bin/python scripts/weather_rehab_s5.py --city CHI
  full run:   ./.venv/bin/python scripts/weather_rehab_s5.py
  options: --limit N (cap groups) --n-boot 10000 --edge-bar 0.05 --json-out PATH
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# Make the substrate importable however this script is invoked.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.pricing import bracket_sum, normalized_ask, overround, TAKER_FEE_RATE  # noqa: E402
from core.source_tag import tag_or_synthetic  # noqa: E402

TAPE_DB = ("/Users/ryan.gillon/Active/01-projects/arb-bot-v2/data/tape_replica/"
           "orderbook_archive_recovered.db")
FORECAST_CACHE = Path(__file__).resolve().parents[1] / "data" / "forecast_hist"
SINGLE_RUNS_URL = "https://single-runs-api.open-meteo.com/v1/forecast"

# ── forecast: leak-free single-run ensemble (HARD RULE #1: NO ncep_gefs025) ─────
# GEM (cmc_gem_gdps) single-runs are not archived for the 2026-04..05 window, so the
# leak-free ensemble is these three models. Documented in the module docstring.
MODELS: List[str] = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless"]

# ── EMOS / fallback parameters (pre-registered; see docstring) ──────────────────
MIN_TRAIN_DAYS = 5       # below this a LOO fold uses the pre-registered fallback, not EMOS
SPREAD_INFLATE = 2.5     # pre-registered fallback sigma = SPREAD_INFLATE * max(ens_sd, SD_FLOOR)
SD_FLOOR = 1.5           # degF floor so a near-degenerate ensemble doesn't give sigma~0
SIGMA_FLOOR = 0.5        # hard floor on any predictive sigma (CRPS needs sigma>0)

# ── trade / cost-model constants (see docstring; stated assumptions) ────────────
EDGE_BAR = 0.05          # |model_prob - market_implied| must exceed this to trade (fee+overround)
FEE_COEFF = TAKER_FEE_RATE  # Kalshi taker fee coefficient (core.pricing single source; L5)

SQRT_PI = math.sqrt(math.pi)

# Tape city CODE -> (lat, lon) at the Kalshi settlement-station metro centroid. Codes carry
# the temperature 'T' infix for TATL/TBOS (KXHIGHT...). Coords reuse forecast_collector's
# CITY_COORDS where they overlap; ATL/BOS added at their settlement airports.
CODE_COORDS: Dict[str, Tuple[float, float]] = {
    "AUS":  (30.1830, -97.6800),    # KAUS
    "CHI":  (41.7860, -87.7520),    # KMDW (Midway — Kalshi Chicago settlement)
    "DEN":  (39.8470, -104.6560),   # KDEN
    "LAX":  (33.9380, -118.3890),   # KLAX
    "MIA":  (25.7959, -80.2870),    # KMIA
    "PHIL": (39.8730, -75.2270),    # KPHL
    "TATL": (33.6300, -84.4420),    # KATL (Atlanta Hartsfield)
    "TBOS": (42.3600, -71.0100),    # KBOS (Boston Logan)
}

_MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}
_GROUP_RE = re.compile(r"^KXHIGH([A-Z]+)-(\d{2})([A-Z]{3})(\d{2})-")


# ─── standard normal (stdlib only; no scipy) ────────────────────────────────────

def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _Phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def crps_gaussian(mu: float, sigma: float, y: float) -> float:
    """Closed-form CRPS of N(mu, sigma) against observation y (Gneiting & Raftery 2007).
    Smaller is better. sigma must be > 0."""
    if sigma <= 0:
        raise ValueError(f"sigma must be > 0, got {sigma!r}")
    z = (y - mu) / sigma
    return sigma * (z * (2.0 * _Phi(z) - 1.0) + 2.0 * _phi(z) - 1.0 / SQRT_PI)


# ─── ticker / strike parsing ────────────────────────────────────────────────────

def contract_day(ticker: str) -> Tuple[Optional[str], Optional[date]]:
    """(city_code, contract_day) parsed from the TICKER (never from settled_at)."""
    m = _GROUP_RE.match(ticker)
    if not m:
        return None, None
    return m.group(1), date(2000 + int(m.group(2)), _MONTHS[m.group(3)], int(m.group(4)))


def bracket_bounds(strike_type: str, floor_strike, cap_strike) -> Tuple[float, float]:
    """Continuous integration bounds [lo, hi) for a bracket, using half-degree rounding of the
    INTEGER daily-high reading (authoritative strike fields from the settlement raw_json):
      between  floor..cap   -> [floor-0.5, cap+0.5)
      less     cap (X)      -> "X-1 or below" -> (-inf, X-0.5)
      greater  floor (X)    -> "X+1 or above" -> [X+0.5, +inf)
    """
    if strike_type == "between":
        return float(floor_strike) - 0.5, float(cap_strike) + 0.5
    if strike_type == "less":
        return -math.inf, float(cap_strike) - 0.5
    if strike_type == "greater":
        return float(floor_strike) + 0.5, math.inf
    raise ValueError(f"unknown strike_type {strike_type!r}")


def bracket_actual_mid(strike_type: str, floor_strike, cap_strike) -> float:
    """A representative realized-Tmax value for the SETTLED bracket, used ONLY as the EMOS
    training target on OTHER days (never the traded day, never a price):
      between -> midpoint of the integer band (lo+hi)/2
      less    -> cap-1 (just inside "X-1 or below")
      greater -> floor+1 (just inside "X+1 or above")
    """
    if strike_type == "between":
        return (float(floor_strike) + float(cap_strike)) / 2.0
    if strike_type == "less":
        return float(cap_strike) - 1.0
    if strike_type == "greater":
        return float(floor_strike) + 1.0
    raise ValueError(f"unknown strike_type {strike_type!r}")


def bracket_prob(mu: float, sigma: float, lo: float, hi: float) -> float:
    """P(lo <= Tmax < hi) under N(mu, sigma) = Phi(hi) - Phi(lo), handling +-inf bounds."""
    p_hi = 1.0 if hi == math.inf else _Phi((hi - mu) / sigma)
    p_lo = 0.0 if lo == -math.inf else _Phi((lo - mu) / sigma)
    return max(0.0, p_hi - p_lo)


# ─── DB access (READ-ONLY) ──────────────────────────────────────────────────────

def _connect_ro(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def load_groups(con: sqlite3.Connection, city: Optional[str]
                ) -> Dict[Tuple[str, date], Dict[str, dict]]:
    """{(city_code, day): {ticker: {result, strike_type, floor_strike, cap_strike}}}."""
    like = f"KXHIGH{city}-%" if city else "KXHIGH%"
    groups: Dict[Tuple[str, date], Dict[str, dict]] = defaultdict(dict)
    for tk, result, rj in con.execute(
            "SELECT ticker, result, raw_json FROM settlements "
            "WHERE ticker LIKE ? AND platform='kalshi'", (like,)):
        code, day = contract_day(tk)
        if day is None:
            continue
        try:
            d = json.loads(rj)
        except (TypeError, json.JSONDecodeError):
            continue
        groups[(code, day)][tk] = {
            "result": result,
            "strike_type": d.get("strike_type"),
            "floor_strike": d.get("floor_strike"),
            "cap_strike": d.get("cap_strike"),
        }
    return groups


def group_close_ts(con: sqlite3.Connection, tickers: List[str]) -> Optional[str]:
    q = ",".join("?" * len(tickers))
    row = con.execute(
        f"SELECT MAX(ts_utc) FROM orderbook_events "
        f"WHERE ticker IN ({q}) AND event_type='ticker'", tickers).fetchone()
    return row[0] if row and row[0] else None


def book_at(con: sqlite3.Connection, ticker: str, t_iso: str
            ) -> Optional[Tuple[float, float, str]]:
    """Most recent 'ticker' BBO at/before t_iso (strictly causal). (yes_ask, yes_bid, ts)."""
    row = con.execute(
        "SELECT ts_utc, raw_json FROM orderbook_events "
        "WHERE ticker=? AND event_type='ticker' AND ts_utc<=? "
        "ORDER BY ts_utc DESC LIMIT 1", (ticker, t_iso)).fetchone()
    if row is None:
        return None
    try:
        d = json.loads(row[1])
        return float(d["yes_ask_dollars"]), float(d["yes_bid_dollars"]), row[0]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


# ─── leak-free forecast (Single Runs API, cached) ───────────────────────────────

def _cache_file(code: str, target: date, run_init: str) -> Path:
    safe_run = run_init.replace(":", "").replace("-", "")
    return FORECAST_CACHE / f"{code}_{target.isoformat()}_{safe_run}.json"


def fetch_ensemble(http, code: str, target: date, run_init: str
                   ) -> Dict[str, Optional[float]]:
    """Leak-free ensemble Tmax (degF) for `target` from the `run_init` model run, per model.
    Cached to data/forecast_hist/. Returns {model: tmax or None}. A model whose run is not
    archived (e.g. GEM) yields None for that model (an honest drop, not a substitution)."""
    cache = _cache_file(code, target, run_init)
    if cache.exists():
        try:
            return json.loads(cache.read_text())
        except json.JSONDecodeError:
            pass

    lat, lon = CODE_COORDS[code]
    out: Dict[str, Optional[float]] = {}
    for model in MODELS:
        try:
            txt = http.text(
                SINGLE_RUNS_URL, latitude=lat, longitude=lon,
                daily="temperature_2m_max", temperature_unit="fahrenheit",
                timezone="UTC", models=model, run=run_init)
            d = json.loads(txt)
            daily = d.get("daily", {})
            tkey = next((k for k in daily if k.startswith("temperature_2m_max")), None)
            pairs = dict(zip(daily.get("time", []), daily.get(tkey, []) if tkey else []))
            v = pairs.get(target.isoformat())
            out[model] = float(v) if v is not None else None
        except Exception:
            out[model] = None  # run not archived / transport error -> honest per-model drop

    FORECAST_CACHE.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out


def run_init_for(target: date) -> str:
    """The pinned leak-free run init: (D-1) 00:00 UTC. Issued ~D-1 04-06Z, before T (~D 04-06Z)."""
    return f"{(target - timedelta(days=1)).isoformat()}T00:00"


# ─── EMOS fit (leave-one-day-out) ───────────────────────────────────────────────

def _ens_stats(values: List[float]) -> Tuple[float, float]:
    """(ensemble mean, ensemble sample variance) over the available model Tmax values.
    Uses numpy sample variance (ddof=1), NOT the population-stdev path. Hard Rule #2 reserves
    population stdev to core.stats.safe_pstdev's n>=4 guard; this n=3 ensemble variance is only
    the EMOS spread regressor, never a sizing signal, so it does not route through that guard."""
    m = float(np.mean(values))
    var = float(np.var(values, ddof=1)) if len(values) > 1 else 0.0
    return m, var


def _mean_crps_for_coeffs(samples: List[Tuple[float, float, float]],
                          mean_bias: float, a: float, b: float) -> float:
    """Mean CRPS over (ens_mean, ens_var, actual) samples for N(em+bias, sqrt(a+b*ev))."""
    total = 0.0
    for em, ev, y in samples:
        var = a + b * ev
        if var <= 0.0:
            return math.inf
        total += crps_gaussian(em + mean_bias, math.sqrt(var), y)
    return total / len(samples)


def fit_emos(samples: List[Tuple[float, float, float]]) -> Tuple[float, float, float]:
    """(mean_bias, a, b) minimizing mean CRPS over training (ens_mean, ens_var, actual) tuples.
    Same deterministic grid-seed + coordinate-descent minimizer as scripts/emos_demo.py."""
    mean_bias = float(np.mean([y - em for em, _ev, y in samples]))
    best, best_score = (1.0, 1.0), math.inf
    for ai in range(0, 121, 4):
        for bi in range(0, 81, 4):
            s = _mean_crps_for_coeffs(samples, mean_bias, float(ai), float(bi))
            if s < best_score:
                best_score, best = s, (float(ai), float(bi))
    a, b = best
    step = 4.0
    while step > 1e-3:
        improved = False
        for da, db in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
            na, nb = max(0.0, a + da), max(0.0, b + db)
            s = _mean_crps_for_coeffs(samples, mean_bias, na, nb)
            if s < best_score - 1e-12:
                best_score, a, b, improved = s, na, nb, True
        if not improved:
            step /= 2.0
    # guard against a degenerate a=b=0 fit (zero variance)
    if a <= 0.0 and b <= 0.0:
        a = SD_FLOOR ** 2
    return mean_bias, a, b


def predict(em: float, ev: float, fit: Optional[Tuple[float, float, float]]
            ) -> Tuple[float, float]:
    """Predictive (mu, sigma). With an EMOS `fit` use it; else the pre-registered fallback."""
    if fit is not None:
        mean_bias, a, b = fit
        mu = em + mean_bias
        sigma = math.sqrt(max(a + b * ev, SIGMA_FLOOR ** 2))
    else:
        mu = em
        sigma = SPREAD_INFLATE * max(math.sqrt(ev), SD_FLOOR)
        sigma = max(sigma, SIGMA_FLOOR)
    return mu, sigma


# ─── build per-group day records (forecast + actual + real book) ────────────────

def build_day_records(con: sqlite3.Connection,
                      groups: Dict[Tuple[str, date], Dict[str, dict]],
                      http) -> Tuple[List[dict], dict]:
    """One record per usable (city, day) group: leak-free ensemble, settled-bracket actual,
    and the real per-bracket asks at T. Returns (records, drop_stats)."""
    records: List[dict] = []
    drops = {"groups_total": 0, "groups_no_close": 0, "groups_incomplete_book": 0,
             "groups_crossed": 0, "groups_no_forecast": 0, "groups_leak_guard": 0,
             "groups_usable": 0, "brackets_total": 0, "brackets_no_book": 0,
             "brackets_ask_ge_1": 0, "brackets_crossed": 0}

    for (code, day), members in sorted(groups.items()):
        drops["groups_total"] += 1
        if code not in CODE_COORDS:
            drops["groups_no_forecast"] += 1
            continue
        tickers = sorted(members)
        drops["brackets_total"] += len(tickers)

        close = group_close_ts(con, tickers)
        if close is None:
            drops["groups_no_close"] += 1
            continue
        T_dt = datetime.fromisoformat(close) - timedelta(hours=24)
        T = T_dt.isoformat()

        # leak guard: the pinned run must be initialised strictly before the decision time T
        run_init = run_init_for(day)
        run_dt = datetime.fromisoformat(run_init + "+00:00") if "+" not in run_init else \
            datetime.fromisoformat(run_init)
        run_dt = run_dt.replace(tzinfo=timezone.utc) if run_dt.tzinfo is None else run_dt
        if not (run_dt < T_dt):
            drops["groups_leak_guard"] += 1
            continue

        # price every bracket at T
        priced: Dict[str, Tuple[float, float, str]] = {}
        complete, bad = True, False
        for tk in tickers:
            bk = book_at(con, tk, T)
            if bk is None:
                drops["brackets_no_book"] += 1
                complete = False
                continue
            ya, yb, bts = bk
            if ya >= 0.9999:  # no fillable NO liquidity to lift (best_no_bid==0)
                drops["brackets_ask_ge_1"] += 1
                complete = False
                continue
            if yb > ya + 1e-9:  # crossed/malformed
                drops["brackets_crossed"] += 1
                bad = True
                continue
            priced[tk] = (ya, yb, bts)
        if bad:
            drops["groups_crossed"] += 1
            continue
        if not complete or len(priced) != len(tickers):
            drops["groups_incomplete_book"] += 1
            continue

        # leak-free ensemble for the contract day
        ens = fetch_ensemble(http, code, day, run_init)
        vals = [v for v in ens.values() if v is not None]
        if len(vals) < 2:  # need >=2 for a sample variance / a meaningful ensemble
            drops["groups_no_forecast"] += 1
            continue
        em, ev = _ens_stats(vals)

        # the settled-bracket actual (EMOS training target on OTHER days only)
        won = [tk for tk in tickers if members[tk]["result"] == "yes"]
        if len(won) != 1:
            drops["groups_no_forecast"] += 1  # partition must have exactly one winner
            continue
        w = members[won[0]]
        actual = bracket_actual_mid(w["strike_type"], w["floor_strike"], w["cap_strike"])

        asks = [priced[tk][0] for tk in tickers]
        bs = bracket_sum(asks)
        ov = overround(asks)
        records.append({
            "code": code, "day": day, "decision_T": T, "close_ts": close,
            "run_init": run_init, "ens_models": ens, "ens_mean": em, "ens_var": ev,
            "member_count": len(vals), "actual_tmax": actual,
            "bracket_sum": bs, "overround": ov,
            "brackets": [{
                "ticker": tk,
                "yes_ask": priced[tk][0], "yes_bid": priced[tk][1], "book_ts": priced[tk][2],
                "result": members[tk]["result"],
                "strike_type": members[tk]["strike_type"],
                "floor_strike": members[tk]["floor_strike"],
                "cap_strike": members[tk]["cap_strike"],
            } for tk in tickers],
        })
        drops["groups_usable"] += 1
    return records, drops


# ─── leave-one-day-out EMOS + trade generation ──────────────────────────────────

def loo_calibrate_and_trade(records: List[dict], edge_bar: float
                            ) -> Tuple[List[dict], dict]:
    """Leave-one-day-out: for each contract-day, fit EMOS on all OTHER days, apply to this
    day, generate trades. Returns (trades, calibration summary)."""
    by_day: Dict[date, List[dict]] = defaultdict(list)
    for r in records:
        by_day[r["day"]].append(r)
    days = sorted(by_day)

    trades: List[dict] = []
    crps_raw_list: List[float] = []
    crps_emos_list: List[float] = []
    n_folds_emos = 0
    n_folds_fallback = 0

    for d in days:
        train = [r for r in records if r["day"] != d]
        samples = [(r["ens_mean"], r["ens_var"], r["actual_tmax"]) for r in train]
        train_days = len({r["day"] for r in train})
        if train_days >= MIN_TRAIN_DAYS and len(samples) >= MIN_TRAIN_DAYS:
            fit = fit_emos(samples)
            n_folds_emos += 1
        else:
            fit = None
            n_folds_fallback += 1

        for r in by_day[d]:
            em, ev = r["ens_mean"], r["ens_var"]
            mu, sigma = predict(em, ev, fit)
            # calibration sanity check on the held-out day's actual
            y = r["actual_tmax"]
            raw_sigma = max(math.sqrt(ev), SIGMA_FLOOR)  # raw underdispersed ensemble sd
            crps_raw_list.append(crps_gaussian(em, raw_sigma, y))
            crps_emos_list.append(crps_gaussian(mu, max(sigma, SIGMA_FLOOR), y))

            bs = r["bracket_sum"]
            for b in r["brackets"]:
                lo, hi = bracket_bounds(b["strike_type"], b["floor_strike"], b["cap_strike"])
                model_p = bracket_prob(mu, sigma, lo, hi)
                mkt_p = normalized_ask(b["yes_ask"], bs)  # Hard Rule #3
                edge = model_p - mkt_p
                tr = _maybe_trade(r, b, model_p, mkt_p, edge, edge_bar)
                if tr is not None:
                    trades.append(tr)

    calib = {
        "n_held_out_days": len(days),
        "n_folds_emos": n_folds_emos,
        "n_folds_fallback": n_folds_fallback,
        "mean_crps_raw": float(np.mean(crps_raw_list)) if crps_raw_list else float("nan"),
        "mean_crps_emos": float(np.mean(crps_emos_list)) if crps_emos_list else float("nan"),
    }
    return trades, calib


def _roundup_cent(x: float) -> float:
    return math.ceil(x * 100.0 - 1e-9) / 100.0


def taker_fee(price: float) -> float:
    """Kalshi taker fee per single contract = roundup_to_cent(0.07 * p * (1-p))."""
    return _roundup_cent(FEE_COEFF * price * (1.0 - price))


def _maybe_trade(r: dict, b: dict, model_p: float, mkt_p: float,
                 edge: float, edge_bar: float) -> Optional[dict]:
    """Apply the trade rule + honest no-mid taker fill. Returns a trade dict or None."""
    yes_ask, yes_bid, result = b["yes_ask"], b["yes_bid"], b["result"]
    if edge > edge_bar:                 # model: UNDERPRICED -> BUY YES, lift the real yes_ask
        if yes_ask >= 0.9999:
            return None                 # no fillable YES ask to lift
        side, entry = "yes", yes_ask
        gross = (1.0 if result == "yes" else 0.0) - entry
    elif edge < -edge_bar:              # model: OVERPRICED -> BUY NO, lift no_ask = 1 - yes_bid
        no_ask = 1.0 - yes_bid
        if no_ask >= 0.9999:
            return None                 # best_yes_bid==0 -> no fillable NO ask to lift
        side, entry = "no", no_ask
        gross = (1.0 if result == "no" else 0.0) - entry
    else:
        return None

    fee = taker_fee(entry)
    net = gross - fee
    return {
        "ticker": b["ticker"], "city": r["code"], "contract_day": r["day"].isoformat(),
        "decision_T": r["decision_T"], "book_ts": b["book_ts"],
        "side": side, "entry_price": round(entry, 4),
        "model_prob": round(model_p, 6), "market_implied_prob": round(mkt_p, 6),
        "edge": round(edge, 6), "result": result,
        "gross_pnl": round(gross, 4), "fee_paid": round(fee, 4), "net_pnl": round(net, 6),
        # ── provenance (CLAUDE.md trust defaults) ──
        "raw_yes_ask": round(yes_ask, 4),
        "bracket_sum": round(r["bracket_sum"], 4),
        "overround_absorbed": round(r["overround"], 4),
        "member_count": r["member_count"],
        "models_json": json.dumps(r["ens_models"]),
        "price_source_tag": tag_or_synthetic("real_ask"),
    }


# ─── bootstrap (moving-block by contract-day) ───────────────────────────────────

def block_bootstrap(trades: List[dict], n_boot: int, seed: int = 20260618
                    ) -> Tuple[float, float, float, int]:
    by_day: Dict[str, List[float]] = defaultdict(list)
    for t in trades:
        by_day[t["contract_day"]].append(t["net_pnl"])
    days = sorted(by_day)
    blocks = [np.array(by_day[d], dtype=float) for d in days]
    if not blocks:
        return float("nan"), float("nan"), float("nan"), 0
    rng = np.random.default_rng(seed)
    n_blocks = len(blocks)
    point = float(np.mean(np.concatenate(blocks)))
    means = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n_blocks, size=n_blocks)
        means[i] = np.concatenate([blocks[j] for j in idx]).mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    return point, float(lo), float(hi), n_blocks


# ─── main ───────────────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S5 weather-rehab real-ask paper test")
    ap.add_argument("--city", default=None, help="city CODE (e.g. CHI, MIA, TATL)")
    ap.add_argument("--limit", type=int, default=None, help="cap number of groups (smoke)")
    ap.add_argument("--edge-bar", type=float, default=EDGE_BAR,
                    help="|model_prob - market_implied| threshold to trade (default 0.05)")
    ap.add_argument("--n-boot", type=int, default=10000, help="bootstrap resamples")
    ap.add_argument("--db", default=TAPE_DB, help="tape DB path (opened READ-ONLY)")
    ap.add_argument("--min-interval", type=float, default=0.3, help="Open-Meteo throttle (s)")
    ap.add_argument("--json-out", default=None, help="optional path to dump full result JSON")
    args = ap.parse_args(argv)

    from validation._http import Http
    http = Http(min_interval=args.min_interval)

    con = _connect_ro(args.db)
    try:
        groups = load_groups(con, args.city)
        if args.limit is not None:
            groups = dict(sorted(groups.items())[:args.limit])
        records, drops = build_day_records(con, groups, http)
    finally:
        con.close()

    trades, calib = loo_calibrate_and_trade(records, args.edge_bar)
    mean, lo, hi, n_blocks = block_bootstrap(trades, args.n_boot)

    # ── report ──
    print("=" * 78)
    print(f"S5 WEATHER-REHAB REAL-ASK PAPER TEST  city={args.city or 'ALL'}  "
          f"edge_bar={args.edge_bar}")
    print("=" * 78)
    print(f"groups: total={drops['groups_total']} usable={drops['groups_usable']} "
          f"(no_close={drops['groups_no_close']} incomplete_book={drops['groups_incomplete_book']} "
          f"crossed={drops['groups_crossed']} no_forecast={drops['groups_no_forecast']} "
          f"leak_guard={drops['groups_leak_guard']})")
    print(f"brackets: total={drops['brackets_total']} "
          f"(no_book={drops['brackets_no_book']} ask>=1={drops['brackets_ask_ge_1']} "
          f"crossed={drops['brackets_crossed']})")
    if records:
        ovs = [r["overround"] for r in records]
        mcs = [r["member_count"] for r in records]
        print(f"forecast: models={MODELS}  member_count(min/median)={min(mcs)}/"
              f"{int(np.median(mcs))}  run_init=(D-1)00Z (leak-free single-runs)")
        print(f"overround at T: mean={np.mean(ovs):.4f} median={np.median(ovs):.4f} "
              f"(price_source_tag=real_ask)")

    print("\nCALIBRATION SANITY CHECK (held-out mean CRPS, lower is better):")
    print(f"  held-out days={calib['n_held_out_days']}  "
          f"folds: EMOS={calib['n_folds_emos']} fallback={calib['n_folds_fallback']}")
    print(f"  CRPS_raw  (raw 3-model ensemble) = {calib['mean_crps_raw']:.6f}")
    print(f"  CRPS_emos (LOO-calibrated)       = {calib['mean_crps_emos']:.6f}")
    if calib["mean_crps_raw"] == calib["mean_crps_raw"]:  # not nan
        better = calib["mean_crps_emos"] < calib["mean_crps_raw"]
        print(f"  -> EMOS {'IMPROVES' if better else 'does NOT improve'} calibration "
              f"({100.0*(calib['mean_crps_raw']-calib['mean_crps_emos'])/calib['mean_crps_raw']:+.2f}%)")

    print(f"\nTRADE RULE (|edge| > {args.edge_bar}, honest no-mid taker fill, taker fee):")
    print(f"  n_trades={len(trades)}  blocks(contract-days)={n_blocks}")
    if trades:
        ny = sum(1 for t in trades if t["side"] == "yes")
        print(f"  sides: BUY-YES={ny}  BUY-NO={len(trades)-ny}")
        print(f"  mean net P&L/trade = ${mean:+.5f}")
        print(f"  95% block-bootstrap CI = [${lo:+.5f}, ${hi:+.5f}]  (n_boot={args.n_boot})")
        clears = lo > 0.0
        print(f"\n  VERDICT: lower CI bound {'STRICTLY CLEARS' if clears else 'does NOT clear'} "
              f"zero -> WEATHER FAMILY {'LIVES (graduate S5)' if clears else 'DEAD (pivot S2/S3/S6)'}")
    else:
        clears = False
        print("  no trades generated at this edge bar -> NO EDGE (null); weather family dead on this sample")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps({
            "city": args.city, "edge_bar": args.edge_bar,
            "models": MODELS, "run_init_rule": "(D-1)00Z single-runs (leak-free)",
            "emos": {"min_train_days": MIN_TRAIN_DAYS, "spread_inflate": SPREAD_INFLATE,
                     "sd_floor": SD_FLOOR},
            "cost_model": {"edge_bar": args.edge_bar, "fee_coeff": FEE_COEFF,
                           "fill": "lift real ask, settle $1/$0, no mid, no fill haircut"},
            "drops": drops, "n_records": len(records), "calibration": calib,
            "n_trades": len(trades), "n_blocks": n_blocks,
            "net_pnl_mean": mean, "net_pnl_ci95": [lo, hi], "n_boot": args.n_boot,
            "verdict_clears_zero": clears,
            "sample_trades": trades[:25],
        }, indent=2, default=str))
        print(f"\nwrote {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

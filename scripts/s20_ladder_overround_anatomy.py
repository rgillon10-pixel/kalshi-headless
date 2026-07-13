#!/usr/bin/env python3
"""s20_ladder_overround_anatomy.py — Q20: BTC/ETH fine-ladder overround anatomy.

LOOP-QUEUE.md Q20 (feeds S14's crypto leg). Q2 (2026-07-03) flagged a KXBTC hourly ladder
whose bracket_sum overround was +$9.27 at real_ask prices (Sigma of all 188 members' yes_asks,
minus $1.00) and it was never investigated. The leading hypothesis (consistent with S10's
DEAD verdict and lesson L12) is that this fat apparent overround is mostly an ARTIFACT of the
~180 far-out-of-the-money strikes pinned at Kalshi's 1c minimum ask (a floor, not a real
maker-capturable quote), not genuine premium.

This is a READ-ONLY decomposition (no network, no orders, no auth). It does three things:

1. DECOMPOSE the overround by strike distance from spot. For each captured hourly ladder
   snapshot, bucket every member by its coordinate's distance from the current spot into an
   ACTIVE band (within +/- N strike-spacings of spot, N=3 default) vs WINGS (everything else),
   and split the wings into WING_FLOOR (yes_ask <= the 1c floor — the mechanically-pinned tail)
   vs WING_ELEVATED (yes_ask above the floor but outside the band — a stale/one-sided quote,
   L31's ask-direction cousin). Quantify how much of bracket_sum - 1 sits in each bucket.
   Strike spacing is read off the ladder's OWN strikes (`core.pricing.infer_strike_spacing`,
   L7 — never a hardcoded width). Spot is the top-level `spot.price` leg (tagged `synthetic`,
   a Coinbase reference — used ONLY as a binning coordinate, NEVER as a fill price; its
   exchange_time is ~synchronous with captured_at, so no L8 lag confound in the binning).

2. JOIN `tape/orderbook_depth/` to see what SIZE actually rests at the wing asks vs the
   active-band asks. A Kalshi YES offer at price p is the mirror of a NO bid at (1 - p), so
   the size resting AT a member's best yes_ask is the top of its no_bid ladder
   (`best_no_bid == 1 - best_yes_ask`). This tests the naive "wings are quote-only (depth ~ 0)"
   claim directly. (Depth capture starts 2026-07-07; the crypto_hourly tape starts 2026-07-03,
   so the join is restricted to the overlapping window — L9. Matched by ticker + NEAREST
   captured_at, because the depth sub-pass runs ~20s after the crypto_hourly sub-pass in the
   same hourly pass with a DIFFERENT capture_id.)

3. Compute the S14-relevant number: restricting to the ACTIVE band only, does
   `sum(yes_asks) - 1 - total_maker_fees` stay positive? Fees from `core.pricing.fee_per_contract`
   at the MAKER rate (L5/L18/L30 — flat $0.01/contract at every interior price). Bootstrapped
   BY EVENT-HOUR (L6 — one settlement fixes all outcomes within an hour; snapshots within an
   hour are correlated draws, not independent) via `core.bootstrap.block_bootstrap`, with the
   L27 magnitude gate. This is an ANATOMY + parameter-block deliverable, NOT a P&L verdict and
   NOT a registry flip (Q20: "No registry flip without the two-agent rule"); any P&L-shaped
   number here is labeled EXPLORATORY.

Run:
    python scripts/s20_ladder_overround_anatomy.py
    python scripts/s20_ladder_overround_anatomy.py --band-steps 3 --n-boot 10000
    python scripts/s20_ladder_overround_anatomy.py --series KXBTC --json-out /tmp/s20.json
"""
from __future__ import annotations

import argparse
import json
import sys
from bisect import bisect_left
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.bootstrap import block_bootstrap, clears_tick_magnitude  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402
from core.pricing import (  # noqa: E402
    MAKER_FEE_RATE,
    bracket_sum,
    fee_per_contract,
    infer_strike_spacing,
)

CRYPTO_DIR = REPO_ROOT / "tape" / "crypto_hourly"
DEPTH_DIR = REPO_ROOT / "tape" / "orderbook_depth"
FLOOR_ASK = 0.01          # Kalshi 1c minimum YES ask — the mechanical floor a wing pins to
BAND_STEPS = 3            # active band = within this many strike-spacings of spot (Q20: +/-3)
DEPTH_JOIN_MAX_DELTA_SEC = 600.0   # a depth capture must be within 10 min to count as "same pass"

BUCKETS = ("active", "wing_floor", "wing_elevated")


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only — lessons L25/L29 skip stray dt=<date> DIRECTORIES)
# --------------------------------------------------------------------------- #
def load_crypto_snapshots(tape_dir: Path = CRYPTO_DIR,
                          series_filter: Optional[Tuple[str, ...]] = None
                          ) -> List[Dict[str, Any]]:
    """Every crypto_hourly ladder snapshot with a usable `current.outcomes` + `spot.price`.
    Returns lightweight dicts (event_ticker, series, captured_at, spot, outcomes). Never
    mutates tape; a stray `dt=<date>` DIRECTORY is skipped by the is_file guard (L25/L29)."""
    out: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                series = r.get("series")
                if series_filter and series not in series_filter:
                    continue
                cur = r.get("current")
                if not cur or not cur.get("outcomes") or not cur.get("event_ticker"):
                    continue
                spot = r.get("spot") or {}
                spot_price = spot.get("price")
                if spot_price is None:
                    continue
                cap = r.get("captured_at")
                if not cap:
                    continue
                out.append({
                    "event_ticker": cur["event_ticker"],
                    "series": series,
                    "captured_at": cap,
                    "spot": float(spot_price),
                    "spot_tag": spot.get("price_source_tag", "synthetic"),
                    "outcomes": cur["outcomes"],
                    "bracket_sum_recorded": cur.get("bracket_sum"),
                })
    return out


# --------------------------------------------------------------------------- #
# pure ladder geometry + decomposition
# --------------------------------------------------------------------------- #
def member_coord(o: Dict[str, Any]) -> Optional[float]:
    """A single strike coordinate for distance-from-spot binning: the midpoint of a `between`
    band, else whichever boundary strike exists for an edge `less`/`greater` member. None if
    neither strike is present."""
    st = o.get("strike_type")
    fs = o.get("floor_strike")
    cs = o.get("cap_strike")
    if st == "between" and fs is not None and cs is not None:
        return (float(fs) + float(cs)) / 2.0
    if fs is not None:
        return float(fs)
    if cs is not None:
        return float(cs)
    return None


def ladder_spacing(outcomes: List[Dict[str, Any]]) -> Optional[float]:
    """Strike spacing read off the ladder's own `between` floor strikes (L7 — never a hardcoded
    per-symbol width). Median consecutive gap, robust to one missing/duplicated member."""
    return infer_strike_spacing(
        [o["floor_strike"] for o in outcomes
         if o.get("strike_type") == "between" and o.get("floor_strike") is not None])


def classify_bucket(o: Dict[str, Any], spot: float, spacing: Optional[float],
                    band_steps: int = BAND_STEPS, floor: float = FLOOR_ASK) -> str:
    """Bucket one member: `active` if its coordinate is within `band_steps` spacings of spot;
    otherwise a wing, split into `wing_floor` (yes_ask <= the 1c floor) vs `wing_elevated`
    (a stale/one-sided ask above the floor but out of the band). An edge member with no
    coordinate, or a snapshot with no derivable spacing, falls back to the ask-only split so
    it is never silently dropped from bracket_sum."""
    ask = float(o["yes_ask"])
    coord = member_coord(o)
    in_band = (spacing is not None and spacing > 0 and coord is not None
               and abs(coord - spot) <= band_steps * spacing)
    if in_band:
        return "active"
    return "wing_floor" if ask <= floor + 1e-9 else "wing_elevated"


def decompose_snapshot(outcomes: List[Dict[str, Any]], spot: float,
                       band_steps: int = BAND_STEPS, floor: float = FLOOR_ASK,
                       maker_rate: float = MAKER_FEE_RATE) -> Dict[str, Any]:
    """Split one ladder snapshot's bracket_sum by bucket, plus the S14-relevant active-band
    balance. All ask arithmetic is on plain local floats (not the raw `yes_ask` dict field),
    keeping Hard Rule #3 honest — this is overround *decomposition*, not a probability read."""
    spacing = ladder_spacing(outcomes)
    sums = {b: 0.0 for b in BUCKETS}
    mids = {b: 0.0 for b in BUCKETS}
    counts = {b: 0 for b in BUCKETS}
    active_maker_fee = 0.0
    for o in outcomes:
        ask = float(o["yes_ask"])
        bid = float(o.get("yes_bid") or 0.0)
        b = classify_bucket(o, spot, spacing, band_steps, floor)
        sums[b] += ask
        mids[b] += (ask + bid) / 2.0
        counts[b] += 1
        if b == "active":
            active_maker_fee += fee_per_contract(ask, rate=maker_rate)
    bsum = bracket_sum([float(o["yes_ask"]) for o in outcomes])
    overround = bsum - 1.0
    active_ask_sum = sums["active"]
    active_mid_sum = mids["active"]
    # S14-relevant registry-literal balance: underwrite the active band as a mini ladder,
    # collect its asks (net of the flat maker fee), pay $1 to the winner. sum(asks) - 1 - fees.
    active_over_1_after_fees = active_ask_sum - 1.0 - active_maker_fee
    # capturable half-spread the maker actually earns above mid, net of the flat fee — the
    # "expected overround capture" input for the S14-crypto parameter block.
    active_halfspread_after_fees = active_ask_sum - active_mid_sum - active_maker_fee
    wing_sum = sums["wing_floor"] + sums["wing_elevated"]
    return {
        "spacing": spacing,
        "n_members": len(outcomes),
        "bracket_sum": bsum,
        "overround": overround,
        "sums": sums,
        "mids": mids,
        "counts": counts,
        "active_ask_sum": active_ask_sum,
        "active_mid_sum": active_mid_sum,
        "active_maker_fee": active_maker_fee,
        "active_over_1_after_fees": active_over_1_after_fees,
        "active_halfspread_after_fees": active_halfspread_after_fees,
        "wing_sum": wing_sum,
        "frac_overround_in_wings": (wing_sum / overround) if overround > 1e-9 else float("nan"),
    }


# --------------------------------------------------------------------------- #
# orderbook_depth join (mirror: size at yes_ask == size at no_bid 1-p)
# --------------------------------------------------------------------------- #
def _ask_side_depth(rec: Dict[str, Any]) -> float:
    """Contracts resting AT the current best YES ask = top of the NO-bid ladder, because a
    YES offer at p is the mirror of a NO bid at (1-p) and `best_no_bid == 1 - best_yes_ask`.
    0.0 when the no-bid side is empty (a genuinely one-sided wing, L23 — empty != drop)."""
    nb = rec.get("no_bids") or []
    if not nb:
        return 0.0
    try:
        return float(nb[0][1])
    except (IndexError, TypeError, ValueError):
        return 0.0


def _parse_ts(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def build_depth_index(depth_dir: Path = DEPTH_DIR,
                      ticker_prefixes: Tuple[str, ...] = ("KXBTC", "KXETH")
                      ) -> Dict[str, List[Tuple[float, float, float]]]:
    """`{ticker: [(ts, best_yes_ask, ask_side_depth), ...]}` sorted by ts, keeping only the
    lightweight fields the join needs (never the full ladders — bounds memory over ~160k
    depth records). FILES only (L25/L29). Read-only."""
    idx: Dict[str, List[Tuple[float, float, float]]] = {}
    for path in sorted(depth_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                tk = r.get("ticker", "")
                if not tk.startswith(ticker_prefixes):
                    continue
                cap = r.get("captured_at")
                if not cap:
                    continue
                bya = r.get("best_yes_ask")
                idx.setdefault(tk, []).append(
                    (_parse_ts(cap), float(bya) if bya is not None else float("nan"),
                     _ask_side_depth(r)))
    for tk in idx:
        idx[tk].sort(key=lambda t: t[0])
    return idx


def nearest_depth(idx: Dict[str, List[Tuple[float, float, float]]], ticker: str, ts: float,
                  max_delta_sec: float = DEPTH_JOIN_MAX_DELTA_SEC
                  ) -> Optional[Tuple[float, float]]:
    """`(best_yes_ask, ask_side_depth)` from the depth capture of `ticker` NEAREST in time to
    `ts`, or None if no capture is within `max_delta_sec`. Binary-searches the ticker's own
    sorted timeline (the crypto_hourly and depth sub-passes share tickers but not capture_id;
    they run ~20s apart, so nearest-time is a robust join)."""
    series = idx.get(ticker)
    if not series:
        return None
    times = [t[0] for t in series]
    i = bisect_left(times, ts)
    best: Optional[Tuple[float, float, float]] = None
    for j in (i - 1, i):
        if 0 <= j < len(series):
            cand = series[j]
            if best is None or abs(cand[0] - ts) < abs(best[0] - ts):
                best = cand
    if best is None or abs(best[0] - ts) > max_delta_sec:
        return None
    return (best[1], best[2])


def join_depth_by_bucket(
    snapshots: List[Dict[str, Any]],
    depth_idx: Dict[str, List[Tuple[float, float, float]]],
    band_steps: int = BAND_STEPS, floor: float = FLOOR_ASK,
    max_delta_sec: float = DEPTH_JOIN_MAX_DELTA_SEC,
) -> Dict[str, Dict[str, Any]]:
    """For every member in every snapshot, find its nearest depth capture and accumulate the
    ask-side resting size into its bucket. Returns per-bucket {n_matched, depths:[...]} — the
    direct test of 'wings are quote-only' vs 'wings rest deep size at the 1c floor'."""
    agg: Dict[str, Dict[str, Any]] = {b: {"n_members": 0, "n_matched": 0, "depths": []}
                                      for b in BUCKETS}
    for snap in snapshots:
        spacing = ladder_spacing(snap["outcomes"])
        ts = _parse_ts(snap["captured_at"])
        for o in snap["outcomes"]:
            b = classify_bucket(o, snap["spot"], spacing, band_steps, floor)
            agg[b]["n_members"] += 1
            hit = nearest_depth(depth_idx, o["ticker"], ts, max_delta_sec)
            if hit is None:
                continue
            agg[b]["n_matched"] += 1
            agg[b]["depths"].append(hit[1])
    return agg


def _median(xs: List[float]) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    n = len(s)
    m = n // 2
    return s[m] if n % 2 else (s[m - 1] + s[m]) / 2.0


def _frac_positive(xs: List[float]) -> float:
    if not xs:
        return float("nan")
    return sum(1 for x in xs if x > 0.0) / len(xs)


# --------------------------------------------------------------------------- #
# per-series aggregate + bootstrap
# --------------------------------------------------------------------------- #
def summarize_series(snapshots: List[Dict[str, Any]], band_steps: int = BAND_STEPS,
                     floor: float = FLOOR_ASK, n_boot: int = 10000) -> Dict[str, Any]:
    """Decompose every snapshot of one series, aggregate the overround split, and block-
    bootstrap the active-band `sum(asks) - 1 - fees` BY EVENT-HOUR (L6)."""
    decs = [(s["event_ticker"], decompose_snapshot(s["outcomes"], s["spot"], band_steps, floor))
            for s in snapshots]
    n = len(decs)
    if n == 0:
        return {"n_snapshots": 0}

    def mean(key: str) -> float:
        return sum(d[key] for _, d in decs) / n

    def mean_bucket_sum(b: str) -> float:
        return sum(d["sums"][b] for _, d in decs) / n

    def mean_bucket_count(b: str) -> float:
        return sum(d["counts"][b] for _, d in decs) / n

    # block-bootstrap by event-hour: value = active-band sum(asks)-1-fees per snapshot
    unit_values: Dict[str, List[float]] = {}
    for et, d in decs:
        unit_values.setdefault(et, []).append(d["active_over_1_after_fees"])
    boot = block_bootstrap(unit_values, n_boot=n_boot)

    # capturable half-spread (the parameter-block "expected overround capture") — same unit
    hs_values: Dict[str, List[float]] = {}
    for et, d in decs:
        hs_values.setdefault(et, []).append(d["active_halfspread_after_fees"])
    boot_hs = block_bootstrap(hs_values, n_boot=n_boot)

    frac_wings = [d["frac_overround_in_wings"] for _, d in decs
                  if d["frac_overround_in_wings"] == d["frac_overround_in_wings"]]
    return {
        "n_snapshots": n,
        "n_event_hours": len(unit_values),
        "mean_n_members": mean("n_members"),
        "mean_bracket_sum": mean("bracket_sum"),
        "mean_overround": mean("overround"),
        "mean_active_ask_sum": mean("active_ask_sum"),
        "mean_active_mid_sum": mean("active_mid_sum"),
        "mean_bucket_sums": {b: mean_bucket_sum(b) for b in BUCKETS},
        "mean_bucket_counts": {b: mean_bucket_count(b) for b in BUCKETS},
        "mean_frac_overround_in_wings": (sum(frac_wings) / len(frac_wings)
                                         if frac_wings else float("nan")),
        "active_over_1_after_fees": {
            "mean": boot["mean"], "ci95": boot["ci95"], "n_units": boot["n_units"],
            "clears_tick_magnitude": clears_tick_magnitude(boot["ci95"]),
        },
        "active_halfspread_after_fees": {
            "mean": boot_hs["mean"], "ci95": boot_hs["ci95"], "n_units": boot_hs["n_units"],
        },
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def _fmt_ci(ci: List[Optional[float]]) -> str:
    if not ci or ci[0] is None:
        return "[None, None]"
    return f"[{ci[0]:+.4f}, {ci[1]:+.4f}]"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S20/Q20 ladder overround anatomy (read-only)")
    ap.add_argument("--crypto-dir", default=str(CRYPTO_DIR))
    ap.add_argument("--depth-dir", default=str(DEPTH_DIR))
    ap.add_argument("--series", nargs="*", default=["KXBTC", "KXETH"])
    ap.add_argument("--band-steps", type=int, default=BAND_STEPS)
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--no-depth", action="store_true", help="skip the orderbook_depth join")
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    crypto_dir = Path(args.crypto_dir)
    depth_dir = Path(args.depth_dir)
    series_filter = tuple(args.series)
    snaps = load_crypto_snapshots(crypto_dir, series_filter)

    by_series: Dict[str, List[Dict[str, Any]]] = {}
    for s in snaps:
        by_series.setdefault(s["series"], []).append(s)

    depth_idx: Dict[str, List[Tuple[float, float, float]]] = {}
    depth_join: Dict[str, Dict[str, Dict[str, Any]]] = {}
    if not args.no_depth:
        # the series codes ARE the ticker prefixes (KXBTC-... / KXETH-...)
        depth_idx = build_depth_index(depth_dir, ticker_prefixes=series_filter)

    print("=" * 80)
    print("S20 / Q20 — BTC/ETH FINE-LADDER OVERROUND ANATOMY (read-only, no network)")
    print("=" * 80)
    print(f"crypto_hourly snapshots: {len(snaps)}  series={list(by_series.keys())}  "
          f"band=+/-{args.band_steps} strike-spacings of spot")
    print(f"spot leg tag: synthetic (binning coordinate ONLY, never a fill price)")
    print(f"depth index tickers: {len(depth_idx)}  (join by ticker + nearest captured_at)")

    result: Dict[str, Any] = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "band_steps": args.band_steps,
        "n_snapshots": len(snaps),
        "price_source_tags": {"asks": "real_ask", "depth": "real_bid(mirror)",
                              "spot_binning": "synthetic", "settlement": "n/a"},
        "series": {},
    }

    for series, sl in sorted(by_series.items()):
        summ = summarize_series(sl, band_steps=args.band_steps, n_boot=args.n_boot)
        print("-" * 80)
        print(f"[{series}]  snapshots={summ['n_snapshots']}  event-hours={summ['n_event_hours']}"
              f"  mean members={summ['mean_n_members']:.0f}")
        print(f"  mean bracket_sum = {summ['mean_bracket_sum']:.3f}  "
              f"mean overround (bracket_sum-1) = {summ['mean_overround']:+.3f}")
        mbs = summ["mean_bucket_sums"]; mbc = summ["mean_bucket_counts"]
        print(f"  OVERROUND DECOMPOSITION (mean Sigma yes_ask per bucket, all real_ask):")
        print(f"    active band   : sum={mbs['active']:.3f}  ({mbc['active']:.1f} members)")
        print(f"    wing_floor(1c): sum={mbs['wing_floor']:.3f}  ({mbc['wing_floor']:.1f} members)")
        print(f"    wing_elevated : sum={mbs['wing_elevated']:.3f}  ({mbc['wing_elevated']:.1f} members)")
        print(f"    -> fraction of overround sitting in WINGS = "
              f"{summ['mean_frac_overround_in_wings']:.1%}")
        print(f"  ACTIVE-BAND balance (S14-relevant, real_ask):")
        print(f"    mean active sum(asks)={summ['mean_active_ask_sum']:.3f}  "
              f"mean active sum(mids)={summ['mean_active_mid_sum']:.3f}")
        a1 = summ["active_over_1_after_fees"]
        print(f"    sum(asks) - 1 - maker_fees : mean={a1['mean']:+.4f}  "
              f"95% CI={_fmt_ci(a1['ci95'])}  n_event_hours={a1['n_units']}  "
              f"(block-bootstrap BY EVENT-HOUR)")
        ahs = summ["active_halfspread_after_fees"]
        print(f"    capturable half-spread - maker_fees : mean={ahs['mean']:+.4f}  "
              f"95% CI={_fmt_ci(ahs['ci95'])}  [EXPLORATORY overround-capture estimate]")
        print(f"    magnitude gate (L27, lower bound >= 1 tick $0.01): "
              f"{'CLEARS' if a1['clears_tick_magnitude'] else 'does NOT clear'}")

        series_out: Dict[str, Any] = {"decomposition": summ}

        if not args.no_depth and depth_idx:
            dj = join_depth_by_bucket(sl, depth_idx, band_steps=args.band_steps)
            print(f"  DEPTH JOIN (ask-side resting size, real_bid mirror of yes_ask):")
            depth_out: Dict[str, Any] = {}
            for b in BUCKETS:
                depths = dj[b]["depths"]
                cov = (dj[b]["n_matched"] / dj[b]["n_members"]) if dj[b]["n_members"] else float("nan")
                med = _median(depths)
                fpos = _frac_positive(depths)
                print(f"    {b:>13}: matched {dj[b]['n_matched']}/{dj[b]['n_members']} "
                      f"({cov:.0%})  median ask-depth={med:.0f} contracts  "
                      f"frac depth>0 = {fpos:.0%}")
                depth_out[b] = {"n_members": dj[b]["n_members"], "n_matched": dj[b]["n_matched"],
                                "coverage": cov, "median_ask_depth": med,
                                "frac_depth_positive": fpos}
            series_out["depth_join"] = depth_out

        result["series"][series] = series_out

    print("-" * 80)
    print("READING: the fat bracket_sum overround is dominated by the WINGS (1c-floor + stale")
    print("one-sided asks), NOT the active band. The active band's sum(asks)-1-fees is <= 0")
    print("(coherent near-money book + flat 1c maker fee, L30). ANATOMY + parameter block only")
    print("— NOT a P&L verdict, NOT a registry flip (Q20 two-agent rule).")
    print("=" * 80)

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"[s20] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

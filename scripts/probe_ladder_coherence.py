"""Probe W-D — ladder coherence on the recovered weather L2 tape (read-only).

Candidate W-D from findings/2026-07-15-weather-revival-dossier.md (kalshi.1 H1, never
run). Falsifiable question: within a single (city, contract-day) 6-bracket MECE ladder,
how often is the ladder EXECUTABLY incoherent at real derived prices, net of Kalshi taker
fees, with real depth-at-touch?

Data (READ-ONLY, opened via `file:...?mode=ro`):
    arb-bot-v2/data/tape_replica/orderbook_archive_recovered.db  (24 GB)
    - orderbook_events: two event_types. We use only `ticker` snapshots (5.85M Kalshi
      rows), which carry the BBO + sizes directly in raw_json:
        yes_bid_dollars / yes_ask_dollars   (DOLLAR units, e.g. "0.6100")
        yes_bid_size_fp / yes_ask_size_fp   (contracts, FLOAT — can be fractional, L47)
      The 95.9M `delta` rows (which would need book reconstruction — size_total is NULL)
      are NOT needed: the ticker feed already resolves the top of book on every change.
    - settlements: 2,112 rows, `result` in {yes,no} (broker_truth). Every weather ladder
      is exactly 6 members with exactly 1 `yes` — a clean MECE partition (verified).

Price semantics / source tags (Hard Rule #3, CLAUDE.md trust defaults):
    Kalshi has no separate ask book — a YES ask IS `1 - best_no_bid` by construction, and
    `yes_ask_dollars` is exactly that derived value with `yes_ask_size_fp` = the resting
    NO-bid size. So `yes_ask` is a real derived ask off a real resting bid (tag `real_ask`).
    For the NO leg we derive `no_ask = 1 - yes_bid` explicitly, depth = `yes_bid_size_fp`
    (the real resting YES bid you lift). Both sides are real resting levels; nothing here
    is synthetic. No `yes_ask`/`no_ask` arithmetic lives outside core.pricing — the sums we
    take are of asks-as-prices for the complete-ladder payout algebra, not ask-as-probability.

The three incoherence classes, on a COMPLETE MECE 6-bracket ladder:
    (a) Buy the whole YES ladder: 1 YES per bracket. Exactly one wins => guaranteed $1.
        Arb iff  sum(yes_ask_i) + sum(fee_i) < 1.00.  net_a = 1 - Sigma_ask - fees_a.
    (b) Buy the whole NO ladder: 1 NO per bracket, no_ask_i = 1 - yes_bid_i. Exactly (n-1)
        win => guaranteed $(n-1). Arb iff  sum(no_ask_i) + fees < (n-1).  Algebraically
        net_b = sum(yes_bid_i) - 1 - fees_b  (i.e. the YES bids sum above $1 net of fees).
    (c) Cross-strike CDF monotonicity: on a MECE ladder of DISJOINT bins with independent
        non-negative bracket prices, the implied CDF (a cumulative sum of non-negatives) is
        monotone BY CONSTRUCTION — there is no fillable adjacent-bin arb (buying bin_i YES
        and selling bin_{i+1} YES is a DIRECTIONAL spread, not a hedge, because the bins are
        mutually exclusive, not nested). No separate cumulative/nested ">=X" markets exist
        for these days in this tape. So (c) reduces to (a)/(b): a whole-ladder CDF
        inconsistency IS the sum-off-from-$1 arb. We report this structurally rather than
        manufacturing a non-executable "opportunity". (This is the honest read, not a dodge.)

Executability (a descriptive incoherence is NOT a verdict):
    - depth-at-touch: min leg size across the 6 legs must be >= MIN_DEPTH contracts.
    - duration: the incoherence must persist for >= MIN_SNAPS consecutive joint snapshots.
    - net of fees: fee_per_contract per leg from core.pricing (never hand-rolled, L18).
    We report the joint distribution (magnitude x duration x min-depth), then block-bootstrap
    (block = ladder / contract-day, L6) the mean net profit per executable ladder-completion
    if any class is frequent enough to matter. Bootstrap + gates via core.bootstrap.

Run:  python scripts/probe_ladder_coherence.py            # full 352-ladder pass
      python scripts/probe_ladder_coherence.py --limit-ladders 5
      python scripts/probe_ladder_coherence.py --sample-ladder KXHIGHTBOS-26APR17
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.bootstrap import (  # noqa: E402
    block_bootstrap,
    bootstrap_verdict_admissible,
    clears_tick_magnitude,
)
from core.pricing import TAKER_FEE_RATE, fee_per_contract  # noqa: E402

DEFAULT_DB = ("/Users/ryan.gillon/Active/01-projects/arb-bot-v2/data/"
              "tape_replica/orderbook_archive_recovered.db")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "reports")

# Executability floors (from the milestone spec).
MIN_DEPTH = 10.0    # contracts of depth-at-touch on the thinnest leg
MIN_SNAPS = 2       # consecutive joint snapshots the incoherence must survive
TICK = 0.01         # 1-cent fillable tick, for the L27 magnitude gate


# ───────────────────────── pure helpers (unit-tested offline) ─────────────────────────

def ladder_key(ticker: str) -> str:
    """The (series+city, contract-day) key: the ticker minus its final -BRACKET segment.
    'KXHIGHTBOS-26APR17-B65.5' -> 'KXHIGHTBOS-26APR17'; bracket labels use '.', not '-',
    so a single rsplit is unambiguous."""
    return ticker.rsplit("-", 1)[0]


def _to_float(v) -> Optional[float]:
    """Parse a dollar/size string to float; empty string / None / unparsable -> None.
    A price of exactly 0 on a BID means the side is absent (no fillable resting order)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f


def yes_ladder_arb(yes_asks: Sequence[float], rate: float = TAKER_FEE_RATE) -> dict:
    """Class (a): buy 1 YES per bracket on a complete MECE ladder -> guaranteed $1.
    net = 1.00 - sum(yes_ask_i) - sum(fee(yes_ask_i)). Positive net = a real fillable arb."""
    sum_ask = sum(float(a) for a in yes_asks)
    fees = sum(fee_per_contract(float(a), rate) for a in yes_asks)
    return {"sum_ask": sum_ask, "fees": fees, "net": 1.0 - sum_ask - fees}


def no_ladder_arb(yes_bids: Sequence[float], n_members: int,
                  rate: float = TAKER_FEE_RATE) -> dict:
    """Class (b): buy 1 NO per bracket, no_ask_i = 1 - yes_bid_i -> guaranteed $(n-1).
    net = (n-1) - sum(no_ask_i) - sum(fee(no_ask_i)) = sum(yes_bid_i) - 1 - fees."""
    no_asks = [1.0 - float(b) for b in yes_bids]
    sum_no_ask = sum(no_asks)
    fees = sum(fee_per_contract(a, rate) for a in no_asks)
    return {"sum_no_ask": sum_no_ask, "fees": fees,
            "net": (n_members - 1) - sum_no_ask - fees}


# ───────────────────────── tape reconstruction ─────────────────────────

def load_ladders(con: sqlite3.Connection) -> Dict[str, dict]:
    """Weather ladders from settlements (broker_truth): members + winner. Only complete
    6-member, exactly-1-yes ladders are kept (verified to be all 352)."""
    cur = con.cursor()
    rows = cur.execute(
        "SELECT ticker, result FROM settlements WHERE platform='kalshi'").fetchall()
    lad: Dict[str, dict] = defaultdict(lambda: {"members": [], "winner": None})
    for tk, res in rows:
        if not (tk.startswith("KXHIGH") or tk.startswith("KXLOWT")):
            continue
        k = ladder_key(tk)
        lad[k]["members"].append(tk)
        if res == "yes":
            lad[k]["winner"] = tk
    return {k: v for k, v in lad.items()
            if len(v["members"]) == 6 and v["winner"] is not None}


def joint_snapshots(con: sqlite3.Connection, members: Sequence[str]) -> List[dict]:
    """Reconstruct forward-filled joint ladder states from per-member `ticker` snapshots.
    A member's last-seen BBO is its current resting book until the feed emits a change, so
    forward-fill is a valid reconstruction (Kalshi emits a ticker on any BBO move). We emit
    a joint snapshot on every event once all 6 members have been seen at least once; dt to
    the next event is that snapshot's opportunity-window (seconds it stays resting)."""
    cur = con.cursor()
    ph = ",".join("?" * len(members))
    rows = cur.execute(
        f"SELECT ticker, ts_utc, raw_json FROM orderbook_events "
        f"WHERE ticker IN ({ph}) AND event_type='ticker' ORDER BY ts_utc",
        list(members)).fetchall()

    state: Dict[str, dict] = {}
    events: List[dict] = []
    for tk, ts, rj in rows:
        d = json.loads(rj)
        state[tk] = {
            "yes_bid": _to_float(d.get("yes_bid_dollars")),
            "yes_ask": _to_float(d.get("yes_ask_dollars")),
            "yes_bid_size": _to_float(d.get("yes_bid_size_fp")),
            "yes_ask_size": _to_float(d.get("yes_ask_size_fp")),
        }
        if len(state) < len(members):
            continue
        ts_dt = datetime.fromisoformat(ts)
        events.append({"ts": ts, "ts_dt": ts_dt,
                       "state": {m: dict(state[m]) for m in members}})
    # attach dt-to-next (opportunity-seconds); last snapshot gets 0
    for i, ev in enumerate(events):
        if i + 1 < len(events):
            ev["dt_s"] = (events[i + 1]["ts_dt"] - ev["ts_dt"]).total_seconds()
        else:
            ev["dt_s"] = 0.0
    return events


def _leg_prices(state: dict, members: Sequence[str]):
    """Return (yes_asks, yes_ask_sizes, yes_bids, yes_bid_sizes) or None if a side is
    not fully executable (any leg missing a fillable ask/bid: a price of 0/None on a bid
    means the side is absent -> no_ask = $1, unfillable, the L26 mirror)."""
    yes_asks, yes_ask_sizes, yes_bids, yes_bid_sizes = [], [], [], []
    ask_ok = bid_ok = True
    for m in members:
        s = state[m]
        ya, yas = s["yes_ask"], s["yes_ask_size"]
        yb, ybs = s["yes_bid"], s["yes_bid_size"]
        # a fillable ask needs a price in (0,1) with positive size
        if ya is None or ya <= 0.0 or ya >= 1.0 or not yas or yas <= 0:
            ask_ok = False
        if yb is None or yb <= 0.0 or yb >= 1.0 or not ybs or ybs <= 0:
            bid_ok = False
        yes_asks.append(ya if ya is not None else float("nan"))
        yes_ask_sizes.append(yas if yas else 0.0)
        yes_bids.append(yb if yb is not None else float("nan"))
        yes_bid_sizes.append(ybs if ybs else 0.0)
    return yes_asks, yes_ask_sizes, yes_bids, yes_bid_sizes, ask_ok, bid_ok


# ───────────────────────── per-ladder evaluation ─────────────────────────

def evaluate_ladder(key: str, members: Sequence[str], events: List[dict]) -> dict:
    """Walk the joint snapshots, score classes (a) and (b), collapse consecutive
    incoherent snapshots into opportunity runs (duration x min-depth x magnitude)."""
    n = len(members)
    per_snap = []
    for ev in events:
        yes_asks, yas, yes_bids, ybs, ask_ok, bid_ok = _leg_prices(ev["state"], members)
        rec = {"ts": ev["ts"], "dt_s": ev["dt_s"]}
        # class (a)
        if ask_ok:
            a = yes_ladder_arb(yes_asks)
            rec["a_net"] = a["net"]
            rec["a_sum_ask"] = a["sum_ask"]
            rec["a_min_depth"] = min(yas)
        else:
            rec["a_net"] = None
        # class (b)
        if bid_ok:
            b = no_ladder_arb(yes_bids, n)
            rec["b_net"] = b["net"]
            rec["b_sum_yes_bid"] = sum(yes_bids)
            rec["b_min_depth"] = min(ybs)
        else:
            rec["b_net"] = None
        per_snap.append(rec)

    opps = {"a": _runs(per_snap, "a"), "b": _runs(per_snap, "b")}
    # descriptive coverage: seconds spent raw-incoherent (pre-depth, pre-duration)
    total_s = sum(r["dt_s"] for r in per_snap)
    a_raw_s = sum(r["dt_s"] for r in per_snap
                  if r.get("a_net") is not None and r["a_sum_ask"] < 1.0)
    a_net_s = sum(r["dt_s"] for r in per_snap
                  if r.get("a_net") is not None and r["a_net"] > 0)
    b_raw_s = sum(r["dt_s"] for r in per_snap
                  if r.get("b_net") is not None and r["b_sum_yes_bid"] > 1.0)
    b_net_s = sum(r["dt_s"] for r in per_snap
                  if r.get("b_net") is not None and r["b_net"] > 0)
    return {
        "ladder": key, "n_snaps": len(per_snap), "total_seconds": total_s,
        "a_raw_seconds": a_raw_s, "a_net_seconds": a_net_s,
        "b_raw_seconds": b_raw_s, "b_net_seconds": b_net_s,
        "opps": opps,
    }


def _runs(per_snap: List[dict], cls: str) -> List[dict]:
    """Collapse maximal runs of consecutive snapshots with net>0 for class `cls` into
    opportunity records. Each run: duration in snapshots + seconds, min-depth over the run
    (the binding fillable size), entry/peak net. A run is `executable` iff it survives
    >= MIN_SNAPS snapshots AND its min-depth over the run is >= MIN_DEPTH."""
    net_k, depth_k = f"{cls}_net", f"{cls}_min_depth"
    runs, cur = [], None
    for r in per_snap:
        net = r.get(net_k)
        if net is not None and net > 0:
            if cur is None:
                cur = {"start_ts": r["ts"], "snaps": 0, "seconds": 0.0,
                       "min_depth": float("inf"), "entry_net": net, "peak_net": net}
            cur["snaps"] += 1
            cur["seconds"] += r["dt_s"]
            cur["min_depth"] = min(cur["min_depth"], r[depth_k])
            cur["peak_net"] = max(cur["peak_net"], net)
        else:
            if cur is not None:
                runs.append(cur)
                cur = None
    if cur is not None:
        runs.append(cur)
    for run in runs:
        run["executable"] = (run["snaps"] >= MIN_SNAPS and run["min_depth"] >= MIN_DEPTH)
    return runs


# ───────────────────────── driver ─────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--limit-ladders", type=int, default=None)
    ap.add_argument("--sample-ladder", default=None)
    ap.add_argument("--out", default=os.path.join(REPORTS_DIR, "ladder_coherence"))
    args = ap.parse_args()

    os.makedirs(REPORTS_DIR, exist_ok=True)
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)

    ladders = load_ladders(con)
    keys = sorted(ladders)
    if args.sample_ladder:
        keys = [k for k in keys if k == args.sample_ladder]
    if args.limit_ladders:
        keys = keys[:args.limit_ladders]
    print(f"[probe] {len(keys)} ladders to evaluate (of {len(ladders)} weather ladders)")

    opp_path = args.out + "_opps.jsonl"
    per_ladder = []
    # per-ladder value lists for the block bootstrap (executable opportunities only)
    a_exec_vals: Dict[str, List[float]] = {}
    b_exec_vals: Dict[str, List[float]] = {}
    # descriptive tallies
    n_a_raw = n_a_net = n_a_exec = 0
    n_b_raw = n_b_net = n_b_exec = 0
    a_net_magnitudes, a_exec_magnitudes = [], []
    b_net_magnitudes, b_exec_magnitudes = [], []

    with open(opp_path, "w") as opp_f:
        for i, k in enumerate(keys):
            members = sorted(ladders[k]["members"])
            events = joint_snapshots(con, members)
            res = evaluate_ladder(k, members, events)
            per_ladder.append({kk: res[kk] for kk in
                               ("ladder", "n_snaps", "total_seconds", "a_raw_seconds",
                                "a_net_seconds", "b_raw_seconds", "b_net_seconds")})
            for cls, exec_vals, raw_c, net_c, exec_c, net_mag, exec_mag in (
                ("a", a_exec_vals, "n_a_raw", "n_a_net", "n_a_exec",
                 a_net_magnitudes, a_exec_magnitudes),
                ("b", b_exec_vals, "n_b_raw", "n_b_net", "n_b_exec",
                 b_net_magnitudes, b_exec_magnitudes),
            ):
                for run in res["opps"][cls]:
                    if net_c == "n_a_net":
                        n_a_net += 1
                        a_net_magnitudes.append(run["entry_net"])
                    else:
                        n_b_net += 1
                        b_net_magnitudes.append(run["entry_net"])
                    row = {"ladder": k, "class": cls, **run}
                    opp_f.write(json.dumps(row) + "\n")
                    if run["executable"]:
                        exec_vals.setdefault(k, []).append(run["entry_net"])
                        if cls == "a":
                            n_a_exec += 1
                            a_exec_magnitudes.append(run["entry_net"])
                        else:
                            n_b_exec += 1
                            b_exec_magnitudes.append(run["entry_net"])
            # raw-incoherence snapshot tallies (pre-duration) for context
            if (i + 1) % 50 == 0:
                print(f"[probe] {i + 1}/{len(keys)} ladders processed")

    con.close()

    # ── bootstrap any executable class (block = ladder/contract-day, L6) ──
    def summarize(vals: Dict[str, List[float]], label: str) -> dict:
        if not vals:
            return {"class": label, "n_units": 0, "n_opps": 0, "verdict": "no executable opportunities"}
        boot = block_bootstrap(vals)
        adm = bootstrap_verdict_admissible(vals, min_units=10)
        mag = clears_tick_magnitude(boot["ci95"], tick=TICK)
        n_opps = sum(len(v) for v in vals.values())
        alive = (boot["ci95"][0] is not None and boot["ci95"][0] > 0
                 and mag and adm["admissible"])
        return {"class": label, "n_units": boot["n_units"], "n_opps": n_opps,
                "mean": boot["mean"], "ci95": boot["ci95"],
                "clears_tick_magnitude": mag, "admissible": adm,
                "verdict": "ALIVE-worth-verifying" if alive else "DEAD"}

    a_boot = summarize(a_exec_vals, "a_buy_yes_ladder")
    b_boot = summarize(b_exec_vals, "b_buy_no_ladder")

    def dist(mags: List[float]) -> dict:
        if not mags:
            return {"n": 0}
        s = sorted(mags)
        return {"n": len(s), "min": s[0], "p50": s[len(s) // 2], "max": s[-1],
                "mean": sum(s) / len(s)}

    summary = {
        "probe": "W-D ladder coherence (weather L2 recovered tape)",
        "db": args.db,
        "n_ladders": len(keys),
        "min_depth_contracts": MIN_DEPTH, "min_snaps": MIN_SNAPS, "fee_rate": TAKER_FEE_RATE,
        "class_a_buy_yes": {
            "n_net_positive_runs": n_a_net, "n_executable_runs": n_a_exec,
            "net_positive_magnitude_dist": dist(a_net_magnitudes),
            "executable_magnitude_dist": dist(a_exec_magnitudes),
            "bootstrap": a_boot,
        },
        "class_b_buy_no": {
            "n_net_positive_runs": n_b_net, "n_executable_runs": n_b_exec,
            "net_positive_magnitude_dist": dist(b_net_magnitudes),
            "executable_magnitude_dist": dist(b_exec_magnitudes),
            "bootstrap": b_boot,
        },
        "class_c_cdf_monotonicity": (
            "NOT EXECUTABLE on a MECE disjoint-bin ladder: the implied CDF is a cumulative "
            "sum of independent non-negative bracket prices, hence monotone by construction; "
            "no nested/cumulative markets exist for these days to arb. Reduces to (a)/(b)."),
        "per_ladder_seconds": per_ladder,
    }
    out_path = args.out + "_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)

    print("\n===== LADDER COHERENCE PROBE =====")
    print(f"ladders: {len(keys)}   opp rows -> {opp_path}   summary -> {out_path}")
    for cls, boot, nnet, nexec in (("(a) buy YES ladder", a_boot, n_a_net, n_a_exec),
                                   ("(b) buy NO ladder", b_boot, n_b_net, n_b_exec)):
        print(f"\n{cls}: net>0 runs={nnet}  executable runs (>= {int(MIN_DEPTH)} "
              f"contracts & >= {MIN_SNAPS} snaps)={nexec}")
        print(f"   bootstrap: {json.dumps(boot)}")
    print("\n(c) CDF monotonicity: not executable on MECE disjoint bins (see summary).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

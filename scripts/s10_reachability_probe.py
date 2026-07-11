#!/usr/bin/env python3
"""s10_reachability_probe.py — S10 crypto-hourly reachability-decay first cut (LOOP-QUEUE Q7).

The hypothesis (S10, kb/strategies/00-index.md row 22 / lines 127-129): far crypto-hourly
range-brackets stay priced *above* their remaining-time reachability as the hour elapses
(retail under-updates the tails), so late in the hour a taker could fade an over-priced,
essentially-unreachable bracket — sell the rich YES, i.e. **buy NO** — for a fee-clearing
edge. The gate: "T-5/2 reachability vs ask > overround+fee; clear artifact floor; bootstrap
by hour; CI>0". The queue item's own warning: this MUST clear Kalshi's 1c minimum-tick
"artifact noise floor" and the chunky longshot fee.

What this probe actually has, and how it substitutes for a reachability model
--------------------------------------------------------------------------------
There is no continuous intra-hour tape. Two collectors (cloud + VPS) hit the same hourly
group at different offsets, so ~190/240 (symbol, event_ticker) groups carry 2-3 `real_ask`
captures at different `captured_at` within the hour (typically one ~30-48min-before-close
EARLY capture and one ~5-6min-before-close LATE capture). That is the only within-hour time
variation available.

Rather than fabricate a stochastic hitting-probability model from thin data, this probe uses
the **realized settlement** as ground truth (`broker_truth`): for each genuinely-far bracket
(one the market ITSELF already parks at/near the 1c YES floor at the EARLY capture — the
market's own near-zero-probability judgment, no external vol model invented), it prices the
mechanically-available taker trade — **buy NO at the LATE capture's `no_ask`** — and books its
realized P&L against whether the bracket actually settled in-band. Fees come from
`core.pricing.fee_per_contract` (never hand-rolled — lesson L18). The realized outcome is more
defensible than a modeled reachability given the sample.

The trade booked, explicitly:
    cost   = no_ask                      (real_ask, the LATE capture's NO ask)
    fee    = fee_per_contract(no_ask)    (core.pricing, taker rate)
    payout = $1 if the bracket settled NO (did not hit), else $0   (broker_truth)
    pnl    = payout - cost - fee

The structural cap this immediately exposes: for a genuinely-far bracket the YES ask sits at
the 1c tick floor, which means `yes_bid` is 0 and therefore `no_ask` is pinned at $1.00 — so
the trade costs a full dollar to (at best) win a dollar back. The 1c minimum tick on the YES
side mirrors into a $1.00 NO ask; there is nothing to decay *below* a floor that was already
hit at the EARLY capture. This is precisely the artifact floor the gate demanded be cleared,
observed from the market's own book.

Read-only over `tape/crypto_hourly/dt=*.jsonl` (FILES only — the stray
`tape/crypto_hourly/dt=2026-07-10/` directory of unrelated raw blobs is skipped by the
`*.jsonl` glob and an explicit is_file guard; lesson L25). Never mutates tape, no network,
no order code.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from collection.crypto_hourly import previous_hour_event_ticker
from core.io import REPO_ROOT
from core.pricing import fee_per_contract

TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly"

# "Far" = the market's own near-zero-probability judgment at the EARLY capture: a YES ask at
# (0.01) or near (0.02) Kalshi's 1c minimum tick. The sweep relaxes the definition to show
# what happens as less-far (genuinely-reachable, real-hit-risk) brackets are pulled in.
FLOOR_THRESHOLD = 0.01
THRESHOLD_SWEEP = [0.01, 0.02, 0.05, 0.10]


# --------------------------------------------------------------------------- #
# join arithmetic (pure — no clock, no network)
# --------------------------------------------------------------------------- #
def next_hour_event_ticker(event_ticker: str) -> Optional[str]:
    """Inverse of `collection.crypto_hourly.previous_hour_event_ticker`: the event one hour
    AHEAD. A given event X's settlement is reported in the pass whose `current.event_ticker`
    is X+1h (that pass carries X as its `previous_settlement`). Round-trips with
    `previous_hour_event_ticker` — that identity is what makes the settlement join sound."""
    series_part, sep, token = event_ticker.partition("-")
    if not sep:
        return None
    from collection.crypto_hourly import parse_hour_token  # local import: pure helper
    from datetime import timedelta

    dt = parse_hour_token(token)
    if dt is None:
        return None
    nxt = dt + timedelta(hours=1)
    return f"{series_part}-{nxt.strftime('%y%b%d%H').upper()}"


# --------------------------------------------------------------------------- #
# loading (read-only; FILES only, never the stray dt= directory — lesson L25)
# --------------------------------------------------------------------------- #
def load_records(tape_dir: Path = TAPE_DIR) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for path in sorted(tape_dir.glob("dt=*.jsonl")):
        if not path.is_file():
            continue  # belt-and-suspenders: a dt=<date> directory would not match *.jsonl anyway
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    return records


def build_settlement_map(records: List[Dict[str, Any]]) -> Dict[Tuple[str, str], Dict[str, Any]]:
    """(symbol, settled event_ticker) -> the `broker_truth` settlement block. An event X's
    settlement is carried by the pass whose `previous_settlement.event_ticker == X`; that pass'
    own `current.event_ticker` is `next_hour_event_ticker(X)` (join arithmetic). We key the
    map directly by the settled event so the lookup is O(1) at use."""
    out: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for r in records:
        ps = r.get("previous_settlement", {})
        if ps.get("status") != "settled":
            continue
        et = ps.get("event_ticker")
        if not et:
            continue
        out[(r["symbol"], et)] = ps
    return out


def group_current_captures(records: List[Dict[str, Any]]
                           ) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    """(symbol, current event_ticker) -> all records that captured that hour's `real_ask`
    bracket book (status ok)."""
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for r in records:
        cur = r.get("current", {})
        if cur.get("status") != "ok":
            continue
        et = cur.get("event_ticker")
        if not et:
            continue
        groups.setdefault((r["symbol"], et), []).append(r)
    return groups


# --------------------------------------------------------------------------- #
# far-bracket detection + the mechanically-available taker trade (pure)
# --------------------------------------------------------------------------- #
def far_bracket_tickers(early_record: Dict[str, Any], threshold: float = FLOOR_THRESHOLD
                        ) -> List[str]:
    """Tickers the market ITSELF prices at/near the 1c YES floor at the EARLY capture — i.e.
    already near-zero probability well before close (no external vol model). `threshold`
    selects how far: 0.01 = strictly floor-pinned, higher pulls in less-far brackets."""
    out: List[str] = []
    for o in early_record.get("current", {}).get("outcomes", []):
        ya = o.get("yes_ask")
        if ya is not None and ya <= threshold:
            out.append(o["ticker"])
    return out


def no_buy_edge(no_ask: float, settled_no: bool, rate: Optional[float] = None) -> float:
    """Realized dollar P&L of the mechanically-available taker trade — buy NO at `no_ask`:
    payout ($1 if the bracket settled NO / did not hit, else $0) minus cost minus the taker
    fee from `core.pricing.fee_per_contract` (never hand-rolled). A genuinely-far bracket has
    `no_ask` pinned at $1.00 (the 1c YES-tick floor mirrored), so this is capped at ~$0."""
    fee = fee_per_contract(no_ask) if rate is None else fee_per_contract(no_ask, rate)
    payout = 1.0 if settled_no else 0.0
    return payout - float(no_ask) - fee


@dataclass
class Trade:
    hour_key: str            # "SYMBOL|event_ticker" — the independent bootstrap unit
    symbol: str
    event_ticker: str
    bracket_ticker: str
    early_yes_ask: float     # real_ask
    late_yes_ask: Optional[float]  # real_ask
    entry_no_ask: float      # real_ask — the price the taker actually pays for NO
    entry_fee: float         # core.pricing.fee_per_contract
    settled_result: str      # broker_truth: 'yes' (hit) / 'no' (did not hit)
    settled_no: bool
    realized_pnl: float      # payout(broker_truth) - entry_no_ask(real_ask) - fee
    has_room: bool           # entry_no_ask < 1.00 — a taker NO trade with any profit room
    price_source_tag: str = "real_ask"        # the entry price
    settlement_source_tag: str = "broker_truth"  # the outcome


def candidate_trades(groups: Dict[Tuple[str, str], List[Dict[str, Any]]],
                     settle_map: Dict[Tuple[str, str], Dict[str, Any]],
                     threshold: float = FLOOR_THRESHOLD) -> List[Trade]:
    """For every (symbol, event) group with >=2 distinct `captured_at` and a resolved
    settlement: EARLY = first capture, LATE = last. For each far bracket (early yes_ask <=
    threshold), book the buy-NO taker trade at the LATE capture price against realized
    settlement (broker_truth). Skips brackets with
    no late quote, no no_ask, or an unresolved per-bracket result (never guessed)."""
    trades: List[Trade] = []
    for (symbol, event_ticker), rs in groups.items():
        if len({r["captured_at"] for r in rs}) < 2:
            continue
        settle = settle_map.get((symbol, event_ticker))
        if settle is None:
            continue
        results = settle.get("results", {})
        ordered = sorted(rs, key=lambda r: r["captured_at"])
        early, late = ordered[0], ordered[-1]
        late_by_ticker = {o["ticker"]: o for o in late.get("current", {}).get("outcomes", [])}
        early_by_ticker = {o["ticker"]: o for o in early.get("current", {}).get("outcomes", [])}
        for tk in far_bracket_tickers(early, threshold):
            lt = late_by_ticker.get(tk)
            if lt is None:
                continue
            no_ask = lt.get("no_ask")
            if no_ask is None:
                continue
            res = results.get(tk)
            if res not in ("yes", "no"):
                continue  # unresolved / disagreeing per-bracket truth — drop, never guess
            settled_no = res == "no"
            pnl = no_buy_edge(no_ask, settled_no)
            trades.append(Trade(
                hour_key=f"{symbol}|{event_ticker}", symbol=symbol,
                event_ticker=event_ticker, bracket_ticker=tk,
                early_yes_ask=float(early_by_ticker[tk]["yes_ask"]),
                late_yes_ask=(float(lt["yes_ask"]) if lt.get("yes_ask") is not None else None),
                entry_no_ask=float(no_ask), entry_fee=fee_per_contract(no_ask),
                settled_result=res, settled_no=settled_no, realized_pnl=pnl,
                has_room=float(no_ask) < 1.0,
            ))
    return trades


# --------------------------------------------------------------------------- #
# block bootstrap BY HOUR (never by bracket — brackets within an hour are not
# independent draws; lesson L6 / CLAUDE.md / S7c)
# --------------------------------------------------------------------------- #
def block_bootstrap_by_hour(trades: List[Trade], n_boot: int = 10000, seed: int = 42
                            ) -> Dict[str, Any]:
    """Resample HOUR blocks with replacement, pool their trades, report the pooled-mean
    realized P&L distribution. The independent unit is the hour, not the bracket."""
    by_hour: Dict[str, List[float]] = {}
    for t in trades:
        by_hour.setdefault(t.hour_key, []).append(t.realized_pnl)
    hours = list(by_hour.keys())
    if not hours:
        return {"n_hours": 0, "n_trades": 0, "mean": None, "ci95": [None, None]}
    total = sum(sum(v) for v in by_hour.values())
    count = sum(len(v) for v in by_hour.values())
    grand_mean = total / count

    rng = random.Random(seed)
    means: List[float] = []
    for _ in range(n_boot):
        tot = 0.0
        cnt = 0
        for _ in hours:
            v = by_hour[rng.choice(hours)]
            tot += sum(v)
            cnt += len(v)
        means.append(tot / cnt)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return {
        "n_hours": len(hours), "n_trades": count, "mean": grand_mean,
        "ci95": [lo, hi], "n_boot": n_boot, "seed": seed,
        "price_source_tag": "real_ask", "settlement_source_tag": "broker_truth",
    }


def decay_stats(trades: List[Trade]) -> Dict[str, Any]:
    """Descriptive: does the far-bracket YES ask actually decay early->late? (It cannot fall
    below the 1c floor it already sits at — this quantifies exactly that.)"""
    changes = [t.late_yes_ask - t.early_yes_ask for t in trades if t.late_yes_ask is not None]
    if not changes:
        return {"n": 0}
    return {
        "n": len(changes),
        "mean_yes_ask_change": sum(changes) / len(changes),
        "n_decayed": sum(1 for c in changes if c < 0),
        "n_rose": sum(1 for c in changes if c > 0),
        "n_unchanged": sum(1 for c in changes if c == 0),
        "price_source_tag": "real_ask",
    }


def threshold_report(groups, settle_map, threshold: float) -> Dict[str, Any]:
    trades = candidate_trades(groups, settle_map, threshold)
    n = len(trades)
    if n == 0:
        return {"threshold": threshold, "n_trades": 0}
    room = sum(1 for t in trades if t.has_room)
    settled_no = sum(1 for t in trades if t.settled_no)
    pos = sum(1 for t in trades if t.realized_pnl > 0)
    mean = sum(t.realized_pnl for t in trades) / n
    hours = {t.hour_key for t in trades}
    return {
        "threshold": threshold, "n_trades": n, "n_hours": len(hours),
        "n_has_room_no_ask_lt_1": room, "frac_has_room": room / n,
        "n_settled_no": settled_no, "frac_settled_no": settled_no / n,
        "n_pnl_positive": pos, "frac_pnl_positive": pos / n,
        "mean_realized_pnl": mean,
        "price_source_tag": "real_ask", "settlement_source_tag": "broker_truth",
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="S10 crypto reachability-decay first cut (read-only)")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--n-boot", type=int, default=10000)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)

    records = load_records(Path(args.tape_dir))
    settle_map = build_settlement_map(records)
    groups = group_current_captures(records)

    multi = {k: v for k, v in groups.items() if len({r["captured_at"] for r in v}) >= 2}
    resolved = {k for k in multi if k in settle_map}

    sweep = [threshold_report(groups, settle_map, t) for t in THRESHOLD_SWEEP]
    primary_trades = candidate_trades(groups, settle_map, FLOOR_THRESHOLD)
    boot = block_bootstrap_by_hour(primary_trades, n_boot=args.n_boot)
    decay = decay_stats(primary_trades)

    result = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_records": len(records),
        "n_current_groups": len(groups),
        "n_multi_capture_groups": len(multi),
        "n_multi_capture_resolved_groups": len(resolved),
        "floor_threshold": FLOOR_THRESHOLD,
        "threshold_sweep": sweep,
        "decay_far_yes_ask": decay,
        "bootstrap_by_hour_primary": boot,
    }

    print(f"[s10] {len(records)} records, {len(groups)} current groups, "
          f"{len(multi)} multi-capture, {len(resolved)} multi-capture+resolved")
    print(f"[s10] far-bracket decay (early->late yes_ask, thr={FLOOR_THRESHOLD}): "
          f"n={decay.get('n')} mean_change={decay.get('mean_yes_ask_change')}")
    for row in sweep:
        if row.get("n_trades", 0) == 0:
            print(f"  thr={row['threshold']}: 0 trades")
            continue
        print(f"  thr={row['threshold']}: n_trades={row['n_trades']} n_hours={row['n_hours']} "
              f"has_room={row['n_has_room_no_ask_lt_1']}({row['frac_has_room']:.2%}) "
              f"settled_NO={row['frac_settled_no']:.3%} "
              f"pnl>0={row['n_pnl_positive']}({row['frac_pnl_positive']:.3%}) "
              f"mean_pnl={row['mean_realized_pnl']:+.6f} [real_ask/broker_truth]")
    if boot["mean"] is not None:
        print(f"[s10] block-bootstrap-by-hour (thr={FLOOR_THRESHOLD}): "
              f"n_hours={boot['n_hours']} n_trades={boot['n_trades']} "
              f"mean_pnl={boot['mean']:+.6f} "
              f"95% CI [{boot['ci95'][0]:+.6f}, {boot['ci95'][1]:+.6f}] [real_ask/broker_truth]")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2, default=str))
        print(f"[s10] wrote {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

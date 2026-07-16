"""Deep-dive inspector for the executable opportunities W-D flags (read-only).

The verdict hinges on a handful of runs that pass the depth+duration+fee gates. This tool
reconstructs the full 6-leg book at each such run's entry instant so a human/verifier can
see whether it is a real transient crossed book or a settlement/empty-book artifact
(L26/L65 family: near close Kalshi thins/empties the book and asks collapse to the 1c floor,
producing an apparent but unfillable "sum of asks << $1").
"""
from __future__ import annotations
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.probe_ladder_coherence import (  # noqa: E402
    DEFAULT_DB, load_ladders, joint_snapshots, _to_float,
)

REPORTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")


def main() -> int:
    db = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    opps = [json.loads(l) for l in open(os.path.join(REPORTS, "ladder_coherence_opps.jsonl"))]
    execs = [o for o in opps if o["executable"]]
    print(f"{len(execs)} executable opportunities of {len(opps)} net>0 runs\n")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    ladders = load_ladders(con)
    for o in execs:
        k = o["ladder"]
        members = sorted(ladders[k]["members"])
        winner = ladders[k]["winner"]
        events = joint_snapshots(con, members)
        if not events:
            continue
        ts_first = events[0]["ts_dt"]
        ts_last = events[-1]["ts_dt"]
        # find the entry snapshot
        ev = next((e for e in events if e["ts"] == o["start_ts"]), None)
        if ev is None:
            continue
        mins_from_last = (ts_last - ev["ts_dt"]).total_seconds() / 60.0
        span_h = (ts_last - ts_first).total_seconds() / 3600.0
        print(f"=== {k}  class {o['class']}  net={o['entry_net']:.4f}  "
              f"min_depth={o['min_depth']:.0f}  snaps={o['snaps']}  secs={o['seconds']:.1f}")
        print(f"    entry {o['start_ts']}  |  {mins_from_last:.1f} min before last capture "
              f"(ladder span {span_h:.1f}h)  |  winner={winner}")
        sum_ask = sum_bid = 0.0
        for m in members:
            s = ev["state"][m]
            mark = " <-- WINNER" if m == winner else ""
            ya = s["yes_ask"]; yb = s["yes_bid"]
            if ya is not None:
                sum_ask += ya
            if yb is not None:
                sum_bid += yb
            print(f"      {m:26s} yes_bid={_fmt(yb)} (sz {_fmt(s['yes_bid_size'])})  "
                  f"yes_ask={_fmt(ya)} (sz {_fmt(s['yes_ask_size'])}){mark}")
        print(f"      Sigma yes_ask={sum_ask:.4f}   Sigma yes_bid={sum_bid:.4f}\n")
    con.close()
    return 0


def _fmt(x):
    return "  -  " if x is None else f"{x:.4f}" if x < 5 else f"{x:.1f}"


if __name__ == "__main__":
    raise SystemExit(main())

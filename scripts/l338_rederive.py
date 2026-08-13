#!/usr/bin/env python3
"""l338_rederive.py — independent re-derivation of the L338 scope audit's headline.

REDUNDANCY, NOT VERIFICATION. No `Task`/subagent tool exists in this harness (the
L287/L288/L290/L291/L295/L308/L313/L325 precedent), so the two-agent rule could not be
satisfied by an independent `verifier` agent. This module is the sanctioned fallback: a
second implementation that shares NO code with `scripts/l338_trend_claim_scope_audit.py`
and is not imported by it. It cannot catch an error both implementations share and is
never claimed to.

Deliberately different at every step:
  * its own JSONL reader (no `load_depth`/`load_prints`);
  * its own ISO-8601 -> epoch conversion by STRING SLICING plus a day-offset arithmetic,
    never `core.timeutil.parse_iso_utc` (pinned equal to it on real timestamps by
    `tests/test_l338_rederive.py`);
  * a linear MERGE walk over two time-sorted sequences instead of a per-print binary
    search, so an off-by-one in either index scheme cannot cancel out;
  * the two join rules expressed as an explicit `(prev_idx, has_next)` pair rather than as
    a bounds condition.

Reproduces, for the bid side: the 2x2 grid's admitted counts and agreement rates, and the
claim that the POPULATION factor moves nothing while the JOIN RULE flips the direction.

READ-ONLY, fully OFFLINE. No network, no credentials, no order path. No P&L, no CI.

    python3 scripts/l338_rederive.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

DAY = "2026-08-03"
_DAYS_BEFORE_MONTH = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)


def epoch_seconds(stamp: str) -> float:
    """ISO-8601 UTC -> epoch seconds, by string slicing and civil-date arithmetic.

    Handles a trailing `Z` or a `+00:00` offset and an optional fractional second. This
    repo's tapes are UTC-only by construction, so no zone database is consulted.
    """
    year = int(stamp[0:4])
    month = int(stamp[5:7])
    day = int(stamp[8:10])
    hour = int(stamp[11:13])
    minute = int(stamp[14:16])
    second = int(stamp[17:19])
    frac = 0.0
    if len(stamp) > 19 and stamp[19] == ".":
        i = 20
        while i < len(stamp) and stamp[i].isdigit():
            i += 1
        frac = float(stamp[19:i])

    def leaps(y: int) -> int:
        return y // 4 - y // 100 + y // 400

    prior = year - 1
    days = 365 * prior + leaps(prior)
    days += _DAYS_BEFORE_MONTH[month - 1]
    if month > 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)):
        days += 1
    days += day - 1
    # 719162 = days from 0001-01-01 to 1970-01-01 under this same accumulation
    return (days - 719162) * 86400.0 + hour * 3600.0 + minute * 60.0 + second + frac


def _read(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


def rederive(day: str = DAY, side: str = "bid") -> Dict[str, Any]:
    depth = _read(REPO / "tape" / "orderbook_depth" / f"dt={day}.jsonl")
    trades = _read(REPO / "tape" / "kalshi_trades" / f"dt={day}.jsonl")

    quotes: Dict[str, List[Tuple[float, Any, Any]]] = {}
    seen: List[str] = []
    for rec in depth:
        tk = rec.get("ticker")
        if not tk:
            continue
        if tk not in quotes:
            quotes[tk] = []
            seen.append(tk)
        quotes[tk].append((epoch_seconds(rec["captured_at"]),
                           rec.get("best_yes_bid"), rec.get("best_yes_ask")))
    for v in quotes.values():
        v.sort(key=lambda x: x[0])

    fills: Dict[str, List[Tuple[float, Any, Any]]] = {}
    for rec in trades:
        tk = rec.get("ticker")
        if not tk:
            continue
        fills.setdefault(tk, []).append((epoch_seconds(rec["created_time"]),
                                         rec.get("taker_book_side"), rec.get("yes_price")))
    for v in fills.values():
        v.sort(key=lambda x: x[0])

    import scripts.q51_maker_fillsim as probe
    probe_universe = {t for t in probe.reconstruct_sample(seen)
                      if probe.is_sports_game_market(t)}
    full_universe = set(seen)

    def grid_cell(universe, require_next: bool, max_age: float) -> Tuple[int, int]:
        agree = total = 0
        for tk, prs in fills.items():
            if tk not in universe:
                continue
            qs = quotes.get(tk) or []
            if not qs:
                continue
            # linear merge walk: advance `k` to the newest quote at or before each print
            k = -1
            n = len(qs)
            for pts, pside, price in prs:
                while k + 1 < n and qs[k + 1][0] <= pts:
                    k += 1
                if k < 0 or pside != side or price is None:
                    continue
                if require_next and k == n - 1:
                    continue
                qts, qbid, qask = qs[k]
                if pts - qts > max_age or not qbid or not qask:
                    continue
                total += 1
                if side == "bid" and price >= qask - 1e-9:
                    agree += 1
                elif side == "ask" and price <= qbid + 1e-9:
                    agree += 1
        return agree, total

    out: Dict[str, Any] = {"day": day, "side": side, "grid": {}}
    for uname, universe in (("probe_sports_sample", probe_universe),
                            ("full_depth_day", full_universe)):
        out["grid"][uname] = {}
        for rname, require_next in (("bracketed", True), ("last_preceding", False)):
            series = []
            for window in (900.0, 3600.0, 1e9):
                agree, total = grid_cell(universe, require_next, window)
                series.append({"window_s": window, "n": total,
                               "rate": (agree / total) if total else None})
            out["grid"][uname][rname] = series
    return out


def population_moves_nothing(result: Dict[str, Any]) -> bool:
    g = result["grid"]
    return all(g["probe_sports_sample"][r] == g["full_depth_day"][r]
               for r in ("bracketed", "last_preceding"))


def join_rule_flips_direction(result: Dict[str, Any]) -> bool:
    def strictly(seq, up: bool) -> bool:
        vals = [c["rate"] for c in seq]
        if any(v is None for v in vals):
            return False
        return all((a < b) if up else (a > b) for a, b in zip(vals[:-1], vals[1:]))
    g = result["grid"]
    return all(strictly(g[p]["bracketed"], up=False) and strictly(g[p]["last_preceding"], up=True)
               for p in ("probe_sports_sample", "full_depth_day"))


def main(argv: Optional[Sequence[str]] = None) -> int:
    res = rederive()
    for pop, by_rule in res["grid"].items():
        for rule, cells in by_rule.items():
            pretty = " ".join(f"{int(c['window_s'])}s={c['rate']:.5f}(n={c['n']})"
                              if c["rate"] is not None else f"{int(c['window_s'])}s=n/a"
                              for c in cells)
            print(f"{pop:20s} {rule:15s} {pretty}")
    print(f"population moves nothing: {population_moves_nothing(res)}")
    print(f"join rule flips direction: {join_rule_flips_direction(res)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

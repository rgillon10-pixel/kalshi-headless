#!/usr/bin/env python3
"""Data-quality deep-dive on `tape/crypto_hourly/` (LOOP-QUEUE.md idle-run policy (c),
2026-08-06). READ-ONLY and FULLY OFFLINE: this module opens committed tape files and
nothing else -- no network, no credentials, no orders, no writes outside `reports/`. It
produces a DATA-QUALITY report, never a P&L, never a CI, never a registry flip (S8/S10/S14
already carry their own real-ask verdicts -- DEAD/DEAD/DEAD -- and nothing here touches
them).

Why this family, why now. `crypto_hourly` is Q2's original collector (2026-07-03) and feeds
three now-DEAD strategies (S8 Q5, S10 Q7, S14's crypto-ladder leg Q13/Q34) plus Q20's
overround anatomy (DONE). No dedicated data-quality audit of the family itself exists --
recent idle-run(c) passes covered `orderbook_depth` (L282), `weather_books`-meta (L281),
`kalshi_trades` (L280), `polymarket_cpi_pairs` (L286) and a repo-wide duplicate census
(L285) that touched `crypto_hourly` only for byte-identical duplicate rows. The family is
still actively collected every hourly pass, so a latent defect in its settlement payload
would silently corrupt any future revival attempt or cross-family join -- worth checking
even with no strategy currently alive on it (CLAUDE.md: "collect data where others aren't").

Three measurements, each falsifiable from committed bytes:

1. `settlement_integrity` -- `previous_settlement.status` distribution (`settled` / `pending`
   / `no_current_group` / `not_found`), and the load-bearing invariant a MECE bracket ladder
   settlement must hold: exactly one member has `result == "yes"`. Checked ONLY on
   `status == "settled"` records -- `pending`/`no_current_group`/`not_found` correctly carry
   no `results` key at all (verified against `collection/crypto_hourly.py::fetch_settlement`
   and the `run()` no-current-group branch), so counting their absence as a violation would
   be the exact false-positive this audit exists to avoid. Per-ticker results are read
   through `core.settlement.filter_binary_results_map` (L52/L155's sanctioned guard) rather
   than a bare `== "yes"` comparison, so a non-binary (`scalar`) result -- not observed on
   this family to date, unlike Q26's sports series -- is dropped and counted, never silently
   read as a loss.
2. `capture_cadence` -- lines/day and passes/day (a pass = one BTC + one ETH line) across
   the family's full history, min/max/most-recent-vs-peak, no root-cause narrative (the
   VPS-death / cloud-slot-attrition mechanism is already diagnosed for other families in
   `findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md` and
   `findings/2026-08-03-vps-collector-true-outage-273h-burst-contamination-blind-spot.md`;
   this module only measures THIS family's own number, never re-derives the cause).
3. `discovery_gap_profile` -- how often `discover_current_hour_group` fails
   (`current.status != "ok"`), split into the genuine "no hourly group exists right now"
   case vs. a transient network/proxy error, per symbol and per day, so a reader can see
   whether the gap is a live risk or a closed historical episode.

Run:
    python3 scripts/crypto_hourly_settlement_audit.py
    python3 scripts/crypto_hourly_settlement_audit.py --tape-dir tape/crypto_hourly --json-out reports/x.json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.settlement import filter_binary_results_map  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
TAPE_DIR = REPO_ROOT / "tape" / "crypto_hourly"
REPORT_PATH = REPO_ROOT / "reports" / "crypto_hourly_settlement_audit.json"
SCHEMA_VERSION = "crypto_hourly_settlement_audit.v1"


def _iter_records(tape_dir: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for fp in sorted(tape_dir.glob("dt=*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                rec["_day"] = fp.stem.split("=", 1)[1] if "=" in fp.stem else fp.stem
                records.append(rec)
    return records


def settlement_integrity(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """`previous_settlement.status` census + the exactly-one-winner check, `settled` only."""
    status_counts: Counter = Counter()
    n_settled = 0
    n_violations = 0
    violation_examples: List[Dict[str, Any]] = []
    n_settled_missing_expiration_value = 0
    for rec in records:
        ps = rec.get("previous_settlement") or {}
        status = ps.get("status", "<no status field>")
        status_counts[status] += 1
        if status != "settled":
            continue
        n_settled += 1
        if not ps.get("expiration_value"):
            n_settled_missing_expiration_value += 1
        raw_results = ps.get("results") or {}
        results, _report = filter_binary_results_map(raw_results)
        n_yes = sum(1 for v in results.values() if v == "yes")
        if n_yes != 1:
            n_violations += 1
            if len(violation_examples) < 5:
                violation_examples.append({
                    "day": rec.get("_day"),
                    "capture_id": rec.get("capture_id"),
                    "symbol": rec.get("symbol"),
                    "event_ticker": ps.get("event_ticker"),
                    "n_yes": n_yes,
                    "n_results": len(results),
                })
    return {
        "status_distribution": dict(status_counts),
        "n_settled": n_settled,
        "n_mece_exactly_one_winner_violations": n_violations,
        "mece_invariant_holds": n_violations == 0,
        "n_settled_missing_expiration_value": n_settled_missing_expiration_value,
        "violation_examples": violation_examples,
    }


def capture_cadence(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Lines/day and passes/day (BTC+ETH paired) across the family's history."""
    lines_by_day: Counter = Counter()
    caps_by_day: Dict[str, set] = {}
    for rec in records:
        day = rec.get("_day")
        lines_by_day[day] += 1
        caps_by_day.setdefault(day, set()).add(rec.get("capture_id"))
    days = sorted(lines_by_day)
    if not days:
        return {"n_days": 0}
    per_day = [
        {"day": d, "n_lines": lines_by_day[d], "n_passes": len(caps_by_day[d])}
        for d in days
    ]
    pass_counts = [len(caps_by_day[d]) for d in days]
    peak_day = days[pass_counts.index(max(pass_counts))]
    # "recent" = the last 7 committed day-files, mirroring the L213/L221-style trailing window.
    recent = per_day[-7:]
    recent_mean_passes = (
        sum(r["n_passes"] for r in recent) / len(recent) if recent else None
    )
    return {
        "n_days": len(days),
        "first_day": days[0],
        "last_day": days[-1],
        "peak_day": peak_day,
        "peak_passes": max(pass_counts),
        "recent_7day_mean_passes": recent_mean_passes,
        "per_day": per_day,
    }


def discovery_gap_profile(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """How often `current` discovery fails, split genuine-gap vs transient error."""
    n_total = len(records)
    n_ok = 0
    reason_counts: Counter = Counter()
    by_symbol: Counter = Counter()
    by_day: Counter = Counter()
    last_gap_day: Optional[str] = None
    for rec in records:
        cur = rec.get("current") or {}
        status = cur.get("status")
        if status == "ok":
            n_ok += 1
            continue
        reason = "no_hourly_group_found" if status == "no_hourly_group_found" else (
            "transient_error" if status and "Max retries exceeded" in str(status) else str(status)
        )
        reason_counts[reason] += 1
        by_symbol[rec.get("symbol")] += 1
        day = rec.get("_day")
        by_day[day] += 1
        if last_gap_day is None or day > last_gap_day:
            last_gap_day = day
    return {
        "n_total": n_total,
        "n_ok": n_ok,
        "n_gap": n_total - n_ok,
        "frac_gap": round((n_total - n_ok) / n_total, 4) if n_total else None,
        "reason_counts": dict(reason_counts),
        "by_symbol": dict(by_symbol),
        "by_day": dict(sorted(by_day.items())),
        "last_gap_day": last_gap_day,
    }


def build_report(tape_dir: Path = TAPE_DIR) -> Dict[str, Any]:
    records = _iter_records(tape_dir)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "offline": True,
        "n_records": len(records),
        "settlement_integrity": settlement_integrity(records),
        "capture_cadence": capture_cadence(records),
        "discovery_gap_profile": discovery_gap_profile(records),
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="crypto_hourly data-quality deep-dive")
    ap.add_argument("--tape-dir", default=str(TAPE_DIR))
    ap.add_argument("--json-out", default=str(REPORT_PATH))
    args = ap.parse_args(argv)

    rep = build_report(Path(args.tape_dir))
    out = Path(args.json_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=1, sort_keys=True)

    si, cc, dg = rep["settlement_integrity"], rep["capture_cadence"], rep["discovery_gap_profile"]
    print(f"[crypto_hourly:quality] n_records={rep['n_records']}")
    print(f"[crypto_hourly:quality] settlement: n_settled={si['n_settled']} "
          f"mece_violations={si['n_mece_exactly_one_winner_violations']} "
          f"(holds={si['mece_invariant_holds']}) status_dist={si['status_distribution']}")
    print(f"[crypto_hourly:quality] cadence: {cc['n_days']} days, peak={cc['peak_passes']} "
          f"passes/day on {cc.get('peak_day')}, recent 7-day mean="
          f"{cc.get('recent_7day_mean_passes')} passes/day")
    print(f"[crypto_hourly:quality] discovery gaps: {dg['n_gap']}/{dg['n_total']} "
          f"({dg['frac_gap']}), last gap day={dg['last_gap_day']}, reasons={dg['reason_counts']}")
    print(f"[crypto_hourly:quality] wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

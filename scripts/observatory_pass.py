#!/usr/bin/env python3
"""observatory_pass.py — one nightly Observatory pass (OBS-1 pilot).

Incremental by design (a cloud run should be minutes, not an hour):
  1. For each pilot family, summarize any committed tape day that has no daily
     aggregate yet under reports/observatory/daily/ (small, committed, reproducible
     from tape by rerunning with --rebuild).
  2. Run the outlier screen over each NEWLY summarized day, oldest first, and
     reconcile each day against the append-only pattern ledger
     (findings/observatory/patterns.jsonl) — so persistence accrues day by day in
     capture order even when a run catches up on several days at once.
  3. Write a run report to reports/observatory/runs/run-<latest_dt>.md: state
     counts, current persistent/candidate patterns, and — for any pattern that
     reached ``candidate`` — a DRAFTED queue-item block. Drafts are text in a
     report; registration in LOOP-QUEUE.md stays with the research loop /
     edge-hunter under the two-agent rule. This script never touches LOOP-QUEUE.md,
     kb/, or the registry.

Usage:
    python scripts/observatory_pass.py               # incremental pass
    python scripts/observatory_pass.py --rebuild     # re-summarize + re-screen all days
    python scripts/observatory_pass.py --status      # replay ledger, print state, no writes

--rebuild recomputes daily aggregates in place but NEVER truncates the ledger —
the ledger is append-only; replaying an already-processed day (hit OR miss) is a
no-op by construction (reconcile skips any dt <= a pattern's last_seen_dt and
re-observations of known ids). Two documented consequences of append-only:
(a) a rebuild after an extractor bugfix corrects the committed daily aggregates
but cannot rewrite ledger history — corrected flags for already-processed days
are dropped, not re-scored; (b) a tape day BACKFILLED behind a pattern's
last_seen_dt (union-merge recoveries do this) records neither hit nor miss for
that pattern. Both are deliberate: ledger truth only ever moves forward.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analysis.observatory import features, ledger, screens  # noqa: E402
from core.io import REPO_ROOT  # noqa: E402

RUNS_DIR = REPO_ROOT / "reports" / "observatory" / "runs"


def draft_queue_item(p: dict) -> str:
    fee = "cleared (margin at latest hit)" if p["latest_fee_floor_cleared"] else "NOT cleared"
    return "\n".join([
        "```",
        "DRAFT queue item (Observatory OBS-1 — needs edge-hunter adversarial review + registration)",
        "- pattern_id: {}".format(p["pattern_id"]),
        "- what: {family}/{series} {metric} is a {direction}-tail cross-sectional outlier".format(**p),
        "  (latest robust_z {}, value {}), persistent on {} distinct days ({} -> {}).".format(
            p["latest_robust_z"], p["latest_value"], len(p["hit_days"]),
            p["first_dt"], p["last_dt"]),
        "- factor family: {} | nearest dead cousin: {}".format(
            p["factor_family"], p["nearest_dead_cousin"] or "none"),
        "- fee floor: {}".format(fee),
        "- required before registration: mechanism hypothesis + kill condition +",
        "  'why it survives its nearest dead cousin' (Q21 rule) + verifier review.",
        "```",
    ])


def run_pass(rebuild: bool = False) -> dict:
    new_days = []  # (dt, family) pairs summarized this pass
    for fam in features.PILOT_FAMILIES:
        for dt in features.tape_days(fam):
            written = features.build_day(fam, dt, force=rebuild)
            if written is not None:
                new_days.append((dt, fam))

    # Screen + reconcile in strict capture order so persistence accrues honestly.
    appended = 0
    screened_days = []
    for dt in sorted({d for d, _ in new_days}):
        day_flags, day_screened = [], set()
        for fam in features.PILOT_FAMILIES:
            if (dt, fam) not in set(new_days):
                continue
            rows = features.load_day(fam, dt)
            out = screens.outlier_screen(fam, dt, rows)
            day_flags.extend(out["flags"])
            day_screened.update(tuple(x) for x in out["screened"])
        res = ledger.reconcile(day_flags, dt, day_screened)
        appended += res["appended"]
        screened_days.append(dt)

    state = ledger.replay(ledger.read_events())
    return {"new_days": sorted(set(d for d, _ in new_days)), "appended": appended,
            "screened_days": screened_days, "state": state}


def write_report(result: dict) -> Path:
    state = result["state"]
    counts = Counter(p["status"] for p in state.values())
    latest = max(result["screened_days"]) if result["screened_days"] else "none"
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    out = RUNS_DIR / "run-{}.md".format(latest if latest != "none" else "noop")

    lines = [
        "# Observatory pass — through dt={}".format(latest),
        "",
        "Days screened this pass: {} | ledger events appended: {}".format(
            ", ".join(result["screened_days"]) or "none", result["appended"]),
        "State: {}".format(dict(sorted(counts.items())) or "{}"),
        "",
    ]
    interesting = sorted(
        (p for p in state.values() if p["status"] in ("persistent", "candidate")),
        key=lambda p: (p["status"] != "candidate", -len(p["hit_days"])))
    if interesting:
        lines.append("## Open patterns (persistent / candidate)")
        lines.append("")
        lines.append("| id | status | family/series | metric (dir) | hit days | z | fee | factor family |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for p in interesting:
            lines.append("| {} | {} | {}/{} | {} ({}) | {} | {} | {} | {}{} |".format(
                p["pattern_id"], p["status"], p["family"], p["series"], p["metric"],
                p["direction"], len(p["hit_days"]), p["latest_robust_z"],
                p["latest_fee_floor_cleared"], p["factor_family"],
                " [GRAVEYARD-BLOCKED]" if p["graveyard_blocked"] and not p["survival_rationale"] else ""))
        lines.append("")
    cands = [p for p in interesting if p["status"] == "candidate"]
    if cands:
        lines.append("## Drafted queue items (NOT registered — edge-hunter review required)")
        lines.append("")
        for p in cands:
            lines.append(draft_queue_item(p))
            lines.append("")
    else:
        lines.append("No candidates this pass (pre-registered kill: 14 runs, 0 "
                     "verifier-surviving promotions -> decommission).")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        state = ledger.replay(ledger.read_events())
        counts = Counter(p["status"] for p in state.values())
        print(json.dumps({"patterns": len(state), "by_status": dict(sorted(counts.items()))},
                         indent=2))
        return 0

    result = run_pass(rebuild=args.rebuild)
    report = write_report(result)
    counts = Counter(p["status"] for p in result["state"].values())
    print(json.dumps({
        "new_days": result["new_days"],
        "ledger_events_appended": result["appended"],
        "patterns_by_status": dict(sorted(counts.items())),
        "report": str(report.relative_to(REPO_ROOT)),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

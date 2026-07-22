"""Append-only pattern ledger + persistence screen (the out-of-sample half).

``findings/observatory/patterns.jsonl`` is an EVENT LOG, same discipline as tape/
and paper/: lines are appended, never rewritten; current pattern state is derived
by replay. Events:

  observed      first flagging of a pattern key (family, series, metric, direction)
  recheck_hit   a later run's screen flagged the same key again (held-out day)
  recheck_miss  a later run screened the key's metric and did NOT flag it

Pre-registered state machine (OBS-1, 2026-07-21):

  observed    ->  persistent   total distinct hit-days >= PERSIST_DAYS (3), where
                               hit-days AFTER the first observation are out-of-sample
                               by construction (the screen never saw them when the
                               pattern was first emitted)
  persistent  ->  candidate    fee_floor_cleared is True on the latest hit AND the
                               factor family is not graveyard-blocked (or a human/
                               edge-hunter authored survival_rationale exists in a
                               later ``annotate`` event)
  any         ->  expired      EXPIRE_MISSES (5) consecutive recheck misses

"candidate" here means: the run report drafts a queue item for LOOP-QUEUE.md. The
Observatory itself NEVER registers queue items, flips the registry, or writes to
kb/ — registration stays with the research loop / edge-hunter under the two-agent
verdict rule.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.io import REPO_ROOT

LEDGER_PATH = REPO_ROOT / "findings" / "observatory" / "patterns.jsonl"

PERSIST_DAYS = 3
EXPIRE_MISSES = 5


def pattern_id(family: str, series: str, metric: str, direction: str) -> str:
    key = "|".join((family, series, metric, direction))
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def append_events(events: List[Dict[str, Any]], ledger_path: Path = LEDGER_PATH) -> int:
    if not events:
        return 0
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, sort_keys=True, separators=(",", ":")) + "\n")
    return len(events)


def read_events(ledger_path: Path = LEDGER_PATH) -> List[Dict[str, Any]]:
    if not ledger_path.exists():
        return []
    out = []
    with ledger_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def replay(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Event log -> {pattern_id: state}. Pure, deterministic."""
    state: Dict[str, Dict[str, Any]] = {}
    for ev in events:
        pid = ev["pattern_id"]
        kind = ev["event"]
        if kind == "observed":
            state[pid] = {
                "pattern_id": pid,
                "family": ev["family"], "series": ev["series"],
                "metric": ev["metric"], "direction": ev["direction"],
                "factor_family": ev.get("factor_family"),
                "nearest_dead_cousin": ev.get("nearest_dead_cousin"),
                "graveyard_blocked": bool(ev.get("graveyard_blocked")),
                "first_dt": ev["dt"], "last_dt": ev["dt"],
                "last_seen_dt": ev["dt"],
                "hit_days": [ev["dt"]],
                "consecutive_misses": 0,
                "latest_fee_floor_cleared": ev.get("fee_floor_cleared"),
                "latest_robust_z": ev.get("robust_z"),
                "latest_value": ev.get("value"),
                "survival_rationale": None,
            }
        elif kind == "recheck_hit" and pid in state:
            s = state[pid]
            if ev["dt"] not in s["hit_days"]:
                s["hit_days"].append(ev["dt"])
            s["last_dt"] = ev["dt"]
            s["last_seen_dt"] = max(s["last_seen_dt"], ev["dt"])
            s["consecutive_misses"] = 0
            s["latest_fee_floor_cleared"] = ev.get("fee_floor_cleared")
            s["latest_robust_z"] = ev.get("robust_z")
            s["latest_value"] = ev.get("value")
        elif kind == "recheck_miss" and pid in state:
            state[pid]["consecutive_misses"] += 1
            # Misses advance last_seen_dt too — idempotency keys off the last day
            # PROCESSED (hit or miss), not the last hit, or a --rebuild would
            # re-append every historical miss and could spuriously (and, in an
            # append-only ledger, irreversibly) expire a live pattern.
            if ev.get("dt"):
                state[pid]["last_seen_dt"] = max(state[pid]["last_seen_dt"], ev["dt"])
        elif kind == "annotate" and pid in state:
            if ev.get("survival_rationale"):
                state[pid]["survival_rationale"] = ev["survival_rationale"]
    for s in state.values():
        s["status"] = _status(s)
    return state


def _status(s: Dict[str, Any]) -> str:
    if s["consecutive_misses"] >= EXPIRE_MISSES:
        return "expired"
    if len(s["hit_days"]) >= PERSIST_DAYS:
        if s["latest_fee_floor_cleared"] is True and (
            not s["graveyard_blocked"] or s["survival_rationale"]
        ):
            return "candidate"
        return "persistent"
    return "observed"


def reconcile(flags: List[Dict[str, Any]], dt: str,
              screened: "set",
              ledger_path: Path = LEDGER_PATH) -> Dict[str, Any]:
    """One run's screen output vs the ledger -> new events, appended.

    ``screened`` is the set of (family, metric) pairs the screen ACTUALLY evaluated
    this run (cleared MIN_CROSS_SECTION etc.) — passed explicitly by the runner,
    never inferred from the flags: a metric that emitted zero flags this run must
    still record misses for its open patterns, or nothing would ever expire.
    Absence of tape, by contrast, is not evidence of absence of pattern — unscreened
    metrics record nothing.
    """
    prior = replay(read_events(ledger_path))
    flagged_ids = set()
    events: List[Dict[str, Any]] = []
    screened_metrics = set(screened)

    for f in flags:
        pid = pattern_id(f["family"], f["series"], f["metric"], f["direction"])
        flagged_ids.add(pid)
        base = dict(f)
        base["pattern_id"] = pid
        if pid not in prior:
            base["event"] = "observed"
        else:
            if dt <= prior[pid]["last_seen_dt"]:
                continue  # replayed/duplicate day (hit OR miss) — append nothing
            base["event"] = "recheck_hit"
        events.append(base)

    for pid, s in sorted(prior.items()):
        if pid in flagged_ids or s["status"] == "expired":
            continue
        if (s["family"], s["metric"]) not in screened_metrics:
            continue
        if dt <= s["last_seen_dt"]:
            continue
        events.append({"event": "recheck_miss", "pattern_id": pid, "dt": dt})

    append_events(events, ledger_path)
    return {"appended": len(events), "state": replay(read_events(ledger_path))}

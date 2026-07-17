#!/usr/bin/env python3
"""Collector gap-detector + missing-day monitor (LOOP-QUEUE Q44 / GOAL.md M1a).

Read-only reliability monitor. It answers one question per tape family: *is the
collector pipe still delivering, and if not, is the silence a real failure or a
benign market-universe exhaustion?* It makes **no strategy claim, no P&L number,
no registry change** — it only reports pipe health.

What it reads
-------------
Committed tape only: ``tape/<family>/dt=YYYY-MM-DD.jsonl`` append-only lines.
It never makes a live network call for the health computation, and it never
reads any other process's in-memory return value. The one and only outbound
call is an optional ntfy POST when a family alerts (see below). "Reads only the
hourly-pass summary shape" (Q44 wording) means its *own* output mirrors this
repo's ``completeness_ok`` summary convention (see ``collection/hourly_pass.py``,
``collection/polymarket_pairs.py::run``) — it does NOT mean it has access to a
running pass's summary.

Directories named ``dt=YYYY-MM-DD`` (no ``.jsonl``) are the 2026-07-08 tape-format
regression artifacts (lessons L25/L29 — raw per-market API blobs, not canonical
lines) and are correctly ignored by the ``dt=*.jsonl`` glob: they carry no
canonical capture line, so a day that exists only as a directory reads as a
genuine gap, which is the honest result.

Two detectors, per family, over a lookback window ending at an injectable ``now``
-------------------------------------------------------------------------------
1. **STALE (contiguous silence).** ``age_hours = now - newest captured_at`` across
   ALL of the family's tape (not just today's file — a leg stuck since yesterday
   shows a >24h age even with no ``dt=today.jsonl`` at all). Alerts when the
   silence exceeds ``2 x expected_interval_h``. This catches a fully-dead leg.
2. **UNDER-CAPTURE (distributed drops).** Over the last ``window_hours``, the count
   of distinct capture passes vs. the family's expected count. Alerts when the
   capture ratio drops below ``UNDER_CAPTURE_FLOOR``. This catches the case where
   the day still has a full span (one collector alive) but roughly half the passes
   silently dropped (one of two staggered collectors died).

Why two collectors matter for the config. The live pipe runs TWO staggered
collectors (VPS cron at :23 UTC, cloud trigger at :53 UTC), so a healthy hourly
family lands ~46-48 passes/day, not ~24. The config therefore carries BOTH the
"roughly hourly" stall cadence (``interval_h``, used by the STALE detector so a
single missed collector-pass never pages) AND the realized ``passes_per_day``
(used by the UNDER-CAPTURE detector so losing one of the two collectors DOES
page). Empirically calibrated against committed tape: healthy days 45-53 passes
(ratio 0.94-1.10), the 2026-07-15 under-capture 32 passes (ratio 0.67) — the 0.8
floor sits with comfortable margin between them.

Honest completeness
-------------------
Each line's completeness signal is extracted by looking for a boolean
``completeness_ok`` (top-level, e.g. ``sports_pairs``), ``pass_complete``
(``crypto_hourly``/``econ_prints``), or a nested ``*.completeness_ok``
(``crypto_hourly``'s ``current``). A line with none of these yields **no signal**
(reported as ``null`` / "no_signal") — NEVER a fabricated ``True``. As of this
build, most families (orderbook_depth, weather_books, the polymarket_* pairs,
weather_actuals, perp_tape, hyperliquid_funding) carry no per-line completeness
field in committed tape at all, so they honestly read "no_signal"; only
``sports_pairs``/``crypto_hourly``/``econ_prints`` carry a signal today. If any
line in the window is incomplete, the family summary is ``False`` (a partial
failure is never AND/OR'd away).

The false-positive discriminator
--------------------------------
``KNOWN_BENIGN_SILENCES`` is a small, human-editable allowlist of documented
legitimate silences. A family in it is ALWAYS shown in the health table (never
hidden) but its silence is downgraded from a ``Priority: high`` alert to
``alert_reason = "known_benign_silence"``. Seeded with exactly one entry:
``polymarket_pairs`` since 2026-07-15 — the World Cup champion market resolved
that day (tape shows ``yes_ask=1.0``), so the collector's ``status=open``
discovery correctly returns 0 matches and its ``if lines:`` guard
(``collection/polymarket_pairs.py:342``) writes no file — a legitimate zero-match,
not a crashed collector. The suppression is tied to the specific onset day
(matches only when the family's newest capture falls on ``silent_since``), so it
does NOT mask the unrelated 2026-07-09 systemic outage (where polymarket_pairs's
last capture was 07-08) and would NOT mask a *new* silence if the family resumes
and later dies again for a different reason.

NOT done here (future work, deliberately out of scope for one deliverable):
the real long-term fix is a **zero-match heartbeat** — having each collector's
empty-match code path still emit a status/summary line ("ran, matched 0,
universe empty") so "ran but found nothing" stays distinguishable in-tape from
"did not run", without a hand-maintained allowlist. Retrofitting every
collector's zero-match path is out of scope for this milestone; this monitor uses
the allowlist as the interim bridge and names the heartbeat as the durable fix.

Alerting
--------
When any family hard-alerts, one ``Priority: high`` ntfy note is POSTed. The URL
comes from ``--ntfy-url`` or the ``NTFY_TOPIC_URL`` environment variable and is
NEVER hardcoded and NEVER read from ``config/notify.topic`` (retired — this repo
is public and topic names must never be committed). If no URL is supplied the
POST is a no-op (prints a note, never crashes), mirroring the ``ODDS_API_KEY``-
absent pattern in ``collection/odds_api.py``. The POST function is injectable so
tests never touch the network.

Scheduling is a **Ryan pause point** (Q44 wording): wiring this into a cron /
GitHub Action / cloud trigger is a manual checklist item, intentionally NOT done
by the autonomous build.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Config — deliberately explicit, human-editable, NOT inferred from the data
# (inferring cadence from noisy historical gaps would be circular with the very
#  thing this monitor exists to detect).
# --------------------------------------------------------------------------- #
# interval_h    : the "roughly hourly / daily" stall cadence for the STALE
#                 detector (a single missed collector-pass must NOT page).
# passes_per_day: realized healthy pass count for the UNDER-CAPTURE detector
#                 (hourly families run 2 staggered collectors => ~48/day).
# kind          : documentation label only.
FAMILY_CONFIG: Dict[str, Dict[str, Any]] = {
    # Hourly, dual-collector (VPS :23 + cloud :53 ~= 2 passes/hour).
    "sports_pairs":            {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    "crypto_hourly":           {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    "orderbook_depth":         {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    "weather_books":           {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    "polymarket_pairs":        {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    "polymarket_macro_pairs":  {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    # Daily / 09-UTC econ slot (1-2 passes/day). passes_per_day too small for a
    # ratio detector, so these are STALE-only (age > 2 days pages).
    "polymarket_cpi_pairs":    {"interval_h": 24.0, "passes_per_day": 1,    "kind": "daily-econ-slot"},
    "econ_prints":             {"interval_h": 24.0, "passes_per_day": 1,    "kind": "daily-econ-slot"},
    "weather_actuals":         {"interval_h": 24.0, "passes_per_day": 1,    "kind": "daily"},
    # One-shot / backfill families: no cadence expectation. Tracked for age only;
    # never alerted on cadence (Q44: "treat as always-complete captures, just
    # track their captured_at cadence").
    "perp_tape":               {"interval_h": None, "passes_per_day": None, "kind": "one-shot-backfill"},
    "hyperliquid_funding":     {"interval_h": None, "passes_per_day": None, "kind": "one-shot-backfill"},
}

# Detector thresholds (documented; edit here, not in the logic).
DEFAULT_WINDOW_HOURS = 24.0
STALE_INTERVAL_MULTIPLE = 2.0   # STALE alert when age_hours > this * interval_h
UNDER_CAPTURE_FLOOR = 0.8       # UNDER-CAPTURE alert when captured/expected < this
UNDER_CAPTURE_MIN_PPD = 6       # ratio detector only runs for families this dense

# The one benign-silence allowlist entry (see module docstring for full rationale).
KNOWN_BENIGN_SILENCES: List[Dict[str, str]] = [
    {
        "family": "polymarket_pairs",
        "silent_since": "2026-07-15",
        "reason": ("World Cup champion market resolved 2026-07-15 (tape shows yes_ask=1.0); "
                   "status=open discovery legitimately returns 0 matches and the collector's "
                   "`if lines:` guard writes no file — a legitimate zero-match, not a crash."),
        "citation": ("LOOP-QUEUE.md Q44 item (2026-07-16 HIGH-confidence triage); "
                     "collection/polymarket_pairs.py:342 `if lines:` guard"),
    },
]


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO8601-with-tz timestamp; return None on anything unparseable.
    Naive timestamps are assumed UTC (defensive — committed tape always carries tz)."""
    if not isinstance(ts, str):
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_day_from_filename(path: Path) -> Optional[date]:
    """`dt=2026-07-15.jsonl` -> date(2026,7,15); None if it doesn't match."""
    name = path.name
    if not (name.startswith("dt=") and name.endswith(".jsonl")):
        return None
    try:
        return datetime.strptime(name[3:-6], "%Y-%m-%d").date()
    except ValueError:
        return None


def extract_completeness(rec: Dict[str, Any]) -> Optional[bool]:
    """Honest per-line completeness signal.

    Looks for a boolean ``completeness_ok`` (top-level), ``pass_complete``, or any
    nested ``*.completeness_ok`` (e.g. crypto_hourly's ``current``). ANDs every
    boolean signal found. Returns ``None`` (no signal) when the line carries none
    — never a fabricated ``True``.
    """
    signals: List[bool] = []
    v = rec.get("completeness_ok")
    if isinstance(v, bool):
        signals.append(v)
    v = rec.get("pass_complete")
    if isinstance(v, bool):
        signals.append(v)
    for val in rec.values():
        if isinstance(val, dict):
            iv = val.get("completeness_ok")
            if isinstance(iv, bool):
                signals.append(iv)
    if not signals:
        return None
    return all(signals)


# --------------------------------------------------------------------------- #
# Aggregation (streaming, memory-bounded per L10)
# --------------------------------------------------------------------------- #
def _family_files(tape_root: Path, family: str) -> List[Tuple[date, Path]]:
    """Sorted (ascending by day) list of the family's canonical dt=*.jsonl REGULAR
    files. Directories (the L25/L29 regression artifacts) are excluded."""
    fam_dir = tape_root / family
    out: List[Tuple[date, Path]] = []
    if not fam_dir.is_dir():
        return out
    for p in fam_dir.iterdir():
        if not p.is_file():
            continue
        d = _parse_day_from_filename(p)
        if d is not None:
            out.append((d, p))
    out.sort(key=lambda t: t[0])
    return out


def _scan_file_max_captured_at(path: Path, now: datetime) -> Optional[datetime]:
    """Newest captured_at <= now in one file (streaming, O(1) extra memory)."""
    newest: Optional[datetime] = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    continue
                ca = _parse_iso(rec.get("captured_at"))
                if ca is None or ca > now:
                    continue
                if newest is None or ca > newest:
                    newest = ca
    except OSError:
        return None
    return newest


class FamilyAggregate:
    """Streaming aggregate over a family's committed tape, relative to ``now``."""

    def __init__(self, family: str) -> None:
        self.family = family
        self.newest_captured_at: Optional[datetime] = None
        # Distinct passes within the lookback window: capture_id -> earliest ts.
        self._window_passes: Dict[str, datetime] = {}
        self.n_complete = 0
        self.n_incomplete = 0
        self.n_no_signal = 0
        self.total_files = 0

    @property
    def window_pass_count(self) -> int:
        return len(self._window_passes)

    def _consume_window_line(self, rec: Dict[str, Any], ca: datetime) -> None:
        key = rec.get("capture_id") or ca.isoformat()
        prev = self._window_passes.get(key)
        if prev is None or ca < prev:
            self._window_passes[key] = ca
        comp = extract_completeness(rec)
        if comp is True:
            self.n_complete += 1
        elif comp is False:
            self.n_incomplete += 1
        else:
            self.n_no_signal += 1


def aggregate_family(tape_root: Path, family: str, now: datetime,
                     window_hours: float = DEFAULT_WINDOW_HOURS) -> FamilyAggregate:
    """Build a memory-bounded aggregate for one family.

    Recent files (>= window start day) are fully scanned for the window pass-set,
    completeness counts, and the newest-capture candidate. Older files are only
    touched (newest-first) if the family has stalled beyond the window and no
    newest capture was found in recent files — so normal-case work is bounded to
    the window's files even when a family has months of tape.
    """
    agg = FamilyAggregate(family)
    files = _family_files(tape_root, family)
    agg.total_files = len(files)
    if not files:
        return agg

    window_start = now - timedelta(hours=window_hours)
    window_start_day = window_start.date()

    recent = [(d, p) for (d, p) in files if d >= window_start_day]
    older = [(d, p) for (d, p) in files if d < window_start_day]

    for _d, path in recent:
        try:
            fh = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    continue
                ca = _parse_iso(rec.get("captured_at"))
                if ca is None or ca > now:
                    continue
                if agg.newest_captured_at is None or ca > agg.newest_captured_at:
                    agg.newest_captured_at = ca
                if ca > window_start:
                    agg._consume_window_line(rec, ca)

    # Only reach into older files if the family appears stalled beyond the window.
    if agg.newest_captured_at is None:
        for _d, path in reversed(older):
            newest = _scan_file_max_captured_at(path, now)
            if newest is not None:
                agg.newest_captured_at = newest
                break

    return agg


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _benign_match(family: str, newest: Optional[datetime]) -> Optional[Dict[str, str]]:
    """Return the benign-silence entry that applies, or None. Matches only when the
    family's newest capture falls exactly on the documented ``silent_since`` day —
    so it suppresses the specific documented silence and nothing else."""
    if newest is None:
        return None
    for entry in KNOWN_BENIGN_SILENCES:
        if entry["family"] != family:
            continue
        try:
            since = datetime.strptime(entry["silent_since"], "%Y-%m-%d").date()
        except ValueError:
            continue
        if newest.date() == since:
            return entry
    return None


def evaluate_family(agg: FamilyAggregate, now: datetime,
                    window_hours: float = DEFAULT_WINDOW_HOURS) -> Dict[str, Any]:
    """Turn an aggregate into the machine-readable per-family health record."""
    cfg = FAMILY_CONFIG.get(agg.family, {"interval_h": None, "passes_per_day": None, "kind": "unconfigured"})
    interval_h = cfg["interval_h"]
    ppd = cfg["passes_per_day"]

    newest = agg.newest_captured_at
    age_hours: Optional[float] = None
    if newest is not None:
        age_hours = (now - newest).total_seconds() / 3600.0

    # Completeness summary (partial failure never AND/OR'd away).
    if agg.n_incomplete > 0:
        completeness_ok: Optional[bool] = False
    elif agg.n_complete > 0:
        completeness_ok = True
    else:
        completeness_ok = None

    reasons: List[str] = []

    # STALE detector.
    stale_missed = 0.0
    if interval_h is not None and age_hours is not None:
        stale_missed = max(0.0, age_hours / interval_h - 1.0)
        if age_hours > STALE_INTERVAL_MULTIPLE * interval_h:
            reasons.append(
                f"stale: {age_hours:.1f}h since last pass "
                f"(> {STALE_INTERVAL_MULTIPLE * interval_h:.0f}h threshold)"
            )

    # A family with NO capture at or before `now` is "dark": either not yet
    # launched at this reference time, config added ahead of deploy, or genuinely
    # never ran. Tape alone can't tell these apart, so we SHOW it (never hide) but
    # do NOT page — paging on that ambiguity is exactly the alert-fatigue Q44
    # warns against. A leg that ran and then died still has a (stale) newest and
    # is paged by the STALE detector above; only never-produced-anything is
    # downgraded here.
    dark = interval_h is not None and newest is None

    # UNDER-CAPTURE detector (dense families only).
    shortfall = 0.0
    expected_window = None
    ratio = None
    if ppd is not None and ppd >= UNDER_CAPTURE_MIN_PPD and not dark:
        expected_window = ppd * (window_hours / 24.0)
        actual = agg.window_pass_count
        if expected_window > 0:
            ratio = actual / expected_window
            shortfall = max(0.0, expected_window - actual)
            if ratio < UNDER_CAPTURE_FLOOR:
                reasons.append(
                    f"under_capture: {actual}/{expected_window:.0f} passes in "
                    f"{window_hours:.0f}h (ratio {ratio:.2f} < {UNDER_CAPTURE_FLOOR})"
                )

    missed_passes_estimate = round(max(stale_missed, shortfall), 1)
    would_alert = bool(reasons)

    benign = _benign_match(agg.family, newest) if would_alert else None
    if would_alert and benign is not None:
        alert = False
        alert_reason = f"known_benign_silence: {benign['reason']}"
    elif would_alert:
        alert = True
        alert_reason = "; ".join(reasons)
    elif dark:
        alert = False
        alert_reason = "dark: no capture at or before now (not-yet-active / never ran — shown, not paged)"
    else:
        alert = False
        alert_reason = "ok" if newest is not None else "no tape (uncadenced family)"

    return {
        "family": agg.family,
        "kind": cfg["kind"],
        "last_captured_at": newest.isoformat() if newest is not None else None,
        "age_hours": round(age_hours, 2) if age_hours is not None else None,
        "completeness_ok": completeness_ok,
        "completeness_detail": {
            "complete_lines": agg.n_complete,
            "incomplete_lines": agg.n_incomplete,
            "no_signal_lines": agg.n_no_signal,
        },
        "passes_in_window": agg.window_pass_count,
        "expected_in_window": round(expected_window, 1) if expected_window is not None else None,
        "capture_ratio": round(ratio, 3) if ratio is not None else None,
        "missed_passes_estimate": missed_passes_estimate,
        "alert": alert,
        "alert_reason": alert_reason,
    }


def build_report(tape_root: Path, now: datetime,
                 window_hours: float = DEFAULT_WINDOW_HOURS,
                 families: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """The machine-readable blob: family -> health record."""
    fam_list = families if families is not None else list(FAMILY_CONFIG.keys())
    report: Dict[str, Dict[str, Any]] = {}
    for fam in fam_list:
        agg = aggregate_family(tape_root, fam, now, window_hours)
        report[fam] = evaluate_family(agg, now, window_hours)
    return report


# --------------------------------------------------------------------------- #
# Presentation
# --------------------------------------------------------------------------- #
def _fmt_completeness(rec: Dict[str, Any]) -> str:
    c = rec["completeness_ok"]
    det = rec["completeness_detail"]
    if c is None:
        return "no_signal"
    if c is True:
        return "ok"
    return f"PARTIAL ({det['incomplete_lines']} incomplete)"


def format_table(report: Dict[str, Dict[str, Any]], now: datetime) -> str:
    """Human-readable per-family health table."""
    lines: List[str] = []
    lines.append(f"tape gap monitor — now={now.isoformat()}")
    lines.append("")
    header = f"{'family':24} {'age':>10} {'completeness':16} {'passes(win)':>12} {'missed':>7}  alert"
    lines.append(header)
    lines.append("-" * len(header))
    for fam, rec in report.items():
        age = rec["age_hours"]
        age_s = f"{age:.1f}h" if age is not None else "never"
        pw = rec["passes_in_window"]
        exp = rec["expected_in_window"]
        pw_s = f"{pw}/{exp:.0f}" if exp is not None else str(pw)
        missed = rec["missed_passes_estimate"]
        if rec["alert"]:
            flag = "ALERT"
        elif rec["alert_reason"].startswith("known_benign_silence"):
            flag = "benign"
        elif rec["alert_reason"].startswith("dark"):
            flag = "dark"
        else:
            flag = "-"
        lines.append(
            f"{fam:24} {age_s:>10} {_fmt_completeness(rec):16} {pw_s:>12} {missed:>7}  {flag}"
        )
    n_alert = sum(1 for r in report.values() if r["alert"])
    n_benign = sum(1 for r in report.values() if not r["alert"]
                   and r["alert_reason"].startswith("known_benign_silence"))
    lines.append("")
    lines.append(f"{n_alert} alerting, {n_benign} benign-silence (suppressed).")
    for fam, rec in report.items():
        if rec["alert"]:
            lines.append(f"  ALERT  {fam}: {rec['alert_reason']}")
        elif rec["alert_reason"].startswith("known_benign_silence"):
            lines.append(f"  benign {fam}: {rec['alert_reason']}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# ntfy (optional, no-op when no URL; POST fn injectable => no network in tests)
# --------------------------------------------------------------------------- #
def _default_post(url: str, data: bytes, headers: Dict[str, str]) -> None:
    import requests  # local import: monitor core stays import-light and offline
    requests.post(url, data=data, headers=headers, timeout=15)


def maybe_notify(report: Dict[str, Dict[str, Any]],
                 url: Optional[str],
                 post_fn: Optional[Callable[[str, bytes, Dict[str, str]], None]] = None,
                 env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """POST one Priority:high ntfy note iff any family hard-alerts.

    URL precedence: explicit ``url`` arg > ``NTFY_TOPIC_URL`` env var. Absent =>
    no-op (prints a note, never raises). Never reads config/notify.topic.
    """
    if env is None:
        env = dict(os.environ)
    resolved = url or env.get("NTFY_TOPIC_URL")
    alerts = [f for f, r in report.items() if r["alert"]]
    if not alerts:
        return {"sent": False, "reason": "no_alerts", "alerts": []}
    if not resolved:
        print("[tape_gap_monitor] alerts present but no NTFY_TOPIC_URL / --ntfy-url "
              "supplied — ntfy POST skipped (no-op).", file=sys.stderr)
        return {"sent": False, "reason": "no_url", "alerts": alerts}
    body_lines = ["Tape gap monitor: collector families alerting:"]
    for f in alerts:
        body_lines.append(f"- {f}: {report[f]['alert_reason']}")
    body = "\n".join(body_lines).encode("utf-8")
    headers = {"Priority": "high", "Title": "kalshi.headless tape gap alert"}
    post_fn = post_fn or _default_post
    try:
        post_fn(resolved, body, headers)
    except Exception as exc:  # noqa: BLE001 — a monitor must never die on its own alert
        print(f"[tape_gap_monitor] ntfy POST failed: {exc}", file=sys.stderr)
        return {"sent": False, "reason": f"post_error:{exc}", "alerts": alerts}
    return {"sent": True, "reason": "posted", "alerts": alerts}


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _default_tape_root() -> Path:
    return Path(__file__).resolve().parent.parent / "tape"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Collector tape gap-detector / missing-day monitor (read-only).")
    ap.add_argument("--tape-root", default=str(_default_tape_root()),
                    help="root tape/ directory (default: repo tape/).")
    ap.add_argument("--now", default=None,
                    help="ISO8601 reference time (default: current UTC). Injectable for testing.")
    ap.add_argument("--window-hours", type=float, default=DEFAULT_WINDOW_HOURS,
                    help=f"lookback window for the under-capture detector (default {DEFAULT_WINDOW_HOURS}).")
    ap.add_argument("--ntfy-url", default=None,
                    help="ntfy topic URL for Priority:high alerts (else NTFY_TOPIC_URL env; else no-op).")
    ap.add_argument("--json", action="store_true", help="print ONLY the machine-readable JSON blob.")
    ap.add_argument("--no-notify", action="store_true", help="never POST (print table/JSON only).")
    args = ap.parse_args(argv)

    if args.now:
        now = _parse_iso(args.now)
        if now is None:
            print(f"[tape_gap_monitor] could not parse --now={args.now!r}", file=sys.stderr)
            return 2
    else:
        now = datetime.now(timezone.utc)

    tape_root = Path(args.tape_root)
    report = build_report(tape_root, now, window_hours=args.window_hours)

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(format_table(report, now))
        print("")
        print("=== machine-readable JSON ===")
        print(json.dumps(report, indent=2, sort_keys=True))

    if not args.no_notify:
        maybe_notify(report, args.ntfy_url)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

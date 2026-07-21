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

Collector attribution (L117, 2026-07-20)
-----------------------------------------
The aggregate UNDER-CAPTURE ratio above answers "did passes drop?" but not
"which of the two staggered collectors died?" — the 2026-07-19/20 VPS-cron
outage (``findings/2026-07-20-tape-cadence-decline-vps-collector-down.md``)
was diagnosed by hand, bucketing each line's ``captured_at`` minute into the
VPS cron's signature (``:23``, i.e. minute-of-hour 20-29, ``ops/ROUTINES.md``)
vs the cloud routine's (``:53``, minute-of-hour 50-59). For ``hourly-dual``
kind families only (the two families' cadence assumption this split relies
on), each health record now also carries a ``collectors`` breakdown:
``vps``/``cloud``/``other`` pass counts and newest ``captured_at`` in the
window. ``other`` is not fabricated into either bucket — ad-hoc live-pass
smoke tests and one-off runs land there honestly, same discipline as
``no_signal`` for completeness. When a family alerts (STALE or UNDER-CAPTURE)
and exactly one of vps/cloud has zero passes in the window while the other is
non-zero, the alert reason is extended with which collector looks dead
(``collector_diagnosis``) — a genuine attribution, never a guess when both
sides are non-zero or both are zero (ambiguous cases stay unattributed).

Per-family expected-bucket map (L120, 2026-07-21)
-------------------------------------------------
L118's attribution above only ever names ``vps_dead``/``cloud_dead`` and reads
``vps=0 & cloud=0`` as ambiguous. That permanently blinds it to a family whose
SECOND collector lands in neither named window: ``weather_books``' cloud leg
fires at minutes ~00-03 (``other``, not ``:5x``), so once its VPS(:2x) leg died
on 2026-07-19 the monitor saw ``vps=0 & cloud=0`` and gave up — even though the
tape proves the vps primary is the dead leg and ``other`` is the survivor.
``EXPECTED_COLLECTOR_BUCKETS`` fixes this: a per-family ``{primary, secondary}``
bucket map, calibrated against the REAL committed-tape minute histograms (see
the constant's own comment for the 07-18..20 numbers). For a MAPPED family,
``diagnose_collector`` names the dead expected leg when the other still produces;
an UNMAPPED family keeps L118's exact vps/cloud logic (no regression). Both
expected buckets zero, or both non-zero, still stay unattributed — L118's
"no false attribution" discipline is preserved.
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
    # L123: settlement_ledger fires on its own single exact UTC hour
    # (SETTLEMENT_LEDGER_UTC_HOUR=10 in collection/hourly_pass.py), which the live
    # every-3h `kalshi-collector` cron (`53 */3 * * *` -> hours {0,3,6,9,12,15,18,21})
    # NEVER lands on -> the leg has been silently frozen at its 2026-07-17 build day
    # ever since, invisibly, because this family was never registered here (an
    # unconfigured family's STALE detector is a no-op — `interval_h=None` skips the
    # check entirely and `evaluate_family` reports a bare "ok"). Registering it closes
    # that exact gap: the STALE detector (2x24h=48h threshold) now catches the freeze.
    "settlement_ledger":       {"interval_h": 24.0, "passes_per_day": 1,    "kind": "daily"},
    # L127: perp_tape was misfiled here as "one-shot-backfill" since its 2026-07-16
    # build, but `collection/hourly_pass.py` (lines ~56-61, 383-385) runs one
    # `collection.perp_tape` pass EVERY hourly_pass invocation, unconditionally, same
    # as the hourly-dual block above — it is a genuine ~48/day family, not a backfill.
    # Being misclassified made its real degradation (VPS-death fallout, same L117
    # cause as every other hourly-dual family) structurally invisible: an
    # `interval_h=None` family never runs the UNDER-CAPTURE ratio check at all. Its
    # captures land at minute-of-hour ~00-04 (verified against committed tape), which
    # is neither the vps (:20-29) nor cloud (:50-59) bucket — same "other" signature
    # as `weather_books`' L120 secondary leg, hence the same EXPECTED_COLLECTOR_BUCKETS
    # mapping below rather than leaving it unmapped/ambiguous.
    "perp_tape":               {"interval_h": 1.0,  "passes_per_day": 48,   "kind": "hourly-dual"},
    # One-shot / backfill families: no cadence expectation. Tracked for age only;
    # never alerted on cadence (Q44: "treat as always-complete captures, just
    # track their captured_at cadence"). NOTE (L127): hyperliquid_funding is
    # perp_tape's ONLY cross-venue join partner (scripts/q42_crossvenue_funding_join.py)
    # and has been frozen at its single 2026-07-17 manual backfill (108h+ stale and
    # counting) with no collector ever wired to refresh it — the join silently
    # truncates at that date rather than erroring. Genuinely one-shot by design
    # (correct classification, so interval_h stays None — no cadence/UNDER-CAPTURE
    # expectation). The join-critical staleness that L127 flagged "not fixed here"
    # IS now enforced: the JOIN-STALENESS detector in `evaluate_family` (via
    # JOIN_CRITICAL_ONE_SHOT below) age-alerts this family specifically because a
    # live join depends on it, without giving it a false cadence expectation.
    "hyperliquid_funding":     {"interval_h": None, "passes_per_day": None, "kind": "one-shot-backfill"},
}

# Detector thresholds (documented; edit here, not in the logic).
DEFAULT_WINDOW_HOURS = 24.0
STALE_INTERVAL_MULTIPLE = 2.0   # STALE alert when age_hours > this * interval_h
UNDER_CAPTURE_FLOOR = 0.8       # UNDER-CAPTURE alert when captured/expected < this
UNDER_CAPTURE_MIN_PPD = 6       # ratio detector only runs for families this dense

# Minute-of-hour signature of the two staggered collectors (ops/ROUTINES.md:
# VPS cron :23, cloud trigger :53). Bucketed by ten-minute decile so ordinary
# start-up jitter (observed: VPS lands 20-28, cloud lands 50-59) still
# attributes correctly; anything else is honestly "other", never forced into
# a bucket (L117).
COLLECTOR_MINUTE_BUCKETS: Dict[str, range] = {
    "vps": range(20, 30),
    "cloud": range(50, 60),
}

# Per-family expected collector-bucket map (L120). L118's ``collector_diagnosis``
# only ever names ``vps_dead``/``cloud_dead`` and reads ``vps=0 & cloud=0`` as
# ambiguous/unattributed — which permanently BLINDS it to a family like
# ``weather_books`` whose real second collector lands in NEITHER the named
# ``vps``(:20-29) nor ``cloud``(:50-59) window but in ``other`` (minutes ~00-03).
# Once that family's PRIMARY (vps) leg dies, L118 sees ``vps=0 & cloud=0`` and
# gives up, even though the tape itself proves the primary is the dead leg and
# ``other`` is the sole survivor.
#
# Calibrated against the REAL committed-tape minute-of-hour histograms
# (``tape/<family>/dt=2026-07-18..20``), NOT guessed:
#   * ``weather_books``: PRIMARY leg lands at :27-:28 (``vps`` bucket), SECONDARY
#     leg at :00-:03 (``other`` bucket). Verified: 07-18 vps=4098 lines /
#     other=2410; 07-19 & 07-20 vps=0 while other persists (2940 / 3278). So the
#     VPS primary died 07-19 and ``other`` is the survivor — mapped here so the
#     diagnosis can NAME ``vps_dead`` instead of returning ambiguous.
#   * ``crypto_hourly`` (representative dual-cron, read to anchor the map): PRIMARY
#     :23 (``vps``), SECONDARY :54-:55 (``cloud``). Because its secondary is
#     already the NAMED ``cloud`` bucket, L118's existing vps/cloud logic already
#     attributes it correctly, so it needs NO override and is deliberately left
#     OUT of this map (the same is true of ``orderbook_depth``/``sports_pairs``/
#     the polymarket_* pairs — all standard :2x/:5x dual-cron families).
#
# A family NOT in this map keeps EXACTLY L118's ``vps``/``cloud`` diagnosis — no
# regression. Only a mapped family uses the primary/secondary attribution below.
EXPECTED_COLLECTOR_BUCKETS: Dict[str, Dict[str, str]] = {
    "weather_books": {"primary": "vps", "secondary": "other"},
    # L127: perp_tape's surviving collector lands at minute-of-hour ~00-04, the same
    # "other" bucket as weather_books' secondary leg (both are captured later in the
    # same hourly_pass() call, after the pass has crossed a minute boundary) — without
    # this mapping the real vps-dead state reads as ambiguous (vps=0 & cloud=0).
    "perp_tape": {"primary": "vps", "secondary": "other"},
}

# JOIN-STALENESS detector (L127, 2026-07-21) — enforces the UNENFORCED half of L127.
# ---------------------------------------------------------------------------------
# A one-shot / backfill family (``interval_h=None``) carries NO cadence expectation,
# so neither the STALE nor the UNDER-CAPTURE detector ever fires for it (both are
# structural no-ops when ``interval_h``/``passes_per_day`` are None). That is correct
# for a genuinely one-shot leg — until a LIVE family depends on it for a join, at which
# point its silent staleness is no longer harmless: it silently strangles the join.
# ``hyperliquid_funding`` is exactly this case: it is ``perp_tape``'s ONLY cross-venue
# join partner (``scripts/q42_crossvenue_funding_join.py``) and has been frozen at a
# single 2026-07-17 manual backfill with no collector wired to refresh it, so every
# Kalshi funding window after 07-17 silently has no HL counterpart (the join's
# EXCLUDE-partial-window logic drops it) with no error and no age-alert.
#
# This detector age-alerts such a family SPECIFICALLY because a live join consumes it,
# WITHOUT giving it a false cadence expectation (interval_h stays None, so `dark`
# stays False and no UNDER-CAPTURE ratio is invented). It fires ONLY for the families
# explicitly listed here — every other one-shot family keeps Q44's
# "age-tracked-only, never paged" posture untouched.
#
# Why max_age_h=48.0: the consumed join finalizes funding windows every 8h, so >48h
# stale means ~6 join windows (48/8) have been silently dropped. The 48h threshold
# deliberately mirrors the daily-family STALE posture (STALE_INTERVAL_MULTIPLE=2.0 x
# 24h = 48h) — the same "two missed cadence units before paging" discipline, applied
# to the join's 8h window budget rather than a collector cadence this family doesn't
# have. See L127.
JOIN_CRITICAL_ONE_SHOT: Dict[str, Dict[str, Any]] = {
    "hyperliquid_funding": {"max_age_h": 48.0, "consumer": "scripts/q42_crossvenue_funding_join.py"},
}

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


def collector_bucket(dt: datetime) -> str:
    """Attribute a capture timestamp to "vps" / "cloud" / "other" by its
    minute-of-hour, per ``COLLECTOR_MINUTE_BUCKETS``. Never guesses: a minute
    outside both windows (an ad-hoc live-pass smoke test, a one-off run) is
    honestly "other", not forced into whichever bucket is closer."""
    minute = dt.minute
    for name, bucket in COLLECTOR_MINUTE_BUCKETS.items():
        if minute in bucket:
            return name
    return "other"


def diagnose_collector(family: str,
                       collectors: Dict[str, Dict[str, Any]]) -> Optional[str]:
    """Attribute an alerting hourly-dual family's silence to a dead collector.

    Two paths, both preserving L117/L118's "never guess when ambiguous" rule:

    * **Mapped family (L120).** If ``family`` is in ``EXPECTED_COLLECTOR_BUCKETS``,
      use its ``primary``/``secondary`` bucket names. When exactly one of the two
      expected buckets is zero while the other still produces passes, name the dead
      one (``f"{dead}_dead: 0 passes in window, {alive} collector still
      producing"``). This is what lets ``weather_books`` — whose secondary leg is
      ``other``, not ``cloud`` — read ``vps_dead`` instead of ambiguous. Both
      expected buckets zero (fully dark, already covered by STALE) or both non-zero
      (no single leg to blame) stay unattributed.

    * **Unmapped family.** EXACTLY L118's logic: bucket ``vps``/``cloud`` only —
      one at zero while the other produces => ``vps_dead``/``cloud_dead``; both-zero
      or both-non-zero => unattributed. No behavior change for any family L118
      already handled.

    Returns ``None`` when nothing can be attributed (never a guess).
    """
    mapping = EXPECTED_COLLECTOR_BUCKETS.get(family)
    if mapping is not None:
        primary = mapping["primary"]
        secondary = mapping["secondary"]
        p_n = collectors[primary]["passes"]
        s_n = collectors[secondary]["passes"]
        if p_n == 0 and s_n > 0:
            return f"{primary}_dead: 0 passes in window, {secondary} collector still producing"
        if s_n == 0 and p_n > 0:
            return f"{secondary}_dead: 0 passes in window, {primary} collector still producing"
        return None
    vps_n = collectors["vps"]["passes"]
    cloud_n = collectors["cloud"]["passes"]
    if vps_n == 0 and cloud_n > 0:
        return "vps_dead: 0 passes in window, cloud collector still producing"
    if cloud_n == 0 and vps_n > 0:
        return "cloud_dead: 0 passes in window, vps collector still producing"
    return None


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
        # Same, split by collector-minute bucket (vps/cloud/other) — L117.
        self._window_passes_by_bucket: Dict[str, Dict[str, datetime]] = {
            "vps": {}, "cloud": {}, "other": {}
        }
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
        bucket = collector_bucket(ca)
        bucket_passes = self._window_passes_by_bucket[bucket]
        bprev = bucket_passes.get(key)
        if bprev is None or ca < bprev:
            bucket_passes[key] = ca
        comp = extract_completeness(rec)
        if comp is True:
            self.n_complete += 1
        elif comp is False:
            self.n_incomplete += 1
        else:
            self.n_no_signal += 1

    def collector_summary(self) -> Dict[str, Dict[str, Any]]:
        """Per-bucket (vps/cloud/other) window pass count + newest capture in
        that bucket. Read-only summary of ``_window_passes_by_bucket`` — does
        not affect the aggregate STALE/UNDER-CAPTURE detectors, which stay
        collector-agnostic (a family is healthy if EITHER collector covers
        it)."""
        out: Dict[str, Dict[str, Any]] = {}
        for bucket, passes in self._window_passes_by_bucket.items():
            newest = max(passes.values()) if passes else None
            out[bucket] = {
                "passes": len(passes),
                "newest_captured_at": newest.isoformat() if newest is not None else None,
            }
        return out


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

    # JOIN-STALENESS detector (L127). The STALE block above is a structural no-op
    # for a one-shot family (interval_h is None), so a join-critical one-shot leg
    # going stale is otherwise never paged. For a family explicitly registered in
    # JOIN_CRITICAL_ONE_SHOT, alert when its age exceeds the join's tolerated
    # max_age_h — this is the ONLY family class this detector touches, so no other
    # family's STALE/UNDER-CAPTURE/dark posture changes. Uses the already-computed
    # age_hours; flows through the shared `would_alert = bool(reasons)` path below.
    join_cfg = JOIN_CRITICAL_ONE_SHOT.get(agg.family)
    if join_cfg is not None and age_hours is not None:
        max_age_h = join_cfg["max_age_h"]
        consumer = join_cfg["consumer"]
        if age_hours > max_age_h:
            reasons.append(
                f"join_stale: {age_hours:.1f}h since last pass "
                f"(> {max_age_h:.0f}h threshold) — live join consumer {consumer} "
                f"silently truncates at this date"
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

    # Collector attribution (L117) — only meaningful for the two-collector
    # families; other kinds don't have a VPS/cloud split to attribute to.
    collectors: Optional[Dict[str, Dict[str, Any]]] = None
    collector_diagnosis: Optional[str] = None
    if cfg["kind"] == "hourly-dual":
        collectors = agg.collector_summary()
        # Attribute only the unambiguous case (see ``diagnose_collector``):
        # exactly one expected bucket silent while the other still produces.
        # Both-zero (fully dark, already covered by STALE) and both-non-zero (no
        # single collector to blame) stay unattributed rather than guessed at.
        # A mapped family (L120, e.g. weather_books whose secondary leg is
        # ``other``) can now name a dead PRIMARY that L118 would have read as
        # ambiguous; unmapped families keep L118's exact vps/cloud logic.
        if would_alert:
            collector_diagnosis = diagnose_collector(agg.family, collectors)

    benign = _benign_match(agg.family, newest) if would_alert else None
    if would_alert and benign is not None:
        alert = False
        alert_reason = f"known_benign_silence: {benign['reason']}"
    elif would_alert:
        alert = True
        alert_reason = "; ".join(reasons)
        if collector_diagnosis is not None:
            alert_reason = f"{alert_reason}; {collector_diagnosis}"
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
        "collectors": collectors,
        "collector_diagnosis": collector_diagnosis,
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


def format_collector_diagnoses(report: Dict[str, Dict[str, Any]]) -> str:
    """One line per alerting hourly-dual family that has an unambiguous
    collector attribution (L117) — empty string if none. Kept separate from
    ``format_table`` so a caller that only wants the diagnosis (e.g. an idle
    run's own digest) doesn't have to re-parse the full table."""
    lines: List[str] = []
    for fam, rec in report.items():
        if rec["alert"] and rec.get("collector_diagnosis"):
            lines.append(f"{fam}: {rec['collector_diagnosis']}")
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

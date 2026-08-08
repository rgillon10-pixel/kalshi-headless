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

Retrospective-list family coverage (L171, 2026-07-26)
-------------------------------------------------------
Every detector above measures ``dt=`` day-FILE presence/cadence, which assumes
a family's records are point-in-time observations (one capture, one moment).
That assumption breaks for a family whose record instead embeds a
RETROSPECTIVE LIST of historical observations —
``hyperliquid_funding``'s ``prints[].time_ms`` is the current example: a
catch-up pass after a freeze backfills the ENTIRE missing window into one
record on the catch-up day, so the family can show a multi-day hole in
``dt=`` file presence (``dt=2026-07-18``..``dt=2026-07-21`` absent, the L127
VPS-freeze window) while its actual historical coverage — the union of every
``prints[].time_ms`` across ALL committed files — has zero gaps
(``findings/2026-07-26-hyperliquid-funding-tape-audit.md``). Counting
day-files as coverage for such a family manufactures a false gap finding.
``RETROSPECTIVE_LIST_FAMILIES`` names which families carry this shape (the
embedded list key + per-item timestamp key + the grid's step size);
``retrospective_coverage()`` computes real coverage — span + missing
fixed-step slots — over that embedded-timestamp union instead of file
presence, and ``evaluate_family`` attaches it to a registered family's health
record (informational; does not feed the STALE/UNDER-CAPTURE alert path,
which already correctly reads this family via its forward collector cadence
per L127/L128). A family NOT registered here is unaffected — this is purely
additive.

Capped-pagination span-vs-cadence coverage (L185, 2026-07-27)
--------------------------------------------------------------
Every detector above asks "did the pass RUN?". None of them asks "how much
CALENDAR did the pass actually reach?" — and for a capped, newest-first
paginated harvest with no time-window parameter, those are different
questions with different answers. ``collection/settlement_ledger.py`` pulls
``MAX_SETTLED_MARKETS=5000`` newest-first with no ``min_close_ts``/
``max_close_ts`` once per day (``SETTLEMENT_LEDGER_UTC_HOUR=10``), so each
pass reaches back only ``cap / event_rate`` — ~1.3-3.8h of ``close_time``
against a 24h firing interval, a structural ~13.5% coverage ceiling that MORE
DAYS CANNOT FIX (the cursor just restarts from "now" each day). Every STALE /
UNDER-CAPTURE / completeness signal reads perfectly green while that hole is
wide open.

``CAPPED_PAGINATION_FAMILIES`` names which families carry this shape (the
per-row event-time key, the leg's firing cadence, the cap, a thin-capture
adequacy floor and the flag threshold); ``capped_pagination_span_coverage()``
groups ALL committed lines by ``capture_id`` and reports each capture's
event-time span, its ``span_hours / cadence_hours`` ratio (= the implied
coverage ceiling fraction) and the observed ``rows_per_hour`` that makes
L185's ``cap / event_rate`` arithmetic checkable. ``evaluate_family`` attaches
it to a registered family's record under ``capped_pagination_span``, purely
INFORMATIONALLY — it does not touch ``alert``/``alert_reason`` at all (this is
a design-time cap/window mismatch, not a pipe outage, and it is un-fixable by
a cloud run mid-loop; ``scripts/invariants.py`` surfaces it as a NON-GATING
stderr advisory for the same reason).

What it refuses to guess. A capture with fewer than ``min_rows_for_span``
timestamped rows is reported as NOT-JUDGED, never narrow: a 3-row capture has
a short span for entirely legitimate reasons (thin hour, tail page), and
calling that a coverage failure would be a fabricated finding — the same "no
signal, never a guess" discipline as ``extract_completeness``. Rows with a
missing/malformed event time are skipped (never fabricated to now), and a
capture with no parseable time at all is NOT-JUDGED, not silently "ok". A
family not registered here gets ``None`` — this function makes no claim about
a shape it wasn't told about. The self-check that the measurement is real: the
``settlement_ledger`` family's own 605-row ``migrated:q26_settlement_cache``
legacy backfill spans ~8 days and is correctly NOT flagged, while the three
live ``live_settled_markets`` captures on the same tape are.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
from bisect import bisect_left
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from collection import burst_capture as _burst_capture

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
    # L139: `anomalies` (collection/hourly_pass.py runs `scripts/anomaly_sweep.py` as a
    # subprocess only when `ts.hour == ANOMALY_SWEEP_UTC_HOUR` (9), the exact same
    # single-exact-UTC-hour gate shape as `settlement_ledger` (L123) and
    # `weather_actuals` (L126) before they were registered here — and, like both of
    # those, `anomalies` was simply never added to FAMILY_CONFIG. Since the default
    # report only iterates `list(FAMILY_CONFIG.keys())`, an unregistered family isn't
    # merely mis-scored, it is never EVALUATED at all: a silent freeze here (the same
    # failure mode that hit settlement_ledger for 5 days and weather_actuals for 2)
    # would have no detector watching it, unlike its sibling daily-econ-slot legs.
    # Registering it closes that blind spot pre-emptively, before it bites, rather
    # than after (unlike L123/L126, `anomalies` is NOT currently frozen — see L139).
    "anomalies":               {"interval_h": 24.0, "passes_per_day": 1,    "kind": "daily-econ-slot"},
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
    # L127/L128 close-out (candidate (a), 2026-07-21): hyperliquid_funding is NO LONGER a
    # frozen one-shot. `collection.hyperliquid_funding.run_incremental` is now wired into
    # `collection/hourly_pass.py` and runs EVERY pass, union-appending only genuinely-new
    # hourly prints — so the family now has a real forward cadence and its freeze is caught
    # by the STALE detector at 2h instead of the old 48h join-staleness stopgap (which it has
    # therefore graduated out of; see JOIN_CRITICAL_ONE_SHOT below). It is STALE-only
    # (passes_per_day=None => the UNDER-CAPTURE ratio detector is a no-op), NOT hourly-dual,
    # for a structural reason: it is single-WRITE per new HL hourly print, not per pass. HL
    # posts hourly at :00; whichever staggered collector runs first after a new print archives
    # it (VPS :23 in steady state), the other (cloud :53) then finds nothing new and writes no
    # line — so the tape carries ~24 records/day landing in whatever bucket won the race, NOT
    # the ~48/day two-writer shape the UNDER-CAPTURE ratio and the vps/cloud attribution assume.
    # A fixed passes_per_day would false-alarm (cloud legitimately writes 0 in a healthy VPS
    # window) and the collector self-heals across collectors anyway (if VPS dies, cloud catches
    # every print, losing no data — the very failure a ratio would misread). STALE (2h) is the
    # correct degradation detector here: it fires only when BOTH collectors miss ~2 consecutive
    # opportunities or HL genuinely stops — the true "join is going stale" signal.
    "hyperliquid_funding":     {"interval_h": 1.0,  "passes_per_day": None, "kind": "hourly"},
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
# Currently EMPTY (L127/L128 close-out, 2026-07-21): hyperliquid_funding — the family this
# detector was built for (L128) — GRADUATED to a forward-refreshed hourly family this run
# (candidate (a) of L127: `run_incremental` wired into `collection/hourly_pass.py`). Its freeze
# is now caught by the STALE detector at 2h (see FAMILY_CONFIG above), which strictly subsumes
# the old 48h join-staleness stopgap, so it no longer needs — and would be double-flagged by —
# a JOIN_CRITICAL_ONE_SHOT entry. The mechanism below is RETAINED (dormant) for any FUTURE
# genuinely-one-shot leg that a live join comes to depend on; register it here the moment that
# arises rather than re-deriving the detector.
JOIN_CRITICAL_ONE_SHOT: Dict[str, Dict[str, Any]] = {}

# FIELD-HEALTH detector (L307, 2026-08-08).
# ------------------------------------------------------------------------------------
# A family can pass every STALE/UNDER-CAPTURE/JOIN-STALENESS check above while a
# join-critical SUB-FIELD inside its own records is 100% dead for weeks: none of those
# detectors can see it, since a file's mtime, its line count, and its inter-pass gap are
# the only three things they observe, and a dead sub-field changes none of the three.
# ``tape/sports_pairs/`` is exactly this case — registered in FAMILY_CONFIG, passing
# every check, cadence normal, not stale — while its ``odds_leg`` sub-object (the S7/S11
# external sharp-odds fair-anchor join) has produced ZERO ``matched`` rows on any day
# since 2026-07-19, invisible to every detector registered before this one.
#
# Each entry:
#   json_path                : dotted path to the field inside each record.
#   healthy_predicate         : callable(value) -> bool, judging a PRESENT field value
#                               only. The field being entirely ABSENT on a record (a
#                               schema the record never carried) is never fed to this
#                               predicate — it is its own day-class (``field_absent``),
#                               per L289/L298's counter-absent-vs-empty-denominator rule;
#                               collapsing "never had the field" into "unhealthy" would
#                               let a schema change read as an instant outage.
#   max_consecutive_bad_days : the trailing consecutive-BAD-DAY run length that ALERTS
#                              (``field_degraded``). Measured per DAY, not per pass —
#                              L307's design constraint: a single bad pass is noise,
#                              N straight days is an outage.
#
# sports_pairs -> odds_leg.status: healthy = ``matched`` (the only status that actually
# feeds the anchor; ``blocked_key``/``unmapped_series``/``not_selected``/``unmatched`` are
# all live refusals, not signal-free days). Calibrated against committed tape: every day
# in the one week the anchor ever worked (2026-07-12..07-18) carries >=1 ``matched`` row
# (6/48/45/25/48/48/20); every day since (2026-07-19 onward, verified through 2026-08-07)
# carries exactly 0 — so ``max_consecutive_bad_days=7`` catches the real outage at roughly
# a third of its true length (it reached 20 straight days before this detector existed)
# while never firing during the healthy week itself.
FIELD_HEALTH_FAMILIES: Dict[str, Dict[str, Any]] = {
    "sports_pairs": {
        "json_path": ("odds_leg", "status"),
        "healthy_predicate": lambda v: v == "matched",
        "max_consecutive_bad_days": 7,
        "note": ("L307: the S7/S11 external sharp-odds fair-anchor join. Every day of the "
                 "one week the anchor ever worked carries >=1 `matched` row; every day "
                 "since 2026-07-19 carries 0 (measured through 2026-08-07: 20 straight "
                 "days) while the family itself reads perfectly healthy on every "
                 "existing cadence/staleness check."),
    },
}
FIELD_HEALTH_DEFAULT_MAX_BAD_DAYS = 7

# Retrospective-list family coverage map (L171, 2026-07-26). See module
# docstring. ``list_key``: the record field holding the embedded observation
# list. ``time_key``: the per-item epoch-milliseconds timestamp field.
# ``step_seconds``: the list's own fixed grid spacing (used only to size the
# expected-slot count between the observed min/max — never to infer a family
# NOT registered here).
RETROSPECTIVE_LIST_FAMILIES: Dict[str, Dict[str, Any]] = {
    "hyperliquid_funding": {"list_key": "prints", "time_key": "time_ms", "step_seconds": 3600},
}

# Capped-pagination span-vs-cadence map (L185, 2026-07-27). See module docstring.
# A family listed here harvests newest-first under a row CAP with NO time-window
# request parameter, so each pass reaches back only `cap / event_rate` of calendar
# regardless of how often the leg fires. Registering a second such collector is one
# entry here — nothing about this check is settlement_ledger-specific.
#   time_key         : the per-row EVENT-time field (NOT `captured_at` — the point is
#                      the gap between when the pass ran and how far back it reached).
#   cadence_hours    : the leg's firing interval, i.e. the calendar each pass must cover
#                      to have no hole.
#   cap              : the collector's own row cap, quoted for the advisory text.
#   min_rows_for_span: adequacy floor. Below this many timestamped rows a capture is
#                      NOT-JUDGED, never flagged — a thin capture has a short span for
#                      legitimate reasons and calling that a coverage failure would be
#                      a fabricated finding.
#   span_ratio_alert : flag when span_hours / cadence_hours falls below this.
# settlement_ledger provenance (measured on committed tape, 2026-07-27):
#   MAX_SETTLED_MARKETS = 5000 (collection/settlement_ledger.py:84), no min_close_ts /
#   max_close_ts anywhere in the request; fires once/day at SETTLEMENT_LEDGER_UTC_HOUR
#   = 10 (collection/hourly_pass.py:150). Observed live spans 800 rows/1.26h,
#   4200/3.83h, 5000/3.25h => ratios 0.053/0.160/0.135 against a 24h interval.
#   min_rows_for_span=50: an order of magnitude below the smallest observed live
#   capture (800) and below the 605-row legacy backfill, so it excludes only genuinely
#   thin/one-off captures, never a real harvest. span_ratio_alert=0.5: half a firing
#   interval — a pass covering less than half the calendar it is responsible for has a
#   structural hole; the observed live ratios sit ~3-10x below it, and the ~8-day
#   legacy backfill (ratio ~8.1) sits far above, so the threshold is not load-bearing
#   for either verdict on today's tape.
CAPPED_PAGINATION_FAMILIES: Dict[str, Dict[str, Any]] = {
    "settlement_ledger": {
        "time_key": "close_time",
        "cadence_hours": 24.0,
        "cap": 5000,
        "min_rows_for_span": 50,
        "span_ratio_alert": 0.5,
    },
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


def retrospective_coverage(tape_root: Path, family: str) -> Optional[Dict[str, Any]]:
    """Real coverage for a retrospective-list family (L171): the union of every
    embedded per-observation timestamp across ALL of the family's committed
    ``dt=*.jsonl`` files, NOT ``dt=`` day-file presence — a catch-up pass can
    backfill a whole missing window into one record on the catch-up day, which
    file-presence coverage would misread as a gap on the days the collector
    itself was silent (see module docstring, ``findings/2026-07-26-hyperliquid-
    funding-tape-audit.md``).

    Returns ``None`` for a family not registered in
    ``RETROSPECTIVE_LIST_FAMILIES`` — this function makes no claim about a
    family it wasn't told carries this shape. Malformed/missing embedded
    timestamps are skipped (never fabricated into the union), mirroring
    ``extract_completeness``'s "no signal, never a guess" discipline.
    """
    cfg = RETROSPECTIVE_LIST_FAMILIES.get(family)
    if cfg is None:
        return None
    list_key = cfg["list_key"]
    time_key = cfg["time_key"]
    step_s = cfg["step_seconds"]

    seen_ms: set = set()
    for _d, path in _family_files(tape_root, family):
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
                items = rec.get(list_key)
                if not isinstance(items, list):
                    continue
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    t = item.get(time_key)
                    if isinstance(t, (int, float)) and not isinstance(t, bool):
                        seen_ms.add(int(t))

    if not seen_ms:
        return {
            "family": family,
            "n_observations": 0,
            "span_start": None,
            "span_end": None,
            "step_seconds": step_s,
            "n_missing_steps": None,
        }

    lo, hi = min(seen_ms), max(seen_ms)
    step_ms = step_s * 1000
    n_expected_steps = (hi - lo) // step_ms + 1
    n_missing = max(0, int(n_expected_steps) - len(seen_ms))
    return {
        "family": family,
        "n_observations": len(seen_ms),
        "span_start": datetime.fromtimestamp(lo / 1000.0, tz=timezone.utc).isoformat(),
        "span_end": datetime.fromtimestamp(hi / 1000.0, tz=timezone.utc).isoformat(),
        "step_seconds": step_s,
        "n_missing_steps": n_missing,
    }


def _parse_event_time(ts: Optional[str]) -> Optional[datetime]:
    """``_parse_iso`` with a bare-``Z`` suffix normalization.

    Committed ``settlement_ledger`` rows write ``close_time`` as
    ``2026-07-22T10:30:00Z`` (bare ``Z``), which ``datetime.fromisoformat`` —
    and therefore ``_parse_iso`` — cannot parse on Python < 3.11. Rewriting the
    suffix to ``+00:00`` is a pure string normalization, not a second parser:
    this file keeps exactly ONE ``datetime.fromisoformat`` call site (the
    gating ``inv_no_raw_datetime_fromisoformat`` allowance), and anything still
    unparseable stays ``None`` rather than being guessed at."""
    if isinstance(ts, str) and ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    return _parse_iso(ts)


def capped_pagination_span_coverage(tape_root: Path,
                                    family: str) -> Optional[Dict[str, Any]]:
    """Per-``capture_id`` event-time SPAN vs the leg's firing CADENCE (L185).

    A capped, newest-first-paginated harvest with no time-window request
    parameter reaches back only ``cap / event_rate`` of calendar per pass,
    independent of how often the leg runs and NOT improvable by accumulating
    more days. This groups every committed line of ``family`` by ``capture_id``,
    measures each capture's min/max of the configured event-time field, and
    flags the captures whose span is small relative to the firing interval.

    Returns ``None`` for a family not registered in
    ``CAPPED_PAGINATION_FAMILIES`` — no claim is made about a shape this
    function wasn't told the family has (same refusal as
    ``retrospective_coverage``).

    What it refuses to guess (mirrors ``extract_completeness``'s "no signal,
    never a guess"):

    * a capture with fewer than ``min_rows_for_span`` PARSEABLE-time rows is
      ``judged=False`` with ``not_judged_reason="below_min_rows_for_span"`` —
      counted in ``n_captures_not_judged``, never in ``n_captures_narrow`` and
      never folded into "ok";
    * a row whose event time is absent/malformed is skipped, never fabricated;
      a capture with zero parseable times is
      ``not_judged_reason="no_parseable_event_times"``;
    * a judged capture with an exactly-zero span is genuinely narrow (all rows
      share one instant), but its ``rows_per_hour`` is ``None`` — undefined, not
      an invented infinity.

    Per-capture fields: ``capture_id``, ``n_rows`` (all lines),
    ``n_rows_with_time``, ``span_start``/``span_end``, ``span_hours``,
    ``span_ratio`` (= span/cadence = ``coverage_ceiling_fraction``, L185's
    ceiling made computable), ``rows_per_hour`` (the observed event rate the cap
    is being spent against), ``judged``, ``narrow``, ``not_judged_reason``.
    """
    cfg = CAPPED_PAGINATION_FAMILIES.get(family)
    if cfg is None:
        return None
    time_key = cfg["time_key"]
    cadence_h = float(cfg["cadence_hours"])
    min_rows = int(cfg["min_rows_for_span"])
    ratio_alert = float(cfg["span_ratio_alert"])

    # capture_id -> [n_rows, n_rows_with_time, min_dt, max_dt]. Only 4 scalars per
    # capture are retained, so a 10k+-line family stays memory-bounded (L10).
    by_capture: Dict[str, Dict[str, Any]] = {}
    for _d, path in _family_files(tape_root, family):
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
                if not isinstance(rec, dict):
                    continue
                cid = rec.get("capture_id")
                if not isinstance(cid, str) or not cid:
                    # No capture_id => no pass to attribute the row to. Skipped
                    # honestly rather than lumped into a synthetic bucket.
                    continue
                slot = by_capture.setdefault(
                    cid, {"n_rows": 0, "n_rows_with_time": 0, "lo": None, "hi": None})
                slot["n_rows"] += 1
                dt = _parse_event_time(rec.get(time_key))
                if dt is None:
                    continue
                slot["n_rows_with_time"] += 1
                if slot["lo"] is None or dt < slot["lo"]:
                    slot["lo"] = dt
                if slot["hi"] is None or dt > slot["hi"]:
                    slot["hi"] = dt

    captures: List[Dict[str, Any]] = []
    for cid in sorted(by_capture):
        slot = by_capture[cid]
        rec_out: Dict[str, Any] = {
            "capture_id": cid,
            "n_rows": slot["n_rows"],
            "n_rows_with_time": slot["n_rows_with_time"],
            "span_start": slot["lo"].isoformat() if slot["lo"] is not None else None,
            "span_end": slot["hi"].isoformat() if slot["hi"] is not None else None,
            "span_hours": None,
            "span_ratio": None,
            "coverage_ceiling_fraction": None,
            "rows_per_hour": None,
            "judged": False,
            "narrow": False,
            "not_judged_reason": None,
        }
        if slot["n_rows_with_time"] == 0:
            rec_out["not_judged_reason"] = "no_parseable_event_times"
            captures.append(rec_out)
            continue
        if slot["n_rows_with_time"] < min_rows:
            rec_out["not_judged_reason"] = "below_min_rows_for_span"
            span_h = (slot["hi"] - slot["lo"]).total_seconds() / 3600.0
            rec_out["span_hours"] = round(span_h, 4)
            captures.append(rec_out)
            continue

        span_h = (slot["hi"] - slot["lo"]).total_seconds() / 3600.0
        ratio = span_h / cadence_h if cadence_h > 0 else None
        rec_out["judged"] = True
        rec_out["span_hours"] = round(span_h, 4)
        rec_out["span_ratio"] = round(ratio, 6) if ratio is not None else None
        rec_out["coverage_ceiling_fraction"] = rec_out["span_ratio"]
        if span_h > 0:
            rec_out["rows_per_hour"] = round(slot["n_rows_with_time"] / span_h, 2)
        rec_out["narrow"] = ratio is not None and ratio < ratio_alert
        captures.append(rec_out)

    judged = [c for c in captures if c["judged"]]
    narrow = [c for c in judged if c["narrow"]]
    return {
        "family": family,
        "time_key": time_key,
        "cadence_hours": cadence_h,
        "cap": cfg["cap"],
        "min_rows_for_span": min_rows,
        "span_ratio_alert": ratio_alert,
        "n_captures": len(captures),
        "n_captures_judged": len(judged),
        "n_captures_not_judged": len(captures) - len(judged),
        "n_captures_narrow": len(narrow),
        "captures": captures,
        "narrow_captures": narrow,
    }


# ─── Completeness-cap saturation detector (L270: non-gating, offline-safe) ─────
#
# L270: a bounded-collector leg whose `completeness_ok` is derived from `cursor_exhausted`
# (`collection/universe_sweep.py:224` `completeness_ok = cursor_exhausted and n_parse_errors
# == 0`) reports FALSE on every pass whose own page cap sits below the population it
# enumerates -- a property of the cap vs. the universe size, not a per-pass failure.
# `collection/hourly_pass.py:587` ANDs every leg's own `completeness_ok` into one pass-level
# signal and `collection/hourly_pass.py:635` exits 1 on any False; `ops/vps/kalshi-headless-
# hourly.sh:86-87` fires a `Priority:high` phone notification on that nonzero exit. When a
# leg's `completeness_ok` is STRUCTURALLY False on (nearly) 100% of real passes -- the cap is
# permanently below the universe, by design -- the pager fires for a standing, already-known
# fact, indistinguishable in both the exit code and the notification text from a genuine new
# outage. Measured on committed tape 2026-08-03: `universe_sweep` (`MAX_CALLS=20 *
# PAGE_LIMIT=1000` = 20,000 rows/pass, `collection/universe_sweep.py:74-75`) sits AT its cap
# on 35/35 committed captures.
#
# `settlement_ledger` carries the same shape (see the `CAPPED_PAGINATION_FAMILIES` provenance
# comment above -- `MAX_SETTLED_MARKETS=5000`) but is NOT always at cap in practice (800/1.26h,
# 4200/3.83h, 5000/3.25h observed) -- honestly MEASURED per family, never assumed from the cap
# alone.
#
# NON-GATING: whether a bounded collector's cap should be raised, or whether `hourly_pass`'s
# AND should carve known-saturated legs onto a separate axis, is Ryan's design call -- the
# exact question `kb/00-LOG.md` raised for `settlement_ledger` on 2026-07-17 and left open,
# not something a cloud run can decide or repair mid-loop. Same posture as every other
# tape-shape advisory in this module.
#
# Single source of truth: `COMPLETENESS_CAP_FAMILIES` and the computation live here, imported
# into scripts/invariants.py via the existing `_load_tape_gap_monitor` path (the L100
# duplication trap), never re-declared there.

COMPLETENESS_CAP_FAMILIES: Dict[str, Dict[str, Any]] = {
    "universe_sweep": {"cap": 20000, "min_captures_for_verdict": 3},
    "settlement_ledger": {"cap": 5000, "min_captures_for_verdict": 3},
}

# Only flag a family whose measured at-cap fraction clears this threshold -- a family that
# occasionally, not structurally, reaches its cap is a capacity/adequacy question (L185's
# territory), not a saturated-signal one.
COMPLETENESS_CAP_SATURATION_ALERT_FRACTION = 0.90


def completeness_cap_saturation(tape_root: Path, family: str) -> Optional[Dict[str, Any]]:
    """Fraction of ``family``'s committed captures whose line count sits EXACTLY at the
    collector's own page cap (L270) -- computed from committed tape only, no network.

    Returns ``None`` for a family not registered in ``COMPLETENESS_CAP_FAMILIES`` (no claim
    about a shape this function wasn't told the family has, same refusal as
    ``capped_pagination_span_coverage``) and for a family with fewer than
    ``min_captures_for_verdict`` distinct ``capture_id``s (adequacy floor -- a thin sample
    cannot support a saturation verdict either way).
    """
    cfg = COMPLETENESS_CAP_FAMILIES.get(family)
    if cfg is None:
        return None
    cap = int(cfg["cap"])
    min_captures = int(cfg["min_captures_for_verdict"])

    by_capture: Dict[str, int] = {}
    for _d, path in _family_files(tape_root, family):
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
                if not isinstance(rec, dict):
                    continue
                cid = rec.get("capture_id")
                if not isinstance(cid, str) or not cid:
                    # No capture_id => no pass to attribute the row to. Skipped honestly
                    # rather than lumped into a synthetic bucket.
                    continue
                by_capture[cid] = by_capture.get(cid, 0) + 1

    n_captures = len(by_capture)
    if n_captures < min_captures:
        return None

    n_at_cap = sum(1 for n in by_capture.values() if n == cap)
    fraction = n_at_cap / n_captures

    return {
        "family": family,
        "cap": cap,
        "n_captures": n_captures,
        "n_at_cap": n_at_cap,
        "fraction_at_cap": round(fraction, 4),
        "saturated": fraction >= COMPLETENESS_CAP_SATURATION_ALERT_FRACTION,
    }


# ─── Expected-window-grid coverage detector (L208: non-gating, offline-safe) ────
#
# L208: a per-window density statistic computed only over windows that produced >=1
# observation is a SURVIVORSHIP statistic, not a coverage statistic. A window in which the
# collector never fired cannot enter it at all, so the metric reads healthy exactly where
# coverage is worst. The honest denominator is the EXPECTED window grid.
#
# The lesson's own enforcement candidate says the grid must be "keyed to a collector's own
# cadence instead of a fixed interval" — and that phrase is load-bearing in a way the
# worked example itself missed. `findings/2026-07-27-perp-tape-audit.md` (PERP-F1) built its
# 33-window grid by binning `captured_at` into 8h CALENDAR bins anchored at 00Z. But Kalshi
# perps' funding boundaries, read off the collector's own `next_funding_time` field, land on
# the **04/12/20Z** grid — every committed `funding_estimate` row in `tape/perp_tape/` is on
# that anchor, none on 00/08/16. A 00Z-anchored bin is therefore a different object from a
# funding window, and the two disagree about WHICH windows are empty (see the finding
# `findings/2026-07-30-l208-window-grid-coverage.md`). So:
#
#   * the grid is enumerated from the family's OWN boundary field (`window_key`), never from
#     `captured_at` and never from a fixed wall-clock bin;
#   * the anchor is CONFIGURED and then VALIDATED against the data — a window key that is not
#     on the configured (width, anchor) grid is counted in `n_offgrid_window_keys` and
#     reported, NEVER snapped to the nearest slot. Silently snapping is precisely how a
#     mis-anchored grid produces a confident wrong answer;
#   * the observed-only statistic and the grid-filled statistic are BOTH reported, side by
#     side, so the survivorship gap L208 names is a visible number rather than an inference.
#
# Density unit is the distinct capture PASS (`capture_id`), because that is what "a window
# with zero capture passes" means and it is what a per-window path-length statistic is
# actually made of. Known blind spot, stated rather than papered over: `capture_id` is a
# second-granularity label, so two invocations colliding in one second count as one pass
# here (exactly the L210 defect this module already reports separately) — a collision makes
# this detector's density read LOW, i.e. toward flagging, never toward a false all-clear.
#
# NON-GATING. A zero-capture window is a permanently unrecoverable historical fact: the
# collector destroys the premium path at each boundary with no re-fetch, so no run can
# repair it and gating would halt the loop forever over the past. Same posture as the
# hollow-ladder / capped-pagination advisories: it PRINTS, it never flips the exit code.

# family -> window-grid spec. `window_key` is the collector's OWN boundary field.
# `anchor_hour_utc` is the hour of ONE real grid boundary (any of them; the grid is
# `anchor + k*window_hours`). `thin_max_passes` is the density at or below which a window
# carries no usable PATH — 1 sample is a point, not a path (L208's "12/33 path-inadequate"
# counted 1-sample windows alongside the zero ones).
WINDOW_GRIDDED_FAMILIES: Dict[str, Dict[str, Any]] = {
    "perp_tape": {
        "record_type": "funding_estimate",
        "window_key": "next_funding_time",
        "window_hours": 8.0,
        "anchor_hour_utc": 4,
        "thin_max_passes": 1,
    },
}

_GRID_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _on_grid(dt: datetime, window_hours: float, anchor_hour_utc: int) -> bool:
    """True when ``dt`` falls exactly on the ``anchor + k*window_hours`` UTC grid.

    Exactness is deliberate: a funding/settlement boundary is published on the hour, so a
    boundary that is even a minute off-grid means the venue changed its cadence (or the
    field is not the boundary we think it is) — a fact to REPORT, never to round away."""
    period = window_hours * 3600.0
    if period <= 0:
        return False
    offset = (dt - _GRID_EPOCH).total_seconds() - anchor_hour_utc * 3600.0
    return abs(offset % period) < 1e-6


def expected_window_grid_coverage(tape_root: Path,
                                  family: str,
                                  days: Optional[Sequence[str]] = None
                                  ) -> Optional[Dict[str, Any]]:
    """Expected window GRID vs observed windows for a window-bucketed family (L208).

    Returns ``None`` for a family not registered in ``WINDOW_GRIDDED_FAMILIES`` — no claim
    is made about a shape this function wasn't told the family has (same refusal as
    ``retrospective_coverage`` / ``capped_pagination_span_coverage``).

    ``days`` optionally restricts the scan to an explicit list of ``dt=YYYY-MM-DD`` day
    stems. This exists for L191: a real-tape acceptance test must pin a FROZEN slice, or a
    live, still-growing family red-lines the gate on ordinary capture with zero code change.

    What it refuses to guess:

    * a row of the wrong ``record_type``, or with an absent/unparseable ``window_key``, is
      skipped and counted (``n_rows_skipped_no_window_key``) — never bucketed into a
      neighbouring window;
    * a window key that is NOT on the configured grid is counted in
      ``n_offgrid_window_keys`` (with up to 5 examples) and excluded — never snapped;
    * with zero on-grid observations the grid is undefined, so it reports
      ``n_windows_expected = 0`` and ``reason = "no_on_grid_window_keys"`` rather than
      inventing a span.

    Fields: ``grid_start``/``grid_end``/``n_windows_expected`` (the honest denominator),
    ``n_windows_observed``, ``n_windows_zero_capture`` + ``zero_capture_windows``,
    ``n_windows_thin`` + ``path_inadequate_fraction`` (thin INCLUDES zero — a zero window is
    the extreme thin window), ``observed_only`` vs ``grid_filled`` pass-count summaries, and
    ``survivorship_gap_median`` (= observed-only median - grid-filled median), the single
    number that makes L208's distortion visible.
    """
    cfg = WINDOW_GRIDDED_FAMILIES.get(family)
    if cfg is None:
        return None
    record_type = cfg.get("record_type")
    window_key = cfg["window_key"]
    window_hours = float(cfg["window_hours"])
    anchor = int(cfg["anchor_hour_utc"])
    thin_max = int(cfg["thin_max_passes"])

    wanted_days = set(days) if days is not None else None
    passes_by_window: Dict[datetime, Set[str]] = {}
    n_rows_considered = 0
    n_rows_skipped = 0
    offgrid_examples: List[str] = []
    n_offgrid = 0

    for _d, path in _family_files(tape_root, family):
        if wanted_days is not None and path.stem not in wanted_days:
            continue
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
                if not isinstance(rec, dict):
                    continue
                if record_type is not None and rec.get("record_type") != record_type:
                    continue
                n_rows_considered += 1
                dt = _parse_event_time(rec.get(window_key))
                if dt is None:
                    n_rows_skipped += 1
                    continue
                if not _on_grid(dt, window_hours, anchor):
                    n_offgrid += 1
                    if len(offgrid_examples) < 5:
                        offgrid_examples.append(dt.isoformat())
                    continue
                cid = rec.get("capture_id")
                # No capture_id => the row cannot be attributed to a pass. Counted as its
                # own singleton so the window is never wrongly read as EMPTY, but never
                # merged with a real pass either.
                key = cid if isinstance(cid, str) and cid else f"__nocid__{len(passes_by_window)}"
                passes_by_window.setdefault(dt, set()).add(key)

    base: Dict[str, Any] = {
        "family": family,
        "record_type": record_type,
        "window_key": window_key,
        "window_hours": window_hours,
        "anchor_hour_utc": anchor,
        "thin_max_passes": thin_max,
        "days_scanned": sorted(wanted_days) if wanted_days is not None else None,
        "n_rows_considered": n_rows_considered,
        "n_rows_skipped_no_window_key": n_rows_skipped,
        "n_offgrid_window_keys": n_offgrid,
        "offgrid_examples": offgrid_examples,
    }
    if not passes_by_window:
        base.update({
            "reason": "no_on_grid_window_keys",
            "grid_start": None,
            "grid_end": None,
            "n_windows_expected": 0,
            "n_windows_observed": 0,
            "n_windows_zero_capture": 0,
            "zero_capture_windows": [],
            "n_windows_thin": 0,
            "path_inadequate_fraction": None,
            "coverage_fraction": None,
            "observed_only": {"median_passes": None, "min_passes": None, "max_passes": None},
            "grid_filled": {"median_passes": None, "min_passes": None, "max_passes": None},
            "survivorship_gap_median": None,
        })
        return base

    lo = min(passes_by_window)
    hi = max(passes_by_window)
    step = timedelta(hours=window_hours)
    grid: List[datetime] = []
    cursor = lo
    while cursor <= hi:
        grid.append(cursor)
        cursor += step

    per_window = [len(passes_by_window.get(w, set())) for w in grid]
    observed = [n for n in per_window if n > 0]
    zero_windows = [w for w in grid if not passes_by_window.get(w)]
    thin_windows = [w for w in grid if len(passes_by_window.get(w, set())) <= thin_max]

    obs_median = statistics.median(observed) if observed else None
    grid_median = statistics.median(per_window)
    base.update({
        "reason": None,
        "grid_start": lo.isoformat(),
        "grid_end": hi.isoformat(),
        "n_windows_expected": len(grid),
        "n_windows_observed": len(observed),
        "n_windows_zero_capture": len(zero_windows),
        "zero_capture_windows": [w.isoformat() for w in zero_windows],
        "n_windows_thin": len(thin_windows),
        "path_inadequate_fraction": round(len(thin_windows) / len(grid), 6),
        "coverage_fraction": round(len(observed) / len(grid), 6),
        "observed_only": {
            "median_passes": obs_median,
            "min_passes": min(observed) if observed else None,
            "max_passes": max(observed) if observed else None,
        },
        "grid_filled": {
            "median_passes": grid_median,
            "min_passes": min(per_window),
            "max_passes": max(per_window),
        },
        "survivorship_gap_median": (
            round(float(obs_median) - float(grid_median), 6) if obs_median is not None else None
        ),
    })
    return base


# ─── Wall-clock-slot cadence (L213: non-gating, offline-safe) ───────────────────

def slot_cadence_by_time_of_day(tape_root: Path,
                                family: str,
                                window_start: str,
                                window_end: str,
                                days: Optional[Sequence[str]] = None,
                                ) -> Dict[str, Any]:
    """Per-day distinct-pass count within a fixed UTC time-of-day window (L213).

    A family's PER-DAY AVERAGE cadence can look perfectly healthy while a specific
    wall-clock slot inside every day is never covered — the question that matters
    before relying on a recurring collector as the fallback for a one-shot burst
    trigger. L213: over 07-18..07-27, `polymarket_macro_pairs` landed dozens of
    passes/day on average yet exactly ZERO of them fell inside 17:40-18:30Z, the
    slot the 2026-07-29T18:00Z FOMC statement needed — invisible to any check that
    only asks "how many passes today", never "which minutes of today".

    ``window_start``/``window_end`` are "HH:MM" 24h UTC strings with
    ``window_start <= window_end`` — a midnight-wrapping window raises
    ``ValueError`` rather than silently doing the wrong thing (no burst release in
    this project's tape is scheduled across a UTC midnight).

    ``days`` restricts the scan to an explicit list of ``dt=YYYY-MM-DD`` stems and,
    when given, every requested day is reported even if the family has no file for
    it at all (a genuinely missing day is a zero-pass day, not a silent skip). Same
    FROZEN-slice discipline as ``expected_window_grid_coverage`` (L191): a real-tape
    acceptance test must pin an explicit ``days`` list, never a live glob. With
    ``days=None`` every committed day-file the family has is scanned instead.

    Returns per-day distinct ``capture_id`` counts inside the slot
    (``per_day_pass_count``) plus ``n_days_zero``/``zero_days``/``all_days_zero`` —
    the single boolean L213's own finding collapses to. ``n_days_scanned == 0``
    (no requested day and no committed file) is reported honestly, never read as
    "safe" or "risky" by the caller.
    """
    start_h, start_m = (int(x) for x in window_start.split(":"))
    end_h, end_m = (int(x) for x in window_end.split(":"))
    start_t = time(start_h, start_m)
    end_t = time(end_h, end_m)
    if end_t < start_t:
        raise ValueError(
            f"window_end {window_end!r} is before window_start {window_start!r} "
            "(midnight-wrapping windows are not supported)"
        )

    wanted_days = list(days) if days is not None else None
    by_day: Dict[str, Set[str]] = {d: set() for d in wanted_days} if wanted_days is not None else {}

    for _d, path in _family_files(tape_root, family):
        stem = path.stem
        if wanted_days is not None and stem not in by_day:
            continue
        try:
            fh = open(path, "r", encoding="utf-8")
        except OSError:
            continue
        day_passes = by_day.setdefault(stem, set())
        with fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    continue
                if not isinstance(rec, dict):
                    continue
                ca = _parse_iso(rec.get("captured_at"))
                if ca is None:
                    continue
                ca_utc_time = ca.astimezone(timezone.utc).time()
                if not (start_t <= ca_utc_time <= end_t):
                    continue
                cid = rec.get("capture_id")
                key = cid if isinstance(cid, str) and cid else ca.isoformat()
                day_passes.add(key)

    per_day_counts = {day: len(s) for day, s in sorted(by_day.items())}
    zero_days = [day for day, n in per_day_counts.items() if n == 0]
    return {
        "family": family,
        "window_start": window_start,
        "window_end": window_end,
        "days_scanned": sorted(wanted_days) if wanted_days is not None else None,
        "n_days_scanned": len(per_day_counts),
        "per_day_pass_count": per_day_counts,
        "n_days_zero": len(zero_days),
        "zero_days": zero_days,
        "all_days_zero": len(per_day_counts) > 0 and len(zero_days) == len(per_day_counts),
    }


# ─── Colliding-capture_id detector (L210: non-gating, offline-safe) ─────────────

# `capture_id` is a SECOND-GRANULARITY pass LABEL (`YYYYMMDDThhmmssZ`), not a unique
# capture key. Two things can therefore share one id:
#
#   (a) BENIGN — one pass that walks several items and stamps each row with its own
#       `captured_at` (a ladder/burst round). `hf_burst`'s single committed capture_id
#       covers 10 strikes over 1.3s. Grouping those by capture_id is CORRECT: they are
#       one round.
#   (b) HAZARDOUS — two genuinely DISTINCT invocations that happened to start inside the
#       same wall-clock second, e.g. a `--backfill-funding` one-shot landing on top of a
#       scheduled `perp_tape` pass (L210's original observation). A consumer that groups
#       or de-duplicates by capture_id then sees ONE pass where there were TWO, silently
#       merging two different payloads.
#
# The discriminator between (a) and (b) is NOT "how many `captured_at` values does this
# capture_id have" — that flags the benign ladder walk. It is: **does the SAME logical
# item appear twice under one capture_id?** A pass walking a ladder visits each item
# once; two passes colliding revisit every item they share. So the check is
# `(capture_id, item_identity) -> {captured_at}` and a collision is `len(...) > 1`.
#
# `scripts/tape_gap_monitor.py` itself consumes the flawed key (`aggregate_family`'s
# distinct-pass counter keys on `capture_id`), which is why this lives here: the
# UNDER-CAPTURE ratio undercounts passes by exactly the number of collisions.
#
# Non-gating. These are HISTORICAL properties of already-committed append-only tape; no
# run can retroactively repair them, so gating would halt the loop forever over a fact.

# Fields whose presence means the family declares its OWN within-pass ordering, so several
# `captured_at` under one `capture_id` are BY DESIGN (case (a)) and the family is exempt.
# This is a STRUCTURAL exemption keyed on the schema, never a hard-coded family name-list:
# a new burst collector that stamps `capture_seq` inherits it without an edit here.
WITHIN_PASS_SEQUENCE_FIELDS: Tuple[str, ...] = (
    "capture_seq",
    "capture_mono_ns",
    "round_index",
)

# Candidate fields for a row's logical identity WITHIN one pass, most specific first. The
# item key is the tuple of whichever of these the row actually carries; a row carrying none
# of them has identity "the pass summary itself" (empty key), which is correct — a family
# like `anomalies` writes exactly one summary row per pass, so two summary rows under one
# capture_id ARE two passes.
ITEM_IDENTITY_FIELDS: Tuple[str, ...] = (
    "record_type",
    "ticker",
    "market_ticker",
    "event_ticker",
    "series",
    "series_key",
    "coin",
    "symbol",
    "pair_id",
    "venue",
)

_CAPTURE_ID_RE = re.compile(r'"capture_id"\s*:\s*"([^"]*)"')
_CAPTURED_AT_RE = re.compile(r'"captured_at"\s*:\s*"([^"]*)"')


def _collision_candidate_families(tape_root: Path) -> Dict[str, List[str]]:
    """CHEAP prefilter: family -> capture_ids that carry >1 distinct ``captured_at``.

    A regex skim (no JSON parse) over every committed line. Full ``json.loads`` of all
    ~1.1M committed lines costs ~16s on every gate run; this costs ~5s and returns the
    identical candidate set, with the authoritative parse deferred to the handful of
    families that actually have a candidate.

    Soundness of the shortcut: it UNIONS **every** ``capture_id``/``captured_at`` match on
    the line, including any nested one. A union can only ever ADD distinct values, so this
    can over-nominate a family (harmless — pass 2 re-checks it authoritatively with
    ``json.loads``) but it can NEVER under-nominate one relative to a top-level-only read.
    That asymmetry is what makes it safe to use as a gate on the expensive pass.
    """
    out: Dict[str, List[str]] = {}
    if not tape_root.is_dir():
        return out
    for fam_dir in sorted(p for p in tape_root.iterdir() if p.is_dir()):
        seen: Dict[str, set] = {}
        for _d, path in _family_files(tape_root, fam_dir.name):
            try:
                fh = open(path, "r", encoding="utf-8")
            except OSError:
                continue
            with fh:
                for line in fh:
                    if not line.strip():
                        continue
                    cids = _CAPTURE_ID_RE.findall(line)
                    if not cids:
                        continue
                    cas = _CAPTURED_AT_RE.findall(line)
                    if not cas:
                        continue
                    for cid in cids:
                        seen.setdefault(cid, set()).update(cas)
        cands = sorted(c for c, v in seen.items() if len(v) > 1)
        if cands:
            out[fam_dir.name] = cands
    return out


def duplicate_capture_id_collisions(tape_root: Path,
                                    family: str,
                                    candidate_ids: Optional[List[str]] = None
                                    ) -> Optional[Dict[str, Any]]:
    """Capture_ids under which the SAME logical item was written more than once (L210).

    Returns ``None`` when the family has nothing to judge (no tape, or no candidate
    capture_id) — an honest "no claim", never a fabricated clean bill. Returns a summary
    dict with ``n_collisions == 0`` when candidates existed but every one resolved to a
    benign single-pass ladder walk.

    What it refuses to guess (mirrors ``extract_completeness``'s "no signal, never a
    guess"):

    * a family whose rows carry a ``WITHIN_PASS_SEQUENCE_FIELDS`` member is reported
      ``exempt_reason="declares_within_pass_sequence"`` with ``n_collisions=0`` — its
      multi-``captured_at`` capture is a documented round, not a collision, and calling it
      one would be a false positive;
    * a row with no ``capture_id`` or no ``captured_at`` is skipped, never assigned to a
      neighbouring pass;
    * a malformed line is skipped, never counted as either clean or colliding.

    Per-collision fields: ``capture_id``, ``item_key`` (the identity fields that repeated),
    ``n_distinct_captured_at``, ``captured_at_values``, and ``differing_fields`` — the
    scalar fields that actually DIFFER between the collided rows (``mode`` for perp_tape's
    backfill-vs-recent), which is the evidence that they were two invocations.
    """
    if candidate_ids is None:
        cands = _collision_candidate_families(tape_root).get(family, [])
    else:
        cands = list(candidate_ids)
    if not cands:
        return None
    cand_set = set(cands)

    # (capture_id, item_key) -> {captured_at: [row-scalars]}. Bounded: only rows whose
    # capture_id is one of the (few) candidates are ever retained.
    groups: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, List[Dict[str, Any]]]] = {}
    declares_sequence = False
    n_rows_examined = 0
    for _d, path in _family_files(tape_root, family):
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
                except Exception:
                    continue
                if not isinstance(rec, dict):
                    continue
                cid = rec.get("capture_id")
                cap_at = rec.get("captured_at")
                if not isinstance(cid, str) or cid not in cand_set:
                    continue
                if not isinstance(cap_at, str):
                    continue
                n_rows_examined += 1
                if any(rec.get(f) is not None for f in WITHIN_PASS_SEQUENCE_FIELDS):
                    declares_sequence = True
                item_key = tuple(
                    (f, str(rec[f])) for f in ITEM_IDENTITY_FIELDS
                    if rec.get(f) is not None
                )
                scalars = {
                    k: v for k, v in rec.items()
                    if isinstance(v, (str, int, float, bool)) and k != "captured_at"
                }
                # Retain only the FIRST row's scalars per (item, captured_at): that is all
                # `differing_fields` reads, and it keeps a pathologically large candidate
                # capture (a 100k-row sweep pass) memory-bounded rather than O(rows) (L10).
                slot = groups.setdefault((cid, item_key), {}).setdefault(cap_at, [])
                if not slot:
                    slot.append(scalars)

    if declares_sequence:
        return {
            "family": family,
            "n_candidate_capture_ids": len(cand_set),
            "n_rows_examined": n_rows_examined,
            "n_collisions": 0,
            "collisions": [],
            "exempt_reason": "declares_within_pass_sequence",
        }

    collisions: List[Dict[str, Any]] = []
    for (cid, item_key), by_time in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if len(by_time) < 2:
            continue
        # Which scalar fields actually differ across the collided rows? That difference is
        # the evidence of two distinct invocations rather than one retried write.
        differing: Dict[str, List[Any]] = {}
        per_time_first = [rows[0] for _t, rows in sorted(by_time.items()) if rows]
        all_keys = sorted({k for s in per_time_first for k in s})
        for k in all_keys:
            vals = [s.get(k) for s in per_time_first]
            if len({repr(v) for v in vals}) > 1:
                differing[k] = vals
        collisions.append({
            "capture_id": cid,
            "item_key": list(item_key),
            "n_distinct_captured_at": len(by_time),
            "captured_at_values": sorted(by_time),
            "differing_fields": differing,
        })

    return {
        "family": family,
        "n_candidate_capture_ids": len(cand_set),
        "n_rows_examined": n_rows_examined,
        "n_collisions": len(collisions),
        "collisions": collisions,
        "exempt_reason": None,
    }


# ─── Caller-explicability audit (L222: non-gating, offline-safe, on-demand) ─────
#
# L222: "A tape family whose observed firing pattern contradicts its only in-repo caller
# cannot be root-caused without invocation provenance on the record itself." On
# `tape/econ_prints/dt=2026-07-23.jsonl`, 18 distinct passes land in hour 09 while
# `sports_pairs`/`crypto_hourly`/`orderbook_depth` — legs of the SAME `hourly_pass.run()`
# invocation `econ_prints` is a leg of — recorded ZERO captures in hours 09 or 10 that day.
# Roughly 65% of that family's passes had no identifiable caller.
#
# That row names TWO candidates. Only the SECOND is buildable from a research run:
#
#   (1) every collector record carries a `capture_source` (module path + entrypoint)
#       alongside `capture_id` — a change to a LIVE collector's WRITE PATH, out of scope
#       here, and the only thing that can ever PROVE provenance. Stays UNENFORCED.
#   (2) "a tape-quality check asserts each family's realized pass count is explicable by
#       its registered callers' known firing windows" — READ-ONLY over committed tape.
#       That is what this section is.
#
# The machine-checkable discriminator is CO-OCCURRENCE, not a declared schedule. Every
# registered caller drives SEVERAL families in one invocation, so a genuine pass leaves a
# signature: sibling families written at nearly the same wall-clock instant. A pass with no
# sibling capture anywhere near it was produced by something this repo does not know about.
# Co-occurrence beats hard-coded firing windows because it needs no schedule table to stay
# in sync with `hourly_pass`'s cron, and because it correctly ABSTAINS on the case that
# matters: the 2026-07-14 CPI burst fired `econ_prints` 137 times in a day, which a
# window-based rule would flag as 137 violations — but `burst_capture` co-wrote
# `crypto_hourly` and `polymarket_macro_pairs` throughout, so every one of those passes is
# explicable and this check reports 0 unexplained. On dt=2026-07-23 the same check reports
# 18/18 unexplained, reproducing L222's own finding.
#
# HONEST COVERAGE LIMIT, stated in the report itself: co-occurrence is a PROXY for
# provenance, never proof. `n_unexplained == 0` means "some registered caller's signature is
# present", NOT "the registered caller wrote it" — a rogue invocation that happens to run
# concurrently with a scheduled pass is indistinguishable here. Only candidate (1),
# `capture_source` on the record, closes that gap. This check therefore RAISES the floor
# (it can prove a pass is INEXPLICABLE) without ever certifying a pass as legitimate.
#
# Non-gating and NOT wired into `invariants.py --full`, for the same two reasons as L213's
# slot-cadence tool plus one of its own: (a) these are HISTORICAL properties of already
# committed append-only tape, which no run can retroactively repair, so gating would halt
# the loop over a fact (the L210 posture); (b) there is no standing "family of the day" to
# re-check every routine run; and (c) an all-family scan re-reads every sibling family's
# full tape, which is the runtime budget of the whole gate. On-demand tool, same posture as
# the audit that produced this row.

# Families written by ONE `collection.hourly_pass.run()` invocation with NO hour gate — the
# legs whose presence is the invocation's wall-clock signature. Hour-gated legs
# (`anomalies`/`econ_prints`/`polymarket_cpi_pairs` at 09, `settlement_ledger` at 10,
# forecast at 11, `weather_actuals` at 12, `universe_sweep` at {0,6,12,18}) are deliberately
# EXCLUDED from the signature: they are the families one AUDITS, and a gated leg cannot
# witness another gated leg (both would be absent for the same reason).
HOURLY_PASS_CO_WRITTEN_FAMILIES: Tuple[str, ...] = (
    "sports_pairs",
    "crypto_hourly",
    "orderbook_depth",
    "polymarket_pairs",
    "polymarket_macro_pairs",
    "perp_tape",
    "weather_books",
    "hyperliquid_funding",
)

# Every tape family a `collection.burst_capture` invocation CAN write, keyed by the
# `--families` value that writes it (2026-07-31 polymarket_pairs tape audit: the previous
# hand-maintained 3-family tuple only listed the families a MULTI-family FOMC burst happened
# to co-write (L227), and silently omitted "wc"/"cpi"/"sports" — so `polymarket_pairs` and
# `sports_pairs` were never even REGISTERED as burst_capture-written, and a real
# `kalshi-burst-wcsemi2-0715` capture (14 passes, dt=2026-07-15 20:39-21:05Z) read as having
# NO registered caller at all. Derived from `collection.burst_capture.FAMILY_REGISTRY` keys so
# this can't drift again silently; `test_burst_capture_key_to_tape_family_matches_registry`
# fails loudly if burst_capture adds/removes a family without this map being updated. See
# findings/2026-07-31-polymarket-pairs-tape-audit.md.
BURST_CAPTURE_KEY_TO_TAPE_FAMILY: Dict[str, str] = {
    "wc": "polymarket_pairs",
    "fed": "polymarket_macro_pairs",
    "cpi": "polymarket_cpi_pairs",
    "econ": "econ_prints",
    "crypto": "crypto_hourly",
    "sports": "sports_pairs",
}

BURST_CAPTURE_CO_WRITTEN_FAMILIES: Tuple[str, ...] = tuple(
    BURST_CAPTURE_KEY_TO_TAPE_FAMILY.values()
)

# IMPORTANT LIMIT (2026-07-31, polymarket_pairs tape audit): this registry fix makes
# `burst_capture` a registered caller of every family it can write, but co-occurrence
# explicability is STILL structurally blind to a burst invoked with a SINGLE `--families`
# value (e.g. `--families wc` alone, as `kalshi-burst-wcsemi2-0715` was) — a single-family
# round writes no sibling leg at all, so there is no co-occurrence signature to witness by
# construction, no matter how complete this map is. `caller_explicability()` will correctly
# keep reporting such passes as UNEXPLAINED; that is NOT proof of a rogue process. Before
# reading `n_unexplained > 0` as an incident, check whether the unexplained passes form a
# regular fixed-interval train (a burst signature) rather than assuming co-occurrence is
# exhaustive. Only L222's `capture_source`-on-record candidate (still UNENFORCED) can close
# this gap for good.

REGISTERED_CALLER_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "hourly_pass": HOURLY_PASS_CO_WRITTEN_FAMILIES + (
        # gated legs of the same invocation: registered as WRITTEN BY hourly_pass, but never
        # used as a witness for another family (see `_witness_families`).
        "anomalies", "econ_prints", "polymarket_cpi_pairs", "settlement_ledger",
        "weather_actuals", "universe_sweep",
    ),
    "burst_capture": BURST_CAPTURE_CO_WRITTEN_FAMILIES,
}

# Only these may serve as a co-occurrence WITNESS. A gated leg is never a witness.
_WITNESS_FAMILIES: Dict[str, Tuple[str, ...]] = {
    "hourly_pass": HOURLY_PASS_CO_WRITTEN_FAMILIES,
    "burst_capture": BURST_CAPTURE_CO_WRITTEN_FAMILIES,
}

# Widest observed spread between the FIRST and LAST leg of one real `hourly_pass` invocation
# on healthy committed tape: sports_pairs -> weather_books runs ~380-542s (dt=2026-07-20,
# eight invocations). 900s is that worst case with ~1.7x headroom — deliberately generous,
# because a FALSE "unexplained" is the expensive error here (it would manufacture a
# provenance incident), while a missed one only leaves the status quo.
CO_OCCURRENCE_TOLERANCE_S = 900.0

# `validation/v3_market.py`'s per-pass rate-limit floor. Two pass starts closer together than
# this cannot be the same sequential caller, so they PROVE concurrent invocations (L222
# observed 0.153s on dt=2026-07-14).
PASS_RATE_LIMIT_FLOOR_S = 1.8


def _file_pass_instants(path: Path) -> Dict[str, datetime]:
    """Earliest `captured_at` per distinct pass key in one day-file. Streaming regex scan
    (the L210 fast path) — these files run to 10^6 lines and only two scalars are needed.
    Malformed/absent timestamps are skipped, never guessed. Best-effort: an unreadable file
    yields {}."""
    out: Dict[str, datetime] = {}
    try:
        fh = open(path, "r", encoding="utf-8")
    except OSError:
        return out
    with fh:
        for line in fh:
            m_ca = _CAPTURED_AT_RE.search(line)
            if not m_ca:
                continue
            ts = _parse_iso(m_ca.group(1))
            if ts is None:
                continue
            m_cid = _CAPTURE_ID_RE.search(line)
            key = m_cid.group(1) if (m_cid and m_cid.group(1)) else m_ca.group(1)
            prev = out.get(key)
            if prev is None or ts < prev:
                out[key] = ts
    return out


def pass_instants(tape_root: Path,
                  family: str,
                  days: Optional[Sequence[str]] = None,
                  ) -> List[datetime]:
    """Sorted start instants of every distinct pass a family committed (L222).

    One "pass" is one `capture_id`; its instant is the EARLIEST `captured_at` stamped under
    that id, so a ladder-walking pass (L210 case (a)) counts once, at its start. Rows with no
    `capture_id` fall back to their own `captured_at` as the key.

    ``days`` restricts the scan to explicit ``dt=YYYY-MM-DD`` stems (FROZEN-slice discipline,
    L191); ``None`` scans every committed day-file. A family with no files returns ``[]``.
    """
    wanted = set(days) if days is not None else None
    merged: Dict[str, datetime] = {}
    for _d, path in _family_files(tape_root, family):
        if wanted is not None and path.stem not in wanted:
            continue
        for key, ts in _file_pass_instants(path).items():
            prev = merged.get(key)
            if prev is None or ts < prev:
                merged[key] = ts
    return sorted(merged.values())


def _nearest_gap_s(target: datetime, sorted_others: List[datetime]) -> Optional[float]:
    """Seconds from `target` to the nearest instant in a SORTED list; None when empty. Pure."""
    if not sorted_others:
        return None
    i = bisect_left(sorted_others, target)
    best: Optional[float] = None
    for j in (i - 1, i):
        if 0 <= j < len(sorted_others):
            d = abs((sorted_others[j] - target).total_seconds())
            if best is None or d < best:
                best = d
    return best


def caller_explicability(tape_root: Path,
                         family: str,
                         days: Optional[Sequence[str]] = None,
                         tolerance_s: float = CO_OCCURRENCE_TOLERANCE_S,
                         max_examples: int = 20,
                         ) -> Dict[str, Any]:
    """Is each of a family's realized passes explicable by a REGISTERED caller? (L222)

    For every distinct pass of ``family``, ask whether any registered caller of that family
    co-wrote one of its OTHER (ungated) legs within ``tolerance_s`` — the wall-clock signature
    a real invocation leaves. A pass with no such witness anywhere near it was produced by
    something this repo does not know about, which is exactly the condition L222 could only
    establish by hand.

    Returns ``verdict``:
      * ``FAMILY_NOT_REGISTERED`` — no known caller writes this family; no explicability claim
        is made (an unregistered family is a gap in `REGISTERED_CALLER_FAMILIES`, not evidence).
      * ``NO_PASSES`` — the family committed nothing in scope.
      * ``NO_WITNESS_TAPE`` — registered, but not one witness family has a committed pass in
        scope, so "unexplained" would only be measuring the absence of witness tape.
      * ``ALL_EXPLICABLE`` / ``UNEXPLAINED_PASSES`` — a real reading.

    ``n_unexplained == 0`` is NOT proof of correct provenance: co-occurrence is a proxy, and a
    rogue invocation running concurrently with a scheduled pass is indistinguishable here. Only
    L222's other candidate — `capture_source` on the record — can close that. This function can
    prove a pass INEXPLICABLE; it can never certify one as legitimate. That limit is restated
    in the returned ``coverage_note`` so it travels with any quoted number.

    ``explained_by_caller`` counts per caller and its values OVERLAP — `crypto_hourly` and
    `polymarket_macro_pairs` are witnesses for BOTH registered callers, so one pass can be
    explained by both. The values do NOT sum to ``n_explained``; never add them.

    Also reports ``min_consecutive_pass_gap_s`` and ``concurrent_invocations_proven``: two pass
    starts closer than ``PASS_RATE_LIMIT_FLOOR_S`` cannot come from one sequential caller.

    ARITY BLIND SPOT (2026-07-31, polymarket_pairs audit): `burst_capture` can be invoked with
    a SINGLE `--families` value (e.g. `kalshi-burst-wcsemi2-0715` ran `--families wc` alone). A
    single-family round writes no sibling leg, so it leaves NO co-occurrence signature and reads
    UNEXPLAINED here no matter how complete `BURST_CAPTURE_CO_WRITTEN_FAMILIES` is — this is a
    limit of the co-occurrence METHOD, not a registry gap. Before treating `n_unexplained > 0` as
    an incident, check whether the unexplained passes form a regular fixed-interval train (a
    burst signature, e.g. a constant sub-second `captured_at` offset at the burst's `--interval`)
    rather than assuming co-occurrence is exhaustive.

    Read-only, offline, non-gating.
    """
    callers = sorted(c for c, fams in REGISTERED_CALLER_FAMILIES.items() if family in fams)
    targets = pass_instants(tape_root, family, days=days)
    base: Dict[str, Any] = {
        "family": family,
        "registered_callers": callers,
        "days_scanned": sorted(days) if days is not None else None,
        "tolerance_s": tolerance_s,
        "n_passes": len(targets),
        "n_explained": 0,
        "n_unexplained": 0,
        "unexplained_fraction": None,
        "explained_by_caller": {},
        "witness_families": {},
        "n_witness_passes": 0,
        "nearest_witness_gap_s": {},
        "unexplained_examples": [],
        "per_day_unexplained": {},
        "n_passes_near_slice_edge": 0,
        "min_consecutive_pass_gap_s": None,
        "concurrent_invocations_proven": False,
        "rate_limit_floor_s": PASS_RATE_LIMIT_FLOOR_S,
        "verdict": "FAMILY_NOT_REGISTERED",
        "coverage_note": (
            "Co-occurrence with a registered caller's sibling legs is a PROXY for provenance, "
            "never proof: n_unexplained==0 means a caller's signature is PRESENT, not that the "
            "caller wrote the pass. Only L222's other candidate (a `capture_source` field on "
            "each record) can certify provenance. This check can prove a pass inexplicable; it "
            "cannot certify one as legitimate. ARITY BLIND SPOT: a caller invoked with a SINGLE "
            "family (e.g. a one-family burst_capture round) writes no sibling leg and is "
            "unexplainable by construction — n_unexplained>0 is not automatically an incident; "
            "check for a regular fixed-interval train before treating it as one."
        ),
    }

    gaps = [round((targets[i + 1] - targets[i]).total_seconds(), 3)
            for i in range(len(targets) - 1)]
    if gaps:
        base["min_consecutive_pass_gap_s"] = min(gaps)
        base["concurrent_invocations_proven"] = min(gaps) < PASS_RATE_LIMIT_FLOOR_S

    if not callers:
        return base
    if not targets:
        base["verdict"] = "NO_PASSES"
        return base

    witness: Dict[str, List[datetime]] = {}
    per_caller: Dict[str, List[datetime]] = {}
    for caller in callers:
        fams = [f for f in _WITNESS_FAMILIES.get(caller, ()) if f != family]
        base["witness_families"][caller] = fams
        merged: List[datetime] = []
        for fam in fams:
            if fam not in witness:
                witness[fam] = pass_instants(tape_root, fam, days=days)
            merged.extend(witness[fam])
        per_caller[caller] = sorted(merged)

    base["n_witness_passes"] = sum(len(v) for v in witness.values())
    if base["n_witness_passes"] == 0:
        base["verdict"] = "NO_WITNESS_TAPE"
        return base

    explained_by = {c: 0 for c in callers}
    nearest_all: List[float] = []
    unexplained: List[datetime] = []
    for t in targets:
        hit = False
        best: Optional[float] = None
        for caller in callers:
            g = _nearest_gap_s(t, per_caller[caller])
            if g is None:
                continue
            if best is None or g < best:
                best = g
            if g <= tolerance_s:
                explained_by[caller] += 1
                hit = True
        if best is not None:
            nearest_all.append(round(best, 3))
        if not hit:
            unexplained.append(t)

    per_day: Dict[str, int] = {}
    for t in unexplained:
        stem = "dt=" + t.astimezone(timezone.utc).date().isoformat()
        per_day[stem] = per_day.get(stem, 0) + 1

    # A pass within `tolerance_s` of the edge of a PINNED slice may look unexplained only
    # because its witness lies in an adjacent day-file that was not scanned. Reported, never
    # silently dropped. With `days=None` every committed day is scanned, so no witness can be
    # out of scope and the field is None (there is nothing to caveat) rather than a bare 0.
    scanned_days = sorted({t.astimezone(timezone.utc).date() for t in targets})
    edge: Optional[int] = None if days is None else 0
    if days is not None and scanned_days:
        lo = datetime.combine(scanned_days[0], time(0, 0), tzinfo=timezone.utc)
        hi = datetime.combine(scanned_days[-1], time(0, 0), tzinfo=timezone.utc) + timedelta(days=1)
        edge = sum(1 for t in targets
                   if (t - lo).total_seconds() <= tolerance_s
                   or (hi - t).total_seconds() <= tolerance_s)

    base.update({
        "n_explained": len(targets) - len(unexplained),
        "n_unexplained": len(unexplained),
        "unexplained_fraction": round(len(unexplained) / len(targets), 6),
        "explained_by_caller": explained_by,
        "nearest_witness_gap_s": {
            "min": min(nearest_all) if nearest_all else None,
            "median": sorted(nearest_all)[len(nearest_all) // 2] if nearest_all else None,
            "max": max(nearest_all) if nearest_all else None,
        },
        "unexplained_examples": [t.isoformat() for t in unexplained[:max_examples]],
        "per_day_unexplained": per_day,
        "n_passes_near_slice_edge": edge,
        "verdict": "UNEXPLAINED_PASSES" if unexplained else "ALL_EXPLICABLE",
    })
    return base


# ─── L221: single-hour gate IDEMPOTENCE (the rate-gate half nothing measured) ──────────
#
# `if ts.hour == N:` in `collection/hourly_pass.py` is a RATE gate, not an IDEMPOTENCE gate.
# One line of code produces BOTH failure modes at once: UNBOUNDED passes inside hour N, and
# ZERO passes outside it. The zero-outside half is already covered — L74/L123's
# `daily_family_gap_warning` sees the frozen family, and L144's meta-guard makes sure every
# such leg is registered for it. NOTHING measured the other half, which is what L221 recorded
# and what this answers: how many passes did the gate actually ADMIT inside its hour, and how
# much of the resulting tape is byte-redundant re-capture that carries no new information?
#
# `econ_prints` is L221's own reference case: over dt=2026-07-05..28 its 1,720 committed lines
# collapse to 785 distinct payloads once `capture_id`/`captured_at` are stripped — **54.4%
# byte-redundant re-capture** of a monthly-cadence print (`payrolls` 87.5%, `gdp` 72.1%,
# `cpi_core_mom` 52.0%). See `findings/2026-07-29-econ-prints-tape-audit.md` D2.
#
# TWO measures, deliberately BOTH reported, because each is blind exactly where the other
# sees (the L59 both-measures discipline — frequency and magnitude can disagree in sign of
# implication, so a check that picks one is a check that can be talked out of its own finding):
#   * `max_passes_per_day` — the DIRECT rate-gate measure, and the HEADLINE one. The gate's
#     contract is ONE pass per UTC day, so any day with >1 pass is a pass it had no way to
#     refuse, whichever hour that pass's own `captured_at` fell in. This stays sound on a
#     FAST-MOVING payload, where every re-capture differs and redundancy reads 0.
#     (`max_passes_in_gate_hour` is reported too, but it is the WEAKER of the two — see
#     limit (e): a leg landing ~40min after pass start can carry a `captured_at` in hour N+1
#     while its gate was evaluated on a pass-start `ts` in hour N.)
#   * `redundant_line_fraction` — the COST measure: what share of the family is re-capture of
#     an unchanged payload. This stays sound where a modest pass count looks innocuous but
#     the family's cadence is monthly, so every extra pass is pure duplication.
#
# HONEST LIMITS (restated in every report's own `coverage_note`, so they travel with any
# quoted number):
#   (a) Byte-redundancy is a PROXY for "the gate admitted a pass that added nothing". It
#       cannot prove the GATE caused the duplicate — a deliberate twice-daily sampling of a
#       monthly print would read identically. It proves the tape is redundant, not who made
#       it so; only an on-record `capture_source` field (L222 candidate (1), still UNENFORCED)
#       can attribute a pass.
#   (b) `redundant_line_fraction == 0` is NOT evidence of an idempotent gate — see the
#       fast-moving-payload case above. Read it WITH `max_passes_in_gate_hour`, never alone.
#   (c) Passes are keyed by `capture_id`, so an L210 second-granularity collision merges two
#       real invocations into one apparent pass: `max_passes_in_gate_hour` is a LOWER bound
#       (it errs toward under-reporting over-capture, never toward a false alarm).
#   (d) This is a historical property of already-committed append-only tape. No run can
#       repair the redundant lines; the fix is a once-per-day dedup KEY on the write path
#       (L221's own candidate, a live-collector change out of a research run's lane).
#   (e) The gate is evaluated on the PASS-START `ts`, but tape carries only each LEG's own
#       `captured_at`. `econ_prints` is leg #10 and lands ~40min after pass start (L222
#       measured 380-542s intra-invocation leg spread), so a pass gated in hour N can stamp
#       its records in hour N+1. `max_passes_in_gate_hour` is therefore a LOWER bound and
#       `n_passes_off_gate_hour` an UPPER bound on "the gate leaked" — neither is read as a
#       verdict. `max_passes_per_day` is immune to the drift and carries the verdict instead.
#       Live example: `tape/weather_actuals/dt=2026-07-17` has one pass at 12:29Z (in the
#       hour-12 gate) and one at 13:02Z (out of it) — almost certainly ONE late leg of a pass
#       that started inside hour 12, not a leaked gate.

# Fields that differ between two captures of the SAME payload and therefore must NOT count
# toward a record's information content. `capture_id`/`captured_at` are the pass stamps L221's
# own measurement excluded; the within-pass sequence fields are the same class (a ladder walk's
# step index is not payload) and are reused from the L210 constant so the two cannot desync.
PAYLOAD_VOLATILE_FIELDS: Tuple[str, ...] = (
    ("capture_id", "captured_at") + WITHIN_PASS_SEQUENCE_FIELDS
)


def payload_identity(rec: Dict[str, Any]) -> str:
    """Canonical JSON of one record with `PAYLOAD_VOLATILE_FIELDS` removed (L221).

    Two records sharing an identity carry the SAME information, captured twice. Pure;
    `default=str` so an exotic value can never raise inside a best-effort audit.
    """
    stripped = {k: v for k, v in rec.items() if k not in PAYLOAD_VOLATILE_FIELDS}
    return json.dumps(stripped, sort_keys=True, separators=(",", ":"), default=str)


# A declared burst trigger DELIBERATELY re-fires the same collectors every 60-120s inside its
# window (LOOP-QUEUE.md "Burst-capture legs", Ryan-approved 2026-07-10). Those passes are
# EXPECTED, not gate leakage — counting them as over-capture would manufacture an incident out
# of sanctioned collection. The pad absorbs trigger start/stop jitter; it only ever EXCUSES
# passes, so it biases toward under-reporting over-capture, never toward a false alarm.
BURST_WINDOW_PAD_S: float = 900.0


def _burst_windows_for_family(family: str) -> List[Tuple[datetime, datetime]]:
    """Declared burst windows (padded) during which `family` is deliberately re-captured.
    Reuses BURST_TRIGGER_WINDOWS + BURST_CAPTURE_KEY_TO_TAPE_FAMILY so a rename in either
    cannot silently desync this. Best-effort: an unparseable bound is skipped, never guessed."""
    out: List[Tuple[datetime, datetime]] = []
    pad = timedelta(seconds=BURST_WINDOW_PAD_S)
    for spec in BURST_TRIGGER_WINDOWS.values():
        fams = {BURST_CAPTURE_KEY_TO_TAPE_FAMILY.get(k) for k in spec.get("burst_keys", ())}
        if family not in fams:
            continue
        lo = _parse_iso(spec.get("window_start"))
        hi = _parse_iso(spec.get("window_end"))
        if lo is None or hi is None:
            continue
        out.append((lo - pad, hi + pad))
    return sorted(out)


def single_hour_leg_idempotence(tape_root: Path,
                                family: str,
                                gate_hour_utc: int,
                                days: Optional[Sequence[str]] = None,
                                max_days: Optional[int] = None,
                                max_examples: int = 10,
                                ) -> Optional[Dict[str, Any]]:
    """Did a once-per-UTC-day `ts.hour == N` collector gate behave idempotently? (L221)

    Returns ``None`` — a distinct `no_signal`, never conflated with a clean result — when
    the family has no committed ``dt=*.jsonl`` day-files at all. A family whose files exist
    but yield no parseable line returns a dict with ``verdict == "NO_PARSEABLE_LINES"``.

    ``days`` pins a FROZEN ``dt=YYYY-MM-DD`` slice (L191); ``max_days`` keeps only the N most
    RECENT day-files after that filter (so a routine advisory stays cheap without silently
    changing which days a pinned slice covers). Passing both applies ``days`` first.

    ``gate_hour_utc`` must be 0..23; anything else raises ``ValueError`` rather than
    quietly scanning for an hour that cannot occur.
    """
    if not isinstance(gate_hour_utc, int) or isinstance(gate_hour_utc, bool) \
            or not (0 <= gate_hour_utc <= 23):
        raise ValueError(f"gate_hour_utc must be an int in 0..23, got {gate_hour_utc!r}")

    files = _family_files(tape_root, family)
    if days is not None:
        wanted = set(days)
        files = [(d, p) for d, p in files if p.stem in wanted]
    if max_days is not None and max_days >= 0:
        files = files[-max_days:] if max_days else []
    if not files:
        return None

    n_lines = 0
    n_malformed = 0
    payloads: Set[str] = set()
    per_day: Dict[str, Dict[str, Any]] = {}
    # day stem -> capture_id -> earliest captured_at
    day_passes: Dict[str, Dict[str, datetime]] = {}
    # (day stem, capture_id) -> payload identities written under that one pass. A line with no
    # usable capture_id keys on its own identity, so it forms its own singleton "pass" bucket
    # and can never make intra-pass redundancy look larger than it is.
    pass_payloads: Dict[Tuple[str, str], Set[str]] = {}

    for _d, path in files:
        stem = path.stem
        entry = per_day.setdefault(stem, {"n_lines": 0, "payloads": set()})
        day_passes.setdefault(stem, {})
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
                except Exception:
                    n_malformed += 1
                    continue
                if not isinstance(rec, dict):
                    n_malformed += 1
                    continue
                n_lines += 1
                entry["n_lines"] += 1
                key = payload_identity(rec)
                payloads.add(key)
                entry["payloads"].add(key)
                cid = rec.get("capture_id") or rec.get("captured_at")
                if not isinstance(cid, str) or not cid:
                    cid = ""
                pass_payloads.setdefault((stem, cid or key), set()).add(key)
                ts = _parse_iso(rec.get("captured_at"))
                if ts is None or not cid:
                    continue
                prev = day_passes[stem].get(cid)
                if prev is None or ts < prev:
                    day_passes[stem][cid] = ts

    scanned = sorted(per_day)
    burst_windows = _burst_windows_for_family(family)
    coverage_note = (
        "L221 two-measure report. `redundant_line_fraction` is a PROXY for 'the gate admitted "
        "a pass that added nothing' — it cannot prove the GATE caused the duplicate (only an "
        "on-record capture_source, L222 candidate (1), can attribute a pass), and a value of 0 "
        "is NOT evidence of idempotence on a fast-moving payload. The whole-slice figure is "
        "also a LUMP of three mechanisms with three different culprits, so it can accuse a "
        "clean gate: `redundancy_decomposition` splits it into intra_pass (the collector "
        "duplicated inside ONE invocation), across_pass_within_day (the GATE admitted a "
        "redundant second pass — the only gate-attributable share, surfaced as "
        "`gate_attributable_redundant_line_fraction`), and cross_day (a legitimate "
        "retrospective re-report). The whole-slice figure is kept because it is the number "
        "L221 itself quoted. Read any of them WITH "
        "`max_passes_in_gate_hour`, which is the direct rate-gate measure and stays sound "
        "there. Passes are keyed by capture_id, so an L210 second-granularity collision makes "
        "`max_passes_in_gate_hour` a LOWER bound (errs toward under-reporting, never a false "
        "alarm), and a leg landing ~40min after pass start can stamp `captured_at` in the "
        "hour AFTER the one its gate was evaluated on, so `max_passes_in_gate_hour` is a "
        "LOWER bound and `n_passes_off_gate_hour` an UPPER bound on 'the gate leaked' — the "
        "verdict is carried by `max_passes_per_day`, which is immune to that drift because "
        "the gate's contract is one pass per DAY — and specifically "
        "`max_passes_per_day_excl_burst`, since a DECLARED burst trigger re-fires these "
        "collectors on purpose and those passes are excused (padded window, so the exclusion "
        "only ever under-reports over-capture). Historical property of committed append-only tape: no run can repair these "
        "lines; the fix is a once-per-day dedup KEY on the collector write path."
    )
    base: Dict[str, Any] = {
        "family": family,
        "gate_hour_utc": gate_hour_utc,
        "days_scanned": scanned,
        "n_days": len(scanned),
        "n_lines": n_lines,
        "n_malformed_lines": n_malformed,
        "slice_pinned": days is not None,
        "max_days": max_days,
        "coverage_note": coverage_note,
    }
    if n_lines == 0:
        base["verdict"] = "NO_PARSEABLE_LINES"
        return base

    day_rows: Dict[str, Dict[str, Any]] = {}
    over_capture_days: List[Dict[str, Any]] = []
    zero_gate_hour_days: List[str] = []
    max_in_gate = 0
    max_per_day = 0
    max_per_day_excl_burst = 0
    n_days_multi_pass = 0
    n_days_multi_pass_excl_burst = 0
    n_burst_passes = 0
    for stem in scanned:
        starts = day_passes.get(stem, {})
        in_gate = sorted(t for t in starts.values()
                         if t.astimezone(timezone.utc).hour == gate_hour_utc)
        off_gate = len(starts) - len(in_gate)
        d_lines = per_day[stem]["n_lines"]
        d_distinct = len(per_day[stem]["payloads"])
        non_burst = sorted(t for t in starts.values()
                           if not any(lo <= t <= hi for lo, hi in burst_windows))
        n_burst_passes += len(starts) - len(non_burst)
        row = {
            "n_passes": len(starts),
            "n_passes_excl_burst": len(non_burst),
            "n_passes_in_gate_hour": len(in_gate),
            "n_passes_off_gate_hour": off_gate,
            "n_lines": d_lines,
            "n_distinct_payloads": d_distinct,
            "redundant_line_fraction": (round(1.0 - d_distinct / d_lines, 6)
                                        if d_lines else None),
        }
        day_rows[stem] = row
        max_in_gate = max(max_in_gate, len(in_gate))
        max_per_day = max(max_per_day, len(starts))
        max_per_day_excl_burst = max(max_per_day_excl_burst, len(non_burst))
        if len(non_burst) > 1:
            n_days_multi_pass_excl_burst += 1
        if len(starts) > 1:
            n_days_multi_pass += 1
            all_starts = sorted(starts.values())
            over_capture_days.append({
                "day": stem,
                "n_passes": len(starts),
                "n_passes_excl_burst": len(non_burst),
                "n_passes_in_gate_hour": len(in_gate),
                "first_pass": all_starts[0].isoformat(),
                "last_pass": all_starts[-1].isoformat(),
            })
        if len(in_gate) == 0:
            zero_gate_hour_days.append(stem)

    over_capture_days.sort(key=lambda r: (-r["n_passes"], r["day"]))
    n_distinct = len(payloads)
    # Redundancy DECOMPOSITION (L236 artifact-decomposition discipline). The whole-slice
    # figure L221 quoted lumps three mechanisms with three different culprits; only the
    # middle one is the hour-gate's doing, so a check that reports the lump alone can accuse
    # a clean gate. Nesting is exact: n_lines >= D_pass >= D_day >= D_all, and the three
    # deltas below partition (n_lines - D_all) with no remainder.
    #   * intra-pass  (n_lines - D_pass): the COLLECTOR wrote the same payload twice inside
    #     ONE invocation. Nothing to do with the gate.
    #   * across-pass-within-day (D_pass - D_day): the GATE admitted a second pass the same
    #     day that re-captured an unchanged payload. THIS is L221's rate-gate cost.
    #   * cross-day (D_day - D_all): the same payload re-reported on a later day — legitimate
    #     for a retrospective/monthly-cadence family, and not a gate defect at all.
    n_distinct_within_pass = sum(len(v) for v in pass_payloads.values())
    n_distinct_within_day = sum(len(per_day[s]["payloads"]) for s in scanned)
    base.update({
        "n_distinct_payloads": n_distinct,
        "n_distinct_payloads_within_day": n_distinct_within_day,
        "n_distinct_payloads_within_pass": n_distinct_within_pass,
        "redundant_line_fraction": round(1.0 - n_distinct / n_lines, 6),
        "redundancy_decomposition": {
            "intra_pass": round((n_lines - n_distinct_within_pass) / n_lines, 6),
            "across_pass_within_day": round(
                (n_distinct_within_pass - n_distinct_within_day) / n_lines, 6),
            "cross_day": round((n_distinct_within_day - n_distinct) / n_lines, 6),
        },
        "gate_attributable_redundant_line_fraction": round(
            (n_distinct_within_pass - n_distinct_within_day) / n_lines, 6),
        "max_passes_per_day": max_per_day,
        "max_passes_per_day_excl_burst": max_per_day_excl_burst,
        "max_passes_in_gate_hour": max_in_gate,
        "n_days_over_capture": n_days_multi_pass,
        "n_days_over_capture_excl_burst": n_days_multi_pass_excl_burst,
        "n_burst_expected_passes": n_burst_passes,
        "burst_windows_applied": [[lo.isoformat(), hi.isoformat()] for lo, hi in burst_windows],
        "n_days_zero_gate_hour_pass": len(zero_gate_hour_days),
        "zero_gate_hour_days": zero_gate_hour_days[:max_examples],
        "over_capture_examples": over_capture_days[:max_examples],
        "per_day": day_rows,
        "verdict": ("OVER_CAPTURE" if max_per_day_excl_burst > 1
                    else "ONE_PASS_PER_DAY"),
    })
    return base


# Declared burst-trigger windows (LOOP-QUEUE.md "Burst-capture legs" table, 2026-07-10
# Ryan-approved). Hand-transcribed from that table, not the live trigger API — an offline
# check may not reach the network, and the table IS the record of what was PROMISED, which
# is exactly what L227's audit needs to compare the tape against. `burst_keys` reuses
# `BURST_CAPTURE_KEY_TO_TAPE_FAMILY` so a family rename there can't silently desync this map.
BURST_TRIGGER_WINDOWS: Dict[str, Dict[str, Any]] = {
    "kalshi-burst-cpi-0714": {
        "window_start": "2026-07-14T12:05:00+00:00",
        "window_end": "2026-07-14T13:45:00+00:00",
        "expected_interval_s": 60.0,
        "burst_keys": ("econ", "cpi", "fed", "crypto"),
    },
    "kalshi-burst-wcsemi1-0714": {
        "window_start": "2026-07-14T20:10:00+00:00",
        "window_end": "2026-07-14T22:30:00+00:00",
        "expected_interval_s": 120.0,
        "burst_keys": ("wc",),
    },
    "kalshi-burst-wcsemi2-0715": {
        "window_start": "2026-07-15T20:10:00+00:00",
        "window_end": "2026-07-15T22:30:00+00:00",
        "expected_interval_s": 120.0,
        "burst_keys": ("wc",),
    },
    "kalshi-burst-wcfinal-0719": {
        "window_start": "2026-07-19T20:10:00+00:00",
        "window_end": "2026-07-19T22:45:00+00:00",
        "expected_interval_s": 120.0,
        "burst_keys": ("wc",),
    },
    "kalshi-burst-fomc-0729": {
        "window_start": "2026-07-29T17:40:00+00:00",
        "window_end": "2026-07-29T19:45:00+00:00",
        "expected_interval_s": 90.0,
        "burst_keys": ("fed", "econ", "crypto"),
    },
}


def burst_window_liveness(tape_root: Path,
                          family: str,
                          window_start: datetime,
                          window_end: datetime,
                          expected_interval_s: float,
                          gap_multiplier: float = 3.0,
                          ) -> Dict[str, Any]:
    """L227's PREVENTION half: did `family`'s capture cadence stay LIVE across a burst
    trigger's DECLARED window, or did it go dark during the one event the burst leg exists
    to catch? A `0 burst windows cover the release` verdict from a downstream probe (L227's
    own originating case, `q48_s55_fomc_lag_probe.py`) doesn't distinguish sparse tape from a
    real capture outage — this answers that question directly, from the tape alone, any time
    after the fact (no live process/container log needed).

    Compares actual `pass_instants()` against `expected_interval_s` inside
    `[window_start, window_end]`. Any gap exceeding `gap_multiplier * expected_interval_s`
    (default 3x — generous vs the ~1.1-1.8x jitter seen on healthy real burst tape, so normal
    scheduling noise never false-alarms) is a silence episode, reported with its own
    start/end/duration so a human can see exactly what was missed, not just a bare flag. LEAD-IN
    (`window_start` to the first pass) and TRAIL (the last pass to `window_end`) are checked the
    same way as interior gaps — a burst that never started, or stopped early, is exactly as much
    an outage as a mid-window gap, and a naive "gap between passes" scan would miss both.

    Read-only, offline, non-gating: this reports an outage, it does not repair one — by the
    time it runs, the burst window has already closed. `verdict`: `NO_PASSES_IN_WINDOW` (the
    family committed nothing at all in scope — the total-loss case), `LIVE` (no gap exceeded
    the threshold), `OUTAGE_DETECTED` (one or more episodes did).
    """
    days = sorted({window_start.date().isoformat(), window_end.date().isoformat()})
    day_stems = [f"dt={d}" for d in days]
    in_day = pass_instants(tape_root, family, days=day_stems)
    window = [t for t in in_day if window_start <= t <= window_end]

    threshold_s = gap_multiplier * expected_interval_s
    base: Dict[str, Any] = {
        "family": family,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "expected_interval_s": expected_interval_s,
        "gap_multiplier": gap_multiplier,
        "threshold_s": threshold_s,
        "n_passes_in_window": len(window),
        "first_pass": None,
        "last_pass": None,
        "gaps": [],
        "max_gap_s": None,
        "verdict": "NO_PASSES_IN_WINDOW",
    }
    if not window:
        return base
    base["first_pass"] = window[0].isoformat()
    base["last_pass"] = window[-1].isoformat()

    episodes: List[Dict[str, Any]] = []
    lead_in = (window[0] - window_start).total_seconds()
    if lead_in > threshold_s:
        episodes.append({"start": window_start.isoformat(), "end": window[0].isoformat(),
                          "duration_s": round(lead_in, 3), "kind": "lead_in"})
    for i in range(len(window) - 1):
        gap = (window[i + 1] - window[i]).total_seconds()
        if gap > threshold_s:
            episodes.append({"start": window[i].isoformat(), "end": window[i + 1].isoformat(),
                              "duration_s": round(gap, 3), "kind": "interior"})
    trail = (window_end - window[-1]).total_seconds()
    if trail > threshold_s:
        episodes.append({"start": window[-1].isoformat(), "end": window_end.isoformat(),
                          "duration_s": round(trail, 3), "kind": "trail"})

    base["gaps"] = episodes
    base["max_gap_s"] = max((e["duration_s"] for e in episodes), default=None)
    base["verdict"] = "OUTAGE_DETECTED" if episodes else "LIVE"
    return base


def burst_trigger_liveness(tape_root: Path,
                           trigger_name: str,
                           gap_multiplier: float = 3.0,
                           ) -> Dict[str, Any]:
    """Runs `burst_window_liveness` for every tape family a named burst trigger drives, per
    `BURST_TRIGGER_WINDOWS` (LOOP-QUEUE.md's own declared table — see that dict's docstring
    note on provenance). An unknown trigger name returns an honest `UNKNOWN_TRIGGER` verdict
    rather than guessing a window. `families` de-duplicates by tape family (some burst keys,
    e.g. a multi-family FOMC round, can map distinct keys to distinct families; two keys never
    collide onto the same family within one trigger in the table as written, but the dedup
    guards against it if one ever does)."""
    cfg = BURST_TRIGGER_WINDOWS.get(trigger_name)
    if cfg is None:
        return {"trigger": trigger_name, "verdict": "UNKNOWN_TRIGGER", "families": {}}
    window_start = _parse_iso(cfg["window_start"])
    window_end = _parse_iso(cfg["window_end"])
    families: Dict[str, Any] = {}
    any_outage = False
    any_total_loss = False
    for key in cfg["burst_keys"]:
        fam = BURST_CAPTURE_KEY_TO_TAPE_FAMILY[key]
        if fam in families:
            continue
        result = burst_window_liveness(tape_root, fam, window_start, window_end,
                                       cfg["expected_interval_s"], gap_multiplier=gap_multiplier)
        families[fam] = result
        if result["verdict"] == "OUTAGE_DETECTED":
            any_outage = True
        elif result["verdict"] == "NO_PASSES_IN_WINDOW":
            any_total_loss = True
    verdict = "OUTAGE_DETECTED" if (any_outage or any_total_loss) else "LIVE"
    return {
        "trigger": trigger_name,
        "window_start": cfg["window_start"],
        "window_end": cfg["window_end"],
        "verdict": verdict,
        "families": families,
    }


# ---------------------------------------------------------------------------
# L223 — per-key STATUS-REGRESSION detector ("never had it" vs "lost it")
# ---------------------------------------------------------------------------
#
# The failure this exists to catch: a collector leg whose honest-status
# vocabulary has only TWO states — a real value, and one null-shaped string
# ("no_settled_events" / "not_built") that is counted as a NON-error and so
# leaves ``pass_complete: true`` intact. Under that vocabulary a regression is
# byte-indistinguishable from "this series never had one": ``econ_prints``'s
# ``gdp`` leg reported one real settlement and then ``no_settled_events`` on
# every subsequent pass for 24 days while every persisted field read healthy.
#
# L223's own words: the vocabulary needs a THIRD state, not two — never-had-this
# vs used-to-have-it-and-lost-it vs currently-has-it — and the discriminator (the
# same key's PRIOR tape) is already sitting in committed history, so detecting
# the second state needs no new collection, only a check that reads backward.
# That is exactly what this does, read-only, over committed tape.
#
# Three design points that are load-bearing, each learned from the real tape:
#
# 1. **Neutral (transport) statuses must not split an episode.** ``fetch_error``
#    is evidence of neither "has it" nor "lost it" — it is the absence of an
#    observation. gdp's two 2026-07-29 ``fetch_error`` rows sit INSIDE its single
#    null run; scoring them as real values shatters one 364-pass episode into
#    three short ones and destroys the very signal the check exists to raise.
# 2. **A recovery must not erase the history.** A key that lost its value and
#    later regained it classifies ``has_it`` (its CURRENT state is honest) but
#    still publishes the closed episode. Otherwise the check goes blind the
#    moment the pipe recovers, and a 24-day hole becomes retroactively invisible
#    — the same "silence reads as healthy" failure one level up.
# 3. **A LEADING null run is not a regression.** Null passes before a key's first
#    real value are the ``never_had`` state by definition; counting them as an
#    episode would fire on every legitimately-not-yet-settled series.
#
# State is the three-way partition (always computed); the RUN-LENGTH threshold
# only decides whether a ``lost_it`` key ALERTS. Read-only, no network, and a
# subcommand-only report — it changes no existing detector, table or exit code.

STATUS_REGRESSION_MIN_RUN_PASSES = 3

# family -> how to read (key, status) off one line, and which status strings are
# null-shaped vs neutral. A family absent from here is NOT audited: this check
# refuses to guess which of a family's strings mean "nothing to report", because
# guessing wrong turns it into a false-positive generator (extract_completeness's
# "no signal, never a fabricated value" discipline, applied to statuses).
STATUS_KEYED_FAMILIES: Dict[str, Dict[str, Any]] = {
    "econ_prints": {
        "key_path": ("series_key",),
        "status_path": ("recent_settlement", "status"),
        "null_statuses": ("no_settled_events", "not_built"),
        "neutral_statuses": ("fetch_error",),
        "min_run_passes": STATUS_REGRESSION_MIN_RUN_PASSES,
        "note": ("L223: recent_settlement.status collapses never-had-a-settlement and "
                 "lost-the-settlement into one non-error string while pass_complete "
                 "stays true; collection/econ_prints.py counts it as complete."),
    },
}

_MISSING = object()


def _dig_path(rec: Any, path: Tuple[str, ...]) -> Any:
    """Follow a dotted path; return ``_MISSING`` if any hop is absent.

    ``_MISSING`` (key not present at all) is deliberately distinct from a present
    ``None``: the first is "this family does not carry this field on this line"
    (no signal — skipped and counted), the second is an explicit null status
    (null-shaped — a real observation of nothing). Collapsing them would let a
    schema change read as a 100% regression.
    """
    cur = rec
    for hop in path:
        if not isinstance(cur, dict) or hop not in cur:
            return _MISSING
        cur = cur[hop]
    return cur


def classify_status(value: Any,
                    null_statuses: Iterable[str],
                    neutral_statuses: Iterable[str]) -> Optional[str]:
    """``'real'`` | ``'null'`` | ``'neutral'`` | ``None`` (no signal).

    ``None``/``""`` present in the record is NULL-shaped (an observed nothing).
    A non-string, non-None value is ``'real'`` only if it is a scalar the venue
    could have meant as a value; a dict/list is treated as real (a populated
    payload). ``_MISSING`` is handled by the caller, never here.
    """
    if value is None:
        return "null"
    if isinstance(value, str):
        if value in tuple(neutral_statuses):
            return "neutral"
        if value == "" or value in tuple(null_statuses):
            return "null"
        return "real"
    if isinstance(value, bool):
        return "real"
    return "real"


def _episode_span_days(start: Optional[str], end: Optional[str]) -> Optional[float]:
    a, b = _parse_iso(start), _parse_iso(end)
    if a is None or b is None:
        return None
    return round((b - a).total_seconds() / 86400.0, 4)


def status_regression_by_key(tape_root: Path,
                             family: str,
                             days: Optional[List[str]] = None,
                             min_run_passes: Optional[int] = None,
                             config: Optional[Dict[str, Any]] = None
                             ) -> Dict[str, Any]:
    """Per-key three-state status audit for FAMILY (L223). Read-only.

    Raises ``ValueError`` for a family with no ``STATUS_KEYED_FAMILIES`` entry and
    no injected ``config`` — an unaudited family is reported as such by the caller,
    never silently scored clean.

    Per key: ``state`` in {``never_had``, ``lost_it``, ``has_it``} (an exact
    partition, asserted by ``partition_ok``), the CURRENT trailing null run, and
    every CLOSED regression episode (null run bounded by a real value on both
    sides) with its length in passes and span in days.

    ``alerting_keys`` = ``lost_it`` keys whose current run reaches
    ``min_run_passes``. Closed episodes never alert — they are the diagnostic that
    keeps a recovered hole visible.
    """
    cfg = dict(config) if config is not None else dict(STATUS_KEYED_FAMILIES.get(family, {}))
    if not cfg:
        raise ValueError(
            f"family {family!r} has no STATUS_KEYED_FAMILIES entry; add one (key_path, "
            "status_path, null_statuses, neutral_statuses) rather than guessing which "
            "of its status strings mean 'nothing to report'"
        )
    key_path = tuple(cfg["key_path"])
    status_path = tuple(cfg["status_path"])
    nulls = tuple(cfg.get("null_statuses", ()))
    neutrals = tuple(cfg.get("neutral_statuses", ()))
    threshold = int(min_run_passes if min_run_passes is not None
                    else cfg.get("min_run_passes", STATUS_REGRESSION_MIN_RUN_PASSES))

    day_filter = set(days) if days else None
    # key -> [(captured_at, kind, raw_status)] with neutral rows retained for
    # counting but DROPPED from the run scan (design point 1).
    per_key: Dict[str, List[Tuple[str, str, Any]]] = {}
    n_rows = 0
    n_no_signal = 0
    n_no_key = 0
    n_malformed = 0
    files_read: List[str] = []

    for _d, path in _family_files(tape_root, family):
        if day_filter is not None and path.stem not in day_filter:
            continue
        files_read.append(path.name)
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
                except Exception:
                    n_malformed += 1
                    continue
                if not isinstance(rec, dict):
                    n_malformed += 1
                    continue
                n_rows += 1
                key = _dig_path(rec, key_path)
                if key is _MISSING or key is None or not isinstance(key, (str, int)):
                    n_no_key += 1
                    continue
                raw = _dig_path(rec, status_path)
                if raw is _MISSING:
                    n_no_signal += 1
                    continue
                cap_at = rec.get("captured_at")
                if not isinstance(cap_at, str):
                    n_no_signal += 1
                    continue
                kind = classify_status(raw, nulls, neutrals)
                if kind is None:
                    n_no_signal += 1
                    continue
                per_key.setdefault(str(key), []).append((cap_at, kind, raw))

    keys_out: Dict[str, Any] = {}
    counts = {"never_had": 0, "has_it": 0, "lost_it": 0}
    alerting: List[str] = []

    for key, rows in per_key.items():
        rows.sort(key=lambda r: r[0])
        n_neutral = sum(1 for r in rows if r[1] == "neutral")
        seq = [r for r in rows if r[1] != "neutral"]      # design point 1
        n_real = sum(1 for r in seq if r[1] == "real")
        n_null = sum(1 for r in seq if r[1] == "null")

        episodes: List[Dict[str, Any]] = []
        leading_null = 0
        current_run: List[Tuple[str, str, Any]] = []
        prev_real: Optional[Tuple[str, str, Any]] = None
        i = 0
        while i < len(seq):
            if seq[i][1] == "null":
                j = i
                while j < len(seq) and seq[j][1] == "null":
                    j += 1
                run = seq[i:j]
                if prev_real is None:
                    leading_null += len(run)          # design point 3
                elif j < len(seq):
                    episodes.append({                 # design point 2
                        "last_real_before_captured_at": prev_real[0],
                        "last_real_before_status": prev_real[2],
                        "start_captured_at": run[0][0],
                        "end_captured_at": run[-1][0],
                        "n_passes": len(run),
                        "span_days": _episode_span_days(run[0][0], run[-1][0]),
                        "recovered_at": seq[j][0],
                        "recovered_status": seq[j][2],
                    })
                else:
                    current_run = run
                i = j
            else:
                prev_real = seq[i]
                i += 1

        if n_real == 0:
            state = "never_had"
        elif current_run:
            state = "lost_it"
        else:
            state = "has_it"
        counts[state] += 1

        run_passes = len(current_run)
        alerts = state == "lost_it" and run_passes >= threshold
        if alerts:
            alerting.append(key)

        keys_out[key] = {
            "state": state,
            "alerts": alerts,
            "n_passes": len(rows),
            "n_real": n_real,
            "n_null": n_null,
            "n_neutral": n_neutral,
            "first_captured_at": rows[0][0],
            "last_captured_at": rows[-1][0],
            "last_real_captured_at": prev_real[0] if prev_real else None,
            "last_real_status": prev_real[2] if prev_real else None,
            "current_null_run_passes": run_passes,
            "current_null_run_started_at": current_run[0][0] if current_run else None,
            "current_null_run_span_days": (
                _episode_span_days(current_run[0][0], current_run[-1][0]) if current_run else None
            ),
            "leading_null_passes": leading_null,
            "n_closed_episodes": len(episodes),
            "longest_closed_episode_passes": max((e["n_passes"] for e in episodes), default=0),
            "closed_episodes": episodes,
        }

    n_keys = len(keys_out)
    partition_ok = (counts["never_had"] + counts["has_it"] + counts["lost_it"]) == n_keys
    return {
        "family": family,
        "key_path": ".".join(key_path),
        "status_path": ".".join(status_path),
        "null_statuses": list(nulls),
        "neutral_statuses": list(neutrals),
        "min_run_passes": threshold,
        "note": cfg.get("note"),
        "days_filter": sorted(day_filter) if day_filter else None,
        "n_files_read": len(files_read),
        "n_rows": n_rows,
        "n_no_signal": n_no_signal,
        "n_rows_without_key": n_no_key,
        "n_malformed_lines": n_malformed,
        "n_keys": n_keys,
        "n_never_had": counts["never_had"],
        "n_has_it": counts["has_it"],
        "n_lost_it": counts["lost_it"],
        "partition_ok": partition_ok,
        "n_keys_with_closed_episodes": sum(1 for v in keys_out.values() if v["n_closed_episodes"]),
        "alerting_keys": sorted(alerting),
        "verdict": ("REGRESSION_OPEN" if alerting
                    else "RECOVERED_EPISODES_ON_RECORD"
                    if any(v["n_closed_episodes"] for v in keys_out.values())
                    else "CLEAN" if n_keys else "NO_KEYS"),
        "keys": keys_out,
    }


def field_health_by_day(tape_root: Path,
                        family: str,
                        days: Optional[List[str]] = None,
                        config: Optional[Dict[str, Any]] = None,
                        max_consecutive_bad_days: Optional[int] = None
                        ) -> Dict[str, Any]:
    """Per-day health of one join-critical SUB-FIELD for FAMILY (L307). Read-only.

    Raises ``ValueError`` for a family with no ``FIELD_HEALTH_FAMILIES`` entry and no
    injected ``config`` — an unaudited family is reported as such by the caller, never
    silently scored clean.

    Each committed day-file gets exactly one of three classes:
    ``field_absent`` (every record that day lacks the field entirely — a schema the
    day never carried, e.g. before the field existed), ``healthy`` (>=1 record that day
    satisfies ``healthy_predicate``), or ``degraded`` (>=1 record carries the field, but
    none satisfy the predicate). ``field_absent`` days are excluded from the
    consecutive-day run scan entirely — same treatment as a ``neutral`` status in
    ``status_regression_by_key`` (design point 1): they carry no signal either way, so
    they neither extend nor break a run.

    ``current_bad_day_run`` is the trailing run of ``degraded`` days (most recent day
    backward, skipping over any ``field_absent`` days in between). ``degraded`` (bool)
    is True once that run reaches ``max_consecutive_bad_days``. Closed episodes (a
    degraded run bounded by a healthy day on both sides) are kept on the record even
    after recovery — L223's "a recovered hole must stay visible" rule, one level up.
    """
    cfg = dict(config) if config is not None else dict(FIELD_HEALTH_FAMILIES.get(family, {}))
    if not cfg:
        raise ValueError(
            f"family {family!r} has no FIELD_HEALTH_FAMILIES entry; add one (json_path, "
            "healthy_predicate, max_consecutive_bad_days) rather than guessing whether "
            "a sub-field's silence is benign"
        )
    json_path = tuple(cfg["json_path"])
    healthy_predicate = cfg["healthy_predicate"]
    threshold = int(max_consecutive_bad_days if max_consecutive_bad_days is not None
                    else cfg.get("max_consecutive_bad_days", FIELD_HEALTH_DEFAULT_MAX_BAD_DAYS))

    day_filter = set(days) if days else None
    by_day: Dict[str, Dict[str, Any]] = {}
    n_rows = 0
    n_malformed = 0
    files_read: List[str] = []

    for _d, path in _family_files(tape_root, family):
        if day_filter is not None and path.stem not in day_filter:
            continue
        files_read.append(path.name)
        day_key = path.stem  # "dt=YYYY-MM-DD"
        counts = by_day.setdefault(day_key, {"n_rows": 0, "n_absent": 0,
                                             "n_present": 0, "n_healthy": 0})
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
                except Exception:
                    n_malformed += 1
                    continue
                if not isinstance(rec, dict):
                    n_malformed += 1
                    continue
                n_rows += 1
                counts["n_rows"] += 1
                value = _dig_path(rec, json_path)
                if value is _MISSING:
                    counts["n_absent"] += 1
                    continue
                counts["n_present"] += 1
                if healthy_predicate(value):
                    counts["n_healthy"] += 1

    for day_key, counts in by_day.items():
        if counts["n_present"] == 0:
            day_class = "field_absent"
        elif counts["n_healthy"] > 0:
            day_class = "healthy"
        else:
            day_class = "degraded"
        counts["day_class"] = day_class

    ordered_days = sorted(by_day.keys())
    # design point 1 (mirrors status_regression_by_key): field_absent days carry no
    # signal and are excluded from the run-scanning sequence entirely.
    seq = [d for d in ordered_days if by_day[d]["day_class"] != "field_absent"]

    episodes: List[Dict[str, Any]] = []
    leading_bad = 0
    current_run: List[str] = []
    prev_healthy: Optional[str] = None
    i = 0
    while i < len(seq):
        if by_day[seq[i]]["day_class"] == "degraded":
            j = i
            while j < len(seq) and by_day[seq[j]]["day_class"] == "degraded":
                j += 1
            run = seq[i:j]
            if prev_healthy is None:
                leading_bad += len(run)
            elif j < len(seq):
                episodes.append({
                    "last_healthy_before_day": prev_healthy,
                    "start_day": run[0],
                    "end_day": run[-1],
                    "n_days": len(run),
                    "recovered_day": seq[j],
                })
            else:
                current_run = run
            i = j
        else:
            prev_healthy = seq[i]
            i += 1

    run_days = len(current_run)
    degraded = run_days >= threshold
    n_days = len(by_day)
    n_field_absent = sum(1 for v in by_day.values() if v["day_class"] == "field_absent")
    n_healthy_days = sum(1 for v in by_day.values() if v["day_class"] == "healthy")
    n_degraded_days = sum(1 for v in by_day.values() if v["day_class"] == "degraded")

    if degraded:
        verdict = "FIELD_DEGRADED"
    elif episodes:
        verdict = "RECOVERED_EPISODES_ON_RECORD"
    elif n_days:
        verdict = "CLEAN"
    else:
        verdict = "NO_DAYS"

    return {
        "family": family,
        "json_path": ".".join(json_path),
        "max_consecutive_bad_days": threshold,
        "note": cfg.get("note"),
        "days_filter": sorted(day_filter) if day_filter else None,
        "n_files_read": len(files_read),
        "n_rows": n_rows,
        "n_malformed_lines": n_malformed,
        "n_days": n_days,
        "n_field_absent_days": n_field_absent,
        "n_healthy_days": n_healthy_days,
        "n_degraded_days": n_degraded_days,
        "current_bad_day_run": run_days,
        "current_bad_day_run_started": current_run[0] if current_run else None,
        "leading_bad_days": leading_bad,
        "degraded": degraded,
        "n_closed_episodes": len(episodes),
        "closed_episodes": episodes,
        "verdict": verdict,
        "by_day": by_day,
    }


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
                    window_hours: float = DEFAULT_WINDOW_HOURS,
                    tape_root: Optional[Path] = None) -> Dict[str, Any]:
    """Turn an aggregate into the machine-readable per-family health record.

    ``tape_root``, when given and the family is registered in
    ``RETROSPECTIVE_LIST_FAMILIES``, attaches the L171 ``retrospective_coverage``
    reading to the record (informational — file presence stays unused as a
    coverage signal for this family class; the STALE/UNDER-CAPTURE alert path
    above is untouched). ``tape_root=None`` (e.g. a caller building a record
    straight from an aggregate) simply omits it — never fabricated.
    """
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

    # FIELD-HEALTH detector (L307). Structurally independent of every check above: a
    # family can be perfectly on-cadence (STALE/UNDER-CAPTURE both silent) while a
    # join-critical SUB-FIELD inside its records is dead, since none of those detectors
    # ever look inside a record. Only runs when `tape_root` is given (this function is
    # also called with tape_root=None from tests/callers building a record straight off
    # an aggregate — never fabricated in that path) and the family is registered.
    field_health = None
    if tape_root is not None and agg.family in FIELD_HEALTH_FAMILIES:
        field_health = field_health_by_day(tape_root, agg.family)
        if field_health["degraded"]:
            reasons.append(
                f"field_degraded: {field_health['json_path']} unhealthy for "
                f"{field_health['current_bad_day_run']} consecutive day(s) "
                f"(>= {field_health['max_consecutive_bad_days']} threshold), "
                f"since {field_health['current_bad_day_run_started']}"
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

    retro_coverage = None
    if tape_root is not None and agg.family in RETROSPECTIVE_LIST_FAMILIES:
        retro_coverage = retrospective_coverage(tape_root, agg.family)

    # L185: per-capture event-time span vs firing cadence. INFORMATIONAL only —
    # deliberately computed after `reasons` is closed and never appended to it, so it
    # cannot touch `alert`/`alert_reason`. A cap/window mismatch is a collector DESIGN
    # property, not a pipe outage; paging on it would fire every single day forever.
    capped_span = None
    if tape_root is not None and agg.family in CAPPED_PAGINATION_FAMILIES:
        capped_span = capped_pagination_span_coverage(tape_root, agg.family)

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
        "retrospective_coverage": retro_coverage,
        "capped_pagination_span": capped_span,
        "field_health": field_health,
    }


def build_report(tape_root: Path, now: datetime,
                 window_hours: float = DEFAULT_WINDOW_HOURS,
                 families: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
    """The machine-readable blob: family -> health record."""
    fam_list = families if families is not None else list(FAMILY_CONFIG.keys())
    report: Dict[str, Dict[str, Any]] = {}
    for fam in fam_list:
        agg = aggregate_family(tape_root, fam, now, window_hours)
        report[fam] = evaluate_family(agg, now, window_hours, tape_root=tape_root)
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
    ap.add_argument("--window-grid", action="store_true",
                    help="print ONLY the L208 expected-window-grid coverage report for every "
                         "family in WINDOW_GRIDDED_FAMILIES (read-only, no notify) and exit.")
    ap.add_argument("--window-grid-days", default=None,
                    help="comma-separated dt= day stems to restrict --window-grid to "
                         "(e.g. dt=2026-07-17,dt=2026-07-18). Pins a FROZEN slice, per L191.")
    ap.add_argument("--slot-cadence", default=None, metavar="FAMILY",
                    help="print ONLY the L213 wall-clock-slot cadence report for FAMILY over "
                         "--slot-window (read-only, no notify) and exit. Answers 'how many "
                         "passes land inside this specific UTC time-of-day slot, per day' — "
                         "the check a burst-trigger fallback plan needs, distinct from the "
                         "family's per-day average.")
    ap.add_argument("--slot-window", nargs=2, metavar=("START", "END"), default=None,
                    help="HH:MM HH:MM UTC window bounds for --slot-cadence (required with it).")
    ap.add_argument("--slot-cadence-days", default=None,
                    help="comma-separated dt= day stems to restrict --slot-cadence to "
                         "(e.g. dt=2026-07-18,dt=2026-07-19). Pins a FROZEN slice, per L191. "
                         "Default: every committed day-file the family has.")
    ap.add_argument("--caller-explicability", default=None, metavar="FAMILY",
                    help="print ONLY the L222 caller-explicability audit for FAMILY "
                         "(read-only, no notify) and exit. Answers 'is each realized pass "
                         "explicable by a registered caller', via co-occurrence with that "
                         "caller's other legs — the question a family with no `capture_source` "
                         "field on its records cannot answer about itself.")
    ap.add_argument("--explicability-days", default=None,
                    help="comma-separated dt= day stems to restrict --caller-explicability to "
                         "(e.g. dt=2026-07-23). Pins a FROZEN slice, per L191. Default: every "
                         "committed day-file the family has.")
    ap.add_argument("--explicability-tolerance-s", type=float, default=CO_OCCURRENCE_TOLERANCE_S,
                    help=f"co-occurrence window in seconds (default {CO_OCCURRENCE_TOLERANCE_S}, "
                         "the widest observed real hourly_pass leg spread plus headroom).")
    ap.add_argument("--leg-idempotence", default=None, metavar="FAMILY",
                    help="print ONLY the L221 single-hour-gate idempotence report for FAMILY "
                         "(read-only, no notify) and exit. Requires --leg-gate-hour. Answers "
                         "'how many passes did the `ts.hour == N` gate ADMIT inside its hour, "
                         "and how much of the tape is byte-redundant re-capture' — the "
                         "rate-gate half that L74/L123's frozen-family check cannot see.")
    ap.add_argument("--leg-gate-hour", type=int, default=None, metavar="N",
                    help="the UTC hour (0-23) the leg is gated on (required with "
                         "--leg-idempotence); read it off collection/hourly_pass.py's "
                         "<NAME>_UTC_HOUR constant, never guessed.")
    ap.add_argument("--leg-idempotence-days", default=None,
                    help="comma-separated dt= day stems to restrict --leg-idempotence to "
                         "(e.g. dt=2026-07-23). Pins a FROZEN slice, per L191. Default: every "
                         "committed day-file the family has.")
    ap.add_argument("--leg-idempotence-max-days", type=int, default=None,
                    help="keep only the N most RECENT day-files after --leg-idempotence-days "
                         "filtering (default: all).")
    ap.add_argument("--status-regression", default=None, metavar="FAMILY",
                    help="print ONLY the L223 per-key status-regression audit for FAMILY "
                         "(one of STATUS_KEYED_FAMILIES, e.g. econ_prints; read-only, no "
                         "notify) and exit. Answers 'did any key that USED to report a real "
                         "status quietly fall back to a null-shaped one' — the third state a "
                         "two-state honest-status vocabulary cannot express.")
    ap.add_argument("--status-regression-days", default=None,
                    help="comma-separated dt= day stems to restrict --status-regression to "
                         "(e.g. dt=2026-07-05,dt=2026-07-06). Pins a FROZEN slice, per L191. "
                         "Default: every committed day-file the family has.")
    ap.add_argument("--status-regression-min-run", type=int, default=None, metavar="N",
                    help="a `lost_it` key ALERTS only once its CURRENT null run reaches N "
                         f"passes (default: the family's own min_run_passes, "
                         f"else {STATUS_REGRESSION_MIN_RUN_PASSES}). The three-state "
                         "classification itself is threshold-independent.")
    ap.add_argument("--field-health", default=None, metavar="FAMILY",
                    help="print ONLY the L307 join-critical sub-field health audit for "
                         "FAMILY (one of FIELD_HEALTH_FAMILIES, e.g. sports_pairs; "
                         "read-only, no notify) and exit. Answers 'is the sub-field this "
                         "family's live join actually depends on still producing healthy "
                         "values', per DAY — the check no STALE/UNDER-CAPTURE/cadence "
                         "detector can see, since none of them look inside a record.")
    ap.add_argument("--field-health-days", default=None,
                    help="comma-separated dt= day stems to restrict --field-health to "
                         "(e.g. dt=2026-07-19,dt=2026-08-07). Pins a FROZEN slice, per "
                         "L191. Default: every committed day-file the family has.")
    ap.add_argument("--field-health-max-bad-days", type=int, default=None, metavar="N",
                    help="the trailing consecutive-BAD-DAY run length that ALERTS "
                         "(default: the family's own max_consecutive_bad_days, else "
                         f"{FIELD_HEALTH_DEFAULT_MAX_BAD_DAYS}). The per-day "
                         "classification itself is threshold-independent.")
    ap.add_argument("--burst-liveness", default=None, metavar="TRIGGER_NAME",
                    help="print ONLY the L227 burst-window liveness audit for TRIGGER_NAME "
                         "(one of BURST_TRIGGER_WINDOWS, e.g. kalshi-burst-fomc-0729; "
                         "read-only, no notify) and exit. Answers 'did every family this "
                         "trigger drives stay live across its declared window, or did tape "
                         "go dark during the one event the burst leg exists to catch'.")
    ap.add_argument("--burst-gap-multiplier", type=float, default=3.0,
                    help="a gap > this many x the trigger's expected interval is flagged as "
                         "an outage episode (default 3.0).")
    args = ap.parse_args(argv)

    if args.window_grid:
        days = ([d.strip() for d in args.window_grid_days.split(",") if d.strip()]
                if args.window_grid_days else None)
        out = {fam: expected_window_grid_coverage(Path(args.tape_root), fam, days=days)
               for fam in sorted(WINDOW_GRIDDED_FAMILIES)}
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.slot_cadence:
        if not args.slot_window:
            print("[tape_gap_monitor] --slot-cadence requires --slot-window START END", file=sys.stderr)
            return 2
        days = ([d.strip() for d in args.slot_cadence_days.split(",") if d.strip()]
                if args.slot_cadence_days else None)
        out = slot_cadence_by_time_of_day(Path(args.tape_root), args.slot_cadence,
                                          args.slot_window[0], args.slot_window[1], days=days)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.caller_explicability:
        days = ([d.strip() for d in args.explicability_days.split(",") if d.strip()]
                if args.explicability_days else None)
        out = caller_explicability(Path(args.tape_root), args.caller_explicability,
                                   days=days, tolerance_s=args.explicability_tolerance_s)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.leg_idempotence:
        if args.leg_gate_hour is None:
            print("[tape_gap_monitor] --leg-idempotence requires --leg-gate-hour N",
                  file=sys.stderr)
            return 2
        days = ([d.strip() for d in args.leg_idempotence_days.split(",") if d.strip()]
                if args.leg_idempotence_days else None)
        try:
            out = single_hour_leg_idempotence(Path(args.tape_root), args.leg_idempotence,
                                              args.leg_gate_hour, days=days,
                                              max_days=args.leg_idempotence_max_days)
        except ValueError as exc:
            print(f"[tape_gap_monitor] {exc}", file=sys.stderr)
            return 2
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.status_regression:
        days = ([d.strip() for d in args.status_regression_days.split(",") if d.strip()]
                if args.status_regression_days else None)
        try:
            out = status_regression_by_key(Path(args.tape_root), args.status_regression,
                                           days=days,
                                           min_run_passes=args.status_regression_min_run)
        except ValueError as exc:
            print(f"[tape_gap_monitor] {exc}", file=sys.stderr)
            return 2
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.field_health:
        days = ([d.strip() for d in args.field_health_days.split(",") if d.strip()]
                if args.field_health_days else None)
        try:
            out = field_health_by_day(Path(args.tape_root), args.field_health,
                                      days=days,
                                      max_consecutive_bad_days=args.field_health_max_bad_days)
        except ValueError as exc:
            print(f"[tape_gap_monitor] {exc}", file=sys.stderr)
            return 2
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

    if args.burst_liveness:
        out = burst_trigger_liveness(Path(args.tape_root), args.burst_liveness,
                                     gap_multiplier=args.burst_gap_multiplier)
        print(json.dumps(out, indent=2, sort_keys=True))
        return 0

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

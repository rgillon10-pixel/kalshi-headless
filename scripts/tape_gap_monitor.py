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

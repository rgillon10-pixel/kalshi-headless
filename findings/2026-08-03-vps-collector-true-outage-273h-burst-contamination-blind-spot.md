# VPS collector: true outage is ~274h (11.4 days), not the 104.7h `invariants.py --full` reports — a burst-window contamination blind spot in the dead-leg diagnosis (2026-08-03)

Idle-run milestone (idle-run policy (c), data-quality deep-dive on the VPS collector-health
family, per LOOP-QUEUE.md v3's idle-run policy — the queue itself has 0 eligible TODO/IN-PROGRESS
items this run, everything Q0-Q50 is DONE/BLOCKED/gated; see this run's kb/00-LOG.md entry for
the full queue re-check).

## Headline

`python3 scripts/invariants.py --full`'s non-gating collector-health advisory currently reads:

```
COLLECTOR HEALTH ADVISORY (non-gating): the 'vps' collector leg appears DEAD.
  - dead leg: vps (captures at minutes 20-29 of the hour)
  - last capture written by it: 2026-07-29T18:29:45.808389+00:00
  - silent for: 104.7h (threshold: 24h)
```

That **104.7h is not the true outage** for four of the six affected families. It is contaminated
by a single capture that landed in the VPS minute-bucket (20-29) by coincidence — the declared
`kalshi-burst-fomc-0729` trigger (window `2026-07-29T17:40:00Z`–`19:45:00Z`,
`scripts/tape_gap_monitor.py::BURST_TRIGGER_WINDOWS`), not the actual VPS `:23` cron. Excluding
that one contaminated timestamp, the real, uncontaminated last-VPS-signature capture across every
affected family is **2026-07-22T17:2x:xxZ** — **~273.9h (11.4 days) silent as of this run**, a
**2.6x understatement** by the advisory's own headline number.

## Method

Independently re-derived every family's newest `captured_at` whose minute-of-hour falls in the
VPS bucket (20-29), reading every committed `tape/<family>/dt=*.jsonl` line directly (not
trusting `invariants.py`'s aggregate reading, which computes ONE number across ALL `hourly-dual`
families):

| family | newest VPS-bucket capture | silent (h, as of this run) |
|---|---|---|
| `orderbook_depth` | 2026-07-22T17:24:00.000505Z | ~273.9 |
| `perp_tape` | 2026-07-22T17:29:45.195883Z | ~273.9 |
| `sports_pairs` | 2026-07-22T17:23:02.155607Z | ~274.0 |
| `weather_books` | 2026-07-22T17:29:49.498223Z | ~273.9 |
| `settlement_ledger` | 2026-07-17T12:23:02.256942Z | ~399 (VPS-sole-writer; see below) |
| `crypto_hourly` | **2026-07-29T18:29:45.808389Z** | 104.8 (the contaminating read) |
| `polymarket_macro_pairs` | **2026-07-29T18:29:24.891810Z** | 104.8 (the contaminating read) |

The two starred rows are the source of the misleadingly-fresh `invariants.py` reading (it takes
the MAX across all `hourly-dual` families for the "vps" leg). Both timestamps sit squarely inside
the declared FOMC burst window, and both families are explicitly burst-covered by that trigger:
`kalshi-burst-fomc-0729`'s `burst_keys = ("fed", "econ", "crypto")` maps via
`BURST_CAPTURE_KEY_TO_TAPE_FAMILY` to `polymarket_macro_pairs` ("fed"), `econ_prints` ("econ"),
and `crypto_hourly` ("crypto") — an exact match to the two families showing the anomalously-recent
"VPS" capture. `sports_pairs` is NOT in that trigger's `burst_keys` and correctly shows no
contamination; neither are `orderbook_depth`/`perp_tape`/`weather_books`/`settlement_ledger` ever
burst-covered by any declared trigger (`BURST_CAPTURE_KEY_TO_TAPE_FAMILY` has no entry that maps
to them), which is exactly why they show the honest, uncontaminated date instead.

This is the same class of blind spot **L213** already named and fixed for the slot-cadence check
(`slot_cadence_by_time_of_day` explicitly excuses declared burst windows via
`BURST_TRIGGER_WINDOWS`) — `_collector_leg_last_seen`/`_dead_collector_leg_diagnosis` in
`scripts/invariants.py` (the function backing the `--full` advisory) does **not** apply the same
exclusion, so a burst pass landing in the vps bucket is indistinguishable from a genuine VPS pass
there.

## What this changes

- **No registry flip, no CI, no P&L, no kill decision** — this is a collector-health data-quality
  finding (idle-run policy (c)), not a strategy verdict; the two-agent rule does not bind this
  milestone class (same posture as L156/L168/L172/L185/L213/L221/L222).
- **The VPS `:23` leg has not produced a single genuine capture for `orderbook_depth`,
  `perp_tape`, `sports_pairs`, or `weather_books` since 2026-07-22T17:2x** — i.e. it has been
  continuously dead since the **second** death this project already documented
  (`findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md`,
  `findings/2026-07-27-stranded-tape-recovery-hourly20260726T2204Z-and-vps-dead-102h.md`). There
  was **no recovery** between 07-27 and now — the apparent "life" at 07-29T18:29 on two families
  was the FOMC burst trigger, not the VPS cron. This is now the **longest VPS outage on record**
  for this project (prior max reported: 102.9h on 07-27; true continuous figure is now 273.9h+
  and counting), and — unlike the 07-27 report — it went **completely unnoticed for 11+ days**:
  no run between 07-27 and this one flagged it (`kb/00-LOG.md` has zero VPS mentions between
  07-27 and this entry), exactly the "silent for 2 days without anyone noticing" scenario
  LOOP-QUEUE.md's 2026-07-10 hardening note was written to prevent — except this time it was the
  advisory's own contamination, not an absent ntfy note, that let it slip through: the advisory
  fired every run (non-gating, easy to skim past) and under-reported its own severity each time.
- **`settlement_ledger`** is a distinct, worse case: it is VPS-**sole**-writer (its 10Z gate hour
  has no cloud/other fallback, per the 07-27 finding), last genuine capture
  **2026-07-22T10:31:41Z**, now **~280.7h (11.7 days) fully stale — zero lines of any kind since**
  (confirmed via `tape_gap_monitor.py --no-notify --json`'s `settlement_ledger` entry:
  `"alert_reason": "stale: 280.7h since last pass (> 48h threshold)"`, matching the direct scan).
  This is not new information (Q45/L185/L186/L187 already characterized the family's structural
  cap/window problem) but the sheer duration of the current freeze had not been reported since
  the family's own tape stopped growing.
- **New lesson `L269` (UNENFORCED)**, recorded in `kb/lessons/00-lessons.md`: the dead-collector-
  leg diagnosis in `scripts/invariants.py` computes the "vps" leg's last-seen timestamp as the MAX
  across every `hourly-dual` family with no burst-window exclusion, so a single burst pass landing
  in the 20-29 minute bucket for ANY monitored family (not just the family it burst-covers) resets
  the WHOLE leg's apparent freshness and can mask a family-specific death for the length of that
  burst's silence afterward. Candidate fix: reuse `tape_gap_monitor.BURST_TRIGGER_WINDOWS` /
  `BURST_CAPTURE_KEY_TO_TAPE_FAMILY` (already imported elsewhere in `invariants.py` for the L213
  slot-cadence path) to exclude burst-window captures from `_collector_leg_last_seen`'s per-family
  scan, mirroring `slot_cadence_by_time_of_day`'s existing pad-and-exclude logic. Not built this
  run — this run is diagnosis-only (idle-run policy (c) scope); left for a future run or Ryan to
  prioritize against the mixed-tier backlog L268 already confirmed is otherwise empty.

## Ryan-side action needed (repeat of the 07-20/07-25/07-27 ask, now overdue much longer than
last reported)

1. **Restart the VPS `:23` cron on 87.99.146.250.** This is the fourth (or later — see above,
   the 07-27→now gap was never actually a recovery) documented death of the same leg, now the
   longest yet, and it is the sole writer for `tape/settlement_ledger/` and half the cadence for
   five other families. A cloud sandbox structurally cannot restart it.
2. Because the last three "is it still dead" checks were all done by hand mid-run, **the
   automated advisory itself needs the L269 fix** before its own headline number can be trusted
   again — until then, treat any `invariants.py --full` "silent for Nh" reading on the `vps` leg
   as a **lower bound**, not the true figure, whenever a burst trigger has fired inside the
   window it's currently reporting.

## Gates

Read-only investigation: no source file touched, `pytest`/`invariants --full` counts are
unchanged from this run's own baseline (taken after this diff's only change, a docs-only
`findings/` + `kb/` + `LOOP-QUEUE.md` append — see this run's `kb/00-LOG.md` entry for the
fresh-taken gate line, per L162).

## Reproduce

```
# the contaminated aggregate reading:
python3 scripts/invariants.py --full 2>&1 | grep -A4 "COLLECTOR HEALTH ADVISORY"

# per-family honest VPS-bucket newest capture (uncontaminated by burst windows):
python3 - <<'PY'
import json, glob
from datetime import datetime
for fam in ["orderbook_depth","perp_tape","sports_pairs","weather_books",
            "settlement_ledger","crypto_hourly","polymarket_macro_pairs"]:
    newest = None
    for path in sorted(glob.glob(f"tape/{fam}/dt=*.jsonl")):
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ca = rec.get("captured_at")
            if not ca:
                continue
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            if 20 <= dt.minute <= 29 and (newest is None or dt > newest):
                newest = dt
    print(fam, newest)
PY

# the burst-window declaration that explains the two contaminated families:
python3 -c "from scripts.tape_gap_monitor import BURST_TRIGGER_WINDOWS as w; print(w['kalshi-burst-fomc-0729'])"

# settlement_ledger's independent staleness reading:
python3 scripts/tape_gap_monitor.py --no-notify --json | python3 -c "import json,sys; print(json.load(sys.stdin)['settlement_ledger'])"
```

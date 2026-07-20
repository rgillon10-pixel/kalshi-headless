# Tape capture-cadence decline — root cause: VPS `:23` collector dead since ~2026-07-18 (idle-run option c, 2026-07-20)

- **Date:** 2026-07-20 (idle-run, protocol v3 option c — data-quality deep-dive).
- **Scope:** Why `tape/perp_tape/` and `tape/crypto_hourly/` line counts have been halving day over
  day (511→238→102, 64→28→14 over 2026-07-17→07-19), a decline flagged repeatedly (Q42/Q43 prep,
  PR #132, #134) but never root-caused. Extends Q44's aggregate under-capture finding
  (`kb/00-LOG.md` 2026-07-17) with a per-collector liveness decomposition.
- **Mode:** READ-ONLY over committed tape + `collection/`/`ops/` source. No collector run, no
  network calls, no files modified other than this write-up.
- **Verification:** tape-auditor sub-agent report, independently re-verified by the research loop
  against the real committed tape (line counts re-counted from scratch; the minute-of-hour
  attribution re-derived independently by parsing every `captured_at` timestamp per family/day —
  both reproduce the sub-agent's numbers exactly). This is a data-quality/ops diagnosis, **not** a
  strategy verdict or registry change — the two-agent verifier rule (verdict-class changes only)
  does not apply; the independent re-derivation here follows the same "don't just trust the
  agent's self-report" discipline used for Q44/Q45/Q46's collector builds.
- **Provenance lessons:** extends L74 (single-UTC-hour daily-family blackouts — a different
  mechanism), L75 (`daily_family_gap_warning`), and Q44's own `scripts/tape_gap_monitor.py`
  under-capture finding (2026-07-17: cloud `:53` collector at ~58-62% of expected cadence).

---

## 1. Bottom line

The decline is **real, global across every continuously-sampled hourly family (not specific to
perp_tape/crypto_hourly), still accelerating, and not reversing on 07-20.** Minute-of-hour
attribution of each line's `captured_at` timestamp pins the cause precisely: **the VPS collector
(the `:23` cron on 87.99.146.250 per `ops/ROUTINES.md`) stopped writing tape starting
2026-07-19 — zero VPS-signature lines on 07-19 and 07-20 — after a partial day on 07-18.** The
cloud `kalshi-collector` routine (`ops/ROUTINES.md`'s `:53` trigger) is the sole survivor and is
itself chronically under-cadence, the exact leak Q44 already flagged on 07-17. **This is a
Ryan/VPS-infra item, not a repo/code bug** — every collector module inspected is clean (fixed
symbol lists, honest `try/except`, `completeness_ok` all-true whenever a pass does fire); there is
no code change in this repo that would restore cadence.

## 2. Per-day line counts (independently re-counted, `wc -l` over committed tape)

| family | 07-17 | 07-18 | 07-19 | 07-20 (partial) |
|---|---|---|---|---|
| `perp_tape` | 511 | 238 | 102 | 51 |
| `crypto_hourly` | 64 | 28 | 14 | 6 |
| `orderbook_depth` | 29,435 | 15,020 | 6,655 | 3,295 |

Lines-per-pass is dead constant across all four days (perp_tape 17.0/pass, crypto_hourly
2.0/pass) — confirming per-pass capture is healthy and the decline is purely in **pass count**,
not per-pass record loss.

## 3. Minute-of-hour attribution (the root-cause evidence, independently re-derived)

Bucketing every line's `captured_at` by minute-of-hour into VPS-signature (`:20`-`:29`) vs
cloud-signature (`:50`-`:59`) windows:

**`crypto_hourly`:**

| day | VPS (`:2x`) | cloud (`:5x`) |
|---|---|---|
| 07-17 | 48 | 16 |
| 07-18 | 18 | 10 |
| 07-19 | **0** | 14 |
| 07-20 | **0** | 6 |

**`orderbook_depth`:**

| day | VPS (`:23`) | cloud (`:54`-`:56`) |
|---|---|---|
| 07-17 | 22,710 | 5,751 |
| 07-18 | 9,766 | 5,254 |
| 07-19 | **0** | 6,655 |
| 07-20 | **0** | 3,295 |

`perp_tape` uses a different per-family minute signature (`:00`/`:27`/`:28`/`:03` rather than a
clean `:23`), but shows the identical die-off shape: non-zero VPS-pattern captures through 07-18,
**zero** from 07-19 onward.

**Reading:** the VPS collector carried the majority of daily load through 07-17 (e.g. 22,710/29,435
orderbook_depth lines = 77%), degraded partially on 07-18 (last VPS-pattern capture ~09:00 UTC),
and has been **completely silent on 07-19 and 07-20**. The cloud collector — already running at
Q44's flagged ~60% of expected cadence since 07-15 — is now the *only* surviving collector, which
is why the family-wide totals keep halving rather than stabilizing at Q44's already-degraded
baseline.

## 4. Ruling out a repo-side cause

- `collection/hourly_pass.py` fires exactly one pass per invocation; nothing in the repo controls
  invocation frequency (no committed cron, no GHA workflow, no sleep loop) — scheduling is
  external by design (per Q44's own note that wiring a cron/routine is "an explicit Ryan pause
  point").
- `collection/crypto_hourly.py` (`SYMBOLS = {"BTC": "KXBTC", "ETH": "KXETH"}`) and
  `collection/perp_tape.py` (fixed `PERP_API_BASE`) both have unchanged, fixed symbol lists — no
  silent symbol-list shrinkage.
- `completeness_ok` on every crypto_hourly pass that DID fire on 07-17/18/19/20 is 62/28/14/6
  true, **0 false** — capture quality is perfect whenever the collector actually runs.

## 5. Verdict — not cloud-run-actionable

The dead collector is a VPS crontab at 87.99.146.250; the degraded backup is a `claude.ai`-side
routine (`ops/ROUTINES.md`, trigger not version-controlled). Neither is reachable or restartable
from a cloud sandbox (no SSH credentials — by design, per CLAUDE.md's credential-isolation rule).
**Recommended action for Ryan:** (a) check/restart the VPS `:23` cron on 87.99.146.250 (dead since
~07-18 09:00 UTC — the primary regression); (b) diagnose the cloud `kalshi-collector` routine,
chronically under-cadence since ~07-15 per Q44.

## 6. Impact on Q43

Q43's gate (`>=7 days of tape/perp_tape/ forward coverage`, opens ~2026-07-23/24) is a
**calendar-day** gate. At the current cadence those 7 days will carry ~3-7 passes/day instead of
the ~30-48/day baseline the probe was designed against — the gate will open on tape roughly
1/8th the intended density. Flagged for whoever runs Q43 once its gate opens: check per-day pass
count, not just calendar-day count, before trusting the result as adequately powered.

## 7. Lesson candidate (for kb-distiller)

**When an hourly tape family's line count halves day-over-day in lockstep with OTHER unrelated
families, at a CONSTANT lines-per-pass, the cause is the shared external scheduler dying — not a
per-family collector bug.** The discriminator is minute-of-hour bucketing of `captured_at`: each
collector's fixed capture-minute signature (VPS `:2x`, cloud `:5x`) lets a monitor attribute a
cadence drop to a SPECIFIC collector rather than only reporting an aggregate under-capture ratio
(Q44's current signal). This upgrades `scripts/tape_gap_monitor.py` from "family X is
under-captured" to "family X's VPS leg specifically died on day Y" — actionable detail Q44's
aggregate ratio doesn't surface. Extends L74/L75/Q44.

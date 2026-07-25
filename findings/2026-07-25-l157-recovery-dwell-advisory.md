# L157 enforcement: recovery-dwell advisory in `scripts/invariants.py`

**2026-07-25, research loop, idle-run policy (a).**

## The gap

L157 (`kb/lessons/00-lessons.md`) records that L129's "VPS collector RECOVERED" declaration
(`findings/2026-07-22-vps-collector-recovered-post-pr151.md`) was filed on the strength of a
single fresh pass, with no stated dwell window. The recovery dwelled **18.8h** measured from
L129's declared recovery moment (`2026-07-21T22:41Z`), or **18.1h** measured from the first
`:23`-cadence pass (`2026-07-21T23:23:01Z`) — then the collector died again and stayed dead
**61.7h** unnoticed (`findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md`).
A point observation cannot distinguish a fixed collector from one that will die again tomorrow.
L157's rule: no collector-recovery finding may be filed without stating an observed dwell of
**≥24 consecutive hours** of the expected signature bucket, post-restart, anchored to a named
UTC moment.

## What this run built

`scripts/invariants.py::_recovery_dwell_issues` / `recovery_dwell_warning`, wired into `main()`'s
`--full` path as a **non-gating** stderr advisory (never appended to the gating `failures` list).

**Scope — headline-only, by design.** Recovery-class membership is decided from a finding's
filename slug + its first `# ` H1 only, never the body. On the 2026-07-25 tree, 16/83
`findings/*.md` mention "recover" somewhere in the body (usually while correcting or refuting an
earlier claim) while exactly 1 makes a recovery claim in its headline. A body-wide match would be
a ~16x precision disaster of the kind L155 warns about, and would fire hardest on the findings
that are *correcting* a bad recovery claim — exactly backwards.

**Both halves of L157 are checked, independently reported:**
- a **stated dwell** — an hours-quantified duration (≥24) sharing a line with dwell vocabulary
  (`dwell`/`consecutive`/`uptime`/`since the restart`/...). A bare duration elsewhere in the
  document doesn't count — a recovery finding routinely quotes the *outage* length in hours,
  which is not a dwell. Durations in days or minutes don't count either; L157's bar is stated in
  hours.
- a **named anchor** — an explicit `YYYY-MM-DD hh:mm` UTC moment on or within 2 lines of the
  dwell statement. A bare calendar date or a relative phrase ("since the restart") is not an
  anchor.

**Escape hatch (narrow, per L162):** a finding recording its own supersession — an ALL-CAPS
`SUPERSEDED`/`RETRACTED`/`WITHDRAWN`/`CORRECTED` marker at the start of a line near the top,
naming the superseding lesson ID or finding file — is skipped, so ordinary prose mentioning
supersession can't silence the check by accident.

## Test coverage (`tests/test_recovery_dwell_advisory.py`, 48 tests)

Per L155's own discipline (a lexical proxy's clean report on the real tree is evidence of
precision only, never recall): a constructed-positive corpus (17 violation shapes that must
fire, including near-misses like day/minute-stated durations and relative anchors), a
constructed-negative corpus (10 clean/near-miss shapes, including both escape-hatch variants),
a constructed-blind-spot corpus (4 genuine misses — repair-verb headlines like "is fixed", an
H2-only claim, an outage-duration read as a dwell — asserted as misses so widening the rule
requires deleting an entry on purpose, never by accident), and a HARD acceptance suite against
the real `findings/` tree. **Measured recall on the full 22-shape adversarial corpus: 18/22**,
stated honestly in the advisory's own text rather than implied as complete.

Five more tests pin that the advisory can **never** change the exit code — detector exception,
non-`str` formatter return, `BaseException`/`SystemExit` raised by the formatter — all degrade to
a stderr note, none touch `main()`'s return value.

## Live verification against the real tree

`python scripts/invariants.py --full` correctly flags the known-defective
`findings/2026-07-22-vps-collector-recovered-post-pr151.md` (reason: no stated dwell ≥24h) and
stays silent on `findings/2026-07-21-vps-collector-day3-still-down.md` ("still dead on day 3")
and `findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md` ("SECOND
death") — neither's headline is a recovery claim, even though the 07-25 finding's *body* quotes
an 18.8h dwell (below the 24h bar) that would incorrectly fire if the headline scoping leaked
into the body.

## Gates

`pytest`: full suite green (+48 new). `python scripts/invariants.py --full`: exit 0, same
pre-existing non-gating advisory classes as `HEAD` before this run, plus the new L157 advisory
firing correctly once.

No strategy claim, no bootstrap CI, no registry change — reliability infrastructure, same class
as L109/L118/L126/L144/L150/L152/L156/L160/L161. Two-agent verdict rule N/A.

## Not done here

The advisory's own documented blind spots (repair-verb headlines, H2-only claims, outage-vs-dwell
line-sharing) are deliberate scope decisions, not oversights — widening the rule is future work
that must delete the corresponding `_BLIND_SPOT_SHAPES` entry on purpose.

# Every zero now carries its own denominator — and S3's checks were not immune either

`2026-08-06` · research loop, IDLE RUN, idle-run policy **(a)** (convert an UNENFORCED lesson
into an invariant/test) · main-context build (this harness exposes no `Task`/subagent tool, so
no `verifier` was dispatchable — the L287/L288/L290/L291/L295 precedent) · **verdict class:
TOOLING + DESCRIPTIVE data-quality. No registry flip, no bootstrap CI, no kill decision.
Still 0 proven edges.**

## What this run converted

`kb/lessons/00-lessons.md` **L296** (2026-08-06) is filed as
`UNENFORCED (verdict half) + protocol (the reading rule)`. Its reading rule:

> `n_hits == 0` and `n_candidates_checked == 0` are different claims, and S15 has been
> reporting the second while its registry row was read as the first for a month.

Nothing in the repo made that state visible. `scripts/anomaly_sweep.py` persisted three
candidate counters and ONE aggregate hit count (`n_anomalies`) spanning all three checks, so a
reader could not attribute a zero to a check at all, let alone to a denominator. This run makes
the pairing structural, at the write path, and replays the whole committed history through the
same predicate.

Built (ONE shared site, not three private copies — the L36/L102 twin discipline, same shape as
`core.pricing.is_fillable_ask` and `core.subject_identity.same_subject`):

- **`core/detector_evidence.py`** — `classify_detector_evidence(n_candidates_checked, n_hits)`
  returning four values: `hits` · `informative_zero` (the ONLY zero readable as absence) ·
  `empty_denominator` (L296's failure) · `incoherent` (hits over an empty denominator).
  `zero_is_informative(klass)` is the single question a consumer should ask, and it refuses by
  default on any unknown class. `evidence_block()` is the persisted shape — denominator,
  numerator and class in one dict, so a hit count can never again be written down without the
  number that makes it readable. A fifth constant, `counter_absent`, exists for RECORDS: a key
  the collector never wrote and a key it wrote as `0` are different claims (L289's exact shape).
  Malformed INPUT (negative, non-integer counts) raises; an INCOHERENT CLAIM does not — a raise
  inside a live collector would destroy a pass's tape over a bookkeeping contradiction (L86),
  and in replay it would make the audit unable to COUNT the contradictions, which is the one
  number that matters when you find one.
- **`scripts/anomaly_sweep.py`** — persists `check_evidence`, additive to `anomaly_sweep.v1`,
  no existing field changed in shape or meaning: per check, `{n_candidates_checked, n_hits,
  evidence}`, with hits counted **per check from each anomaly's own `kind`** rather than from
  the aggregate. The evidence class is also printed to stderr on every pass, so an empty
  denominator is loud at run time — the failure went unnoticed for a month precisely because
  nothing said it out loud. Exit-code semantics are untouched: an empty denominator is not a
  fetch failure, and `completeness_ok` still drives `main()`.
- **`scripts/anomaly_detector_evidence_audit.py`** → `reports/anomaly_detector_evidence_audit.json`
  — read-only, NO network, no dependency on the new field, so it covers the whole committed
  history rather than only post-guard passes.

## Measured — `tape/anomalies/`, CLOSED window `--max-day 2026-08-04`, 248 passes / 26 capture-days / 0 malformed lines

| check | hits | informative_zero | **empty_denominator** | counter_absent | Σ candidates | Σ hits |
|---|---|---|---|---|---|---|
| `bracket_arb` | 0 | 225 | **23** | 0 | 2,210 | 0 |
| `cross_strike_monotonicity` | 137 | 88 | **23** | 0 | 2,210 | 43,038 |
| `cross_event_implication` | 0 | **0** | **243** | 5 | **0** | 0 |

**L296's 243/243 reproduces exactly**, on an independent code path, through the shared
predicate — and the 5 records that predate the counter are reported as their own class rather
than folded into the zero (248 = 243 + 5).

**New, and not in L296: S3's own two checks are not immune.** 23 of 248 passes (9.3%)
evaluated **zero** candidate groups — and all 23 report `completeness_ok: true`, `fetch_error:
null`, and a non-zero `n_markets_scanned` (up to the full 20,000-market cap). A pass that
scanned 20,000 markets, checked nothing, and looks clean is the same defect one family over.
They cluster: 10 of the 23 fall on `dt=2026-07-18`.

Also measured, descriptive: `n_bracket_groups_checked == n_monotonicity_groups_checked` on
**248/248** passes. That is **not** an identity the code guarantees — an event holding three
`between` rungs increments the bracket counter and not the monotonicity one — so it is pinned
as a regression target rather than explained away. Whatever the cause, the qualifying
population is tiny: 2,210 group-checks over 26 days is ~8.9 per pass out of ~20,000 markets
scanned.

## What this does NOT do

- **It does not make S3 or S15 killable.** The coverage denominator is still truncation-bound:
  247/248 passes are `markets_truncated` at the 20,000 cap, and Q55's `scanned_tickers_sha256`
  (added today) only starts accumulating from the next passes forward, so cross-pass population
  comparison is not yet possible. This guard measures whether a check ran; it says nothing
  about what fraction of the platform it ran against.
- **It does not fix check 3's empty denominator.** Q55 milestone 2 gave
  `config/implication_pairs.yaml` its first live family (`KXMARMADROUND`, 1,120 pairs on an
  offline direct fetch), but the first real live pass still recorded
  `n_implication_pairs_checked: 0` because the 20,000-market cursor was unexhausted before
  reaching that series. The expected reading of the next few passes is therefore **still
  `empty_denominator`** — now labelled as such instead of silently passing as a clean zero.
  That is the whole point: the state is unchanged, its visibility is not.
- **No verdict.** No registry status was touched, no CI computed, no kill proposed. L296's
  verdict half stays `PROVISIONAL` and Ryan/two-agent-gated exactly as filed.

## Reproduce

```
python3 scripts/anomaly_detector_evidence_audit.py --max-day 2026-08-04
python3 -m pytest tests/test_detector_evidence.py tests/test_anomaly_detector_evidence_audit.py tests/test_anomaly_sweep.py -q
```

Tests: `tests/test_detector_evidence.py` (22) · `tests/test_anomaly_detector_evidence_audit.py`
(16: 9 fixture + 7 real-tape acceptance) · `tests/test_anomaly_sweep.py` (+5, now 70). Every
fixture is written to FIRE on the planted defect (L191), including a pass that scanned 20,000
markets, checked nothing, and reported success.

Deliberately NOT wired into `scripts/invariants.py --full` — the L210/L280/L290 posture: the
property is enforced at the write path itself, so a standing advisory would only re-measure
frozen history and add noise runs learn to ignore.

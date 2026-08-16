# `close_time` is not a schedule — it is rewritten at settlement, always earlier

**Date:** 2026-08-16 · **Run:** kalshi-research-loop (3-hourly), protocol v3 · **Class:**
data-quality deep-dive (idle-run policy (c)) · **Verdict class:** DESCRIPTIVE / PRE-FLIGHT.
**No CI, no P&L, no bootstrap, no kill, no registry flip. Still 0 proven edges.**
**Committed PROVISIONAL** — the two-agent rule is not satisfiable in this harness (no
`Task`/`verifier` subagent exists; L287/L288/L290/L291/L295/L308/L313/L325/L338 precedent),
so the sanctioned redundancy fallback ran instead and is reported AS redundancy, never as
verification.

## The premise that was never measured

`scripts/q51_m3_fill_projection.py` reads `close_time` out of a deliberately FROZEN
pre-settlement cache and documents the choice as safe on an explicit premise — `close_time`
is *"a SCHEDULE field, never an outcome"* (`:51`, `:118-119`, and the emitted report field
`what_is_read_from_the_cache`). Four sports probes (`q26`, `q28`, `q29`, `q30`) rely on the
same premise differently: a cached `close_time` is the boundary that defines a "pre-close"
snapshot (`captured_at < close_time`), and in `q26`/`q28` it is also the ORIGIN of a
time-to-close feature (`ttc_seconds` / `ttc_hours`).

Nothing had ever checked it. It is checkable, because committed tape holds two substrates
that answer from opposite directions: `tape/q51_settlement_cache/` has three pulls of the
SAME 60-ticker population (one before those markets settled, two after), and
`tape/universe_sweep/` re-observes LIVE open markets across 26 days.

## F1 — three regimes, each measured separately

Classification is by the SETTLEMENT STATE of the two rows, never by the timestamps themselves
(the trustworthiness of the timestamp is the thing under test). Over all 8 committed
settlement-cache blobs, 9 overlapping blob pairs, **1,689 paired observations / 533 distinct
tickers**:

| regime | observations | close_time instant changed | direction |
|---|---|---|---|
| `open_to_open` | 3 | 0 | — |
| `open_to_settled` | 98 | **96** | **96 earlier, 0 later** |
| `settled_to_settled` | **1,588** | **0** | — |

Median shift on the changed rows: **−51.90 h**. Range **−0.67 h to −333.34 h** (−13.9 days).

**Live control** (`tape/universe_sweep/`, a different family, a different collector, a
different mechanism): **1,100,000 records**, 36,765 tickers observed at ≥2 distinct instants,
**36,765 stable / 0 changed**. While a market is open its `close_time` never moves.

So the mutation happens EXACTLY ONCE, at the active→finalized transition, and it is strictly
one-directional. Granularity corroborates the mechanism: pre-close, 20/60 close_times sit on a
round hour and only 10 are second-precise; post-close, **58/60 are second-precise**. A
scheduled placeholder is replaced by a recorded event instant.

**The stability while open is the trap.** A reasonable engineer who asked "is `close_time`
stable?" and checked live tape would get 36,765/36,765 and conclude the field is a reliable
constant. It is reliably *wrong*: the value a trader can observe is systematically LATER than
the market's true close.

## F2 — the exposure, at the granularity a consumer actually uses

`q51_m3_fill_projection._close_date_map` buckets rows by the UTC calendar DATE of
`close_time`, read from the frozen m2 cache. Between that cache and the post-settlement pull,
**47 of 60 tickers (78.3%) change close DATE** — the derived value, not just the instant.
Distinct-ticker totals across the whole cache registry: **48 tickers' close instant changed,
47 changed close date, 49 crossed open→settled**.

(The `n=98` above is an OBSERVATION count — a ticker shared by three blobs appears in three
pairs. The honest market-level unit is 48/49, and the audit reports both under separate names
precisely so the larger number cannot be quoted as markets.)

**Consequence, stated exactly.** Two different things are going on and only one is a defect:

* Using the settled `close_time` to SELECT pre-close snapshots (`captured_at < close_time`)
  is *correct* — it is the true instant trading stopped, and it excludes snapshots the
  placeholder would have wrongly admitted. `q29`/`q30` use it this way.
* Using it as a FEATURE — `ttc_seconds`, `ttc_hours`, "the last snapshot before close", a
  close-date bucket — is a **look-ahead**. At trade time the observable was the placeholder,
  a median 51.9 h later. A "final hour before close" bin identified post-hoc could not have
  been identified live at all.

**No verdict flips, and that is not luck — it is direction.** `q26`, `q28`, `q29`, `q30` and
`q51` M3 are all closed DEAD or admissible-null. A look-ahead inflates a result; a strategy
that is dead *with* the inflation is more dead without it. So this repairs no past number and
is recorded as **forward-binding** only: the next probe that reaches a POSITIVE result on a
close-time-conditioned feature would be inflated by exactly this mechanism, and nothing in the
repo warned about it.

## F3 — the label substrate itself is clean, and that is what makes the gate worth having

Across the same 1,588 settled-to-settled paired observations there are **0 disagreements on
`result`**. The caches every closed DEAD verdict leaned on are internally consistent today.

That clean baseline is why it is now GATED rather than merely noted.
`core.settlement_sources.resolve_market_results` structurally cannot surface this class: its
precedence is first-BINARY-wins, so a second cache carrying the OPPOSITE binary result is
discarded silently and the resolver reports full confidence. The disagreement is visible only
by comparing caches to EACH OTHER, which nothing did until this audit.

## Enforcement

`scripts/invariants.py::_settlement_cache_result_conflict_issues` /
`settlement_cache_result_conflict_failure`, wired into `--full` as **GATING**. Gating rather
than advisory (contrast L353's posture) because unlike a collector-created data condition, a
settlement cache changes only when a probe in THIS repo writes one — the trigger is fully
under our control, and a corrupt label invalidates whichever verdict rests on it, so it must
stop the line rather than scroll past on stderr. Deliberately narrow: only rows BOTH sides
call settled participate (settlement lag is not a conflict, L262); `scalar`-vs-binary counts;
casing/padding does not.

**Deliberately NOT done:** repointing any probe's `close_time` source, or adding a
"placeholder close" warning to the fill-sims. Every affected probe is sealed or closed
(L309/L311 forbid touching a sealed probe's logic), and re-pointing an input would change the
population of verdicts that are already recorded — a two-agent change, filed as a candidate,
not executed.

## Redundancy (NOT verification)

`scripts/close_time_mutation_rederive.py` — AST-pinned to import neither the audit, nor
`core.close_time_mutation`, nor `core.settlement_sources`, nor `core.result_evidence`. It
finds fields by regex over raw bytes and attributes them POSITIONALLY (nearest preceding
ticker-shaped key) rather than structurally; it enumerates cache files by glob rather than
from the source registry, so a registry omission cannot hide a file from both; and it answers
the live-stability question BACKWARDS and without any ordering — `close_time` is stable for
every ticker iff the number of distinct `(ticker, close_time)` pairs equals the number of
distinct tickers. It reads no `captured_at` at all, so a clock defect cannot produce the same
answer twice.

Result: **1,063,235 distinct tickers, 1,063,235 distinct (ticker, close_time) pairs, 0
tickers with more than one close_time** — strictly stronger than the audit's 36,765-ticker
first-vs-last comparison, and agreeing with it. Every cache-side number reconciles exactly:
8 files, 1,689 paired observations, 533 distinct tickers, regimes 3/98/1,588/0, 48 / 47 / 49
distinct, 96 earlier / 0 later, 0 conflicts.

**One published limit:** L136/L150 gate every new raw `datetime.fromisoformat` site (Kalshi's
bare-`Z` / short-fraction timestamps are 38.27% of committed tape and crash on the declared
Python-3.9 floor while passing CI's 3.11). So both implementations import
`core.timeutil.parse_iso_utc`, and a defect INSIDE that parser is the one error class this
redundancy cannot catch. Independence bought with a known bug would have been worse; the
limit is published rather than hidden, and the shared surface is AST-pinned to exactly one
module.

**The redundancy found a bug — in itself, and only via a fixture.** Its positional attributor
keyed on each ticker match's END offset with a strict `<`. In COMPACT JSON the next character
is the first field's opening quote, so the owner's offset EQUALS the field's start and the
field was attributed to the PREVIOUS ticker. The committed caches are pretty-printed, so real
tape never reached it and every reconciled number was identical before and after the repair —
which is exactly why the fixture, not the tape, had to be the thing that asked.

## Provenance and discipline

No price is read or persisted by this audit, so **no `price_source_tag` attaches to its own
outputs**; the rows it counts carry their sources' tags (`broker_truth` on all 8 committed
cache blobs, 0 without a `pulled_at`). Read-only, offline, no network. Report keys are pinned
against ever carrying a `pnl`/`ci95`/`bootstrap`/`kelly`/`sharpe` name.

**Three existing ratchets fired on this run's brand-new code before it could be committed** —
L136/L150 (two raw `fromisoformat` sites) and L345 (an `unknown`-class settlement root in the
re-derivation). All three were repaired rather than exempted. That is the second consecutive
run in which the invariant wall caught the current run's own new code.

## Artifacts

* `core/close_time_mutation.py` (+ `tests/test_close_time_mutation.py`, 29 tests)
* `scripts/close_time_mutation_audit.py` (+ `tests/test_close_time_mutation_audit.py`, 21)
* `scripts/close_time_mutation_rederive.py` (+ `tests/test_close_time_mutation_rederive.py`, 15)
* `scripts/invariants.py` GATING check (+ 9 tests in `tests/test_invariants.py`)
* `reports/close_time_mutation_audit.json`, `reports/close_time_mutation_rederive.json`

# L292 → an invariant: the trade-tape registration-surface guard

`research loop` · **IDLE RUN** · 2026-08-07 · idle-run policy **(a)** (convert an UNENFORCED
lesson into an invariant/test) · **NOT verdict-class**: no bootstrap CI, no P&L, no fill rate
quoted as an edge, no registry status flip, no kill decision. Still **0 proven edges**.

## Why this run is an idle run

Full Q0–Q55 rescan at each item's **current** (topmost) Status line, 2026-08-07:

| item | current state | eligible? |
|---|---|---|
| Q0–Q13, Q16, Q18, Q20, Q22–Q31, Q34, Q37, Q38, Q44–Q46, Q49, Q50 | DONE | no |
| Q14 (`fedwatch-scrape`), Q15 (`no-live-market`), Q33 (`polymarket-us-credentials`) | BLOCKED | no |
| Q17 | RESERVED for PR #46 (Ryan-review-only) | no |
| Q19, Q32, Q35, Q36, Q42, Q43, Q47, Q48 | gated (burst / credential / density / Ryan-activation) | no |
| **Q51** | milestone 3 **time-gated to 2026-08-10**, pre-flighted 08-05 | no (3 days early) |
| Q52, Q54 | DATA-GATED — need multi-day `tape/kalshi_trades/`; still exactly **1** committed day | no |
| Q53 | milestones 1–2 DONE; milestone 3 delivered PROVISIONAL, owes an independent `verifier` | **not satisfiable** — see below |
| Q55 | milestones 1–2 DONE | no |

Q53's outstanding milestone is the only non-gated one in the file, and it is a **verdict-class**
closure: its own text says "turning it into a kill requires the two-agent rule (producer + independent
`verifier`)". **No `Task`/subagent tool exists in this harness** (available tools this run: Read,
Grep, Glob, Bash — no `Task`, no `Edit`, no `Write`), so no `verifier` was dispatchable, exactly as
on Q19/Q49/Q50/Q51/Q53/Q55 (the L287/L288/L290/L291/L295 precedent). A verdict-class change is
therefore off the table by rule, and the run falls to idle-run policy (a).

**Standing UNENFORCED work queue, recomputed with the repo's own detector** (`invariants.py::
_parse_lesson_rows` + `_lesson_disposed_ids` + `_UNENFORCED_MARKER_RE`): 6 open rows —
`L213` (Ryan-action half), `L221` (write-path half, cell says **DO NOT BUILD**, duplicate of open
PR #165), `L222` (write-path half, out of a research run's lane), `L282` (Ryan-lane step-0b sweep
workflow), `L296` (verdict half, needs the unavailable verifier), and **`L292`**. L292 was the only
one with a buildable, in-lane, offline artifact left. It is now `test`; the queue is down to 5, all
of them Ryan-lane or verifier-gated.

## What L292 says, and what was wrong with its enforcement cell

> A `tape/kalshi_trades/`-anchored maker/taker candidate must name its target tickers' PRESENCE on
> the trade tape at proposal time — the only committed day (`dt=2026-08-03`) is sports+crypto-only,
> so any econ/weather/politics markout-filter candidate is UNMEASURABLE today.

Its enforcement cell closed the row with *"no machine-checkable artifact fits it ... the check is a
one-line ticker-inventory grep the proposing run must run."* Both halves of that sentence are true;
the conclusion does not follow. A one-line grep that every proposing run must **remember** to run is
the exact thing CLAUDE.md's third prime directive says to convert. That is the new lesson **L299**.

## Built

**1. `scripts/kalshi_trades_ticker_inventory.py`** — read-only, fully offline, no network, never
imported by a collector. Per-SERIES inventory of `tape/kalshi_trades/` (`series_of`,
`trade_tape_inventory`, `series_coverage`, `named_series_tokens`) with a stable JSON shape and a
`--max-day` window freeze (L140).

Three-valued coverage, so an un-collected family can never render as an absent one (L289/L296):
`COVERED` / `ABSENT` / `UNKNOWN_NO_TAPE`.

**2. `scripts/invariants.py::kalshi_trades_registration_surface_warning`** over
`_kalshi_trades_registration_issues` — reads every `kb/strategies/00-index.md` row anchored on
`kalshi_trades`, extracts the KX series tokens it names, and classifies it into three classes that
are **reported separately and never merged** (L289):

* `uncovered` — names ≥1 series with no committed print. **The S81 shape.**
* `unscoped` — anchors on the trade tape but names no series token, so coverage cannot be checked.
  Reported, explicitly **not** called a defect.
* `covered` — every named token has committed prints.

Non-gating, permanently and by design (same posture as the L152/L205/L210 ledger advisories):
an uncovered family is the honest data-gated posture S55/S78/S79 already carry, and the trade
collector's cadence is Ryan-gated (L221/L222). `BaseException`-wrapped at the call site so a raise
in the formatter can never turn an advisory into a gate (L156 DEFECT-1).

**3. `tests/test_kalshi_trades_ticker_inventory.py`** — 30 tests. The load-bearing one is
`::test_acceptance_the_s81_shape_is_flagged_from_a_synthetic_registry`: the exact registration L292
folded by hand on 2026-08-06, now a pinned regression.

## Measured

**Committed trade tape, window CLOSED at `--max-day 2026-08-03` (L140).** L292's published numbers
re-derived on this independent code path, and they reproduce exactly:

* **39,698** prints / **42** tickers / **20** series / **1** committed day / **0** malformed lines.
* Every series is sports (`*GAME`, 18 of them) or crypto (`KXBTC` 47 prints, `KXETH` 10). Largest:
  `KXNWSLGAME` 10,156 · `KXMLBGAME` 7,756 · `KXNPBGAME` 5,462 · `KXDIMAYORGAME` 5,453.
* `KXCPI` / `KXCPICORE` / `KXNFP` / `KXGDP` / `KXFED` / `KXPCE` → **ABSENT**, all six (pinned).

**Live registry reading, and it is a fact nobody had published:** of the **2** registry rows
anchored on `tape/kalshi_trades/` (**S78**, **S79**), **0 are uncovered** and **2 are `unscoped` —
neither names a KX series token at all**. So the discipline L292 asks for could not have been
applied to either row as written: the grep has no input. Both are legitimately generic designs
(S78 "series × price-bucket × regime", S79 "wide-spread sports moneylines"), which is why
`unscoped` is its own class and not a violation count.

## Honesty caveats, stated in the tool's own output

* The universe is **committed tape**, never the platform and never the collector's capability.
  `collection/kalshi_trades.py` is ticker-scoped by construction (venue-wide density ~1e6
  prints/day), and the one committed day was a stride-13 sample of 200 of the 2,713 tickers in
  `orderbook_depth/dt=2026-08-03`. `ABSENT` reads **"unmeasurable from committed tape today"**.
* An absence measured over **one** day is a floor statement. `n_days` rides on every verdict.
* Prefix matching is deliberately generous (`KXB` matches `KXBTC`). That biases toward NOT flagging:
  it can under-report an absence, it can never invent one. A low count is precision evidence, not
  recall (L155).
* A silent advisory means every anchored row named a series and every named series has prints —
  the only reading under which silence is informative.

## What this does NOT do

It does not revive S78 or S79, does not move any registry status, does not make Q52/Q54 runnable,
and does not add a committed trade day. It bounds what the nightly idea-gen leg may REGISTER as
measured, one class of mistake, mechanically.

## Files

`scripts/kalshi_trades_ticker_inventory.py` · `scripts/invariants.py` ·
`tests/test_kalshi_trades_ticker_inventory.py` · `kb/lessons/00-lessons.md` (L292 cell moved
`UNENFORCED` → `test`; new **L299**) · `LOOP-QUEUE.md` · `kb/00-LOG.md` · this file.

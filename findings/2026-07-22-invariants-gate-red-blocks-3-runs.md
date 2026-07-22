# `invariants --full` still red on `main` — now blocking 3 consecutive research-loop runs (~8h)

- **Date:** 2026-07-22 (research-loop run, protocol v3, step 0/idle-run confirmation).
- **Scope:** Independent re-confirmation of `findings/2026-07-22-*` context behind GitHub issue
  #157 ("main is red on invariants --full since PR #153"), first filed 06:47Z this run-cycle.
  Question: is the gate still broken, and how much work has piled up unmergeable behind it?
  Answer, independently re-derived (not assumed from #157's own text): **yes, still red, byte-
  identical failure set to the one #157 diagnosed at 06:47Z, and it has now stalled 3 separate
  PRs (#158, #159, and this run's own) across ~8 hours with zero progress.**
- **Mode:** READ-ONLY diagnosis + append-only tape recovery (step 0b). No source code touched,
  no invariant relaxed, no credentials, no strategy verdict. Two-agent rule N/A (no registry
  flip, no bootstrap CI, no kill decision — ops/pipeline-health confirmation only).

## Independent re-verification

Ran both gates fresh from a clean `pip install -e ".[dev,analysis]"` sandbox, on top of
`origin/main` HEAD (`01c74de`):

- `python scripts/invariants.py --full` → **exit 2**, the same two `order_endpoints_confined`
  violations #157 named (`tests/test_polymarket_us_live.py`, `tests/test_ws_depth.py` — auth-header
  literals in test files that were never added to the invariant's exemption list when PR #153
  exempted their corresponding source files).
- `pytest` (excluding the two files that fail to *collect* — missing `cryptography` dependency,
  the second half of #157's diagnosis) → 5 failures, all in `tests/test_invariants.py`, all
  downstream of the same 2 violations (`test_real_tree_is_green` + four
  `*_never_gates_exit_code` tests whose fixtures assert `rc == 0`).
- Confirmed the failure set is **pre-existing and unrelated** to any diff a research-loop run
  could produce today: stashed this run's own tape changes and reran — byte-identical 5
  failures / exit 2 with or without the stash. This is `main`'s own steady-state, not something
  introduced downstream.

## Pileup

Three PRs now sit open, individually green, unable to merge per LOOP-QUEUE.md step 6 ("if gates
are red ... leave the PR open"):

| PR | Opened | Milestone | Status |
|---|---|---|---|
| #158 | 06:47Z | Q42 cross-venue funding join un-freeze (130→146 windows) | open, green in isolation |
| #159 | 09:23Z | L136→L138 tolerant ISO-timestamp parser | open, green in isolation |
| (this run) | ~12:1xZ | stranded-tape sweep (2,293 lines) + this escalation | open, green in isolation |

None of the three diffs touch `tests/test_polymarket_us_live.py` or `tests/test_ws_depth.py` —
the block is entirely inherited from `main`'s own state, not from anything these runs did.

## Why this run did not fix it (same restraint as #158/#159)

`scripts/invariants.py::inv_order_endpoints_confined` is a Stop-rules-adjacent safety invariant
(confines authenticated/order-capable code to `execution/kalshi_client.py`). Lesson L131
explicitly flagged this exact collision risk before it happened and said not to relax the
invariant silently. #157's own body includes a ready-to-apply fix spec (exempt the two test
files, mirroring the existing `scripts/kalshi_sign.py` exemption; add `cryptography` +
`websocket-client` to dev deps) but deliberately leaves it unapplied, calling it "a call for
Ryan, not a cloud loop." This run agrees with and preserves that judgment rather than re-deciding
it independently a third time.

## What actually happened this run (step 0b, unaffected by the gate)

Swept the newest stranded `tape/hourly-*` branch (`tape/hourly-20260722T0403Z`, ~8h old,
superset of the also-stranded `...0357Z` branch) — **2,293 genuinely-missing lines** recovered
via sorted-line-set union-append (`comm -13` against `origin/main`'s per-day files), 0 invalid
JSON, no reordering: 1,397 `orderbook_depth`, 530 `weather_books`, 332 `sports_pairs`, 17
`perp_tape`, 15 `polymarket_macro_pairs`, 2 `crypto_hourly`. This work is independent of the
red-gate block (pure tape data, touches none of the two broken test files) but is, per protocol,
still not being merged until `main` itself is green again — it will merge cleanly the moment
issue #157 resolves.

## Needs Ryan

Every research-loop run from here forward will keep finding this same wall and re-confirming it
rather than doing new work, until one of: (a) Ryan applies (or rejects) #157's fix spec, or
(b) Ryan applies a different fix. The three stalled PRs above are ready to merge (in submission
order: #158, #159, this one) the moment `main`'s gate turns green — no further research-loop
action is needed on them.

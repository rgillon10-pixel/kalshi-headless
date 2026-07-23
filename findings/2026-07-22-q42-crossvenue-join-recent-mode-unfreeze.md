# Q42 cross-venue funding join un-frozen — the Kalshi leg was consumer-side-frozen at the one-shot backfill (mirror of L127's HL freeze)

`2026-07-22` · research loop, idle-run policy (c) data-quality/joinability deep-dive · read-only + offline over committed tape · **NOT a P&L verdict, no registry change** (Q42 is a research item, not a registered strategy; same descriptive posture as Q42 part 2).

## One-line

The Q42 Kalshi↔Hyperliquid cross-venue funding join was **double-frozen** at the 2026-07-17 backfill horizon: L127 (2026-07-21) found the *Hyperliquid* leg frozen and PR #153 healed it with an incremental refresh — but the join still returned **130 windows/asset** because `scripts/q42_crossvenue_funding_join.py::collect_kalshi_prints` reads `mode="backfill"` **only**, silently ignoring the 73 ongoing `recent`-mode finalized-print captures. Reading BOTH modes (deduped on `(ticker, funding_time)`) extends the join **130 → 146 windows/asset** (span 2026-06-03T20:00 → 2026-07-22T04:00, `partial_excluded=0`) and un-freezes it going forward.

## Provenance chain (why this is fresh, not a duplicate of L127)

1. **L127 (2026-07-21):** `tape/hyperliquid_funding/` frozen at a single manual 2026-07-17 backfill, silently strangling the Q42 join (every window after 07-17 EXCLUDEd, no error). Flagged; the collector-wiring fix (candidate (a)) left as an OPEN follow-up.
2. **PR #153 (`fcc6c9b`, merged; Ryan-interactive):** wired an incremental `hyperliquid_funding` refresh. Confirmed here: `tape/hyperliquid_funding/dt=2026-07-22.jsonl` carries `mode:"incremental"` records; the first capture (02:43:22Z) backfilled 116 BTC prints spanning `funding_time` 07-17T07:00 → 07-22T02:00 — the HL gap is **healed** (`hl_hours` 1063 → 1182).
3. **This finding:** healing HL alone did **not** extend the join — and L134's own PR-#153 smoke reported the join at "130/130 windows joined, 0 partial-excluded" and treated it as healthy, missing that `collect_kalshi_prints` was still reading the backfill mode only. The Kalshi leg is frozen by a **consumer-side mode filter** — the exact mirror of L127's collection-side freeze, one layer down. perp_tape's Kalshi finalized funding prints (`record_type:"funding_rates"`) reach `max_funding_time=2026-07-22T04:00` in raw committed tape (KXBTCPERP: 346 raw prints across 1 `backfill` + 73 `recent` captures), but `collect_kalshi_prints(..., mode="backfill")` reads only the single one-shot `backfill` record.

## Numbers (all `broker_truth` — finalized venue prints, not fills)

| | backfill-only (frozen) | both modes (fixed) |
|---|---|---|
| BTC windows joined | 130 | **146** |
| ETH windows joined | 130 | **146** |
| partial_excluded | 0 | 0 |
| span | 06-03T20:00 → ~07-17 | 06-03T20:00 → **07-22T04:00** |
| Kalshi zero-fraction (joined) BTC / ETH | 0.6692 / 0.7923 | 0.7055 / 0.8151 |
| part-1 BTC clamp cross-check (0.669) | pass | pass |

Re-characterized differential (HL 8h-equiv − Kalshi print) over the fuller 146-window sample — **descriptive sizing only**:

- **BTC:** mean `+0.00003017` (≈ +0.30 bp/8h), median `+0.00007373` (≈ +0.74 bp). Regime-dependent, NOT a uniform harvest: low-|HL| tercile mean `-0.00004518`; HL-negative windows (n=10) mean `-0.00011620`.
- **ETH:** mean `+0.00008017` (≈ +0.80 bp/8h), median `+0.00010000` (≈ +1.0 bp). HL-negative windows (n=30) mean `-0.00000387`.

vs Q42 part-2's 130-window figures (BTC +0.238/+0.702 bp, ETH +0.777/+1.000 bp): the qualitative conclusion is **unchanged** — HL runs ≈+1 bp above Kalshi's clamped funding in the modal window, but the differential flips negative in the low-|HL| and HL-negative regimes, so it is a regime-dependent basis, not a durable harvest. The extension enlarges the sample and un-freezes forward growth; it does not change the (still-NOT-a-verdict) picture. Part 3 (the fee/carry model) remains BLOCKED(needs-auth).

## Redundant recompute (data-quality hygiene, per L119)

The headline un-freeze number (130 backfill-only → 146 both-mode unique `(ticker, funding_time)` windows/asset, span → 07-22T04:00) was reproduced by an independent ad-hoc dedup over the raw committed tape (not importing the join script) BEFORE the fix, and matches the fixed CLI exactly.

## Fix

`scripts/q42_crossvenue_funding_join.py`: `collect_kalshi_prints` / `analyze` now accept `mode` as a single string OR a collection; the CLI (`--modes`, default `backfill recent`) and `analyze`'s default read BOTH. Dedup on `(ticker, funding_time)` collapses a window seen in both modes to one. `mode="backfill"` semantics are unchanged (still excludes `recent`), so the existing unit test that pins that behavior stays green. New regression test `tests/test_q42_crossvenue_funding_join.py::test_collect_kalshi_both_modes_included_and_cross_mode_dedup`. Lesson **L137**.

## Gate note (pre-existing, NOT introduced by this change — ESCALATED)

`main` (`66f4d57`) is **pre-existing RED** from PR #153, independent of this change (base and branch have byte-identical failure sets):
- `python scripts/invariants.py --full` exits **2**: `inv_order_endpoints_confined` (a Stop-rules safety invariant) false-fires on `tests/test_ws_depth.py` — PR #153 exempted the sanctioned source `collection/ws_depth.py` but not its test, which contains `KALSHI-ACCESS-*` auth-header strings (and order-verb literals in absence-assertions). This cascades into `test_invariants.py::test_real_tree_is_green` + four `*_never_gates_exit_code` failures.
- `pytest` cannot collect `tests/test_polymarket_us_live.py` / run `tests/test_ws_depth.py`: a pyo3/`_cffi_backend` ABI panic from `cryptography` (a deferred optional dep; PR #153 flagged the pyproject change as deferred). Environmental — not code-fixable in this sandbox.

This run did **not** modify the Stop-rules safety invariant (working-agreement discipline: safety-surface changes are Ryan's). Ready-to-apply fix spec for Ryan / a future run: (1) exempt `tests/test_ws_depth.py` from `inv_order_endpoints_confined` (mirror the `scripts/kalshi_sign.py` full exemption — a test verifying the daemon's read-only-ness is safety-neutral); (2) add `cryptography`+`websocket-client` to the dev deps (or guard the two tests with a skip) so pytest collects. This is exactly the collision **L131** already documented and flagged to Ryan as UNRESOLVED ("MUST be settled before ws_depth.py merges to main or the gate breaks. Never relax the invariant silently.") — the prediction has now MATERIALIZED: PR #153 merged `collection/ws_depth.py` + its test, and `main`'s gate is red. No new lesson row filed (L131 owns it); re-escalated here at `Priority: high`.

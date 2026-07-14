# Q26 / S22 — OFI / depth-imbalance settlement predictor verdict: DEAD by calibration

`2026-07-14` · LOOP-QUEUE.md Q26 · registry S22 · verifier CONFIRMED (independent re-run,
sign-convention attack, hand-verified sample row) · every price below carries its source tag

## The question

Resting L2 book-imbalance (size on the `yes_bids` ladder vs the `no_bids` ladder, from
`tape/orderbook_depth/`) was hypothesized to carry information that LEADS the displayed
mid and predicts settlement — the losing counterparty being retail traders who trade the
BBO/mid without reading depth (Cont, Kukanov & Stoikov 2014's OFI mechanism, distilled this
round into `kb/quant-finance/order-flow-imbalance.md`). Tested ONLY on the two-sided,
low-frozen, high-turnover sports cells Q25's anatomy scan flagged: KBO, NPB, WNBA, MLB, UCL/
UECL/UEL soccer — not the one-sided crypto wings (structurally different, L31).

Data: `tape/orderbook_depth/` for the imbalance signal + Kalshi's free settled-markets
endpoint (`collection/sports_history.py::fetch_kalshi_settled`) pulled once and cached at
`tape/q26_settlement_cache/settlement.json` (458 settled markets, `pulled_at`
2026-07-14T09:25:53Z, within the ~60-day L11 retention window) for the settlement outcome —
same games, an ex-post join over the depth tape's OWN window per L50 (the fix for S21's
disjoint-window death).

## Verdict: DEAD by calibration (verifier-CONFIRMED)

**Gate 1 (settlement-join adequacy) PASSED, well clear of the floor.** 599 markets in the 7
target series' depth tape; 450 settled-joined (8 cached settlements were `result:"scalar"`,
correctly excluded — a binary-outcome probe must filter `result ∈ {yes,no}` explicitly, not
assume settled ⇒ binary); 450 markets had a valid pre-close (`ttc>0`) last snapshot; **205
distinct joinable GAMES**, 20× the 10-game floor. Per-series games: MLB 95, NPB 34, UECL 26,
WNBA 23, UCL 14, KBO 13, UEL 0 (its depth events are 07-16 fixtures, not yet settled — honest
zero, not padded). L50's ex-post-join fix is positively confirmed here: unlike S21, the join
death did not transfer.

**Gate 2 (calibration precheck) is the decisive hard kill.** Overall the imbalance signal's
hit rate already trails the mid (0.7466 vs 0.7697, n=446/317). On the **disagreement subset —
the actual trade population, n=86 rows across 81 games where imbalance and the mid pointed to
different sides — imbalance hit only 0.2791 vs the mid's 0.7209.** Brier score confirms the
same ordering (disagreement-subset: imbalance 0.3099, mid 0.1953). Per the milestone's own
binding spec, this is a hard stop: gates 3 (taker-lift P&L) and 4 (block-bootstrap CI) were
correctly never computed — no bootstrap, no CI, nothing to report there.

### Why 27.9% and not ~50% — checked explicitly, not a sign bug

The verifier's sharpest attack targeted exactly this: a disagreement-subset hit rate this far
below 50% is the signature you'd also see from a **sign-flipped signal that's actually a
strong contrarian predictor** — worth ruling out before writing DEAD. It isn't that. On the
disagreement subset `imb_side` and `mid_side` are opposite by construction (both directional,
`imb_side != mid_side` is the subset's defining filter), and `hit()` uses the identical
`settled_yes` convention for both — so on this subset **`imb_hit ≡ NOT mid_hit`, exactly**
(0.27906976744186046 + 0.7209302325581395 = 1.0 to full float precision, confirmed against
raw imb_correct=24/mid_correct=62 sum=86). Flipping the imbalance sign on this subset would
just reproduce the mid's own call — zero independent edge either direction. The 28% is not an
independent measurement of a contrarian signal; it is arithmetic complementarity. The honest
reading: when a raw resting-size imbalance contradicts the market's own displayed price, the
market wins 72% of the time. The mid already prices in whatever the depth ladder shows.

Verifier additionally hand-verified one disagreement row end to end against raw tape
(`KXKBOGAME-26JUL090530KIALOT-KIA`: last pre-close snapshot `yes_bid_size=2692`,
`no_bid_size=10833` → imbalance says "no"; `best_yes_bid/ask 0.62/0.66` → mid says "yes";
`result=yes` — mid right, imbalance wrong, matching the aggregate pattern) and confirmed
`load_last_preclose_snapshots` genuinely selects the latest snapshot strictly before close
(`ttc>0`), not the closest-to-open or a post-close read. `distinct_games_joinable=205` vs
`disagree_games=81`/`disagree_n=86` is explained cleanly: exactly 5 games contribute a
disagreement row from both of their mirror markets (81+5=86), no double-count beyond the
legitimate two-outcome mirror structure Kalshi's own market design produces; the bootstrap
unit (had gates 3/4 been reached) is `event_ticker` (game-level, L6), not the row.

Time-to-close robustness (S9-family cadence honesty check): the kill holds at every ttc cut
— ttc≤1h (29 games) imbalance 0.281 vs mid 0.719; ttc≤2h 0.250 vs 0.750; ttc≤6h 0.256 vs
0.744; the full n=450 sample median ttc is 0.84h (~51 min). This rules out DEAD-by-cadence
(a coarse-capture washout, S9/S10-family) as the actual mechanism — the signal is simply
wrong, not under-powered or stale.

## Registry

S22 flipped `idea → dead ✗` in `kb/strategies/00-index.md`. Still 0 proven edges. This closes
the OFI/depth-imbalance direction on Kalshi's two-sided sports books as currently instrumented
(displayed BBO/mid already integrates the depth ladder on these high-churn cells).

## Gates

`pytest -q`: 817 passed (796 prior + 21 new). `python scripts/invariants.py --full`: green
(only the standing non-gating L25/L29 stray-directory advisory, unrelated). No execution code
outside the sanctioned paper tier; no network calls beyond the one documented, cached,
re-runnable settlement pull; no credentials.

## Files

- `scripts/q26_ofi_depth_imbalance_probe.py` — the probe (4-gate structure, offline-first
  against the cache, `--refresh-cache` for a fresh live pull).
- `tests/test_q26_ofi_depth_imbalance_probe.py` — 21 offline unit tests, including a
  hand-verifiable disagreement-subset case.
- `tape/q26_settlement_cache/settlement.json` — cached settlement snapshot (re-runnable
  offline by any future verifier without a fresh network call).

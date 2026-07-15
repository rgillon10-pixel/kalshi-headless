# Q21 idea-generation round (2026-07-15, kalshi-edge-hunter): 3 proposed, 0 survived idea-stage

`2026-07-15` · kalshi-edge-hunter nightly run · LOOP-QUEUE.md Q21 · two-agent rule applied at
the IDEA stage (independent `verifier` attack before any registration) · **0 registry rows added**

## Why the round fired

Eligible (TODO, unclaimed, unblocked) research items in the queue = **0** (< 2 → Q21
re-eligibility trigger). Q14/Q15 BLOCKED (fedwatch-scrape / no-live-market), Q17 RESERVED
(Ryan-review), Q24 DONE (S21 dead), Q19's remaining per-event legs are TIME-GATED on the
WC-semi/WC-final/FOMC burst windows, Q26/Q27/Q28 all DONE-DEAD (2026-07-14). So the pipeline
needed restocking.

## The three candidates and their kills

Each was proposed with a named mechanism/counterparty, an already-collected-or-free data source,
a falsifiable gate + kill condition, and a "why it survives its nearest dead cousin" argument.
Each was then handed to an independent `verifier` agent to attack **before** registration. **All
three were killed at the idea stage** — the two-agent discipline working as designed: a killed
idea costs one idea-gen round and saves a full wasted probe run.

### S25 — Post-release within-Kalshi econ-ladder staleness (known-outcome pickoff) → KILL-AT-IDEA

*Mechanism:* at the 12:30Z CPI print the outcome is public instantly but the Kalshi ladder was
hypothesized to reprice over seconds-to-minutes, leaving a now-certain bucket's YES ask below its
$1 payout (net fee) to buy, or a now-worthless bucket's YES bid above 0 to sell. Single-venue.

*Kill (decisive):* **the resolving-month ladder settles AT the print — it is gone before the
outcome is public.** `KXCPI-26JUN`/`KXCPICORE-26JUN`/`KXCPIYOY-26JUN` carry `close_time`
12:25:00Z / 12:29:00Z (ahead of the 12:30Z release) and vanish from `tape/econ_prints/dt=2026-07-14.jsonl`
at 12:28:59Z; **zero** post-12:30Z records contain any `-26JUN` event. The "100 records in the
12:30–12:49Z window" are all forward months (`-26JUL`/`-26AUG`/…) — a different object whose
outcome the June print does not determine. Kalshi closes the market ~5 min early precisely to deny
this pickoff. Also reproduces the S10 1¢-YES→$1.00-NO mirror wall on the last pre-close near-certain
buckets (no fillable fade). Structural DOA, not a data-collecting restocker (FOMC Jul 29 will halt
the same way). → **lesson L61.**

### S26 — Polymarket-anchored single-venue Kalshi macro convergence → KILL-AT-IDEA

*Mechanism:* use Polymarket's more-liquid macro book as a free fair-value anchor (à la S7's
DraftKings de-vig); when Kalshi's normalized bucket ask diverges from Poly's implied prob by more
than the Kalshi taker fee + overround share, take only the Kalshi side toward the anchor and hold
to convergence. Single-venue (Poly never held → claimed escape from S17's cross-venue rail risk).

*Kill (decisive):* the entry condition IS reachable (19.8% of records clear it — the "gap always <
overround+fee" attack does NOT kill it), but it clears **for the wrong reason**. On the thin
far-dated KXFEDDECISION buckets the Kalshi yes bid-ask spread is median 9¢ (up to 30¢), and in
**62.6%** of entry-met records the Polymarket anchor sits **inside** Kalshi's own bid-ask — so the
"divergence" is Kalshi's half-spread vs Poly's tight ask; Kalshi's true mid already agrees (L62).
For the ~37% where Poly is genuinely outside, capturing it needs either a full Kalshi round-trip
(~9¢ spread + 2 taker fees, dwarfing the $0.01–0.04 durable gap S17-burst measured) or a
hold-to-FOMC on a single unhedged bucket = a directional macro bet (S2/S16 family; L63). And the
gate (block-bootstrap of *convergence* P&L) is un-runnable on committed tape: 0 of the 3 tracked
meetings have resolved (earliest Jul 29). Provenance is clean (Poly `real_ask` is a legitimate free
anchor) — it dies on mechanism + reachability. → **lessons L62, L63.**

### S27 — Macro-print overshoot fade within-Kalshi (behavioral) → KILL-AT-IDEA

*Mechanism:* the Kalshi ladder's initial repricing at a print overshoots the settled distribution
(retail chases the headline before core/revisions/guidance nuance sinks in) then partially
retraces; fade the spike. Survival claim vs dead cousin S24 (near-close sports fade, DEAD by
round-trip): a macro surprise moves a bucket 10–40¢, so the retrace can plausibly clear the ~7¢
round-trip, unlike a routine in-game event's ~0.7¢ reversal.

*Kill (decisive):* same close-before-print structure as S25 — the June ladder that actually settles
on the print vanishes at 12:28:59Z, so there are **zero** post-print observations of the object you
would fade (n=0 for the mechanism, not the assumed n=1). The forward ladders that ARE present show
no print spike (KXCPI-26JUL mid 0.485→0.485→0.475 across the print) and carry a **median 0.88
yes-spread (half-spread 0.44)** — the fade would need to clear ~$0.88 + 2×0.07, worse than S24's 7¢
hurdle. A bigger headline jump does not imply a bigger *absolute* retrace (S24's ≥2¢ jumps retraced
only ~0.7¢). And `captured_at` is a single pass-level stamp at ~60s spacing, so a within-minute
overshoot-then-retrace is structurally unresolvable (L57) — any "retrace" is a flapping-ask
artifact. This is the L58/S24 failure mode (behavioral reversal real in mid units, un-fillable
against the round-trip) on econ tape. → covered by **lesson L61.**

## Outcome

- **0 candidates registered.** No new rows in `kb/strategies/00-index.md`; still **0 proven edges**.
- **3 lesson candidates → L61/L62/L63** in `kb/lessons/00-lessons.md` (all ledger-only —
  proposal/probe-stage design gates, not statically assertable invariants).
- The queue stays thin; the next research-loop firing will be an IDLE RUN per the v3 idle-run
  policy (convert an UNENFORCED lesson, prep the next gated probe, deep-dive a tape family, or
  re-prep Q21). This is the honest state of a well-mined surface: three sound, novel-shaped
  candidates each died to a real structural fact, not to a lazy dead-cousin match.

## Verification note (two-agent rule at idea stage)

Each candidate was attacked by an independent `verifier` agent that re-ran the relevant tape
(`tape/econ_prints/dt=2026-07-14.jsonl`, `tape/polymarket_macro_pairs/dt=2026-07-14.jsonl`) and the
nearest dead-cousin findings (S10, S17-burst, S24, S9-resolution) before returning a verdict. All
three returned KILL-AT-IDEA with the tape-grounded reasoning recorded above. No candidate reached
registration, so no registry status was changed and no probe was built.

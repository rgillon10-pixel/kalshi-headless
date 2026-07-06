# Q12 — S17 Fed-decision leg: first cut (2026-07-06)

**Status:** data-collecting (S17 flipped from `idea`). Not a verdict — one live snapshot,
descriptive only.

## What was built

`collection/polymarket_pairs.py` gained a second discovery family, `run_fed_decision()`,
retargeting the same discipline `discover_kalshi_round_markets`/`discover_polymarket_round_events`
already proved out for World Cup rounds (Q8/S9) at Fed rate-decision meetings, which — unlike
the World Cup — don't die on July 19.

**Kalshi side.** `KXFEDDECISION-<yymon>-<H|C><bps>` markets. Each open meeting-month event
(e.g. `KXFEDDECISION-26JUL`) carries exactly 5 markets that partition the outcome space:
cut >25bps, cut 25bps, no change, hike 25bps, hike >25bps. The ticker's bps suffix is
*not* trusted for matching semantics — it uses the literal string `"26"` as a stand-in for
">25" rather than an actual 26bps value (confirmed live 2026-07-06). Instead,
`parse_kalshi_fed_ticker` reads the verb/magnitude/month/year straight from the market's own
title text ("Will the Federal Reserve Hike rates by >25bps at their July 2026 meeting?"),
the same "confirm structurally, don't trust the ticker suffix alone" lesson the Q1
reconciliation note already carries.

**Polymarket side.** "Fed Decision in `<Month>`?" events, discovered via `/public-search` with
`limit_per_type=20&events_status=active` (the default `limit_per_type` only returned 5 hits,
too few to see beyond the nearest meeting). Each event carries the same 5-bucket partition
("50+ bps decrease" / "25 bps decrease" / "No change" / "25 bps increase" / "50+ bps
increase"), parsed via each question's own text ("...after the July 2026 meeting?") for month
+ year, and the `groupItemTitle` for the bucket. Two other query hits were deliberately
excluded rather than guessed at: multi-month bundle events ("Fed decisions (Jul-Oct)") and
an unrelated market shape ("How many dissent at the July Fed meeting?") — neither is the
same one-meeting/5-bucket partition as Kalshi's event, so matching them would mean guessing.

**Matching.** Exact key = (meeting `YYYY-MM`, bucket). Same match/unmatched/ambiguous
discipline as the WC-round leg — a pair either matches 1:1, is recorded unmatched, or (if
Polymarket somehow returned two candidates for one key) is recorded ambiguous, never guessed.

**Completeness metric — the one real design decision this run made.** Kalshi lists
`KXFEDDECISION` meetings roughly 18 months out (confirmed live: open events ran to January
2028), but Polymarket only creates a meeting's event closer to it (this run found live
events for July/September/October 2026 only). Grading completeness against "every open
Kalshi market must match" — the metric the WC-round leg correctly uses, since Kalshi only
lists near-term rounds there — would make this leg report `completeness_ok: False` forever,
which would poison `hourly_pass.py`'s combined completeness signal with a structural
non-issue rather than a real one. Instead, completeness here is judged against Polymarket's
side: every market Polymarket is *actively quoting right now* either matched 1:1 or is
accounted for as ambiguous. `unmatched_kalshi` (Kalshi's forward calendar Polymarket hasn't
caught up to yet) is still recorded in full, it just doesn't gate. A genuine integrity break
— a Polymarket market this pass failed to pair with any Kalshi ticker — surfaces as
`unmatched_polymarket` and does gate. Both directions are covered by dedicated unit tests.

## Wiring

`run_fed_decision()` writes to its own tape family, `tape/polymarket_macro_pairs/`, kept
separate from `tape/polymarket_pairs/` (WC rounds) since it's a structurally different
record shape (`meeting`/`bucket` instead of `round`/`team`) — mixing them would force any
downstream analysis to branch on shape anyway. Wired into `collection/hourly_pass.py` as a
fourth cross-venue sub-pass (`polymarket_macro_pairs`), same fault-isolation +
completeness-AND discipline as the other three sub-passes.

## Live pass (2026-07-06, four snapshots during this run's dev/smoke cycle)

- 65 open Kalshi `KXFEDDECISION` markets (13 meeting-months × 5 buckets, July 2026 → January
  2028).
- 15 Polymarket Fed-decision markets found live (July/September/October 2026 × 5 buckets).
- **15/15 matched**, 0 ambiguous, 0 book-fetch errors, `completeness_ok: True`.
- `price_gap_yes_ask` (Kalshi `yes_ask` − Polymarket `best_ask`) ranged **−3¢ to +15¢** across
  the 15 pairs this run observed — widest gap on 2026-10 `no_change` (Kalshi 83¢ vs
  Polymarket 68¢). One snapshot, descriptive only — not a lead-lag or mispricing claim.

## Remaining for full DONE

- **CPI/inflation leg deliberately deferred.** Kalshi's CPI ladder (`collection/econ_prints.py`)
  prices a cumulative "≥ threshold T" (nested, not a partition — see that module's own
  docstring), while Polymarket prices an exact bucket (confirmed live: "0.2%", "0.3%", ...,
  "≥0.9%"). Pairing those two shapes 1:1 as `real_ask` the way the Fed-decision leg does would
  be wrong — it would require differencing adjacent Kalshi thresholds into a derived
  probability, which is a model output, not a same-question fillable pair. That transform is
  real, useful future work, but faking a same-question pairing here would violate Hard Rule
  #3's spirit (never treat a derived quantity as directly fillable). Left as a named gap, not
  built.
- Accumulate hourly snapshots (already wired), then run a lead-lag cross-correlation once
  enough history exists — same shape as `scripts/s9_leadlag_probe.py`, generalized to this
  tape family once it has enough captures.
- S17's own gate (≥5 matched live-book pairs/month) is already cleared by this one pass
  (15 matched); the remaining test is the lead-lag CI itself, once there's enough history to
  characterize an information shock (the next FOMC meeting is a natural one to watch for).

# Q21 idea-generation round — 2026-07-19 (kalshi-edge-hunter, nightly)

**Trigger:** re-eligibility fired again — eligible (TODO/unclaimed/unblocked/**gate-open**)
research items = **0**, verified by FILE SHAPE (L25), not path existence:

- Q19 (S17 burst studies) — per-event; WC final kicks off tonight 19:00Z, burst tape not yet
  captured; FOMC Jul-29. The lead-lag/shock harness (`scripts/s17_leadlag_probe.py`,
  `scripts/s9_shock_eventstudy.py`) is already built — tonight's run only executes.
- Q36 (weather revival) — gated ~Jul-22 naive / ~Jul-23+ clean-day; `tape/weather_books/` holds
  4 calendar-days (07-16 partial, **07-17 the only clean hourly day**, 07-18 VPS-broken, 07-19 in
  progress). Also design-blocked: its settlement-basis join needs an intraday KNYC actual that the
  daily `weather_actuals` feed does not carry (see 2026-07-18 audit flag #3).
- Q37 gated ~Aug-05 (21 summer contract-days); Q43 gated ~Jul-23/24 (`tape/perp_tape/` 3 thin
  days, 07-18 VPS-stalled to 238 lines); Q32/Q33/Q35-build blocked on Polymarket US credentials;
  Q42 part 3 BLOCKED(needs-auth); Q24/Q29/Q30/Q31/Q34 DONE-DEAD.

**Bar unchanged:** still **0 proven edges** (block-bootstrapped 95% CI > 0 at `real_ask` net of
fees). A round restocks the hypothesis pipe; it does not move the bar. Next free number after the
07-18 round consumed S38/S39/S40 was **S41**. Target 3–5 defensible candidates; every proposal
attacked by an independent `verifier` BEFORE registration (two-agent rule at the idea stage);
register only survivors, never pad to quota. This is the **5th round in a week** (07-13/14/15/16/18),
four of which registered 0 — the binding constraint remains generation surface, not cadence, and no
new tape surface has landed since the 07-18 round.

---

## S41 — Full-universe SIMULTANEOUS within-event overround-underflow free-money scan

**Mechanism / counterparty.** In a complete mutually-exclusive-and-exhaustive (MEE) bracket set
(one `event_ticker`), buying every bracket's YES at ask guarantees exactly $1 at settlement. If
Σ(`yes_ask` over all brackets) + total per-contract fees < $1.00 at a **single shared `capture_id`**,
that is a locked static arb. Counterparty: a market maker's stale/crossed quote mid-requote. The
novelty claim was that `anomaly_sweep.py::check_bracket_arb` (which already does exactly this math via
`core.pricing.bracket_sum` + `true_arb_edge` + `fee_per_contract`) has NEVER been pointed at
`tape/universe_sweep/` — the full-universe (~20k markets/pass, 4×/day) census where all legs of one
pass share one `capture_id`, a genuinely simultaneous cross-section (unlike forward-filled ladder
tape's S33 asynchrony artifact or Q31's frozen-quote artifact).

**Data.** `tape/universe_sweep/` (`real_ask`, `event_ticker` grouping, `yes_ask` + `yes_ask_size`
touch depth, shared `capture_id`).

**Falsifiable gate.** Per (`event_ticker`, `capture_id`) complete MEE set: Σ`yes_ask` + Σfee vs
$1.00; require ≥1 set below $1 net of fees with every leg fillable (`yes_ask_size` ≥ 1). **Kill:** no
complete set ever prices below $1 net of fees with fillable depth.

## S42 — Perp funding-clamp reversion carry

**Mechanism / counterparty.** Q42 confirmed a genuine ±1bp funding dead-band on Kalshi perps
(76.2% exact-zero). Thesis: when true carry pins funding at the clamp edge (0), the next print
over-corrects (mean-reverts), tradeable by holding the perp. Counterparty: perp holders mispricing
the clamped funding. **Data:** `tape/perp_tape/` (`broker_truth` funding prints).

---

## Verifier attack (two-agent rule, idea stage) — RESULTS: 2 proposed, **0 registered**

Both candidates attacked by an independent `verifier` that re-ran the actual committed tape. **Both
KILL-AT-IDEA** — a clean sweep, same outcome as the 07-15/07-16/07-18 rounds. Still **0 proven
edges**. S41/S42 consumed → **next free = S43**.

**S41 — KILL-AT-IDEA.** The verifier computed, over `tape/universe_sweep/dt=2026-07-19.jsonl`
(20,000 rows, single `capture_id` `20260719T010354Z`), the Σ`yes_ask` distribution per
(`event_ticker`, `capture_id`) multi-market group (n=2,441): min 0.0000, **median 0.0000**, mean
0.5192, p75 1.0000, p95 2.0000, max 17.16. **1,565 groups have Σyes_ask < $1.00, but ZERO are
fillable** (all-legs `yes_ask_size ≥ 1 ∧ yes_ask > 0`); **1,537 of the 1,565 are all-zeros** — the
sub-$1 "sum" is the *absence of any resting YES offer*, not a crossed book. Treating a `yes_ask=0.0`
no-offer leg as a $0.00 buyable fill is the exact pt1 / prime-directive violation (a nominal price is
never a fill). Three independent kills, any one fatal: (1) **file-shape (L25/L29)** —
`universe_sweep.v1` has NO `strike_type`/`floor_strike`/`cap_strike`/`yes_ask_dollars` fields, so
`check_bracket_arb`'s `_segment_bounds()` exhaustiveness proof cannot run at all; the "first
simultaneous surface" novelty is moot because the surface lacks the fields the check needs.
(2) **truncation (L96)** — every pass caps at exactly 20,000 markets over an >80k universe, so any
bracket set straddling the cap boundary is split mid-event; exhaustiveness is unprovable in
principle. (3) **duplication** — registering it re-points existing infra at a field-incompatible
tape and adds nothing.

**S42 — KILL-AT-IDEA.** The reversion thesis is directly contradicted by the funding-print sequence
in `tape/perp_tape/` (136 unique prints/ticker back to 2026-06-03 — deeper than the "3 thin days"
worry): after a zero print, the next print is **zero again** with probability BTC 78/92 = 85%,
ETH 94/108 = 87%, SOL 121/127 = 95% — the dead-band is a **persistent/near-absorbing state, not a
coiled spring**; a clamped zero predicts another zero, not an over-correction, so there is no
reversion signal. Nonzero rates when they occur are ±0.001 max. Independent second kill: the
mechanism requires **holding a leveraged PERP** (funding + mark-to-market P&L), entirely outside the
project's binary-market + `real_ask`/`no_ask` fill discipline — there is no perp fill model (same
"signal-real-but-unfillable-within-our-discipline" pattern as L58). Also duplicates Q43's queued
(gated) perp-vs-binary consistency territory.

## New lesson candidate (surfaced by the S41 attack) → ledger L105

`tape/universe_sweep/` (schema `universe_sweep.v1`) is a **top-of-book census WITHOUT strike-ladder
fields** (`strike_type`/`floor_strike`/`cap_strike`/`yes_ask_dollars` all absent) — it **cannot feed
`anomaly_sweep.check_bracket_arb`**, and its sub-$1 Σ`yes_ask` groups are ~98% all-zero no-offer
artifacts (0/1,565 fillable on 07-19). This restates the L96/S38 illiquidity floor (fillable
population ~0.56–1.05%, `yes_ask_size==0` on ~96%) for the full-universe simultaneous census: a
crossable complete-set book never appears there, and a nominal sub-$1 sum is the absence of offers,
not an arb. Kills any future "point the anomaly sweep at the universe census" proposal at the idea
stage.

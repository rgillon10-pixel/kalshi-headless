# Q21 idea-gen round — 2026-08-03 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 0 REGISTERED.** Round #21. Consumes S72/S73/S74 for provenance → next free **S75**.
Still **0 proven edges.** A DEAD verdict at the idea stage is a success, not a failure.

## Why the round fired

Full Q0–Q50 file-shape rescan (L25), reading each item's LATEST status (several carry a stale
`TODO` above a later `DONE`/`CLOSED`): **0 eligible TODO/IN-PROGRESS** — the same finding as every
rescan for two-plus weeks. Every item is DONE, credential/auth-BLOCKED (Q14/Q15/Q32/Q33/Q35-build/
Q47), calendar-gated (Q19/Q48 burst events fired; **Q37 at 20/21 real summer contract-days by file
shape, opens ~08-04**), or density-inadequate (Q36/Q42/Q43 — VPS `:23` collector dead since
2026-07-22, now 11+ days per PR #277). The apparent-TODO items were each re-confirmed NOT eligible
by file shape: **Q50** reads `TODO` at its topmost status line but was verifier-CONFIRMED CLOSED on
2026-08-01 (S68 stays `dead ✗`) — the TODO marker is stale (L152-class); Q9/Q11/Q12/Q16/Q23/Q24/Q27
sit on dead or superseded strategies. Fewer than 2 eligible → the Q21 standing replenishment
condition is satisfied.

## Posture: last-corner probes on frozen tape, not re-skins

After 21 rounds and 20+ dead strategy families, the two structural walls are fully mapped and
unchanged:
- **WALL-A — taker → overround** (dead S1/S5/S7/S52; sharpened by round #20's S70, a CI-falsified
  kill on the lowest-overround ≤3¢-spread game subset).
- **WALL-B — maker → unmeasurable fill** (dead S6/S13/S14/S23/S68 — **no committed tape family
  carries a trade/volume/last-print field**, so a maker fill-sim over `tape/orderbook_depth/` cannot
  distinguish a cancel from a trade and adverse selection is unmeasurable; L68/L106/L253/L255).

Each of the three candidates was built to route around BOTH walls using only already-collected tape
(no new data is possible — VPS dead 11+ days, no new family since). An independent `verifier` agent
attacked all three on committed tape BEFORE any registration (two-agent rule at the idea stage) and
returned **KILL / KILL / KILL**.

## The three candidates

### S72 — LIP-window fee-halved complete-ladder coherence arb on weather ladders → KILL
Mechanism: during the ~54–60 min post-listing Liquidity Incentive Program window Kalshi charges
50%-off (`discount_factor_bps=5000`, confirmed by `scripts/weather_fee_schedule_probe.py` over
10,372 weather programs), so S33's Σ(leg `real_ask`) < $1 complete-ladder coherence arb has a halved
6-leg fee floor and might clear net > 0. Nearest dead cousin S33.
**Kill (verifier, two independent walls neither of which fee-halving touches).** (1) The tape cannot
observe the LIP window: `tape/weather_books/` captures at **7 snapshots/day (~3 h cadence)**, so a
54–60 min post-listing window cannot be located, let alone measured for the "≥60 s duration" gate.
(2) **S33 did NOT die on fee.** `reports/ladder_coherence_summary.json` (`fee_rate: 0.07`, full
taker) already had **14 executable runs** clearing the *full* fee (`executable_magnitude_dist.mean
= 0.182`, ci95 [0.114, 0.256]); S33's DEAD verdict came from `admissible: false, n_opposing_units:
0` (the L249 one-sided-support definitional cut) layered on the **depth×duration executability
wall** (only 14 of 221 net-positive runs cleared the 10-contract floor). Halving the fee cannot
manufacture opposing units, raise the executable count, or create the missing LIP observations —
S72's founding premise ("S33 used the full fee and might clear if halved") is simply false.

### S73 — Perp-anchored maker on near-money crypto_hourly, orderbook_depth touch-fill → KILL
Mechanism: use `perp_tape` (delta-1, `real_ask`/`real_bid`) as a free fair anchor; rest a maker
order on the near-money `crypto_hourly` bracket the perp says is cheap (restricted to the two-sided
band, not S71's OTM 200%-overround strip); fill = `orderbook_depth` touch with an explicit
`OPTIMISTIC_FILL` cap. Nearest dead cousins S71 (taker version) / S68 (maker-fill).
**Kill (verifier): WALL-B, verbatim.** `tape/orderbook_depth/` keys carry `best_*`/`*_bids`/`depth`
but the trade/volume/last-print field search returns `[]` — a resting-depth snapshot with no trade
prints cannot distinguish a cancel from a trade, so the "OPTIMISTIC_FILL touch" model IS the
unmeasurable-adverse-selection kill of S68. "Near-money not OTM" changes the signal, not the fill
primitive. (Corroborating, not needed: of 42,086 crypto rows only 925 = 2.2% are two-sided in-band —
the near-money bracket is also thin.) The only trade-bearing escape is Q47 `orderbook_delta`
(BUILD-DONE, Ryan-gated on an API key).

### S74 — Summer weather maker mid-miss calibration fade on repaired weather_actuals → KILL
Mechanism: using the #270-repaired `tape/weather_actuals/` (`broker_truth`, 87.4% settlement join),
find where Kalshi's terminal mid systematically misses realized settlement on summer daily temp
ladders and rest a maker order to fade the miss. Nearest dead cousins S1/S5 (weather taker) / Q37.
**Kill (verifier): duplicate-plus-WALL-B.** It is materially the same cell as the already-built
`scripts/q37_weather_summer_makerno_probe.py` (SUMMER × MAKER, gate opens ~08-04) — a signal-selection
tweak on the identical execution primitive over the identical tape. And that tape hits WALL-B:
`weather_books` carries no trade/volume field (Q37's own docstring says the fill is
"UNCONSTRUCTIBLE here," which is exactly why Q37 is PROBE-PREP, not a verdict). `broker_truth`
settlement fixes the *fair-value* input, not the *fill* input — the wall is on execution, not signal.

## Lesson candidate (deferred to kb-distiller — prose note here to avoid a ledger merge conflict)

**Fee-discount ideas must first prove the object died on FEE, not on executability/admissibility.**
S72 assumed a 50%-off LIP fee could revive S33, but `reports/ladder_coherence_summary.json` shows
S33's executable runs already cleared the full 0.07 fee (mean 0.182, ci95 [0.114, 0.256]); death was
the L249 no-opposing-unit definitional cut plus the 14/221 depth×duration wall. A fee lever cannot
move an executability/admissibility wall. Pair with a cadence pre-check (L28 family): confirm the
target window (LIP ≈1 h) is observable in the tape's snapshot cadence (`weather_books` = 7 snaps/day,
~3 h) before proposing any within-window probe.

## What stays true

The binding constraint that has held all month is unchanged and this round is its cleanest
confirmation yet: **idea capacity is not the limit — the data surface is.** Both walls are mapped,
and the one tape family that would break the maker-fill wall (a trade-bearing feed) is exactly the
**Q47 `orderbook_delta` WebSocket daemon — BUILD DONE, activation Ryan-gated on a working API key.**
Until that or a comparable trade-print surface lands, further idea-gen rounds will keep returning
KILLs on the same two walls. Consumed S72/S73/S74 → **next free = S75.** Still **0 proven edges.**

## Price source tags

All candidate re-derivations by the verifier used `real_ask`/`real_bid` (fills), `broker_truth`
(settlement), `midpoint` (controls); fees via `core.pricing` (taker 0.07 / maker 0.0175). No
synthetic price used as a fill. Tape read: `tape/weather_books/`, `tape/weather_actuals/`,
`tape/orderbook_depth/`, `tape/crypto_hourly/`, `tape/perp_tape/`; artifact
`reports/ladder_coherence_summary.json`.

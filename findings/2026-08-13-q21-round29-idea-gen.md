# Q21 idea-gen round #29 — kalshi-edge-hunter nightly 2026-08-13

**Run:** kalshi-edge-hunter nightly, 2026-08-13 ~04:15Z UTC. **Trigger:** eligible queue count < 2
(full Q0–Q56 file-shape rescan, L25 — each item's LATEST status: **0 eligible TODO/unclaimed/unblocked**;
7th consecutive idle-adjacent run; Q56 done, Q52/S78 + Q54/S79 data-gated `collect-and-revisit`,
everything else DONE / cred- or burst-gated / on a dead strategy) → Q21 round required per the
edge-hunter spec.

## Surface note (the binding constraint, unchanged since round #25)
`tape/kalshi_trades/` — the only genuinely-new lane this year, the one that enabled S78/S79 — is
**byte-frozen at 6 backfill days (last `dt=2026-08-03`; the collector is Ryan-key-gated, Q47/Q51).**
Rounds #25–#28 worked this same frozen tape. Every *other* fresh-flowing family
(`crypto_hourly`, `perp_tape`, `hyperliquid_funding`, `orderbook_depth`, `universe_sweep`,
`sports_pairs`, `weather_*`, `polymarket_*`) is foreclosed by a mapped wall (WALL-A taker-into-overround;
WALL-B no-trade-field-on-`orderbook_depth`; flat-maker-fee > spread; funding dimensionally negligible;
crypto_hourly hollow-book / 200% overround). So this round deliberately reached PAST the frozen
sports/trade surface into three corners a prior round had not attacked, each with a named
counterparty and an explicit escape from its nearest dead cousin.

## Outcome
Three NEW falsifiable S-candidates (S82/S83/S84) proposed by the producer (main context). An
independent `verifier` subagent attacked each against committed tape BEFORE registration (two-agent
pre-registration discipline). **0 of 3 survived — all KILL on directly re-derived tape facts.** A
0-registration round with honest verifier refutations is a valid outcome; **no S-numbers are burned**
on a kill (round #27 precedent): next free stays **S82**. Still **0 proven edges.**

| cand | name | verdict | load-bearing tape fact (verifier-rederived) |
|---|---|---|---|
| **S82** | Cross-sectional perp-funding DISPERSION → BTC/ETH RELATIVE hourly-binary directional taker | **KILL (magnitude + doubled overround)** | Over n=1042 aligned BTC/ETH funding hours (`q42_hl_funding_cache`), `\|BTC−ETH\|` funding max **3.607e-05/hr** ⇒ max **$2.16** BTC drift over the 1h settle horizon vs a **$100** bracket — **~46× too small** to move which bracket settles (the S76/magnitude wall, unmoved: a difference of two ~1e-5 rates is still ~1e-5, and ETH funding is clamp-pinned at +1.25e-05). And the RELATIVE form makes it WORSE: crypto_hourly has no directional binary, so a "directional" bet is synthesized from the range ladder and holds BOTH legs → it eats the **SUM** of two overrounds (median `bracket_sum` BTC **2.875** ≈187%, ETH **4.025** ≈302%), not a netted-down cost. WALL-A doubled + S76. |
| **S83** | Perp-anchored DISAGREEMENT taker on crypto_hourly near-money | **KILL (overround swamps + no fill + anchor not independent)** | On `KXBTC-26JUL3121` (bracket_sum 2.870) the modal near-money bracket quotes **yes_ask=0.84** vs overround-normalized fair **0.293** — taking YES **overpays by 0.547/contract**, so a disagreement edge would have to exceed ~55¢ (WALL-A). crypto_hourly has **no size field** and OTM legs pin `yes_bid=0` (hollow book L88/L168) → the taker fill is unverifiable. And the perp anchor is **not independent**: the perp mark is `broker_truth` on the SAME crypto spot that settles the Kalshi binary, so "perp-implied − binary-mid" is one underlying disagreeing with itself (basis noise), not an external fair value — the escape-vs-S53 premise collapses. |
| **S84** | Cross-venue macro DISLOCATION taker exploiting Kalshi's delisting lag vs Polymarket | **KILL (sub-L41 n + delist-at-decision + non-fillable leg)** | `polymarket_macro_pairs` is entirely `fed_decision`, 5 meetings, but only **ONE has settled inside the tape window** (2026-07 FOMC; 09/10/12/27-01 still open) — ~1 independent unit ≪ the L41 10-floor. On `dt=2026-07-29` the decided `KXFEDDECISION-26JUL` shows **50 pre-release records, 0 post-release** — Kalshi delists AT the decision (L231), so the post-decision window has **zero Kalshi observations** to dislocate against. The only still-listed leg is Polymarket, and on our tape that is the **INTERNATIONAL CLOB, not Ryan's fillable Polymarket US** (L57/L63) → a single-venue directional bet, not arb. Restricting to `terms_equivalent=true` (816 records), the largest net-of-both-fee gaps are **0.081/0.071/0.061**, all ordinary cross-venue basis on the UNSETTLED 2027-01 meeting, not a post-decision residual (re-confirms S17). |

## Verifier lesson candidate (flagged for kb-distiller, NOT enshrined here)
**A "relative"/spread reframing of a dimensionally-negligible factor inherits the magnitude death AND
multiplies the execution cost.** S82's `\|BTC−ETH\|` funding dispersion is a difference of two ~1e-5
rates (max $2.16 drift vs $100 bracket — still ~46× under the bracket, so the S76 wall is unmoved)
while requiring TWO range-ladder legs whose overrounds *add* (187% + 302%), not net. When a candidate
claims a spread/relative version lowers the signal bar, check whether it instead **sums the overrounds**
— cite S76/L-magnitude.

## Provenance / discipline
- All numbers above re-derived by the `verifier` from committed tape (`q42_hl_funding_cache`,
  `crypto_hourly/dt=2026-08-01`, `polymarket_macro_pairs`, `polymarket_cpi_pairs`); nothing trusted
  from proposal prose. Fees only via `core.pricing` (7% taker, 1.75% maker; Polymarket via
  `polymarket_fee_per_contract`). Bootstrap unit per L6/L41 (≥10 independent units). Settlement via
  `core.settlement_sources.resolve_market_results`.
- A pre-registration verifier attack is the mandated step for idea-stage candidates; it ran and
  returned 0 survivors. No candidate was registered, so nothing here is verdict-class.
- Still **0 proven edges.** Binding constraint stays the DATA SURFACE (multi-day `kalshi_trades`
  aimed at book-covered tickers; Q47/Q51 collector, Ryan-key-gated), not idea capacity.

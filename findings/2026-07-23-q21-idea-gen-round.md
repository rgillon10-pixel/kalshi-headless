# Q21 idea-generation round — 2026-07-23 (kalshi-edge-hunter, nightly Opus)

**Outcome: 2 candidates proposed (S48, S49), BOTH killed at idea stage → 0 registered.**
Eighth consecutive zero-registration round. This round deliberately left the exhausted
`orderbook_depth` maker/depth surface (rounds 1–7) and attacked the one genuinely *newer*
broad surface — `tape/universe_sweep/` (full-universe BBO **plus** `last_price` / `volume` /
`volume_24h` / `open_interest`, 4×/day, tagged `real_ask`) joined to `tape/settlement_ledger/`
(ex-post `broker_truth` outcomes). It dies too, on a hard **join-collapse** wall that is worth
recording because it will kill every future "hold-to-settlement, keyed on the universe
sweep × the settlement ledger" idea before any signal is computed.

Next free after this round: **S50.** Still **0 proven edges** repo-wide.

---

## S48 — Full-universe `last_price`-vs-BBO flow-follow taker, hold-to-settlement (DEAD)

- **Mechanism proposed:** in `tape/universe_sweep/`, when the last actual trade (`last_price`)
  sits materially above the resting YES mid `(yes_bid+yes_ask)/2`, treat it as informed YES
  buying not yet in the quote → BUY YES at `yes_ask` (real_ask, fillable) and HOLD TO
  SETTLEMENT so only ONE taker fee is paid (no round-trip). Symmetric on the NO side.
  Volume-gated to genuinely-traded markets; ground truth = `settlement_ledger` realized result.
- **Claimed distinction from the graveyard:** the signal is `last_price` — a REAL traded price,
  not a synthetic/de-vig anchor (unlike S1/S5/S7); it is a TAKER fill at a published ask, so it
  needs no maker fill-model / trade-print tape (unlike S6/S13/S19/S21/S23/S47); and it is not a
  depth-ladder-derived feature the mid already integrates (unlike S22/S24/S46).
- **Verifier verdict: KILL, tape-backed (n=2).** The independent `verifier` re-ran the full join
  and sim over the committed tape (fees via `core.pricing.fee_per_contract` at TAKER rate,
  entries only at real `yes_ask`/`no_ask` size≥1, `last_price` never treated as fillable —
  provenance clean). Population attrition:
  - `universe_sweep` dt=2026-07-17..07-23 = 460,000 rows / 442,109 distinct tickers; only
    **48,906 (10.6%)** carry `last_price>0` — the rest are untraded dead-tail (the 95%-dead-tail
    census, restated).
  - `settlement_ledger` = 10,605 distinct settled tickers, but only **2 capture dates**
    (07-17, 07-22) — a snapshot, not a continuous ledger.
  - JOIN (swept ∩ settled) = **373 tickers**. Of those: 300 never carried `last_price>0` at any
    pre-close sweep, 70 had a trade but no two-sided book to define a mid, 1 unfillable →
    **n=2 trades, 1 distinct event, 1 series** (`KXMVESPORTSMULTIGAMEEXTENDED`, a multi-leg
    combinatorial sports product). The most-generous relaxation (any sweep, pre/post close) still
    ceilings at **n=3**. No filter interpretation reaches the ~10–20-event bootstrap floor (L6),
    and the single event is L41-degenerate (both legs resolve the same way).
  - The two surviving trades independently confirm the mechanistic killers: both had
    `last_price` printing near a distant ask in a wide one-sided book (`yes_bid=0.01 / ask=0.08`
    and `0.064 / 0.336`), so `last_price > mid` is **mechanically forced** by the wide spread,
    and the "informed-flow gap" (3.3¢, 5.3¢) is **smaller than the half-spread you cross to buy
    at the ask** (3.5¢, 13.6¢). Both `volume_24h=0`; both settled NO; mean P&L **−$0.223**, win
    rate 0/2. This is the L31 wide/one-sided-spread-is-nominal artifact + L67 thin-book
    price-illusion, lifted one abstraction onto `last_price`; plus the taker-into-overround wall
    (S1/S5/S7). Sweep cadence (1–5 irregular passes/day, 6h+ gaps) also makes any lp-vs-mid gap
    stale by construction (killer b).

## S49 — Settlement-ledger category-conditional calibration maker/taker (DEAD at idea)

- **Mechanism proposed:** use the 10,605 `settlement_ledger` outcomes as ex-post fair to find a
  NON-sports/weather category whose pre-settlement `real_ask` calibration is off by more than the
  overround, then maker-bid or taker the mispriced side.
- **Kill at idea (no separate verifier round needed — dies on the SAME join-collapse the S48
  verifier just established, plus two already-verified walls):**
  1. **Join collapse.** A category-calibration test needs a settled + priced + *traded*
    population. The only priced-history surface that spans the settled tickers is the same
    `universe_sweep` × `settlement_ledger` join the verifier just measured at **n≈2–3 tradeable**
    markets (settlement_ledger is a 2-date snapshot; its overlap with the open-market sweep is
    dominated by untraded combinatorial `KXMVE*` products). Below the bootstrap floor before any
    calibration is computed.
  2. **Maker version → fill wall.** `universe_sweep` carries a market-wide `last_price`, not a
    queue-position fill model for *our* resting bid; claiming a maker fill from it is a
    `synthetic`-as-fill (prime-directive-forbidden, the S6/S21/S47 death).
  3. **Taker version → overround-at-ask wall.** Buying at `real_ask` pays away the full overround
    (S1/S5/S7); a calibration gap smaller than the overround nets negative, and the census shows
    the fillable universe is ~95% dead-tail longshots.

---

## The join-collapse corollary (why the newest surface is already exhausted)

The `universe_sweep` ∩ `settlement_ledger` join is **structurally ~2 tradeable markets**, not
because of a bug but because the settled tickers that also appear in the open-market sweep with a
real trade and a two-sided book are dominated by untraded combinatorial `KXMVE*` products. Any
hold-to-settlement idea keyed on that join is below the bootstrap floor *before any signal is
computed*. This is the `universe_sweep`-surface analogue of the two walls (the fill wall and the
mid-efficiency wall) that killed rounds 1–7 on the `orderbook_depth` surface — recorded here as a
finding-level observation rather than a numbered lesson (it restates L31/L41/L67 applied to a new
join; the in-flight lesson PRs already occupy L136–L139, so no `kb/lessons/` append this run to
avoid a merge conflict with that backlog).

## The standing signal (unchanged from round 7, now confirmed on the broad surface too)

The binding constraint is the **data surface, not idea capacity.** Rounds 1–7 exhausted the
hourly `orderbook_depth` maker/depth surface (fill wall + mid-efficiency wall); round 8 confirms
the newest broad surface (`universe_sweep` last_price/volume × `settlement_ledger`) is *also*
already exhausted, by join-collapse. Eight consecutive well-attacked zeros with the last registry
candidate closed (S14, Q34) is itself the finding: proving a new fillable edge needs a **new data
input** — trade-print / sub-hourly burst tape (the Q19 lane), or the credential-gated
cross-venue / CME / Polymarket-US legs (S2 / Q32 / Q33 / Q47) — which is a Ryan decision, not a
cloud-run one. Recommendation surfaced to Ryan (not acted on): consider pausing or widening the
nightly Q21 mandate until a new surface lands, so the round stops re-killing the same walls.

Consumed **S48 / S49 → next free = S50.**

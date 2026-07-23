# 2026-07-23 — `tape/universe_sweep/` family shapes: breadth idea-gen prep (schema defect + untested-family fingerprint)

**Type:** LOOP-QUEUE idle-run policy **(d)** — an observations memo from accumulated tape for
the NEXT Q21 idea-gen round. Descriptive breadth-discovery (prime directive #2). **NO strategy
claim, NO bootstrap CI, NO P&L, NO fills, NO registration, NO registry change**
(`kb/strategies/00-index.md` untouched). Two-agent verdict rule **N/A** (no verdict-class change —
same posture as L96/L125/L142). Every number is descriptive over `real_ask`-tagged committed tape,
re-derivable by the one reproduce command below.

## Falsifiable question

Across the full committed `tape/universe_sweep/` breadth census (7 days, `dt=2026-07-17`..`23`,
**460,000 lines / 0 malformed**), are there liquid, genuinely-**active** Kalshi series-**families**
the strategy registry has never touched (outside weather / crypto-ladders / sports-moneyline /
econ / fed / perp) whose top-of-book is a **genuine two-sided quote** — a surface a future round
could point a dedicated collector at?

## Two enabling findings (both verified on committed tape)

**(A) Schema defect — the breadth collector drops the NO-side sizes (fresh, sibling to L96).**
`collection/universe_sweep.py` maps only the YES-side sizes (`yes_bid_size_fp`, `yes_ask_size_fp`;
lines 116–117) and has **no mapping for `no_ask_size_fp` / `no_bid_size_fp`**, so those keys are
persisted **0.0 on 100% of all 460,000 lines** (nonzero fraction 0.000%, max 0.0). Contrast the
YES side: `yes_ask_size` nonzero 3.406% (max 228,571), `yes_bid_size` nonzero 0.480% (max 15,000).
A naive consumer reading `no_ask_size==0` would falsely conclude "no NO-side offer" — this is why a
breadth two-sided-liquidity screen looks empty until you correct for it. This is a distinct
collector field from L96 (`volume_24h` always 0) and from L142 (conflict markers) — **flagged as a
schema-quality note for Q46 / a collector-engineer pass, NOT fixed here** (collector code is the
Ryan-gated Q46 lane).

**(B) Mirror — the dropped NO-side size is recoverable, not lost.** A Kalshi binary's NO ask IS the
mirror of its YES bid: `no_ask == 1 − yes_bid` **and** `no_bid == 1 − yes_ask` hold **exactly on
2208/2208 (100.00%)** of lines carrying both YES prices. So the fillable NO-ask size **equals
`yes_bid_size`**, and the correct two-sided test uses the YES-side sizes. Defining two-sided as
`yes_ask>0 & yes_ask_size≥1` **AND** `yes_bid>0 & yes_bid_size≥1` recovers **1,986** genuinely
two-sided lines the `no_ask_size==0` artifact had hidden.

## Class composition (why the breadth tape is mostly noise)

| class | families | lines | active | two-sided |
|---|---|---|---|---|
| deadtail (`KXMVE*`) | 2 | 457,472 (99.4%) | 48,840 | 199 |
| untested | 106 | 2,500 | 66 | 1,759 |
| tested | 3 | 28 | 0 | 28 |

99.4% of the census is the two auto-generated multi-leg `KXMVE*` series (L105/L125). The bounded
20-call sweep slice barely reaches the tested families (28 lines) — **the breadth tape is not where
tested-family analysis happens**; its value is discovering *new* families.

## Untested-family shortlist (raw idea-gen material — descriptive, NOT a shortlist of edges)

79 untested families carry ≥1 genuine two-sided line, but most are the **L31 nominal-spread
artifact** — a 1¢-bid / 99¢-ask "two-sided" book with ~$0.98 median spread and zero volume/OI
(e.g. `KXARGNACBTOTAL`, `KXCHNSLTOTAL`, dozens of soccer `*TOTAL`/`*SPREAD`/`*BTTS` legs). Filtering
to **active (volume or OI > 0) AND tight (≤15¢ median two-sided spread)** leaves a short list:

| series | meaning | n | two-sided | active | Σvol | maxOI | events | median 2-sided spread |
|---|---|---|---|---|---|---|---|---|
| `KXWTIH` | WTI crude daily close | 440 | 367 | 23 | 1,683 | 223 | 10 | **8¢** |
| `KXGOLDH` | gold daily close | 320 | 237 | 8 | 237 | 25 | 7 | **4¢** |
| `KXSILVERH` | silver daily close | 320 | 236 | 4 | 321 | 269 | 7 | **4¢** |
| `KXMLBHRR` | MLB home-runs total | 78 | 78 | 4 | 167 | 100 | 2 | **2¢** |
| `KXWNBATOTAL` | WNBA game total pts | 4 | 4 | 4 | **8,469** | **2,785** | 1 | 6.5¢ |
| `KXATPCHALLENGERMATCH` | tennis match winner | 6 | 6 | 2 | 110 | 105 | 3 | 3.5¢ |

**The standout novel surface is the commodity daily-close ladder cluster — `KXWTIH` (oil),
`KXGOLDH` (gold), `KXSILVERH` (silver).** These are a **settlement-basis MECE strike ladder**
structurally analogous to weather (`KXHIGH*`) and crypto (`KXBTC`) — a bounded numeric outcome
(the commodity's settlement price) partitioned into strike brackets — a market **structure the
registry has never touched**. `KXWNBATOTAL` carries the most real depth (Σvol 8,469, maxOI 2,785).

## Honest annotation — which known wall each would hit (do NOT re-derive the graveyard)

For the next Q21 round, so it does not re-propose a re-killed factor:

- **Commodity close ladders (WTI/gold/silver)** sit in the **same factor slots that already died**:
  settlement-basis longshot-fade (S1/S5), intra-ladder coherence arb (S33 — DEAD on 6-leg fee
  floor + forward-fill asynchrony), overround underwriting (S14 — DEAD at queue-aware fills). A
  cross-sectional single-pass snapshot **cannot** establish the *simultaneity* an arb needs (L33) —
  do not read a Σask<$1 off one sweep line as an arb (L12). They would need a *dedicated dense
  collector* (the breadth sweep captures only ~23 active `KXWTIH` lines over 7 days) before any
  probe, and the honest prior is they hit the **same overround/fee walls** as weather/crypto unless
  the commodity settlement mechanics differ materially (e.g. a genuine index-vs-quote basis, the
  angle that at least kept S8 alive to a real ρ-guard). Diversity-floor value only.
- **Two-sided sports totals (`KXWNBATOTAL`, `KXMLBHRR`)** hit the **fill wall (L131) + mid-efficiency
  wall (L130)** the last seven idea-gen rounds already ran into: hourly/sweep snapshots carry **no
  trade prints**, so no maker fill is measurable, and the two-sided mid already integrates the depth
  ladder — the exact walls that killed S46/S47 at idea stage (2026-07-22, `findings/2026-07-22-q21-idea-gen-round.md`).
- **The wide `~$0.98`-spread soccer `*TOTAL`/`*SPREAD`/`*BTTS` families are the L31 nominal-spread
  artifact** — their "two-sided" is an untradeable 1¢/99¢ quote; excluded from the shortlist and
  flagged so no round mistakes their count for liquidity.

## Interpretation (keep honest)

The single most useful output is the **enabling caveat (A)+(B)**: any future breadth two-sided /
selective-maker (S11-lane) screen over `universe_sweep` **must** reconstruct the NO side from the
mirror (`yes_bid_size`), because the collector persists `no_ask_size`/`no_bid_size` as a false 0.
Beyond that, the breadth census surfaces **one genuinely new market STRUCTURE** (commodity
daily-close ladders) — but it is a new *surface* on *old, dead factors*, and every actively-quoted
untested family maps to a wall the graveyard already documents. This is **not** evidence any
tradeable edge exists in the breadth universe; it is pre-vetted raw material so the next Q21 round
spends its idea budget on the data-surface question (does a dense commodity-ladder or trade-print
tape exist to change any premise?) rather than re-deriving L130/L131/L31/L33.

## Reproduce

```
python scripts/universe_sweep_family_shapes.py
```

Writes `findings/universe_sweep_family_shapes.json` (schema `universe_sweep_family_shapes.v1`).
Read-only, no network, no credentials; every input line is `real_ask`-tagged committed tape.
Offline unit tests: `tests/test_universe_sweep_family_shapes.py` (7 tests, synthetic fixtures).

## Verification trail

Numbers reproduced two ways this run: the committed script above AND the research-lead's own
throwaway aggregation over the same 7 committed files (class totals, mirror 2208/2208, the
`no_ask_size` 0.000% defect, and the shortlist all reproduced exactly). Descriptive data-quality +
idea-gen prep, not a strategy verdict — the two-agent verdict rule is N/A. Lesson **candidates**
(deferred to a kb-distiller/collector-engineer pass, not recorded as rows here): "universe_sweep
drops `no_ask_size`/`no_bid_size`; reconstruct the NO side from the YES-side mirror" (sibling to
L96); and "the breadth census is a family-DISCOVERY surface, not a tested-family analysis surface —
its active/tight untested families are new surfaces on already-dead factors."

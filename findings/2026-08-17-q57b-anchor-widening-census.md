# Q57b / S82 — the anchor widening is a NO-OP, and the cell that "works" buys sign variation with mechanism

`2026-08-17` · research loop, protocol v3 · **verdict class: DATA-ADEQUACY (population). No CI,
no P&L, no outcome VALUE read.** · **PROVISIONAL** (no second AGENT was dispatchable; see §7) ·
`kb/strategies/00-index.md` **S82 stays `idea` — no registry flip**

Repro:

```
python3 scripts/q57b_anchor_widening_census.py     # -> reports/q57b_anchor_widening_census.json
python3 scripts/q57b_rederive.py                   # independent second implementation
python3 -m pytest -q -o addopts='' tests/test_q57b_anchor_widening_census.py tests/test_q57b_rederive.py
```

---

## 1. The question, and why it is a population question

LOOP-QUEUE.md Q57 was left OPEN on 2026-08-16 with exactly two named roads back in:

> (a) uses the ledger anchor at a 15-min window once one more settled game lands (a near-term
> data-adequacy wait, not a rebuild), or (b) widens the entry anchor to `q51_settlement_cache`
> as its OWN pre-registered choice (not a post-hoc addition) at `sign_variation_admissible`'s
> real `min_exclusive_minority_units=2` floor.

This run executes **(b)**, sealed before counting (`PREREG_SHA256 = 9ce0cf1140a26c8e…`,
inheriting Q57's own seal `dd80f5973c39a0f4…` by IMPORT rather than by retyping, so Q57's
constants cannot drift out from under it). The seal declares exactly two deltas and names the
direction of each:

| id | field | Q57 seal | Q57b seal | direction |
|---|---|---|---|---|
| **D1** | `close_anchor` | `settlement_ledger.close_time` | `UNION(settlement_ledger, q51_settlement_cache)` | **wider** (mandated by the reopen text) |
| **D2** | `min_exclusive_minority_units` | `1` | `2` | **stricter** — restores `core.bootstrap`'s own default, which Q57's probe had silently relaxed |

Everything else — 120-min flow window, 60-min max entry lag, `|rho| >= 0.20`, count floor 100,
band `[0.02, 0.98]`, `argmax|rho|` game collapse, FADE direction, L41's 10-unit floor — is
inherited byte-for-byte.

**This module never reads a settlement result VALUE.** It imports `settled_ticker_set`
(membership: WHICH tickers settled binary) and not `outcome_map` / `binary_outcome` /
`score_rows` (value: HOW). That is AST-pinned by
`test_census_is_outcome_blind_by_ast`. The reason is not squeamishness: Q57's gate (2) is a
POPULATION gate, a CI over a population that fails it does not measure the signal, and peeking
at outcomes now would burn the tape's re-testability for the properly-powered retest that path
(a) is still waiting on.

Substrate: **87 GAME tickers / 72 games / 81 settled binary**, `tape/kalshi_trades/` ×
`tape/orderbook_depth/` × `tape/settlement_ledger/` × `tape/q51_settlement_cache/`. Every entry
price quoted anywhere below is `best_yes_ask` / `best_no_ask` read from `orderbook_depth` rows
whose own `price_source_tags.asks == "real_ask"` — **`price_source_tag = real_ask`**. Nothing
here is derived, complemented from a bid, or midpointed.

---

## 2. F1 — path (b), executed as a single change, adds ZERO units

| anchor | game units | sides | L41 floor | sign-variation (`min_excl=2`) |
|---|---|---|---|---|
| `settlement_ledger` only (the Q57 baseline) | **11** | `{no: 11}` | pass | **FAIL** |
| **UNION with `q51_settlement_cache` (PRIMARY)** | **11** | `{no: 11}` | pass | **FAIL** |

`widening_is_a_noop_at_the_sealed_spec = true`. Identical unit count, identical side split,
identical population. The two close-time sources are **fully DISJOINT** (49 ledger-only + 38
cache-only + **0** in both = 87), so the widening is not being masked by an overlap — the
cache genuinely contributes 38 new anchored tickers and **not one of them becomes a unit**.

The 11-unit `{no: 11}` baseline reproduces the 2026-08-16 probe's headline exactly.

## 3. F2 — why: the cache widens the CLOSE-TIME population, not the DEPTH-COVERED one

An anchor source only yields a unit if a depth snapshot sits inside the lag budget.

| source | tickers w/ close_time | entry-lag p10 / **p50** / p90 (min) | **within the sealed 60-min budget** |
|---|---|---|---|
| `settlement_ledger` | 49 | 4.1 / **6.3** / 199.9 | **37 / 49** |
| `q51_settlement_cache` | 38 | 36.4 / **143.8** / 653.7 | **5 / 38** |

The ledger's tickers are the ones the depth collector was actually watching near their close
(median lag **6.3 minutes**). The cache's are markets the collector was not near — median
**143.8 minutes**, a 23x worse lag, only 5 of 38 inside budget, and those 5 are then eliminated
by the ordinary flow/band gates. This is a **coverage** fact about which markets a once-an-hour
collector happened to see, not a fact about S82.

## 4. F3 — the grid: 36 cells work, and every one of them abandons the mechanism

Pre-registered outcome-blind grid over the UNION anchor:
window `{15,30,45,60,90,120,180,240}` × lag `{30,60,90,120,180,240,360,720}` × `|rho|`
`{0.10,0.15,0.20,0.30,0.40}` × count floor `{0,50,100,250}` = **1,280 cells**. It reports
population SHAPE only — unit counts and side counts, never a return — so it costs no
multiplicity (L362).

- **976** cells clear L41's 10-unit floor.
- **36** of those also clear `sign_variation_admissible(min_exclusive_minority_units=2)`.
- **0** of those 36 are mechanism-faithful.

Every one of the 36 uses **`flow_window_minutes = 15`** and **`max_entry_lag_minutes >= 180`**.
The minimum admissible lag anywhere in the grid is **180 minutes**. At the sealed lag of 60 the
count of admissible cells is **zero**.

The seal's own justification for 60 minutes is *"the depth collector's own cadence: the
tightest lag that can be met by a once-an-hour capture."* A cell at lag 180–240 fills at a book
up to **three to four hours before the market closes** — for a sports game that is frequently a
pre-game book being used to trade a late-in-play signal. So the sign variation those cells
exhibit is **purchased with mechanism, not with data**, and the seal's pre-registered
disposition rule (written before any cell was counted) classifies them as non-qualifying.

**This corrects the ATTRIBUTION in Q57's verifier round, not its arithmetic.** That round's
cell — cache anchor, window 15, lag ≤ 240 → **12 units, `{no: 10, yes: 2}`, 2 exclusive-minority
units** — reproduces here **exactly**. What it credited to the anchor widening is in fact
produced by the *lag* relaxation riding along with it: the anchor alone (F1) moves nothing, and
the same window-15 cell at lag ≤ 60 gives **9 units `{no: 8, yes: 1}`** — short on BOTH floors.

**Disposition: `PATH_B_CLOSED_DATA_ADEQUACY`.**

## 5. F4 — the declared anchor look-ahead is real, and NON-BINDING on this population

Q57 declared the entry anchor's ex-ante knowability **UNVERIFIED** (L360/L361: Kalshi rewrites
`close_time` at settlement, always EARLIER) and could not check it, because both committed
`settlement_ledger` day-files are post-settlement. The cache family *can* be checked, and this
run checked it:

- **27 of 38** cache tickers carry more than one distinct `close_time` across capture files —
  the rewrite is real and large: spread **min 40.1 min / median 3,103 min (~2.2 days) / max
  20,000 min (~13.9 days)**.
- Yet the selected entry snapshot is **IDENTICAL under the earliest-value rule and the
  latest-value rule on 38 / 38 tickers** (`entry_snapshot_differs = 0`).

Because the entry instant is "the last depth snapshot at or before close", and the depth cadence
is hourly while the rewrite is measured in days, **which `close_time` you believe cannot move a
single entry price here.** L360/L361 stands in general; the exposure is non-binding on *this*
population, which is a narrower and checkable claim. The check is not vacuous — a fixture where
the rewrite *does* straddle a snapshot makes it fire
(`test_rewrite_invariance_FIRES_when_the_rewrite_moves_the_entry_snapshot`).

## 6. What Q57 path (a) actually costs (a correction to the queue's own text)

Q57 wrote path (a) as waiting for *"one more settled game."* Measured: the ledger anchor at
window 15 / lag 60 yields **9 units `{no: 8, yes: 1}`**. It is short **1 unit** of L41's floor
**and** short **1 exclusive-minority unit** of the real `min_exclusive_minority_units = 2`
floor — and the minority arm is the scarce one. The 2026-08-16 probe measured only **3 of 45**
observations carrying negative net flow at all, of which **0** had a fillable in-band YES ask.
So path (a) is not "one game away"; it needs at least one more settled game **that is also a
fade-to-YES unit with a live in-band ask**, an event this tape has produced roughly once per 45
observations. That is a real wait, and it should be written down as one.

These numbers are persisted, not just quoted: `path_a_cost` in
`reports/q57b_anchor_widening_census.json` carries the cell under BOTH anchors
(`units_short_of_L41_floor = 1`, `minority_units_short_of_floor = 1`), and the union anchor
reads **identically** to the ledger anchor there — F1's no-op holds at this cell too. Pinned by
`test_acceptance_path_a_is_short_on_BOTH_floors_and_the_scarce_arm_is_named`. The cell's
coordinates are Q57's own ("ledger anchor at a 15-min window"), not chosen here, and it adds no
term to the seal.

## 7. Two-agent rule — NOT satisfied; this is PROVISIONAL

No `Task`/subagent tool exists in this harness (the L287/L288/L290/L291/L295/L308/L313/L325/
L349 precedent, and the same constraint the 2026-08-16 probe run recorded). The sanctioned
redundancy fallback ran instead: **`scripts/q57b_rederive.py`**, AST-pinned by test to import
neither the census, nor the Q57 probe, nor `core.bootstrap`/`core.settlement_sources`/
`core.timeutil`/`core.pricing`/`core.markets`/`core.io`. It uses its own JSONL reader, its own
ISO→epoch parser (string slicing + `calendar.timegm`), its own sports-ticker predicate, its own
settled-set reader, a running-scan flow accumulator instead of a windowed slice, and its own
minority-side counter. It agrees on **22 / 22** compared fields.

**A second IMPLEMENTATION is not a second AGENT.** That agreement downgrades transcription risk,
not reasoning risk. Hence: no registry flip, **S82 stays `idea`**, and this document is
PROVISIONAL until an independent agent confirms.

## 7b. Two disclosures against my own result

Neither changes the headline, and both are the kind of thing a reader is entitled to be told
rather than to discover.

**(i) The disposition rule's mechanism-faithfulness criterion was written by the same session
that had already scratch-explored the lag axis.** I knew, before sealing, that lag was the
binding constant and that the minimum admissible lag was 180. The criterion itself is anchored
to text written *before* this run — the inherited seal's own stated reason for choosing 60
minutes ("the depth collector's own cadence: the tightest lag that can be met by a once-an-hour
capture", sealed 2026-08-16) — so it is not a threshold invented to produce an answer. But the
*choice to treat lag rather than window as the mechanism-binding axis* was made with that
knowledge in hand and is a real degree of freedom. It is disclosed rather than laundered.

**The headline (§2) is immune to this.** F1 is a single, fully pre-specified cell with zero
free parameters — the inherited seal, one anchor change — and it reads 11 units `{no: 11}` both
ways. The grid (§4) is supporting evidence for *why*, not the finding itself.

**(ii) The redundancy leg has a real semantic difference from the census, which happens not to
bind here.** `scripts/q57b_anchor_widening_census.py` collapses each game to its `argmax|rho|`
ticker and *then* filters to settled tickers; `scripts/q57b_rederive.py` filters to settled
*before* collapsing. On a game whose highest-`|rho|` ticker is unsettled while a sibling ticker
is settled, the census drops the game and the re-derivation keeps the sibling. The two agree on
all 22 fields, including every one of the 1,280 grid cells, so the divergence is empirically nil
on this tape — but it is a genuine difference in reading, not a transcription of the same rule,
and it is part of why the agreement is worth something at all.

## 8. Disposition

- **Q57 stays OPEN**, with path **(b) CLOSED** and path (a) re-costed per §6.
- **S82 stays `idea`.** No kill: the prior verifier round explicitly withdrew the presumptive-KILL
  recommendation, and nothing here re-earns it — a population that cannot be scored is not a
  falsified edge.
- **No CI, no P&L, no fill, no capital.** Still **0 proven edges** in the registry.
- A future run that wants to reopen (b) must beat the coverage fact in §3, not the spec: it needs
  `orderbook_depth` snapshots inside 60 minutes of close on markets the cache anchors — i.e. a
  collector change, not a probe change.

**Files:** `scripts/q57b_anchor_widening_census.py`, `scripts/q57b_rederive.py`,
`tests/test_q57b_anchor_widening_census.py`, `tests/test_q57b_rederive.py`,
`reports/q57b_anchor_widening_census.json` (live) and
`reports/q57b_anchor_widening_census-2026-08-17.json` (the FROZEN, sha256-pinned snapshot the
numbers above were published from — L325/L341: an exact pin against a self-regenerating live
artifact turns red on correct data, so the tests pin the frozen copy and let the live one move),
plus four triage declarations in `scripts/invariants.py` (L323 trade-print tie-break
ORDER-INSENSITIVE, L321 minority-side gate EXCLUSIVE, for both new modules).

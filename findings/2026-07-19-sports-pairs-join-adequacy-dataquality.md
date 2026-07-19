# sports_pairs data-quality + join-adequacy deep-dive (idle-run option c, 2026-07-19)

- **Date:** 2026-07-19 (idle-run, protocol v3 option c)
- **Scope:** `tape/sports_pairs/` health + the sports-maker / CLV-anchored-fill join-adequacy question
  (can we join a `synthetic` fair anchor to a real resting pre-settlement book?).
- **Mode:** READ-ONLY, offline over committed tape. No collector code touched. All prices/derived
  numbers source-tagged.
- **Verification:** two concordant read-only agents — research-lead direct computation + a
  tape-auditor pass. This is a **data-adequacy** verdict, NOT a CI falsification, and it is
  **NON-registry-flipping** (S21 is already DEAD-by-data-adequacy; this run only reaffirms *why*
  it stays untestable).
- **Provenance lessons:** L9, L43 (structural fair/depth timing gap), L64 / S28 (settlement-emptying
  book transition), L25 (tape format-regression debris).

---

## 1. CORE VERDICT — join-adequacy (two-agent concordant, non-registry-flipping)

> The sports-maker / CLV-anchored fill question remains **STILL DATA-STARVED** (n=3 concurrent
> games, only 2 clean-live pre-settlement books; below the 10-game floor). The **L9/L43 structural
> timing gap persists** — no join-window relaxation can fix it because the game date is embedded in
> the ticker string.

**Independent computation #1** (research-lead, `sports_clv` fair universe only, kickoffs
2026-06-04..2026-07-03): **0 concurrent games** vs `orderbook_depth` (which runs live only from
>= 07-07). No overlap at all.

**Independent computation #2** (tape-auditor, adding the one-shot `tape/sports_clv_s7/trades.jsonl`,
which reaches game-date 07-07): **3 concurrent games**, of which:
- **2 clean-live** pre-settlement books: `KXWCGAME-26JUL07SUICOL`, `KXWCGAME-26JUL07ARGEGY`.
- **1 marginal / reject**: `KXWCGAME-26JUL06USABEL` — the book is already collapsing at the first
  depth capture (the L64 / S28 settlement-emptying transition), not a clean pre-close resting book.

**Why the 0 -> 3 delta is not new signal.** The delta comes *solely* from `sports_clv_s7` extending
the fair universe two days later than `sports_clv`, catching the 07-06/07-07 boundary — **NOT** from
any new concurrent forward collection. Fair-anchor collection never advanced past game-date 07-07;
depth ran 07-07..07-19. Every WC game with depth on 07-09..07-19 has **NO fair anchor**; every
fair-anchored game <= 07-05 had **already settled before depth began**. The two families pass each
other in the night with a two-day kissing overlap.

**Span table:**

| family | field joined on | span | tag |
|--------|-----------------|------|-----|
| `sports_clv` | kickoff | kickoffs 2026-06-04 -> 2026-07-03 | fair `synthetic` |
| `sports_clv_s7/trades.jsonl` | game-date (fair-anchor union max game-date 07-07) | game-dates -> 2026-07-07 | fair `synthetic` |
| `orderbook_depth` (sports subset) | ticker (outcome suffix dropped) | 2026-07-06 -> 2026-07-19 | real_ask/real_bid |

(KXBTC/KXETH crypto tickers excluded from the depth sports subset.)

**Price tags.** Fair legs carry `price_source_tag_odds: "synthetic"` (`sports_clv_s7` `fair_prob`);
depth legs `real_ask`/`real_bid`; Kalshi settlement `broker_truth`. Because the anchor is synthetic,
even a full overlap would not by itself clear the prime-directive real-ask CI bar — but that question
never arises, because the overlap does not exist. **Data-adequacy verdict, not a CI falsification.**

---

## 2. sports_pairs HEALTH (16 canonical `dt=*.jsonl`, 2026-07-03..2026-07-19)

- **101,801 lines** total across 16 canonical day-files, **0 JSON-invalid**.
- **`completeness_ok = True` on 100%** (0 False, n=101,801).
- **~30-min cadence** (a full day = 48 capture_ids).
- **33 distinct series**, all `KX...GAME`.
- Schema `sports_pairs.v1`; **every priced outcome tagged `real_ask`** (0 non-`real_ask`, 0 untagged).

**Overround.** Median `overround_absorbed` is **FLAT at 0.02-0.05 the whole span** — no material
drift. The *mean* per day sits at 0.13-0.33; it is right-skewed and composition-driven (illiquid
3-way soccer / draw markets fat-tail the absorbed overround). **Report median as the honest figure;
the mean is skewed** and tracks 3-way-market composition, not book quality.

| day | lines | games (distinct event_ticker) | series | median overround |
|-----|------:|------:|------:|------:|
| 2026-07-03 | 4,351 | 219 | 16 | 0.04 |
| 2026-07-04 | 7,844 | 236 | 19 | 0.04 |
| 2026-07-05 | 9,003 | 243 | 21 | 0.04 |
| 2026-07-06 | 8,995 | 211 | 18 | 0.05 |
| 2026-07-07 | 8,287 | 205 | 19 | 0.03 |
| 2026-07-08 | 4,719 | 224 | 25 | 0.04 |
| 2026-07-10 | 1,968 | 221 | 26 | 0.02 |
| 2026-07-11 | 9,404 | 238 | 26 | 0.03 |
| 2026-07-12 | 6,578 | 195 | 25 | 0.03 |
| 2026-07-13 | 5,652 | 135 | 25 | 0.03 |
| 2026-07-14 | 6,386 | 163 | 26 | 0.03 |
| 2026-07-15 | 7,047 | 251 | 27 | 0.05 |
| 2026-07-16 | 8,152 | 326 | 29 | 0.04 |
| 2026-07-17 | 8,521 | 291 | 27 | 0.03 |
| 2026-07-18 | 3,667 | 299 | 26 | 0.02 |
| 2026-07-19 | 1,227 | 275 | 26 | 0.04 |

(07-10 = 1,968 lines is the **truncated** canonical file — see §3; 07-03/07-19 are day-edge partials.)

---

## 3. DATA-QUALITY DEFECT (genuinely-new actionable item): resident L25 format-regression debris

The **L25** format-regression debris is **STILL RESIDENT in the committed tree ~9 days after L25
documented it**. L25's self-correction fixed *forward* collection but never garbage-collected the
corrupt directories, so three `dt=` entries are **directory-shaped, not canonical files**:

- `tape/sports_pairs/dt=2026-07-02/` — one early-format pass file (pre-canonical shape).
- `tape/sports_pairs/dt=2026-07-09/` — raw per-market `capture-*/*.raw.json` blobs, **and there is NO
  canonical `dt=2026-07-09.jsonl` at all** -> 07-09 is a **PERMANENTLY MISSING day**.
- `tape/sports_pairs/dt=2026-07-10/` — raw blobs **coexisting** with a **TRUNCATED
  `dt=2026-07-10.jsonl`** of only **9/48 captures (1,968 lines)**.

Consequences:
- A naive `ls tape/sports_pairs/ | grep dt=` day-count would **over-count** (07-02, 07-09 appear as
  "days") and **mis-shape** (07-10 looks whole but is 9/48).
- `orderbook_depth` also has **07-09 absent** — the same stall window bit both families.

L25 asserted that a `dt=<date>` path should be the expected *file* shape; but nothing yet flags an
**orphaned directory-shaped day for cleanup/GC**. The debris is inert to forward collection yet
permanently pollutes any path-shaped census of the tape.

---

## 4. REPRODUCE (exact paths / method)

- **sports_pairs health:** `glob tape/sports_pairs/dt=*.jsonl` (canonical files only — the three
  directory-shaped `dt=` entries are excluded by the `*.jsonl` suffix), group by `capture_id` /
  `event_ticker` / `series`, parse `overround_absorbed`, take per-day median (mean is skewed —
  report median). Verify `completeness_ok`, `schema_version == sports_pairs.v1`,
  `price_source_tag == real_ask`.
- **fair set:** union of `tape/sports_clv/dt=*.jsonl` (field: kickoff) and
  `tape/sports_clv_s7/trades.jsonl` (field: `kalshi_event_ticker`); fair leg tag
  `price_source_tag_odds` = `synthetic`, value `fair_prob`.
- **depth events:** `tape/orderbook_depth/dt=*.jsonl` (field: `ticker`, drop the outcome suffix,
  **exclude KXBTC/KXETH** crypto).
- **join:** intersect fair-event-tickers with depth-event-tickers; require `no_bids`/`yes_bids`
  non-empty for a *pre-settlement* resting book.
- **book-emptying spot-check:** the `KXWCGAME-26JUL07SUICOL` captures sorted by `captured_at`
  (clean pre-close resting book) vs `KXWCGAME-26JUL06USABEL` (already collapsing at first depth
  capture — the L64 / S28 settlement-emptying transition, rejected).

---

## 5. Outcome

- **No registry flip.** S21 stays DEAD-by-data-adequacy; the fair/depth timing gap (L9/L43) is
  structural (game date embedded in the ticker) and no join-window relaxation resolves it.
- **New lesson filed:** L109 (the L25 orphaned-directory-debris data-quality defect) — see
  `kb/lessons/00-lessons.md`. Marked PROVISIONAL / UNENFORCED candidate; the escalation
  (an audit/invariant that flags orphaned directory-shaped `dt=` days for GC, beyond L25's
  file-shape assert) is deliberately NOT built this run (idle-run scope).

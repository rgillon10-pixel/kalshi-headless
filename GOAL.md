# GOAL — Data-Collection Workstream

`v1 · set 2026-07-16 via goal-council (Archivist / Cost-Ops-Realist / Quant-Consumer)`

This is the long-term goal for the **data-collection** workstream — the archive the
whole project looks back on. It is set by the goal-council pattern (re-convene personas,
force a single falsifiable sentence, record dissents so goal-posts can't move later).
It sits *under* the project prime directive (`CLAUDE.md`): collection is in service of a
profitable set of strategies at real fillable prices, never an end in itself.

**Decided frame (Ryan, 2026-07-16 — non-negotiable):**
- **Both, phased.** Phase 1 = plug permanent-loss holes with cheap, ungated collectors
  (systematic settlement harvest + full-universe top-of-book sweep). Phase 2 = go deep
  (focused L2 depth, sub-15-min cadence, trade prints).
- **REST-only.** No credentialed WebSocket feed in scope. The Kalshi `orderbook_delta` WS
  feed (true continuous sub-second) and the full signed trade feed are **out of scope /
  future Ryan-gated** (they require credentials → VPS/local only, never cloud).

---

## The falsifiable goal (Phase 1)

> **By 2026-08-31, kalshi.headless systematically captures, with source tags and
> gap-monitoring:**
> **(a)** a `broker_truth` settlement label (`result` + `settlement_value` + terminal
> `volume`/`open_interest`) for **≥95%** of every Kalshi market settling on or after
> 2026-07-17, **within 14 days** of its close; **and**
> **(b)** a full-universe top-of-book snapshot (BBO + `volume` + `open_interest` +
> `last_price`, tagged `real_ask`) for **≥95%** of open Kalshi markets at **≥ every-6h**
> cadence with a **<5%** missing-snapshot rate —
> with an automated gap-detector alerting **≤6h** on any family going silent, a sustained
> per-family missing-day rate **<2%** over the final 7 days, **≥90%** of settled markets
> joinable to a prior BBO snapshot, and an executed external-storage/compression path
> keeping **no git-committed family >50 MB** uncompressed.

Falsifiable on eight numbers: 95% settlement coverage · ≤14-day capture lag · 95% universe
coverage/sweep · <5% missing-snapshot rate · ≤6h detector latency · <2% missing-day rate ·
≥90% label↔snapshot join · 50 MB per-family git ceiling.

---

## Why this shape (the enabling facts, verified in-repo)

- **Full-universe breadth is nearly free.** `/markets` (paginated, `limit≤1000`, `cursor`)
  returns `yes_bid`/`yes_ask` **+ `volume` + `open_interest` + `last_price` inline per
  market** (`collection/sports_pairs.py:123`, `validation/v3_market.py:157`). A snapshot of
  all ~10k open markets ≈ **10–15 calls, ~3 MB** — a rounding error against the shared
  ~20 read-req/s token bucket. This defeats the cost objection to breadth.
- **Settlement labels purge; the archive does not persist them for free.** Kalshi purges
  settled `/markets` ~60 days after close (lesson L11). `/events?status=settled` lists
  forever but the per-market settlement fields age out. The label is the y-variable for
  every backtest — un-collected = permanently un-backtestable.
- **Trade prints are partially REST-collectable after all.** `market_trades()`
  (`validation/v3_market.py:180`, public `GET /markets/trades`) reaches **recent public
  prints** over REST — no credentials. This is the Phase-2 flow lane (recent, per-market).
  The *continuous signed real-time* sequence still needs the out-of-scope WS feed.
- **The pipe leaks today.** Confirmed permanent holes: 07-09 systemic full-day outage
  across 6+ families; 07-15 dropped ~16 mid-day passes; `polymarket_pairs` collector died
  07-15 and went unnoticed until the 07-16 audit. Gap-detection latency today is unbounded
  (human-only). No new family ships onto an un-monitored pipe.
- **Storage is a one-way door.** `.git` is already ~359 MB and the repo is **public**
  (`rgillon10-pixel/kalshi-headless`). `orderbook_depth` = 212 MB (4.2× the 50 MB README
  flag), `sports_pairs` = 167 MB; whole-tape growth ~35 MB/day → ~13 GB/yr. Storage is
  reversible (compress/externalize); the 60-day purge is not.

---

## Milestones (today = 2026-07-16)

| # | Date | Measurable done-criterion |
|---|---|---|
| **M1 — Reliability + labels** | 2026-07-23 | **(a)** Gap-detector aggregates `completeness_ok` per family per UTC day + "age since last successful pass"; ntfy alert fires ≤6h after any family goes >2 expected passes silent. Acceptance: run over existing tape it must independently flag the 07-09 outage, the 07-15 interior holes, AND the `polymarket_pairs` death — miss any of the three → fail. **(b)** One append-only `tape/settlement_ledger/` family keyed by `(ticker, close_time, result, settlement_value)`, tagged `broker_truth`, capturing ≥95% of the prior UTC day's settled markets; filters non-binary `result:"scalar"` rows (L52); replaces the four ad-hoc `qNN_settlement_cache/` dirs. Offline unit tests green. |
| **M2 — Universe sweep** | 2026-07-30 | One paginated `/markets` sweep enumerates ≥95% of the open universe (cross-checked vs the listing's own total count) in ≤20 calls, writing one `real_ask`-tagged line per market (BBO + `volume` + `OI` + `last_price`) at ≥ every-6h cadence; <5% missing-snapshot rate over 3 consecutive days. Monitored by the M1 gap-detector from day one. Repairs the dead `polymarket_pairs` leg. |
| **M3 — Storage decision (Ryan-gated)** | 2026-08-06 | Families >50 MB (`orderbook_depth` 212 MB, `sports_pairs` 167 MB) gzipped in place and/or offloaded to external storage with a git-committed manifest; a CI check fails the build when any family exceeds 50 MB uncompressed in the working tree; hot window = current + prior 30 days git-committed, older gzipped/externalized; gap-day registry file enumerates every missing pass (incl. 07-09, 07-15) with a reason code. |
| **M4 — Join test** | 2026-08-20 | ≥90% of settled markets in a trailing 30-day window join to ≥1 prior BBO snapshot by ticker — i.e. label tape and feature tape are actually joinable, not two disjoint windows (the S21 / L50 failure mode). This is the gate that makes breadth prove analytic value, not just accumulate. |
| **M5 — Certification** | 2026-08-31 | An auditor run confirms both goal thresholds over the trailing 14 days (settlement ≥95%/≤14d, BBO ≥95%/<5% miss) AND a per-family missing-day rate <2% for 7 consecutive days. Phase-1 done gate; pre-condition for any Phase-2 family. |
| **Phase 2 (post-2026-08-31, behind M5 + M3)** | — | Focused (~500 most-recently-active tickers) L2-depth expansion; REST `/markets/trades` prints on the focused set; promote `collection/hf_burst.py` from stopgap to standing ≤15-min cadence on the focused set; REST `volume`/`OI` delta features (probationary, see kill #7). Each is focused, not universe-wide. **Out of scope / Ryan-gated:** WS `orderbook_delta` feed, full signed trade feed, live-capital anything. |

---

## Kill / stop criteria (any one → the workstream is failing; stop or rescope)

1. **Label pipe broken:** settlement coverage <80% of settled markets for 7 consecutive
   days → stop adding any capture, fix it (unlabeled book tape is worthless).
2. **Leak freeze:** per-family missing-day rate >5% over any 7-day window after M1 →
   FREEZE all new-family/breadth work until the leak is fixed. No "the market is closing"
   exception.
3. **Storage ceiling:** committed working-tree tape >1.0 GB, or `.git` >750 MB, before M3
   executes → halt `orderbook_depth` + the largest producers until offloaded; if `.git`
   >750 MB, raw-tape git commits STOP entirely (external offload becomes mandatory).
4. **Cadence infeasible:** BBO universe missing-snapshot rate >20% over any rolling 7-day
   window → cadence is infeasible on the shared token bucket; rescope cadence downward.
5. **Reliability is binding:** a second systemic multi-family full-day outage recurs after
   M1 (a repeat of 07-09) → stop adding families, fix host reliability first.
6. **Hoarding unjoinable tape:** settlement→BBO join <50% at M4 → the label and feature
   tapes are disjoint; rescope rather than keep accumulating.
7. **Phase-2 futility (Quant gate):** if focused depth+prints+cadence runs 21 continuous
   days and no structural lane (L-mech / L-speed / L-flow) produces a non-degenerate
   block-bootstrap CI (≥30 clusters, both bounds admissible), freeze expansion and rescope
   the lane. The REST `volume`/`OI` flow proxy is probationary: if it adds 0 of ≥3
   attempted lane features that shift a CI bound by ≥$0.01, delete the leg.

---

## Recorded dissents (kept so goal-posts can't move later)

- **Quant-Consumer:** *"Universe-wide BBO is negative-value hoarding — the repo's own
  graveyard shows breadth kills candidates on data-adequacy (S14 capped at 0.335 winner
  coverage, S21 0/81 joinable), while the narrow L2-depth family is the only one that ever
  produced a real-ask verdict. Collect zero universe BBO until a lane CI clears zero."*
  → **Overridden for Phase 1** by the decided both-phased frame + the ~3 MB/15-call cost
  fact. **Honored** by the M4 join-gate (breadth must prove joinable) and by keeping all
  Phase-2 depth/prints focused, not universe-wide.
- **Cost/Ops Realist:** *"A wider pipe on a leaking joint loses more per outage. No new
  breadth family ships until per-family missing-day rate <2% for 7 straight days, and
  nothing deep gets committed to a 359 MB public git repo until the 50-MB-per-family
  external-storage offload lands."*
  → **Honored:** gap-detector is M1 (ships with the new families), <2% is in the M5 cert
  gate and kill #2, storage is a hard Ryan-gated milestone (M3) with CI enforcement.
  **Overridden only** on sequencing: the 0.5 MB/day settlement harvest is NOT blocked
  behind the 212 MB depth-family cleanup (storage is reversible; the purge is not).
- **Archivist:** *"Storage is reversible, the 60-day purge is not — capture the label and
  the whole board now at top-of-book because both are cheap and both vanish in 60 days; go
  deep later and focused. Do not narrow settlement/BBO to a 'focused set' defined by
  today's dead hypotheses (prime directive #2: collect where others aren't)."*
  → **Adopted** as the Phase-1 spine.

---

## Out of scope / explicitly deferred

- **WS `orderbook_delta` feed** (true continuous sub-second) and the **full signed trade
  feed** — need credentials → VPS/local only, never cloud; Ryan-gated, not in this goal.
- **Any live-capital path** — governed by `CLAUDE.md` execution-lane tiers, unaffected here.
- **Full 154-branch `tape/*` stranded-line certification** — audit sampled 3, found nothing
  genuinely stranded; a full read-write sweep is separate ops hygiene.

---

*Provenance: goal-council 2026-07-16, informed by the tape audit of the same date (499 MB,
23 families, ~2 weeks, all hourly REST book-snapshots; zero trade-print/volume/OI families;
settlement = 4 ad-hoc caches). Council transcripts summarized in-session; positions quoted
above are the personas' own words. Related discipline: prime directive #1 (real-ask CI is
the binding gate — this goal produces evidence toward it, never a substitute for it).*

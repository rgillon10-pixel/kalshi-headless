# The settlement-source registry has a real recall gap — and it is worth almost nothing

**Date:** 2026-08-15 · **Run:** research loop (Opus 5, 3-hourly), IDLE RUN under LOOP-QUEUE.md
protocol v3 step 3, **idle-run policy (c)** — data-quality deep-dive on one tape family.
**Class:** DATA-ADEQUACY / registry-correctness. **No P&L, no CI, no bootstrap, no kill, no
registry flip.** `kb/strategies/00-index.md` untouched — still **0 proven edges**.
**Status: PROVISIONAL** (see §7: no `verifier` subagent is dispatchable in this harness; the
sanctioned redundancy fallback ran instead and is reported as redundancy, never as the
two-agent rule being satisfied).

**Artifacts (all re-runnable, offline, read-only):**
`scripts/settlement_source_recall_audit.py` · `core/result_evidence.py` ·
`scripts/settlement_source_recall_rederive.py` ·
`reports/settlement_source_recall_audit.json` · `reports/settlement_source_recall_rederive.json` ·
`tests/test_result_evidence.py` · `tests/test_settlement_source_recall_audit.py` ·
`tests/test_settlement_source_recall_rederive.py` ·
`scripts/invariants.py::undeclared_result_family_warning` (non-gating advisory).

---

## 0. Why this question, today

The 06:xx run's depth-label substrate census (`findings/2026-08-15-depth-label-substrate-census.md`)
ended on a routing decision: the sports depth tape is observation-rich and label-poor, the fix is a
forward-running settlement collector, and that is **Ryan-side**. Before accepting a Ryan-side
blocker, the cheap hypothesis deserved a falsification: **maybe we already hold the labels and are
simply not reading them.**

That hypothesis is not idle. `core/settlement_sources.py` — the ONE sanctioned answer to "is this
market's outcome known?" — publishes its own blind spot in its docstring: its
`undeclared_settlement_dirs()` guard matches **directory names**, and therefore *"structurally
CANNOT detect a family that hides settlement inside another family's record schema"*. Three of its
ten declared sources are exactly that shape. A zero from that guard is precision evidence, never
recall. Nobody had ever looked at the **fields**.

## 1. Method

`core/result_evidence.py` (new) is a field-level detector, deliberately dumb: walking a decoded
record, a dict node yields evidence when it carries a `result` key with a **non-empty** string
(Kalshi writes `""` on an unsettled market — the exchange's own "not yet", counted separately as
`schema_only`), or a `status` in `{settled, finalized, determined}`. `closed` is **not** terminal
and is counted apart: trading stopped is not an outcome known. A label is attributed only when the
record itself supplies a ticker (own `ticker`/`market_ticker` field, or a ticker-shaped map key);
evidence with no ticker in reach is counted as `unattributed` and never guessed — a label you
cannot join to a book is not coverage. Binary classification is delegated to
`core.settlement.is_binary_result` (L52's allow-list), never re-derived.

`scripts/settlement_source_recall_audit.py` streams **every committed `.json`/`.jsonl` file in every
family** under `tape/`: **31 families · 2,135,008 lines · 0 malformed**. It then asks the question
that matters — not "how many labels" but "how many labels **land on a population a probe could
score**".

## 2. F1 — the gap is real: two undeclared capture families, 367 net-new labels

| family | binary-labeled tickers | resolver overlap | agreement | net new | class |
|---|---|---|---|---|---|
| `tape/sports_history/` | 341 | **0** | n/a (no overlap to check) | 341 | undeclared, capture |
| `tape/sports_history_s7/` | 291 | 4 | **4/4 = 100%** | 287 | undeclared, capture |
| `tape/sports_clv_s7/` | 167 | 3 | **3/3 = 100%** | 164 | undeclared, **derived artefact** |

`sports_clv_s7` is this repo's own S7c probe output and is **excluded from the yield** by an
explicit table: declaring a derived artefact would launder a number we computed back in as broker
truth. The two capture families are genuine — they carry Kalshi's own `result` field read back off
the exchange — and the sanctioned resolver cannot see either. **Union net-new: 367 tickers.**

Where a cross-check exists, the undeclared source **agrees with broker truth on every ticker**
(7/7 across the two overlaps). No disagreement anywhere, on any family.

## 3. F2 — the gap is worth almost nothing, and that is the finding

A label count is not evidence. What it buys:

| substrate | population | resolvable today | + net new | delta |
|---|---|---|---|---|
| `tape/orderbook_depth/` (the maker fill substrate) | 110,632 legs / 4,171 event units | — | **8 legs land** | **4 units** become fully labeled (0.10% of 4,171) |
| `tape/sports_pairs/` (every sports taker study's substrate) | 11,663 legs | 659 (5.6%) | **38 legs land** | 697 (6.0%) |

**367 net-new labels move the sports price substrate from 5.6% to 6.0% resolvable and the depth
substrate by four event units.** The census's routing decision survives intact: the sports label
famine is **real absence**, not a bookkeeping artefact, and it cannot be repaired from tape we
already hold.

## 4. F3 — the mechanism, which is new: it is a CADENCE property, not a coverage property

The negatives are sharper than the positives.

* **`tape/sports_pairs/` — 13,404 files, 31,016 captured market objects, `result` populated on
  ZERO of them, `status == "active"` on all 31,016.** The largest sports family carries the
  exchange's full settled-market schema and has never once observed it filled in.
* **`tape/universe_sweep/` — 1,100,000 records, 1,807 with `status == "closed"`, `settled` /
  `finalized` / `determined` on ZERO, a populated `result` on ZERO.** The full-universe sweep has
  watched markets stop trading 1,807 times and has never seen one resolve.

So the famine is not "we collect the wrong families". Every sports family we collect **would**
carry the outcome — the exchange puts it in the same object we already save. We never look again
after expiry. The label famine is a property of **when the collectors poll**, not of **what they
poll**, and the cheap repair is therefore a re-poll pass over already-known tickers rather than a
new family. (Collection change → Ryan/collector-side, out of an idle run's lane. Recorded, not built.)

## 5. What was BUILT so the gap cannot silently regrow

`scripts/invariants.py::_undeclared_result_family_issues` / `undeclared_result_family_warning` —
the **field-level complement** to `undeclared_settlement_dirs()`'s directory-name matcher, wired
into `--full` as a **non-gating stderr advisory**. It samples each family's newest file (capped
decode budget) and names any family carrying an attributed binary result while being neither
declared nor a known derived artefact. It fires today on both `sports_history` and
`sports_history_s7` (non-vacuity pinned by a test that also tells a future reader why it went
quiet if those families are ever declared).

Non-gating deliberately, on the L353 precedent: the trigger is a **data** condition (a collector
can write a new family at any hour) and the repair is a **considered** change to a resolver every
past verdict leaned on. Sampled, not exhaustive: a miss is expected and is stated in the warning
text — the exhaustive answer is the audit script.

**Not done, on purpose:** the two families were **NOT declared** as settlement sources this run.
Declaring changes the output of the single resolver that every prior data-adequacy verdict used
(Q24's 0/81 join, Q54's data gate, Q21 rounds #30/#31), so it is a two-agent, verifier-confirmed
change — and §3 says the payoff is four depth units. Recorded as a candidate, not executed.

## 6. Incidental defect found and fixed in this run's own code

The audit's first draft called `resolve_market_results(...)` **without** `root=`, so an audit
pointed at any other tree would have scored its labels against the repo's committed tape and
reported a fabricated 100% overlap. `scripts/invariants.py::_settlement_root_anchoring_issues`
(the L345/L348 gate) caught it as a **gating** failure before commit — the ratchet worked on brand
new code written by the run that was being gated. Repaired by re-exporting the anchored
`core.settlement_sources.DEFAULT_TAPE_ROOT` rather than re-declaring the relative string `"tape"`.

## 7. Redundancy (NOT verification) — and it found two bugs, both in itself

No `Task`/`verifier` subagent is dispatchable in this harness (the L287/L288/L290/L291/L295/L308/
L313/L325/L338 precedent), so the sanctioned fallback ran:
`scripts/settlement_source_recall_rederive.py` imports neither the audit, nor
`core.result_evidence`, nor `core.settlement_sources` (AST-pinned), finds results by **regex over
raw bytes** instead of decoding and walking, attributes by **position** instead of by structure,
and answers the overlap question **backwards** (does any declared source file mention the
candidate series at all?) instead of re-implementing the resolver.

It disagreed twice, and **both times the re-derivation was wrong** — which is the point of running
one: a nearest-**preceding** attribution rule under-counted `sports_history` 341 → 214 (these files
are written `sort_keys=True`, so `result` lands *before* `ticker` inside the same object), and a
reader that knew only `"ticker"` scored `sports_history_s7` at 0 (it names the field
`market_ticker`). After both repairs:

* every family's **line count** agrees (2,135,008), every family's **labeled-ticker count** agrees
  outside one published limit, `sports_pairs`'s 31,016 empty results agree, `universe_sweep`'s
  1,807 closed / 0 settled agree, and both leg populations agree exactly (110,632 depth, 11,663 price);
* the two substrate intersections **reconcile exactly**: the re-derivation counts all 371 candidate
  labels and the audit counts only the 367 net-new ones, and 371−367 = 12−8 = 42−38 = **the same 4
  tickers** (all World-Cup `-TIE` legs already resolvable through the q30 cache) — verified by set
  identity, not by arithmetic coincidence;
* **published limit, measured not hand-waved:** on ticker-KEYED maps with small objects (the six
  `qNN_settlement_cache` families) positional attribution shifts by 1–2 tickers (≤0.4%). Every
  family it touches is a DECLARED source the audit reads through the sanctioned resolver anyway, so
  it cannot reach any headline number. The reconciliation test excludes those families **by name**,
  never by loosening the assertion.

## 8. What this cannot show

Detection is key-name based on `result`/`status` only. A family encoding outcomes under any other
name — `winner`, `settled_to`, a bare numeric `expiration_value` — is invisible to both the audit
and the advisory. A clean run means *"no `result`/`status`-shaped undeclared source"*, never *"the
registry is complete"*. Stating it the other way round would recreate exactly the L165/L300 failure
this audit exists to close.

No price is persisted by any artifact here, so **no `price_source_tag` applies to this audit's own
outputs**; the labels it counts carry their sources' own tags (`broker_truth` where the source is a
read-back exchange result).

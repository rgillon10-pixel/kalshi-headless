# L214 → enforced: cross-venue resolution-terms provenance on the Fed pair tape

`2026-07-30` · research loop, **IDLE RUN**, idle-run policy (a) (convert an UNENFORCED lesson
into enforced code + tests) · protocol v3 · one read-only live collector pass, no strategy
claim, no bootstrap CI, no P&L, no registry status change, **0 proven edges**.

## The question

L214 (2026-07-28 tape audit, D2):

> *A cross-venue pairing can be confirmed correct at match time and be structurally unauditable
> at read time if only the matched IDs are persisted, not the matched terms.*

Concretely: `collection/polymarket_pairs.py::match_fed_pairs` pairs Kalshi's `*_50plus` bucket
against Polymarket's `*_50plus` bucket. Kalshi's side comes from a market TITLE reading
`">25bps"` — settlement region **[26, ∞) bps**. Polymarket's side comes from a `groupItemTitle`
reading `"50+ bps"` — settlement region **[50, ∞) bps**. A 26–49bp move settles **YES on one
venue and NO on the other**. Pairing them anyway is a defensible collection-time judgment (each
is that venue's own top bucket; a non-25bp-multiple Fed move is near-zero probability), but
`polymarket_macro_pairs.v1` persisted only `ticker` / `event_id` / `market_id`. So for a v1
record the asymmetry is not "checked and fine" — it is **NOT CHECKABLE AT ALL** from tape. The
only way to learn of it was to re-read collector source, which is exactly what L214 names.

Question this run answers: *can the two legs' settlement terms be compared from tape alone, and
how much of the existing tape can answer that question at all?*

## Why this run is an idle run

Full Q0–Q48 FILE-SHAPE rescan (L25): **0 eligible TODO/IN-PROGRESS items** — the sixth such zero
of 2026-07-30. The three nearest gates are still shut (Q36 `n_settled_events=2/10`; Q37 opens
~08-05; Q48/S55 still burst-gated). → **IDLE RUN, policy (a)**.

Of the **6** genuinely-open `**UNENFORCED**` rows at run start — L145, L213, L214, L221, L222,
L227, per the repo's own `invariants.stale_unenforced_recall_report()` — **L214** was chosen. It
is the only one both in-lane and EV-protecting for the next gate to open: `tape/polymarket_macro_pairs/`
is the **SIGNAL leg** of the burst-gated S55/Q48 probe, so a terms defect there contaminates the
statistic that probe will compute the moment its window opens. (L145 and L213 are Ryan policy
calls; L221/L222 are live collector write-path questions whose fix is a collector redesign, not
an enforcement; L227's remaining half is not statically assertable.)

## What was built

* **`collection/polymarket_pairs.py` — `polymarket_macro_pairs.v2`.** Fed pair records now carry
  v1 PLUS: `kalshi.title`, `kalshi.resolution_basis = "kalshi_rulebook"`, `polymarket.question`,
  `polymarket.group_item_title`, `polymarket.resolution_basis = "uma_oracle"`, and a
  `bucket_terms` block. `discover_polymarket_fed_events` now **carries** `groupItemTitle` through
  to tape (it previously read it to normalize the bucket label and discarded it — the exact layer
  at which the asymmetry disappears). **Provenance only:** not one price, size or tag field
  changed; both legs remain `price_source_tag: real_ask`.
* **`fed_bucket_terms()`** — new pure, offline function. Derives each leg's threshold from **its
  own recorded text** (never from the already-normalized bucket label), compares bps regions AND
  the `meeting_key` it presupposes, and returns `terms_equivalent` **True / False / None —
  never a guessed True**. Persists `compares: "bps_region+meeting_key"` and
  `meeting_key_checked`, so the block names its own scope. Absent or unparseable text on either
  side ⇒ `None` basis and `terms_equivalent: None` ("unknown", to be read as unaudited, not as
  agreement).
* **`scripts/polymarket_pair_terms_audit.py`** (+ `tests/test_polymarket_pair_terms_audit.py`,
  11 tests) — read-only census of how much of the tape can answer the L214 question at all. No
  gate, no network, no writes, no verdict.
* **Readers widened to accept v1 AND v2:** `scripts/q48_s55_fomc_lag_probe.py`
  (`ACCEPTED_SCHEMA_VERSIONS`, a new `n_by_schema_version` computed from records actually
  loaded, corrected `depth_note`), `scripts/q31_cross_venue_arb_probe.py`
  (`RESOLUTION_EQUIVALENT_SCHEMAS`, `n_by_schema_version`),
  `scripts/s17_leadlag_probe.py` (docstring only — it filters structurally, not on the schema
  string).
* **One live read-only collector pass** (`capture_id` `20260730T183708Z`) appended 20 v2 pair
  lines + 1 capture-summary line to `tape/polymarket_macro_pairs/dt=2026-07-30.jsonl`.
  Append-only, verifier-checked: `HEAD`'s copy of that file is a **byte-exact prefix** of the new
  one.

## The census — every qualifier attached

Command: `python3 scripts/polymarket_pair_terms_audit.py`, run **2026-07-30T20:22:13Z**, over
`tape/polymarket_macro_pairs/` **in this working tree**: 24 day-files, 9,612 lines, **0 malformed**.

| quantity | value | qualifier |
|---|---|---|
| pair records | **9,575** | working tree, not `HEAD` |
| capture-summary records (L212) | 37 | counted separately, never as pairs with missing terms |
| by schema | **9,555 `polymarket_macro_pairs.v1` + 20 `...v2`** | the 20 v2 are THIS RUN's own uncommitted addition |
| unauditable-by-construction | **9,555** | no `bucket_terms` field at all — never asked |
| `terms_equivalent: true` | **12** | 3 bucket classes × 4 meetings |
| `terms_equivalent: false` | **8** | `hike_50plus` + `cut_50plus`, 4 each |
| `terms_equivalent: null` (undecidable) | **0** | block present, no verdict — none occurred |

Partition identity, published in the report itself and asserted in test:
`12 + 8 + 0 + 9,555 (no terms block at all) = 9,575`. It holds per bucket too: five buckets ×
`4 + 0 + 0 + 1,911 = 1,915`.

**PROVENANCE QUALIFIER — do not drop it.** At `HEAD` (`7871d03`) the **committed** tape holds
**9,555 v1 pair records and ZERO v2** (`git grep -c 'polymarket_macro_pairs.v2' HEAD -- tape/polymarket_macro_pairs/`
→ no matches, same timestamp; the v1 sum at `HEAD` → 9,555). So: never write "9,575 records
committed", and never write "99.79% of the committed population". Against the population
**committed at `HEAD`** the unauditable share is **100%**. The 99.79% (9,555 / 9,575) figure is a
**working-tree** number and must be labelled as such. This is a forward fix only — pre-v2 tape
stays unauditable forever, which is an absence of evidence, not a clean bill of health.

### The asymmetry, exactly

The 8 `false` records are exactly the `hike_50plus` and `cut_50plus` buckets, **4 each, across
the 4 meetings 2026-09 / 2026-10 / 2026-12 / 2027-01**. The persisted note, verbatim from tape:

> `resolution terms differ: kalshi title 'hike_gt_25bps' settles YES over [26, inf)bps, polymarket 'increase_gte_50bps' over [50, inf)bps`

and its mirror for `cut_50plus` / `decrease_gte_50bps`. Example record (`dt=2026-07-30.jsonl`):
Kalshi title *"Will the Federal Reserve Hike rates by >25bps at their January 2027 meeting?"* vs
Polymarket `groupItemTitle` *"50+ bps increase"*.

### UNIT COUNT — this is not n=20

All 20 v2 records come from **ONE capture pass**, and `terms_equivalent` is a deterministic
function of the parsed **threshold basis pair** `(kalshi_basis, polymarket_basis)` — NOT of the
literal (title, label) pair, which is distinct on all 20 only because the Kalshi title embeds the
meeting month. Collapsing on the parsed bases:

**5 bucket classes — 3 equivalent, 2 provably not — n=4 each. 20 = 5 classes × 4 meetings × 1 pass.**

And the two non-equivalent classes are the **same** `>25bps`-vs-`>=50bps` rule mirrored
hike/cut, so the number of **independent asymmetry mechanisms is 1, not 2**. Reading "2" as
corroboration would be wrong.

## Probe impact — tape-constant vs data-driven, stated separately

**Tape-constant (the code claim).** Held tape-constant — old code vs new code on a **frozen**
tape, verified by a `git worktree` differential — q48 / q31 / s17 outputs are **byte-identical**.
The reader widening is additive and changes no computation.

**Data-driven (the data claim).** The same diff also appends 20 records, which moves the default
invocations. It is FALSE to say "no probe's numeric output changed":

| probe | quantity | before | after |
|---|---|---|---|
| q48 | `n_fed_records` | 9,555 | 9,575 |
| q48 | `n_passes` | 640 | 641 |
| q48 | `mean_abs` | 0.0206128 | 0.0206215 |
| q48 | headline `all` | +2.061¢ | **+2.062¢** |
| q31 | observations | 15,905 | 15,925 |
| q31 | pooled mean net | −0.03244 | **−0.03246** |
| q31 | 95% CI | [−0.04006, −0.02540] | **[−0.04007, −0.02541]** |
| s17 | contemporaneous ρ | 0.43582 | 0.43724 |
| s17 | kalshi-leads ρ | 0.019706 | 0.015051 |

Every price on both legs is **`price_source_tag: real_ask`** — 9,575 / 9,575 records, zero
synthetic, zero midpoint. **These are DESCRIPTIVE / diagnostic statistics. They are NOT a
strategy CI and NOT a P&L.** No verdict is drawn from them.

## What this does and does not settle

* Settles: whether a *reader of tape* can compare the two legs' bps regions for a given meeting.
  From v2 on: yes, with the verdict, the evidence text, and the scope all persisted.
* Does **not** settle: contract-level settlement equivalence. The legs are adjudicated by
  different bodies — `kalshi_rulebook` vs `uma_oracle`, now persisted per leg — so even a
  `terms_equivalent: True` leaves adjudicator risk unmeasured. `compares:
  "bps_region+meeting_key"` exists precisely so nobody reads it as more than it is.
* Does **not** repair v1 tape. 9,555 records remain unauditable by construction.

## Consequences

* **EV-protecting fact for S55 / S17 / Q48:** the two `*_50plus` Fed buckets are **provably not
  the same contract across venues**. Any future statistic that pools them cross-venue is
  comparing different contracts, and a gap measured on that pair is partly a terms difference,
  not a lag.
* **No registry status flipped.** S55 stays `collect-and-revisit` (burst-gated, n=0, no CI, no
  verdict); S17 stays `data-collecting`. Q48's own verdict and gate are **unchanged**.
* **No CI, no P&L, no verdict, 0 proven edges.** The bar has not moved.

## Two-agent rule

Two independent `verifier` rounds ran against this diff.

**Round 1 — CONFIRMED-WITH-CORRECTIONS.** Confirmed: every v1 field byte-preserved under
identical inputs; the tape append is genuinely append-only (`HEAD`'s file a byte-exact prefix);
both legs `real_ask`; the census exactly reproduced by the verifier's own throwaway stdlib
parser; house rules clean. **REFUTED as worded:** (a) the claim that "the L214 row is flipped" —
it was not yet flipped at that point (this bookkeeping milestone is what flips it); (b) the claim
that "no probe output changed" — see the tape-constant / data-driven split above. **7 defects**
found; the collector lane fixed the 4 code defects (D3 → L239, D4 → L240, the unverified join-key
presupposition → L241, plus the probe-impact wording).

**Round 2 — CONFIRMED-WITH-CORRECTIONS.** All four fixes re-derived and hold, including a
**1,764-combination fuzz** finding **0** cases of `terms_equivalent: True` with both meeting keys
present and differing, and verdict-neutrality of the fix on the 20 already-written v2 lines.
Remaining corrections, applied in this document and in the ledger: the *"committed"* provenance
qualifier (→ L242) and the mechanism-count wording (→ L243). One cosmetic note left as-is: q31's
`n_by_schema_version` is emitted to `--json-out` only, not to human stdout.

## Reproduce

```
python3 scripts/polymarket_pair_terms_audit.py
python3 -m pytest -o addopts='' -q tests/test_polymarket_pair_terms_audit.py
python3 -m pytest -o addopts='' -q tests/test_polymarket_pairs.py
python3 -m pytest -o addopts='' -q tests/test_q48_s55_fomc_lag_probe.py tests/test_q31_cross_venue_arb_probe.py tests/test_s17_leadlag_probe.py
git grep -c 'polymarket_macro_pairs.v2' HEAD -- tape/polymarket_macro_pairs/
python3 scripts/invariants.py --full
```

Lessons: **L214** enforcement cell moved `UNENFORCED` → `test` (lesson text unchanged, original
cell preserved verbatim inside the new one, per L152); new **L239** (an auditability predicate
must key on the exact field the deriving function reads), **L240** (never pool "never asked" with
"asked, undecidable"), **L241** (a public verdict function must verify its presupposed join key),
**L242** (`UNENFORCED` — a working-tree census must never be reported as "committed"; named
mechanizable candidate), **L243** (`protocol` — tape-constant vs data-driven reporting, and
record count ≠ sample size when a verdict is a parsed function of a label).

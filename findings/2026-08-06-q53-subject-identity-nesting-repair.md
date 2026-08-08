# A shared `event_ticker` is not a strike ladder — the nesting premise, repaired and measured

`2026-08-06` · research loop, **Q53** (milestones 1–3) · main-context build (no `Task`/subagent
tool in this harness) · **verdict class: TOOLING repair (milestones 1–2) + DATA-ADEQUACY
verdict (milestone 3, PROVISIONAL). No registry flip, no bootstrap CI, no kill. Still 0 proven
edges.**

## The defect (L291, measured 2026-08-06 earlier the same day)

`scripts/anomaly_sweep.py::check_monotonicity` — the repo's oldest live scanner — assumed that
markets sharing an `event_ticker` and a `strike_type` are rungs of ONE strike ladder on ONE
underlying, so that a narrower strike's YES-region is a subset of a wider one's and
`buy YES(outer) + NO(inner)` pays a guaranteed ≥ $1. **Kalshi packs MULTIPLE SUBJECTS under one
`event_ticker`.** After the L290 fillability guard removed 43,025 `$0.00`-leg records, 13 of
43,038 recorded anomalies survived — and 100% of them paired two different subjects (two tennis
players' game spreads, three batters' props, three cities' rain markets). Buying YES(subject A)
+ NO(subject B) is a naked directional bet, not an arb.

---

## Milestone 1 — the subject-identity test, and BOTH its error rates

`core/subject_identity.py`. Three-valued on purpose (`PROVEN_SAME_SUBJECT` /
`DIFFERENT_SUBJECT` / `UNVERIFIABLE`), because nesting must be **proven**, never merely
un-disproven — the caller refuses on two of the three.

### What signal it actually uses

**The market's own descriptive text (`title` / `subtitle` / `yes_sub_title`), anchored to the
market's own strike bounds. It parses NO ticker suffixes** — the shortcut Q1's build note and
the collector house rule both warn against ("structural confirmation, not ticker suffixes"; the
KXFEDDECISION ">25bps as 26" trap). The only ticker involvement anywhere is the caller's
`event_ticker` grouping, which predates this work.

Two conditions, both required:

1. **Skeleton equality** — the alphabetic/punctuation content, with numeric tokens removed, must
   match. This does the discriminating work: two subjects differ in *words*
   (`Will **Navone** win ... than **Struff**?` vs `Will **Struff** win ... than **Navone**?`;
   `**Wilyer Abreu**: 4+ hits...` vs `**Tsung-Che Cheng**: 5+ hits...`), and no numeric
   normalization can repair an alphabetic difference.
2. **Strike-attributable numeric differences** — wherever the two numeric token sequences differ
   at the same index, there must exist a shared offset `d` with `a_token == a_strike + d` and
   `b_token == b_strike + d`.

Condition 2 exists because **Kalshi's strike LABEL is routinely offset from its strike VALUE by
a per-family constant**, which a naive "the number in the text must equal the strike" rule would
trip over — the KXFEDDECISION trap, one family over:

| family | published label | `floor_strike` | offset |
|---|---|---|---|
| `KXHIGHNY` (daily temp) | `97° or above` | `96` | `+1` |
| `KXTEMPNYCH` (hourly temp) | `82° or above` | `81.99` | `+0.01` |
| `KXCPICORE` | `Will CPI Core rise more than 0.3% in August?` | `0.3` | `0` |

The comparison is **positional**, not a global mask, for a second measured reason: a global
"blank every number equal to the strike" normalizer would, on a `KXGDP` rung with
`floor_strike == 2.0` and title *"...more than 2.0% in Q2 2026?"*, also blank the `2` in `Q2`
while its sibling rung (`floor_strike 0.3`) kept it — inventing a false refusal out of nothing.

### Error rate 1 — FALSE REFUSE (refusing a genuine ladder: silently deletes real arbs)

Scored in `check_monotonicity`'s own shape (within one event, within one `strike_type` ∈
{greater, less}, all pairs), closed window `dt ≤ 2026-08-04`, exhaustive (0 classes sampled):

| genuine-ladder corpus | pairs | refused | rate |
|---|---|---|---|
| `tape/econ_prints/` (title CONTAINS the strike) | 2,348 | **0** | **0.00%** |
| `tape/weather_books/` (sub-title only, offset labels) | 31,986 | **0** | **0.00%** |
| `tape/crypto_hourly/` | 0 *(by construction)* | 0 | n/a |
| **total** | **34,334** | **0** | **0.00%** |

`crypto_hourly` contributes zero pairs *by construction*, not by omission: each crypto event
carries exactly one `greater` and one `less` rung, everything else is `between`. Reported rather
than hidden inside a total. It does contribute to the bracket shape (802/802 events admitted),
as does `econ_prints` (27/27).

### Error rate 2 — FALSE ADMIT (admitting a cross-subject pair: manufactures fake arbs)

Ground truth from a rule **independent of the predicate** — a player-name regex, not a skeleton
comparison — over the exact counterexample families L291 named, sourced from committed
`tape/universe_sweep/` titles:

| labeled corpus | true cross-subject pairs | **false admits** | true same-subject pairs | **false refuses** |
|---|---|---|---|---|
| `KXATPGSPREAD` (tennis game spreads) | 4 | **0** | 5 | **0** |
| `KXMLBHRR`/`HIT`/`TB` (batter props) | 2,360 | **0** | 146 | **0** |
| **total** | **2,364** | **0 (0.00%)** | **151** | **0 (0.00%)** |

The hard case is inside one event, and it is in the corpus: `KXMLBHRR-26JUL171335TBBOSG1` holds
Wilyer Abreu's 1+/2+/3+/4+ rungs *alongside* Tsung-Che Cheng's, and
`KXATPGSPREAD-26JUL22STRNAV` holds both directions of one match *alongside* Navone's own
2.5/5.5 ladder. The predicate refuses the cross-player pairs and admits the within-player ones,
with no per-series table.

### Platform-wide cut, reported honestly rather than as a rate it cannot support

All within-event pairs over `tape/universe_sweep/` (703,235 distinct markets, 545,857 events,
68,634 with ≥2 markets, 1,190,426 pairs, 0 malformed lines):

| bucket | pairs | share |
|---|---|---|
| decided REFUSE (alphabetic difference — undecidable by no numeric rule) | 932,965 | 78.37% |
| decided ADMIT (byte-identical descriptive text) | 15 | 0.0013% |
| **INDETERMINATE** (same words, different numbers, corpus persists no strike) | 257,446 | 21.63% |

`universe_sweep` carries titles but **no** `floor_strike`/`cap_strike`, so a pair whose words
match and whose numbers differ is genuinely undecidable *on this corpus*. That is a corpus
limit, not a predicate limit — the live scanner reads `/markets`, which does carry the strike
fields — but "assume it would be fine" is the move this repo forbids, so both residual buckets
were enumerated:

* **All 15 decided-ADMITs are correct.** Every one is `KXATPGTOTAL` — *"Jan-Lennard Struff vs
  Mariano Navone: Total Games"* — genuine rungs of ONE match's total-games ladder whose strike
  lives in a field this family does not publish. **0 false admits among decided pairs.**
* **The indeterminate bucket spans 24,094 distinct skeletons**, dominated by two classes that
  both resolve correctly live: `KXMVECROSSCATEGORY` / `KXMVESPORTSMULTIGAMEEXTENDED` parlay
  combos (no `strike_type` at all — they never reach `check_monotonicity`, and would be
  `UNVERIFIABLE` if they did) and `KXGOLDH` / `KXSILVERH` / `KXWTIH` commodity hourlies
  (genuine single-subject ladders whose differing number IS the strike).

### The measurement that changed the design

Scoring whole ladders on the sub-title refuses **880 of 1,591** genuine single-city weather
ladders — a **55.3% false-refuse rate** — because a MECE ladder's rungs legitimately carry three
different sub-title *grammars* (`88° or below` / `95° to 96°` / `97° or above`) for one city.
A sub-title describes the RUNG; only the title describes the SUBJECT. Hence two documented field
sets: `DESCRIPTIVE_FIELDS` for same-`strike_type` pairs, `SUBJECT_FIELDS_CROSS_STRIKE_TYPE`
(title only) for the cross-type bracket shape. The wrong-field-set number is kept in the report
so the reason for the split stays falsifiable instead of becoming folklore. Honest limit:
`tape/weather_books/` persists no `title`, so the field set the scanner actually uses is
`UNVERIFIABLE` on that family (1,591/1,591) — the live scanner reads `/markets`, which does
carry it.

---

## Milestone 2 — wired, behind the same counted-refusal discipline as L290

`scripts/anomaly_sweep.py`, checks 1 and 2 (check 3 is exempt by construction: its implication
graph is hand-curated against both markets' settlement rules text, a stronger nesting proof than
any text comparison). Two new refusal keys, additive to `anomaly_sweep.v1`, no existing field
changed in shape or meaning:

* `n_cross_subject_pair_refusals` — "these are provably two different subjects".
* `n_subject_unverifiable_refusals` — "I could not tell".

Kept **separate on purpose**: collapsing them would let a pass that could not read anything
report the same shape as a pass that proved everything clean — the exact misreading L288's
`n_anomalies: 0` invited. Flagged anomalies now also persist `subject_identity_reason`, so a
future replay can audit *why* a pair's premise was accepted; the inability to do that for
historical records is the whole reason this repair needed a corpus rather than a tape replay.

The guard runs **last** in `check_monotonicity` (after fillability and edge materiality) so the
live refusal ledger's funnel is identical to the published committed-tape replay's
(43,038 → 43,025 → 13 → 0) rather than two decompositions of one population that never
reconcile, and so `n_cross_subject_pair_refusals` counts pairs that *would otherwise have been
flagged* — the actionable number.

Replay of all committed tape, closed window `dt ≤ 2026-08-04`, 26 capture-days:

| stage | records |
|---|---|
| recorded `cross_strike_monotonicity` anomalies | 43,038 |
| refused — leg not on the tradeable price grid (L290) | 43,025 (99.9698%) |
| refused — sub-tick float residue (L290) | 0 |
| survive both PRICE guards | 13 / 6 ticker pairs |
| refused — nesting premise not proven (L291, this run) | **13** |
| **survive all three guards** | **0** |

Read the mechanism honestly: a committed anomaly record persists only
`outer_ticker`/`inner_ticker`, with no title and no strike bounds, so the replay **cannot** prove
or disprove subject identity from the tape. All 13 are refused as `UNVERIFIABLE` — absence of
evidence, recorded as such, never upgraded to evidence of absence. The proof that the guard
genuinely *separates* the classes is fixture-side and corpus-side (above), not replay-side.

---

## Milestone 3 — S3 / S15: an explicit DATA-ADEQUACY verdict (PROVISIONAL)

The exposure denominators, computed from committed `tape/anomalies/` over `dt ≤ 2026-08-04`:

| quantity | value |
|---|---|
| capture-days / records | 26 / 248 |
| market-observations scanned (sum) | 4,908,300 |
| monotonicity group-checks | 2,210 |
| bracket group-checks | 2,210 |
| **implication pairs checked (S15)** | **0** |
| records with `markets_truncated: True` | **247 / 248** |
| records with `completeness_ok: True` | 248 / 248 |

### S3 — cross-strike monotonicity

Zero verified fillable arbs in 26 capture-days. Taking the **capture-day** as the independent
unit (passes within a day re-observe overlapping quote states — L221's byte-redundant re-capture
inflation is the precedent), the rule-of-three 95% upper bound on the arrival rate is
**≤ 3/26 = 0.115 per capture-day** (≤ ~1 per 8.7 days), or **≤ 3/2,210 = 0.00136 per
monotonicity group-check**. Independently corroborated on a family this delegate's coverage may
never have reached: L287's executable econ-ladder screen found **0** fillable crossings in
**849,958** nested pairs, the best of only 9 sub-$1-gross pairs being **−$0.02 net**.

**This is NOT a kill, and the reason is the denominator, not the numerator.** 247 of 248 passes
are truncated at the 20,000-market cap and persist no scanned-ticker manifest, so the fraction of
the platform actually swept is **unmeasurable from the tape** — a rate whose denominator is
unknown cannot falsify anything. Verdict: **S3's evidence base for being alive is now zero, and
its standing kill clause is unreachable on current instrumentation.** The blocker is
instrumentation (persist the scanned event/ticker inventory per pass), not elapsed days.

### S15 — cross-event logical implication

**Every one of the 243 committed records carrying the counter reports `n_implication_pairs_checked:
0`.** That is 0 pairs *checked*, not N pairs checked with 0 hits — the row's "0 hits" carries no
information at all, and its kill clause ("kill if 0 fee-clearing hits in 60 days") can never
fire meaningfully over an empty denominator.

The registry row claims a 2026-07-05 live validation of "38 pairs / 40 open markets". **That
validation is not reproducible from committed tape**: no record ever reports a nonzero pair
count. Meanwhile the graph's only curated family, `kxwcround_progression`, is time-boxed by its
own `audit` field ("World Cup 2026 ends 2026-07-19, after which this family stops generating live
pairs"), and `tape/universe_sweep/` (2026-07-17 onward) contains **zero** World Cup markets. What
*is* checkable: `tape/polymarket_pairs/` holds **48 distinct `KXWCROUND` tickers** across
2026-07-06 … 07-14, and **all 48 match the family's `ticker_regex` and rank map** — so the graph
would have generated pairs had those markets been inside the scanned slice. The most likely
explanation is the same 20,000-market truncation, but the tape cannot decide it.

Verdict: **DATA-INADEQUATE, categorically.** No kill is possible and no support exists for
reading "0 hits" as evidence. The blocker is curation (the graph has had no live family since
2026-07-19) plus the same coverage instrumentation S3 needs.

### Two-agent disposition

**PROVISIONAL — not verifier-CONFIRMED.** No `Task`/subagent tool exists in this harness, so no
independent `verifier` could be dispatched (the L287/L288/L290/L291 precedent). Per protocol,
**no registry status was flipped**: S3 and S15 both stay `data-collecting`, and each row carries
a dated PROVISIONAL prose note instead. Every number above was instead re-derived on a second,
independent code path (naive O(n²) pair enumeration with separate loaders and no
skeleton-class fast path) and agreed exactly: econ 2,348/0, weather 31,986/0, replay
43,038 → 13 → 0.

### One retraction, made here rather than published

An earlier draft of the S15 finding asserted a *chronology* — that check 3 and its config
shipped on 2026-08-02, after the World Cup ended — derived from `git log -S`. **That inference
was wrong and is withdrawn.** This working copy is a **shallow clone** (50 commits, earliest
2026-08-02), so `git log -S` reports the truncation boundary, not the fact. Every S15 claim above
is derived from committed tape and config text only. The failure mode is now L297.

---

---

## Verifier disposition (2026-08-07)

**CONFIRMED-WITH-CORRECTIONS.** An independent `verifier` re-derived every load-bearing number
in this finding on separate code paths (a from-scratch replay of the 43,038→13→0 funnel, an
independent ticker-entity→title-subject map over `universe_sweep`, a fresh run of
`subject_identity_corpus_audit.py` diffed byte-for-byte against the committed report) and
adversarially probed the framing (do the 13 `UNVERIFIABLE` survivors actually hide a real arb?
does the false-admit ground truth have blind spots? is "0 pairs checked" consistent with the
actual check-3 code path?). **Every number reproduced exactly, both verdicts survive every
attack, and the two-agent rule is satisfied**: S3 stays `data-collecting`, killable only once a
scanned-ticker manifest exists; S15 stays `data-collecting`, `DATA-INADEQUATE`, unkillable while
its curated family is time-boxed to a market with zero committed 2026-07-17+ coverage. Full
pytest (3,313/3,313) and `invariants.py --full` both green on the verified tree.

**Three claims in this finding were factually wrong; corrected here rather than silently
edited, per this document's own retraction precedent above:**

- **D1 — the platform-wide decided-ADMIT family attribution was wrong.** "All 15 decided-ADMITs
  are correct... Every one is `KXATPGTOTAL`" understated the population: independent
  enumeration of all 15 (not the report's 5-example-per-reason cap) finds **9 are
  `KXATPGTOTAL`** (3 each on `STRNAV`/`FARBUE`/`KOUWIN`) and **6 are
  `KXWNBATOTAL-26JUL22LVWSH`** ("Las Vegas vs Washington", total-points rungs `-192`/`-196`/
  `-199`/`-203`). The *correctness* claim survives — the WNBA six are genuine rungs of one
  game's total-points ladder, so 15/15 decided-ADMITs are still all correct — only the "every
  one is X" family attribution was wrong. Root cause: `reports/subject_identity_corpus_audit.json`
  caps stored examples at 5 per reason, all of which happened to be `KXATPGTOTAL`; the 5→15
  generalization was never re-checked against the full population. General lesson: a capped
  `examples` list in a JSON report is a sample, not the population — re-enumerate before writing
  "every one."

- **D2 — the KXWCROUND ticker-count/window claim was internally inconsistent.** "48 distinct
  `KXWCROUND` tickers across 2026-07-06 … 07-14" does not hold: distinct tickers per day are
  07-04: 48 · 07-05: 40 · 07-06: 36 · 07-07: 28 · 07-08: 16 · 07-10: 13 · 07-11: 10 · 07-12: 10 ·
  07-13: 4 · 07-14: 4 · 07-15: 2 (independently re-derived, exact). The union over the *claimed*
  window (07-06..07-14) is **36**, not 48; all 48 appear only if the window is widened to
  07-04..07-15, and in fact all 48 are present on `dt=2026-07-04` alone. The qualitative point
  this supported — that markets matching the family's ticker regex existed on committed tape
  outside the scanned slice — still holds (36 or 48, both are nonzero and both are outside the
  slice `check_cross_event_implication` actually ran against), so the S15 verdict is unaffected.

- **D3 — "the '38 pairs / 40 open markets' validation is not reproducible from committed tape" was
  false, and this is the load-bearing correction.** `tape/polymarket_pairs/dt=2026-07-05.jsonl`
  holds exactly **40** distinct `KXWCROUND` tickers over 14 entities (12 teams with QUAR+SEMI+
  FINAL rungs, FRA and MAR with SEMI+FINAL only); run through the family's own `ticker_regex` and
  `round_order_raw_suffix_to_rank` in `config/implication_pairs.yaml`, that generates exactly
  **12×3 + 2×1 = 38 pairs**. Both numbers reproduce to the digit (independently re-derived here
  a second time). The defensible claim was narrower than what was written: not reproducible from
  `tape/anomalies/` (true — no record there ever reports a nonzero pair count), but fully
  reproducible from `tape/polymarket_pairs/`. **This correction strengthens, not weakens, the S15
  verdict**: the sweep genuinely ran on 2026-07-05 (3 committed `tape/anomalies/` records that
  day) while 40 matching markets sat on tape and 38 pairs were mechanically generatable from them,
  and still recorded `n_implication_pairs_checked: 0` — the truncation/scope explanation for that
  zero goes from "most likely" to positively corroborated, not merely un-refuted.

**Caveats surfaced but not requiring a verdict change**, recorded so they are not silently lost
(full detail in the verifier's own report, referenced from `kb/lessons/00-lessons.md` L303):
the replay's final funnel stage (13→0) is definitional, not measured, because the committed
`tape/anomalies/` schema cannot carry descriptive text at all — the S3 registry row's prose reads
this stage as evidence, which it is not (the corpus-side proof is the real evidence, and it is
sound); and `check_cross_event_implication`'s own subject-identity proof still derives from a
ticker-suffix regex (`_round_progression_pairs`'s `entity` capture group) — the exact shortcut
`core/subject_identity.py` was built to avoid — which costs nothing today (0 pairs ever checked)
but goes live the moment a family with more coverage (e.g. Q55's `KXMARMADROUND`, 1,120 pairs)
enters the sweep's scanned slice.

## Reproduce

```
python scripts/subject_identity_corpus_audit.py --max-day 2026-08-04   # -> reports/subject_identity_corpus_audit.json
pytest -o addopts='' -q tests/test_subject_identity.py tests/test_anomaly_sweep.py
pytest -o addopts='' -q tests/test_anomaly_sweep.py -k acceptance       # the committed-tape replay
```

Provenance: every number is computed from committed tape (`tape/anomalies/`,
`tape/econ_prints/`, `tape/weather_books/`, `tape/crypto_hourly/`, `tape/universe_sweep/`,
`tape/polymarket_pairs/`) over the closed window `dt ≤ 2026-08-04`, at the `price_source_tag`
each collector persisted (`real_ask`). No network, no orders, no credentials, `execution/`
untouched.

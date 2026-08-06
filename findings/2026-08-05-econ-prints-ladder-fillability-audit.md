# 2026-08-05 — `tape/econ_prints/`: a `real_ask` tag certifies provenance, not fillability

Idle-run policy (c) (LOOP-QUEUE.md v3): a data-quality deep-dive on one tape family. Steps
0/0a/0b were established by the calling session (history-integrity PASS at `5db5b4f`, no open
PR claims queue work, full-sweep in flight elsewhere); own re-verification of policy (a):
`invariants.py --full`'s L152 stanza still reads `n_open_unenforced = 4` (L213/L221/L222/L282,
all Ryan-lane/credential-gated), so (a) remains exhausted and (b) is empty (Q51 m3 gated to
2026-08-10). Read-only, offline, DESCRIPTIVE ONLY: **no gate, no bootstrap CI, no P&L, no
strategy verdict, no registry status changed.** `kb/strategies/00-index.md` is untouched.

**Correction to the milestone's premise.** This is NOT the family's first audit — it is the
third. `findings/2026-07-15-econ-daily-cadence-gap-dataquality.md` (cadence/blackout) and
`findings/2026-07-29-econ-prints-tape-audit.md` (D1-D7: invocation provenance, the hour-gate,
redundancy, `expiration_value` types) came first, and produced L221/L222/L224. Both audited
**presence** — does the tape exist, how often, from where. Neither audited **content**: whether
a persisted price on an econ ladder is a price a consumer could act on. That is this pass.

Artifacts: `scripts/econ_prints_ladder_fillability_audit.py` (read-only, `--max-day` closes the
window), `tests/test_econ_prints_ladder_fillability_audit.py` (29 tests: 16 fixture + 13 real-
tape acceptance), `reports/econ_prints_ladder_fillability_audit.json`.

Window: `--max-day 2026-08-04`. 25 day-files, `dt=2026-07-05` … `dt=2026-08-04`, **2,290 lines
/ 457 captures / 126,841 open-ladder strikes**.

---

## Part 1 — internal integrity: clean, and cleaner than the families around it

| check | result |
|---|---|
| parse errors / blank-line torn writes | **0 / 0** over 2,290 lines |
| schema drift | **0** — `econ_prints.v1` on 2,290/2,290 |
| series balance | exactly **458 records each** for all 5 series |
| byte-identical duplicate LINES (L285's class) | **0** |
| duplicate `(capture_id, series_key)` | **5**, all on the single `20260716T092842Z` collision the L210 advisory already names — no new occurrence |
| `price_source_tag` | **126,841/126,841 `real_ask`** on strikes, **1,916/1,916 `broker_truth`** on settled records, **452/452 `synthetic`** on GDPNow nowcasts, **0 untagged** |
| null required price fields | **0** |
| prices outside `[0,1]` / off the whole-cent grid | **0 / 0** |
| crossed books (`yes_bid > yes_ask`) | **0** |
| `$0.00` ask legs (L105's class) | **0** — `_capture_strikes` drops a market with no `yes_ask_dollars` |

One new integrity defect, minor: **3 within-file `captured_at` inversions** (`dt=2026-07-05`
line 16 jumps back 5.3 h; `dt=2026-07-14` line 6 and `dt=2026-07-16` line 6 back ~10 and ~8
minutes). The day file is **append-ordered, not time-ordered** — a consumer that replays this
family line-by-line as a time series gets an out-of-order feed. The 07-14/07-16 pair is the
concurrency L221/L222 already diagnosed; the 07-05 one is wider than any single pass.

## Part 2 — the headline: 44.4% of the `real_ask` strikes are one-sided books

Kalshi mirrors a NO order into the same book as a YES order, so the four persisted BBO fields
should carry only two degrees of freedom. Measured, not assumed:

* `yes_ask + no_bid == 1` on **126,841 / 126,841** strikes (0 violations)
* `no_ask + yes_bid == 1` on **126,841 / 126,841** strikes (0 violations)

`no_ask` and `no_bid` therefore carry **zero independent information**. Consequence: a strike
with no resting YES bid reports `no_ask == $1.00`, and a strike with no resting NO bid reports
`yes_ask == $1.00` — **a quote pinned by the ABSENCE of a bid, not by anyone's belief.**

| class | n | share |
|---|---|---|
| two-sided (`yes_bid > 0` and `yes_ask < 1`) | 70,573 | 55.64% |
| only a NO bid rests (`yes_bid == 0`) | 52,083 | 41.06% |
| only a YES bid rests (`yes_ask == 1.00`) | 3,889 | 3.07% |
| nothing rests at all | 296 | 0.23% |
| **one-sided (any of the last three)** | **56,268** | **44.36%** |

Median `yes_ask − yes_bid` spread is **$0.06**, but the mean is **$0.3179** and p90 is **$0.98**
— the L31 shape exactly. Two-sided AND inside a 5¢ spread: **41,684 / 126,841 = 32.86%**.

**All 126,841 carry the same tag: `real_ask`.** The tape persists no field separating the
32.9% a consumer could act on from the 44.4% that are the absence of a market. The
discriminator (`yes_bid > 0 AND yes_ask < 1`) is derivable, but only by a consumer who already
knows to derive it — which is the same trap L286 recorded one family over.

## Part 3 — the screen gap: 13.06% naive, 0.00% executable

Every econ strike is `strike_type: "greater"`, so a higher threshold's YES-region is a strict
subset of a lower one's. Two screens over the same ladders:

**Naive** (`yes_ask` must be non-increasing in `floor_strike`; ADJACENT rungs only — the most
conservative form):

* **15,234 / 116,632 adjacent pairs = 13.06%**
* **6,152 / 10,209 ladder snapshots = 60.26%** carry at least one hit
* **80.96%** of those hits touch a one-sided rung
* on two-sided-only pairs the rate falls to **2,900 / 56,563 = 5.13%**
* concentrated in the CPI ladders (`cpi_core_mom` 2,359/2,407 snapshots, `cpi_mom` 2,061/2,407,
  `cpi_yoy` 1,710/1,955) and near-absent in `gdp` (21/1,160) and `payrolls` (1/2,280)

**Executable** (buy YES(outer, lower T) + NO(inner, higher T) at both real asks — a guaranteed
≥$1 payoff — priced through `core.pricing.monotonicity_crossing_edge`; ALL nested pairs, the
most generous form, matching `anomaly_sweep.check_monotonicity`'s own `i<j` enumeration):

* **849,958 nested pairs**
* **9** cost under $1.00 gross (0.001%) — and those 9 are only **2 distinct quote states**,
  the rest being L221's byte-redundant re-capture of one of them 8 times on 2026-07-29
* **0** clear $1.00 net of taker fees. Worst-case-best is `KXCPIYOY-26SEP-T3.5` YES @ $0.50
  (`real_ask`) + `-T3.6` NO @ $0.48 (`real_ask`) = $0.98 gross, **−$0.02** net of two 1¢ taker
  fees. The single non-repeat, `KXCPIYOY-26JUL` on 2026-07-05, is **−$0.01** net.

So the naive screen a probe writer reaches for carries a **~1,700× false-positive load** on this
family (13.06% vs 0.00%), and four fifths of it is explained by one-sidedness alone.

## Part 4 — three prior claims re-checked against the longer tape

**D4 / L224 — CLOSED.** `_normalize_expiration_value` is now **total** over every committed
string: 9 distinct `expiration_value` raws across 5 series, **0 uncoercible**, **0** records
with `expiration_values_disagree`. The three that a bare `float()` still raises on — `'0%'`
(`KXCPICORE-26JUN`), `'3.5%'` (`KXCPIYOY-26JUN`), `'57,000'` (`KXPAYROLLS-26JUN`) — all coerce.
Tag discipline holds: `broker_truth` on 1,916/1,916.

**D5 — CORRECTED.** The 2026-07-29 audit called `gdp`'s long `no_settled_events` run "a silent
23-day regression". The longer tape shows it is a **purge window that reopened**, i.e. correct
collector behaviour: `settled KXGDP-26APR30` (2026-07-05) → `no_settled_events` from
2026-07-06 (Kalshi's ~60-day settled-market purge, L11, removed the April event) → `settled
KXGDP-26JUL30` from **2026-07-31T10:05:35Z**, when the next quarterly landed. 364
`no_settled_events` records in between, broken only by two **honest** `fetch_error`s on
2026-07-29 — never a fabricated placeholder. The status vocabulary is still unable to say
"used to have this", but nothing regressed.

**A new, small one.** **3** `gdp` records carry `nowcast.status: "not_built"` — a value
`fetch_nowcast("gdp")` cannot produce today, since it routes `gdp` to the GDPNow scrape
unconditionally. They predate that leg (2026-07-05). All 2,290 lines still say
`schema_version: econ_prints.v1`: **a payload-semantics change is invisible in the version
field**, so "how often was a GDP nowcast available?" cannot be answered from the tape without
knowing the collector's own build history.

## Part 5 — side-finding (DESCRIPTIVE, flips nothing): the delegate scanner prices legs this family never would

`collection/econ_prints.py`'s docstring delegates the one arb shape these ladders admit to
`scripts/anomaly_sweep.py::check_monotonicity` (Q6/S3) — "already covered platform-wide". Two
things the anomaly tape says about that delegation:

**(a) Coverage is unverifiable from the tape.** `tape/anomalies/` holds 248 records, **247 of
them `markets_truncated: True`** (the 20,000-market cap), with counts but no scanned-ticker
list. Econ hits: **0 / 43,038** `cross_strike_monotonicity` anomalies name a `KXCPI*` /
`KXPAYROLLS` / `KXGDP` event. That 0 is consistent both with "scanned and genuinely clean" and
with "never reached". Part 3 supplies the missing half from the econ side: there was nothing to
find.

**(b) But the delegate's own output does not clear the bar this audit applies.** Re-derived
over the committed anomaly tape (the persisted `edge` reproduces exactly — **0/43,038
recompute disagreements** — so this is about the INPUTS, not arithmetic):

* **43,025 / 43,038 = 99.97%** of `cross_strike_monotonicity` records carry
  **`outer_ask == 0.00`**. `check_monotonicity` filters its legs on `is None` only, so
  `yes_ask_dollars: 0` — the **ABSENCE of a resting offer**, never a $0.00 buyable fill —
  passes straight through as the YES leg, and the "edge" is then ~$0.96 of imaginary money.
  L105 already names this exact class ("Treating a `yes_ask=0.0` no-offer leg as a $0.00
  buyable fill is the pt1 / prime-directive violation") for `check_bracket_arb`'s inputs;
  nobody had checked `check_monotonicity`'s. The records carry `price_source_tag: "real_ask"`.
* **1,480 / 43,038 = 3.44%** carry an `edge` of `8.673617379884035e-18` — `outer_ask=0.00`,
  `inner_no_ask=0.99`, i.e. **exactly $0.00** in decimal, admitted by a bare `if edge > 0`
  because binary float lifts it one ULP above zero. L27's class. The distribution has a clean
  gap: after those 1,480, the smallest edge is **≥ $0.005** — these are not small real edges,
  they are exact zeros. Reproduce:
  `monotonicity_crossing_edge(0.50, 0.48, MAKER_FEE_RATE) == 1.734723475976807e-17`.
* Zero-edge hits by family: `KXGOLDH` 1,049, `KXWTIH` 216, `KXSILVERH` 215. Zero-ask hits are
  dominated by `KXCOPPERD` (17,457), `KXSILVERH` (11,927), `KXGOLDH` (10,210), `KXWTIH` (3,431).

**This is recorded, not acted on.** It bears on S3, whose registry row still reads "0 so far in
3 capped live passes (expected, rare)" while 43,038 anomalies have since accumulated — but a
registry status is verdict-class and the two-agent rule binds. **No `Task`/subagent tool exists
in this harness** (the L285/L145/L223 precedent), so no independent `verifier` was dispatchable;
every number here was instead computed twice, once in an ad-hoc exploratory pass and once in the
committed script, on separate code paths, and reproduced exactly. `kb/strategies/00-index.md`
is deliberately untouched. The write-path repair — an `ask > 0` fillability guard and a
tolerance on `edge > 0` in `check_monotonicity` — is NOT attempted here: it changes a live
detector's output and belongs in its own item.

## One thing that happened while building this

`scripts/invariants.py`'s `no_yes_ask_arithmetic` (Hard Rule #3) **failed the gate on this audit's
own first draft** — 5 hits in the script, 3 in the tests — because verifying the BBO mirror
identity necessarily writes `yes_ask` next to an arithmetic operator, and the rule is lexical. The
rule is right and the draft was rewritten around it (locals `ya`/`yb`, identity labels and comments
reworded); the invariant was NOT relaxed and no exemption was added. Recorded because it is the
invariants-over-memory design working as intended on a file whose author believed it was exempt.

## What this does and does not say

It does **not** say `econ_prints` is bad data. It is the cleanest family this repo has audited
on every presence and validity axis. It says the family's *usable* population is about a third
of its nominal one, that the naive coherence screen over it is ~1,700× more optimistic than the
executable one, and that the one arb shape these ladders admit **has not occurred once** in
850k nested pairs over 24 days at real asks net of fees.

Bottom line for S12/Q10: when the ≥20-release gate finally opens, the ladder tape is sound, but
any probe over it must (1) restrict to `yes_bid > 0 AND yes_ask < 1` before treating a `yes_ask`
as a price, and (2) never take a `yes_ask` ordering violation as evidence of anything.

Files: `scripts/econ_prints_ladder_fillability_audit.py`;
`tests/test_econ_prints_ladder_fillability_audit.py`;
`reports/econ_prints_ladder_fillability_audit.json`;
`collection/econ_prints.py:138-157` (`_capture_strikes`);
`scripts/anomaly_sweep.py:186-220` (`check_monotonicity`);
`core/pricing.py` (`monotonicity_crossing_edge`, `fee_per_contract`).

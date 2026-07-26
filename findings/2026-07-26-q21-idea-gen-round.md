# Q21 idea-gen round — 2026-07-26 (kalshi-edge-hunter → independent verifier, two-agent rule)

**3 proposed, 1 queued (collect-and-revisit), 2 killed, 0 registered-live.** Consumes S54/S55/S56
for provenance → next free **S57**. Still **0 proven edges**. This is the **14th consecutive round
with no live registration**, but — unlike the prior 13 — it produces one genuine forward candidate
(S55) that is *reopenable on already-scheduled tape*, not a dead end.

## Why the round fired

Full Q0–Q47 re-scan (this run's step 0/0a/0b + the last several loop firings, all logged) finds
**0 eligible TODO/IN-PROGRESS** items — every item is DONE, credential/auth-BLOCKED (Q32/Q33/
Q35-build/Q42-pt3/Q47), calendar-gated-not-open (Q19 FOMC 07-29, Q37 ~08-05), or gate-open-but-
density-inadequate (Q36 both legs, Q43). Fewer than 2 eligible → the Q21 standing replenishment
condition is satisfied.

The producer (main context) proposed three candidates chosen to probe **under-explored corners** and
route around every dead cousin; an independent `verifier` agent attacked each against the committed
tape BEFORE any registration (two-agent rule at the idea stage). Verdicts: **A KILL, B
COLLECT-AND-REVISIT, C KILL** — every one grounded in a fresh tape re-run, not a memory of an old kill.

## The three candidates and their verifier verdicts (re-run numbers)

### S54 — Overround liquidity-cycle conditioning → KILL / CI-falsified (fee sinks it where the book is most efficient)
Mechanism: the real-ask bracket overround that kills every taker (S1/S5/S7) is a liquidity premium
that should compress in peak-liquidity hours; condition the dead calibration on capture-hour and hunt
the **lowest-overround tail** — a covariate none of S1/S5/S7 conditioned on. Counterparty: off-hours
retail crossing a wide book.

**Kill (re-run).** Read `tape/sports_pairs/dt=2026-07-{02..26}` (305,410 YES-ask snapshots) joined to
`tape/settlement_ledger/` (10,605 broker_truth tickers, L50 ex-post join); yield 21.6% → 330 games /
605 outcome tickers, **100% `real_ask`**. Two findings kill it: (1) **the premise is false on this
tape** — median `overround_absorbed` is flat at **1–2¢ across all 24 UTC hours** (no liquidity cycle);
the fat 9–21¢ overround that killed S1/S5 lived on the multi-bracket weather/crypto **ladders**, not on
these 2-way sports books (a useful correction to carry forward). (2) In the lowest-overround decile
(`ov ≤ 0.01`, n=138 games/272 outcomes) the raw `winrate − ask = −0.0013` (the book is *most* efficient
exactly where overround is lowest), and net of the taker fee via `core.pricing`: mean **−$0.0131,
95% block-bootstrap-by-game CI [−0.0234, −0.0017]** (stable across seeds, admissible — 6/138 opposing
clusters, not L41). **Upper bound strictly below zero → CI-falsified (L27)**, not merely straddling.
The ~2–3¢ taker fee on a median-0.48 ask sinks it even at a zero calibration gap. **Reopen:** a real
fair-value model flagging the *subset* of legs where `ask < fair − (fee + overround_share)`, bootstrapped
by game — not an unconditional buy-every-leg over an already-efficient surface.

### S55 — Post-release single-leg Kalshi-lag taker on FOMC via burst-class tape → COLLECT-AND-REVISIT (queued as Q48, gated on the 07-29 FOMC burst)
Mechanism: in the seconds–minute after the 18:00Z FOMC statement, Kalshi's thin econ book reprices
slower than Polymarket/CME. Use Polymarket's post-release implied as a **free exogenous signal** (NOT a
traded leg → single Kalshi fee only); when Kalshi's `real_ask` still prices the pre-release distribution
while Polymarket has already moved by > taker fee, taker the Kalshi side toward the new truth, hold to
convergence/settlement. Counterparty: retail holding stale Kalshi quotes on the thin FOMC book.

**Verdict: COLLECT-AND-REVISIT (sound, not registerable now).** The verifier confirmed the fed leg IS
genuinely `real_ask` on current tape (`tape/polymarket_macro_pairs/`, 8,940 fed rows,
`KXFEDDECISION-{26JUL,26SEP,26OCT}-{H0,H25,H26,C25,C26}`, `price_source_tag=real_ask`; Polymarket side
is a `real_ask` signal, not a fee leg) and that **no FOMC burst tape exists yet** — `tape/hf_burst/`
holds one file (`dt=2026-07-16`) which is a *crypto* book, not FOMC; the recurring `macro_pairs`
collector runs only **~2 captures/day**, which cannot see the seconds-to-minute reprice window (the S9
cadence wall), so the burst collector is genuinely required and today **n=0**. It is **not** pre-killed
(S9 died on cadence, which the burst fixes; S34 died as a *two-fee* arb, this is single-fee) and **not**
structurally void (per-meeting decision buckets need no nesting — a single-leg taker on one bucket is
admissible, unlike the discarded S54-cumulative framing). **Two honesty caveats carried onto the queue
item:** (1) the *steady-state* gap today is `price_gap_yes_ask ≈ 0.6¢`, far under the ~7¢ taker fee —
the entire bet rides on a **transient burst-window dislocation that is completely unmeasured**; (2) one
burst = n=1 event, and a block-bootstrap-by-burst needs several FOMC meetings (~8/yr), so the real
revisit horizon is **months**, not the single 07-29 fire.

### S56 — Weather near-certain-winner taker keyed on realized intraday temperature → KILL / signal leg does not exist + L41-degenerate
Mechanism: a daily HIGH-temp market is effectively decided by ~late afternoon (the day's max usually
occurs 3–5pm and rarely rises after) while Kalshi settles ~midnight, so for hours the winning bracket is
near-certain **from the realized intraday temp** yet its `real_ask` can still be < $1. Distinct from S28
(sports empty at close — weather books don't), S5/S1 (a realized-temp FACT, not a forecast), S10/S53
(floor-pin / near-money crypto).

**Kill (re-run).** The book/settlement join is clean — `tape/weather_books/dt=2026-07-{16..24}` joins
to `tape/weather_actuals/` giving the winning-bracket ticker (broker_truth): 232 settled events, 154
with pre-close book captures, **100% fillable (`best_yes_ask` < 1.00, 0% $1-pinned)** — so the pin
kill-condition is *false*. But two compounding defects kill it anyway: (1) **the signal leg does not
exist** — `weather_actuals` carries only the *finalized daily-high* broker_truth value (median 1 capture
per city-date, **0 of 82 cells show any intraday change**); there is no timestamped running-temperature
series anywhere in committed tape, so "the realized-so-far high already locks bracket B at capture t" is
**unreconstructable ex-ante**. Buying the eventual winner at pre-close captures is pure lookahead; the
market already prices the winner in as the day resolves (winning-bracket median `yes_ask`: 0.34 at >24h,
0.49 at 12–24h, 0.92 at 6–12h, 0.98 at 0–6h — ~2¢ of room near close, inside the ~1¢ taker fee). (2)
**L41-degenerate even granting perfect ex-post winner identity** — the latest ≤6h-to-close fillable
capture of the realized winner, by station-day: mean **+$0.0367, CI [+0.0159, +0.0639]** but **75/75
clusters positive, 0 opposing** → `no_opposing_unit` inadmissible (identical in shape to S20's 8/8
degenerate bootstrap). The catastrophic bracket-flip leg (late-day heat pushes the high out of the
"locked" bracket → buy at 0.98, lose 98¢) is **structurally unsampled** because the population conditions
on the realized winner. The +3.67¢ is a resolution-conditioning artifact, not an edge. **Reopen:**
collect a timestamped intraday realized-temperature feed (hourly METAR) **concurrent** with
`weather_books`, then run a bracket-*selection* rule that lets flips lose (≥1 opposing station-day cluster)
and bootstrap by station-day.

## Lesson candidates (deferred to kb-distiller, not appended here to avoid a ledger merge conflict)

- **(S54 pattern)** On a well-calibrated **2-way** book, the taker fee alone (~2–3¢ at mid prices)
  guarantees a negative net-taker CI *regardless of overround band* — conditioning on the lowest-overround
  tail lands you on the **most efficient** sub-population (raw winrate−ask ≈ 0), so the fee has nothing to
  offset. And: the fat 9–21¢ overround is a **multi-bracket-ladder** property, not a 2-way-book property
  (median 1–2¢ there) — don't import the weather/crypto overround figure onto sports.
- **(S56 pattern)** A "near-certain-winner" taker is **L41-degenerate** whenever the winner is identified
  from *settlement* rather than from a *real-time* feed: selecting on the realized winner deletes the
  flip-loss leg, so any CI>0 is a resolution-conditioning artifact. The ex-ante signal feed (intraday temp)
  is the binding data-surface requirement — L41 × L9/L43 applied to a **signal** leg, not a join leg.
- **(S55 note, not a kill)** The Kalshi Fed-decision leg in `tape/polymarket_macro_pairs/` is `real_ask`;
  a single-leg post-release Kalshi-lag taker is a genuine **collect-and-revisit**, gated on the 07-29 FOMC
  burst firing AND ≥ several settled FOMC meetings before any CI is attempted.

## Bottom line

Register-live = nothing (the real-ask CI bar has not moved), but the round is **not** a dead-end: S55 is
queued (Q48) as a burst-gated collect-and-revisit with both honesty caveats, and S54's kill corrected a
standing misconception (the 9–21¢ overround is a ladder property, not a sports-book one). Two-agent rule
satisfied at the idea stage (producer + independent verifier, all numbers re-run against tape). Consumed
S54/S55/S56 → **next free = S57**. Still **0 proven edges**.

# S9 lead-lag resolution decision — data-adequacy DEAD

`LOOP-QUEUE.md` Q8 · 2026-07-06 (research loop) · decision, not new data — **verdict**

## What this closes out

The 2026-07-06 shock event-study (`findings/2026-07-06-polymarket-leadlag-s9-shock-eventstudy.md`)
found that Kalshi and Polymarket reprice together at every observed round transition (n=8
ticker-steps, mean `|Δkalshi − Δpolymarket|` 2.2¢, no consistent leader) and diagnosed why:
collection cadence (30–60 min, cloud+VPS offset) is coarser than the event itself (a match
settles within minutes of the final whistle). That run left an explicit resolution decision
for the next one: either build a sub-hourly capture burst around the remaining matches'
scheduled end times, or accept the lead-lag question as untestable with this infrastructure
and mark it dead.

## Why a sub-hourly burst isn't buildable from here

Checked the actual scheduling primitives this loop has access to (`create_trigger`,
`send_later`, both `Claude_Code_Remote` MCP tools):

- Recurring cron triggers are hard-capped at **hourly minimum interval** — the tool's own
  schema states it explicitly. That rules out a recurring sub-hourly poll outright.
- One-shot triggers (`run_once_at` / `send_later`) aren't cadence-limited, so in principle a
  handful of one-shot fires spaced 5–10 min apart could bracket a single match's expected
  end window. But that requires knowing each remaining match's kickoff time precisely enough
  in advance to place the bursts — the accumulated tape (`tape/polymarket_pairs/`) only
  carries round/team/price, no kickoff timestamp, and neither `collection/polymarket_pairs.py`
  nor `collection/sports_pairs.py` currently resolve one for KXWCROUND markets specifically
  (unlike `sports_history.py`'s ESPN-scoreboard leg, which is scoped to moneyline games, a
  different series).
- Even with a kickoff time in hand, wiring up "N one-shot triggers per remaining match,
  each invoking a capture-and-commit pass, for the semifinals and final" is a new class of
  autonomous scheduled action running unattended over many days — the same category as the
  VPS collector and the `ntfy-watch` trigger, both of which were stood up as **Ryan-requested
  ops changes**, not decided unilaterally by a research-loop run. Standing up recurring/burst
  automation on a hunch is a bigger, harder-to-reverse commitment than a single milestone's
  scope, and isn't what this run's standing approval (research + data collection on the
  existing infra) covers.

Building the burst mechanism is therefore not a same-run action a research loop pass can
responsibly take alone. Given the World Cup ends 2026-07-19 and the last run already flagged
this as time-boxed, forcing a wait for Ryan's sign-off risks the tournament ending with the
question exactly where it's been for three runs: untested.

## Verdict: lead-lag sub-thesis is DEAD (data-adequacy), parity infra stays alive under S17

Per the Stop rules, a DEAD verdict recorded honestly is a success, not a failure to keep
collecting. Splitting S9 into its two sub-questions:

- **Lead-lag (does one venue reprice before the other around a shock?) → DEAD, data-adequacy.**
  Not falsified by a bootstrapped CI (there's no CI to compute — n=8 ticker-steps, no
  variance structure to test), but structurally untestable with the automation this loop has
  available: hourly-minimum recurring triggers can't resolve a same-minute event, and the
  one-shot-burst alternative needs infrastructure (kickoff-time resolution + a new
  multi-day autonomous scheduling commitment) this run isn't positioned to build alone.
- **Cross-venue price parity (do the two venues quote the same real-money price for the same
  question, on average, right now?) → stays alive, already answered usefully.** The 2026-07-04
  first cut found a small, roughly symmetric gap (+0.20¢ mean, −3¢/+3¢ range) on 48/48 matched
  markets — that's the question `collection/polymarket_pairs.py` and its Q12 generalization
  (`run_fed_decision()`, S17) actually answer well, and it doesn't need sub-hourly resolution.
  S17 already carries this forward past the World Cup with recurring macro pairs.

## Status

`kb/strategies/00-index.md` S9 flipped to **dead ✗** (lead-lag sub-thesis; data-adequacy, not
a CI falsification) with a note pointing to S17 for the surviving parity angle. No code
changes this run — this is a decision on already-collected evidence, not a new probe. 297
tests unchanged, `invariants --full` green.

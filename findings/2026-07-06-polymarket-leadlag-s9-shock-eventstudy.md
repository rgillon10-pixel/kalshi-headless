# S9 shock event-study — the first real round-transition data lands

`LOOP-QUEUE.md` Q8 · 2026-07-06 (research loop) · read-only, descriptive — **NOT a verdict**

## What this is

The 2026-07-05 first cut (`findings/2026-07-05-polymarket-leadlag-s9-first-cut.md`) found
zero real round-transition shocks inside the continuously-collected window — every price
tick observed was book noise, and S9's actual thesis (does one venue reprice before the
other around a team advancing/being eliminated?) was untested. By this run, two teams have
been eliminated inside the collected window: **Brazil** (quarterfinal loss, ~2026-07-05
21:24–21:54Z) and **Mexico** (quarterfinal loss, ~2026-07-06 01:24–02:24Z, with a further
decay step through 02:55Z before the market closed). This is the "once an actual round
transition lands, re-run and inspect that market's captures around the transition
specifically" work Q8's own notes called for.

New `scripts/s9_shock_eventstudy.py` isolates real transitions from
`market_membership_changes()` (excluding the one documented startup artifact — the diff
between the 2026-07-04T15:15Z pre-wiring smoke-test capture and 2026-07-05T00:11:30Z, when
continuous hourly collection actually began) and, for each removed KXWCROUND ticker, reports
the last two captured rows on both venues — the actual repricing step, since the capture at
which a ticker vanishes from Kalshi's open-markets listing is not itself a price observation.

## Result: both venues moved together, no lead-lag signal at this resolution

| ticker | gap | kalshi Δ | polymarket Δ | \|Δk − Δp\| |
|---|---|---|---|---|
| KXWCROUND-26QUAR-BRA | 30.3 min | −0.670 | −0.659 | 0.011 |
| KXWCROUND-26SEMI-BRA | 30.3 min | −0.360 | −0.370 | 0.010 |
| KXWCROUND-26FINAL-BRA | 30.3 min | −0.180 | −0.190 | 0.010 |
| KXWCROUND-26QUAR-NOR (Brazil's opponent, advanced) | 30.3 min | +0.650 | +0.669 | 0.019 |
| KXWCROUND-26QUAR-MEX | 60.0 min | −0.360 | −0.350 | 0.010 |
| KXWCROUND-26SEMI-MEX | 60.0 min | −0.240 | −0.160 | 0.080 |
| KXWCROUND-26FINAL-MEX | 60.0 min | −0.130 | −0.103 | 0.027 |
| KXWCROUND-26QUAR-ENG (Mexico's opponent, advanced) | 60.0 min | +0.370 | +0.380 | 0.010 |

n=8 ticker-steps across 2 real events. Mean `|Δkalshi − Δpolymarket|` = **2.2¢**, max 8¢ — in
the same range as ordinary bid/ask spread noise already characterized in the 2026-07-05 cut
(contemporaneous ρ +0.293 on noise alone). **No consistent one-venue-leads-the-other pattern**
— both venues had already repriced to reflect the outcome by the very next capture in every
case.

## The actual finding: collection cadence is coarser than the event itself

A World Cup match resolves within minutes of the final whistle — real-world information
arrives essentially instantly to anyone watching. The hourly (here, 30–60 min due to the
cloud+VPS collector offset) capture interval cannot resolve which venue moved first *within*
that window; by the time either collector fires again, both books already reflect the result.
Mexico's data additionally shows the reprice was not even a single clean jump: Kalshi's
`FINAL-MEX` ask stepped 0.16 → 0.03 (01:24→02:24Z) → 0.04 (02:55Z) before the market closed —
multiple hourly captures apart, still both venues moving in lockstep at each step, never one
venue leading by a full interval.

This is a genuine methodological finding, not a null result on the thesis itself: **S9's
lead-lag thesis cannot be tested at this collection resolution.** Testing it for real needs
either (a) sub-hourly captures bracketing scheduled game-end times for the tournament's
remaining matches, or (b) accepting that the infrastructure built for Q8 answers a different,
still-useful question (cross-venue price parity) but not the lead-lag question as designed.

## Status

`kb/strategies/00-index.md` S9 stays **data-collecting** (not enough events for a bootstrap
either way, and the resolution gap needs a decision before more of this kind of data is
worth collecting). World Cup ends 2026-07-19 — a handful of transitions remain (semifinals,
final); if a sub-hourly capture burst isn't built before then, this angle should be marked a
data-adequacy DEAD rather than left open indefinitely past the tournament.

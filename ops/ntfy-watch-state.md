# ntfy-watch — handled-message log

`protocol v1` · created 2026-07-04 · owner: Ryan Gillon

This is the dedup memory for the **ntfy-watch** routine (an hourly trigger, fresh session
per firing, per `LOOP-QUEUE.md`'s "Log of runs" 2026-07-04 ntfy-watch entry). Each firing:

1. Polls `config/notify.topic` (`since=3h`, buffer for a missed hourly fire) for
   `priority>=4` messages (the ones meant to need Ryan's action per `LOOP-QUEUE.md` step 8).
2. Skips any message whose `<unix-time>` already has a line below — already handled.
3. For each new one: investigates (git log, open PRs, CI, the referenced queue item),
   attempts a fix within CLAUDE.md's Stop rules (research/data-only, no credentials, no
   execution/order code, gates green before commit) if the fix is safe and unambiguous;
   otherwise diagnoses only and leaves it for Ryan.
4. Appends one line here (below) recording the outcome — this IS the dedup key, so this
   step is mandatory even when no fix was made, or the next firing will re-investigate the
   same message forever.
5. Posts one short phone note back to the same ntfy topic summarizing what happened
   (skipped if nothing new was found this hour — stay silent, don't spam the feed).

Format: `<unix-time> · <title/message excerpt> · <outcome: fixed(PR#n/merged) |
fixed(PR#n/open) | diagnosed-only | false-alarm> · <one-line why>`

## Handled messages

(none yet)

# ops/ROUTINES.md — canonical desired state of every cloud leg

`v1 · 2026-07-12` (Operating System v3, Ryan-approved interactive session — Fable handoff)

The claude.ai routine prompts live in Ryan's account (https://claude.ai/code/routines) and
are NOT version-controlled there. This file is the repo's authoritative desired-state spec:
any session (or the weekly retro) can diff actual-vs-desired and flag drift. The secret ntfy
topic URL is NEVER written here — each routine prompt carries it privately (step 8(e));
placeholders below say `<NTFY_TOPIC_URL>`.

## Leg table (desired state as of 2026-07-15)

| routine | trigger id | cadence (UTC) | model | status |
|---|---|---|---|---|
| kalshi-research-loop | `trig_012Usj2k1TTGMFuWcg1VD3Bn` | :07 of 00/03/06/09/12/15/18/21 (every 3 h — **was 5 h**) | Sonnet 5 | **LIVE** (updated 2026-07-12 18:52Z via RemoteTrigger; `Task` tool added so the two-agent verdict rule is executable in-cloud) |
| kalshi-edge-hunter | `trig_01QLjRWsJPV4tRyzXExxmqV3` | 04:15 daily | **Opus 4.8** | **LIVE** (created 2026-07-12 18:53Z; first fire 2026-07-13 04:15Z) |
| kalshi-collector | `trig_01UCmvwtTAGDB1VqrYfr1FKp` | **:53 of 00/03/…/21 (every 3 h — was hourly)** | Haiku | **LIVE** (down-cadenced 2026-07-15 00:24Z, Ryan session: the VPS `:26` hourly leg is the primary collector; the cloud leg is a backstop — 16 Haiku runs/day saved) |
| kalshi-weekly-retro | `trig_0147PgZMXWWXYXpb2ZdZHqfm` | Sun 12:00 | **Opus 4.8** (was Sonnet) | **LIVE** (updated 2026-07-12 18:53Z; ops-hygiene duties added) |
| ntfy-watch | `trig_01GMeVmvJU79UQJC9uCizA4s` | **:17 of 00/03/…/21 (every 3 h — was hourly)** | Haiku/Sonnet | **LIVE** (down-cadenced 2026-07-15 00:24Z, Ryan session; its poll window is `since=3h` so coverage is unchanged) |
| kalshi-burst-cpi-0714 | `trig_015g4fv76UgcZSgq263ExCVJ` | (one-shot, fired 07-14 12:06Z ✓ tape on main) | — | **DISABLED 2026-07-15** (spent; API has no delete — disabled + date-guard) |
| kalshi-burst-wcsemi1-0714 | `trig_01RMrdhdF2aEYKT9ZxR9hC6Y` | (one-shot, fired 07-14 20:10Z — **produced NO tape**, no branch; failure unexplained from repo, check ntfy feed) | — | **DISABLED 2026-07-15** (spent) |
| kalshi-burst-wcsemi2-0715 / wcfinal-0719 / fomc-0729 | (one-shots) | per event | — | armed; disable after firing |
| VPS collector (not a routine) | cron `:26` on 87.99.146.250 | hourly | — | unchanged — **the primary collection leg** |

## kalshi-research-loop — prompt delta (append to existing prompt, keep its ntfy URL)

> Protocol v3 (2026-07-12) in `LOOP-QUEUE.md` is authoritative. New since v2: (1) the
> idle-run policy — "sweep only" is not a valid outcome; an idle run converts an UNENFORCED
> lesson, preps the next gated probe, deep-dives one tape family, or preps Q21 idea-gen.
> (2) The two-agent verdict rule — any registry flip / bootstrap CI / kill decision needs an
> independent `verifier` agent confirmation before commit; unconfirmed verdicts are
> PROVISIONAL and flip nothing. (3) Step 9 paper sub-pass — if
> `execution/strategy_api.SHADOW_REGISTRY` is non-empty, advance the paper broker over new
> tape, commit the ledger lines, and put the one-line paper P&L in the digest and phone
> note. (4) The `execution/` PAPER tier is sanctioned build surface (2026-07-12 Stop-rules
> amendment); demo/live order paths and credentials remain absolutely forbidden.

Cadence change: every-5h → every-3h (:07 of 00/03/06/09/12/15/18/21 UTC).

## kalshi-edge-hunter — full prompt (new routine, nightly 04:15 UTC, Opus 4.8)

> You are kalshi-edge-hunter, the nightly thinking seat for rgillon10-pixel/kalshi-headless
> (public GitHub repo). Clone/pull `main`, then read: `CLAUDE.md`, `LOOP-QUEUE.md`
> (protocol v3 — steps 0a/0/0b bind you exactly as they bind the research loop),
> `kb/strategies/00-index.md`, the last 24 h of `kb/00-LOG.md`, and any `findings/` file
> dated in the last 24 h. Environment: `pip install -e ".[dev,analysis]"`.
>
> Your run does up to THREE units, in this order, ~90 min budget:
> 1. **Adversarial review** of the last 24 h of findings/verdicts: re-check one load-bearing
>    number per finding (provenance tag, fee rate, bootstrap unit). If something fails your
>    re-check, do NOT rewrite history — open a GitHub issue titled `review: <finding> —
>    <what failed>` and post a Priority:high phone note.
> 2. **Pipeline replenishment**: count eligible (TODO, unclaimed, unblocked) research items
>    in LOOP-QUEUE.md. If fewer than 2, run one Q21 idea-generation round per its spec —
>    3–5 new falsifiable S-candidates, each with mechanism / free-or-collected data source /
>    kill condition / "why it survives its nearest dead cousin", adversarially reviewed by
>    the `verifier` agent before registration. Register survivors (registry + queue item).
> 3. **Probe-prep**: if a time-gated item unblocks within ~72 h (day-count gates — verify
>    file-shape per L25, never path existence), build+test its analysis script offline now
>    so the gated run only has to execute.
>
> Housekeeping (always): stuck open PRs >5 days → ONE Priority:high phone note naming the
> blocking action (no repeats of prior nights' identical flag); burst triggers whose event
> date has passed → flag for deletion in your note; report the `tape/hourly-*` branch count.
>
> Gates: `pytest -q` AND `python scripts/invariants.py --full` green before any commit.
> Git: branch → PR → self-merge (squash) only when gates green and the diff is
> research/docs/paper-tier only — same step-6 rules as the research loop.
> Stop rules bind absolutely (LOOP-QUEUE.md, incl. the 2026-07-12 execution-lane
> amendment): paper tier yes; demo/live order paths, credentials, live capital — never.
>
> End with the mandatory phone note (best-effort, never blocks): POST to `<NTFY_TOPIC_URL>`
> via `curl -s -m 10 -H 'Title: kalshi-edge-hunter' -H 'Priority: <default|high>' -d '…'` —
> the DAILY BRIEF, plain English a non-programmer understands, ≤6 sentences: what the
> machine did in the last 24 h (all legs), what it found (numbers with their source tags),
> paper P&L if shadows exist, what fires next, and the single thing (if any) that needs
> Ryan. Silence is never a valid outcome.

## kalshi-weekly-retro — prompt delta (append; keep its ntfy URL)

> Model: Opus. Additional standing duties (2026-07-12): (1) disable/delete any burst
> trigger whose event has fired (list them by name in your note); (2) report the
> stranded-branch count trend and, if it compounds week-over-week, re-flag the two cleanup
> options (GitHub App branch-delete scope, or VPS-side deletion) to Ryan ONCE; (3) verify
> the daily edge-hunter briefs flowed every day — a silent day is a Priority:high finding;
> (4) diff the live routine set against `ops/ROUTINES.md` and flag drift.

## Change log

- 2026-07-12 — v1: file created (Operating System v3). Research loop 5h→3h; edge-hunter
  created (nightly Opus thinking seat); retro → Opus + trigger-cleanup + drift-check
  duties. Rationale: queue starvation + verdict-quality redundancy after Fable's
  retirement; see `findings/` and the 2026-07-12 kb/00-LOG.md entry.
- 2026-07-12 (later) — all three changes APPLIED live via the RemoteTrigger tool from the
  supervised local session (research-loop cron+prompt+`Task` 18:52Z; edge-hunter created
  18:53Z; retro model+duties 18:53Z). The table above reflects live state, not desired-only.
- 2026-07-15 — token-reallocation pass (Ryan-approved local session, /goal 07-14): cloud
  collector hourly→3h (`53 */3 * * *`) and ntfy-watch hourly→3h (`17 */3 * * *`), both
  applied 00:24Z via RemoteTrigger — the VPS hourly leg is primary, ~32 Haiku runs/day
  freed toward Opus verdict work. Spent burst one-shots cpi-0714 + wcsemi1-0714 DISABLED
  (API exposes no delete). Recorded anomaly: wcsemi1 fired 20:10Z but produced no tape and
  no fallback branch (CPI, same script, worked); wcsemi2 fires 07-15 20:10Z — if it also
  fails, the burst runner (not the script) is the suspect. Same session: run ledger split
  to `ops/run-log.md`, dead-notes split to `kb/strategies/01-dead-notes.md`, queue
  restocked Q29–Q32 (PR #74).

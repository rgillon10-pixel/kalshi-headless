---
name: loop-recap
description: Recap what the kalshi.headless cloud loops (research loop, edge-hunter, hourly collector) actually did over the last N hours, then reconcile the stale local logs to match. Use when Ryan asks "how did the last day/night go", "what did the loops do", "how are the research runs / scans working out", "catch me up on the loop", or wants project-status / memory / journal brought current with the cloud work. Read-first, then writes local logs — never touches the shared repo history or capital.
---

Answer "how is the autonomous system doing, and are the local logs telling the truth?" in one
pass. The cloud loops (research loop every 3h, nightly Opus edge-hunter, hourly collector) run
unattended and record everything in the repo; the *local* status/memory/journal files drift
behind. This skill reads the loop's own audit trail, digests it, and — per Ryan's standing
choice — **auto-applies** the log updates that drift requires.

Order of operations is fixed: **pull → read → digest → reconcile logs → report.** Never write a
log before you've read the run trail, or you'll copy a stale claim forward.

## 0. Pull first (non-negotiable)

The loops push to `main`; your local checkout is always behind. Per LOOP-QUEUE.md this is step 0
of everything.

```bash
cd ~/Active/01-projects/kalshi.headless && git pull --rebase 2>&1 | tail -5
```

If the pull is not clean (conflict, or a "would be overwritten" on a tape file), stop and tell
Ryan — do not force anything. A rewind of `main` is the one case that must escalate, never
self-heal (see LOOP-QUEUE.md step 0a; `main_branch_protection` memory).

## 1. Read the run trail (the source of truth)

The run ledger **`ops/run-log.md`** (moved 2026-07-15 from LOOP-QUEUE.md's old "## Log of
runs" section) is the one-line-per-run file every research pass appends to. Pull the recent
entries — default window is "since the last recap / ~last 24h"; widen if Ryan asks.

```bash
grep -nE '^\- 2026-[0-9-]+T' ops/run-log.md | tail -12   # adjust year/date to today
```

(If a run that cloned pre-move appended below LOOP-QUEUE.md's pointer header instead,
read those lines too — the next loop run migrates them.)

Each line is `<UTC ts> · <item> · <one-line outcome>`. Read the ones inside your window fully —
they already contain the verdict, the CI, the verifier ruling, and any registry flip.

Then cross-check the three things a run-line summarizes, so the digest is grounded, not just
transcribed:

- **Registry state** — `kb/strategies/00-index.md` status column. Note any `idea → data-collecting`,
  `→ dead ✗`, or (the one that matters) `→ live`. The count of proven edges is the headline: a
  candidate is only *proven* with a bootstrapped CI **strictly > 0 at real asks** — "data-collecting"
  and "PROXY-POSITIVE" are NOT proven. Say the true number (it has been **0** since inception; do
  not round a proxy-positive up to a win).
- **Paper P&L** — if `paper/ledger/` exists, the shadow tier's realized P&L is *evidence, not a
  verdict*. Report it with that label. Check `execution/strategy_api.py` `SHADOW_REGISTRY` for what's
  actually shadowing.

```bash
sed -n '1,40p' kb/strategies/00-index.md          # status table
ls -la paper/ledger/ 2>/dev/null                   # paper tier exists?
```

## 2. Collector + sweep health

The hourly collector and the stranded-tape sweep are the plumbing. Confirm they're alive:

```bash
git log --oneline -15 --grep='tape: hourly pass'   # cadence — should be ~1/hr on the :26
git ls-remote --heads origin 'refs/heads/tape/hourly-*' 'refs/heads/tape/burst-*' 2>/dev/null | wc -l
```

A large count of un-swept `tape/hourly-*` branches is normal (the collector's push falls back to
a branch; the research loop sweeps them — see LOOP-QUEUE.md step 0b). Only flag it if the newest
hourly-pass commit is more than a couple hours old (collector may be down) or if a whole calendar
day has no tape (a real coverage gap, like the 2026-07-09 one already on record).

Optionally fold in the phone feed via the **check-ntfy** skill if Ryan wants to know what actually
paged him — don't duplicate its logic here.

## 3. Digest (what you print)

A tight, honest digest — this is a status read, not a pitch:

- One table: `run ts · queue item · outcome` for the window.
- Headline line: **proven edges = N** (almost always 0) + the single most important state change
  (a new `data-collecting` candidate, a kill, a paper-tier first).
- Collector health: one line.
- Then: "logs were X behind; reconciling now" → section 4.

Resist making it sound better than it is. The prime directive is edge at real asks; process wins
(a candidate advancing, a clean kill, a test-count bump) are progress, not money. If the run trail
shows a CONFIRMED-WITH-CAVEAT or PROXY-POSITIVE, carry the caveat into the digest verbatim.

## 4. Reconcile the local logs (auto-apply — Ryan's standing choice, 2026-07-13)

Ryan chose **report + auto-apply**: when you detect drift, fix it in the same pass — these are
local logs (status/memory/journal), not shared branch history or capital, so they don't need a
per-run confirm. Still *show* each edit in your report. Three targets:

**(a) `~/Active/02-ai-context/project-status.md`** — the kalshi.headless section + the top
`last-updated:` field. Update only if a registry status, the edge count, the paper tier, or the
"Next/Blocked" line actually changed. Match the file's existing prose style; don't restructure it.

**(b) Memory** at `~/.claude/projects/-Users-ryan-gillon-Active-01-projects-kalshi-headless/memory/` —
the live-state files drift fastest:
  - `finding_no_realask_edge.md` — the DEAD/alive strategy roster + the "as of <date>" line. This
    is the single most important memory to keep true; update its date and roster on any flip.
  - Update `MEMORY.md`'s one-line pointer only if the hook/summary changed. One fact per file; edit
    in place, never duplicate (per the memory contract).

**(c) Today's journal** `~/Active/03-journal/kalshi.headless/YYYY-MM-DD.md` — append a session-log
block in the workspace CLAUDE.md format (`## [HH:MM ET] — kalshi.headless`, Done/Decisions/Status
change/Follow up). If `status change: yes`, that's your signal you also had to touch (a).

Get the current date/time from the environment context or `date` — do not guess.

## 5. Report what you wrote

Close by listing exactly which files you changed and the one-line reason for each (e.g.
"project-status.md: last-updated 06-18 → 07-13, added S14 data-collecting + paper tier"). If a
target was already current, say "already current — no change" rather than silently skipping it, so
Ryan can trust the recap ran end to end.

## Boundaries

- **Read the repo, write only local logs.** This skill never edits `kb/`, `findings/`,
  `LOOP-QUEUE.md`, tape, or code — those are the loops' own append-only lanes. It never commits,
  pushes, opens a PR, or touches capital/execution beyond *reading* the paper ledger.
- **Never flip a strategy verdict.** Verdicts require the two-agent rule inside a loop run; this
  skill only *reports* verdicts the loops already recorded. If the run trail and the registry
  disagree, report the discrepancy — don't resolve it.
- **Don't round up.** Proxy-positive ≠ proven; paper P&L ≠ a verdict; a swept branch ≠ an edge. The
  headline number is proven-edges-at-real-asks, and it is what it is.

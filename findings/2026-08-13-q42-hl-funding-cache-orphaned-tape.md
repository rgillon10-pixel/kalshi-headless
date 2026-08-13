# `tape/q42_hl_funding_cache/` data-quality audit — clean, complete, and orphaned

2026-08-13 · research loop, idle-run policy (c) · main context (read-only, offline). No
strategy claim, no P&L, no fee model, no bootstrap CI, no registry change — two-agent rule
N/A (data-quality characterization, not a verdict; same posture as L104/L110/L118/L126/L127/
L137/L287/L318).

## Why this family, why now

Full Q0–Q56 rescan (file-shape, L25): every item reads DONE / BLOCKED(Ryan-or-credential) /
gated / data-inadequate at its current status line — 9th consecutive idle-adjacent run
(`kalshi-edge-hunter` round #28, 2026-08-12, independently found the same). Idle-run policy
(a) checked next: the 9 open `UNENFORCED` lesson rows (`L213`/`L221`/`L222`/`L282`/`L319`/
`L320`/`L321`/`L323`/`L338`, via `_stale_unenforced_scan`) are each either Ryan/VPS-gated
(`L213`/`L221`/`L222`), a general workflow-level repair outside a single milestone's scope
(`L282`), or explicitly "not statically assertable — a prose/semantic judgment" by the row's
own text (`L319`/`L320`/`L321`/`L323` each keep a residual half by design; `L338` is the same
shape) — policy (a) is empty. Policy (b) (prep the next time-gated queue item) has no target:
no queue item names a calendar gate that has not already opened (Q42/Q43 are density-gated,
not date-gated; Q37/Q51 already opened and ran). Took policy (c): a data-quality deep-dive on
one tape family. `grep -c` against `kb/lessons/00-lessons.md` shows `q42_hl_funding_cache` has
**zero** prior lesson mentions — genuinely unaudited — so this run looked there.

## What the family is

`tape/q42_hl_funding_cache/` holds 13 files, `hl_funding_<COIN>.jsonl` for
`{BTC, ETH, XRP, DOGE, LINK, SOL, LTC, BCH, NEAR, SUI, ZEC, kSHIB, HYPE}` — exactly Kalshi's 13
active crypto-perp contracts named in Q42's own mechanism note. Schema per line:
`{coin, time_ms, funding_rate_hourly, premium, price_source_tag, venue, fetched_at}`,
`price_source_tag: "broker_truth"`, `venue: "hyperliquid"`.

## Internal quality: clean

Every one of the 13 files:
- has exactly **1,042 rows**, exactly **0 duplicate `time_ms` values**, and exactly **1-hour
  spacing wall-to-wall** (`max_gap_h == min_gap_h == 1.00` for every file — no gaps, no
  double-counted hours);
- spans the identical window, **2026-06-03T11:00:00Z → 2026-07-16T20:00:00Z** (43.4 days);
- carries a **single** `fetched_at` value, `2026-07-17T01:40:22.534536+00:00` — one bulk
  historical pull, not an ongoing collector pass.

0 malformed lines across all 13 files (13,546 total rows). This is a genuinely complete,
gap-free, cross-asset-consistent dataset — better-behaved than most of the tape audited to
date.

## The finding: it is orphaned

`findings/2026-07-17-q42-funding-clamp-firstcut.md` (line 5) names this directory as the
`--offline` cache backing that day's first-cut Q42 probe. But:

- `git log --all -S "q42_hl_funding_cache" -- scripts/` returns **nothing** — no commit, in
  the entire repository history, ever had a `scripts/` file reference this path as a string.
- `grep -rln "q42_hl_funding_cache" scripts/ core/ collection/ tests/` returns **nothing**
  today either.
- The current Q42 cross-venue script, `scripts/q42_crossvenue_funding_join.py`, reads
  Hyperliquid data from `DEFAULT_HL_GLOB = "tape/hyperliquid_funding/dt=*.jsonl"` — a
  **different, separate** family, backfilled by `collection/hyperliquid_funding.py` and kept
  live by incremental refresh (L127/L134). That family covers **BTC and ETH only**
  (`{'BTC', 'ETH'}`, verified against every committed `dt=*.jsonl` today) — 2 of the 13 assets
  this cache holds.

So `tape/q42_hl_funding_cache/` is not a stale copy of the live family; it is a **disjoint,
wider-coverage, one-shot snapshot** (13 assets vs. 2) that the pipeline never wired in. The
`--offline` capability the 07-17 finding describes appears to have been prototyped against this
cache and then superseded by the incremental `tape/hyperliquid_funding/` collector before any
script that reads this path landed in the tree — an evolution-in-place, not a defect in either
family's own collection.

## Why this matters (data-quality read, not a verdict)

1. **Don't mistake it for current.** The cache is frozen at 2026-07-17; today is 2026-08-13,
   27 days later. Its window (06-03→07-16) does not overlap the live family's coverage at all.
   Any future reader who greps `tape/` for Hyperliquid funding and finds this directory first
   could join it as if it were live and silently backtest against month-old, single-snapshot
   data with no `price_source_tag` distinction from the live family (both say `broker_truth`).
2. **It is a real, unused resource for the 11 non-BTC/ETH assets.** If a future Q42 milestone
   wants to extend the cross-venue join beyond BTC/ETH, this cache already has clean HL funding
   for all 13 Kalshi perp contracts — but only for the historical 06-03→07-16 window; it cannot
   answer anything about now without a live collector extension (a build task, not analysis).
3. **Not a defect to fix under this run's scope.** Wiring this cache into a script, extending
   `collection/hyperliquid_funding.py` to the other 11 assets, or deleting the orphaned
   directory are each a deliberate decision (build or cleanup), not a data-quality repair — left
   for Ryan / a future dedicated milestone, consistent with how L127 handled the sibling
   HL-family freeze finding (flagged, not fixed, in the same idle-run policy (c) class).

## Reproduce

```
python3 - <<'EOF'
import json, glob
from datetime import datetime, timezone
for f in sorted(glob.glob("tape/q42_hl_funding_cache/hl_funding_*.jsonl")):
    rows = [json.loads(l) for l in open(f) if l.strip()]
    times = sorted(r["time_ms"] for r in rows)
    gaps = [(times[i+1]-times[i])/3.6e6 for i in range(len(times)-1)]
    print(f, len(rows), len(times)-len(set(times)), max(gaps), min(gaps),
          len(set(r["fetched_at"] for r in rows)))
EOF
grep -rln "q42_hl_funding_cache" scripts/ core/ collection/ tests/   # -> no output
grep -n "DEFAULT_HL_GLOB" scripts/q42_crossvenue_funding_join.py     # -> tape/hyperliquid_funding
```

No code changed this run. `pytest`/`invariants --full` gates are unaffected by a docs-only
diff; see the Log-of-runs line for the fresh-gate-line count taken after this commit's actual
last change (the step-0b tape sweep below).

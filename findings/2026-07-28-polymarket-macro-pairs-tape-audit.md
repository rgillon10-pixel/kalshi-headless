# 2026-07-28 — `tape/polymarket_macro_pairs/` data-quality audit (first dedicated pass)

Idle-run policy (c) (LOOP-QUEUE.md v3): a dedicated data-quality deep-dive on
`polymarket_macro_pairs`, the Fed-decision cross-venue tape (Kalshi `KXFEDDECISION*` vs
Polymarket) that Q19/Q48/S55 (`scripts/q48_s55_fomc_lag_probe.py`) depend on. No dedicated
audit of this family existed before today — every other actively-collected family
(perp_tape, settlement_ledger, hyperliquid_funding, orderbook_depth, weather_books,
universe_sweep) already has one. Timed deliberately: the FOMC burst-capture trigger
(`kalshi-burst-fomc-0729`) fires **2026-07-29T17:40:00Z**, ~41.5h from this audit, so any
live risk found today is still actionable. Produced by a `tape-auditor` subagent; every
number below was independently re-derived from the committed bytes (per-line `json.loads`,
`git ls-tree`/branch diffs), not taken from any prior finding. Two-agent verdict rule N/A —
data-quality audit, not a registry flip/CI/kill decision (same posture as the
perp_tape/settlement_ledger/hyperliquid_funding audit precedents).

## Coverage

`tape/polymarket_macro_pairs/` — 21 day-files, `dt=2026-07-06` … `dt=2026-07-27`
(`dt=2026-07-09` is the one missing calendar day — confirmed absent from `main` AND from all
200 `refs/heads/tape/*` branches, so it is genuinely lost, not stranded). **9,090 lines**,
4.4 MB, **0 malformed** (100% valid JSON). **606 distinct `capture_id`s**, each carrying
exactly 15 rows (3 tracked `KXFEDDECISION` meetings × 5 outcome buckets) — 0 captures with a
short/long row count, 0 duplicate `(capture_id, meeting, bucket)` keys, 0 `capture_id`
spanning more than one day-file. `family="fed_decision"` and
`schema_version="polymarket_macro_pairs.v1"` on all 9,090 lines.

## What's clean

- **Trust tags (CLAUDE.md's default-FALSE rule): fully clean.** `kalshi.price_source_tag`
  and `polymarket.price_source_tag` are both `real_ask` on 9,090/9,090 rows — 0 `synthetic`,
  0 `midpoint`, 0 untagged, on either leg. (Contrast the sibling `tape/polymarket_cpi_pairs/`,
  whose Kalshi leg is `synthetic` by construction — a genuinely different family, not a bug
  here.)
- **Join keys the probe reads are 100% populated.** `scripts/q48_s55_fomc_lag_probe.py`
  joins on `family`/`schema_version`/`capture_id`/`captured_at`/`meeting`/`bucket` and reads
  `kalshi.{ticker,yes_ask,no_ask}` + `polymarket.{best_ask,best_bid,book_fetch_ok}` +
  both `price_source_tag`s — null rate on every one of those fields is **0**, except
  `polymarket.{best_ask,best_bid}`/`price_gap_yes_ask`, null on exactly **3/9,090 (0.033%)**
  rows, and all 3 are honestly self-flagged `book_fetch_ok: false` — a case the probe already
  skips (`:621`), not a silent gap.
- **Internal consistency holds.** `price_gap_yes_ask` recomputed independently as
  `kalshi.yes_ask - polymarket.best_ask` matches the stored value on all 9,087 non-null rows
  (tolerance 1e-12). 0 out-of-[0,1] prices, 0 crossed books on either leg. Identifiers are
  stable: 15 `(meeting,bucket)` keys map to exactly one `(event_id,market_id)` pair each
  across all 22 days, no reassignment.
- **Append-only holds.** 21 commits touch this directory; `git log --follow --numstat` shows
  zero deletion lines on every file.
- **Nothing stranded.** Swept all 200 `refs/heads/tape/*` branches' line-set diff for this
  family against `main` — 0 lines absent from main anywhere.
- **Re-derived headline gap numbers reproduce the 2026-07-26 finding exactly**, now extended
  2 more days: front-meeting (`2026-07`) n=3,030, mean **+0.5367¢**, median **+0.600¢**,
  mean\|gap\| **+0.7451¢** (prior run: +0.743¢/+0.745¢). `2026-09` mean\|gap\| **+1.9286¢**,
  `2026-10` **+3.7263¢**, pooled **+2.1330¢** — still not a valid single headline (L183's
  tenor-cut rule). Front-meeting floor-pinned fraction (`kalshi.yes_ask == 0.01`):
  **1,614/3,030 = 53.3%**.

## Defects found

**D1 — the collector computes `completeness_ok` and never persists it, so its own gaps are
unfalsifiable.** `run_fed_decision` (`collection/polymarket_pairs.py:634-657`) builds a full
honesty summary — `completeness_ok`, `unmatched_kalshi`, `unmatched_polymarket`,
`ambiguous_kalshi`, `book_errors`, `polymarket_discovery_error`, `raw_kalshi_sha256` — then
writes ONLY the tape lines and returns the summary in-process; nothing in the repo persists
it (`collection/hourly_pass.py` folds it into an in-memory total at `:463-470` and drops it).
A pass where Polymarket discovery raises produces `lines == []` → zero bytes written →
indistinguishable in tape from "the collector never fired." Every gap this audit measures
(D3/D4 below) is therefore attributed by absence, not by a recorded cause — this is the only
actively-collected family where a `completeness_ok` false-rate cannot be recomputed from
committed tape.

**D2 — a resolution-basis term mismatch on 2 of 5 buckets exists in code and is invisible in
tape.** Kalshi's `*_50plus` bucket derives from the title magnitude
(`collection/polymarket_pairs.py:394`, `>=25` bps → `{side}_50plus`) while Polymarket's
derives from its own `groupItemTitle` "50+ bps" wording (`:469`, `>=50` bps) — these are not
the same settlement term; a 26-49bp move resolves the two markets' `*_50plus` buckets
oppositely. Low live-risk (non-multiple-of-25 Fed moves are near-zero probability), but the
tape persists no title, question text, or resolution-source field on either leg (only
`ticker`/`event_id`/`market_id`) — the structural-title confirmation happens at match time
(`match_fed_pairs`, `:528-551`) and is discarded, so this asymmetry (and any future one like
it) cannot be audited from tape at all, only from re-reading the collector's source.

**D3 — cadence collapse, worst in the exact slot Q48/S55 needs.** Pass rate: 27.67/day over
the full 21.9-day span → 8.79/day since 07-19 → 5.74/day since 07-23; median inter-pass gap
3.00h. Largest gaps: 56.91h (07-08T11:00→07-10T19:55), then a run of ~6-12h holes 07-23
through 07-27. Captures landing in the FOMC-relevant 17:40-18:30Z window: 1-2/day through
07-17, **zero on every day 07-18 through 07-27** (10 consecutive days). Since 07-23 the 18Z
hour produced a capture on only 2 of 5 days, both ~55min late (~18:55Z). On 07-27 the tape
jumps 15:55:15Z straight to 21:55:40Z — a 6.01h hole straddling 18:00Z exactly.

**D4 — `dt=2026-07-09` is fully absent**, confirmed lost (not stranded) per the branch sweep
above.

## Live risk to the 2026-07-29 FOMC burst — quantified, and still actionable

1. **If the burst trigger doesn't fire cleanly, the recurring 3-hourly leg is not a
   fallback.** D3's own numbers say so directly: 0 captures in the release window on any of
   the last 10 days. A repeat of the burst failure means `scripts/q48_s55_fomc_lag_probe.py`
   returns INSUFFICIENT DATA for the FOMC event specifically — a third occurrence of the
   WC-semi1/WC-final pattern (`LOOP-QUEUE.md` Q19 Status lines, both burst-fired-but-lost).
2. **The live trigger still carries the known-broken single-commit design.** Checked directly
   against the trigger API this run: `trig_01L9RysFtWUUjj3BgQmNKw7g`
   (`kalshi-burst-fomc-0729`, `next_run_at: 2026-07-29T17:40:00Z`, enabled) runs
   `python -m collection.burst_capture --until 2026-07-29T19:45:00Z --interval 90 --families
   fed,econ,crypto` for the full ~125-minute window, THEN does one commit + one push at the
   very end. `ops/ROUTINES.md` and `kb/00-LOG.md` (2026-07-26 entries) both record that the
   seam-safe chunked recipe (`ops/burst_capture_chunked.md`,
   `scripts/burst_chunk_plan.py --protect 2026-07-29T18:00:00Z` → chunks
   `[16,14,14,14,14,12]`) is built and verified but **was never applied to this live trigger**.
   Base rate on the single-commit-at-end design across this project's prior one-shot bursts:
   2 of 4 lost 100% of their captured tape (WC-semi1, WC-final — both `last_fired_at` set,
   zero tape ever landed).
3. **This family's only burst-density tape today is a CPI window, not an FOMC one.**
   Clustering the 606 passes at ≤300s gaps finds exactly two runs of ≥5 passes: a 5-pass
   blip on 07-06, and the 07-14T12:07-13:45Z CPI burst (n=101, median gap 60.1s). Zero
   FOMC-covering windows exist yet — Q48/S55's entire 07-29 evidentiary basis is tape that
   does not exist yet.
4. **Seam risk persists even if the chunked recipe is applied.** Chunk 1
   (17:40:00-18:02:30Z) gives 14 pre-release ticks but only 2 post-release ticks
   (18:01:00, 18:02:30) before the inter-chunk commit boundary. The probe clusters bursts at
   `BURST_MAX_INTERVAL_S=300.0` (`scripts/q48_s55_fomc_lag_probe.py:283`) — if the
   commit/push/verify pause between chunks exceeds 5 minutes, the release-covering window is
   silently truncated at 18:02:30Z rather than disqualified (each chunk individually still
   clears `BURST_CADENCE_MIN_PASSES=10`/`BURST_CADENCE_MIN_DURATION_S=600` at `:291-292`, so
   nothing would flag the truncation).
5. **Resolution timing is coarser than the phenomenon.**
   `KILL_MAX_CAPTURES_TO_REPRICE=1` and `STALE_WINDOW_MIN_SECONDS=60.0` (`:300-301`) resolve
   the kill/keep decision at ±90s (the capture interval), coarser than the 60.1s median
   convergence already on record from the 07-14 CPI burst.
6. **One shot only** — Kalshi discovery filters `status:"open"` (`:422`); once the 26JUL
   markets settle on 07-29 the front-meeting rows stop existing, no re-capture is possible.
7. **Even a perfect capture is descriptive-only.** `MIN_BURSTS_FOR_CI=3` (`:295`) — n=1
   cannot produce a CI by the probe's own design; worth stating so tomorrow's result (if any)
   isn't misread as a probe failure rather than an expected single-event descriptive cut.

## Recommended follow-up (not acted on this run — Ryan-side judgment calls per protocol)

1. **Time-critical, before 2026-07-29T17:40Z:** confirm whether `trig_01L9RysFtWUUjj3BgQmNKw7g`
   carries the chunked recipe; if not, apply it (`ops/burst_capture_chunked.md`). Keep any
   inter-chunk pause under 300s so the probe doesn't split the release window.
2. **Cheap insurance regardless of (1):** the recurring 3h collector will not land a capture
   near 18:00Z on 07-29 (base rate 2/5 days at ~18:55Z per D3) — a manual
   `python -m collection.polymarket_pairs` (or `burst_capture --families fed`) around
   ~17:55Z/~18:05Z would guarantee at least a bracketing pre/post record even if the burst
   session dies.
3. **D1 repair** (a future read-write run): persist `run_fed_decision`'s summary — a
   `record_type:"capture_summary"` line in the same day-file, or a sibling
   `tape/polymarket_macro_pairs/summaries/dt=*.jsonl` — so a zero-line pass becomes
   distinguishable from a non-run and a future audit can quote a real `completeness_ok`
   false-rate.
4. **D2 repair:** persist `kalshi.title` + `polymarket.question`/`groupItemTitle` (already in
   hand at match time) plus a resolution-basis tag per leg (`kalshi_rulebook`/`uma_oracle`),
   so the `>25bps` vs `50+bps` asymmetry — and any future one like it — is auditable from
   tape instead of only from source.

Not this family's problem but surfaced in passing: `tape/` overall is 1.3GB (dominated by
`universe_sweep` 445M / `orderbook_depth` 323M / `sports_pairs` 228M / `weather_books` 111M),
~26x past the ~50MB threshold `tape/README.md` names as the storage-migration decision
point (see open PR #166) — a standing Ryan-side item, unrelated to this audit's scope.

## Addendum (2026-07-28, research loop, idle-run policy (a): L212 → enforced)

D1 (recommended follow-up item 3 above) built the same day: `collection/polymarket_pairs.py::
run_fed_decision` now always appends one `family: "capture_summary"` line to the per-day
tape file — even on a zero-match or fully-failed-discovery pass, which used to write nothing
at all. It carries the exact fields the audit could not recompute from tape
(`completeness_ok`, `unmatched_kalshi`/`unmatched_polymarket`/`ambiguous_kalshi`,
`n_book_errors`, `polymarket_discovery_error`), on its own `schema_version`
(`polymarket_macro_pairs_summary.v1`, never the pair-record schema) so every existing reader
that filters on schema_version/family (`q31_cross_venue_arb_probe`, `q48_s55_fomc_lag_probe.
load_family_records`) skips it exactly like a foreign record — verified directly, not
assumed. D1 closed; D2 (bucket-definition provenance) and D3/D4 (burst-trigger recipe,
lost 07-09 day) remain open, D3 still time-critical and Ryan-side per the recommendation
above. See `kb/lessons/00-lessons.md` L215 (formal disposition of L212).

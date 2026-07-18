# weather_books tape audit (Q36 gate mid-flight check)

- **Date:** 2026-07-18 (audit run at 21:12 UTC)
- **Scope:** `tape/weather_books/` (Q36 gate: >=7 days hourly-family); cross-check `tape/weather_actuals/`
- **Mode:** READ-ONLY. No collector code touched, no repair applied.
- **Collector audited against:** `collection/weather_books.py` (schema `weather_books.v1`, `_book_record` lines 222-256)
- **Verdict (one line):** **gate-at-risk** — schema/validity/tags are pristine and 07-17 is a perfect clean day, but a whole-VPS commit stall on 07-18 (08:30Z onward) has already punched permanent holes in day-3 hourly cadence. Not a `weather_books` code bug; an ops/uptime problem.

---

## 1. Per-day line counts & cadence

Total: **31,928 lines** across 3 day-files, 71 distinct capture passes. All 5 hourly series
(`KXTEMPAUSH`, `KXTEMPCHIH`, `KXTEMPDCH`, `KXTEMPLAXH`, `KXTEMPNYCH`) present every pass; 45 distinct
series overall (40 daily + 5 hourly), stable across all three days.

| day | file | lines | passes | UTC hours present | hourly lines | KXTEMPNYCH lines | assessment |
|-----|------|------:|-------:|-------------------|-------------:|-----------------:|------------|
| 2026-07-16 | `tape/weather_books/dt=2026-07-16.jsonl` | 12,758 | 28 | 01–23 (hour **00 absent**) | 1,520 | 300 | day-1 partial, expected — collector landed 07-15, first capture `20260716T012911Z` @01:29Z |
| 2026-07-17 | `tape/weather_books/dt=2026-07-17.jsonl` | 13,722 | 31 | **00–23 all present** | 1,560 | 320 | CLEAN full day |
| 2026-07-18 | `tape/weather_books/dt=2026-07-18.jsonl` | 5,448 | 12 | **00–08, 13 only** | 600 | 120 | BROKEN — see gap list |

Line count per pass varies 290–530 (fewer overnight-UTC open markets); hourly lines/pass 50–100.
This variation is normal venue structure (open-market count), not a capture defect.

### Gap dates / missing hours (exact)
- **2026-07-16 hour 00** — absent because the collector had not yet started (first pass 01:29Z). Not a stall.
- **2026-07-18 hours 09, 10, 11, 12** — absent (already-elapsed, permanent hole).
- **2026-07-18 hours 14–23** — absent in main except a single cloud catch-up capture `20260718T130049Z` @13:00Z.

### Root cause (from `git log`, main)
The whole VPS commit pipeline stalled after `2026-07-18T08:30:19Z` (last `(vps)` pass). ALL families
went quiet, not just weather_books — the next main commits are a single cloud idle-run batch at
~13:00–13:03Z (`weather_books`, `weather_actuals`, `universe_sweep`, `orderbook_depth`/`perp_tape`),
then nothing on main. So the 07-18 hole is a host-uptime stall, not a `weather_books.py` fault.

## 2. JSON validity & schema

- **31,928 / 31,928 lines parse as JSON. 0 parse failures.**
- **0 missing fields, 0 extra fields** vs the 24-field `weather_books.v1` contract in `_book_record`
  (`collection/weather_books.py:226-256`): schema_version, capture_id, captured_at, venue, group,
  series, ticker, close_time, strike_type, floor_strike, cap_strike, yes_sub_title, raw_orderbook,
  book_shape, yes_bids, no_bids, best_yes_bid, best_no_bid, best_yes_ask, best_no_ask, depth,
  price_source_tag, price_source_tags, raw_sha256.
- `schema_version` = `weather_books.v1` on 100% of lines. `book_shape` = `orderbook_fp` on 100%
  (no legacy-cents fallback fired, no `empty`-shape venue rollback).
- Books carry real levels: 07-17 hourly 1,509/1,560 lines have >=1 bid level and a derived best ask;
  51 fully-empty books are valid-not-dropped (lesson L23). Sample: `depth=48, best_yes_ask=0.04,
  best_no_ask=0.97`.

## 3. price_source_tag correctness

- `price_source_tag` = **`real_ask` on 31,928/31,928 lines (100%)**. Zero `synthetic`, zero untagged.
- `price_source_tags` = `{"asks":"real_ask","bids":"real_bid"}` on 100% of lines.
- Matches CLAUDE.md trust-default + Hard Rules #3/#4 and the collector's own contract
  (`weather_books.py:252-254`). No silent synthetic default. PASS.

## 4. Append-only integrity & stranded-branch tape

- **Append-only PASS:** `git log --numstat` shows **0 removed lines** on all three day-files
  (added: 12,758 / 13,722 / 5,448; removed: 0 / 0 / 0). 07-16 arrived in one branch-sweep commit;
  07-17/07-18 grew incrementally.
- **Stranded tape:** `git ls-remote --heads origin 'refs/heads/tape/hourly-*' 'refs/heads/tape/burst-*'`
  returns ~200 branches, almost all dated 2026-07-03…07-06 (pre-collector, cannot hold weather_books).
  Recent branches carrying a 07-18 weather_books file: `tape/hourly-20260718T0403Z` (6 passes, all
  already in main — 0 new lines) and **`tape/hourly-20260718T1855Z`** which holds **1 pass main lacks:
  `20260718T190341Z` (530 lines, @19:03Z)**. Freshness OK (>2h old, past the 30-min rule).
  Sweeping it would add hour 19 to 07-18, but hours 09–12, 14–18, 20–23 stay empty — the stranded
  line is a fragment of, not a fix for, the VPS stall. (Sweep/append belongs to a read-write run.)

## 5. Cross-check: weather_actuals join-ability (Q36/Q37)

- `tape/weather_actuals/` present for all 3 days (2 / 40 / 20 lines; schema `weather_actuals.v1`).
- Join key exists: actuals carries `cli_station=KNYC` / city `New York` — the settlement station for
  hourly `KXTEMPNYCH`. All 20 config cities present.
- `weather_books/meta/dt=*.jsonl` (45 series/day) records `KXTEMPNYCH` settlement source verbatim:
  `[{"name":"The Weather Company","url":"https://weather.com/kalshi"}]`, `frequency=one_off`,
  `detail_error=null` — the settlement-basis reference the W-B study needs is captured.
- **Join caveat (not a defect):** `weather_actuals.settled_markets` currently joins DAILY series
  (`KXHIGHT*`/`KXLOWT*`, tag `broker_truth`); it does not yet settle the hourly `KXTEMPNYCH` line.
  Q36's settlement-basis join will need an hourly-actual source (The Weather Company KNYC intraday),
  which this daily-climate actuals feed does not provide. Flag for Q36 design, not for this audit.

## 6. Size trajectory

- `du -sh tape/weather_books/` = **60M** (24M + 26M + 12M per day) — **already past the ~50 MB
  threshold** `tape/README.md:15` names as the "move to external storage — Ryan's decision" trigger.
  At ~25 MB per full day (raw_orderbook stored verbatim per line), 7 gate-days project to ~175 MB.
  `weather_actuals` is negligible (104K).

---

## FLAGS

1. **[gate-risk] 07-18 VPS commit stall.** No pass committed to main between 08:30Z and ~13:00Z, and
   nothing after 13:03Z (main) except a stranded 19:03Z branch pass. Hours 09–12 of 07-18 are a
   permanent hole; the rest of the day is near-empty. All families affected → host uptime, not
   weather_books code. **Repair (for the lead to dispatch, not this run):** restart the VPS collector
   loop; sweep `tape/hourly-20260718T1855Z` to recover the 19:03Z pass.
2. **[size] weather_books already 60 MB (>50 MB README trigger) at day ~2.5.** External-storage
   decision for Ryan is now, not later; verbatim `raw_orderbook` per line is the driver.
3. **[join-gap, downstream] weather_actuals settles only DAILY series.** Hourly `KXTEMPNYCH`
   settlement basis has no matching actual in this feed — Q36 will need an intraday KNYC source.

## Gate reality (item 5)

Q36 needs >=7 days of hourly-family coverage; the implied calendar date from day-1 (07-16) is ~07-22.
Clean hourly-cadence days banked so far: **07-17 (1 full clean day)**; 07-16 is a day-1 partial
(hour 00 only missing); **07-18 is currently NOT clean** (VPS stall). If a gate "day" requires roughly
complete hourly cadence, 07-18 does not qualify as-is, so the 7th clean day slips past the naive 07-22
to **~07-23 or later, and continues slipping for every future day the VPS is down.** The collector
itself is delivering clean, well-tagged, append-only tape whenever it runs — the only thing between
here and the gate is VPS uptime. Cadence *if uninterrupted* delivers 7 clean days on schedule; cadence
*as actually observed on 07-18* does not.

## Lesson candidate (for kb-distiller)

A per-family tape family can be schema-perfect and still miss its gate purely on collector-host
uptime: measure gate progress in **committed clean capture-days on main**, not calendar days elapsed
since day-1. A day with a multi-hour host stall (permanent past-hour holes) should not silently count
toward a day-count gate. Consider a cadence-completeness assert (e.g. >=N passes AND no >2h intra-day
gap) before a day is credited to a gate.

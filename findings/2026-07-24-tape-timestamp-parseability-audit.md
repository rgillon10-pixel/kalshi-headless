# Tape timestamp-value parseability audit — the L136/L138 Python-3.9 `fromisoformat` hazard is LIVE in committed tape (URGENT)

`2026-07-24` · research loop, idle-run policy (c) data-quality deep-dive · read-only over committed tape · two-agent confirmed (tape-auditor + verifier, exact-integer agreement) · reproducer `scripts/tape_timestamp_parseability_audit.py`

## Question (falsifiable)

L138's own row states: *"this sandbox runs Python 3.11 (where `fromisoformat` already tolerates short fractions), so the fix could not be proven against the literal 3.9 failure here."* So it was an **open, never-measured** question whether the committed tape **actually carries** the timestamp shape that crashes a strict Python-3.9 `datetime.fromisoformat` consumer, or whether the L138/L141 raw-`fromisoformat` migration backlog (36 code call sites) is a purely theoretical hazard. This audit answers it directly.

This is a distinct dimension from the recent data-quality audits: L142 (git-conflict markers), L143 (zero/null/constant numeric fields), L148 (JSON-per-line structural validity), Q43 (`record_type` consumer-correctness) all checked **structural** validity; none checked **semantic timestamp-value parseability**.

## Method

`scripts/tape_timestamp_parseability_audit.py` (read-only, offline, no network) walks `tape/<family>/dt=*.jsonl`, recursively finds every ISO-8601 timestamp **string** value, and classifies each. Because the sandbox is Python 3.11 (where raw `fromisoformat` tolerates the hazardous shapes), the 3.9 hazard is **emulated by a regex/digit-count rule**, never by calling `fromisoformat` and catching:

- **3.9-HAZARDOUS** = ends in a bare trailing `Z` **OR** its fractional-seconds digit-count ∉ {3, 6} (a short 1–2 digit fraction, or an over-length >6-digit nanosecond fraction).
- **3.9-CLEAN** = numeric UTC offset (e.g. `+00:00`) and fraction absent or exactly 3/6 digits.
- Every value is also cross-checked through `core.timeutil.parse_iso_utc` (the sanctioned wrapper, L138) to confirm it neutralizes the hazard.

## Result — VERDICT: URGENT

Over the canonical `dt=` tape (182 files, 1,030,416 lines, the committed reproducer's own run):

| metric | value |
|---|---|
| ISO timestamp string values scanned | **1,669,146** |
| 3.9-HAZARDOUS | **638,730 (38.27%)** |
| 3.9-CLEAN | 1,030,416 |
| genuinely unparseable (any parser) | **0** |
| `core.timeutil.parse_iso_utc` failures | **0** |
| families carrying the hazard | 12 |

Reason breakdown: `bare_z` 638,730 · `overlen_frac` (9-digit nanosecond) **1,409** · `short_frac` (1–2 or 4–5 digit) **1,054**.

Two independent agents (a `tape-auditor` pass and an adversarial `verifier` re-derivation with its own from-scratch code) reproduced the **broader** scope — all `.jsonl` under `tape/` incl. probe caches (210 files / 1,058,610 lines / 23 families) — to the **exact integer**: **1,725,070** total, **653,208 (37.87%)** hazardous, 650,745 bare-Z-only, 2,463 short/odd-frac-and-Z, 0 unparseable, 0 wrapper failures. The scope gap (210 vs 182 files) is exactly the 28 non-`dt=`-named probe-cache `.jsonl` files (`q42_hl_funding_cache` ×13, `sports_clv_s7`, `sports_history_s7`, `seed5_funding_cache`, etc.). **Both scopes give the same URGENT verdict** — ~38% of committed timestamps are 3.9-hazardous, and the wrapper fixes 100%.

## Concrete hazard shapes present in real tape

- **Bare `Z` (dominant, ~99.6% of hazards):** e.g. `2026-07-03T06:00:00Z` (`crypto_hourly`), and seconds-less `2026-06-28T02:00Z` — Python 3.9 rejects `Z`, needs `+00:00`.
- **The literal L136 short fraction:** `2026-06-19T20:54:47.2Z`, `2026-06-28T01:18:29.71Z` in `sports_history/occurrence_datetime` (~36 values) — 3.9 requires exactly 3 or 6 fractional digits.
- **NEW shape L136 never named — 9-digit NANOSECOND fractions:** `2026-07-03T05:14:41.181618848Z` in `crypto_hourly/exchange_time` (exactly **1,409** values). `core.timeutil.parse_iso_utc` truncates the fraction to 6 digits and parses it without error (verifier-confirmed) — so the sanctioned wrapper is a **complete** fix, but any consumer that assumes ≤6 fractional digits or calls raw `fromisoformat` would break on it.

## Implications

1. **The L138/L141 backlog is an URGENT live landmine, not theoretical.** A production consumer running under Python 3.9 (or any parser assuming the 3.9 `fromisoformat` contract) would crash on **38% of committed timestamps** — including the auto-collected `captured_at`/`fetch_ts` fields that every backtest reads. The advisory L141 already surfaces the 36 raw-`fromisoformat` code call sites; this audit shows those sites are reading data that genuinely triggers the bug.
2. **`core.timeutil.parse_iso_utc` is confirmed the complete fix** — 0 failures over 1.67–1.72M values across every hazardous shape, including the newly-surfaced nanosecond fraction. The migration is a mechanical repoint, not a redesign.
3. **The migration itself stays a separate, behaviour-sensitive pass** (tz-aware vs naive comparison semantics vary per call site — L138's own scope note), too large for one idle milestone; this audit's job is to prove urgency and give the re-runnable evidence.
4. **No genuine corruption** — 0 unparseable values; this is a *format-contract* hazard, not a data-integrity defect (distinct from L142's conflict markers).

## Reproduce

```
python scripts/tape_timestamp_parseability_audit.py            # human table + verdict
python scripts/tape_timestamp_parseability_audit.py --json     # machine-readable
```

Offline tests: `tests/test_tape_timestamp_parseability_audit.py` (12 cases: classifier per shape incl. the 3.11-accepts-but-hazardous `.71Z` case, the wrapper-parses-every-shape load-bearing check, and end-to-end URGENT/BENIGN over a fixture).

No registry change, no P&L, no CI — a data-adequacy/integrity characterization (same posture as L143). Two-agent rule not a verdict-class trigger, but redundancy applied anyway (tape-auditor + verifier exact agreement). Lesson **L150**.

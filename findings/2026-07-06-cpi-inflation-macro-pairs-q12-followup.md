# Q12 follow-up — S17 CPI/inflation leg: derived-transform pairing (2026-07-06)

**Status:** data-collecting (S17 stays `data-collecting`; this closes the item's only
documented remaining-work gap besides accumulation). Not a verdict — one live snapshot,
descriptive only.

## Why this needed a different design than the Fed-decision leg

The Fed-decision leg (Q12's first cut, same day) could pair Kalshi and Polymarket 1:1
because both venues quote the *same partition* of the *same question*: exactly 5
mutually-exclusive buckets, each a real, independently fillable Yes/No market on both
sides.

CPI is structurally different. Kalshi's `KXCPI`/`KXCPIYOY`/`KXCPICORE` series (see
`collection/econ_prints.py`) price a *cumulative* ladder — each market asks "will the
print exceed threshold T?" and several strikes share one `event_ticker`, nested rather than
partitioned (`core.pricing.bracket_sum` is deliberately not applicable here, per that
module's own docstring). Polymarket prices the *same report* as an exact 0.1-point-wide
bucket partition instead: "≤0.0%", "0.1%", "0.2%", ..., "0.6% or more" (confirmed live
2026-07-06 against "Core CPI MoM - July 2026", "Core CPI YoY - June 2026", and "June
Inflation US - Monthly/Annual").

There is no same-question `real_ask` pair here — a Polymarket bucket's probability has to
be *derived* from two adjacent Kalshi asks. Faking a same-question pair (e.g. treating the
nearest Kalshi threshold's `yes_ask` as if it priced Polymarket's exact bucket) would
directly violate Hard Rule #3 ("no `yes_ask` treated as probability" without the correct
transform) — this is exactly why the Fed-decision cut named this a deferred follow-up
instead of building it on the spot.

## The transform

`price_cpi_bucket_from_kalshi(strikes, bucket_kind, bucket_value)` in
`collection/polymarket_pairs.py`, given Kalshi's `{floor_strike: yes_ask}` map for one
event:

- **floor** ("≤ V"): `1 - ask(V)`
- **exact** ("= V"): `ask(V - step) - ask(V)`
- **ceiling** ("≥ V"): `ask(V - step)` directly (Kalshi already prices "exceed V-step", the
  literal same event as "V or more" once granularity is 1 step)

`step = 0.1`, confirmed live against both venues' actual quoting granularity for all 3
series before being hardcoded as a constant rather than assumed. If either required Kalshi
strike is missing (a threshold Kalshi hasn't listed), the function returns `None` — the
bucket is recorded as unpriced (`n_buckets_priced < n_buckets_total`), never guessed.

Every derived value is tagged `synthetic`, never `real_ask`, even though its two inputs are
each a genuine Kalshi fill — the transform itself is a model (a subtraction across two
markets), which is the whole reason this leg was deferred rather than built alongside the
Fed leg.

**Monotonicity is not enforced, only reported.** A coherent market has `ask(T)`
non-increasing in `T`; a thin or stale strike can violate that, producing a negative
"derived probability." This is recorded honestly via `monotonicity_violation: true`, never
clipped to zero or silently dropped — the same "record it, don't paper over it" discipline
`anomaly_sweep.py` and the crypto/basis probes already follow.

## Discovery

**Kalshi side** (`discover_kalshi_cpi_events`): every open event across the 3 US CPI
series, keyed by `(series_key, year, month)` parsed from the event ticker
(`SERIES-<yy><MON>`, e.g. `KXCPICORE-26JUL`) — reusing `econ_prints.py`'s own series-key
map so the two collectors' naming never drifts apart. Only `strike_type == "greater"`
markets with a live ask are kept; everything else is dropped, never fabricated.

**Polymarket side** (`discover_polymarket_cpi_events`): `/public-search` on `"CPI"` and
`"Inflation"`, filtered to the 3 US-series title shapes (`Core CPI MoM - <Month> <Year>`,
`<Month> Inflation US - Monthly`, `<Month> Inflation US - Annual`) — every other country's
inflation event (Japan, UK, Eurozone, Brazil, ...) and off-topic keyword hits (egg prices,
ground-beef prices) that also matched the search terms are excluded structurally, not by
guessing. `cpi_mom`/`cpi_yoy` titles carry no year — inferred from the event's own
`endDate` (the release date), correctly handling the December-report/January-release
year rollover. Buckets are parsed from each market's `groupItemTitle` (`_parse_pm_cpi_bucket_label`
handles the inconsistent open-ended marker placement observed live: "≤0.0%" vs "<1.0%" for
floors, "0.6%+" vs "≥3.3%" for ceilings).

**Matching**: exact `(series_key, year, month)` key, same match/unmatched/ambiguous
discipline as the WC-round and Fed-decision legs. Completeness is judged against
Polymarket's side (same rationale as the Fed leg — Kalshi's series lists events further
forward than Polymarket creates them), *plus* a finer-grained bucket-level completeness
signal: a Polymarket bucket whose required Kalshi strike(s) are missing lowers
`n_buckets_priced` below `n_buckets_total`, which does gate completeness — that gap is a
real pricing limitation, not forward-calendar noise.

## Wiring

`run_cpi()` writes to its own tape family, `tape/polymarket_cpi_pairs/`. Wired into
`collection/hourly_pass.py`'s existing 09 UTC daily slot (same slot as `econ_prints`) rather
than every hour — CPI prints release monthly and the underlying Kalshi ladder doesn't move
meaningfully faster than that either, so hourly polling would just be extra load for no new
information.

## Live pass (2026-07-06)

- 17 open Kalshi CPI events across the 3 series.
- 3 Polymarket events matched (current core-CPI-MoM, core-CPI-YoY, and headline-CPI-MoM
  prints — the only ones Polymarket currently lists for these 3 series), 0 unmatched, 0
  ambiguous.
- 28 Polymarket buckets requested across the 3 matched events; **22 priced, 6 not** — the 6
  gaps are all cases where Polymarket's bucket partition extends one or two steps further
  out-of-the-money than Kalshi's currently-open ladder reaches (e.g. Polymarket's `cpi_mom`
  event asks about a 0.6–0.9% range Kalshi hasn't listed strikes for yet). Recorded, not
  hidden — `completeness_ok: False` this pass, correctly.
- One derived bucket (`cpi_core_mom` 2026-07, exact 0.5%) came back with
  `monotonicity_violation: true`: Kalshi's raw ladder for that far-forward month prices
  "exceed 0.4%" at 8¢ and "exceed 0.5%" at 97¢ — backwards for a coherent market, a live
  example of the thin/stale far-OTM quoting this project's other probes (Q2/Q5's crypto
  overround, Q6's anomaly sweep) have already documented. Recorded as `derived_prob: -0.89`,
  not clipped.
- Where both sides priced, the derived Kalshi probability and Polymarket's live ask tracked
  reasonably closely (e.g. `cpi_yoy` 3.8%: derived 0.47 vs Polymarket ask 0.52) — descriptive
  only, one snapshot, not a mispricing or lead-lag claim.

## Remaining for S17 overall

S17's own gate (≥5 matched live-book pairs/month) was already cleared by the Fed-decision
leg. Both the Fed and CPI legs now run automatically at their appropriate cadence, so the
only remaining work is accumulation, then the eventual lead-lag cross-correlation — same
shape as S9, which was itself closed dead ✗ on data-adequacy grounds this run window (a
different constraint: S9 needed sub-hourly resolution around a scheduled event, which S17
does not).

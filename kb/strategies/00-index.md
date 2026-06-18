# Strategy candidates — registry

`drafted` · 2026-06-18 · seeded from `findings/2026-06-18-codebase-money-map.md` + `../quant-finance/`

Each candidate is a **falsifiable hypothesis with a binding test**, not a vibe. A candidate
may only graduate (gain capital) after a bootstrapped CI **strictly > 0 at real fillable asks**
(prime directive). Status: `idea` → `binding-test-defined` → `data-collecting` → `tested` →
`live` / `dead`. Confidence is the workflow's verifier confidence.

| id | name | source | status | conf | gate (binding test, abbreviated) |
|---|---|---|---|---|---|
| **S0** | Real-ask substrate (tape + actuals gate + ask primitive) | kalshi.1 + invariants | **built ✅** | 0.9 | substrate, not an edge — enables all scoring (53 tests green, invariants live) |
| **S1** | Longshot-fade real-ask calibration (weather) | arb-bot-v2 tape · QF Theme 2 | **dead ✗** | 0.45 | TESTED n=990 real-ask brackets: net P&L CI [−$0.005,+$0.013] ⊄ >0 → falsified |
| **S2** | FOMC × ZQ single-meeting basis | kalshi.ibkr · QF Theme 6 | binding-test-defined | 0.40 | one-meeting replay, real asks − ZQ p_hold − fees; net>0 |
| **S3** | K3 cross-strike monotonicity staleness | kalshi.ibkr · QF Theme 6 | binding-test-defined | 0.30 | 1h calibrate; signal must clear artifact noise floor |
| **S4** | FEx wing-strike fat-tail mispricing | arb-bot H1 · QF Theme 5 | blocked-on-data | 0.25 | quoted tail mass < empirical by > overround+fee |
| **S5** | Weather rehab (real signal × honest fill × fwd tape) | combo · QF Theme 5 | binding-test-defined | — | fwd summer real-ask CI>0, else weather family dead |
| **S6** | Inventory-aware market-making (maker rebate of spread) | QF Theme 3 | idea | — | A-S quotes; spread income > adverse-selection cost |

## Notes on each

**S0 — substrate. → BUILT (2026-06-18).** The machine that lets every other candidate be scored
*honestly*. Lifted byte-identical from `kalshi.1@fd37ae2`: `normalize.py` (real taker ask),
`v1_actuals.py` (3-source gate), `capture_orderbooks.py` (bitemporal forward tape), `v3_market.py`.
Authored fresh for this project: `scripts/invariants.py` (6 Hard Rules, static+DB), `core/pricing.py`
(sanctioned `yes_ask/bracket_sum` site), `core/source_tag.py` (trust=FALSE default), `core/stats.py`
(safe_pstdev n≥4). **53 tests green; `invariants --full` green.** Provenance: `../../PROVENANCE.md`.
S1 was scored on top of it (above) — the substrate works. **Still GATED:** cron forward capture
(needs Kalshi creds + conflicts with the kalshi.1 laptop-cron HOLD) — see `project-status.md`.
→ `findings/2026-06-18-codebase-money-map.md` #1.

**S1 — longshot fade. → DEAD (tested 2026-06-18, real asks).** The bias *exists* and points the
textbook way — longshots (<0.20) realize fewer wins than priced (gaps −1.4¢ to −7.0¢), favorites
(>0.65) underpriced — but the mispricing is only single-digit cents and is swamped by a mean
**+9.84¢ overround** absorbed at the real ask. Net maker-NO-on-longshot P&L = **+$0.00448/trade,
95% block-bootstrap CI [−$0.00486, +$0.01333]** (n=990 reconstructed-real-ask brackets, 654
longshot trades, 21 contract-day blocks); the threshold sweep 0.05→0.25 is uniformly null and the
deepest longshots (<0.05) are negative. Lower CI bound does **not** clear zero → the whole
bias-chasing family is falsified on this sample, exactly as the dossier predicted. Prices are
`real_ask` (exchange BBO), not synthetic. Probe: `scripts/longshot_fade_probe.py`; full writeup:
`findings/2026-06-18-longshot-fade-s1.md`. **Near-miss recorded:** the first run cleared zero on a
cost-model sign bug (maker entry booked as a 2¢ improvement, not a cost) — the exact prime-directive
failure mode; caught and corrected. Candidate invariant filed: a cost haircut must never move the
entry in the trader's favor.

**S2 — FOMC × ZQ basis.** The structurally cleanest candidate: prob-to-prob, **no weather
overround** (Theme 6 no-arbitrage). But it's a directional pre-position (Kalshi halts before
settlement), unbounded per-event downside, ~8 events/year. Replay one meeting at real asks first.

**S3 — cross-strike monotonicity.** Theme 6 again: P(≥80°F) ≥ P(≥85°F) must hold; staleness can
violate it briefly. Cheapest Kalshi-only probe. Taker-by-construction → ~8¢ round-trip floor binds.

**S4 — FEx fat tails.** Theme 5 tail mispricing across venues. Blocked until the FEx tape archiver
(#24) is fixed — unrunnable, do not start until tape persists.

**S5 — weather rehab.** The open question that decides the project's direction. The directional
signal is *real*; the dollar edge died to overround. A $0-capital forward paper test on the summer
subset (where synthetic edge was strongest) settles it. **If the forward real-ask CI straddles zero,
declare the weather family dead and pivot to non-weather (S2/S3/S6).**

**S6 — market-making.** Theme 3 (Avellaneda-Stoikov). Earn the spread instead of paying it; maker
fee is 4× cheaper (`../kalshi-api/03-fees-and-breakeven.md`). The structural long-term play if a
forecast edge never materializes — but adverse selection in thin books is the killer. Idea-stage;
needs the forward tape (S0) to even estimate order-arrival intensity.

## The one rule that orders all of this

Build S0. Run S1 and S2 (near-free, no capital). Let their results — not optimism — decide whether
weather lives (S5) or the project pivots to microstructure/basis (S2/S3/S6). No weather-model capital
until a real-ask CI clears zero.

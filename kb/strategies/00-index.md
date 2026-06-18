# Strategy candidates — registry

`drafted` · 2026-06-18 · seeded from `findings/2026-06-18-codebase-money-map.md` + `../quant-finance/`

Each candidate is a **falsifiable hypothesis with a binding test**, not a vibe. A candidate
may only graduate (gain capital) after a bootstrapped CI **strictly > 0 at real fillable asks**
(prime directive). Status: `idea` → `binding-test-defined` → `data-collecting` → `tested` →
`live` / `dead`. Confidence is the workflow's verifier confidence.

| id | name | source | status | conf | gate (binding test, abbreviated) |
|---|---|---|---|---|---|
| **S0** | Real-ask substrate (tape + actuals gate + ask primitive) | kalshi.1 + invariants | **build-first** | 0.9 | substrate, not an edge — enables all scoring |
| **S1** | Longshot-fade real-ask calibration (weather) | arb-bot-v2 tape · QF Theme 2 | binding-test-defined | 0.45 | maker NO-on-longshot net P&L after fees+haircut; CI>0 |
| **S2** | FOMC × ZQ single-meeting basis | kalshi.ibkr · QF Theme 6 | binding-test-defined | 0.40 | one-meeting replay, real asks − ZQ p_hold − fees; net>0 |
| **S3** | K3 cross-strike monotonicity staleness | kalshi.ibkr · QF Theme 6 | binding-test-defined | 0.30 | 1h calibrate; signal must clear artifact noise floor |
| **S4** | FEx wing-strike fat-tail mispricing | arb-bot H1 · QF Theme 5 | blocked-on-data | 0.25 | quoted tail mass < empirical by > overround+fee |
| **S5** | Weather rehab (real signal × honest fill × fwd tape) | combo · QF Theme 5 | binding-test-defined | — | fwd summer real-ask CI>0, else weather family dead |
| **S6** | Inventory-aware market-making (maker rebate of spread) | QF Theme 3 | idea | — | A-S quotes; spread income > adverse-selection cost |

## Notes on each

**S0 — substrate (build first).** Not a money-maker itself; the machine that lets every other
candidate be scored *honestly*. Lift `normalize.py`, `v1_actuals.py`, `capture_orderbooks.py`,
the invariant engine, and `pricing.py`. Cron forward capture today. Until S0 exists, no candidate
below can produce a trustworthy number. → `findings/2026-06-18-codebase-money-map.md` #1.

**S1 — longshot fade.** Literature says weather longshots are overpriced (Theme 2: Ali 1977,
Thaler-Ziemba 1988, Snowberg-Wolfers 2010), concentrating in the final 48h. The fee caveat is
severe: cheap longshots pay a huge *relative* fee (1¢ on a 5¢ contract = 20% — see
`../kalshi-api/03-fees-and-breakeven.md`). Run the score script on the recovered 24GB tape; expect
it to straddle/below zero — but it kills or confirms a whole family near-free.

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

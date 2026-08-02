# L250 UNENFORCED → test + protocol: a saturated fill proxy stops being weak evidence and becomes no evidence

`2026-08-02` · research loop, IDLE RUN, idle-run policy (a) · **no registry flip, no bootstrap CI,
no kill decision — S68 stays `dead ✗`, still 0 proven edges**

## What this is (and is not)

This is a **lesson→test conversion**, not a probe. Nothing here is a verdict about any strategy.
The only numbers below are *fill-rate statistics recomputed from committed tape* under two fill
rules that `scripts/q49_s68_bothside_maker_fillsim.py` already implemented; no P&L claim, no CI,
and no registry row changes. Verdict class: **methodology/tooling**.

## The gap

`kb/lessons/00-lessons.md` **L48** established that a *turnover* queue-departure proxy (departures
at ANY level at or above our resting price) can rule a population **OUT**, never IN. **L250** (from
Q49/S68's 2026-08-01 verifier pass) added the corollary L48 never stated: over a hold long enough
for the book to migrate away from a now-stale resting price, **every** size reduction anywhere above
us counts as advancing us, the cumulative counter runs to tens of thousands against a queue of tens,
and the rule fills essentially everything. At that point a HIGH fill rate is **not weak evidence of
fillability — it is no evidence in either direction**, because the statistic has no variation left.

L250's own enforcement cell said "not statically assertable ... likely terminal as protocol". That
claim is **half right**, and this run corrects it the same way L249/L251 corrected theirs: *which*
rule a probe calls primary is a design choice and stays protocol, but **whether the loose rule has
saturated is a plain statistic** — the fill rate, the departures-to-queue ratio and the hold length
were all already computed by Q49 and simply never compared.

## Built

1. **protocol** — `.claude/agents/edge-prober.md` gains a house-style bullet citing **L250** by ID,
   with Q49's own measured numbers stated verbatim so the shape is recognisable before it is
   repeated.
2. **test** — `core.bootstrap.turnover_rule_saturation(loose_filled, strict_filled, departures=...,
   queue_ahead=..., snapshots_held=...)` plus `TURNOVER_SATURATION_RATIO=10.0`,
   `TURNOVER_SATURATION_FILL_RATE=0.95`, `MIN_SNAPSHOTS_FOR_SATURATION=8`,
   `PRIMARY_FILL_RULE`/`DIAGNOSTIC_FILL_RULE`. It reports `loose_fill_rate`, `strict_fill_rate`,
   `fill_rate_gap`, `median_departure_queue_ratio`, `frac_units_above_ratio_floor`,
   `median_snapshots_held`, `long_hold`, `loose_rule_discriminates`, `saturated`,
   `loose_rule_direction`; echoes every threshold it used; **excludes and counts** zero-queue
   (front-of-queue) units rather than treating an undefined ratio as infinite; and returns
   `no_signal=True` on an empty population rather than a clean bill.
3. **operative half the row did not ask for** — `core.bootstrap.headline_fill_rate(report, rule)`
   **raises** on the loose rule *always* (saturated or not: L48's OUT-only direction is
   unconditional), so a fill-rate headline cannot be taken from the turnover proxy through this API.
   It can only REMOVE a headline, never award one.
4. **a real adopter** (L59's zero-caller residual, deliberately avoided) —
   `scripts/q49_s68_bothside_maker_fillsim.py` computes the report for every labeled cut, prints it
   beside the fill counts, persists it as `turnover_saturation`, and fetches its printed
   headline-eligible rate **through the guard**.

## Measured (committed tape, frozen fixture)

Frozen to `tests/fixtures/q49_turnover_saturation_2026-08-02.json` per L191/L192 — the depth tape
grows hourly, so the acceptance tests bind to a committed snapshot, never the moving tree.
`price_source_tag` on every input: `real_bid(fills)+real_bid(queue)+broker_truth(settlement)`.

| cut | n | loose `turnover` both-fill | strict `touch` both-fill | median departures / queue_ahead | median snapshots held | `saturated` |
|---|---|---|---|---|---|---|
| `unrestricted` | 445 | **97.98%** | **42.47%** | 306.2x | 66 | True |
| `fillable_entry` (Q49 PRIMARY) | 20 | **100.00%** (20/20, `loose_rule_discriminates=False`) | **55.00%** | 31.7x | 32 | True |

**L250's own stated measurement reproduces exactly** ("the turnover rule read 98% both-fill ... a
stricter `touch` rule read 42% on the identical tape"): 97.98% vs 42.47% on the same 445 candidates.
The primary cut is the sharper illustration — the loose rule fills 20 of 20, a statistic with zero
variation, which is precisely why Q49's verdict had to rest on the strict rule's 55%.

## Additive-only

A JSON diff of the same `scripts/q49_s68_bothside_maker_fillsim.py` run before and after the change
shows exactly one added key per cut (`turnover_saturation`, 8 paths = 4 cuts x 2 model views) and
every pre-existing field byte-identical apart from `generated_at`. No Q49 number moved.

## Honest limits (in the docstring and pinned by tests)

1. It does **not** validate the strict rule. `touch` is itself generous — a depth tape carries no
   trade field (L68/L106), so a cancel at our price is still counted as a fill. A low
   `strict_fill_rate` remains an upper bound, not a measured fill rate.
2. `saturated=False` is **not** a licence to headline the loose rule; the L48 direction holds
   unconditionally, which is why `headline_fill_rate` refuses it either way and
   `loose_rule_direction` never returns "IN".
3. A short hold **withholds** the saturation call (`long_hold=False`) rather than asserting it —
   a short window genuinely cannot accumulate book migration.
4. Deliberately **not** wired into `scripts/invariants.py --full` (L210/L213/L222/L249 posture):
   there is no standing repo-wide artifact to re-scan; the check runs inside a probe, on that
   probe's own fill population.

## Two-agent rule

**N/A for this milestone class** (lesson→test conversion; no registry flip, no bootstrap CI destined
for `kb/`, no kill decision — L104/L110/L118/L126/L127/L137/L208/L213/L236/L249/L251 precedent).
Recorded for the register: the `Task`/Agent tool was **UNAVAILABLE** in this session, so no
`verifier` subagent could have been dispatched even had one been required; the milestone was scoped
non-verdict-class partly for that reason. L250's row is therefore **not** formally disposed (per
L190 that marker records an adjudication, and an author's claim about the author's own work does not
qualify) — its enforcement cell moves from `**UNENFORCED**` to `test + protocol` under the L152
own-row-update rule, lesson TEXT unchanged.

Open `UNENFORCED` rows (the `invariants._stale_unenforced_scan()` count): **6 → 5**
(`L213, L221, L222, L251, L252`).

## Gates (fresh, taken after the commit's last content change — L162)

`python3 -m pytest -o addopts='' -q` -> **2683 passed in 2256.91s**, exit 0.
`python3 scripts/invariants.py --full` -> `invariants: all green`, exit 0.

## Artifacts

- `core/bootstrap.py` — `turnover_rule_saturation`, `headline_fill_rate`, the four constants.
- `tests/test_bootstrap.py` — 13 new tests (10 unit + 3 HARD frozen-fixture acceptance).
- `tests/test_q49_s68_bothside_maker_fillsim.py` — 3 new adoption tests.
- `tests/fixtures/q49_turnover_saturation_2026-08-02.json` — the frozen per-candidate inputs.
- `scripts/q49_s68_bothside_maker_fillsim.py` — adoption (additive).
- `.claude/agents/edge-prober.md` — the L250 house-style bullet.

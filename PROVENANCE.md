# Provenance — S0 real-ask substrate

Trust default = FALSE (CLAUDE.md). Every file here carries a source tag. This records
exactly what was lifted, from where, when, and whether it is byte-identical — so no future
reader has to trust a claim of "verbatim" without a check they can re-run.

## S0 substrate lift — 2026-06-18

**Source:** `~/Active/01-projects/kalshi.1` @ commit `fd37ae2` (2026-06-07 12:36 -0400).
**Method:** `cp` (no edits), then a `diff -q` byte-identity check (all 16 PASS, recorded below).
**Layout:** kalshi.1's package layout was mirrored verbatim so every internal import resolves
with zero edits (`core.` / `collection.` / `validation.`).

| file (here) | source (kalshi.1) | tag | byte-identical |
|---|---|---|---|
| `core/canonical.py`        | `core/canonical.py`        | lifted | ✅ |
| `core/io.py`               | `core/io.py`               | lifted | ✅ |
| `core/manifest_schema.py`  | `core/manifest_schema.py`  | lifted | ✅ |
| `core/timeutil.py`         | `core/timeutil.py`         | lifted | ✅ |
| `core/schema.py`           | `core/schema.py`           | lifted | ✅ |
| `core/__init__.py`         | `core/__init__.py`         | lifted | ✅ |
| `collection/normalize.py`  | `collection/normalize.py`  | lifted | ✅ |
| `collection/capture_orderbooks.py` | `collection/capture_orderbooks.py` | lifted | ✅ |
| `collection/__init__.py`   | `collection/__init__.py`   | lifted | ✅ |
| `validation/v1_actuals.py` | `validation/v1_actuals.py` | lifted | ✅ |
| `validation/v3_market.py`  | `validation/v3_market.py`  | lifted | ✅ |
| `validation/_http.py`      | `validation/_http.py`      | lifted | ✅ |
| `validation/__init__.py`   | `validation/__init__.py`   | lifted | ✅ |
| `config/{cities,windows,station_candidates,venues}.yaml` | same | lifted | ✅ |
| `tests/test_capture_normalize.py`  | same | lifted | ✅ |
| `tests/test_v3_ticker_parse.py`    | same | lifted | ✅ |
| `tests/test_capture_bitemporal.py` | same | lifted | ✅ |
| `tests/fixtures/kalshi_tickers_sample.json` | same | lifted | ✅ |

Re-run the check: `diff -q <here>/<file> ~/Active/01-projects/kalshi.1/<file>`.

## Authored fresh for kalshi.headless — 2026-06-18

These encode THIS project's 6 Hard Rules + trust default; they are NOT lifted (kalshi.1 has
no equivalent — its invariants are arb-bot-v2's, scoped to a different layout/schema).

| file | tag | what |
|---|---|---|
| `scripts/invariants.py`            | authored | the 6 Hard Rules as static+DB assertions (adapted in structure from `arb-bot-v2/scripts/v3_invariants.py`, retargeted) |
| `core/source_tag.py`               | authored | trust=FALSE default: untagged number => `synthetic`; `{real_ask,broker_truth,midpoint,synthetic}` |
| `core/pricing.py`                  | authored | the only sanctioned `yes_ask/bracket_sum` site (Hard Rule #3) |
| `core/stats.py`                    | authored | `safe_pstdev` with the n>=4 guard (Hard Rule #2) |
| `tests/test_invariants.py`         | authored | the engine fires on violations, exempts sanctioned sites, finds the tree green |
| `tests/test_substrate_primitives.py` | authored | pricing/source_tag/stats + the #1 binding assertion |
| `conftest.py`, `pyproject.toml`    | authored | packaging + pytest wiring |

## Verification (2026-06-18)

- `python -m pytest -q` → **43 passed**.
- `python scripts/invariants.py --full` → **all green** (exit 0).
- Binding assertion (dossier #1) asserted in `test_substrate_primitives.py`:
  `best_yes_ask == round(1 - best_no_bid, 4)`, and a derived ask is stamped `real_ask`.

## NOT yet wired

- The PreToolUse hook (`scripts/invariants.py --pre-edit-hook`) is built + tested but NOT
  yet registered in `.claude/settings.json` — wiring it makes it block edits, a harness
  change left for explicit approval.
- `capture_orderbooks.py` / `v1_actuals.py` / `v3_market.py` are runnable but their LIVE
  paths need Kalshi credentials + network; only the offline (injected-client / fixture)
  paths are exercised by the test suite.

# Q33 hourly-pass wiring gap — `polymarket_us_live` built + credentialed, never actually called

**Date:** 2026-07-22 (research loop, idle-run policy (c) — data-quality deep-dive)
**Status:** collector-wiring bug fix, no strategy claim, no registry change. Two-agent verdict
rule N/A (not a verdict-class change — same posture as Q33/Q44/Q45/Q46's build-only entries).

## Headline

`PR #153` (merged 2026-07-22T04:20:17Z) placed Ryan's verified-live Polymarket-US Ed25519
credentials on the VPS and built `collection/polymarket_us_live.py`, claiming the leg
"self-activates on the first VPS hourly pass after this merges." **14 hours later,
`tape/polymarket_us_pairs/` (and any `polymarket_us_live`-authored tape) still had zero
committed lines.** The claim was false as shipped: the new module was never wired into the
hourly pass.

## Root cause

`collection/hourly_pass.py::_default_polymarket_us_pass()` called:

```python
polymarket_us_pairs.run(api_key=os.environ.get(polymarket_us_pairs.CREDENTIAL_ENV_VAR))
```

`polymarket_us_pairs.py` is the 2026-07-20 credential-gated **skeleton** — absent
`POLYMARKET_US_API_KEY` it is a correct no-op (`blocked_key`, zero network). But when the
credential IS present, `run()` falls back to its own `_default_discover` /
`_default_fetch_us_book`, which are documented `NotImplementedError` VPS-bring-up stubs —
deliberately left unbuilt in the original skeleton because the real Ed25519/KYC'd client was
judged to be Ryan-supervised work, not autonomously wireable.

PR #153 built that real client — but as a **separate** module, `collection/polymarket_us_live.py`,
whose `make_discover_fn()` / `make_fetch_us_book_fn()` factories are meant to be **injected**
into the skeleton's `discover_fn`/`fetch_us_book_fn` parameters. `polymarket_us_live.py` even
ships its own fully-wired `run()` (delegates the credential gate + tape write to
`polymarket_us_pairs.run`, injecting the live callables) — a ready-to-use drop-in entry point.
Nothing in PR #153 pointed `hourly_pass.py` at it. Net effect: a credentialed VPS pass would
call `polymarket_us_pairs.run(api_key=...)`, hit the stub's `NotImplementedError` inside the
skeleton's own error handling, and silently record a `discovery_error` every single hour —
never touching the real, tested, credentialed implementation sitting one file over.

## Fix

```python
def _default_polymarket_us_pass() -> Dict[str, Any]:
    return polymarket_us_live.run()
```

`polymarket_us_live.run()` builds the live `discover_fn`/`fetch_us_book_fn` from `os.environ`
and calls `polymarket_us_pairs.run(env=env, discover_fn=discover_fn, fetch_us_book_fn=fetch_fn)`
— which still checks `POLYMARKET_US_API_KEY` presence **before** ever invoking either callable.
So the cloud-sandbox contract (`blocked_key`, zero network, zero file — the only state a cloud
run can ever be in) is completely unchanged; only the credentialed-VPS path now reaches real
code instead of a stub.

**Verified both paths still behave correctly:**
- Absent credential: `tests/test_hourly_pass.py::test_polymarket_us_default_is_blocked_key_when_env_absent`
  (pre-existing, unmodified) still passes — `_default_polymarket_us_pass()` now runs through
  `polymarket_us_live.run()` but still short-circuits to `blocked_key` before any network call.
- Wiring itself: new `test_polymarket_us_default_pass_delegates_to_live_module` monkeypatches
  `polymarket_us_live.run` and asserts `_default_polymarket_us_pass()` returns exactly that
  result — pins the correct module without re-deriving `polymarket_us_live`'s own (already
  fully-tested, 32-test) internal discover/fetch logic.

## Environment note (separate from the fix, but hit while verifying it)

This sandbox's system `cryptography` package (41.0.7, apt/dist-packages) is missing its
`_cffi_backend` C extension — importing `cryptography.hazmat.primitives.asymmetric.ed25519`
panics with a pyo3 ABI error. This is the exact issue #157 already flagged ("pytest cannot even
collect `tests/test_polymarket_us_live.py` / `tests/test_ws_depth.py`"), and now also breaks
collecting `tests/test_hourly_pass.py` once it transitively imports `polymarket_us_live`. Ran
`pip install --upgrade cryptography cffi websocket-client` (user-level, `~/.local`) to get a
working `cryptography` for this run's own gate verification — this does not touch the repo.
The durable fix (declaring `cryptography`/`websocket-client` as real project dependencies
instead of relying on a system package) is issue #157's own fix-spec item 2, still unapplied.

## Gates (this diff only, in isolation)

- `pytest`: 1435 passed + the same 5 pre-existing `test_invariants.py` failures as base `main`
  (stash-compared: `git stash` → identical failure list on `origin/main` → `git stash pop`).
- `python scripts/invariants.py --full`: exit 2, byte-identical 2 violations to base (this diff
  touches neither `tests/test_polymarket_us_live.py` nor `tests/test_ws_depth.py`, the two files
  issue #157 flags).

## Not merged this run

`main`'s own `invariants --full` gate is red for the pre-existing, unrelated reason tracked in
issue #157 (open since 2026-07-22T06:47Z, ~14h at time of this run). Per LOOP-QUEUE.md step 6, a
red gate blocks merging even when the redness is pre-existing and unrelated. This is now the
5th PR stacked behind #157 (after #158, #159, #160, #161), all still open.

## Reproduce

```
python -m pytest tests/test_hourly_pass.py -k delegates_to_live -v
python scripts/invariants.py --full   # exit 2, same 2 violations as main — unrelated to this diff
git log --oneline -- collection/polymarket_us_live.py collection/hourly_pass.py | head
find tape -iname '*polymarket_us*'    # empty on main, 14h+ after PR #153 merged
```

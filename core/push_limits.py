"""Git-host per-FILE byte limits — the single sanctioned site for the push-wedge thresholds.

WHY THIS MODULE EXISTS
----------------------
GitHub rejects a push, at the pre-receive hook, if ANY blob in ANY commit being pushed
exceeds **100,000,000 bytes** (100 MB decimal, not MiB). This project commits its tape, and
its tape day-files are append-only, so a day-file grows monotonically toward that ceiling and
never shrinks. Three consequences make this a *wedge*, not a nuisance:

1. The rejection is per-PUSH, not per-file: one oversized blob blocks every other change in
   the same push, including bookkeeping and findings that have nothing to do with tape.
2. Once the oversized blob is IN a commit, the rejection is permanent for that branch — the
   only escapes are dropping the content before committing or rewriting history, and a
   history rewrite is precisely the max-priority incident LOOP-QUEUE step 0a exists to catch.
3. The hourly collector falls back to a `tape/hourly-*` branch when its push fails, and step
   0b's sweep recovers those by UNION-APPENDING the missing lines into `main`'s day-files —
   which would recreate the same oversized file. A wedged day-file therefore strands tape in
   a way the standing recovery procedure cannot repair.

This actually bit the project once already: the 2026-08-09 Q52 phase-2 trade-print backfill
measured `tape/kalshi_trades/dt=2026-07-07.jsonl` at 109,151,185 bytes, had its push rejected
outright, and had to drop one whole game (35,144 lines) by hand before it could commit.

THE THRESHOLDS
--------------
`GITHUB_MAX_FILE_BYTES` is the host's documented hard block. `PUSH_SIZE_GATE_BYTES` is this
repo's own gate, set 5,000,000 bytes below it so a run that trips the gate still has room to
land the repair commit itself. `PUSH_SIZE_WARN_BYTES` is GitHub's own documented *warning*
threshold (it warns at 50 MB, blocks at 100 MB) and is used for the non-gating advisory band.

Hand-rolling any of these numbers elsewhere is the same class of mistake as hand-rolling a fee
rate (Hard Rule / `core.pricing`): import them from here.

THE SANCTIONED REPAIR is append-only-safe and needs no history rewrite: STOP APPENDING to the
offending file and shard the family's next writes into a new path (e.g. a `-part2` day-file).
Never truncate, rewrite, or reorder committed tape lines to get under the limit.
"""
from __future__ import annotations

# GitHub's hard per-file push block (bytes, decimal MB). Documented, not measured here.
GITHUB_MAX_FILE_BYTES: int = 100_000_000

# This repo's gate. Deliberately BELOW the host limit so the repair commit itself can land.
PUSH_SIZE_GATE_BYTES: int = 95_000_000

# GitHub's documented per-file WARNING threshold. Advisory band only, never gating.
PUSH_SIZE_WARN_BYTES: int = 50_000_000


# NOTE on the parameter name: these take `nbytes`, deliberately not `size`. A FILE size and an
# order-book ladder SIZE are different things, and `int(size)` is exactly the shape L47's
# ladder-size advisory in scripts/invariants.py scans for — naming the argument `size` here
# produced three false-positive advisory hits on a module that touches no order book at all.
def headroom_bytes(nbytes: int, ceiling: int = GITHUB_MAX_FILE_BYTES) -> int:
    """Bytes a file may still grow before it hits `ceiling`. Negative once it is over."""
    return int(ceiling) - int(nbytes)


def is_gating(nbytes: int) -> bool:
    """True when a file's byte count has reached this repo's own gate threshold."""
    return int(nbytes) >= PUSH_SIZE_GATE_BYTES


def is_warning(nbytes: int) -> bool:
    """True when a file has crossed GitHub's documented warn threshold (advisory band)."""
    return int(nbytes) >= PUSH_SIZE_WARN_BYTES

"""Binary-settlement classification — the one place a settled Kalshi market's `result`
field is turned into a yes/no label (L52's "settled does not imply binary" lesson).

L52 (2026-07-14): Q26's live pull of `fetch_kalshi_settled` over **458 settled markets in
7 sports series returned 8 with `result: "scalar"`**, not `result in {"yes","no"}`. A
binary-outcome probe that joins on "is it settled?" instead of "what does the result field
actually say?" silently injects those non-binary rows into a yes/no hit-rate or P&L number.
The failure mode is quiet by construction: `result == "yes"` is False for a scalar row, so a
naive `1 if r["result"] == "yes" else 0` scores it as a **loss** rather than excluding it.
`binary_outcome()` below returns `None` for exactly that case — never a fabricated 0.

Classification is an ALLOW-LIST, deliberately
--------------------------------------------
`is_binary_result` tests membership in `VALID_BINARY_RESULTS`, never absence from
`KNOWN_NON_BINARY_RESULTS`. A deny-list would let a result value Kalshi introduces
tomorrow pass as binary — which is L52's bug with a new string in it. `KNOWN_NON_BINARY_RESULTS`
is DOCUMENTATION ONLY and is not consulted by any classifier here.

That set contains `"scalar"` and nothing else. `"void"` is a plausible-sounding value and is
NOT included: no Kalshi payload, tape row, or KB page in this repo has ever carried it
(`grep -rn '"void"' kb/ collection/ scripts/ tape/` -> no hits, 2026-07-25), and inventing an
exchange constant we have not observed would be a fabricated fact. The allow-list makes the
omission harmless: an unobserved `"void"` is non-binary anyway, it is simply reported under
its raw value in `BinaryFilterReport.dropped_by_result` rather than pre-labelled.

Case normalization
------------------
Kalshi's wire format for `result` is lowercase (`"yes"`, `"no"`, `"scalar"`); every one of
the 10,605 committed tape rows measured below is lowercase. `normalize_result` still strips
and lowercases, because doing so cannot drop anything real — there is no Kalshi result value
whose meaning depends on case or surrounding whitespace — and it makes a hand-built fixture
or a re-cased legacy cache blob classify the same way as the wire. Non-`str` input (`None`,
`0`, `1`, a dict) returns `None`: a missing label is honestly missing, and an integer 1 is
NOT a yes (that coercion is how a "settled implies binary" assumption sneaks back in).

Who is already safe, and who is not
-----------------------------------
`collection/settlement_ledger.py` ALREADY applies this filter at collection time — verified
this run: `run()` drops `result == "scalar"` at line ~250 (counting it as `n_scalar_dropped`)
and anything else non-binary at line ~256, and the legacy-cache `migrate_caches()` path
repeats it at line ~381/385. So the committed `tape/settlement_ledger/` is PRE-FILTERED and a
downstream reader of that tape is safe today. Two readers are NOT:

  * anything reading the LIVE `/markets` settled API (or a legacy `qNN_settlement_cache` blob)
    directly — the raw payload is where the 8-in-458 scalars live;
  * any future settled-market tape family that does not repeat the collector's filter.

This module exists so those callers reach for a shared, tested classifier instead of
re-deriving a per-probe `== "scalar"` check (the same duplication L100 collapsed out of the
`_to_float` helpers). It deliberately does not modify the existing collector: its inline
filter stays where it is, and this module agrees with it exactly.

Measured tape composition (L162 — a count ships the command that produced it)
----------------------------------------------------------------------------
Measured 2026-07-25, from the repo root::

    python - <<'EOF'
    import json, glob, collections
    c = collections.Counter(); n = 0
    files = sorted(glob.glob('tape/settlement_ledger/*.jsonl'))
    for f in files:
        for line in open(f):
            line = line.strip()
            if not line:
                continue
            n += 1; c[json.loads(line).get('result')] += 1
    print(len(files), n, dict(c))
    EOF

Output: ``2 10605 {'no': 8235, 'yes': 2370}`` — 2 files (`dt=2026-07-17.jsonl`,
`dt=2026-07-22.jsonl`), 10,605 rows, ZERO non-binary results. That zero is the collector's
pre-filter working, not evidence that scalars do not exist; the 8-in-458 upstream rate is the
real one. `tests/test_settlement_binary_filter.py::test_acceptance_1_...` pins it against the
real tape so the day the collector stops filtering, a test goes red.

Pure functions: no I/O, no network, no clock.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

# The only two result values that carry a yes/no outcome.
BINARY_RESULTS: Tuple[str, ...] = ("yes", "no")
VALID_BINARY_RESULTS = frozenset(BINARY_RESULTS)

# DOCUMENTATION ONLY — never consulted by a classifier (see module docstring). Observed in
# the wild: `"scalar"` (L52, 8 of 458 sports settled markets, 2026-07-14; and 25 more found
# in the 4 legacy caches migrated by `collection/settlement_ledger.py`, L92).
KNOWN_NON_BINARY_RESULTS = frozenset({"scalar"})

# Stable label for a row whose result key is absent or None, used in `dropped_by_result`.
MISSING_SENTINEL = "<missing>"


def normalize_result(result: Any) -> Optional[str]:
    """Strip + lowercase a `str` result. Non-`str` or blank -> None (honestly absent).

    An int `1` is NOT a yes and a bool `True` is NOT a yes: both return None. See the
    module docstring for why case-folding is safe here.
    """
    if not isinstance(result, str):
        return None
    s = result.strip().lower()
    return s or None


def is_binary_result(result: Any) -> bool:
    """True only for a value that normalizes into `VALID_BINARY_RESULTS` (allow-list)."""
    return normalize_result(result) in VALID_BINARY_RESULTS


def binary_outcome(result: Any) -> Optional[int]:
    """1 for yes, 0 for no, **None for anything else** — never raises.

    The None is the whole point (L52): a `"scalar"`, blank, or unknown result must not be
    scored as a loss. A caller that wants a 0/1 must decide explicitly what to do with the
    None; it cannot get one by accident.
    """
    norm = normalize_result(result)
    if norm == "yes":
        return 1
    if norm == "no":
        return 0
    return None


def require_binary_result(result: Any, *, context: str = "") -> str:
    """Assert `result` is a binary settlement label; raise ValueError otherwise.

    Use at a site that cannot meaningfully continue without a yes/no (a per-row P&L
    attribution, a label join). Mirrors `core.source_tag.require_fillable`: the message
    names the RAW offending value and the caller's context, so a failure identifies the row.
    """
    norm = normalize_result(result)
    if norm not in VALID_BINARY_RESULTS:
        where = f" [{context}]" if context else ""
        raise ValueError(
            f"non-binary settlement result {result!r}{where}: a yes/no outcome requires "
            f"result in {list(BINARY_RESULTS)}; a settled market may also report "
            f"{sorted(KNOWN_NON_BINARY_RESULTS)} or no label at all (L52)."
        )
    return norm


def _drop_label(result: Any) -> str:
    """Stable `dropped_by_result` key for a non-binary value, raw as seen.

    A `str` is reported verbatim (NOT normalized) so the report shows what the source
    actually sent; None/absent -> MISSING_SENTINEL; anything else -> `<non-str:TYPE>`.
    """
    if result is None:
        return MISSING_SENTINEL
    if isinstance(result, str):
        return result
    return f"<non-str:{type(result).__name__}>"


@dataclass(frozen=True)
class BinaryFilterReport:
    """Honest expected-vs-kept accounting for one filter pass.

    `total == kept + dropped` always. `dropped_by_result` counts dropped rows by their RAW
    result value so a caller can report WHAT it dropped, not just how many — a filter that
    silently removes 40% of a join is as much a bug as one that removes nothing.
    """

    total: int
    kept: int
    dropped: int
    dropped_by_result: Mapping[str, int] = field(default_factory=dict)

    @property
    def kept_fraction(self) -> float:
        """kept/total; 0.0 on empty input (no rows kept), never a ZeroDivisionError."""
        if self.total <= 0:
            return 0.0
        return self.kept / self.total

    def summary(self) -> str:
        """One-line, log-friendly rendering for a collector/probe completeness line."""
        by = ", ".join(f"{k}={v}" for k, v in sorted(self.dropped_by_result.items()))
        return (f"binary-filter: total {self.total}, kept {self.kept} "
                f"({self.kept_fraction:.4f}), dropped {self.dropped}"
                + (f" [{by}]" if by else ""))


def _report(total: int, kept: int, dropped_by: Dict[str, int]) -> BinaryFilterReport:
    return BinaryFilterReport(total=total, kept=kept, dropped=total - kept,
                              dropped_by_result=dict(dropped_by))


def filter_binary_settlements(rows: Iterable[Mapping],
                              *, result_key: str = "result",
                              ) -> Tuple[List[Mapping], BinaryFilterReport]:
    """Keep only rows whose `result_key` is a binary label; report what was dropped.

    Row-shaped case: `tape/settlement_ledger/dt=*.jsonl` lines, or raw `fetch_kalshi_settled`
    market objects. Rows are returned UNMODIFIED (the caller keeps its own fields); use
    `binary_outcome(row[result_key])` for the 0/1. A row missing the key entirely is dropped
    and counted under `MISSING_SENTINEL` — absent is not binary.
    """
    kept: List[Mapping] = []
    dropped_by: Dict[str, int] = {}
    total = 0
    for row in rows:
        total += 1
        raw = row.get(result_key) if hasattr(row, "get") else None
        if is_binary_result(raw):
            kept.append(row)
        else:
            label = _drop_label(raw)
            dropped_by[label] = dropped_by.get(label, 0) + 1
    return kept, _report(total, len(kept), dropped_by)


def filter_binary_results_map(results: Mapping[str, Any],
                              ) -> Tuple[Dict[str, str], BinaryFilterReport]:
    """Same filter for the MECE-ladder shape `{ticker: "yes"|"no"}`.

    That is the shape `previous_settlement["results"]` carries, read UNGUARDED today by
    `scripts/s14_ladder_fillsim.py`, `scripts/s19_wing_fade_fillsim.py`, and
    `scripts/seed5_funding_prior_probe.py` (those are frozen, already-verdicted probes and
    are deliberately NOT edited here — this is the helper a NEW caller should use instead).

    Kept values are the NORMALIZED result, so a downstream `== "yes"` comparison is safe.
    """
    kept: Dict[str, str] = {}
    dropped_by: Dict[str, int] = {}
    total = 0
    for ticker, raw in results.items():
        total += 1
        norm = normalize_result(raw)
        if norm in VALID_BINARY_RESULTS:
            kept[ticker] = norm  # type: ignore[assignment]
        else:
            label = _drop_label(raw)
            dropped_by[label] = dropped_by.get(label, 0) + 1
    return kept, _report(total, len(kept), dropped_by)

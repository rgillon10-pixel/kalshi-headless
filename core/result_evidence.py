"""Field-level outcome-evidence detector — the RECALL complement to
`core.settlement_sources.undeclared_settlement_dirs()`.

Why this module exists (L300's published recall limit, closed 2026-08-15)
-------------------------------------------------------------------------
`core/settlement_sources.py` says of itself, in its own docstring:

    `undeclared_settlement_dirs()` can only detect a NEW settlement family whose directory
    NAME carries the word "settlement" ... It structurally CANNOT detect a tenth family that
    hides settlement inside another family's record schema.

Three of the ten declared sources are exactly that shape (`crypto_hourly`, `weather_actuals`,
`econ_prints`), so the blind spot is not hypothetical — it is the majority shape of how new
sources have arrived. A 0-issue `undeclared_settlement_dirs()` report is PRECISION evidence,
never RECALL.

This module supplies the missing half: it looks at RECORD FIELDS, not directory names. It is
deliberately dumb and deliberately narrow, because a detector that guesses is worse than one
that misses — a false "we already have the labels" would route a run away from the collector
change it actually needs.

The rule, stated so it can be falsified
---------------------------------------
Walking a decoded JSON record (bounded depth), a dict node yields OUTCOME EVIDENCE when:

  D1 `explicit_result`  -- it has a `result` key whose value is a NON-EMPTY string.
                           Kalshi writes `""` on an unsettled market, so emptiness is the
                           exchange's own "not settled yet" and is counted separately as
                           `schema_only` rather than as evidence.
  D2 `terminal_status`  -- it has a `status` key whose value is in `TERMINAL_STATUSES`.
                           `closed` is NOT terminal: a closed market has stopped trading and
                           has no result yet. It is counted under `closed_not_settled` so the
                           distinction is visible instead of assumed.

Both detectors report an ATTRIBUTED ticker only when the record itself supplies one — the
node's own `ticker`/`market_ticker` field, or the map key the node hangs off when that key is
ticker-shaped (`_looks_like_ticker`). Evidence with no ticker in reach is returned as
`unattributed`, never dropped and never guessed: an unattributable label cannot be joined to
a book, so counting it as coverage would overstate what a fill-sim could score.

Binary classification is delegated to `core.settlement.is_binary_result` (L52's allow-list),
never re-derived here, so a `scalar` result can never be scored as an outcome.

HONEST RECALL LIMIT of THIS module, published here for the same reason L300 published its own
--------------------------------------------------------------------------------------------
Detection is KEY-NAME based on exactly two names (`result`, `status`). A family that encodes
its outcome under any other name -- `winner`, `settled_to`, `final_value`, a numeric
`expiration_value` with no `result` beside it -- is INVISIBLE to this module. So a zero from
`scan_record` means "no `result`/`status`-shaped outcome evidence", NOT "this family has no
outcomes". Recall is bounded and always will be; what this module removes is the specific
blind spot where a family carries the exchange's own settled-market schema and nobody noticed.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from core.settlement import is_binary_result, normalize_result

#: A market whose `status` is one of these has a settled outcome on the exchange's own terms.
#: `closed` is deliberately absent -- see the module docstring.
TERMINAL_STATUSES: frozenset = frozenset({"settled", "finalized", "determined"})

#: `status` values that mean "trading stopped" but NOT "outcome known".
CLOSED_NOT_SETTLED_STATUSES: frozenset = frozenset({"closed"})

#: Keys a node may use to name its own market.
TICKER_KEYS: Tuple[str, ...] = ("ticker", "market_ticker")

_MAX_DEPTH = 8


def _looks_like_ticker(key: Any) -> bool:
    """A map key that is plausibly a Kalshi market ticker.

    Narrow on purpose: upper-case, hyphenated, no whitespace, long enough that a field name
    like `RESULT` or a two-letter code cannot pass. This is the ONLY inference in the module
    and it is used only to attribute evidence that a ticker-keyed map already implies.
    """
    if not isinstance(key, str) or len(key) < 8:
        return False
    if any(ch.isspace() for ch in key):
        return False
    if "-" not in key:
        return False
    return key == key.upper() and any(ch.isalpha() for ch in key)


def _node_ticker(node: Mapping[str, Any], parent_key: Optional[str]) -> Optional[str]:
    for k in TICKER_KEYS:
        v = node.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    if _looks_like_ticker(parent_key):
        return str(parent_key)
    return None


def scan_record(record: Any) -> Dict[str, Any]:
    """Outcome evidence in ONE decoded record. Pure, offline, allocation-bounded by depth.

    Returns a dict with:
      `labels`               -- [{ticker, result, binary, detector}] for attributed D1 evidence
      `unattributed_results` -- [result] for D1 evidence with no ticker in reach
      `terminal_status`      -- [{ticker|None, status}] for D2 evidence
      `closed_not_settled`   -- count of `closed`-status nodes (trading stopped, no outcome)
      `schema_only_result`   -- count of nodes carrying a `result` key that is EMPTY
    """
    labels: List[Dict[str, Any]] = []
    unattributed: List[str] = []
    terminal: List[Dict[str, Any]] = []
    closed = 0
    schema_only = 0

    def walk(obj: Any, parent_key: Optional[str], depth: int) -> None:
        nonlocal closed, schema_only
        if depth > _MAX_DEPTH:
            return
        if isinstance(obj, Mapping):
            if "result" in obj:
                raw = obj.get("result")
                if isinstance(raw, str) and raw.strip():
                    tk = _node_ticker(obj, parent_key)
                    norm = normalize_result(raw)
                    if tk is None:
                        unattributed.append(norm)
                    else:
                        labels.append({
                            "ticker": tk,
                            "result": norm,
                            "binary": bool(is_binary_result(raw)),
                            "detector": "explicit_result",
                        })
                else:
                    schema_only += 1
            status = obj.get("status")
            if isinstance(status, str):
                s = status.strip().lower()
                if s in TERMINAL_STATUSES:
                    terminal.append({"ticker": _node_ticker(obj, parent_key), "status": s})
                elif s in CLOSED_NOT_SETTLED_STATUSES:
                    closed += 1
            for k, v in obj.items():
                if isinstance(v, (Mapping, list)):
                    walk(v, k if isinstance(k, str) else None, depth + 1)
        elif isinstance(obj, list):
            for v in obj:
                if isinstance(v, (Mapping, list)):
                    walk(v, parent_key, depth + 1)

    walk(record, None, 0)
    return {
        "labels": labels,
        "unattributed_results": unattributed,
        "terminal_status": terminal,
        "closed_not_settled": closed,
        "schema_only_result": schema_only,
    }


#: Byte-level pre-filter. A line that contains NONE of these tokens cannot produce evidence
#: under `scan_record`, so it need not be decoded. This is a SPEED device with a correctness
#: obligation: `tests/test_result_evidence.py::test_prefilter_never_skips_a_line_scan_would_flag`
#: pins that every token `scan_record` can fire on appears here.
PREFILTER_TOKENS: Tuple[bytes, ...] = (
    b'"result"',
    b'"status"',
)


def line_may_carry_evidence(raw: bytes) -> bool:
    """True if a raw JSONL line could produce evidence. Conservative: false ONLY when no
    evidence-bearing key name occurs anywhere in the bytes."""
    return any(tok in raw for tok in PREFILTER_TOKENS)

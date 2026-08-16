"""Pure primitives for the MUTABILITY of a Kalshi market's `close_time`.

Why this module exists
----------------------
Several probes read `close_time` out of a committed settlement-cache blob and treat it as a
fixed property of the market. `scripts/q51_m3_fill_projection.py` states the premise out loud
-- it reads `close_time` from a deliberately FROZEN pre-settlement cache and documents the
choice as safe because `close_time` is *"a SCHEDULE field, never an outcome"*
(`:118-119`, and the report field `what_is_read_from_the_cache`).

That premise is falsifiable from tape this repo already holds, because the Q51 family
committed TWO pulls of the SAME 60-ticker population six days apart -- one before those
markets settled, one after. This module supplies the vocabulary to state the answer as a
measurement rather than an opinion.

The three regimes, stated so each can be falsified separately
-------------------------------------------------------------
A `close_time` observation is classified by the SETTLEMENT state of the row that carried it,
never by the timestamp itself:

  R1 `open_to_open`        -- both observations of a ticker are of an UNSETTLED row.
  R2 `open_to_settled`     -- the earlier observation is unsettled, the later one settled.
  R3 `settled_to_settled`  -- both observations are of a settled row.

"Settled" is delegated to `core.result_evidence` (a non-empty `result`, or a `status` in
`TERMINAL_STATUSES`); `closed` is NOT settled, exactly as that module defines it. Delegating
matters: a second, disagreeing definition of "settled" living here is precisely how two
modules drift apart (L358's cross-module exemption-table lesson).

This module DOES NOT read tape, DOES NOT know which families exist, and DOES NOT decide
whether a mutation is a defect. It converts paired observations into classified deltas. The
census that walks committed tape is `scripts/close_time_mutation_audit.py`; the judgement
lives in the finding.

Deliberate non-features
-----------------------
* No network, no writes, no clock. `classify_pair` is a pure function of its two inputs, so a
  report built from it is reproducible from the same tape forever.
* An unparseable or absent `close_time` is NEVER coerced to a default instant. It yields
  `delta_hours=None` and lands in `undated`, because a fabricated zero delta would read as
  "stable" -- the exact direction of error that would hide the finding this module exists to
  measure.
* Equality is compared on the RAW string as well as the parsed instant. Two spellings of the
  same instant (`...T09:00:00Z` vs `...T09:00:00+00:00`) are `text_changed` but not
  `instant_changed`, and conflating them would manufacture mutations out of formatting.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from core.result_evidence import TERMINAL_STATUSES
from core.timeutil import parse_iso_utc

#: Regime labels. Exported so a consumer cannot mistype one silently.
OPEN_TO_OPEN = "open_to_open"
OPEN_TO_SETTLED = "open_to_settled"
SETTLED_TO_SETTLED = "settled_to_settled"
SETTLED_TO_OPEN = "settled_to_open"   # backwards: never expected; reported, never dropped.

REGIMES: Tuple[str, ...] = (OPEN_TO_OPEN, OPEN_TO_SETTLED, SETTLED_TO_SETTLED, SETTLED_TO_OPEN)


def is_settled_row(row: Any) -> bool:
    """True when a market row carries the exchange's own evidence that it has settled.

    Mirrors `core.result_evidence`'s rule exactly: a NON-EMPTY `result` string, or a `status`
    in `TERMINAL_STATUSES`. `status == "closed"` is NOT settled -- trading stopped is not an
    outcome known. A non-Mapping row is not settled (it carries no evidence at all).
    """
    if not isinstance(row, Mapping):
        return False
    result = row.get("result")
    if isinstance(result, str) and result.strip():
        return True
    status = row.get("status")
    if isinstance(status, str) and status.strip().lower() in TERMINAL_STATUSES:
        return True
    return False


def parse_close_time(value: Any) -> Optional[datetime]:
    """Parse an ISO-8601 close_time to an aware UTC datetime, else None.

    Returns None -- never a sentinel instant -- for anything unparseable. L357: a helper that
    invents a value for an undefined quantity hands a downstream comparison a fabricated
    answer, and `>=` cannot tell the difference.
    """
    if not isinstance(value, str) or not value.strip():
        return None
    # L136/L150: `core.timeutil.parse_iso_utc`, never the stdlib call directly. Kalshi writes
    # bare-`Z` and short-fraction timestamps that Python 3.9 (this repo's declared floor)
    # rejects and 3.11 accepts, so a hand-rolled parse here would pass CI and fail in prod.
    try:
        dt = parse_iso_utc(value.strip())
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def close_date(value: Any) -> Optional[str]:
    """The UTC calendar date of a close_time (`YYYY-MM-DD`), else None.

    This is the DERIVED value probes actually bucket on (`q51_m3_fill_projection`'s
    `_close_date_map`), so the audit measures mutation at this granularity too -- an instant
    that moves inside one UTC day costs a day-bucketed probe nothing, and one that crosses a
    day boundary silently re-files the row.
    """
    dt = parse_close_time(value)
    return dt.date().isoformat() if dt is not None else None


@dataclass(frozen=True)
class PairedObservation:
    """Two observations of ONE ticker's close_time, ordered earlier -> later by pull time."""

    ticker: str
    earlier_source: str
    later_source: str
    earlier_close_text: Optional[str]
    later_close_text: Optional[str]
    earlier_settled: bool
    later_settled: bool
    regime: str
    text_changed: bool
    instant_changed: bool
    date_changed: bool
    delta_hours: Optional[float]

    @property
    def undated(self) -> bool:
        """True when at least one side had no parseable close_time (delta undefined)."""
        return self.delta_hours is None


def classify_pair(ticker: str, earlier: Mapping[str, Any], later: Mapping[str, Any],
                  earlier_source: str = "earlier", later_source: str = "later"
                  ) -> PairedObservation:
    """Classify one ticker's earlier/later market rows. Pure; no I/O, no clock.

    `earlier`/`later` are market rows in Kalshi's own shape (`close_time`, `result`,
    `status`). Caller guarantees the pull ORDER; this function never infers it from the
    close_time itself, because the whole question is whether close_time is trustworthy.
    """
    e_settled = is_settled_row(earlier)
    l_settled = is_settled_row(later)
    if e_settled and l_settled:
        regime = SETTLED_TO_SETTLED
    elif e_settled and not l_settled:
        regime = SETTLED_TO_OPEN
    elif l_settled:
        regime = OPEN_TO_SETTLED
    else:
        regime = OPEN_TO_OPEN

    e_text = earlier.get("close_time") if isinstance(earlier, Mapping) else None
    l_text = later.get("close_time") if isinstance(later, Mapping) else None
    e_text = e_text if isinstance(e_text, str) else None
    l_text = l_text if isinstance(l_text, str) else None

    e_dt, l_dt = parse_close_time(e_text), parse_close_time(l_text)
    if e_dt is None or l_dt is None:
        delta = None
        instant_changed = False
        date_changed = False
    else:
        delta = (l_dt - e_dt).total_seconds() / 3600.0
        instant_changed = e_dt != l_dt
        date_changed = e_dt.date() != l_dt.date()

    return PairedObservation(
        ticker=ticker,
        earlier_source=earlier_source,
        later_source=later_source,
        earlier_close_text=e_text,
        later_close_text=l_text,
        earlier_settled=e_settled,
        later_settled=l_settled,
        regime=regime,
        text_changed=(e_text != l_text),
        instant_changed=instant_changed,
        date_changed=date_changed,
        delta_hours=delta,
    )


def result_conflict(earlier: Mapping[str, Any], later: Mapping[str, Any]) -> bool:
    """True when BOTH rows are settled and their normalized `result` strings disagree.

    This is the label-corruption predicate: an unsettled row's empty `result` is NOT a
    conflict with a later settled one (that is ordinary settlement lag, L262), and treating it
    as one would bury the real signal under expected noise.
    """
    if not (is_settled_row(earlier) and is_settled_row(later)):
        return False
    a = earlier.get("result")
    b = later.get("result")
    a = a.strip().lower() if isinstance(a, str) else ""
    b = b.strip().lower() if isinstance(b, str) else ""
    if not a or not b:
        return False
    return a != b


def summarize(pairs: Iterable[PairedObservation]) -> Dict[str, Any]:
    """Aggregate classified pairs into a plain, JSON-safe dict. Deterministic ordering."""
    pairs = list(pairs)
    by_regime: Dict[str, Dict[str, Any]] = {
        r: {"n": 0, "instant_changed": 0, "date_changed": 0, "text_only_changed": 0,
            "undated": 0, "moved_earlier": 0, "moved_later": 0}
        for r in REGIMES
    }
    deltas_by_regime: Dict[str, List[float]] = {r: [] for r in REGIMES}
    for p in pairs:
        b = by_regime[p.regime]
        b["n"] += 1
        if p.undated:
            b["undated"] += 1
            continue
        if p.instant_changed:
            b["instant_changed"] += 1
            deltas_by_regime[p.regime].append(p.delta_hours)
            if p.delta_hours < 0:
                b["moved_earlier"] += 1
            elif p.delta_hours > 0:
                b["moved_later"] += 1
        elif p.text_changed:
            b["text_only_changed"] += 1
        if p.date_changed:
            b["date_changed"] += 1
    for r in REGIMES:
        ds = sorted(deltas_by_regime[r])
        if ds:
            n = len(ds)
            by_regime[r]["delta_hours_min"] = ds[0]
            by_regime[r]["delta_hours_max"] = ds[-1]
            by_regime[r]["delta_hours_median"] = (
                ds[n // 2] if n % 2 else (ds[n // 2 - 1] + ds[n // 2]) / 2.0)
            by_regime[r]["delta_hours_mean"] = sum(ds) / n
        else:
            for k in ("delta_hours_min", "delta_hours_max", "delta_hours_median",
                      "delta_hours_mean"):
                by_regime[r][k] = None
    return {"n_pairs": len(pairs), "by_regime": by_regime}

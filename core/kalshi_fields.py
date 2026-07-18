"""Shared parsing for Kalshi's `_dollars` / `_fp` suffixed numeric string fields.

Kalshi's `/markets` (open and settled) objects carry prices and sizes as
wire-format STRINGS under suffixed keys (`yes_ask_dollars`, `volume_fp`,
`settlement_value_dollars`, ...) — the bare `yes_ask`/`volume`/`settlement_value`
keys are absent or unreliable. A collector that reads the bare key silently gets
`None` for every row instead of erroring: a completeness-invalidating bug that
looks like clean output (L90). Before this module, `collection/settlement_ledger.py`
and `collection/universe_sweep.py` each hand-rolled a byte-identical `_to_float`
(L100) — reuse this instead of re-deriving it in the next collector.
"""
from __future__ import annotations

from typing import Any, Optional


def parse_kalshi_numeric(val: Any) -> Optional[float]:
    """Parse a Kalshi `_dollars` / `_fp` string field to float.

    '', None, or an unparseable string -> None (an absent number is honestly
    None, never a fabricated 0). A value already numeric is passed through.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None

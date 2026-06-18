"""Price-source provenance — the trust=FALSE default (CLAUDE.md "Trust defaults").

Every persisted number carries a source tag. The four tags, in descending order of
trust:

  real_ask     — a real, fillable taker price (the yes-side or no-side ask off a live
                 book). The ONLY tag a live-capital decision may rely on (prime directive #1).
  broker_truth — a value reported by the broker/exchange as fact (a fill, a balance).
  midpoint     — (best_bid + best_ask) / 2. NOT fillable. A reference, never a fill.
  synthetic    — a modeled / derived / assumed number. Never a fill price. The pt1
                 trade lost 9.6% partly because a synthetic raw_prob was treated as a
                 fillable price — that mistake is forbidden here.

The default is the hard part: an UNTAGGED number is `synthetic`, never something more
trusted. Optimism is not the default; suspicion is.
"""
from __future__ import annotations

from typing import Optional

# Descending trust order (index 0 = most trusted).
SOURCE_TAGS = ("real_ask", "broker_truth", "midpoint", "synthetic")
VALID_SOURCE_TAGS = frozenset(SOURCE_TAGS)

# Tags a live-capital / fill decision is allowed to consume (prime directive #1).
FILLABLE_TAGS = frozenset({"real_ask", "broker_truth"})

DEFAULT_TAG = "synthetic"


def tag_or_synthetic(tag: Optional[str]) -> str:
    """Coerce a (possibly missing/invalid) tag to a valid one. Untagged => synthetic.

    This is the trust=FALSE default in one function: anything we cannot positively
    identify as a trusted source is treated as the least-trusted source.
    """
    return tag if tag in VALID_SOURCE_TAGS else DEFAULT_TAG


def is_fillable(tag: Optional[str]) -> bool:
    """True only for tags that name a real, fillable price. Untagged => False."""
    return tag in FILLABLE_TAGS


def require_fillable(tag: Optional[str], *, context: str = "") -> str:
    """Assert `tag` is a fillable price source; raise otherwise. Use at every site that
    quotes a P&L number or moves (paper or real) capital — a synthetic/midpoint price
    must never reach a fill decision (prime directive #1; Hard Rule #4)."""
    if not is_fillable(tag):
        where = f" [{context}]" if context else ""
        raise ValueError(
            f"non-fillable price source {tag_or_synthetic(tag)!r}{where}: a fill / P&L "
            f"decision requires a {sorted(FILLABLE_TAGS)} tag, never synthetic/midpoint."
        )
    return tag  # type: ignore[return-value]

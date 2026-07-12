"""execution.limits — THE single sanctioned site for paper/live risk caps.

Every risk cap the execution lane enforces lives here and ONLY here. This is the
same discipline `core.pricing` applies to fee rates (lesson L18): one source of
truth so a cap can never be silently re-defined, loosened, or forgotten at a call
site. Any future tier (demo/live) MUST import its caps from this module.

Changing any cap in this file is a Ryan-level decision (the same class of call as
widening the source-tag enum): it directly bounds how much simulated — and later,
real — exposure a strategy can take. A loop/agent may READ these caps and enforce
them; it may not raise them on its own authority.

Caps are conservative-by-default. The paper tier enforces them exactly as a live
tier would, so a strategy that would breach a cap on real capital breaches it in
simulation too — the sim is not allowed to be more permissive than production.
"""
from __future__ import annotations

from typing import List

from execution.schema import Order

# Max contracts a single order may request. Bounds per-order size so a fat-finger
# or a runaway strategy loop cannot place an unbounded order.
MAX_CONTRACTS_PER_ORDER = 100

# Max total open notional (dollars) across ALL positions, valued at entry cost.
# Bounds aggregate exposure; the paper broker passes in current open notional.
MAX_OPEN_NOTIONAL_DOLLARS = 500.0

# Max orders accepted per calendar day. Bounds churn / runaway-loop order counts.
MAX_DAILY_ORDERS = 200


def check_order(order: Order, open_notional: float, orders_today: int) -> List[str]:
    """Return a list of violation strings for `order` given the current
    `open_notional` (dollars, already-open exposure) and `orders_today` (count of
    orders already accepted today). An empty list means the order is within all
    caps. The caller (paper broker) rejects any order with a non-empty result.

    The order's own marginal notional (limit_price * qty) is added to
    `open_notional` for the aggregate check — a new order that WOULD push total
    open exposure past the cap is rejected, not just one that starts over it.

    This function never mutates state and never raises on a well-formed Order;
    a malformed order (bad price/qty) is caught by Order.validate() upstream.
    """
    violations: List[str] = []

    if order.qty > MAX_CONTRACTS_PER_ORDER:
        violations.append(
            f"qty {order.qty} exceeds MAX_CONTRACTS_PER_ORDER ({MAX_CONTRACTS_PER_ORDER})")

    marginal_notional = float(order.limit_price) * int(order.qty)
    projected = float(open_notional) + marginal_notional
    if projected > MAX_OPEN_NOTIONAL_DOLLARS:
        violations.append(
            f"projected open notional ${projected:.2f} exceeds "
            f"MAX_OPEN_NOTIONAL_DOLLARS (${MAX_OPEN_NOTIONAL_DOLLARS:.2f})")

    if orders_today >= MAX_DAILY_ORDERS:
        violations.append(
            f"orders_today {orders_today} at/over MAX_DAILY_ORDERS ({MAX_DAILY_ORDERS})")

    return violations

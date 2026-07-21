"""core.pricing.book_notional_at_touch — the L119 book-notional units guardrail.

Lesson L119: a "book notional at touch" descriptor computed as `price * size / 100`
silently understates resting-book dollar depth ~100x when `price` is already in dollars
(the L90 `_dollars` convention that `parse_kalshi_numeric` returns). This pins:
  - the correct `price_dollars * size` computation (NO /100),
  - a regression that a reintroduced /100 mistake is caught, and
  - the non-gating units sanity WARNING (fires on implausibly-low, silent otherwise).
"""
from __future__ import annotations

import warnings

import pytest

from core.pricing import (
    LOW_TOUCH_NOTIONAL_WARN_DOLLARS,
    book_notional_at_touch,
)


def test_correct_computation_is_price_dollars_times_size():
    # price already in dollars (L90 convention: '0.98' -> 0.98), size = number of contracts.
    assert book_notional_at_touch(0.98, 500) == pytest.approx(490.0)
    assert book_notional_at_touch(0.50, 1000) == pytest.approx(500.0)
    assert book_notional_at_touch(0.10, 2000) == pytest.approx(200.0)


def test_units_bug_regression_a_reintroduced_divide_by_100_would_be_caught():
    # If a future author wrote `price_dollars * size / 100`, THIS is the value they'd get.
    # The helper must NOT return it — that is exactly the L119 ~100x understatement.
    price_dollars, size = 0.98, 500
    buggy_over_100 = price_dollars * size / 100.0          # 4.9 — the bug
    correct = book_notional_at_touch(price_dollars, size, warn_if_implausibly_low=False)
    assert correct == pytest.approx(490.0)
    assert correct != pytest.approx(buggy_over_100)
    assert correct == pytest.approx(buggy_over_100 * 100.0)  # off by exactly 100x


def test_l119_real_numbers_dollars_price_lands_in_the_hundreds_not_single_digits():
    # The Q36 audit: the buggy /100 metric read medians $2.3-$19.7/market-hour; the correct
    # `price_dollars * size` formula gave the true medians $215-$1,968. A representative
    # liquid KXTEMPNYCH touch (mid-price ~0.43, ~500 contracts resting) must print in the
    # hundreds, not single digits.
    notional = book_notional_at_touch(0.43, 500, warn_if_implausibly_low=False)
    assert notional == pytest.approx(215.0)
    assert notional > 100.0  # not the buggy $2-$19 regime


def test_sanity_warning_fires_on_implausibly_low_notional():
    # 0.98 * 5 = 4.9 — a genuinely-liquid touch never notionals this low; warn (non-gating).
    with pytest.warns(UserWarning, match="L119"):
        result = book_notional_at_touch(0.98, 5)
    assert result == pytest.approx(4.9)  # value is still returned unaltered


def test_sanity_warning_silent_for_plausible_liquid_notional():
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # any warning would raise and fail the test
        assert book_notional_at_touch(0.50, 1000) == pytest.approx(500.0)


def test_zero_notional_is_honest_and_never_warns():
    # An empty / zero-size touch is honestly $0, not a suspicious units bug.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert book_notional_at_touch(0.0, 500) == 0.0
        assert book_notional_at_touch(0.98, 0) == 0.0


def test_warn_flag_can_be_disabled_for_a_known_thin_market():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        # Below the threshold, but the caller has vouched the market is genuinely thin.
        assert book_notional_at_touch(0.98, 5, warn_if_implausibly_low=False) == pytest.approx(4.9)


def test_threshold_boundary_is_exclusive_at_the_warn_dollars_value():
    # Exactly at the threshold does NOT warn (the check is strictly-less-than).
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert book_notional_at_touch(LOW_TOUCH_NOTIONAL_WARN_DOLLARS, 1) == pytest.approx(
            LOW_TOUCH_NOTIONAL_WARN_DOLLARS)

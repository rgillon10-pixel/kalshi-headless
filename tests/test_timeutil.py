"""kb/lessons L45 escalation: a shared, importable close-time parser for Kalshi's
crypto-hourly ticker grammar (hour token is America/New_York, not UTC) so future
probes import the corrected semantics instead of re-deriving them per-script."""
from __future__ import annotations

from datetime import datetime, timezone

from core.timeutil import (is_coarse_close_time, is_genuine_post_close,
                           parse_crypto_hour_token_close_utc,
                           parse_sports_ticker_hhmm_as_utc)

UTC = timezone.utc


def test_confirmed_empirical_example_edt():
    # kb/lessons L45: KXBTC-26JUL0621 captured 00:57:50 UTC on 07-07 (=20:57 EDT on
    # 07-06), closing 21:00 EDT = 01:00 UTC 07-07 — confirmed against live tape.
    close = parse_crypto_hour_token_close_utc("26JUL0621")
    assert close == datetime(2026, 7, 7, 1, 0, tzinfo=UTC)


def test_confirmed_example_is_tz_aware_utc():
    close = parse_crypto_hour_token_close_utc("26JUL0621")
    assert close.tzinfo is not None
    assert close.utcoffset().total_seconds() == 0


def test_winter_token_uses_est_not_edt():
    # January is standard time (EST, UTC-5), not daylight (EDT, UTC-4) — the zone
    # conversion must follow the real calendar, not a hardcoded summer offset.
    close = parse_crypto_hour_token_close_utc("26JAN1512")
    assert close == datetime(2026, 1, 15, 17, 0, tzinfo=UTC)


def test_midnight_hour_token():
    close = parse_crypto_hour_token_close_utc("26JUL0700")
    assert close == datetime(2026, 7, 7, 4, 0, tzinfo=UTC)


def test_lowercase_month_accepted():
    assert parse_crypto_hour_token_close_utc("26jul0621") == parse_crypto_hour_token_close_utc("26JUL0621")


def test_full_ticker_middle_segment_not_stripped_returns_none():
    # Caller must pass the bare token (the middle segment), not the full ticker —
    # this is a grammar mismatch, not a valid token, so it must fail loudly (None),
    # never silently mis-parse a truncated prefix.
    assert parse_crypto_hour_token_close_utc("KXBTC-26JUL0621-B71750") is None


def test_bad_month_returns_none():
    assert parse_crypto_hour_token_close_utc("26XXX0621") is None


def test_hour_out_of_range_returns_none():
    assert parse_crypto_hour_token_close_utc("26JUL0624") is None


def test_wrong_length_returns_none():
    assert parse_crypto_hour_token_close_utc("26JUL062") is None
    assert parse_crypto_hour_token_close_utc("") is None


def test_non_numeric_date_fields_return_none():
    assert parse_crypto_hour_token_close_utc("XXJULXX21") is None


# --------------------------------------------------------------------------- #
# kb/lessons L64 escalation: shared sports-ticker post-close discipline (moved
# byte-identical from scripts/q29_settlement_lag_probe.py so future post-close-adjacent
# probes import it instead of re-deriving the tz-ambiguous-ticker trap per script).
# --------------------------------------------------------------------------- #
def test_parse_sports_ticker_hhmm_as_utc_basic():
    dt = parse_sports_ticker_hhmm_as_utc("KXNPBGAME-26JUL110500YOMYOK-YOK")
    assert dt == datetime(2026, 7, 11, 5, 0, tzinfo=UTC)


def test_parse_sports_ticker_hhmm_as_utc_bad_grammar_is_none():
    assert parse_sports_ticker_hhmm_as_utc("KXBTC-26JUL0621-T69300") is None
    assert parse_sports_ticker_hhmm_as_utc("") is None
    assert parse_sports_ticker_hhmm_as_utc("no-dashes-here") is None


def test_parse_sports_ticker_hhmm_as_utc_out_of_range_is_none():
    assert parse_sports_ticker_hhmm_as_utc("KXMLBGAME-26JUL112599ABCDEF-ABC") is None


def test_is_coarse_close_time_2359_clamp():
    assert is_coarse_close_time(datetime(2026, 7, 11, 23, 59, 0, tzinfo=UTC))
    assert is_coarse_close_time(datetime(2026, 7, 11, 23, 59, 59, tzinfo=UTC))


def test_is_coarse_close_time_exact_midnight_clamp():
    assert is_coarse_close_time(datetime(2026, 7, 11, 0, 0, 0, tzinfo=UTC))


def test_is_coarse_close_time_none_is_coarse():
    assert is_coarse_close_time(None)


def test_is_coarse_close_time_real_intraday_is_fine():
    assert not is_coarse_close_time(datetime(2026, 7, 11, 12, 54, 32, tzinfo=UTC))
    assert not is_coarse_close_time(datetime(2026, 7, 11, 0, 0, 30, tzinfo=UTC))


def test_is_genuine_post_close_none_on_coarse_close():
    assert is_genuine_post_close(
        datetime(2026, 7, 12, 12, 0, tzinfo=UTC),
        datetime(2026, 7, 11, 23, 59, tzinfo=UTC)) is None
    assert is_genuine_post_close(datetime(2026, 7, 12, 12, 0, tzinfo=UTC), None) is None


def test_is_genuine_post_close_true_past_conservative_margin():
    close = datetime(2026, 7, 11, 5, 0, tzinfo=UTC)
    # 20h past close clears the default 13h tz-uncertainty + 6h game-duration margin (19h)
    captured = datetime(2026, 7, 12, 1, 0, tzinfo=UTC)
    assert is_genuine_post_close(captured, close) is True


def test_is_genuine_post_close_false_within_conservative_margin():
    close = datetime(2026, 7, 11, 5, 0, tzinfo=UTC)
    # ticker-HHMM-as-UTC would call this "post_close" (5h past the naive close reading),
    # but it is well inside the conservative 19h margin — genuinely still ambiguous/pre-close
    # under the worst-case tz mis-statement (the exact L64 mislabeling trap).
    captured = datetime(2026, 7, 11, 10, 0, tzinfo=UTC)
    assert is_genuine_post_close(captured, close) is False


def test_is_genuine_post_close_custom_margins():
    close = datetime(2026, 7, 11, 5, 0, tzinfo=UTC)
    captured = datetime(2026, 7, 11, 8, 0, tzinfo=UTC)  # 3h past close
    assert is_genuine_post_close(captured, close, tz_uncertainty_hours=1.0,
                                 max_game_duration_hours=1.0) is True
    assert is_genuine_post_close(captured, close, tz_uncertainty_hours=13.0,
                                 max_game_duration_hours=6.0) is False

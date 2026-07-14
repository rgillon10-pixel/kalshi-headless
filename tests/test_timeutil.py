"""kb/lessons L45 escalation: a shared, importable close-time parser for Kalshi's
crypto-hourly ticker grammar (hour token is America/New_York, not UTC) so future
probes import the corrected semantics instead of re-deriving them per-script."""
from __future__ import annotations

from datetime import datetime, timezone

from core.timeutil import parse_crypto_hour_token_close_utc

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

"""Time handling: LST climate-day boundaries and Kalshi timestamp parsing.

The CLI climate day = local STANDARD-time midnight to midnight (no daylight shift),
year-round. METAR/ASOS archives are UTC. Mixing these is a known silent-corruption
source ('midnight-LST calendar-cutoff effects'). These helpers make the boundary
explicit and are unit-tested.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Tuple
from zoneinfo import ZoneInfo

UTC = timezone.utc
_FRAC = re.compile(r"\.(\d+)")


def _parse_iso(s: str) -> datetime:
    """Parse ISO-8601 tolerating variable fractional-second precision.

    Python 3.9's datetime.fromisoformat only accepts exactly 3 or 6 fractional
    digits and no 'Z'. Kalshi emits microseconds with trailing zeros stripped
    (e.g. '...:04.2743Z'), which would otherwise raise. We normalize the fraction
    to 6 digits and map 'Z' to +00:00.
    """
    s = s.strip().replace("Z", "+00:00")
    m = _FRAC.search(s)
    if m:
        s = s[:m.start()] + "." + (m.group(1) + "000000")[:6] + s[m.end():]
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def standard_utc_offset_hours(tz_name: str, ref_year: int = 2020) -> float:
    """STANDARD-time UTC offset (hours) for a tz, ignoring DST.

    Uses a mid-January reference (standard time in the Northern Hemisphere, where
    all current Kalshi settlement stations sit). A Southern-Hemisphere station
    would need a July reference — flagged, not silently assumed.
    """
    tz = ZoneInfo(tz_name)
    jan = datetime(ref_year, 1, 15, 12, 0, tzinfo=tz)
    off = jan.utcoffset()
    assert off is not None, f"no utc offset for {tz_name}"
    return off.total_seconds() / 3600.0


def climate_day_bounds_utc(local_day: date, tz_name: str) -> Tuple[datetime, datetime]:
    """UTC [start, end) bounding the CLI climate day for `local_day`.

    The climate day runs LST-midnight to LST-midnight. Returns tz-aware UTC
    datetimes so a METAR archive (UTC) can be sliced to the exact CLI window
    before deriving max/min. Uses the STANDARD offset even during DST months.
    """
    off = standard_utc_offset_hours(tz_name)
    start = datetime(local_day.year, local_day.month, local_day.day, 0, 0,
                     tzinfo=UTC) - timedelta(hours=off)
    return start, start + timedelta(days=1)


def parse_kalshi_ts(value) -> Tuple[datetime, str]:
    """Parse a Kalshi timestamp into (tz-aware UTC datetime, unit_detected).

    Handles epoch seconds, epoch milliseconds, and ISO-8601 strings. The s-vs-ms
    ambiguity is a known bug class; we detect by magnitude and RETURN the detected
    unit so callers can assert it matches the endpoint's documented unit.
    """
    if isinstance(value, str):
        s = value.strip()
        if s.lstrip("-").isdigit():
            value = int(s)
        else:
            return _parse_iso(s), "iso8601"
    v = float(value)
    if v >= 1e12:
        return datetime.fromtimestamp(v / 1000.0, tz=UTC), "ms"
    if v >= 1e9:
        return datetime.fromtimestamp(v, tz=UTC), "s"
    raise ValueError(f"timestamp {value!r} too small to be epoch seconds or ms")


_CRYPTO_HOUR_TOKEN_RE = re.compile(r"^\d{2}[A-Za-z]{3}\d{2}\d{2}$")
_ET_ZONE = ZoneInfo("America/New_York")


def parse_crypto_hour_token_close_utc(token: str):
    """UTC close time for a Kalshi crypto-hourly ticker's date+hour token (e.g. '26JUL0621',
    the middle segment of 'KXBTC-26JUL0621-B71750').

    The trailing HH digit is America/New_York local time, NOT UTC (kb/lessons L45 —
    confirmed 2026-07-07 against live tape: KXBTC-26JUL0621 was captured 00:57:50 UTC on
    07-07, i.e. 20:57 EDT on 07-06, closing 21:00 EDT = 01:00 UTC 07-07;
    `collection/crypto_hourly.py`'s own docstring already documents "HH in ET"). Returns
    None if `token` doesn't match the YYMONDDHH grammar or the hour digit is out of range.
    """
    if not _CRYPTO_HOUR_TOKEN_RE.match(token):
        return None
    try:
        naive = datetime.strptime(token.upper(), "%y%b%d%H")
    except ValueError:
        return None
    local = naive.replace(tzinfo=_ET_ZONE)
    return local.astimezone(UTC)

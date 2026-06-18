"""Venue-agnostic data contracts shared by validation/ and analysis/.

ForecastEx must slot in behind these types without a rewrite, so nothing here
names Kalshi-specific fields; adapters (e.g. validation/v3_market.py) translate
raw venue payloads into these.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Verdict(str, Enum):
    CLEAN = "clean"
    DIRTY = "dirty"
    UNVERIFIABLE = "unverifiable"
    PASS = "pass"
    FAIL = "fail"


@dataclass
class BookLevel:
    price: float   # dollars in [0, 1]
    size: float    # contracts (Kalshi supports fractional/dollar-denominated size)


@dataclass
class OrderbookSnapshot:
    """Full-depth, both-sided, both-outcome book. 'yes'/'no' generalize across venues."""
    venue: str
    ticker: str
    ts_utc: datetime
    yes_bids: List[BookLevel] = field(default_factory=list)
    yes_asks: List[BookLevel] = field(default_factory=list)
    no_bids: List[BookLevel] = field(default_factory=list)
    no_asks: List[BookLevel] = field(default_factory=list)
    raw: Optional[Dict[str, Any]] = None

    def best(self, book: str) -> Optional[BookLevel]:
        levels = getattr(self, book)
        return levels[0] if levels else None


@dataclass
class MarketSpec:
    """Parsed market ticker (venue-agnostic)."""
    venue: str
    ticker: str
    series: str
    station: Optional[str] = None       # settlement station label / icao
    target_date: Optional[date] = None
    bucket_type: Optional[str] = None   # 'threshold_above'|'threshold_below'|'band'|...
    lo: Optional[float] = None          # bucket lower bound (deg F)
    hi: Optional[float] = None          # bucket upper bound (deg F)


@dataclass
class ActualsRecord:
    city: str
    station_id: str
    day: date
    tmax_f: Optional[float]
    tmin_f: Optional[float]
    source: str   # 'cli' | 'metar' | 'ghcn'


@dataclass
class ForecastRecord:
    source: str
    init_time_utc: Optional[datetime]
    valid_time_utc: datetime
    station: str
    variable: str
    value: Optional[float]
    unit: str

"""Offline unit tests for scripts/seed3_listing_age_anatomy.py.

Pure synthetic fixtures — no tape dependency, no network. Exercises the
nontrivial logic: age-bin assignment, the L13 startup-artifact exclusion,
2-outcome MECE eligibility, within-event decay, and the half-life fit.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.seed3_listing_age_anatomy import (  # noqa: E402
    bin_for_age, eligible_events, estimate_half_life, is_clean_two_outcome,
    overround_by_age_bin, parse_iso, tape_first_day, within_event_decay,
)

T0 = datetime(2026, 7, 5, 0, 0, tzinfo=timezone.utc)


def _cap(dt: datetime, bs: float, *, expected=2, member=2, comp=True, outcomes=None):
    return {
        "captured_at": dt,
        "bracket_sum": bs,
        "expected_outcomes": expected,
        "member_count": member,
        "completeness_ok": comp,
        "outcomes": outcomes if outcomes is not None else [
            {"yes_ask": 0.6}, {"yes_ask": bs - 0.6},
        ],
        "series": "KXTEST",
    }


def test_parse_iso_handles_z_and_offset():
    assert parse_iso("2026-07-05T00:00:00Z") == T0
    assert parse_iso("2026-07-05T00:00:00+00:00") == T0


def test_bin_for_age_boundaries():
    assert bin_for_age(0.0) == "0-1h"
    assert bin_for_age(0.99) == "0-1h"
    assert bin_for_age(1.0) == "1-2h"      # left-closed, right-open
    assert bin_for_age(23.9) == "8-24h"
    assert bin_for_age(24.0) == "24-72h"
    assert bin_for_age(500.0) == "168h+"
    assert bin_for_age(-1.0) is None


def test_is_clean_two_outcome():
    assert is_clean_two_outcome(_cap(T0, 1.4))
    assert not is_clean_two_outcome(_cap(T0, 1.4, expected=3))
    assert not is_clean_two_outcome(_cap(T0, 1.4, member=3))
    assert not is_clean_two_outcome(_cap(T0, 1.4, comp=False))


def test_l13_excludes_first_day_events():
    # event A first-seen on the tape's first day (T0) -> excluded (L13).
    # event B first-seen a day later -> kept.
    events = {
        "A": [_cap(T0, 1.5), _cap(T0 + timedelta(hours=30), 1.1)],
        "B": [_cap(T0 + timedelta(days=1), 1.5),
              _cap(T0 + timedelta(days=1, hours=30), 1.1)],
    }
    first_day = tape_first_day(events)
    assert first_day == T0.date()
    elig = eligible_events(events, first_day)
    assert "A" not in elig
    assert "B" in elig
    # ages are measured from B's own first_seen, not the tape start
    assert elig["B"][0]["age"] == 0.0
    assert abs(elig["B"][1]["age"] - 30.0) < 1e-6


def test_eligibility_drops_non_two_outcome_captures():
    events = {
        "B": [
            _cap(T0 + timedelta(days=1), 1.5),                    # clean
            _cap(T0 + timedelta(days=1, hours=1), 1.4, member=3),  # dropped
            _cap(T0 + timedelta(days=1, hours=2), 1.3, expected=3),  # dropped
        ],
    }
    elig = eligible_events(events, T0.date())
    assert len(elig["B"]) == 1
    assert abs(elig["B"][0]["overround"] - 0.5) < 1e-9


def test_overround_by_age_bin_groups_by_event():
    events = {
        "B": [_cap(T0 + timedelta(days=1), 1.5),                 # age 0 -> 0-1h
              _cap(T0 + timedelta(days=1, hours=30), 1.1)],      # age 30 -> 24-72h
        "C": [_cap(T0 + timedelta(days=2), 1.6),                 # age 0 -> 0-1h
              _cap(T0 + timedelta(days=2, hours=40), 1.05)],     # age 40 -> 24-72h
    }
    elig = eligible_events(events, T0.date())
    binned = overround_by_age_bin(elig)
    assert set(binned["0-1h"].keys()) == {"B", "C"}
    assert abs(binned["0-1h"]["B"][0] - 0.5) < 1e-9
    assert abs(binned["0-1h"]["C"][0] - 0.6) < 1e-9
    assert set(binned["24-72h"].keys()) == {"B", "C"}


def test_within_event_decay_sign_and_units():
    events = {
        "B": [_cap(T0 + timedelta(days=1), 1.5),                 # fresh overround 0.5
              _cap(T0 + timedelta(days=1, hours=30), 1.1)],      # aged  overround 0.1
    }
    elig = eligible_events(events, T0.date())
    decay = within_event_decay(elig, fresh_hi=2.0, aged_lo=24.0)
    assert "B" in decay
    assert abs(decay["B"][0] - 0.4) < 1e-9  # fresh - aged = 0.5 - 0.1


def test_within_event_decay_requires_both_ends():
    # only fresh captures -> no pair, event omitted
    events = {"B": [_cap(T0 + timedelta(days=1), 1.5),
                    _cap(T0 + timedelta(days=1, minutes=30), 1.4)]}
    elig = eligible_events(events, T0.date())
    assert within_event_decay(elig, fresh_hi=2.0, aged_lo=24.0) == {}


def test_estimate_half_life_recovers_known_decay():
    # construct means = floor + A*exp(-age/tau), tau=6h -> half-life ln2*6 ~ 4.16h
    import math
    floor, A, tau = 0.10, 0.30, 6.0
    mids = {"0-1h": 0.5, "1-2h": 1.5, "2-4h": 3.0, "4-8h": 6.0,
            "8-24h": 16.0, "24-72h": 48.0}
    bin_means = {label: floor + A * math.exp(-mid / tau) for label, mid in mids.items()}
    hl = estimate_half_life(bin_means, floor)
    assert hl is not None
    assert abs(hl - math.log(2) * tau) < 0.5


def test_estimate_half_life_none_when_flat():
    bin_means = {"0-1h": 0.10, "1-2h": 0.10, "2-4h": 0.10, "4-8h": 0.10}
    assert estimate_half_life(bin_means, 0.10) is None

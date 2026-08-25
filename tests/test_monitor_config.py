"""core.monitor_config — load/validate the monitor control surface, offline.

The load-bearing property is the TUNING CONTRACT: a threshold value outside its declared
range must fail LOUDLY (never clamp), both at load time and through the tuner's only write
path (`set_threshold_value`). A clamp here would hide exactly the bug the range exists to
catch — a nightly tuner drifting out of bounds."""
from __future__ import annotations

import copy

import pytest

from core import monitor_config as mc


def _minimal_doc():
    return {
        "scope": {"series_prefixes": ["KXHIGH"], "categories": [], "series_tickers": []},
        "selection": {"max_tickers": 200, "sort": "volume_then_close"},
        "cadences": {"scope_refresh_minutes": 60},
        "thresholds": {"mid_move_points": {"value": 15, "range": [8, 30]}},
        "alerting": {"rate_limit_per_kind_per_hour": 4},
        "retention": {"ws_depth_tape_days": 90},
    }


def test_repo_config_file_loads_and_validates():
    doc = mc.load()                       # the committed config must always be valid
    assert doc["thresholds"]["mid_move_points"]["value"] >= 1
    assert mc.threshold(doc, "mid_move_points") > 0


def test_value_outside_range_fails_loudly():
    doc = _minimal_doc()
    doc["thresholds"]["mid_move_points"]["value"] = 31
    with pytest.raises(mc.MonitorConfigError, match="outside declared range"):
        mc.validate(doc)


def test_empty_scope_rejected():
    doc = _minimal_doc()
    doc["scope"] = {"series_prefixes": [], "categories": [], "series_tickers": []}
    with pytest.raises(mc.MonitorConfigError, match="selects nothing"):
        mc.validate(doc)


def test_malformed_range_rejected():
    doc = _minimal_doc()
    doc["thresholds"]["mid_move_points"]["range"] = [30, 8]
    with pytest.raises(mc.MonitorConfigError, match="min <= max"):
        mc.validate(doc)


def test_set_threshold_value_moves_inside_range_only():
    doc = mc.validate(_minimal_doc())
    mc.set_threshold_value(doc, "mid_move_points", 20)
    assert mc.threshold(doc, "mid_move_points") == 20
    before = copy.deepcopy(doc)
    with pytest.raises(mc.MonitorConfigError, match="outside declared range"):
        mc.set_threshold_value(doc, "mid_move_points", 31)
    assert doc == before                  # rejected proposal leaves the doc untouched


def test_set_threshold_value_may_not_add_keys():
    doc = mc.validate(_minimal_doc())
    with pytest.raises(mc.MonitorConfigError, match="may not add keys"):
        mc.set_threshold_value(doc, "brand_new_knob", 1)

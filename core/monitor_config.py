"""Loader/validator for config/monitor.yaml — the 24/7 monitor's single control surface.

The tuning contract (see the config header): every numeric under `thresholds:` is a
`{value, range: [min, max]}` pair. `value` outside `range` is a CONFIG ERROR that fails
loudly at load — the nightly tuner writes values, humans write ranges, and this loader is
the enforcement point that keeps the loop from ever operating on a value its declared
boundary does not cover. No silent clamping: a clamp would hide exactly the bug (a tuner
writing out of bounds) the range exists to catch.

Pure read + validate; no network, no clock. The one writer-side helper,
`set_threshold_value`, edits a parsed document in memory and re-validates — persisting it
(and changelogging it) is the nightly tuner's job, not this module's.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from core.io import REPO_ROOT

MONITOR_CONFIG_PATH = REPO_ROOT / "config" / "monitor.yaml"

_REQUIRED_TOP_KEYS = ("scope", "selection", "thresholds", "alerting")


class MonitorConfigError(ValueError):
    """A structural or range violation in config/monitor.yaml."""


def _fail(msg: str) -> None:
    raise MonitorConfigError(f"config/monitor.yaml: {msg}")


def validate(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a parsed monitor config document in place; returns it for chaining."""
    if not isinstance(doc, dict):
        _fail("top level must be a mapping")
    for key in _REQUIRED_TOP_KEYS:
        if key not in doc:
            _fail(f"missing required section '{key}'")

    scope = doc["scope"]
    for lst in ("series_prefixes", "categories", "series_tickers"):
        if not isinstance(scope.get(lst), list):
            _fail(f"scope.{lst} must be a list")
    if not any(scope[l] for l in ("series_prefixes", "categories", "series_tickers")):
        _fail("scope selects nothing — at least one prefix, category, or ticker required")

    thresholds = doc["thresholds"]
    if not isinstance(thresholds, dict) or not thresholds:
        _fail("thresholds must be a non-empty mapping")
    for name, spec in thresholds.items():
        if not isinstance(spec, dict) or "value" not in spec or "range" not in spec:
            _fail(f"thresholds.{name} must be a mapping with 'value' and 'range'")
        rng = spec["range"]
        if (not isinstance(rng, list) or len(rng) != 2
                or not all(isinstance(x, (int, float)) for x in rng) or rng[0] > rng[1]):
            _fail(f"thresholds.{name}.range must be [min, max] with min <= max")
        val = spec["value"]
        if not isinstance(val, (int, float)):
            _fail(f"thresholds.{name}.value must be numeric")
        if not (rng[0] <= val <= rng[1]):
            _fail(f"thresholds.{name}.value {val} outside declared range {rng}")
    return doc


def load(path: Optional[Path] = None) -> Dict[str, Any]:
    path = Path(path) if path is not None else MONITOR_CONFIG_PATH
    with open(path, "r", encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return validate(doc)


def threshold(doc: Dict[str, Any], name: str) -> float:
    """The live value of one threshold (validated shape assumed — call after load())."""
    return float(doc["thresholds"][name]["value"])


def set_threshold_value(doc: Dict[str, Any], name: str, value: float) -> Dict[str, Any]:
    """Set a threshold value IN MEMORY, enforcing the declared range. The nightly tuner's
    only sanctioned write path; raises MonitorConfigError on an unknown name or an
    out-of-range value (the tuner must treat that as 'proposal rejected', never clamp)."""
    if name not in doc.get("thresholds", {}):
        _fail(f"unknown threshold '{name}' — the tuner may not add keys")
    rng = doc["thresholds"][name]["range"]
    if not (rng[0] <= value <= rng[1]):
        _fail(f"thresholds.{name}: proposed value {value} outside declared range {rng}")
    doc["thresholds"][name]["value"] = value
    return validate(doc)

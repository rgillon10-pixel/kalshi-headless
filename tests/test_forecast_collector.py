"""Single-pass forecast collector: parse+persist exercised FULLY OFFLINE.

Mirrors tests/test_capture_bitemporal.py — an injected fake Http serves a fixture
Open-Meteo multi-model response; no live network, no clock, no order path. The properties
under test are the ones the missing forecast tape must have from day 1:

  - the model list NEVER contains ncep_gefs025 (Hard Rule #1 — byte-identical to gfs_seamless);
  - every persisted line carries fetch_ts + a raw-response sha256 + source_tag='synthetic'
    (a forecast is a modeled number, never a fillable price — core/source_tag.py);
  - a dropped (city, model) fetch LOWERS the completeness count rather than vanishing
    (D3 honest completeness — the survivorship / silent-skip failure mode).
"""
from __future__ import annotations

import json

import pytest

from collection import forecast_collector as fc


# --------------------------------------------------------------------------- #
# fake Http — only the .text() method the collector uses, served from a fixture.
# Reproduces Open-Meteo's flat multi-model shape (per-model fields suffixed `_<model>`).
# --------------------------------------------------------------------------- #
class FakeHttp:
    base = "https://fake.test"

    def __init__(self, response_by_city, fail_cities=(), bad_json_cities=()):
        self.response_by_city = response_by_city   # {city: dict response}
        self.fail_cities = set(fail_cities)        # cities whose fetch raises
        self.bad_json_cities = set(bad_json_cities)  # cities returning non-JSON text
        self.calls = []                            # (url, params) audit of every fetch

    def text(self, url, **params):
        self.calls.append((url, params))
        # the collector keys a request by lat/lon; map them back to a city for the fixture
        city = self._city_for(params)
        if city in self.fail_cities:
            raise RuntimeError(f"simulated fetch failure: {city}")
        if city in self.bad_json_cities:
            return "<html>rate limited</html>"
        return json.dumps(self.response_by_city[city])

    def _city_for(self, params):
        for city, coords in _COORDS.items():
            if abs(coords["lat"] - params["latitude"]) < 1e-9 \
                    and abs(coords["lon"] - params["longitude"]) < 1e-9:
                return city
        raise KeyError(f"no fixture city for {params.get('latitude')},{params.get('longitude')}")


_COORDS = {
    "Testville": {"lat": 10.0, "lon": 20.0},
    "Othertown": {"lat": 30.0, "lon": 40.0},
}

_MODELS = ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_global"]


def _om_response(present_models, *, base=70.0):
    """An Open-Meteo-shaped response exposing daily Tmax for `present_models` only.
    A model in the request but absent here is the 'partial response' -> a drop."""
    daily = {"time": ["2026-06-18", "2026-06-19", "2026-06-20"]}
    units = {"time": "iso8601"}
    for i, m in enumerate(present_models):
        daily[f"temperature_2m_max_{m}"] = [base + i, base + i + 1, base + i + 2]
        units[f"temperature_2m_max_{m}"] = "°F"
    return {
        "latitude": 10.0, "longitude": 20.0,
        "generationtime_ms": 0.12345,
        "utc_offset_seconds": -14400,
        "timezone": "America/New_York",
        "elevation": 7.0,
        "daily_units": units,
        "daily": daily,
    }


def _tape_lines(store):
    path = store / "forecast.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


# --------------------------------------------------------------------------- #
# Hard Rule #1 — the curated model list excludes ncep_gefs025.
# --------------------------------------------------------------------------- #
def test_model_list_excludes_ncep_gefs025():
    assert "ncep_gefs025" not in fc.MODELS  # inv-pattern-def
    assert fc.MODELS == ["gfs_seamless", "ecmwf_ifs025", "icon_seamless", "gem_global"]


def test_run_rejects_ncep_gefs025_in_model_list(tmp_path):
    http = FakeHttp({"Testville": _om_response(_MODELS)})
    with pytest.raises(ValueError, match="ncep_gefs025"):
        fc.run(http=http, store=tmp_path,
               models=["gfs_seamless", "ncep_gefs025"],  # inv-pattern-def
               city_coords={"Testville": _COORDS["Testville"]})


# --------------------------------------------------------------------------- #
# happy path — every persisted line carries fetch_ts + raw sha256 + synthetic tag.
# --------------------------------------------------------------------------- #
def test_every_line_has_fetch_ts_raw_sha_and_synthetic_tag(tmp_path):
    http = FakeHttp({"Testville": _om_response(_MODELS)})
    summary = fc.run(http=http, store=tmp_path, models=_MODELS,
                     city_coords={"Testville": _COORDS["Testville"]})

    assert summary["n_expected"] == len(_MODELS)
    assert summary["n_complete"] == len(_MODELS)
    assert summary["n_dropped"] == 0

    lines = _tape_lines(tmp_path)
    assert len(lines) == len(_MODELS)
    persisted_models = {ln["model"] for ln in lines}
    assert persisted_models == set(_MODELS)
    assert "ncep_gefs025" not in persisted_models  # inv-pattern-def

    for ln in lines:
        assert ln["source_tag"] == "synthetic"        # a forecast is never a fill price
        assert ln["fetch_ts"] and "T" in ln["fetch_ts"] and "+00:00" in ln["fetch_ts"]
        # ms+ precision: a microsecond fractional second is present
        assert "." in ln["fetch_ts"].split("T")[1]
        assert len(ln["raw_sha256"]) == 64            # sha256 of the raw response bytes
        int(ln["raw_sha256"], 16)                     # hex
        assert ln["variable"] == "temperature_2m_max"
        assert ln["unit"] == "°F"
        assert ln["target_dates"] and ln["tmax_f"]
        assert len(ln["target_dates"]) == len(ln["tmax_f"])
        assert ln["source"] == "open-meteo"


def test_raw_sha256_binds_to_the_actual_response_bytes(tmp_path):
    from core.canonical import sha256_hex
    resp = _om_response(_MODELS)
    http = FakeHttp({"Testville": resp})
    fc.run(http=http, store=tmp_path, models=_MODELS,
           city_coords={"Testville": _COORDS["Testville"]})
    expected = sha256_hex(json.dumps(resp))
    for ln in _tape_lines(tmp_path):
        assert ln["raw_sha256"] == expected   # all models of one city share the response hash


# --------------------------------------------------------------------------- #
# the core property: a dropped fetch LOWERS completeness, never silently vanishes.
# --------------------------------------------------------------------------- #
def test_failed_city_fetch_drops_all_its_models_into_summary(tmp_path):
    http = FakeHttp(
        {"Testville": _om_response(_MODELS), "Othertown": _om_response(_MODELS)},
        fail_cities={"Othertown"},
    )
    summary = fc.run(http=http, store=tmp_path, models=_MODELS, city_coords=_COORDS)

    assert summary["n_expected"] == 2 * len(_MODELS)
    assert summary["n_complete"] == len(_MODELS)        # only Testville persisted
    assert summary["n_dropped"] == len(_MODELS)         # all of Othertown's models dropped
    assert summary["n_complete"] + summary["n_dropped"] == summary["n_expected"]

    dropped = {(d["city"], d["model"]) for d in summary["drops"]}
    assert dropped == {("Othertown", m) for m in _MODELS}
    assert all("fetch_failed" in d["reason"] for d in summary["drops"])

    # honest completeness: the dropped city contributed ZERO lines (not a silent partial)
    cities_in_tape = {ln["city"] for ln in _tape_lines(tmp_path)}
    assert cities_in_tape == {"Testville"}


def test_partial_model_response_drops_only_missing_models(tmp_path):
    # Open-Meteo returns only 2 of the 4 requested models -> the other 2 are honest drops.
    present = ["gfs_seamless", "ecmwf_ifs025"]
    http = FakeHttp({"Testville": _om_response(present)})
    summary = fc.run(http=http, store=tmp_path, models=_MODELS,
                     city_coords={"Testville": _COORDS["Testville"]})

    assert summary["n_complete"] == 2
    assert summary["n_dropped"] == 2
    persisted = {ln["model"] for ln in _tape_lines(tmp_path)}
    assert persisted == set(present)
    missing = {d["model"] for d in summary["drops"]}
    assert missing == {"icon_seamless", "gem_global"}
    assert all(d["reason"] == "model_absent_or_empty_in_response" for d in summary["drops"])


def test_non_json_response_drops_all_models_not_a_crash(tmp_path):
    http = FakeHttp({"Testville": _om_response(_MODELS)}, bad_json_cities={"Testville"})
    summary = fc.run(http=http, store=tmp_path, models=_MODELS,
                     city_coords={"Testville": _COORDS["Testville"]})
    assert summary["n_complete"] == 0
    assert summary["n_dropped"] == len(_MODELS)
    assert _tape_lines(tmp_path) == []
    assert all("parse_failed" in d["reason"] for d in summary["drops"])


# --------------------------------------------------------------------------- #
# append-only + limit + write isolation.
# --------------------------------------------------------------------------- #
def test_tape_is_append_only_across_passes(tmp_path):
    http = FakeHttp({"Testville": _om_response(_MODELS)})
    coords = {"Testville": _COORDS["Testville"]}
    fc.run(http=http, store=tmp_path, models=_MODELS, city_coords=coords)
    fc.run(http=http, store=tmp_path, models=_MODELS, city_coords=coords)
    # second pass appends, does not overwrite
    assert len(_tape_lines(tmp_path)) == 2 * len(_MODELS)


def test_limit_caps_cities(tmp_path):
    http = FakeHttp({"Testville": _om_response(_MODELS), "Othertown": _om_response(_MODELS)})
    summary = fc.run(http=http, store=tmp_path, models=_MODELS, city_coords=_COORDS, limit=1)
    assert summary["n_cities"] == 1
    assert {ln["city"] for ln in _tape_lines(tmp_path)} == {"Testville"}


def test_writes_only_under_given_store(tmp_path):
    http = FakeHttp({"Testville": _om_response(_MODELS)})
    fc.run(http=http, store=tmp_path, models=_MODELS,
           city_coords={"Testville": _COORDS["Testville"]})
    written = {p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file()}
    assert written == {"forecast.jsonl"}

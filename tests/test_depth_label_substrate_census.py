"""Tests for `scripts/depth_label_substrate_census.py` (idle-run policy (c), 2026-08-15).

Two tiers, per the repo's audit-script convention:
  * SYNTHETIC — full control over the population, so every branch (partial labeling, malformed
    lines, leafless tickers, vacuous floors) is exercised deterministically.
  * REAL-TAPE ACCEPTANCE — a FROZEN two-day slice (L191) symlinked into a tmp root, asserted
    with FLOORS AND DIRECTIONS ONLY, never equalities (L320 growth-safety): the tape is
    append-only and these files can still gain lines.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "_depth_label_substrate_census", REPO / "scripts" / "depth_label_substrate_census.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cen = _load()


# ─── ticker grammar ───────────────────────────────────────────────────────────────────
def test_series_of_takes_the_leading_token():
    assert cen.series_of("KXBTC-26AUG1421-B54250") == "KXBTC"
    assert cen.series_of("KXMLBGAME-26JUL07NYYBOS-NYY") == "KXMLBGAME"


def test_event_of_strips_only_the_final_leaf():
    assert cen.event_of("KXBTC-26AUG1421-B54250") == "KXBTC-26AUG1421"
    assert cen.event_of("KXMLBGAME-26JUL07NYYBOS-NYY") == "KXMLBGAME-26JUL07NYYBOS"


def test_event_of_abstains_rather_than_guessing_a_unit():
    """A leafless ticker has no inferable unit — guessing one would merge unrelated markets."""
    assert cen.event_of("KXBTC") is None
    assert cen.event_of("") is None
    assert cen.event_of("-") is None


def test_class_of_partitions_the_three_populations():
    assert cen.class_of("KXBTC-26AUG1421-B1") == "crypto"
    assert cen.class_of("KXETH-26AUG1421-B1") == "crypto"
    assert cen.class_of("KXMLBGAME-26JUL07NYYBOS-NYY") == "sports"
    assert cen.class_of("KXTEMPNYCH-26JUL1707-B1") == "other"


# ─── population scan ──────────────────────────────────────────────────────────────────
def _write(root: Path, family: str, day: str, records) -> None:
    d = root / family
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"dt={day}.jsonl", "a") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def test_population_counts_snapshots_days_and_span(tmp_path):
    _write(tmp_path, "orderbook_depth", "2026-08-01", [
        {"ticker": "KXBTC-26AUG0101-B1", "captured_at": "2026-08-01T01:00:00Z"},
        {"ticker": "KXBTC-26AUG0101-B1", "captured_at": "2026-08-01T02:00:00Z"},
    ])
    _write(tmp_path, "orderbook_depth", "2026-08-02", [
        {"ticker": "KXBTC-26AUG0101-B1", "captured_at": "2026-08-02T01:00:00Z"}])
    pop = cen.scan_depth_population(str(tmp_path))
    e = pop["KXBTC-26AUG0101-B1"]
    assert e["n_snapshots"] == 3
    assert e["days"] == {"2026-08-01", "2026-08-02"}
    assert e["first_captured_at"] == "2026-08-01T01:00:00Z"
    assert e["last_captured_at"] == "2026-08-02T01:00:00Z"


def test_population_counts_malformed_lines_never_silently_skips(tmp_path):
    d = tmp_path / "orderbook_depth"
    d.mkdir(parents=True)
    (d / "dt=2026-08-01.jsonl").write_text(
        json.dumps({"ticker": "KXBTC-26AUG0101-B1", "captured_at": "z"}) + "\n"
        "{not json\n"
        + json.dumps({"captured_at": "z"}) + "\n"      # no ticker
        + "\n")                                          # blank line is not a defect
    pop = cen.scan_depth_population(str(tmp_path))
    assert pop["_n_bad_lines"]["n_snapshots"] == 2


def test_population_is_empty_without_the_family(tmp_path):
    pop = cen.scan_depth_population(str(tmp_path))
    assert set(pop) == {"_n_bad_lines"}


# ─── unit readiness / verdict ────────────────────────────────────────────────────────
class _Rep:
    def __init__(self, resolved):
        self.resolved = {t: object() for t in resolved}
        self.non_binary = {}
        self.listed_unsettled = {}


def _pop(legs):
    return {t: {"n_snapshots": n, "days": set(days)} for t, (n, days) in legs.items()}


def test_partially_labeled_unit_is_never_probe_ready():
    """A fill-sim scoring only a ladder's labeled legs conditions away the catastrophic
    wing (L41/L86) — so partial labeling must NOT count as ready."""
    pop = _pop({"KXBTC-26AUG0101-B1": (5, ["2026-08-01"]),
                "KXBTC-26AUG0101-B2": (5, ["2026-08-01"])})
    units = cen._unit_readiness(pop, _Rep({"KXBTC-26AUG0101-B1"}), "tape")
    u = units["crypto"]["KXBTC-26AUG0101"]
    assert u["n_labeled_legs"] == 1 and u["n_legs"] == 2
    assert u["fully_labeled"] is False and u["probe_ready"] is False


def test_fully_labeled_unit_below_the_snapshot_floor_is_not_ready():
    pop = _pop({"KXBTC-26AUG0101-B1": (1, ["2026-08-01"])})
    units = cen._unit_readiness(pop, _Rep({"KXBTC-26AUG0101-B1"}), "tape")
    assert units["crypto"]["KXBTC-26AUG0101"]["probe_ready"] is False


def test_verdict_names_the_binding_shortfall_not_just_a_boolean():
    pop = _pop({f"KXBTC-26AUG0{i}01-B1": (2, ["2026-08-01"]) for i in range(1, 5)})
    units = cen._unit_readiness(pop, _Rep(set(pop)), "tape")
    v = cen._verdict(units["crypto"])
    assert v["verdict"] == "SUBSTRATE-INADEQUATE"
    assert any("MIN_READY_UNITS" in s for s in v["binding_shortfall"])
    assert any("MIN_DISTINCT_DAYS" in s for s in v["binding_shortfall"])


def test_verdict_adequate_requires_both_floors():
    legs = {f"KXBTC-26AUG{i:02d}01-B1": (2, [f"2026-08-{(i % 28) + 1:02d}"]) for i in range(40)}
    units = cen._unit_readiness(_pop(legs), _Rep(set(legs)), "tape")
    v = cen._verdict(units["crypto"])
    assert v["verdict"] == "SUBSTRATE-ADEQUATE" and v["binding_shortfall"] == []


def test_the_preregistered_unit_floor_is_vacuous_on_a_multileg_ladder_L353():
    """The defect this census found in its OWN pre-registered floor: a 188-leg ladder clears
    `n_snapshots >= 2` at the unit level while EVERY leg carries exactly one snapshot, so the
    unit reads ready and no resting order on it is observable. `fill_observability` is the
    separate measurement that exposes it — this test pins the disagreement itself."""
    legs = {f"KXBTC-26AUG0101-B{i}": (1, ["2026-08-01"]) for i in range(188)}
    units = cen._unit_readiness(_pop(legs), _Rep(set(legs)), "tape")
    assert units["crypto"]["KXBTC-26AUG0101"]["probe_ready"] is True      # vacuously
    obs = cen.fill_observability(_pop(legs))
    assert obs["crypto"]["median_snapshots_per_leg"] == 1.0
    assert obs["crypto"]["frac_legs_with_ge_2_snapshots"] == 0.0


def test_fill_observability_empty_class_abstains_with_none():
    obs = cen.fill_observability({})
    assert obs["crypto"]["n_legs"] == 0
    assert obs["crypto"]["median_snapshots_per_leg"] is None
    assert obs["crypto"]["frac_legs_with_ge_2_snapshots"] is None


# ─── label sources ───────────────────────────────────────────────────────────────────
def test_naive_union_reads_ledger_and_caches_but_not_embedded_sources(tmp_path):
    _write(tmp_path, "settlement_ledger", "2026-07-17",
           [{"ticker": "A-1", "result": "yes"}, {"ticker": "A-2", "result": ""}])
    (tmp_path / "q99_settlement_cache").mkdir()
    (tmp_path / "q99_settlement_cache" / "settlement.json").write_text(
        json.dumps({"markets": {"B-1": {"result": "no"}, "B-2": {"result": "scalar"}}}))
    _write(tmp_path, "crypto_hourly", "2026-08-01", [
        {"previous_settlement": {"status": "settled", "results": {"C-1": "yes"}}}])
    labels = cen.naive_union_labels(str(tmp_path))
    assert labels == {"A-1": "settlement_ledger", "B-1": "q99_settlement_cache"}
    assert "C-1" not in labels          # the embedded source is exactly what it misses


def test_ladder_coherence_flags_a_ladder_without_exactly_one_winner(tmp_path):
    _write(tmp_path, "crypto_hourly", "2026-08-01", [
        {"previous_settlement": {"status": "settled",
                                 "results": {"KXBTC-1-B1": "yes", "KXBTC-1-B2": "no"}}},
        {"previous_settlement": {"status": "settled",
                                 "results": {"KXBTC-2-B1": "yes", "KXBTC-2-B2": "yes"}}},
        {"previous_settlement": {"status": "pending", "results": {"KXBTC-3-B1": "yes"}}},
    ])
    c = cen.ladder_coherence(str(tmp_path))
    assert c["n_ladders_checked"] == 2          # the pending record carries no settlement
    assert c["n_exactly_one_yes"] == 1 and c["n_violations"] == 1
    assert c["violation_examples"] == ["KXBTC-2:2"]


def test_ladder_coherence_ignores_non_bracket_legs(tmp_path):
    _write(tmp_path, "crypto_hourly", "2026-08-01", [
        {"previous_settlement": {"status": "settled",
                                 "results": {"KXBTC-1-B1": "yes", "KXBTC-1-T99": "no"}}}])
    assert cen.ladder_coherence(str(tmp_path))["n_violations"] == 0


# ─── report shape: an adequacy census, never a strategy verdict ───────────────────────
def test_report_emits_no_pnl_ci_or_bootstrap_key(tmp_path):
    _write(tmp_path, "orderbook_depth", "2026-08-01",
           [{"ticker": "KXBTC-26AUG0101-B1", "captured_at": "2026-08-01T01:00:00Z"}])
    rep = cen.census(str(tmp_path))
    # `tape_root` is the tmp dir, whose name is derived from THIS test's own name — excluded
    # so the check reads the report's content, not pytest's path grammar.
    blob = json.dumps({k: v for k, v in rep.items() if k != "tape_root"}).lower()
    for forbidden in ("pnl", "ci95", "bootstrap", "kelly", "edge_per_contract"):
        assert forbidden not in blob
    assert rep["schema_version"] == cen.SCHEMA_VERSION


def test_report_carries_the_verdict_caveat_so_it_travels_with_the_number(tmp_path):
    _write(tmp_path, "orderbook_depth", "2026-08-01",
           [{"ticker": "KXBTC-26AUG0101-B1", "captured_at": "2026-08-01T01:00:00Z"}])
    rep = cen.census(str(tmp_path))
    assert "fill_observability" in rep["verdict_caveat"]
    assert "L353" in rep["verdict_caveat"]


def test_main_writes_the_json_and_exits_zero(tmp_path):
    _write(tmp_path, "orderbook_depth", "2026-08-01",
           [{"ticker": "KXBTC-26AUG0101-B1", "captured_at": "2026-08-01T01:00:00Z"}])
    out = tmp_path / "r.json"
    assert cen.main(["--tape-root", str(tmp_path), "--json-out", str(out)]) == 0
    assert json.loads(out.read_text())["population"]["n_tickers"] == 1


# ─── real-tape acceptance (FROZEN slice, floors/directions only) ──────────────────────
@pytest.fixture(scope="module")
def frozen_slice(tmp_path_factory):
    """Two real depth day-files + the whole real crypto_hourly family, symlinked into a tmp
    root. Skips (never fails) if the tape is not present in this checkout."""
    days = ["dt=2026-08-13.jsonl", "dt=2026-08-14.jsonl"]
    src = REPO / "tape" / "orderbook_depth"
    if not all((src / d).exists() for d in days):
        pytest.skip("frozen depth slice not present in this checkout")
    root = tmp_path_factory.mktemp("slice")
    (root / "orderbook_depth").mkdir()
    for d in days:
        os.symlink(src / d, root / "orderbook_depth" / d)
    ch = REPO / "tape" / "crypto_hourly"
    if ch.exists():
        os.symlink(ch, root / "crypto_hourly")
    return str(root)


def test_acceptance_real_slice_crypto_legs_are_snapshot_poor(frozen_slice):
    """The finding's load-bearing asymmetry, half 1: on the crypto ladder tape a leg is seen
    about once, so a resting order's fate is unobservable. Direction, not equality."""
    obs = cen.fill_observability(
        {k: v for k, v in cen.scan_depth_population(frozen_slice).items()
         if k != "_n_bad_lines"})
    assert obs["crypto"]["n_legs"] > 50
    assert obs["crypto"]["median_snapshots_per_leg"] <= 2.0
    assert obs["crypto"]["frac_legs_with_ge_2_snapshots"] < 0.75


def test_acceptance_real_slice_sports_legs_are_snapshot_rich(frozen_slice):
    """Half 2: the sports depth tape sees a leg many times over — the opposite regime, on the
    same family, in the same days."""
    obs = cen.fill_observability(
        {k: v for k, v in cen.scan_depth_population(frozen_slice).items()
         if k != "_n_bad_lines"})
    assert obs["sports"]["n_legs"] > 500
    assert obs["sports"]["median_snapshots_per_leg"] >= 3.0
    assert obs["sports"]["frac_legs_with_ge_2_snapshots"] > 0.80


def test_acceptance_real_ladder_coherence_holds_on_the_whole_crypto_family(frozen_slice):
    """The only validation available for the embedded label source (its ticker set is disjoint
    from every other source's): a MECE ladder settles exactly one bracket `yes`."""
    c = cen.ladder_coherence(frozen_slice)
    if c["n_ladders_checked"] == 0:
        pytest.skip("crypto_hourly not present in this checkout")
    assert c["n_ladders_checked"] >= 800
    assert c["n_violations"] == 0

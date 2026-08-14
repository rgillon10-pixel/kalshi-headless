"""scripts.l164_seam_rederive — offline unit tests + the independence pin.

Pure arithmetic over datetimes: no network, no tape, no clock (every instant is passed in).
"""
from __future__ import annotations

import ast
import json
import pathlib
from datetime import datetime, timezone

import pytest

from scripts import burst_chunk_plan
from scripts.l164_seam_rederive import (
    audit,
    instant_margin_seconds,
    main,
    materialize_chunk_ticks,
    parse_instant,
    seam_windows,
)

REDERIVE_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "l164_seam_rederive.py"


# --------------------------------------------------------------------------- #
# Independence: the redundancy re-derivation must not import the module it is
# re-deriving (pinned on the AST, not on prose — the L349/Q56 precedent).
# --------------------------------------------------------------------------- #
def test_rederive_imports_nothing_from_the_module_it_re_derives():
    tree = ast.parse(REDERIVE_PATH.read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    assert not any("burst_chunk_plan" in name for name in imported), sorted(imported)
    # and it must not lean on the shared time helper either -- its own parser is the point
    assert not any(name.startswith("core") for name in imported), sorted(imported)


# --------------------------------------------------------------------------- #
# parse_instant / materialize_chunk_ticks / seam_windows
# --------------------------------------------------------------------------- #
def test_parse_instant_matches_the_shared_helper_on_real_timestamps():
    from core.timeutil import parse_iso_utc
    for iso in [
        "2026-07-29T17:40:00Z", "2026-07-29T18:00:00Z", "2026-12-31T23:59:59Z",
        "2024-02-29T12:30:13Z", "2000-02-29T00:00:00Z",
    ]:
        assert parse_instant(iso) == parse_iso_utc(iso), iso


def test_parse_instant_tolerates_a_missing_trailing_z():
    assert parse_instant("2026-07-29T18:00:00") == datetime(2026, 7, 29, 18, tzinfo=timezone.utc)


def test_materialize_first_tick_of_every_chunk_fires_immediately():
    start = parse_instant("2026-07-29T17:40:00Z")
    chunks = materialize_chunk_ticks(start, [3, 3], 60)
    assert chunks[0][0] == start
    assert len(chunks[0]) == 3 and len(chunks[1]) == 3
    assert (chunks[1][0] - chunks[0][-1]).total_seconds() == 60


@pytest.mark.parametrize("seq,interval", [([], 60), ([0, 3], 60), ([3, -1], 60), ([3], 0)])
def test_materialize_rejects_degenerate_input(seq, interval):
    with pytest.raises(ValueError):
        materialize_chunk_ticks(parse_instant("2026-07-29T17:40:00Z"), seq, interval)


def test_seam_windows_one_per_internal_boundary():
    chunks = materialize_chunk_ticks(parse_instant("2026-07-29T17:40:00Z"), [16, 14, 14, 14, 14, 12], 90)
    seams = seam_windows(chunks)
    assert len(seams) == 5
    assert seams[0][0] == parse_instant("2026-07-29T18:02:30Z")
    assert seams[0][1] == parse_instant("2026-07-29T18:04:00Z")


def test_instant_margin_is_zero_inside_the_seam_and_positive_outside():
    seam = (parse_instant("2026-07-29T17:59:30Z"), parse_instant("2026-07-29T18:01:00Z"))
    assert instant_margin_seconds(parse_instant("2026-07-29T18:00:00Z"), seam) == 0.0
    assert instant_margin_seconds(parse_instant("2026-07-29T17:58:00Z"), seam) == 90.0
    assert instant_margin_seconds(parse_instant("2026-07-29T18:02:00Z"), seam) == 60.0


# --------------------------------------------------------------------------- #
# The two headline re-derivations
# --------------------------------------------------------------------------- #
def test_committed_fomc_recipe_re_derives_as_safe_for_statement_and_presser():
    report = audit(
        "2026-07-29T17:40:00Z", [16, 14, 14, 14, 14, 12], 90,
        ["2026-07-29T18:00:00Z", "2026-07-29T18:30:00Z"],
    )
    assert report["all_safe"] is True
    statement, presser = report["instants"]
    assert statement["containing_chunk"] == 1
    assert statement["nearest_seam_margin_seconds"] == 150.0
    assert presser["containing_chunk"] == 3
    assert presser["nearest_seam_margin_seconds"] == 300.0


def test_naive_uniform_plan_re_derives_the_hand_observed_straddle():
    report = audit(
        "2026-07-29T17:40:00Z", [14, 14, 14, 14, 14, 14], 90, ["2026-07-29T18:00:00Z"],
    )
    assert report["all_safe"] is False
    (statement,) = report["instants"]
    # the strongest form of the defect: no chunk captures the release instant AT ALL
    assert statement["containing_chunk"] is None
    assert statement["nearest_seam_margin_seconds"] == 0.0
    assert report["seams_utc"][0] == ("2026-07-29T17:59:30Z", "2026-07-29T18:01:00Z")


# --------------------------------------------------------------------------- #
# Cross-implementation agreement (the actual point of the redundancy run)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("seq,interval,protect_offsets_min", [
    ([16, 14, 14, 14, 14, 12], 90, [20.0, 50.0]),
    ([14, 14, 14, 14, 14, 14], 90, [20.0]),
    ([15, 15, 15, 15, 15, 15, 10], 60, [40.0]),
    ([43, 15, 15, 15, 12], 60, [40.0]),
    ([10, 10, 10], 60, [9.0, 19.5]),
])
def test_both_implementations_agree_on_safety_for_the_same_inputs(seq, interval, protect_offsets_min):
    start_iso = "2026-07-29T17:40:00Z"
    start = parse_instant(start_iso)
    from datetime import timedelta
    isos = [(start + timedelta(minutes=m)).isoformat().replace("+00:00", "Z") for m in protect_offsets_min]
    rederived = audit(start_iso, seq, interval, isos)
    violations = burst_chunk_plan.seam_violations(seq, interval, [m * 60.0 for m in protect_offsets_min])
    assert rederived["all_safe"] == (violations == [])


def test_both_implementations_agree_on_every_seam_position():
    from datetime import timedelta
    seq, interval = [16, 14, 14, 14, 14, 12], 90
    start = parse_instant("2026-07-29T17:40:00Z")
    offsets = burst_chunk_plan.seam_offsets_seconds(seq, interval)
    report = audit("2026-07-29T17:40:00Z", seq, interval, [])
    assert len(offsets) == len(report["seams_utc"])
    for (start_s, end_s), (start_iso, end_iso) in zip(offsets, report["seams_utc"]):
        assert start + timedelta(seconds=start_s) == parse_instant(start_iso)
        assert start + timedelta(seconds=end_s) == parse_instant(end_iso)


def test_multi_generator_output_is_confirmed_safe_by_the_independent_path():
    from datetime import timedelta
    start_iso, start = "2026-07-29T17:40:00Z", parse_instant("2026-07-29T17:40:00Z")
    protects = [20.0, 50.0, 95.0]
    seq = burst_chunk_plan.chunk_max_ticks_sequence_protecting_multi(125, 20, 90, protects)
    isos = [(start + timedelta(minutes=m)).isoformat().replace("+00:00", "Z") for m in protects]
    assert audit(start_iso, seq, 90, isos)["all_safe"] is True


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def test_cli_exits_zero_on_a_safe_plan_and_two_on_an_unsafe_one(capsys, tmp_path):
    out_file = tmp_path / "report.json"
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--interval", "90",
        "--sequence", "16,14,14,14,14,12",
        "--protect", "2026-07-29T18:00:00Z", "--protect", "2026-07-29T18:30:00Z",
        "--json-out", str(out_file),
    ])
    assert rc == 0
    written = json.loads(out_file.read_text())
    assert written["all_safe"] is True
    assert written["n_ticks"] == 84

    capsys.readouterr()
    rc = main([
        "--start", "2026-07-29T17:40:00Z", "--interval", "90",
        "--sequence", "[14, 14, 14, 14, 14, 14]", "--protect", "2026-07-29T18:00:00Z",
    ])
    assert rc == 2
    assert json.loads(capsys.readouterr().out)["all_safe"] is False


def test_cli_emits_no_price_or_pnl_key_this_is_scheduling_arithmetic_only(capsys):
    main([
        "--start", "2026-07-29T17:40:00Z", "--interval", "90", "--sequence", "16,14,14,14,14,12",
        "--protect", "2026-07-29T18:00:00Z",
    ])
    text = capsys.readouterr().out
    for forbidden in ["price", "pnl", "edge", "ci_", "yes_ask", "no_ask", "price_source_tag"]:
        assert forbidden not in text.lower(), forbidden

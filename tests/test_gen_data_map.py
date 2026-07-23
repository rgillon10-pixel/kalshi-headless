"""scripts.gen_data_map — computed-stat rendering, UNANNOTATED drift visibility, and the
--check staleness gate. Fully offline over a tmp tape root."""
from __future__ import annotations

import json

from scripts import gen_data_map as gdm


def _mk_family(root, name, days, lines_per_day=2, tag="real_ask"):
    fam = root / name
    fam.mkdir(parents=True)
    for d in days:
        rec = {"schema_version": f"{name}.v1", "price_source_tag": tag, "yes_ask": 0.42}
        (fam / f"dt={d}.jsonl").write_text(
            "\n".join(json.dumps(rec) for _ in range(lines_per_day)) + "\n")
    return fam


def test_render_computes_stats_and_flags_unannotated(tmp_path):
    tape = tmp_path / "tape"
    _mk_family(tape, "anomalies", ["2026-07-01", "2026-07-03"])  # annotated family, 1 gap
    _mk_family(tape, "brand_new_family", ["2026-07-02"])          # not in ANNOTATIONS

    doc = gdm.render(tape)

    assert "## tape/anomalies/" in doc
    assert "2026-07-01 → 2026-07-03" in doc
    assert "missing days in span: 2026-07-02" in doc
    assert "real_ask: 2" in doc
    assert "anomalies.v1" in doc
    # drift visibility: a family on disk but not curated renders loudly, never silently
    assert "## tape/brand_new_family/ — `UNANNOTATED`" in doc


def test_check_mode_detects_stale_and_fresh(tmp_path):
    tape = tmp_path / "tape"
    _mk_family(tape, "anomalies", ["2026-07-01"])
    out = tmp_path / "DATA-MAP.md"

    # stale: file absent
    assert gdm.main(["--tape-root", str(tape), "--out", str(out), "--check"]) == 1
    # write, then fresh
    assert gdm.main(["--tape-root", str(tape), "--out", str(out)]) == 0
    assert gdm.main(["--tape-root", str(tape), "--out", str(out), "--check"]) == 0
    # tape grows -> stale again
    _mk_family(tape, "econ_prints", ["2026-07-02"])
    assert gdm.main(["--tape-root", str(tape), "--out", str(out), "--check"]) == 1

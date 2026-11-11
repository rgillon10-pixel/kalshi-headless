"""scripts.tape_archive — copy-verify-delete safety, manifest provenance, dry-run default,
idempotency, and hot-window protection. Fully offline over tmp dirs; never touches git."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts import tape_archive as ta

NOW = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)


def _mk(tape, family, day, content="{\"a\":1}\n{\"a\":2}\n"):
    fam = tape / family
    fam.mkdir(parents=True, exist_ok=True)
    p = fam / f"dt={day}.jsonl"
    p.write_text(content)
    return p


def test_dry_run_moves_nothing_and_reports(tmp_path):
    tape, arch = tmp_path / "tape", tmp_path / "arch"
    cold = _mk(tape, "universe_sweep", "2026-07-01")
    hot = _mk(tape, "universe_sweep", "2026-07-20")

    rep = ta.archive_pass(tape, arch, age_days=14, apply=False, now=NOW)

    assert cold.exists() and hot.exists()
    assert not arch.exists()
    assert [r["file"] for r in rep["archived"]] == ["universe_sweep/dt=2026-07-01.jsonl"]
    assert rep["archived"][0]["dry_run"] is True
    assert rep["kept_hot"] == 1
    # manifest not written on dry-run
    assert not (tape / "universe_sweep" / ta.MANIFEST_NAME).exists()


def test_apply_manifests_copies_verifies_then_deletes(tmp_path):
    tape, arch = tmp_path / "tape", tmp_path / "arch"
    cold = _mk(tape, "orderbook_depth", "2026-07-01")

    rep = ta.archive_pass(tape, arch, age_days=14, apply=True, now=NOW)

    assert not cold.exists()
    dest = arch / "orderbook_depth" / "dt=2026-07-01.jsonl"
    assert dest.exists()
    manifest = tape / "orderbook_depth" / ta.MANIFEST_NAME
    rec = json.loads(manifest.read_text().strip())
    assert rec["file"] == "orderbook_depth/dt=2026-07-01.jsonl"
    assert rec["n_lines"] == 2
    assert rec["sha256"] == ta._sha256_and_lines(dest)[0]
    assert rep["errors"] == []
    # verify() closes the loop against the manifest
    v = ta.verify(tape, arch)
    assert v["ok"] == 1 and not v["missing"] and not v["mismatched"]


def test_apply_is_idempotent(tmp_path):
    tape, arch = tmp_path / "tape", tmp_path / "arch"
    _mk(tape, "sports_pairs", "2026-07-01")

    ta.archive_pass(tape, arch, age_days=14, apply=True, now=NOW)
    rep2 = ta.archive_pass(tape, arch, age_days=14, apply=True, now=NOW)

    assert rep2["archived"] == []
    assert rep2["skipped_manifested"] == 1
    manifest = tape / "sports_pairs" / ta.MANIFEST_NAME
    assert len(manifest.read_text().strip().splitlines()) == 1


def test_non_bulk_family_never_touched(tmp_path):
    tape, arch = tmp_path / "tape", tmp_path / "arch"
    p = _mk(tape, "settlement_ledger", "2026-06-01")

    rep = ta.archive_pass(tape, arch, age_days=14, apply=True, now=NOW)

    assert p.exists()
    assert rep["archived"] == []


def test_preexisting_corrupt_copy_keeps_source(tmp_path):
    tape, arch = tmp_path / "tape", tmp_path / "arch"
    src = _mk(tape, "universe_sweep", "2026-07-01")
    bad = arch / "universe_sweep" / "dt=2026-07-01.jsonl"
    bad.parent.mkdir(parents=True)
    bad.write_text("corrupted\n")

    rep = ta.archive_pass(tape, arch, age_days=14, apply=True, now=NOW)

    assert src.exists()  # source never deleted on hash mismatch
    assert len(rep["errors"]) == 1 and "mismatch" in rep["errors"][0]["error"]

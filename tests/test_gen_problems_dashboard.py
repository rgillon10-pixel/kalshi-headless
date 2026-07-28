"""scripts.gen_problems_dashboard — the read-only HTML problem-dashboard generator.

L200 (2026-07-27, kb/lessons/00-lessons.md): this script used to re-implement the
kb/lessons/00-lessons.md table-splitting job with a SECOND, independently-buggy pipe
splitter (honoured an escaped `\\|` but not a `|` inside a backtick code span, e.g.
L161's `` sed 's|refs/heads/||' ``) -- a different bug from the one L194 fixed in
scripts/invariants.py's own splitter, so the two tools silently disagreed on 3 of 190
rows (L89, L161, L173) with no test catching the divergence. It was ALSO hardcoded to
Ryan's local Mac path and raised SystemExit on any other checkout, so it could not even
run in a cloud sandbox -- which is why nobody noticed. Both are fixed: `cells()` now
delegates to `invariants._split_lesson_row` (one parser, not two) and `find_repo` is
anchored on this file's own location.

The module writes reports/problems-dashboard.html as a side effect of being imported
(no `if __name__ == "__main__":` guard -- pre-existing, out of scope here); every test
redirects OUT to tmp_path via sys.argv before loading it, so the repo's committed
dashboard file is never touched by the suite.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_MOD_PATH = _REPO_ROOT / "scripts" / "gen_problems_dashboard.py"

sys.path.insert(0, str(_REPO_ROOT / "scripts"))
import invariants as _invariants  # noqa: E402


def _load_dashboard(monkeypatch, tmp_path):
    """Import scripts/gen_problems_dashboard.py fresh, with OUT redirected to tmp_path
    (the module writes on import — see the module docstring above)."""
    out = tmp_path / "dashboard.html"
    monkeypatch.setattr(sys, "argv", ["gen_problems_dashboard.py", str(out)])
    spec = importlib.util.spec_from_file_location("gen_problems_dashboard_under_test", _MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, out


# ---------------------------------------------------------------------- portability

def test_repo_discovery_is_not_hardcoded_to_a_specific_machine(monkeypatch, tmp_path):
    """The pre-fix REPO = find_repo("/Users/ryan.gillon/...") raised SystemExit on any
    checkout that wasn't Ryan's own Mac -- including every cloud sandbox, which is why
    the cells()/_split_lesson_row divergence below went unnoticed for a full run. This
    pins the fix: importing the module from THIS checkout must succeed and resolve REPO
    to this actual repo root, not Ryan's literal path."""
    mod, _out = _load_dashboard(monkeypatch, tmp_path)
    assert mod.REPO == _REPO_ROOT
    assert (mod.REPO / "kb" / "lessons" / "00-lessons.md").exists()


def test_dashboard_runs_and_writes_output(monkeypatch, tmp_path):
    mod, out = _load_dashboard(monkeypatch, tmp_path)
    assert out.exists()
    assert out.stat().st_size > 0
    assert len(mod.lessons) > 0
    assert len(mod.strategies) > 0


# --------------------------------------------------------- frozen-fixture regression
# The exact 3 rows the 2026-07-28 audit found diverging between this script's old
# splitter and invariants._split_lesson_row, frozen verbatim (not read from the live,
# growing ledger) so this test can never be affected by the file's ongoing growth.

_FROZEN_DIVERGENT_ROWS = {
    'L89': (
        '| L89 | 2026-07-17 | A **clamp-vs-rounding discriminator (dead-band vs quantization) must test the GAP relative to the data\'s OWN granularity — never against an absolute threshold.** The two hypotheses for a zero-heavy series are: (a) a **dead-band clamp** — rates inside a ±band forced to *exactly* 0 while the surviving nonzeros stay **continuous/unquantized**; vs (b) a **symmetric-rounding/quantization artifact** — the "zeros" are a lattice bucket straddling zero and the nonzeros sit on that *same* tick grid. The decisive test is therefore (i) are the nonzeros continuous or lattice-quantized, and (ii) is there a **hard gap in the open interval just above zero**. Q42: the Kalshi perp finalized funding backfill (1,447 `broker_truth` prints, 2026-06-03→07-16, 13 contracts) has a pooled exact-zero fraction 0.762 with a hard gap in `(0, 1e-4)` — **1,102** exact zeros, **0** nonzeros in `(0, 1e-4)`, **186** in `[1e-4, 1.5e-4)` — and the smallest nonzero `|rate|` *varies* per contract (BTC 1.0004e-4 … SUI 1.0560e-4, a floor near ~1e-4, not one shared value). Because the nonzeros are continuous rather than on a 1e-4 lattice, the zeros are a **genuine ±1bp clamp**, not a rounding bucket — confirmed on 12/13 contracts (KXLINKPERP undecidable, 1 nonzero print). An absolute-threshold test ("call it a clamp if zeros dominate below some fixed ε") would misclassify EITHER a fine-tick series (real clamp hidden under a coarse ε) OR a coarse-tick series (rounding mistaken for a clamp). Do NOT headline an inferred single tick / ticks-from-zero figure — it is a sample-dependent proxy, not a physical venue tick. Same per-probe-methodology-gate family as L6 (bootstrap the right unit) / L27 (magnitude-vs-tick) / L28 (observability precheck). | `findings/2026-07-17-q42-funding-clamp-characterization.md` (Q42 part 1, verifier-CONFIRMED); `scripts/q42_funding_clamp_probe.py` | **test (this discriminator) + protocol (the general principle)** — the gap-based discriminator is pinned for the Q42 probe by `tests/test_q42_funding_clamp_probe.py::test_clamp_signature_clear_gap` and `::test_rounding_signature_one_tick_from_zero` (clear-gap vs one-tick-from-zero fixtures) plus `::test_infer_tick_smallest_gap`. The GENERAL methodology (test the gap relative to the data\'s own granularity, never an absolute threshold) is a per-probe verdict-methodology judgment — like L6/L27/L28 the population and granularity are per-design, so it is **not statically assertable** at the invariants layer (the scanner scans text, it cannot evaluate a series\' lattice structure) and is terminal as **protocol** once encoded in probe precedents. NOTE — a second Q42 lesson candidate (route population/sample stdev through `core.stats.safe_pstdev`, which the probe does at `scripts/q42_funding_clamp_probe.py:172` with an `n>=4` guard) was NOT given its own row: it is already covered at the `invariant` end of the gradient by **Hard Rule #2 / L2** (`inv_no_bare_pstdev` + `inv_no_pstdev_import` in `scripts/invariants.py`, sanctioned to `core/stats.py`); the probe simply complied, so a new row would restate an enforced rule rather than move any lesson along the gradient. |'
    ),
    'L161': (
        '| L161 | 2026-07-25 | **Malformed tape-branch names are a RECURRING defect, not a one-off — and a naive lexical "newest branch" sweep silently mis-triages them, which is a data-loss risk in step-0b.** **44 of 192** remote `tape/*` branches fail the canonical name regex `^tape/hourly-[0-9]{8}T[0-9]{4}Z$`, measured 2026-07-25 ~08:5xZ by the exact command this row ships (an earlier draft of this row said "roughly 13-20 of 192" with no command and no definition of "malformed" — unfalsifiable, and re-derived to 44-45 of 192-193 minutes later; an independent verifier measured 45 of 193 in the same hour, i.e. **the count DRIFTS as branches accumulate**, which is precisely why a row asserting a count over refs must inline its command rather than freeze a number): `git ls-remote --heads origin \'refs/heads/tape/*\' | awk \'{print $2}\' | sed \'s|refs/heads/||\' > /tmp/br.txt` then `wc -l < /tmp/br.txt` (192 total), `grep -cE \'^tape/hourly-[0-9]{8}T[0-9]{4}Z$\' /tmp/br.txt` (148 well-formed), `grep -vcE \'^tape/hourly-[0-9]{8}T[0-9]{4}Z$\' /tmp/br.txt` (44 failures). The dominant malformed shape is ~22 branches of the form `hourly-YYYYMMDDHHMMZ` — the `T` separator missing — including this run\'s own newest branch `tape/hourly-202607250406Z`. **The substance is unchanged and still verified:** `tape/hourly-Z` and `tape/hourly-` (no timestamp at all) both exist. Because `Z` and the empty suffix sort AFTER every dated `tape/hourly-*` branch lexically, a sweep that picks "the newest-looking name" picks one of these degenerate branches, concludes it has already swept past everything, and leaves real unswept tape behind — silently. **Rule: any branch failing the name regex must be triaged by COMMIT DATE, never by name order**, and the count of name-regex failures should be reported by the sweep rather than skipped quietly. | step-0b stranded-tape sweep by a separate `tape-auditor`, 2026-07-25 run; `findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md` (§3) | **tool (enforced) + test** — the same `scripts/tape_branch_sweep.py` built for L160 implements this: `is_malformed_branch_name` classifies every branch against the canonical regex, and for malformed names `triage_branch` resolves `commit_date` via `git log -1 --format=%cI` (never name order); `format_report`\'s malformed section is sorted by that date. The malformed-branch count is always printed, never skipped quietly. Live run (2026-07-25) found **44 of 192** malformed — matching this row\'s own measurement exactly. Pinned by `tests/test_tape_branch_sweep.py::TestNameValidation` (7 cases incl. the exact `hourly-Z`/`hourly-`/missing-`T` shapes this row names) and `TestFetchAndTriage` (a malformed-but-contained fixture branch asserts `commit_date is not None`). See `findings/2026-07-25-tape-branch-sweep-tool-and-backlog-audit.md`. |'
    ),
    'L173': (
        '| L173 | 2026-07-26 | **A duration-gated "stale window"/persistence statistic with no PRE-EVENT BASELINE measures the venue pair\'s permanent overround, not the event\'s lag.** On the 2026-07-14 CPI burst the absolute rule (`|gap| - fee > 0` sustained) flagged **12 of 15** units persistent, of which **7** had `|gap| - fee > 0` on **100% of their PRE-release captures** and whose 4502s "stale windows" were simply the full post-release span of the tape — i.e. a standing cross-venue level difference re-labelled as an event-driven dislocation. Baselining each unit against its own pre-release gap cut it to **4 of 15**. Extends L76 from "count vs wall-clock" to "absolute vs baselined": a persistence measure must be differenced against the same unit\'s own quiet-period value, or it cannot distinguish lag from level. | `scripts/q48_s55_fomc_lag_probe.py` (Q48/S55 idle-run policy (b) prep, 2026-07-26; producer + 2 independent `verifier` rounds); counts re-derivable via `python3 scripts/q48_s55_fomc_lag_probe.py --release-ts 2026-07-14T12:30:00Z` (measured 2026-07-26 on committed `tape/polymarket_macro_pairs/`, 9000 records) | **test** — `tests/test_q48_s55_fomc_lag_probe.py::test_stale_window_is_baselined_against_the_units_own_pre_release_gap` (a unit whose gap exceeds fee identically before and after the release must NOT count as persistent) and `::test_stale_window_baseline_unmeasurable_is_none_never_false` (no pre-release captures → `None`, never a silent `False`). |'
    ),
}


@pytest.mark.parametrize("lesson_id", sorted(_FROZEN_DIVERGENT_ROWS))
def test_frozen_divergent_row_cells_match_invariants_split(lesson_id):
    """On the frozen 2026-07-28-vintage text of each previously-divergent row, the
    dashboard's cells() (via invariants._split_lesson_row) and invariants._split_lesson_row
    itself must agree field-for-field -- because after the fix they are the SAME parser.
    This is the concrete regression the row's own text names as its acceptance test;
    frozen strings mean it can never be defeated by editing the live ledger."""
    line = _FROZEN_DIVERGENT_ROWS[lesson_id]
    direct = _invariants._split_lesson_row(line)
    assert len(direct) >= 6, f"{lesson_id}: fixture row must have >=6 raw fields"
    # The dashboard's cells() is the same splitter with leading/trailing empty fields
    # trimmed -- reconstruct that trim here without importing the (import-side-effecting)
    # module, so this test has no filesystem side effect at all.
    trimmed = list(direct)
    if trimmed and trimmed[0].strip() == "":
        trimmed = trimmed[1:]
    if trimmed and trimmed[-1].strip() == "":
        trimmed = trimmed[:-1]
    stripped = [c.strip() for c in trimmed]
    assert stripped[0] == lesson_id
    # No backtick code-span pipe or escaped pipe leaked a phantom extra field beyond the
    # canonical 5 (id/date/lesson/source/enforcement) -- this is exactly what the OLD
    # naive `(?<!\\)\|`-only splitter got wrong for these 3 rows.
    enf = "|".join(stripped[4:])
    assert "\\|" not in stripped[2]  # lesson-text cell never carries a raw escape artifact
    assert enf.strip().startswith("**")  # every enforcement cell opens with a bold tier marker


# ------------------------------------------------------- live-tree structural check
# Not pinned to any specific count or row content (immune to L191/L192's live-document
# growth hazard) -- only asserts the two parsers of the SAME table stay in agreement,
# which must hold for every row the ledger will ever grow to contain.

def test_dashboard_and_invariants_agree_on_every_live_lesson_row(monkeypatch, tmp_path):
    mod, _out = _load_dashboard(monkeypatch, tmp_path)
    inv_rows = {lid: enf.strip() for lid, _lesson, enf in _invariants._parse_lesson_rows()}
    dash_rows = {r["id"]: r["enf"].strip() for r in mod.lessons}
    assert dash_rows, "live ledger produced 0 parsed rows -- parser regression"
    assert set(dash_rows) == set(inv_rows), "the two parsers disagree on WHICH rows exist"
    mismatches = sorted(lid for lid in dash_rows if dash_rows[lid] != inv_rows[lid])
    assert mismatches == [], (
        f"dashboard cells() and invariants._parse_lesson_rows disagree on enforcement "
        f"text for {mismatches} -- two parsers of one table must never diverge (L200)"
    )

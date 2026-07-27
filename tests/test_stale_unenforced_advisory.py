"""Stale-`**UNENFORCED**` candidate advisory — recall, precision and supersession.

Context (the 2026-07-27 defect this file exists to prevent recurring):
`scripts/invariants.py::_stale_unenforced_candidate_issues` extracted ONLY backticked
`func_name()` tokens from an enforcement cell. Measured on the real ledger that was
185 rows parsed / 21 `**UNENFORCED**` / **0 candidate tokens extracted** / 0 issues reported,
while an independent audit classified all 21 of those 21 rows as already-built stale markers.
A zero-recall detector was manufacturing false assurance: "0 issues" read as "queue clean"
when it actually meant "the extractor saw nothing".

So the load-bearing assertions here are RECALL assertions, pinned against a FROZEN copy of
those 21 rows (`tests/fixtures/lessons_unenforced_21_2026-07-27.md`) so they cannot go vacuous
once the real ledger's rows are disposed/flipped. Recall is honestly PARTIAL (7 of 21) and the
14 unreached rows are enumerated below as deliberate blind spots — a fabricated 21/21 would be
the same false assurance in a new costume.

FROZEN vs LIVE (2026-07-27, second correction — the L192/L200 recurrence)
------------------------------------------------------------------------
Every assertion in this file that depends on WHAT A LESSON ROW SAYS runs against a frozen
fixture. Nothing here may gate on the prose of the live, append-only ledger.

Why: the pipe-split counterfactual below used to enumerate, against the LIVE
`kb/lessons/00-lessons.md`, exactly which rows carry an embedded pipe ("these 14 disagree
with a naive split, all other rows agree"). That made the binding pytest gate a function of
the ledger's WORDS: it went red twice on 2026-07-27 when a kb-distiller appended new rows
that legitimately contained a literal `|`, and the distiller had to REWORD ITS OWN LESSON to
get green. The ledger is the artifact of record; a regression test must never dictate what a
future lesson may say. That is L192/L200 recurring inside its own fix.

The split now is:

* FROZEN (`tests/fixtures/lessons_pipe_split_2026-07-27.md` — 49 byte-identical rows copied
  from the ledger on 2026-07-27: all 14 misparsing rows plus a 35-row representative sample of
  correctly-parsing rows). The full counterfactual lives here and is unchanged in strength:
  the naive `line.split("|")[5]` rule disagrees with the delimiter-aware splitter on exactly
  those 14 and agrees on all 35 others. Nobody can rewrite a fixture, so this can neither go
  vacuous nor go red on someone else's legitimate append.
* LIVE (`kb/lessons/00-lessons.md`) — CONTENT-INDEPENDENT structure only: no row is dropped
  by the parser, and no enforcement cell is truncated at either end (its leading tier marker
  survives, and it runs to the end of the row). Those hold for any prose whatsoever, including
  a row containing literal pipes in any of the three shapes (`\\|`, code-span, or bare).
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import sqlite3

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "lessons_unenforced_21_2026-07-27.md"
# The frozen pipe-split snapshot: 49 rows copied byte-identically out of kb/lessons/00-lessons.md
# on 2026-07-27 (all 14 rows a naive `split("|")[5]` misparses + a 35-row representative sample
# of rows it parses correctly, including every plain immediate NEIGHBOUR of a misparsing row,
# the L188 `DISPOSES:` row, and rows spanning L1..L200). Deliberately NOT re-verified against the
# live ledger anywhere: an identity check would re-couple this gate to live prose.
FIXTURE_PIPES = ROOT / "tests" / "fixtures" / "lessons_pipe_split_2026-07-27.md"
LIVE_LEDGER = ROOT / "kb" / "lessons" / "00-lessons.md"


def _load_engine():
    spec = importlib.util.spec_from_file_location("inv_engine", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()


# ─── The frozen 21-row recall record ─────────────────────────────────────────
#
# Measured 2026-07-27 against the frozen fixture + the real tree. Partial by design:
# a row whose enforcement is prose-only ("a per-probe methodology gate", "encoded in probe
# precedents") names no machine-checkable artifact, so nothing can resolve it.

FIXTURE_ALL_21 = (
    "L22", "L27", "L28", "L32", "L39", "L45", "L51", "L59", "L64", "L65", "L66",
    "L68", "L69", "L76", "L86", "L105", "L117", "L119", "L162", "L164", "L165",
)
# REACHED (7): each names an artifact that exists in the committed tree today.
FIXTURE_REACHED_7 = ("L28", "L32", "L51", "L76", "L105", "L164", "L165")
# NOT REACHED (14) — the deliberate, documented blind spots:
#   L22  names a constant + a bare script path only (bare paths never match, by design)
#   L27  prose ("a shared bootstrap-verdict helper"), no named artifact
#   L39  says "edge-prober house-style" in PROSE without backticking the charter path
#   L45  prose ("a shared ticker-grammar parsing helper in core/"), no named artifact
#   L59  prose ("a future core/-write pass"), no named artifact
#   L64  prose ("a core/-level close-time helper"), no named artifact
#   L65  no artifact at all (an idea-stage market-structure kill)
#   L66  no artifact at all (a writeup-precision note)
#   L68  no artifact at all (a proposal-time rule)
#   L69  prose ("any Q27/Q30-style template"), no named artifact
#   L86  prose ("a shared test harness"), no named artifact
#   L117 names `scripts/tape_gap_monitor.py` but no CLI flag → M2 needs BOTH halves
#   L119 prose ("no shared helper computes this metric yet"), no named artifact
#   L162 names `kb/00-LOG.md` + `LOOP-QUEUE.md` (not .py) and a `pytest --collect-only`
#        flag with no .py path in the cell → M2 needs a repo-relative *.py path
FIXTURE_BLIND_SPOTS_14 = tuple(x for x in FIXTURE_ALL_21 if x not in FIXTURE_REACHED_7)
FIXTURE_BY_MATCHER = (("func", 0), ("path_symbol", 1), ("script_flag", 1), ("agent_charter", 5))


def test_frozen_fixture_is_the_21_unenforced_rows():
    rows = inv._parse_lesson_rows(FIXTURE)
    assert len(rows) == 21
    assert tuple(r[0] for r in rows) == FIXTURE_ALL_21
    assert all(r[2].startswith("**UNENFORCED**") for r in rows)
    # The fixture must never carry a DISPOSES: marker — it is the frozen pre-disposition state.
    assert inv._lesson_disposed_ids(rows) == set()


def test_frozen_fixture_recall_is_seven_of_twenty_one():
    """THE recall pin. 7 of 21 — stated honestly, with the 14 blind spots named."""
    rep = inv.stale_unenforced_recall_report(FIXTURE, source_root=ROOT)
    assert rep.n_rows == 21
    assert rep.n_unenforced == 21
    assert rep.n_disposed == 0
    assert rep.n_open_unenforced == 21
    assert rep.n_with_extractable_candidate == 7
    assert rep.n_flagged == 7
    assert rep.flagged_ids == FIXTURE_REACHED_7
    assert rep.by_matcher == FIXTURE_BY_MATCHER
    assert len(FIXTURE_BLIND_SPOTS_14) == 14
    assert not (set(FIXTURE_BLIND_SPOTS_14) & set(rep.flagged_ids))


def test_frozen_fixture_pre_widening_extractor_reached_zero():
    """The measured BASELINE: the original `func_name()`-only matcher extracted 0 tokens from
    all 21 rows — the zero-recall state that made a 0-issue report look like a clean queue."""
    rows = inv._parse_lesson_rows(FIXTURE)
    func_tokens = [
        args for _lid, _lt, enf in rows
        for matcher, args in inv._extract_stale_candidates(enf) if matcher == "func"
    ]
    assert func_tokens == []


def test_frozen_fixture_issue_strings_name_their_evidence():
    issues = inv._stale_unenforced_candidate_issues(FIXTURE, source_root=ROOT)
    assert len(issues) == 8  # L165 names TWO charters; every other reached row names one
    joined = "\n".join(issues)
    assert (
        "L164: cell NAMES script `scripts/burst_chunk_plan.py`, which REGISTERS `--protect`"
        in joined
    )
    assert (
        "L105: cell NAMES charter `.claude/agents/edge-prober.md`, which CITES L105" in joined
    )
    assert "tests/test_probe_ladder_coherence.py::" in joined


# ─── M1: path::symbol ────────────────────────────────────────────────────────

def _ledger(tmp_path, enforcement, lesson_id="L1", lesson_text="some lesson"):
    p = tmp_path / "00-lessons.md"
    p.write_text(f"| {lesson_id} | 2026-07-01 | {lesson_text} | src | {enforcement} |\n")
    return p


def test_m1_path_symbol_fires_when_file_defines_symbol(tmp_path):
    src = tmp_path / "src"
    (src / "tests").mkdir(parents=True)
    (src / "tests" / "test_x.py").write_text("def test_thing_works():\n    pass\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `tests/test_x.py::test_thing_works`")
    issues = inv._stale_unenforced_candidate_issues(lessons, source_root=src)
    assert issues == [
        "L1: cell NAMES `tests/test_x.py::test_thing_works`, which EXISTS in the tree "
        "(name match only -- not proof it enforces L1)"
    ]


def test_m1_path_symbol_fires_for_class_method(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("class Thing:\n    def do_it(self):\n        pass\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `mod.py::Thing.do_it`")
    issues = inv._stale_unenforced_candidate_issues(lessons, source_root=src)
    assert issues == [
        "L1: cell NAMES `mod.py::Thing.do_it`, which EXISTS in the tree "
        "(name match only -- not proof it enforces L1)"
    ]


def test_m1_silent_when_symbol_absent(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def something_else():\n    pass\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `mod.py::not_built_yet`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m1_silent_when_file_absent(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `tests/test_ghost.py::test_ghost`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m1_silent_when_class_missing_for_dotted_symbol(tmp_path):
    # `mod.py::Thing.do_it` where do_it is a module-level function, not Thing's method.
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def do_it():\n    pass\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `mod.py::Thing.do_it`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m1_path_traversal_token_is_refused(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def leaked():\n    pass\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `../src/mod.py::leaked`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src / "sub") == []
    assert inv._safe_repo_path(src, "../src/mod.py") is None
    assert inv._safe_repo_path(src, "/etc/passwd") is None


# ─── M2: script path + CLI flag in the same cell ─────────────────────────────

def test_m2_script_flag_fires_when_script_registers_flag(tmp_path):
    src = tmp_path / "src"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "plan.py").write_text(
        'import argparse\np = argparse.ArgumentParser()\np.add_argument("--protect", default=None)\n'
    )
    lessons = _ledger(
        tmp_path,
        "**UNENFORCED** -- candidate: teach `scripts/plan.py` an optional `--protect` argument",
    )
    issues = inv._stale_unenforced_candidate_issues(lessons, source_root=src)
    assert issues == [
        "L1: cell NAMES script `scripts/plan.py`, which REGISTERS `--protect` "
        "(registration match only -- not proof it enforces L1)"
    ]


def test_m2_silent_when_flag_absent_from_script(tmp_path):
    src = tmp_path / "src"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "plan.py").write_text('p.add_argument("--start")\n')
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `scripts/plan.py` gains `--protect`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m2_silent_when_flag_only_mentioned_unquoted(tmp_path):
    # A prose/comment mention is not a registered option: the flag literal must be QUOTED.
    src = tmp_path / "src"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "plan.py").write_text("# a future --protect argument would go here\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `scripts/plan.py` gains `--protect`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m2_silent_when_script_absent(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: `scripts/ghost.py` gains `--protect`")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m2_needs_both_halves_in_the_same_cell(tmp_path):
    # A bare script path with no flag must NOT fire — nearly every open row names an existing
    # file as the SITE where a new check should be added; path-existence alone carries no signal.
    src = tmp_path / "src"
    (src / "scripts").mkdir(parents=True)
    (src / "scripts" / "plan.py").write_text('p.add_argument("--protect")\n')
    lessons = _ledger(tmp_path, "**UNENFORCED** -- candidate: extend `scripts/plan.py` somehow")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


# ─── M3: agent-charter encoding ──────────────────────────────────────────────

def _charter(src, name, text):
    d = src / ".claude" / "agents"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(text)


def test_m3_agent_charter_fires_when_charter_cites_this_row(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "House style: always do the thing (L105).\n")
    lessons = _ledger(
        tmp_path,
        "**UNENFORCED** -- a future run should add the `.claude/agents/edge-prober.md` bullet",
        lesson_id="L105",
    )
    issues = inv._stale_unenforced_candidate_issues(lessons, source_root=src)
    assert issues == [
        "L105: cell NAMES charter `.claude/agents/edge-prober.md`, which CITES L105 "
        "(citation match only -- not proof it enforces L105)"
    ]


def test_m3_silent_when_charter_does_not_cite_this_row(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "House style: some other rule (L107).\n")
    lessons = _ledger(
        tmp_path, "**UNENFORCED** -- add the `.claude/agents/edge-prober.md` bullet", lesson_id="L105"
    )
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m3_id_match_is_word_bounded(tmp_path):
    # "L1050" must not satisfy the "cites L105" test.
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "See L1050 for the unrelated rule.\n")
    lessons = _ledger(
        tmp_path, "**UNENFORCED** -- add the `.claude/agents/edge-prober.md` bullet", lesson_id="L105"
    )
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m3_silent_when_charter_absent(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    lessons = _ledger(
        tmp_path, "**UNENFORCED** -- add the `.claude/agents/ghost.md` bullet", lesson_id="L105"
    )
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_m3_needs_backticked_path_not_prose(tmp_path):
    # L39's real shape: says "edge-prober house-style" in prose without backticking the path.
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "House style mentions L39.\n")
    lessons = _ledger(
        tmp_path,
        "**UNENFORCED** -- terminal as protocol once the edge-prober house style encodes it",
        lesson_id="L39",
    )
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


# ─── Enforcement-column scoping (unchanged, re-pinned for the new matchers) ──

def test_lesson_text_column_is_never_scanned_by_new_matchers(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def do_it():\n    pass\n")
    _charter(src, "edge-prober.md", "cites L1 already\n")
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L1 | 2026-07-01 | background: `mod.py::do_it` and `.claude/agents/edge-prober.md` "
        "already exist | src | **UNENFORCED** -- candidate: a new prose note |\n"
    )
    assert inv._stale_unenforced_candidate_issues(p, source_root=src) == []


def test_non_unenforced_rows_are_never_scanned(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def do_it():\n    pass\n")
    lessons = _ledger(tmp_path, "**test** (BUILT) -- `mod.py::do_it` pins this")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_unbackticked_prose_naming_an_existing_symbol_does_not_fire(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def _iter_source_files():\n    pass\n")
    lessons = _ledger(
        tmp_path,
        "**UNENFORCED** -- candidate: something like mod.py::_iter_source_files or "
        "_iter_source_files() without backticks",
    )
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


# ─── DISPOSES: the one canonical supersession marker ─────────────────────────

def _rows(*cells):
    return [(f"L{i + 1}", "text", c) for i, c in enumerate(cells)]


def test_disposes_comma_separated_list():
    assert inv._lesson_disposed_ids(_rows("**protocol** -- DISPOSES: L22, L27, L28")) == {
        "L22", "L27", "L28"
    }


def test_disposes_space_separated_and_no_space_after_comma():
    assert inv._lesson_disposed_ids(_rows("DISPOSES: L22 L27,L28")) == {"L22", "L27", "L28"}


def test_disposes_terminates_at_sentence_boundary():
    got = inv._lesson_disposed_ids(
        _rows("**protocol** -- DISPOSES: L22, L27. Audited in findings/x.md, which revisits L39")
    )
    assert got == {"L22", "L27"}


def test_disposes_terminates_at_em_dash_and_prose_word():
    assert inv._lesson_disposed_ids(_rows("DISPOSES: L22 — superseded by L99")) == {"L22"}
    assert inv._lesson_disposed_ids(_rows("DISPOSES: L22 and L27")) == {"L22"}


def test_prose_mention_never_disposes():
    assert inv._lesson_disposed_ids(_rows("**UNENFORCED** -- see L22; supersedes L27")) == set()


def test_disposes_is_case_sensitive():
    assert inv._lesson_disposed_ids(_rows("disposes: L22", "Disposes: L27")) == set()


def test_multiple_disposes_markers_union():
    got = inv._lesson_disposed_ids(_rows("DISPOSES: L22. Also DISPOSES: L27, L28", "DISPOSES: L45"))
    assert got == {"L22", "L27", "L28", "L45"}


def test_disposes_in_lesson_text_column_does_not_count(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "cites L105\n")
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L105 | 2026-07-01 | the marker DISPOSES: L105 written in prose | src | "
        "**UNENFORCED** -- add the `.claude/agents/edge-prober.md` bullet |\n"
    )
    # Still flagged: only the ENFORCEMENT column can dispose.
    assert len(inv._stale_unenforced_candidate_issues(p, source_root=src)) == 1


def test_disposed_row_is_skipped_and_counted(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "cites L105 and L28\n")
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L28 | 2026-07-01 | a | src | **UNENFORCED** -- `.claude/agents/edge-prober.md` |\n"
        "| L105 | 2026-07-01 | b | src | **UNENFORCED** -- `.claude/agents/edge-prober.md` |\n"
        "| L200 | 2026-07-27 | disposition row | src | **protocol** -- DISPOSES: L28. Audited. |\n"
    )
    issues = inv._stale_unenforced_candidate_issues(p, source_root=src)
    assert [i.split(":")[0] for i in issues] == ["L105"]
    rep = inv.stale_unenforced_recall_report(p, source_root=src)
    assert (rep.n_rows, rep.n_unenforced, rep.n_disposed, rep.n_open_unenforced) == (3, 2, 1, 1)
    assert rep.open_unenforced_ids == ("L105",)


def test_prose_l22_does_not_suppress_a_real_hit(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    _charter(src, "edge-prober.md", "cites L22\n")
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L22 | 2026-07-01 | a | src | **UNENFORCED** -- `.claude/agents/edge-prober.md` |\n"
        "| L200 | 2026-07-27 | b | src | **protocol** -- this row merely mentions L22 in prose |\n"
    )
    assert len(inv._stale_unenforced_candidate_issues(p, source_root=src)) == 1


# ─── Recall report + advisory text ───────────────────────────────────────────

def test_recall_report_distinguishes_extractable_from_flagged(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_text("def built_already():\n    pass\n")
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L1 | 2026-07-01 | a | src | **UNENFORCED** -- `mod.py::built_already` |\n"
        "| L2 | 2026-07-01 | b | src | **UNENFORCED** -- `mod.py::not_built_yet` |\n"
        "| L3 | 2026-07-01 | c | src | **UNENFORCED** -- a per-probe methodology gate, prose only |\n"
    )
    rep = inv.stale_unenforced_recall_report(p, source_root=src)
    assert rep.n_open_unenforced == 3
    assert rep.n_with_extractable_candidate == 2   # L1 and L2 name a checkable artifact
    assert rep.n_flagged == 1                      # only L1's exists
    assert rep.flagged_ids == ("L1",)


def test_warning_carries_the_recall_sentence():
    rep = inv.stale_unenforced_recall_report(FIXTURE, source_root=ROOT)
    issues = inv._stale_unenforced_candidate_issues(FIXTURE, source_root=ROOT)
    msg = inv.stale_unenforced_candidate_warning(issues, rep)
    assert msg is not None
    assert "Extraction reached 7 of 21 open UNENFORCED row(s)" in msg
    assert "COVERAGE limit" in msg
    assert "non-gating" in msg
    assert "L152" in msg


def test_zero_issue_scan_with_partial_recall_still_speaks():
    """The heart of the defect: 0 issues + incomplete extraction must NOT read as clean."""
    rep = inv.StaleUnenforcedRecallReport(
        n_rows=185, n_unenforced=21, n_disposed=0, n_open_unenforced=21,
        n_with_extractable_candidate=0, n_flagged=0,
        by_matcher=(("func", 0), ("path_symbol", 0), ("script_flag", 0), ("agent_charter", 0)),
        flagged_ids=(), open_unenforced_ids=(),
    )
    msg = inv.stale_unenforced_candidate_warning([], rep)
    assert msg is not None
    assert "NOT a clean-queue signal" in msg
    assert "Extraction reached 0 of 21 open UNENFORCED row(s)" in msg


def test_zero_issue_scan_is_silent_when_queue_is_empty_or_fully_reached():
    empty = inv._EMPTY_STALE_RECALL
    assert inv.stale_unenforced_candidate_warning([], empty) is None
    full = empty._replace(n_open_unenforced=3, n_with_extractable_candidate=3)
    assert inv.stale_unenforced_candidate_warning([], full) is None
    # Legacy call shape (no recall record) keeps its silent-on-empty contract.
    assert inv.stale_unenforced_candidate_warning([]) is None


# ─── Offline / best-effort safety ────────────────────────────────────────────

def test_missing_ledger_returns_empty_and_never_raises(tmp_path):
    assert inv._stale_unenforced_candidate_issues(tmp_path / "nope.md") == []
    assert inv.stale_unenforced_recall_report(tmp_path / "nope.md") == inv._EMPTY_STALE_RECALL


def test_directory_as_ledger_is_safe(tmp_path):
    assert inv._stale_unenforced_candidate_issues(tmp_path) == []
    assert inv.stale_unenforced_recall_report(tmp_path).n_rows == 0


def test_malformed_ledger_is_safe(tmp_path):
    p = tmp_path / "00-lessons.md"
    p.write_text("| L1 | truncated row with too few columns\n|||||\n\x00garbage\n")
    assert inv._stale_unenforced_candidate_issues(p) == []
    assert inv.stale_unenforced_recall_report(p).n_flagged == 0


def test_undecodable_ledger_is_safe(tmp_path):
    p = tmp_path / "00-lessons.md"
    p.write_bytes(b"\xff\xfe\x00\x01| L1 | a | b | c | **UNENFORCED** |\n")
    assert inv._stale_unenforced_candidate_issues(p) == []
    assert inv.stale_unenforced_recall_report(p) == inv._EMPTY_STALE_RECALL


def test_unreadable_source_file_does_not_break_the_scan(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "mod.py").write_bytes(b"\xff\xfe def built_already():\n")
    lessons = _ledger(tmp_path, "**UNENFORCED** -- `mod.py::built_already`")
    # errors='replace' keeps the read alive; the point is no exception escapes.
    assert isinstance(inv._stale_unenforced_candidate_issues(lessons, source_root=src), list)


# ─── Real-tree acceptance + non-gating contract ──────────────────────────────

def test_real_tree_current_state_is_pinned():
    """STRUCTURAL acceptance pin on the ACTUAL committed ledger. Deliberately holds no live
    COUNT beyond the append-only floor: the ledger is written by other agents (a kb-distiller
    landed L188's 21-ID `DISPOSES:` row mid-run on 2026-07-27, taking the open queue from 21 to
    2), so a hard count here fails for someone else's legitimate edit. What must always hold is
    the arithmetic: disposed + open == unenforced, and every flagged row is an open row.
    The measured numbers live on the FROZEN fixture, which nobody can rewrite."""
    rep = inv.stale_unenforced_recall_report()
    assert rep.n_rows >= 190                      # append-only ledger; 190 rows on 2026-07-27
    assert rep.n_disposed + rep.n_open_unenforced == rep.n_unenforced
    assert rep.n_flagged <= rep.n_with_extractable_candidate <= rep.n_open_unenforced
    assert set(rep.flagged_ids) <= set(rep.open_unenforced_ids)


def test_advisory_is_non_gating_on_the_real_tree(monkeypatch, capsys):
    """ABSENCE OF EFFECT only. This test must NEVER assert the advisory's TEXT: whether it
    prints at all depends on LIVE ledger state another agent may write during the same run —
    on 2026-07-27 a kb-distiller's `DISPOSES:` row took `n_open_unenforced` to 0, the formatter
    correctly returned None, and two text-presence assertions here went red for a reason that
    had nothing to do with the code under test. Text belongs on the frozen fixture
    (`test_advisory_text_is_pinned_on_the_frozen_fixture`) and on the monkeypatched wiring pin
    (`test_main_writes_a_firing_advisory_to_stderr`)."""
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "invariants: all green" in captured.out


def test_advisory_text_is_pinned_on_the_frozen_fixture():
    """The TEXT contract, over an artifact no other agent rewrites: the frozen 21-row fixture
    (7 reached) always produces a firing advisory carrying its recall statement."""
    rep = inv.stale_unenforced_recall_report(FIXTURE, source_root=ROOT)
    issues = inv._stale_unenforced_candidate_issues(FIXTURE, source_root=ROOT)
    msg = inv.stale_unenforced_candidate_warning(issues, rep)
    assert msg is not None
    assert "open UNENFORCED row(s)" in msg
    assert "does NOT affect the exit code" in msg
    assert "L152" in msg


def test_main_writes_a_firing_advisory_to_stderr(monkeypatch, capsys):
    """The WIRING contract, made deterministic by monkeypatching the formatter: when the
    advisory fires, `--full` prints it to STDERR and still exits 0."""
    monkeypatch.setattr(
        inv, "stale_unenforced_candidate_warning",
        lambda issues, recall=None: "warning (non-gating): SENTINEL-STALE-ADVISORY",
    )
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "SENTINEL-STALE-ADVISORY" in captured.err
    assert "SENTINEL-STALE-ADVISORY" not in captured.out
    assert "invariants: all green" in captured.out


def test_advisory_absent_from_pre_edit_hook_mode(monkeypatch, capsys):
    # --pre-edit-hook: single-file/fast path, must never compute or print the advisory.
    payload = '{"tool_name": "Write", "tool_input": {"file_path": "x.py", "content": "a = 1\\n"}}'
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--pre-edit-hook"])
    monkeypatch.setattr(inv.sys, "stdin", __import__("io").StringIO(payload))
    rc = inv.main()
    out = capsys.readouterr()
    assert rc == 0
    assert "UNENFORCED" not in out.err


def test_advisory_absent_from_db_mode(monkeypatch, capsys, tmp_path):
    db = tmp_path / "t.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE t (x INTEGER)")
    con.commit()
    con.close()
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--db", str(db)])
    rc = inv.main()
    out = capsys.readouterr()
    assert rc == 0, out.err
    assert "UNENFORCED" not in out.err


def test_formatter_raising_cannot_flip_the_exit_code(monkeypatch, capsys):
    def boom(*_a, **_k):
        raise RuntimeError("advisory formatter exploded")

    monkeypatch.setattr(inv, "stale_unenforced_candidate_warning", boom)
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "could not be computed" in captured.err


def test_scan_never_raises_on_a_hostile_row(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L1 | 2026-07-01 | a | src | **UNENFORCED** -- `((((.py::[[[` `--` `.claude/agents/` "
        "`a.py` `--x` `((()))` |\n"
    )
    assert inv._stale_unenforced_candidate_issues(p, source_root=src) == []


# ─── Row splitting: pipes INSIDE a cell (2026-07-27 verifier, defect 2) ──────
#
# `line.split("|")` + `cols[5]` mis-aligned 14 of the real ledger's 190 rows, because those
# rows carry a pipe inside a cell — escaped (`\|`) or inside a backticked code span. For them
# `cols[5]` was a FRAGMENT OF THE LESSON TEXT, so their tier marker was never read at all.
# `cols[-2]` is not the fix either: L147's own ENFORCEMENT cell holds the escaped pipe, so the
# last-but-one field is that cell's TAIL with its `**invariant ...**` marker cut off.
#
# ALL OF THE FOLLOWING RUNS ON THE FROZEN SNAPSHOT, NEVER THE LIVE LEDGER (see module docstring):
# an enumeration of "which rows contain a pipe" is a statement about a live document's PROSE,
# and gating pytest on that is what forced a kb-distiller to reword its own lesson twice today.
# The live document's coverage is the content-independent structural pair further below.

# Frozen row census of `tests/fixtures/lessons_pipe_split_2026-07-27.md`.
FIXTURE_PIPES_N_ROWS = 49
FIXTURE_PIPES_N_PLAIN = 35  # 49 - 14; the naive rule must still agree on every one of these

# The enforcement column each of the 14 misparsed rows must now produce (verbatim prefix, as
# it appears at the END of that row in the frozen snapshot).
MISPARSED_14_ENFORCEMENT_PREFIX = {
    "L25": "**test / non-gating advisory (BUILT — superseded by L29, 2",
    "L37": "**ledger-only** — a prose-writing convention, not a code b",
    "L62": "**ledger-only** — generalizes L31 (stale-nominal quote) / ",
    "L89": "**test (this discriminator) + protocol (the general princi",
    "L109": "**non-gating advisory + test (BUILT; stale `UNENFORCED` ma",
    "L145": "**UNENFORCED — UNRESOLVED COLLISION, flagged to parent/Rya",
    "L147": "**invariant (non-gating advisory)** — new `scripts/invaria",
    "L161": "**tool (enforced) + test** — the same `scripts/tape_branch",
    "L173": "**test** — `tests/test_q48_s55_fomc_lag_probe.py::test_sta",
    "L177": "**test** — `tests/test_q48_s55_fomc_lag_probe.py::test_doc",
    "L179": "**test** — unchanged from L176 (`tests/test_q48_s55_fomc_l",
    "L180": "**CLOSED (2026-07-27, kalshi-edge-hunter Unit-3 probe-prep",
    "L183": "**test** — `tests/test_q48_s55_fomc_lag_probe.py::test_doc",
    "L184": "**test** — `tests/test_q48_s55_fomc_lag_probe.py::test_nor",
}


def test_frozen_pipe_fixture_is_the_snapshot_it_claims_to_be():
    """Guard the counterfactual's own population: the frozen snapshot must still hold 49 rows,
    14 of them the misparsing ones, so neither test below can go vacuous by fixture drift."""
    rows = inv._parse_lesson_rows(FIXTURE_PIPES)
    assert len(rows) == FIXTURE_PIPES_N_ROWS
    ids = [lid for lid, _lt, _enf in rows]
    assert len(set(ids)) == FIXTURE_PIPES_N_ROWS          # no duplicated row
    assert set(MISPARSED_14_ENFORCEMENT_PREFIX) <= set(ids)
    assert len(ids) - len(MISPARSED_14_ENFORCEMENT_PREFIX) == FIXTURE_PIPES_N_PLAIN


def test_the_fourteen_misparsed_rows_now_yield_their_enforcement_column():
    """Regression pin for defect 2, enumerated by ID on the FROZEN snapshot of the ledger. Each
    of these rows embeds a pipe in a cell; each must now parse to its REAL enforcement column."""
    parsed = {lid: enf for lid, _lt, enf in inv._parse_lesson_rows(FIXTURE_PIPES)}
    missing = [lid for lid in MISPARSED_14_ENFORCEMENT_PREFIX if lid not in parsed]
    assert missing == [], missing
    for lid, prefix in MISPARSED_14_ENFORCEMENT_PREFIX.items():
        assert parsed[lid].startswith(prefix), (lid, parsed[lid][:120])


def test_naive_pipe_split_really_does_break_those_rows():
    """The counterfactual, so the pin above cannot silently become a tautology: for every one
    of the 14, the OLD `line.split('|')[5]` rule disagrees with the correct column — and agrees
    on every one of the 35 ordinary rows, so the splitter did not just change everything.

    Runs on the FROZEN snapshot. It used to run on the live ledger, which made a green gate
    conditional on no future lesson row containing a literal `|` — the ledger is append-only and
    written by another agent, so that is a gate on prose, not on code (L192/L200)."""
    lessons = FIXTURE_PIPES.read_text().splitlines()
    naive = {}
    for line in lessons:
        m = inv._LESSON_ID_ROW_RE.match(line)
        if m:
            cols = line.split("|")
            if len(cols) >= 6:
                naive[m.group(1)] = cols[5].strip()
    parsed = {lid: enf for lid, _lt, enf in inv._parse_lesson_rows(FIXTURE_PIPES)}
    for lid in MISPARSED_14_ENFORCEMENT_PREFIX:
        assert naive.get(lid) != parsed[lid], lid
    # ...and agrees on a row with no embedded pipe (so the splitter did not change everything).
    plain = [lid for lid in parsed if lid not in MISPARSED_14_ENFORCEMENT_PREFIX]
    assert len(plain) == FIXTURE_PIPES_N_PLAIN
    assert all(naive.get(lid) == parsed[lid] for lid in plain)


# ─── The LIVE ledger's coverage: structure only, never prose ─────────────────

def _assert_ledger_is_wholly_parsed_and_never_truncated(path: pathlib.Path) -> int:
    """Content-INDEPENDENT structural contract, asserted over an entire ledger file.

    Two claims, both true of any prose whatsoever (including a row carrying a literal pipe as
    `\\|`, inside a code span, or bare and unescaped):

      1. NOTHING IS DROPPED — every line the row regex recognises as a lesson row survives into
         `_parse_lesson_rows`, and the splitter is lossless (rejoining its fields on `|`
         reproduces the line byte-for-byte).
      2. NOTHING IS TRUNCATED — each parsed enforcement cell starts at the head of the 5th cell
         (so a leading tier marker such as `**UNENFORCED**` / `**test**` can never be cut off,
         which is the `cols[-2]` failure) and runs to the end of the row (so a trailing residue
         cell can never be dropped, which is the `cols[5]` failure).

    Deliberately NOT asserted: `len(fields) == 7`. A row containing a BARE unescaped pipe splits
    into 8+ fields and `_parse_lesson_rows` handles it by rejoining (see
    `test_an_unknown_extra_pipe_never_truncates_the_marker`); reddening the gate for it would be
    the same "the test dictates what a lesson may say" coupling in a new costume. The floor used
    here is the parser's OWN admission threshold, `>= 6`, so anything the parser accepts, this
    accepts. Returns the row count, for the caller to use as it likes."""
    lines = path.read_text().splitlines()
    id_lines = [ln for ln in lines if inv._LESSON_ID_ROW_RE.match(ln)]
    rows = inv._parse_lesson_rows(path)
    assert len(rows) == len(id_lines), (len(rows), len(id_lines))  # (1) nothing dropped

    for line, (lid, _lt, enf) in zip(id_lines, rows):
        assert inv._LESSON_ID_ROW_RE.match(line).group(1) == lid   # row order preserved
        fields = inv._split_lesson_row(line)
        assert "|".join(fields) == line, lid                       # (1) lossless split
        assert len(fields) >= 6, (lid, len(fields))
        head = fields[5].strip()
        if head:
            assert enf, lid
            assert enf.startswith(head), (lid, head[:60], enf[:60])  # (2) head intact
            if head.startswith("**"):
                assert enf.startswith("**"), lid                     # tier marker intact
        tail = line.rstrip().rstrip("|").rstrip()
        assert tail.endswith(enf), (lid, enf[-60:])                  # (2) tail intact
    return len(rows)


def test_live_ledger_is_wholly_parsed_and_never_truncated():
    """The LIVE-tree coverage that replaces the frozen row enumeration above. Structural: it
    says nothing about which rows contain pipes, or about any row's words, so appending a lesson
    whose prose contains a literal `|` (in any shape) cannot turn it red."""
    n = _assert_ledger_is_wholly_parsed_and_never_truncated(LIVE_LEDGER)
    assert n >= 190  # append-only floor; 198 rows on 2026-07-27


def test_frozen_pipe_fixture_satisfies_the_same_structural_contract():
    """The same content-independent contract holds on the frozen snapshot — so the live check
    above is demonstrably a real constraint and not one that only ever sees well-behaved rows:
    the snapshot's 14 pipe-carrying rows pass it too."""
    assert _assert_ledger_is_wholly_parsed_and_never_truncated(FIXTURE_PIPES) == (
        FIXTURE_PIPES_N_ROWS
    )


def test_split_lesson_row_treats_escaped_pipe_as_literal(tmp_path):
    p = tmp_path / "00-lessons.md"
    p.write_text("| L1 | 2026-07-01 | a `SIGNATURE\\|TIMESTAMP` header | src | **UNENFORCED** x |\n")
    rows = inv._parse_lesson_rows(p)
    assert rows == [("L1", "a `SIGNATURE\\|TIMESTAMP` header", "**UNENFORCED** x")]


def test_split_lesson_row_treats_code_span_pipe_as_literal(tmp_path):
    p = tmp_path / "00-lessons.md"
    p.write_text("| L1 | 2026-07-01 | `sed 's|refs/heads/||'` | src | **UNENFORCED** y |\n")
    rows = inv._parse_lesson_rows(p)
    assert rows == [("L1", "`sed 's|refs/heads/||'`", "**UNENFORCED** y")]


def test_enforcement_cell_with_an_embedded_pipe_keeps_its_marker(tmp_path):
    """L147's shape: the pipe is inside the ENFORCEMENT cell itself, which is exactly where
    `cols[-2]` truncates the tier marker away."""
    p = tmp_path / "00-lessons.md"
    p.write_text("| L1 | 2026-07-01 | a | src | **UNENFORCED** — parses `\\| L<n> \\|` rows |\n")
    rows = inv._parse_lesson_rows(p)
    assert rows[0][2] == "**UNENFORCED** — parses `\\| L<n> \\|` rows"
    assert inv.stale_unenforced_recall_report(p).n_unenforced == 1


def test_an_unknown_extra_pipe_never_truncates_the_marker(tmp_path):
    """Defensive: a shape the splitter does not understand (a bare, unescaped, un-backticked
    pipe in the enforcement cell) must still preserve the leading tier marker — rejoined, not
    dropped. Truncating it is what made a whole row invisible to the queue."""
    p = tmp_path / "00-lessons.md"
    p.write_text("| L1 | 2026-07-01 | a | src | **UNENFORCED** — see a | b for context |\n")
    rows = inv._parse_lesson_rows(p)
    assert rows[0][2] == "**UNENFORCED** — see a | b for context"


# ─── The UNENFORCED marker: BOTH bold shapes (defect 3) ──────────────────────

def test_marker_matches_both_bold_shapes(tmp_path):
    """`**UNENFORCED**  ...` AND `**UNENFORCED  ...**` — L145's em dash sits INSIDE the bold
    span, which is how a genuinely-open row stayed invisible to the queue count."""
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L1 | 2026-07-01 | a | src | **UNENFORCED** — candidate: something |\n"
        "| L2 | 2026-07-01 | b | src | **UNENFORCED — UNRESOLVED COLLISION, flagged.** More. |\n"
    )
    rep = inv.stale_unenforced_recall_report(p)
    assert rep.n_unenforced == 2
    assert rep.open_unenforced_ids == ("L1", "L2")


def test_marker_is_precise_about_what_it_refuses(tmp_path):
    """Kept narrow on purpose: a mixed tier (L168's real shape, whose enforced half is real),
    a longer word, an underscore suffix, a mid-cell mention, and an UNBOLDED opener."""
    p = tmp_path / "00-lessons.md"
    p.write_text(
        "| L1 | 2026-07-01 | a | src | **test (detection) + UNENFORCED (repair)** — x |\n"
        "| L2 | 2026-07-01 | b | src | **UNENFORCEDISH** — x |\n"
        "| L3 | 2026-07-01 | c | src | **UNENFORCED_TIER** — x |\n"
        "| L4 | 2026-07-01 | d | src | **protocol** — still **UNENFORCED** in spirit |\n"
        "| L5 | 2026-07-01 | e | src | UNENFORCED — not a bold marker |\n"
    )
    rep = inv.stale_unenforced_recall_report(p)
    assert rep.n_rows == 5
    assert rep.n_unenforced == 0
    assert rep.open_unenforced_ids == ()


def test_frozen_l145_row_is_an_open_unenforced_row():
    """The row defect 3 surfaced: misparsed AND (once parsed) missed by the old
    `startswith('**UNENFORCED**')` test, because its em dash is inside the bold span. It was a
    genuinely open queue entry (an unresolved invariant collision flagged to Ryan).

    FROZEN, for two reasons: L145's openness is live ledger CONTENT another agent may legitimately
    change (one `DISPOSES: L145` append reds it), and its exact wording is prose. What is being
    pinned is the PARSER's behaviour on that row shape, which the snapshot preserves forever."""
    parsed = {lid: enf for lid, _lt, enf in inv._parse_lesson_rows(FIXTURE_PIPES)}
    enf = parsed["L145"]
    assert not enf.startswith("**UNENFORCED**")          # the old test's blind spot
    assert inv._UNENFORCED_MARKER_RE.match(enf)          # the widened one catches it
    rep = inv.stale_unenforced_recall_report(FIXTURE_PIPES, source_root=ROOT)
    assert "L145" in rep.open_unenforced_ids


# ─── DISPOSES: token boundaries (2026-07-27 verifier note) ───────────────────

def test_disposes_needs_a_left_word_boundary():
    assert inv._lesson_disposed_ids(_rows("XDISPOSES: L22")) == set()
    assert inv._lesson_disposed_ids(_rows("NON_DISPOSES: L22")) == set()
    assert inv._lesson_disposed_ids(_rows("**protocol** DISPOSES: L22")) == {"L22"}


def test_disposes_ids_need_a_right_word_boundary():
    assert inv._lesson_disposed_ids(_rows("DISPOSES: L22abc")) == set()
    assert inv._lesson_disposed_ids(_rows("DISPOSES: L22, L27abc")) == {"L22"}
    assert inv._lesson_disposed_ids(_rows("DISPOSES: L22.")) == {"L22"}


def test_frozen_disposition_row_is_read():
    """L188 (kb-distiller, 2026-07-27) formally disposes of 21 rows; the parser must see it.

    FROZEN: the snapshot carries L188 byte-identically, so the 21-ID claim is permanently
    reproducible. On the live ledger the same assertion is a claim about one row's WORDS —
    a reworded or superseded L188 would red the gate for a legitimate ledger edit."""
    rows = inv._parse_lesson_rows(FIXTURE_PIPES)
    disposed = inv._lesson_disposed_ids(rows)
    assert len(disposed) == 21
    assert {"L22", "L27", "L165"} <= disposed


def test_live_ledger_disposal_ids_are_well_formed():
    """LIVE companion, content-independent: whatever the ledger disposes of, every disposed ID
    has the canonical `L<digits>` grammar and no ID is simultaneously reported open. Asserts no
    particular ID and no count, so any append (including new `DISPOSES:` rows) keeps it green."""
    disposed = inv._lesson_disposed_ids(inv._parse_lesson_rows())
    assert all(re.fullmatch(r"L\d+", lid) for lid in disposed), sorted(disposed)
    rep = inv.stale_unenforced_recall_report()
    assert not (disposed & set(rep.open_unenforced_ids))


# ─── Evidence wording: claim only what was shown (defect 4, L76) ─────────────

def test_m1_evidence_claims_existence_not_enforcement(tmp_path):
    """L76's worked shape: the cell names a test that EXISTS, but whose body pins a different
    mechanism than the row asks for. The emitted evidence must not say "built"/"enforced"."""
    src = tmp_path / "src"
    (src / "tests").mkdir(parents=True)
    (src / "tests" / "test_x.py").write_text("def test_runs_fails_duration_gate():\n    pass\n")
    lessons = _ledger(
        tmp_path, "**UNENFORCED** -- `tests/test_x.py::test_runs_fails_duration_gate`",
        lesson_id="L76",
    )
    issues = inv._stale_unenforced_candidate_issues(lessons, source_root=src)
    assert len(issues) == 1
    ev = issues[0]
    assert "cell NAMES" in ev and "EXISTS in the tree" in ev
    assert "not proof it enforces L76" in ev
    for overclaim in ("already built", "is enforced", "enforcement exists", "is implemented"):
        assert overclaim not in ev


def test_warning_text_does_not_overclaim_and_cites_the_l76_coincidence():
    msg = inv.stale_unenforced_candidate_warning(
        ["L76: cell NAMES `t.py::x`, which EXISTS in the tree "
         "(name match only -- not proof it enforces L76)"]
    )
    assert msg is not None
    assert "NAME an artifact that EXISTS in the tree" in msg
    assert "never proof the enforcement is built" in msg
    assert "READ the named artifact before flipping" in msg
    assert "L76" in msg


def test_docstring_records_l76_as_the_name_coincidence_hazard():
    """Pin the KNOWN-HAZARDS block so the wording cannot regress to an over-claim."""
    doc = inv._stale_unenforced_candidate_issues.__doc__ or ""
    assert "NAME COINCIDENCE" in doc
    assert "L76" in doc
    assert "test_runs_single_deep_snapshot_fails_duration_gate" in doc
    assert "MIN_SNAPS" in doc
    assert "collapse_duration_gated_runs" in doc
    resolver_doc = inv._resolve_stale_candidate.__doc__ or ""
    assert "WORDING CONTRACT" in resolver_doc

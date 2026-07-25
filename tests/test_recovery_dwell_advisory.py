"""scripts/invariants.py — recovery-finding dwell advisory (L157 enforcement).

L157: "no collector-recovery finding may be filed without >=24 consecutive hours of the
expected signature bucket observed post-restart, and the finding MUST state the dwell it
actually observed" — with a named anchor. The lesson explicitly says this check "wants its own
constructed-negative corpus rather than a rushed regex", so that is what this file is:

  * a CONSTRUCTED-POSITIVE corpus (`_VIOLATION_SHAPES`) of realistic violation wordings that
    MUST fire — the recall evidence L155 demands, since 0/1 issues on the real tree only ever
    proves precision;
  * a CONSTRUCTED-NEGATIVE corpus (`_CLEAN_SHAPES`) of compliant/near-miss wordings that must
    NOT fire, including the supersession escape hatch;
  * a KNOWN-BLIND-SPOT corpus (`_BLIND_SPOT_SHAPES`) of genuine violations the rule
    deliberately MISSES, asserted as misses so that widening the rule has to delete an entry
    on purpose rather than by accident;
  * a HARD acceptance test over the REAL `findings/` tree: the 2026-07-22 recovery finding
    (independently known-defective — L157 exists because of it) must be flagged, and the
    07-21 / 07-25 collector findings must not;
  * exit-code pins: the advisory cannot change `invariants.py`'s exit code, no matter what.

All offline: `tmp_path` corpora and read-only reads of committed findings. No network, no git,
no subprocess, no wall-clock dependence.
"""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location(
        "inv_engine_recovery", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()


def _corpus(tmp_path: pathlib.Path, slug: str, body: str) -> pathlib.Path:
    d = tmp_path / slug
    d.mkdir()
    (d / f"{slug}.md").write_text(body, encoding="utf-8")
    return d


# ─── constructed POSITIVES: realistic violation shapes that must FIRE ───────
# (slug, body) — the slug matters: recovery-class membership reads the filename too.
_VIOLATION_SHAPES = [
    pytest.param(
        "2026-08-01-vps-collector-recovered",
        "# VPS collector recovered\n\nIt is producing tape again as of 2026-08-01T10:23Z.\n",
        id="plain-recovered-headline-no-dwell"),
    pytest.param(
        "2026-08-01-collector-back-online",
        "# The :23 collector leg is back online\n\nFresh pass at 2026-08-01T10:23:04Z.\n",
        id="back-online"),
    pytest.param(
        "2026-08-01-vps-cron-restored",
        "# VPS cron restored after PR #9\n\nSeen at 2026-08-01T10:23Z.\n",
        id="restored"),
    pytest.param(
        "2026-08-01-capture-alive-again",
        "# Weather capture is alive again\n\nOne pass observed.\n",
        id="alive-again-no-timestamps-at-all"),
    pytest.param(
        "2026-08-01-tape-feed-resumed",
        "# Sports tape feed resumed\n\nBack at 2026-08-01T10:23Z.\n",
        id="resumed"),
    pytest.param(
        "2026-08-01-collector-self-healed",
        "# Hourly pass self-healed overnight\n\nTwo passes seen.\n",
        id="self-healed"),
    pytest.param(
        "2026-08-01-collector-no-longer-dead",
        "# The vps leg is no longer dead\n\nfresh line at 2026-08-01T10:23Z\n",
        id="no-longer-dead"),
    pytest.param(
        "2026-08-01-vps-collector-revived",
        "# VPS collector revived post-reboot\n\nOne fresh pass.\n",
        id="revived"),
    pytest.param(
        "2026-08-01-collector-green-again",
        "# Collector cadence is green again\n\nOne pass at 2026-08-01T10:23Z.\n",
        id="green-again"),
    pytest.param(
        "2026-08-01-nightly-sweep-leg-came-back",
        "# Nightly sweep: the :23 leg came back\n\nOne pass.\n",
        id="came-back"),
    pytest.param(
        "2026-08-01-collector-recovery-confirmed",
        "# Collector recovery confirmed\n\nDwell observed: 12h consecutive since "
        "2026-08-01T00:00Z.\n",
        id="dwell-below-threshold-12h"),
    pytest.param(
        "2026-08-01-collector-recovered-days",
        "# Collector recovered\n\nWe observed 2 days of consecutive :23 passes since "
        "2026-07-30T22:41Z.\n",
        id="dwell-stated-in-DAYS-not-hours"),
    pytest.param(
        "2026-08-01-collector-recovered-minutes",
        "# Collector recovered\n\n1800 minutes of uninterrupted cadence since "
        "2026-07-30T22:41Z.\n",
        id="dwell-stated-in-MINUTES"),
    pytest.param(
        "2026-08-01-collector-recovered-prose-duration",
        "# Collector recovered\n\nIt has now been running for just over a day without a gap, "
        "since 2026-07-30T22:41Z.\n",
        id="prose-duration-just-over-a-day"),
    pytest.param(
        "2026-08-01-collector-recovered-table",
        "# Collector recovered\n\n| metric | value |\n| --- | --- |\n| dwell | 30 |\n"
        "| unit | hours |\n\nanchor 2026-07-30T22:41Z\n",
        id="dwell-split-across-table-cells"),
    pytest.param(
        "2026-08-01-collector-recovered-outage-hours-only",
        "# Collector recovered\n\nThe outage lasted 61.7h.\n\nIt is producing again as of "
        "2026-08-01T10:23Z.\n",
        id="hours-quoted-but-it-is-the-OUTAGE-not-a-dwell"),
    pytest.param(
        "2026-08-01-collector-recovered-relative-anchor",
        "# Collector recovered\n\n36h of consecutive :23-bucket passes observed since the "
        "restart.\n\nThe restart happened on 2026-07-30 (see timeline).\n",
        id="dwell-ok-anchor-is-a-relative-phrase-plus-bare-date"),
    pytest.param(
        "2026-08-01-collector-recovered-distant-anchor",
        "# Collector recovered\n\n30h of consecutive passes observed.\n\nfiller\nfiller\n"
        "filler\nfiller\n\nThe restart was at 2026-07-30T22:41Z.\n",
        id="dwell-ok-anchor-eight-lines-away"),
]


@pytest.mark.parametrize("slug,body", _VIOLATION_SHAPES)
def test_advisory_fires_on_tested_violation_shapes(tmp_path, slug, body):
    issues = inv._recovery_dwell_issues(findings_dir=_corpus(tmp_path, slug, body))
    assert issues, f"{slug} should be flagged as an L157 violation"
    assert len(issues) == 1
    assert slug in issues[0][0]
    assert issues[0][1], "the reason string must name what is missing"
    msg = inv.recovery_dwell_warning(issues)
    assert msg and "L157" in msg and "does NOT affect the exit code" in msg


def test_reason_names_which_half_is_missing():
    """L157 has two halves; the advisory says which one failed, not just 'bad'."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = pathlib.Path(d)
        (p / "2026-08-01-collector-recovered.md").write_text(
            "# Collector recovered\n\n30h of consecutive passes observed.\n\nfiller\nfiller\n"
            "filler\nfiller\n\nRestart: 2026-07-30T22:41Z.\n", encoding="utf-8")
        (rel, why), = inv._recovery_dwell_issues(findings_dir=p)
        assert "no named anchor" in why
        assert "no stated dwell" not in why      # the dwell half PASSED, say so

        (p / "2026-08-01-collector-recovered.md").write_text(
            "# Collector recovered\n\nOne fresh pass, no dwell measured.\n", encoding="utf-8")
        (rel, why), = inv._recovery_dwell_issues(findings_dir=p)
        assert "no stated dwell of >= 24h" in why
        assert "no named anchor (no UTC timestamp anywhere in the finding)" in why


# ─── constructed NEGATIVES: compliant / near-miss shapes that must NOT fire ──

_CLEAN_SHAPES = [
    pytest.param(
        "2026-08-01-collector-recovered-compliant",
        "# Collector recovered\n\n36.2h of consecutive :23-bucket passes observed since "
        "2026-07-30T22:41Z (anchor = first post-restart pass).\n",
        id="compliant-dwell-and-anchor-same-line"),
    pytest.param(
        "2026-08-01-collector-recovered-compliant-split",
        "# Collector recovered\n\nAnchor: 2026-07-30T22:41Z (declared restart moment).\n"
        "Dwell: 48h uninterrupted.\n",
        id="compliant-anchor-one-line-above-the-dwell"),
    pytest.param(
        "2026-08-01-collector-recovered-exactly-24h",
        "# Collector recovered\n\n24h of unbroken :23 cadence since 2026-07-30T22:41Z.\n",
        id="compliant-exactly-at-the-24h-threshold"),
    pytest.param(
        "2026-08-01-vps-collector-second-death",
        "# VPS collector's SECOND death (61.7h silent, unnoticed)\n\nDeclared RECOVERED three "
        "days ago; the recovery dwelled 18.8h from 2026-07-21T22:41Z before it died again.\n",
        id="negative-recovery-only-in-body-headline-is-a-death"),
    pytest.param(
        "2026-08-01-vps-collector-day3-still-down",
        "# VPS collector still dead on day 3\n\nNo recovery in sight; still zero VPS-signature "
        "lines.\n",
        id="negative-recovery-word-in-body-headline-says-dead"),
    pytest.param(
        "2026-08-01-q21-idea-gen-round",
        "# Q21 idea-gen round\n\nOne idea is to recover the stranded tape branches.\n",
        id="negative-unrelated-finding-with-recover-in-body"),
    pytest.param(
        "2026-08-01-stranded-tape-recovery-tooling",
        "# Stranded tape recovery tooling\n\nA branch sweep tool, not a recovery verdict.\n",
        id="near-miss-recovery-TOOLING-is-not-a-recovery-verdict"),
    pytest.param(
        "2026-08-01-collector-recovered-superseded",
        "# Collector recovered\n\nSUPERSEDED by L157 / "
        "findings/2026-07-25-vps-collector-second-death.md\n\nOne fresh pass, no dwell.\n",
        id="escape-hatch-superseded-marker"),
    pytest.param(
        "2026-08-01-collector-recovered-retracted",
        "# Collector recovered\n\n> **RETRACTED** — see findings/2026-07-25-second-death.md\n\n"
        "One fresh pass.\n",
        id="escape-hatch-retracted-behind-blockquote-and-bold"),
]


@pytest.mark.parametrize("slug,body", _CLEAN_SHAPES)
def test_advisory_stays_quiet_on_clean_shapes(tmp_path, slug, body):
    assert inv._recovery_dwell_issues(findings_dir=_corpus(tmp_path, slug, body)) == []


def test_escape_hatch_is_narrow(tmp_path):
    """Ordinary prose mentioning supersession must NOT silence the check — the marker has to be
    ALL-CAPS, at the start of a line, near the top, AND name what supersedes it."""
    prose = ("# Collector recovered\n\nThis supersedes the confidence of L129, though the "
             "observations stand.\n\nOne fresh pass.\n")
    assert inv._recovery_dwell_issues(findings_dir=_corpus(tmp_path, "a-collector-recovered", prose))

    no_ref = "# Collector recovered\n\nSUPERSEDED (details elsewhere)\n\nOne fresh pass.\n"
    assert inv._recovery_dwell_issues(findings_dir=_corpus(tmp_path, "b-collector-recovered", no_ref))

    buried = ("# Collector recovered\n\n" + "filler\n" * 45 +
              "SUPERSEDED by L157\n")
    assert inv._recovery_dwell_issues(findings_dir=_corpus(tmp_path, "c-collector-recovered", buried))


# ─── deliberate, regression-tested BLIND SPOTS (L155's honest-hole rule) ────
# These ARE genuine L157 violations that the rule does not catch. Each is a documented
# precision/scope trade-off, not an oversight; widening the rule must delete an entry here
# ON PURPOSE. Measured recall over the full 22-shape adversarial corpus: 18/22.

_BLIND_SPOT_SHAPES = [
    pytest.param(
        "2026-08-01-collector-cron-is-fixed",
        "# The VPS collector cron is fixed\n\nOne pass at 2026-08-01T10:23Z.\n",
        id="blind-repair-verb-fixed"),
    pytest.param(
        "2026-08-01-collector-cron-repaired",
        "# VPS collector cron repaired\n\nOne pass at 2026-08-01T10:23Z.\n",
        id="blind-repair-verb-repaired"),
    pytest.param(
        "2026-08-01-collector-status-update",
        "# Collector status update\n\n## The leg has recovered\n\nOne pass at "
        "2026-08-01T10:23Z.\n",
        id="blind-recovery-claim-only-in-an-H2"),
    pytest.param(
        "2026-08-01-collector-recovered-mixed-line",
        "# Collector recovered\n\nThe 61.7h outage is over and the leg has been stable since "
        "2026-08-01T10:23Z.\n",
        id="blind-outage-hours-and-dwell-word-share-one-line"),
]


@pytest.mark.parametrize("slug,body", _BLIND_SPOT_SHAPES)
def test_known_blind_spots_are_misses(tmp_path, slug, body):
    assert inv._recovery_dwell_issues(findings_dir=_corpus(tmp_path, slug, body)) == [], (
        "this shape is a DOCUMENTED miss; if it now fires, delete it from _BLIND_SPOT_SHAPES "
        "and add it to _VIOLATION_SHAPES on purpose")


def test_warning_message_states_its_blind_spots_not_its_intent():
    """L155: the advisory must advertise TESTED coverage, so a reader does not assume a clean
    report means the class is guarded."""
    msg = inv.recovery_dwell_warning([("findings/x.md", "no stated dwell of >= 24h")])
    assert "KNOWN BLIND SPOTS" in msg and "COVERAGE" in msg
    assert "18/22" in msg
    for token in ("repair", "H2", "OUTAGE"):
        assert token in msg


# ─── robustness: nothing here can raise ─────────────────────────────────────

def test_absent_findings_dir_is_silent(tmp_path):
    assert inv._recovery_dwell_issues(findings_dir=tmp_path / "nope") == []
    assert inv.recovery_dwell_warning([]) is None


def test_subdirectories_and_non_markdown_are_ignored(tmp_path):
    (tmp_path / "observatory").mkdir()
    (tmp_path / "observatory" / "2026-08-01-collector-recovered.md").write_text(
        "# Collector recovered\n", encoding="utf-8")
    (tmp_path / "2026-08-01-collector-recovered.json").write_text("{}", encoding="utf-8")
    assert inv._recovery_dwell_issues(findings_dir=tmp_path) == []


def test_undecodable_bytes_do_not_crash(tmp_path):
    (tmp_path / "2026-08-01-collector-recovered.md").write_bytes(
        b"# Collector recovered\n\n\xff\xfe not utf-8 \x00\n")
    issues = inv._recovery_dwell_issues(findings_dir=tmp_path)
    assert len(issues) == 1     # degrades to replacement chars, still classified


def test_headline_reads_slug_and_h1_only():
    lines = ["---", "front: matter", "# VPS collector recovered", "body recovered text"]
    h = inv._recovery_headline(pathlib.Path("/x/2026-08-01-vps-collector-recovered.md"), lines)
    assert "vps collector recovered" in h and "# VPS collector recovered"[2:] in h
    assert "body recovered text" not in h


# ─── HARD acceptance over the REAL findings/ tree ───────────────────────────

_REAL_FINDINGS = ROOT / "findings"
_real = pytest.mark.skipif(not _REAL_FINDINGS.is_dir(), reason="findings/ not present")

_KNOWN_DEFECTIVE = "findings/2026-07-22-vps-collector-recovered-post-pr151.md"
_MUST_NOT_FIRE = (
    "findings/2026-07-21-vps-collector-day3-still-down.md",
    "findings/2026-07-25-vps-collector-second-death-and-cloud-slot-attrition.md",
)


@_real
def test_acceptance_real_tree_flags_the_known_defective_recovery_finding():
    """The 2026-07-22 finding is the true positive L157 was written about: it declared the VPS
    leg RECOVERED on a single fresh pass, with no dwell number. Firing on a real,
    independently-known-defective artifact is the recall evidence L155 asks for."""
    issues = dict(inv._recovery_dwell_issues(findings_dir=_REAL_FINDINGS))
    assert _KNOWN_DEFECTIVE in issues, issues
    assert "no stated dwell" in issues[_KNOWN_DEFECTIVE]


@_real
@pytest.mark.parametrize("rel", _MUST_NOT_FIRE)
def test_acceptance_real_tree_does_not_flag_the_non_recovery_collector_findings(rel):
    """Precision pin with a REASON, not just a zero: neither finding claims recovery in its
    HEADLINE (07-21 = "still dead on day 3", 07-25 = "SECOND death"), so neither is
    recovery-class — even though 07-25's body quotes an 18.8h dwell that is BELOW the 24h bar
    and would fire if the headline matcher leaked into the body."""
    path = ROOT / rel
    lines = path.read_text(encoding="utf-8").splitlines()
    headline = inv._recovery_headline(path, lines)
    assert not inv._RECOVERY_TERM_RE.search(headline), headline
    assert rel not in dict(inv._recovery_dwell_issues(findings_dir=_REAL_FINDINGS))


@_real
def test_acceptance_exactly_one_real_finding_is_recovery_class():
    """The headline-only scoping claim, pinned against the real corpus: 1 headline recovery
    claim vs 16 findings with "recover" somewhere in the body (2026-07-25 census). A body-wide
    matcher would be ~16x less precise — and would fire hardest on the findings CORRECTING a
    bad recovery claim."""
    md = sorted(_REAL_FINDINGS.glob("*.md"))
    recovery_class = [
        p.name for p in md
        if inv._RECOVERY_TERM_RE.search(inv._recovery_headline(p, p.read_text(
            encoding="utf-8", errors="replace").splitlines()))
        and inv._RECOVERY_SUBJECT_RE.search(inv._recovery_headline(p, p.read_text(
            encoding="utf-8", errors="replace").splitlines()))
    ]
    assert recovery_class == ["2026-07-22-vps-collector-recovered-post-pr151.md"], recovery_class
    body_hits = [p.name for p in md if "recover" in p.read_text(
        encoding="utf-8", errors="replace").lower()]
    assert len(body_hits) >= 10, "the body-wide precision hazard this scoping avoids"


# ─── the advisory can NEVER change the exit code ────────────────────────────

def _stub_expensive_checks(monkeypatch):
    """Neuter every OTHER whole-tree/whole-tape scan in main()'s --full branch so these
    exit-code tests are fast. The recovery-dwell path under test is left fully real."""
    monkeypatch.setattr(inv, "scan_tree", lambda *a, **k: [])
    for name in ("_git_tape_refs", "_tape_dir_shape_issues",
                 "_tape_dir_shape_orphan_classification", "_daily_family_gap_issues",
                 "_unregistered_single_hour_leg_issues", "_raw_datetime_fromisoformat_sites",
                 "_ladder_size_coercion_issues", "_duplicate_lesson_id_issues",
                 "_stale_unenforced_candidate_issues", "_tape_conflict_marker_issues",
                 "_tape_invalid_jsonl_issues"):
        monkeypatch.setattr(inv, name, lambda *a, **k: [])
    monkeypatch.setattr(inv, "_dead_collector_leg_diagnosis", lambda *a, **k: None)


def _run_main(monkeypatch) -> int:
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    return inv.main()


def test_real_firing_advisory_still_exits_zero(monkeypatch, capsys):
    """Control + the load-bearing property: the advisory DOES fire on the real tree today, and
    the run still exits 0."""
    _stub_expensive_checks(monkeypatch)
    assert _run_main(monkeypatch) == 0
    assert "recovery-class finding(s)" in capsys.readouterr().err


def test_detector_that_raises_does_not_change_the_exit_code(monkeypatch, capsys):
    _stub_expensive_checks(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("detector blew up")

    monkeypatch.setattr(inv, "_recovery_dwell_issues", _boom)
    assert _run_main(monkeypatch) == 0
    assert "recovery-dwell advisory could not be computed" in capsys.readouterr().err


def test_formatter_returning_a_non_str_does_not_change_the_exit_code(monkeypatch, capsys):
    """`warning + "\\n"` on a non-str is a TypeError at the CALL SITE, outside any guard the
    formatter itself could carry."""
    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "recovery_dwell_warning", lambda _i: 7)
    assert _run_main(monkeypatch) == 0
    assert "recovery-dwell advisory could not be computed" in capsys.readouterr().err


def test_base_exception_in_the_advisory_path_does_not_change_the_exit_code(monkeypatch, capsys):
    def _sys_exit(*a, **k):
        raise SystemExit(3)

    _stub_expensive_checks(monkeypatch)
    monkeypatch.setattr(inv, "recovery_dwell_warning", _sys_exit)
    assert _run_main(monkeypatch) == 0
    assert "recovery-dwell advisory could not be computed" in capsys.readouterr().err


def test_advisory_is_non_gating_by_construction():
    """`main()` writes it to stderr and never appends it to `failures` (the gating list)."""
    src = (ROOT / "scripts" / "invariants.py").read_text(encoding="utf-8")
    i = src.index("dwell_warning = recovery_dwell_warning(")
    block = src[i:i + 400]
    assert "sys.stderr.write(dwell_warning" in block
    assert "failures.append(dwell_warning" not in src
    assert "failures.append(recovery_dwell_warning" not in src


def test_advisory_path_touches_no_network_or_subprocess():
    """Offline contract: the detector reads files only."""
    import inspect
    src = inspect.getsource(inv._recovery_dwell_issues) + inspect.getsource(inv._recovery_headline)
    # dotted/call forms, so the docstring's own prose ("no network, no git, no subprocess")
    # does not trip the check
    for banned in ("subprocess.", "requests.", "urllib.", "socket.", "os.popen", "os.system"):
        assert banned not in src

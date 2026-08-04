"""The Hard-Rule invariant engine fires on violations, exempts the sanctioned sites, and
finds the real tree clean. These are adversarial fixtures by design (this file is on the
engine's EXCLUDE_FILES list so its own banned-pattern strings don't self-trip)."""
from __future__ import annotations

import importlib.util
import pathlib
import sqlite3

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_engine():
    spec = importlib.util.spec_from_file_location("inv_engine", ROOT / "scripts" / "invariants.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


inv = _load_engine()

# A path that is NOT any sanctioned site or excluded file — a generic runtime module.
GENERIC = ROOT / "some_runtime_module.py"

VIOLATIONS = {
    "no_gefs": 'MODELS = ["gfs_seamless", "ncep_gefs025"]',
    "no_bare_pstdev": "spread = pstdev(members)",
    "no_pstdev_import": "from statistics import pstdev",
    "no_yes_ask_arithmetic": "p = yes_ask / bracket_sum",
    "no_static_rho_point_four": "rho = 0.4",
    "no_handrolled_fee_rate": "FEE_RATE = 0.07",
    "no_http_server": "from fastapi import FastAPI",
    "order_endpoints_confined": "resp = client.place_order(ticker, px, qty)",
    "risk_caps_sanctioned": "MAX_CONTRACTS_PER_ORDER = 500",
}


@pytest.mark.parametrize("rule,snippet", list(VIOLATIONS.items()))
def test_each_rule_fires_on_a_violation(rule, snippet):
    failures = inv.scan_text(GENERIC, snippet)
    assert any(f"[{rule}]" in f for f in failures), f"{rule} did not fire on: {snippet!r}\n{failures}"


def test_clean_text_passes():
    assert inv.scan_text(GENERIC, "x = 1 + 2\nreturn x\n") == []


def test_pstdev_exempt_in_sanctioned_stats_site():
    # core/stats.py is the one home allowed to call pstdev (behind safe_pstdev's n>=4 guard)
    assert inv.scan_text(ROOT / "core" / "stats.py", "v = pstdev(values)") == []


def test_yes_ask_arithmetic_exempt_in_sanctioned_pricing_site():
    # core/pricing.py is the one home allowed to do yes_ask/bracket_sum arithmetic
    assert inv.scan_text(ROOT / "core" / "pricing.py", "p = yes_ask / bracket_sum") == []


def test_sentinel_line_is_skipped():
    line = "MODELS = ['ncep_gefs025']  # inv-pattern-def"
    assert inv.scan_text(GENERIC, line) == []


# ─── no_handrolled_fee_rate (L5) ──────────────────────────────────────────────

@pytest.mark.parametrize("snippet", [
    "FEE_RATE = 0.07",                       # taker constant, name-bound
    "MAKER_FEE_RATE = 0.0175",               # maker constant, name-bound
    "SP500_FEE_RATE = 0.035",                # sp500/ndx constant, name-bound
    "FEE_COEFF = 0.07",                       # coeff token as trailing segment
    "SP500_NDX_FEE_RATE = 0.035",             # multi-segment name with digits still fires
    "fee = fee_per_contract(bid, rate=0.0175)",  # rate= kwarg binding
    "f = fee_per_contract(p, 0.07)",         # positional literal into a fee call
    "rate: float = 0.07",                    # annotated default (the sports_history shape)
])
def test_fee_rate_rule_fires(snippet):
    failures = inv.scan_text(GENERIC, snippet)
    assert any("[no_handrolled_fee_rate]" in f for f in failures), (snippet, failures)


def test_fee_rate_rule_exempt_in_sanctioned_pricing_site():
    # core/pricing.py is the single home of the fee-schedule rate constants.
    assert inv.scan_text(ROOT / "core" / "pricing.py", "TAKER_FEE_RATE = 0.07") == []


def test_fee_rate_rule_skips_comment_lines():
    # A commented example must not trip the rule (parity with the rho rule's comment guard).
    assert inv.scan_text(GENERIC, "    # rate = 0.07 is the taker rate") == []


@pytest.mark.parametrize("snippet", [
    "MAKER_FEE = 0.0035",                    # longshot's modeling haircut, NOT a schedule rate
    "fee = fee_per_contract(0.07)",          # 0.07 here is the PRICE (first positional arg)
    "rate = core.pricing.TAKER_FEE_RATE",    # bound to the constant, not a literal
])
def test_fee_rate_rule_silent_on_non_schedule_uses(snippet):
    assert not any("[no_handrolled_fee_rate]" in f for f in inv.scan_text(GENERIC, snippet))


@pytest.mark.parametrize("snippet", [
    "accurate = 0.07",                       # 'rate' is a substring, not a token segment
    "coffee = 0.035",                        # 'fee' is a substring, not a token segment
    "separate = 0.0175",                     # 'rate' substring
    "generate = 0.07",                       # 'rate' substring
    "moderate = 0.035",                      # 'rate' substring
    "corporate = 0.07",                      # 'rate' substring
])
def test_fee_rate_rule_silent_on_benign_substring_names(snippet):
    # pattern A is token-delimited: fee/rate/coeff must be a whole underscore-delimited
    # segment, so identifiers that merely CONTAIN the substring must not fire (verifier catch).
    assert not any("[no_handrolled_fee_rate]" in f for f in inv.scan_text(GENERIC, snippet))


# ─── stranded-tape warning (L17: non-gating advisory) ─────────────────────────

def test_stranded_tape_warning_none_when_empty():
    assert inv.stranded_tape_warning([]) is None


def test_stranded_tape_warning_message_content():
    msg = inv.stranded_tape_warning(["origin/tape/hourly-20260706T1255Z"])
    assert msg is not None
    assert "origin/tape/hourly-20260706T1255Z" in msg
    assert "non-gating" in msg
    assert "0b" in msg


def test_git_tape_refs_returns_list_without_raising():
    refs = inv._git_tape_refs()
    assert isinstance(refs, list)
    assert all(isinstance(r, str) for r in refs)


def test_stranded_tape_warning_never_gates_exit_code(monkeypatch, capsys):
    # Even with stranded refs present, a clean tree must still exit 0 — warnings never gate.
    monkeypatch.setattr(inv, "_git_tape_refs", lambda: ["origin/tape/hourly-FAKE"])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "invariants: all green" in captured.out


def test_real_tree_is_green():
    assert inv.scan_tree() == [], "the committed tree must satisfy every Hard Rule"


# ─── tape dir-shape warning (L25: non-gating advisory) ────────────────────────

def test_tape_dir_shape_warning_none_when_empty():
    assert inv.tape_dir_shape_warning([]) is None


def test_tape_dir_shape_warning_message_content():
    msg = inv.tape_dir_shape_warning(["crypto_hourly/dt=2026-07-10"])
    assert msg is not None
    assert "crypto_hourly/dt=2026-07-10" in msg
    assert "non-gating" in msg
    assert "L25" in msg


def test_tape_dir_shape_issues_finds_directories(tmp_path):
    tape_root = tmp_path / "tape"
    (tape_root / "crypto_hourly").mkdir(parents=True)
    (tape_root / "crypto_hourly" / "dt=2026-07-03.jsonl").write_text("{}\n")
    (tape_root / "crypto_hourly" / "dt=2026-07-10").mkdir()
    (tape_root / "sports_pairs").mkdir()
    (tape_root / "sports_pairs" / "dt=2026-07-09").mkdir()
    issues = inv._tape_dir_shape_issues(tape_root)
    assert issues == ["crypto_hourly/dt=2026-07-10", "sports_pairs/dt=2026-07-09"]


def test_tape_dir_shape_issues_clean_tree_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    (tape_root / "crypto_hourly").mkdir(parents=True)
    (tape_root / "crypto_hourly" / "dt=2026-07-03.jsonl").write_text("{}\n")
    assert inv._tape_dir_shape_issues(tape_root) == []


def test_tape_dir_shape_issues_missing_tape_root_is_empty(tmp_path):
    assert inv._tape_dir_shape_issues(tmp_path / "does-not-exist") == []


def test_tape_dir_shape_warning_never_gates_exit_code(monkeypatch, capsys):
    # Even with real shape issues present, a clean source tree must still exit 0.
    monkeypatch.setattr(inv, "_tape_dir_shape_issues", lambda: ["fake_family/dt=2026-01-01"])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "fake_family/dt=2026-01-01" in captured.err
    assert "invariants: all green" in captured.out


# ─── dir-shape orphan GC classification (L109: non-gating advisory) ───────────

def test_orphan_classification_superseded_when_canonical_file_coexists(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "sports_pairs"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-10").mkdir()
    (fam / "dt=2026-07-10.jsonl").write_text("{}\n")
    (fam / "dt=2026-07-11.jsonl").write_text("{}\n")
    out = inv._tape_dir_shape_orphan_classification(tape_root)
    assert out == [("sports_pairs/dt=2026-07-10", "superseded")]


def test_orphan_classification_unrecoverable_when_no_canonical_file_and_collection_moved_on(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "sports_pairs"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-09").mkdir()
    (fam / "dt=2026-07-11.jsonl").write_text("{}\n")
    out = inv._tape_dir_shape_orphan_classification(tape_root)
    assert out == [("sports_pairs/dt=2026-07-09", "unrecoverable")]


def test_orphan_classification_unclassified_when_directory_is_the_newest_day(tmp_path):
    # Collection may still be mid-write for the newest day — never flag it for GC/backfill.
    tape_root = tmp_path / "tape"
    fam = tape_root / "sports_pairs"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-11.jsonl").write_text("{}\n")
    (fam / "dt=2026-07-12").mkdir()
    out = inv._tape_dir_shape_orphan_classification(tape_root)
    assert out == []


def test_orphan_classification_clean_tree_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    (tape_root / "crypto_hourly").mkdir(parents=True)
    (tape_root / "crypto_hourly" / "dt=2026-07-03.jsonl").write_text("{}\n")
    assert inv._tape_dir_shape_orphan_classification(tape_root) == []


def test_orphan_classification_missing_tape_root_is_empty(tmp_path):
    assert inv._tape_dir_shape_orphan_classification(tmp_path / "does-not-exist") == []


def test_orphan_warning_none_when_empty():
    assert inv.tape_dir_shape_orphan_warning([]) is None


def test_orphan_warning_message_content():
    msg = inv.tape_dir_shape_orphan_warning([
        ("sports_pairs/dt=2026-07-10", "superseded"),
        ("sports_pairs/dt=2026-07-09", "unrecoverable"),
    ])
    assert msg is not None
    assert "SUPERSEDED" in msg
    assert "UNRECOVERABLE" in msg
    assert "sports_pairs/dt=2026-07-10" in msg
    assert "sports_pairs/dt=2026-07-09" in msg
    assert "L109" in msg


def test_orphan_warning_never_gates_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(inv, "_tape_dir_shape_orphan_classification",
                         lambda: [("fake_family/dt=2026-01-01", "unrecoverable")])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "UNRECOVERABLE" in captured.err
    assert "invariants: all green" in captured.out


def test_orphan_classification_matches_real_committed_tree():
    # Ground-truth regression for the exact L109 finding: sports_pairs' dt=2026-07-10
    # directory coexists with a canonical file (superseded); dt=2026-07-02/07-09 have none
    # and collection has since moved on (unrecoverable).
    out = dict(inv._tape_dir_shape_orphan_classification())
    assert out.get("sports_pairs/dt=2026-07-10") == "superseded"
    assert out.get("sports_pairs/dt=2026-07-02") == "unrecoverable"
    assert out.get("sports_pairs/dt=2026-07-09") == "unrecoverable"


# ─── daily-cadence family gap warning (L74: non-gating advisory) ──────────────

def test_daily_family_gap_warning_none_when_empty():
    assert inv.daily_family_gap_warning([]) is None


def test_daily_family_gap_warning_message_content():
    msg = inv.daily_family_gap_warning(["econ_prints/dt=2026-07-09"])
    assert msg is not None
    assert "econ_prints/dt=2026-07-09" in msg
    assert "non-gating" in msg
    assert "L74" in msg


def test_daily_family_gap_issues_finds_gap(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-05.jsonl").write_text("{}\n")
    (fam / "dt=2026-07-08.jsonl").write_text("{}\n")
    issues = inv._daily_family_gap_issues(tape_root, families=("econ_prints",))
    assert issues == ["econ_prints/dt=2026-07-06", "econ_prints/dt=2026-07-07"]


def test_daily_family_gap_issues_clean_run_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "anomalies"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-05.jsonl").write_text("{}\n")
    (fam / "dt=2026-07-06.jsonl").write_text("{}\n")
    (fam / "dt=2026-07-07.jsonl").write_text("{}\n")
    assert inv._daily_family_gap_issues(tape_root, families=("anomalies",)) == []


def test_daily_family_gap_issues_single_file_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-05.jsonl").write_text("{}\n")
    assert inv._daily_family_gap_issues(tape_root, families=("econ_prints",)) == []


def test_daily_family_gap_issues_missing_family_dir_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    tape_root.mkdir()
    assert inv._daily_family_gap_issues(tape_root, families=("econ_prints",)) == []


def test_daily_family_gap_issues_missing_tape_root_is_empty(tmp_path):
    assert inv._daily_family_gap_issues(tmp_path / "does-not-exist") == []


def test_daily_family_gap_issues_treats_dir_shaped_dt_entry_as_missing(tmp_path):
    # A dt=<date>.jsonl DIRECTORY (L25 shape issue) is not a parseable file, so its day
    # correctly surfaces as a gap here too, rather than being silently counted as present.
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-05.jsonl").write_text("{}\n")
    (fam / "dt=2026-07-06.jsonl").mkdir()
    (fam / "dt=2026-07-07.jsonl").write_text("{}\n")
    issues = inv._daily_family_gap_issues(tape_root, families=("econ_prints",))
    assert issues == ["econ_prints/dt=2026-07-06"]


def test_daily_family_gap_warning_never_gates_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(inv, "_daily_family_gap_issues", lambda: ["fake_family/dt=2026-01-02"])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "fake_family/dt=2026-01-02" in captured.err
    assert "L74" in captured.err
    assert "invariants: all green" in captured.out


def test_daily_cadence_families_includes_weather_actuals():
    # L126: weather_actuals is gated to a single fixed UTC hour (12) with no retry/backfill,
    # the same failure shape L74 already covers for anomalies/econ_prints/polymarket_cpi_pairs
    # — it was simply never added to the tracked tuple, so its own gap was invisible.
    assert "weather_actuals" in inv.DAILY_CADENCE_FAMILIES


def test_acceptance_l126_weather_actuals_real_gap_detected():
    # HARD acceptance test anchored to the REAL committed tape (mirrors L75's live-validation
    # posture): tape/weather_actuals/ has files for 07-16/07-17/07-18/07-21 but is MISSING
    # 07-19 and 07-20 — a real 2-day hole caused by the live collector's post-VPS-death cron
    # phase never landing on hour 12. Before L126 this family wasn't in DAILY_CADENCE_FAMILIES
    # at all, so the gap was invisible to this detector; this pins that it's caught now.
    issues = inv._daily_family_gap_issues(ROOT / "tape", families=("weather_actuals",))
    assert "weather_actuals/dt=2026-07-19" in issues
    assert "weather_actuals/dt=2026-07-20" in issues


# ─── unregistered single-hour committed leg meta-guard (L144: non-gating) ─────

def test_daily_cadence_families_includes_settlement_ledger():
    # L144: settlement_ledger is gated at a single fixed UTC hour (10) with no retry/backfill
    # (SETTLEMENT_LEDGER_UTC_HOUR), writes committed tape/settlement_ledger/, and froze at its
    # dt=2026-07-17 build day (Q36 blocker) because the every-3h cron never lands on hour 10 —
    # the same shape L123/L124 root-caused. It was simply never added to the tracked tuple, so
    # daily_family_gap_warning could not see it. This pins the registration.
    assert "settlement_ledger" in inv.DAILY_CADENCE_FAMILIES


def test_unregistered_single_hour_leg_real_tree_is_clean():
    # HARD acceptance test anchored to the REAL repo tree: with settlement_ledger now
    # registered, every single-hour committed leg in collection/hourly_pass.py resolves to a
    # family that IS in DAILY_CADENCE_FAMILIES (or the documented forecast_collector exemption),
    # so the meta-guard produces NO advisory. This is the state the milestone had to reach by
    # hand; the guard now holds it.
    assert inv._unregistered_single_hour_leg_issues() == []


def test_unregistered_single_hour_leg_fires_on_unregistered_known_family():
    # The next-variant bug: settlement_ledger's real single-hour leg exists in hourly_pass.py,
    # but someone forgot to register it. Simulate by dropping it from the monitored tuple; the
    # guard must catch it (this is exactly what bit weather_actuals/L126 and settlement_ledger).
    monitored = tuple(f for f in inv.DAILY_CADENCE_FAMILIES if f != "settlement_ledger")
    issues = inv._unregistered_single_hour_leg_issues(monitored=monitored)
    assert any("SETTLEMENT_LEDGER_UTC_HOUR" in i and "settlement_ledger" in i for i in issues)


def test_unregistered_single_hour_leg_fires_on_unrecognized_new_leg():
    # A FUTURE single-hour committed leg added to hourly_pass.py that the guard's maps don't
    # recognize must be SURFACED, not silently passed — closing the loop L126/L144 closed by
    # hand. Feed a synthetic hourly_pass-shaped source with a brand-new *_UTC_HOUR gate.
    synthetic = (
        "NEWLEG_UTC_HOUR = 5\n"
        "def run(now=None):\n"
        "    ts = now\n"
        "    if ts.hour == NEWLEG_UTC_HOUR:\n"
        "        newleg.run()\n"
    )
    issues = inv._unregistered_single_hour_leg_issues(source=synthetic)
    assert any("NEWLEG_UTC_HOUR" in i and "unrecognized" in i for i in issues)


def test_unregistered_single_hour_leg_ignores_plural_hours_set_gate():
    # The plural `*_UTC_HOURS` set-membership gate (universe_sweep, 4x/day on {0,6,12,18}) is
    # NOT a single-hour leg and must never be flagged — a missed hour there does not black out
    # the day. `ts.hour in ...` is not `ts.hour == ...`, and the name ends _UTC_HOURS not _HOUR.
    synthetic = (
        "UNIVERSE_SWEEP_UTC_HOURS = {0, 6, 12, 18}\n"
        "    if ts.hour in UNIVERSE_SWEEP_UTC_HOURS:\n"
        "        universe.run()\n"
    )
    assert inv._unregistered_single_hour_leg_issues(source=synthetic) == []


def test_unregistered_single_hour_leg_exempt_forecast_not_flagged():
    # forecast_collector writes gitignored data/forecast_tape/, never a committed tape/ family,
    # so it is documented-exempt and must not be flagged even though it is a single-hour leg.
    synthetic = "    if ts.hour == FORECAST_COLLECTOR_UTC_HOUR:\n        forecast.run()\n"
    assert inv._unregistered_single_hour_leg_issues(source=synthetic) == []


def test_unregistered_single_hour_leg_warning_none_when_empty():
    assert inv.unregistered_single_hour_leg_warning([]) is None


def test_unregistered_single_hour_leg_warning_message_content():
    msg = inv.unregistered_single_hour_leg_warning(
        ["SETTLEMENT_LEDGER_UTC_HOUR -> tape/settlement_ledger (single-hour committed leg ...)"])
    assert msg is not None
    assert "non-gating" in msg
    assert "SETTLEMENT_LEDGER_UTC_HOUR" in msg
    assert "L144" in msg


def test_unregistered_single_hour_leg_issues_missing_file_is_empty(tmp_path):
    # Best-effort/offline: a missing hourly_pass.py must return [] (never poison the gate).
    assert inv._unregistered_single_hour_leg_issues(tmp_path / "nope.py") == []


def test_unregistered_single_hour_leg_warning_never_gates_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(inv, "_unregistered_single_hour_leg_issues",
                        lambda: ["FAKE_UTC_HOUR (unrecognized single-hour leg ...)"])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "FAKE_UTC_HOUR" in captured.err
    assert "L144" in captured.err
    assert "invariants: all green" in captured.out


# ─── ladder-size int-coercion advisory (L47: non-gating) ─────────────────────

def test_ladder_size_coercion_real_tree_is_clean():
    # HARD acceptance test anchored to the real tree: the one violation this advisory was
    # built for (execution/fill_models.py::_taker_depth's bare `int(size)`) now routes
    # through core.depth.whole_contracts_available, so the real tree must report ZERO.
    assert inv._ladder_size_coercion_issues() == []


def test_ladder_size_coercion_fires_on_reintroduced_violation(tmp_path):
    (tmp_path / "execution").mkdir()
    (tmp_path / "execution" / "fill_models.py").write_text(
        "def f(remaining, size):\n    return min(remaining, int(size))\n")
    assert inv._ladder_size_coercion_issues(tmp_path) == ["execution/fill_models.py:2"]


def test_ladder_size_coercion_fires_on_round_floor_ceil_and_level_subscript(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "a.py").write_text("a = round(bid_size)\n")
    (tmp_path / "scripts" / "b.py").write_text("b = math.floor(queue_ahead)\n")
    (tmp_path / "scripts" / "c.py").write_text("c = math.ceil(total_depth)\n")
    (tmp_path / "scripts" / "d.py").write_text("d = int(level[1])\n")
    (tmp_path / "scripts" / "e.py").write_text("e = int(rec.no_bid_size)\n")
    (tmp_path / "scripts" / "f.py").write_text("f = int(sizes[i])\n")
    (tmp_path / "scripts" / "g.py").write_text("g = round(sz, 0)\n")
    assert inv._ladder_size_coercion_issues(tmp_path) == [
        f"scripts/{n}.py:1" for n in "abcdefg"]


def test_ladder_size_coercion_exempts_core_depth_and_tests(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "depth.py").write_text("return int(math.floor(size))\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "x.py").write_text("y = int(size)\n")
    assert inv._ladder_size_coercion_issues(tmp_path) == []


def test_ladder_size_coercion_does_not_flag_known_false_positive_shapes(tmp_path):
    (tmp_path / "scripts").mkdir()
    # (a) an ALL-CAPS module constant in a printf (scripts/probe_ladder_coherence.py:405)
    (tmp_path / "scripts" / "a.py").write_text('x = f"{int(MIN_DEPTH)}"\n')
    # (b) a RATIO rounded for reporting (scripts/universe_sweep_family_shapes.py:275)
    (tmp_path / "scripts" / "b.py").write_text("b = round(size_pos[k] / n_lines, 6)\n")
    # (c) a non-size int coercion (qty, timestamps, prices)
    (tmp_path / "scripts" / "c.py").write_text(
        "c = int(order.qty)\nd = int(_parse_iso(t).timestamp())\ne = round(1.0 - ask, 2)\n")
    # (d) a BACKTICKED prose mention of the forbidden pattern inside a docstring
    (tmp_path / "scripts" / "d.py").write_text(
        '"""A consumer assuming integer counts (`int(size)` truncation) corrupts reads."""\n')
    # (e) a comment line
    (tmp_path / "scripts" / "e.py").write_text("# never a bare int(size) here\n")
    # (f) sizes kept as FLOATS (the correct shape) must never be flagged
    (tmp_path / "scripts" / "f.py").write_text("total += float(level[1])\n")
    assert inv._ladder_size_coercion_issues(tmp_path) == []


def test_is_ladder_size_expr_unit_cases():
    assert inv._is_ladder_size_expr("size")
    assert inv._is_ladder_size_expr("bid_size")
    assert inv._is_ladder_size_expr("sizes[i]")
    assert inv._is_ladder_size_expr("rec.no_ask_size")
    assert inv._is_ladder_size_expr("queue_ahead")
    assert inv._is_ladder_size_expr("total_depth")
    assert inv._is_ladder_size_expr("level[1]")
    assert not inv._is_ladder_size_expr("MIN_DEPTH")
    assert not inv._is_ladder_size_expr("SIZE")
    assert not inv._is_ladder_size_expr("level[0]")   # element 0 is the PRICE
    assert not inv._is_ladder_size_expr("qty")
    assert not inv._is_ladder_size_expr("sum_volume")
    # multi-subscript: the LAST index selects element 1 of a [price, size] pair
    assert inv._is_ladder_size_expr("no_bids[0][1]")
    assert inv._is_ladder_size_expr("ladder[i][1]")
    assert not inv._is_ladder_size_expr("no_bids[1][0]")   # element 0 is the PRICE
    assert not inv._is_ladder_size_expr("row[0][1]")       # `row` is not ladder-ish


def _coercion_fires_on(tmp_path, source: str) -> bool:
    """Run one source LINE through the advisory in a throwaway production-shaped file."""
    d = tmp_path / "scripts"
    d.mkdir(exist_ok=True)
    f = d / "probe.py"
    f.write_text(source if source.endswith("\n") else source + "\n")
    return inv._ladder_size_coercion_issues(tmp_path) != []


# --- L155: recall is only what a constructed-negative corpus proves ------------
# A lexical advisory reporting 0 issues on a clean tree is evidence of PRECISION only.
# These two tests are the RECALL half: the first pins the shapes that DO fire, the second
# pins the deliberate blind spots as misses so a future widening has to update them on
# purpose. Derived from the 2026-07-25 verifier's 15-shape adversarial probe.

TESTED_FIRING_SHAPES = (
    "x = int(size)",
    "x = round(bid_size)",
    "x = math.floor(sizes[i])",
    "x = math.ceil(rec.no_ask_size)",
    "x = int(queue_ahead)",
    "x = int(total_depth)",
    "x = int(level[1])",
    "x = int(lvl[1])",
    "x = int(bid[1])",
    "x = int(no_bids[0][1])",      # the shape analysis/observatory/features.py:160 writes
    "x = int(ladder[i][1])",
    "x = int(float(size))",
    "x = round(float(level[1]))",
    "x = math.trunc(size)",
    "x = trunc(level[1])",
)

# Documented, DELIBERATE recall holes. Each was considered and rejected: a lexical rule wide
# enough to catch it would false-positive on the real tree (`depth` is an already-integer
# level COUNT in the orderbook_depth schema; `row`/`pair`/`entry` are ordinary iteration
# names; the rest need dataflow or an AST pass). An honest documented hole beats a
# false-positive-prone guard. If you widen the matcher, DELETE the entry here on purpose.
KNOWN_BLIND_SPOT_SHAPES = (
    "x = int(depth)",                     # bare `depth`: integer level COUNT field
    "x = int(row[1])",
    "x = int(pair[1])",
    "x = int(entry[1])",
    "n = size\nx = int(n)",               # renamed intermediate: needs dataflow
    "x = int(size_remaining)",            # size-ish PREFIX, not suffix
    "x = int(resting_qty_at_level)",      # paraphrase
    "x = int(\n    size\n)",              # multi-line call: the scan is line-by-line
    "x = size // 1",                      # non-call coercion
    "x = '%d' % size",                    # non-call coercion
    'x = f"{size:d}"',                    # non-call coercion
    "if size == 5:\n    pass",            # L47's other half (equality vs whole-number queue)
)


@pytest.mark.parametrize("src", TESTED_FIRING_SHAPES)
def test_ladder_size_coercion_fires_on_tested_shape_set(tmp_path, src):
    assert _coercion_fires_on(tmp_path, src), f"expected a HIT for: {src!r}"


@pytest.mark.parametrize("src", KNOWN_BLIND_SPOT_SHAPES)
def test_ladder_size_coercion_known_blind_spots_are_misses(tmp_path, src):
    # Asserting the MISSES: this is the documented hole, regression-tested so that the kb
    # row and the warning message cannot silently overstate coverage again (L155).
    assert not _coercion_fires_on(tmp_path, src), f"expected a MISS for: {src!r}"


def test_ladder_size_coercion_warning_none_when_empty():
    assert inv.ladder_size_coercion_warning([]) is None


def test_ladder_size_coercion_warning_message_content():
    msg = inv.ladder_size_coercion_warning(["execution/fill_models.py:147"])
    assert msg is not None
    assert "non-gating" in msg
    assert "whole_contracts_available" in msg
    assert "L47" in msg


def test_ladder_size_coercion_warning_never_gates_exit_code(monkeypatch, capsys):
    # The advisory is silent on the clean tree; what is pinned here is that --full stays
    # exit 0 and that this class can never become a gating one.
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "coerce an order-book ladder SIZE" not in captured.err
    assert "invariants: all green" in captured.out


# ─── raw datetime.fromisoformat advisory (L138 residue: non-gating) ───────────

def test_raw_datetime_fromisoformat_sites_finds_real_sites():
    # HARD acceptance test anchored to the real tree: production code widely calls
    # datetime.fromisoformat directly instead of core.timeutil.parse_iso_utc (L136/L138).
    sites = inv._raw_datetime_fromisoformat_sites()
    assert len(sites) >= 28
    assert all(not s.startswith("core/timeutil.py") for s in sites)
    assert all(not s.split("/", 1)[0] == "tests" for s in sites)


def test_raw_datetime_fromisoformat_exempts_timeutil_and_tests(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "timeutil.py").write_text("x = datetime.fromisoformat(s)\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "x.py").write_text("y = datetime.fromisoformat(s)\n")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.py").write_text("z = datetime.fromisoformat(s)\n")
    sites = inv._raw_datetime_fromisoformat_sites(tmp_path)
    assert sites == ["scripts/x.py:1"]


def test_raw_datetime_fromisoformat_skips_comment_lines(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.py").write_text("# datetime.fromisoformat(x)\n")
    assert inv._raw_datetime_fromisoformat_sites(tmp_path) == []


def test_raw_datetime_fromisoformat_does_not_flag_date_fromisoformat(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "x.py").write_text("d = date.fromisoformat(s)\n")
    assert inv._raw_datetime_fromisoformat_sites(tmp_path) == []


def test_raw_datetime_fromisoformat_warning_none_when_empty():
    assert inv.raw_datetime_fromisoformat_warning([]) is None


def test_raw_datetime_fromisoformat_warning_message_content():
    msg = inv.raw_datetime_fromisoformat_warning(["scripts/s8_basis_probe.py:74"])
    assert msg is not None
    assert "non-gating" in msg
    assert "parse_iso_utc" in msg
    assert "L138" in msg


def test_raw_datetime_fromisoformat_warning_never_gates_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "parse_iso_utc" in captured.err
    assert "L138" in captured.err
    assert "invariants: all green" in captured.out


# ─── duplicate lesson-ID advisory (L147: L130/L131 each collided 2026-07-24) ──

def test_duplicate_lesson_id_real_tree_is_clean():
    # HARD acceptance test anchored to the real tree: this run renumbered the two
    # collided IDs (L131 ws_depth-invariant lesson -> L145, L130 Polymarket-US-probe
    # lesson -> L146), so the real ledger must report zero duplicates now.
    assert inv._duplicate_lesson_id_issues() == []


def test_duplicate_lesson_id_issues_finds_real_duplicate(tmp_path):
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | first lesson | src | test |\n"
        "| L2 | 2026-07-02 | second lesson | src | test |\n"
        "| L2 | 2026-07-03 | a DIFFERENT lesson someone else also called L2 | src | test |\n"
    )
    assert inv._duplicate_lesson_id_issues(lessons) == ["L2"]


def test_duplicate_lesson_id_issues_ignores_prose_mentions_outside_id_column(tmp_path):
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | see also L2 for the sibling lesson | src | test |\n"
        "| L2 | 2026-07-02 | the only row actually keyed L2 | src | test |\n"
    )
    assert inv._duplicate_lesson_id_issues(lessons) == []


def test_duplicate_lesson_id_issues_missing_file_is_safe(tmp_path):
    assert inv._duplicate_lesson_id_issues(tmp_path / "does-not-exist.md") == []


def test_duplicate_lesson_id_warning_none_when_empty():
    assert inv.duplicate_lesson_id_warning([]) is None


def test_duplicate_lesson_id_warning_message_content():
    msg = inv.duplicate_lesson_id_warning(["L2"])
    assert msg is not None
    assert "non-gating" in msg
    assert "L2" in msg
    assert "L147" in msg


def test_duplicate_lesson_id_warning_never_gates_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "invariants: all green" in captured.out
    # The real tree is clean post-fix, so the advisory should not fire at all here.
    assert "lesson ID(s)" not in captured.err


# ─── stale-UNENFORCED-candidate advisory (L152: L74/L109/L123 marker-drift class) ──

def test_stale_unenforced_candidate_real_tree_func_matcher_is_clean():
    # STRUCTURE only (L207 narrowing, 2026-07-29 — the same L192/L201 move applied again).
    # The old body hard-asserted `by_matcher["func"] == 0` against the LIVE tree: a future
    # genuinely-open lesson row that happens to backtick a `function_name()` candidate already
    # present somewhere in the tree would turn this file's own gate red for a reason unrelated
    # to the code under test — exactly the L192 hazard shape, one matcher over. The ENUMERATION
    # ("today's open rows name no colliding func()") moved to the frozen fixture below; what's
    # asserted here about the live tree is only that the report computes and the matcher key
    # is present with a well-typed, non-negative count.
    rep = inv.stale_unenforced_recall_report()
    by_matcher = dict(rep.by_matcher)
    assert "func" in by_matcher
    assert isinstance(by_matcher["func"], int) and by_matcher["func"] >= 0


def test_stale_unenforced_candidate_frozen_fixture_func_matcher_is_clean():
    # The ENUMERATION half of the split above, over the frozen 21-row snapshot no other agent
    # rewrites (tests/fixtures/lessons_unenforced_21_2026-07-27.md, already used by
    # tests/test_stale_unenforced_advisory.py for the sibling recall checks) — this is where
    # "no genuinely-open row names a colliding func() candidate" is actually verified, and it
    # can never go red from a future lesson append to the live ledger.
    fixture = ROOT / "tests" / "fixtures" / "lessons_unenforced_21_2026-07-27.md"
    rep = inv.stale_unenforced_recall_report(fixture, source_root=ROOT)
    assert dict(rep.by_matcher)["func"] == 0


def test_stale_unenforced_candidate_issues_finds_real_match(tmp_path):
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | some lesson | src | "
        "**UNENFORCED** -- candidate: a `_iter_source_files()` helper | \n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("def _iter_source_files(root=None):\n    return []\n")
    issues = inv._stale_unenforced_candidate_issues(lessons, source_root=src)
    assert len(issues) == 1
    assert "L1" in issues[0]
    assert "_iter_source_files()" in issues[0]
    assert "helper.py" in issues[0]


def test_stale_unenforced_candidate_issues_ignores_lesson_text_mentions(tmp_path):
    # L105's exact real-world shape: the candidate function is named in the LESSON
    # column (existing code cited as context), not the enforcement column -- must not fire.
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | this cites the existing `_iter_source_files()` helper | src | "
        "**UNENFORCED** -- candidate: a new docstring note, no function proposed | \n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("def _iter_source_files(root=None):\n    return []\n")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_stale_unenforced_candidate_issues_ignores_non_unenforced_rows(tmp_path):
    # Enforcement column mentions "UNENFORCED" but does not START with the bold marker
    # (the L74/L109/L123 corrected shape: "**test** (BUILT ...); ... UNENFORCED ...").
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | some lesson | src | "
        "**test** (BUILT) -- `_iter_source_files()` implements this; UNENFORCED as a "
        "broader static check | \n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("def _iter_source_files(root=None):\n    return []\n")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_stale_unenforced_candidate_issues_ignores_generic_names_without_underscore(tmp_path):
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | some lesson | src | "
        "**UNENFORCED** -- candidate: a `run()` entry point | \n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("def run():\n    return None\n")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_stale_unenforced_candidate_issues_no_match_when_function_absent(tmp_path):
    lessons = tmp_path / "00-lessons.md"
    lessons.write_text(
        "| L1 | 2026-07-01 | some lesson | src | "
        "**UNENFORCED** -- candidate: a `_not_built_yet()` helper | \n"
    )
    src = tmp_path / "src"
    src.mkdir()
    (src / "helper.py").write_text("def _iter_source_files(root=None):\n    return []\n")
    assert inv._stale_unenforced_candidate_issues(lessons, source_root=src) == []


def test_stale_unenforced_candidate_issues_missing_file_is_safe(tmp_path):
    assert inv._stale_unenforced_candidate_issues(tmp_path / "does-not-exist.md") == []


def test_stale_unenforced_candidate_warning_none_when_empty():
    assert inv.stale_unenforced_candidate_warning([]) is None


def test_stale_unenforced_candidate_warning_message_content():
    msg = inv.stale_unenforced_candidate_warning(["L1: candidate `_foo()` already defined in bar.py"])
    assert msg is not None
    assert "non-gating" in msg
    assert "L1" in msg
    assert "L152" in msg


def test_stale_unenforced_candidate_warning_never_gates_exit_code(monkeypatch, capsys):
    # ABSENCE OF EFFECT only, deliberately. A real-tree run must NEVER assert this advisory's
    # TEXT: whether it prints depends on LIVE kb/lessons/00-lessons.md state that another agent
    # (the kb-distiller) may write during the same run — on 2026-07-27 an L188 `DISPOSES:` row
    # took the open queue to 0, the formatter correctly returned None, and this test's two
    # text-presence assertions went red for a reason unrelated to the code under test.
    # Text-presence belongs on the FROZEN fixture: see the test below and
    # tests/test_stale_unenforced_advisory.py.
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "invariants: all green" in captured.out


def test_stale_unenforced_advisory_text_on_the_frozen_fixture():
    # The TEXT half of the split above, over an artifact no other agent rewrites: the frozen
    # 21-row copy of the pre-disposition ledger.
    fixture = ROOT / "tests" / "fixtures" / "lessons_unenforced_21_2026-07-27.md"
    rep = inv.stale_unenforced_recall_report(fixture, source_root=ROOT)
    msg = inv.stale_unenforced_candidate_warning(
        inv._stale_unenforced_candidate_issues(fixture, source_root=ROOT), rep
    )
    assert msg is not None
    assert "UNENFORCED lesson row(s)" in msg
    assert "does NOT affect the exit code" in msg


# ─── DB invariants ────────────────────────────────────────────────────────────

def _db(tmp_path, name, ddl, rows_sql=()):
    p = tmp_path / name
    con = sqlite3.connect(p)
    con.executescript(ddl)
    for stmt in rows_sql:
        con.execute(stmt)
    con.commit()
    con.close()
    return p


def test_db_clean_backtest_passes(tmp_path):
    db = _db(
        tmp_path, "clean.db",
        "CREATE TABLE backtest (pnl REAL, price_source_tag TEXT, fair_probability REAL);",
        ["INSERT INTO backtest VALUES (0.12, 'real_ask', 0.61)",
         "INSERT INTO backtest VALUES (-0.05, 'synthetic', 0.40)"],
    )
    assert inv.scan_db(db) == []


def test_db_pnl_with_null_tag_is_caught(tmp_path):
    db = _db(
        tmp_path, "nulltag.db",
        "CREATE TABLE backtest (pnl REAL, price_source_tag TEXT);",
        ["INSERT INTO backtest VALUES (0.30, NULL)"],
    )
    fails = inv.scan_db(db)
    assert any("pnl_requires_tag" in f for f in fails), fails


def test_db_pnl_without_tag_column_is_caught(tmp_path):
    db = _db(
        tmp_path, "notagcol.db",
        "CREATE TABLE backtest (pnl REAL, note TEXT);",
        ["INSERT INTO backtest VALUES (0.30, 'x')"],
    )
    fails = inv.scan_db(db)
    assert any("no price_source_tag column" in f for f in fails), fails


def test_db_invalid_enum_value_is_caught(tmp_path):
    db = _db(
        tmp_path, "badenum.db",
        "CREATE TABLE signals (price_source_tag TEXT);",
        ["INSERT INTO signals VALUES ('guess')"],
    )
    fails = inv.scan_db(db)
    assert any("price_source_tag" in f for f in fails), fails


def test_db_probability_out_of_range_is_caught(tmp_path):
    db = _db(
        tmp_path, "prob.db",
        "CREATE TABLE signals (fair_probability REAL);",
        ["INSERT INTO signals VALUES (1.4)"],
    )
    fails = inv.scan_db(db)
    assert any("probability_in_range" in f for f in fails), fails


def test_db_real_bid_tag_is_caught_as_invalid_enum(tmp_path):
    """kb/lessons/00-lessons.md L22: `real_bid` (collection/orderbook_depth.py's tag for a
    genuine resting bid) is deliberately NOT in VALID_SOURCE_TAGS — that enum is CLAUDE.md's
    literal trust-taxonomy contract (real_ask/broker_truth/midpoint/synthetic) and widening it
    is a project-contract change, not a research-loop milestone. This pins the claim that made
    the gap "harmless today": if a `real_bid`-tagged value ever reached a DB's
    `price_source_tag` column, the existing enum check would catch it exactly like any other
    invalid tag, same as `test_db_invalid_enum_value_is_caught`'s generic 'guess' case."""
    db = _db(
        tmp_path, "realbid.db",
        "CREATE TABLE signals (price_source_tag TEXT);",
        ["INSERT INTO signals VALUES ('real_bid')"],
    )
    fails = inv.scan_db(db)
    assert any("price_source_tag" in f for f in fails), fails


# ─── Execution-lane invariants (2026-07-12 Stop-rules amendment) ─────────────────────


@pytest.mark.parametrize("snippet", [
    "resp = self.post('/trade-api/v2/portfolio/orders', body)",
    "headers['KALSHI-ACCESS-SIGNATURE'] = sig",
    "def cancel_order(self, order_id):",
    "client.batch_create_orders(orders)",
])
def test_order_endpoint_rule_fires(snippet):
    failures = inv.scan_text(GENERIC, snippet)
    assert any("[order_endpoints_confined]" in f for f in failures), (snippet, failures)


def test_order_endpoint_rule_exempt_in_sanctioned_client_site():
    # execution/kalshi_client.py is the ONE file order/auth endpoints may live in
    # (unbuilt until a strategy nears live graduation — the exemption predates the file).
    assert inv.scan_text(ROOT / "execution" / "kalshi_client.py",
                         "def place_order(self): ...") == []


def test_order_endpoint_rule_skips_comment_lines():
    assert inv.scan_text(GENERIC, "    # never call place_order from a collector") == []


def test_order_endpoint_rule_exempts_kb_signing_repro():
    # scripts/kalshi_sign.py is the KB's offline signing repro (throwaway key, no network) —
    # knowledge, not action; pinned exemption so the KB artifact and the rule coexist.
    assert inv.scan_text(ROOT / "scripts" / "kalshi_sign.py",
                         '"KALSHI-ACCESS-SIGNATURE": signature,') == []


def test_order_endpoint_rule_ws_depth_auth_headers_sanctioned_order_verbs_still_fire():
    # collection/ws_depth.py (L145, Ryan opened the WS build gate 2026-07-21): Kalshi
    # requires the signed handshake even for read-only market data, so the auth headers
    # are sanctioned there — but ONLY the headers; an order verb in that file must fire.
    ws = ROOT / "collection" / "ws_depth.py"
    assert inv.scan_text(ws, '"KALSHI-ACCESS-SIGNATURE": sig,') == []
    assert any("[order_endpoints_confined]" in f
               for f in inv.scan_text(ws, "resp = self.place_order(ticker)"))
    assert any("[order_endpoints_confined]" in f
               for f in inv.scan_text(ws, "self.post('/trade-api/v2/portfolio/orders')"))


@pytest.mark.parametrize("snippet", [
    "orders = sorted(open_orders)",          # benign: no order-verb method name
    "self.orderbook(ticker)",                # read-only public endpoint, not portfolio/orders
    "portfolio = compute_paper_portfolio()", # 'portfolio' alone is not the REST path
])
def test_order_endpoint_rule_silent_on_read_only_uses(snippet):
    assert not any("[order_endpoints_confined]" in f for f in inv.scan_text(GENERIC, snippet))


# ─── L145 residual: private/user WS channel subscription gate ────────────────
#
# L145's sanction for authenticated auth headers in `collection/ws_depth.py` rests on a
# two-part premise ("no order verb AND no private/fill channel subscription"). Only the
# order-verb half was enforced (2026-07-23, issue #157); these pin the other half.

_RULE = "[no_private_ws_channel_subscription]"


@pytest.mark.parametrize("snippet", [
    # the realistic regression: a private channel appended to the module's own tuple,
    # where the banned literal and its context token are on DIFFERENT physical lines
    'DEFAULT_CHANNELS = (\n    "orderbook_delta",\n    "fill",\n)',
    # the raw subscribe envelope
    'return {"cmd": "subscribe", "params": {"channels": ["market_positions"]}}',
    # a caller passing it in rather than editing the collector
    'run(channels=("orderbook_delta", "user_orders"))',
    'sub = subscribe_command(tickers, channels=["user_fills"])',
])
def test_private_ws_channel_rule_fires(snippet):
    assert any(_RULE in f for f in inv.scan_text(GENERIC, snippet))


@pytest.mark.parametrize("snippet", [
    # public market-data channels are the whole point of the collector
    'DEFAULT_CHANNELS = ("orderbook_delta", "ticker", "trade", "market_lifecycle")',
    # the 23 innocent sites a context-free literal match would have broken (L145 residual
    # note): paper-tier record kinds, probe report keys, ledger id lists
    'record_kind: str = "fill"',
    'report["fill"] = {"n_filled": 3}',
    '"fills": [f.fill_id for f in fills],',
    'fills_dir = DATA / "fills"',
    # a comment is not code
    '# DEFAULT_CHANNELS = ("fill",)',
])
def test_private_ws_channel_rule_silent_on_innocent_uses(snippet):
    assert not any(_RULE in f for f in inv.scan_text(GENERIC, snippet))


def test_private_ws_channel_rule_known_blind_spot_variable_indirection():
    """KNOWN BLIND SPOT, regression-tested as a MISS (the L155/L157 convention in this
    repo: a low count is PRECISION evidence, not recall). Binding the channel tuple to a
    plain name on one balanced line and passing that NAME to `subscribe_command` on
    another puts the literal and the context token in two different logical lines, so this
    static rule cannot see it. Recorded rather than papered over — widening the context
    regex to catch it would drag in the 23 innocent `"fill"`/`"fills"` sites the rule
    exists to stay clear of. The realistic regression (editing `DEFAULT_CHANNELS` in
    place, or passing `channels=(...)` at a call site) IS caught, above."""
    snippet = 'CH = ("order_group_updates",)\nconn.send(subscribe_command(t, CH))'
    assert not any(_RULE in f for f in inv.scan_text(GENERIC, snippet))


def test_private_ws_channel_rule_exempts_only_the_sanctioned_sites():
    # the live client (unbuilt) legitimately watches its OWN fills once it exists…
    assert inv.scan_text(ROOT / "execution" / "kalshi_client.py",
                         'CHANNELS = ("fill",)') == []
    # …and ws_depth's own test file, pre-emptively: L145's root cause was PR #153
    # exempting two source files but not their tests.
    assert inv.scan_text(ROOT / "tests" / "test_ws_depth.py",
                         'CHANNELS = ("fill",)') == []
    # everything else, ws_depth.py very much included, still fires.
    assert any(_RULE in f for f in inv.scan_text(
        ROOT / "collection" / "ws_depth.py",
        'DEFAULT_CHANNELS = ("orderbook_delta", "fill")'))


def test_ws_depth_real_source_subscribes_only_to_public_channels():
    """Acceptance test on the REAL committed collector, not a fixture (L145's premise is a
    claim about that file). Its module docstring asserts 'never subscribes to a user/private
    channel (fills, orders, positions)' — this is that sentence as an assertion."""
    ws = ROOT / "collection" / "ws_depth.py"
    assert inv.scan_text(ws, ws.read_text(encoding="utf-8")) == []
    import collection.ws_depth as wsd
    assert wsd.DEFAULT_CHANNELS == ("orderbook_delta",)
    env = wsd.subscribe_command(["KXBTC-T1"])
    assert env["params"]["channels"] == ["orderbook_delta"]


def test_bracket_joined_lines_reports_the_opening_lineno_and_survives_eof():
    text = 'a = (\n  1,\n  2,\n)\nb = 3\nc = (\n  4,\n'
    joined = inv._bracket_joined_lines(text)
    assert joined[0] == (1, "a = ( 1, 2, )")
    assert joined[1] == (5, "b = 3")
    # unterminated bracket at EOF is still yielded, never silently dropped
    assert joined[-1][0] == 6 and "4," in joined[-1][1]


def test_risk_caps_rule_fires_on_rebind_and_exempt_in_limits():
    assert any("[risk_caps_sanctioned]" in f
               for f in inv.scan_text(GENERIC, "MAX_DAILY_ORDERS = 10_000"))
    # execution/limits.py is the single sanctioned caps site…
    assert inv.scan_text(ROOT / "execution" / "limits.py",
                         "MAX_DAILY_ORDERS = 200") == []
    # …and comparisons/imports elsewhere are not bindings.
    assert not any("[risk_caps_sanctioned]" in f for f in inv.scan_text(
        GENERIC, "ok = n <= limits.MAX_DAILY_ORDERS\nassert x == MAX_DAILY_ORDERS"))


# ─── Tape conflict-marker gate (2026-07-23 incident) ─────────────────────────

def test_tape_conflict_marker_issues_finds_all_three_marker_shapes(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-18.jsonl").write_text(
        '{"a":1}\n'
        '=======\n'
        '>>>>>>> 58145d7 (tape: hourly pass 2026-07-18T09:30:28Z (vps))\n'
        '{"a":2}\n'
        '<<<<<<< HEAD\n'
    )
    issues = inv._tape_conflict_marker_issues(tape_root)
    assert issues == [
        "econ_prints/dt=2026-07-18.jsonl:2",
        "econ_prints/dt=2026-07-18.jsonl:3",
        "econ_prints/dt=2026-07-18.jsonl:5",
    ]


def test_tape_conflict_marker_issues_clean_family_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "anomalies"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-20.jsonl").write_text('{"anomalies":[]}\n{"anomalies":[]}\n')
    assert inv._tape_conflict_marker_issues(tape_root) == []


def test_tape_conflict_marker_issues_missing_tape_root_is_empty(tmp_path):
    assert inv._tape_conflict_marker_issues(tmp_path / "no-such-tape") == []


def test_tape_conflict_marker_issues_real_tree_is_clean():
    # HARD acceptance test: the 2026-07-23 incident (tape/econ_prints and tape/anomalies
    # dt=2026-07-18.jsonl each carrying 3 marker lines) is repaired as of this commit — the
    # real committed tape tree must show zero conflict-marker lines.
    assert inv._tape_conflict_marker_issues() == []


def test_tape_conflict_marker_failure_none_when_empty():
    assert inv.tape_conflict_marker_failure([]) is None


def test_tape_conflict_marker_failure_message_content():
    msg = inv.tape_conflict_marker_failure(["tape/anomalies/dt=2026-07-18.jsonl:11"])
    assert msg is not None
    assert "[tape_conflict_marker]" in msg
    assert "tape/anomalies/dt=2026-07-18.jsonl:11" in msg


def test_tape_conflict_marker_gates_exit_code(monkeypatch, capsys):
    # Unlike the advisories above, a conflict marker in committed tape must flip the exit
    # code. `_tape_conflict_marker_issues`'s tape_root default is bound at def-time, so
    # patch the detector function itself (same technique the wiring actually exercises)
    # rather than ROOT, to prove main() turns a non-empty result into a gating failure.
    monkeypatch.setattr(inv, "_tape_conflict_marker_issues",
                         lambda *a, **k: ["tape/econ_prints/dt=2026-07-01.jsonl:2"])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "[tape_conflict_marker]" in captured.err


# ─── Tape invalid-JSON gate (L142 generalization) ────────────────────────────

def _all_jsonl(tape_root):
    """Helper: the set of resolved *.jsonl paths under a fixture tape_root, standing in for the
    git-tracked set so a test's fixture files are all treated as 'committed' without needing a
    real git repo. (`_tape_invalid_jsonl_issues` takes `tracked_files` explicitly for exactly
    this reason.)"""
    return {p.resolve() for p in tape_root.rglob("*.jsonl")}


def test_tape_invalid_jsonl_real_tree_is_clean():
    # HARD acceptance test: pins the current committed tape tree cleanliness. Every non-empty
    # line of every git-TRACKED tape/**/*.jsonl parses as valid JSON right now. Uses the real
    # git-tracked resolution (tracked_files=None default) — real committed tape is all-tracked
    # and clean. Mirrors the conflict-marker real-tree test.
    assert inv._tape_invalid_jsonl_issues() == []


def test_tape_invalid_jsonl_issues_flags_truncated_line(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    f = fam / "dt=2026-07-18.jsonl"
    f.write_text(
        '{"a": 1}\n'
        '{"a": 1,\n'          # truncated write -> invalid JSON
        'garbage not json\n'  # stray non-JSON line
        '{"a": 2}\n'
    )
    issues = inv._tape_invalid_jsonl_issues(tape_root, tracked_files={f.resolve()})
    assert len(issues) == 2
    assert issues[0].startswith("econ_prints/dt=2026-07-18.jsonl:2")
    assert issues[1].startswith("econ_prints/dt=2026-07-18.jsonl:3")


def test_tape_invalid_jsonl_issues_tracked_malformed_is_flagged(tmp_path):
    # Fix-1 direction (b): a malformed .jsonl that IS in the tracked set is still caught — the
    # scope fix excludes untracked files, it does NOT relax detection on committed corruption.
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    f = fam / "dt=2026-07-18.jsonl"
    # torn last line, no trailing newline: a committed torn line IS real corruption (L142).
    f.write_text('{"a": 1}\n{"a": 1,')
    issues = inv._tape_invalid_jsonl_issues(tape_root, tracked_files={f.resolve()})
    assert len(issues) == 1
    assert issues[0].startswith("econ_prints/dt=2026-07-18.jsonl:2")


def test_tape_invalid_jsonl_issues_untracked_malformed_is_not_flagged(tmp_path):
    # Fix-1 direction (a), the wedge-prevention pin: a malformed / torn-last-line .jsonl that is
    # NOT in the tracked set (a collector mid-append in an uncommitted file) must NOT be flagged,
    # or an in-flight torn line would flip this GATING check to exit 2 and wedge the loop on data
    # that was never committed (2026-07-24 incident: two untracked live-capture files appeared
    # mid-run). Same file content as the tracked test above, but tracked_files is empty.
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    f = fam / "dt=2026-07-18.jsonl"
    f.write_text('{"a": 1}\n{"a": 1,')
    assert inv._tape_invalid_jsonl_issues(tape_root, tracked_files=set()) == []


def test_tape_invalid_jsonl_issues_does_not_double_report_conflict_markers(tmp_path):
    # A conflict-marker line also fails json.loads; per the design choice (option (a)) it
    # stays the conflict-marker gate's job and is NOT reported by the invalid-JSON gate.
    tape_root = tmp_path / "tape"
    fam = tape_root / "anomalies"
    fam.mkdir(parents=True)
    f = fam / "dt=2026-07-18.jsonl"
    f.write_text(
        '{"a": 1}\n'
        '=======\n'
        '>>>>>>> 58145d7 (tape merge)\n'
        '<<<<<<< HEAD\n'
        '{"a": 2}\n'
    )
    # Still caught by the conflict-marker gate (filesystem-scoped by design).
    assert inv._tape_conflict_marker_issues(tape_root) == [
        "anomalies/dt=2026-07-18.jsonl:2",
        "anomalies/dt=2026-07-18.jsonl:3",
        "anomalies/dt=2026-07-18.jsonl:4",
    ]
    # NOT double-reported by the invalid-JSON gate.
    assert inv._tape_invalid_jsonl_issues(tape_root, tracked_files={f.resolve()}) == []


def test_tape_invalid_jsonl_issues_tolerates_empty_and_whitespace_lines(tmp_path):
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-20.jsonl").write_text('{"a": 1}\n\n   \n{"a": 2}\n')
    assert inv._tape_invalid_jsonl_issues(tape_root, tracked_files=_all_jsonl(tape_root)) == []


def test_tape_invalid_jsonl_issues_ignores_non_jsonl_files(tmp_path):
    # Scope check: only *.jsonl is scanned. A .raw.json capture blob (L25/L109) and a `meta`
    # file with garbage content under tape/ must be ignored.
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-20.jsonl").write_text('{"a": 1}\n')
    (fam / "dt=2026-07-20.raw.json").write_text('this is not json at all {{{\n')
    (fam / "meta").write_text('garbage not json\n')
    (fam / "README.md").write_text('# notes\nnot json\n')
    assert inv._tape_invalid_jsonl_issues(tape_root, tracked_files=_all_jsonl(tape_root)) == []


def test_tape_invalid_jsonl_issues_missing_tape_root_is_empty(tmp_path):
    assert inv._tape_invalid_jsonl_issues(tmp_path / "no-such-tape") == []


def test_tape_invalid_jsonl_issues_unreadable_file_does_not_crash(tmp_path):
    # A file that cannot be decoded as utf-8 is skipped best-effort, never crashes the gate.
    tape_root = tmp_path / "tape"
    fam = tape_root / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-20.jsonl").write_bytes(b'\xff\xfe\x00\x01 not utf-8\n')
    (fam / "dt=2026-07-21.jsonl").write_text('{"a": 1}\n')
    # No exception; the good file's valid line yields no issue.
    assert inv._tape_invalid_jsonl_issues(tape_root, tracked_files=_all_jsonl(tape_root)) == []


def test_git_tracked_jsonl_subprocess_failure_returns_empty_set(monkeypatch):
    # Offline/robustness: if the `git ls-files` subprocess raises for ANY reason, the tracked
    # set is empty so the GATING check simply skips — a gating check must never flip the exit
    # code on an environment/git failure. (A non-zero return is covered by the same early-out.)
    def _boom(*a, **k):
        raise OSError("git missing")
    monkeypatch.setattr(inv.subprocess, "run", _boom)
    assert inv._git_tracked_jsonl(inv.ROOT / "tape") == set()


def test_git_tracked_jsonl_nonzero_exit_returns_empty_set(monkeypatch):
    class _Proc:
        returncode = 128
        stdout = ""
    monkeypatch.setattr(inv.subprocess, "run", lambda *a, **k: _Proc())
    assert inv._git_tracked_jsonl(inv.ROOT / "tape") == set()


def test_git_tracked_jsonl_finds_committed_tape():
    # On the real repo, the tracked set is non-empty and every entry is a resolved .jsonl path
    # under tape/ (sanity that the default git resolution actually returns the committed tree).
    tracked = inv._git_tracked_jsonl()
    assert tracked  # real repo has committed tape
    assert all(str(p).endswith(".jsonl") for p in tracked)


def test_tape_invalid_jsonl_failure_none_when_empty():
    assert inv.tape_invalid_jsonl_failure([]) is None


def test_tape_invalid_jsonl_failure_message_content():
    msg = inv.tape_invalid_jsonl_failure(['econ_prints/dt=2026-07-18.jsonl:2 ({"a": 1,)'])
    assert msg is not None
    assert "[tape_invalid_jsonl]" in msg
    assert "econ_prints/dt=2026-07-18.jsonl:2" in msg


def test_tape_invalid_jsonl_gates_exit_code(monkeypatch, capsys):
    # Unlike the advisories, an invalid-JSON line in committed tape must flip the exit code.
    # Patch the detector function itself (its tape_root default is bound at def-time), same
    # technique as the conflict-marker gate test.
    monkeypatch.setattr(inv, "_tape_invalid_jsonl_issues",
                        lambda *a, **k: ['econ_prints/dt=2026-07-01.jsonl:2 ({"a": 1,)'])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 2
    assert "[tape_invalid_jsonl]" in captured.err


# ─── raw datetime.fromisoformat ratchet (L136/L150: GATING, allowlisted) ─────

def _raw_iso_failures_over_real_tree():
    """Every failure message the ratchet produces over the REAL repo source tree."""
    out = []
    for p in inv._iter_source_files():
        if p.suffix != ".py":
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        msg = inv.inv_no_raw_datetime_fromisoformat(p, text)
        if msg:
            out.append(msg)
    return out


def test_acceptance_raw_iso_ratchet_real_tree_is_clean():
    # HARD acceptance test, anchored to the REAL tree: the pins in
    # LEGACY_RAW_FROMISOFORMAT_SITES exactly cover today's legacy debt, so the ratchet is
    # green NOW and any new/grown raw call site turns it red. This is the load-bearing test —
    # the 3.9-vs-3.11 blind spot (L136/L150) means nothing else can see this hazard.
    assert _raw_iso_failures_over_real_tree() == []


def test_raw_iso_ratchet_fires_on_new_unlisted_file():
    # The point of the ratchet: a brand-new file (not on the allowlist) with a raw call fails.
    src = "from datetime import datetime\nts = datetime.fromisoformat(s)\n"
    msg = inv.inv_no_raw_datetime_fromisoformat(GENERIC, src)
    assert msg is not None
    assert "NEW raw datetime.fromisoformat call site" in msg
    assert "core.timeutil.parse_iso_utc" in msg
    assert "L136" in msg and "L150" in msg
    assert "3.9" in msg and "3.11" in msg


def test_raw_iso_ratchet_fires_when_legacy_file_exceeds_pin():
    # Debt growth in an ALREADY-allowlisted file must also fail — the pin is a ceiling.
    rel = "collection/crypto_hourly.py"
    pin = inv.LEGACY_RAW_FROMISOFORMAT_SITES[rel]
    src = "".join(f"t{i} = datetime.fromisoformat(x)\n" for i in range(pin + 1))
    msg = inv.inv_no_raw_datetime_fromisoformat(ROOT / rel, src)
    assert msg is not None
    assert f"{pin + 1} > pinned {pin}" in msg


def test_raw_iso_ratchet_silent_when_legacy_file_shrinks():
    # Migration must always be allowed: fewer sites than the pin passes (lower the pin then).
    rel = "collection/sports_history.py"
    pin = inv.LEGACY_RAW_FROMISOFORMAT_SITES[rel]
    assert pin >= 2
    src = "".join(f"t{i} = datetime.fromisoformat(x)\n" for i in range(pin - 1))
    assert inv.inv_no_raw_datetime_fromisoformat(ROOT / rel, src) is None


def test_raw_iso_ratchet_does_not_fire_on_date_fromisoformat():
    # False-positive regression: a bare YYYY-MM-DD day token has no fractional field and no
    # `Z`, so date.fromisoformat carries none of the 3.9 hazard and must never be flagged.
    src = 'd = date.fromisoformat("2026-07-24")\n'
    assert inv.inv_no_raw_datetime_fromisoformat(GENERIC, src) is None


def test_raw_iso_ratchet_does_not_fire_on_parse_iso_utc():
    # False-positive regression: the SANCTIONED call shape is what we want people writing.
    src = "from core.timeutil import parse_iso_utc\nts = parse_iso_utc(row['ts'])\n"
    assert inv.inv_no_raw_datetime_fromisoformat(GENERIC, src) is None


def test_raw_iso_ratchet_skips_comment_lines():
    # Prose/docstring mentions of the hazard (this repo is full of them) are not call sites.
    src = "# datetime.fromisoformat(x) is a 3.9 crash — use parse_iso_utc\n"
    assert inv.inv_no_raw_datetime_fromisoformat(GENERIC, src) is None


def test_raw_iso_ratchet_exempts_core_timeutil_but_fires_elsewhere():
    # Both directions (the L148 precedent): core/timeutil.py legitimately calls the stdlib
    # parser after zero-padding the fractional field, and is exempt; the IDENTICAL line in a
    # non-sanctioned file still fires.
    src = "return datetime.fromisoformat(normalized)\n"
    assert inv.inv_no_raw_datetime_fromisoformat(ROOT / "core" / "timeutil.py", src) is None
    assert inv.inv_no_raw_datetime_fromisoformat(GENERIC, src) is not None


def test_raw_iso_ratchet_registered_in_static_invariants():
    assert any(name == "no_raw_datetime_fromisoformat" for name, _ in inv.STATIC_INVARIANTS)


def test_raw_iso_allowlist_hygiene():
    # Every pinned path must still exist, and its ACTUAL count must be <= its pin — a pin that
    # outlives its file (or over-states the debt) silently widens the ratchet.
    for rel, pin in inv.LEGACY_RAW_FROMISOFORMAT_SITES.items():
        p = ROOT / rel
        assert p.is_file(), f"stale allowlist entry: {rel}"
        text = p.read_text(encoding="utf-8")
        actual = sum(1 for _, ln in inv._scan_lines(text)
                     if not ln.lstrip().startswith("#")
                     and inv._DATETIME_FROMISOFORMAT_RE.search(ln))
        assert actual <= pin, f"{rel}: {actual} raw sites > pinned {pin}"


# ─── capped-pagination span-vs-cadence advisory (L185: non-gating) ────────────

def _sl_line(cid, close_time):
    return {"capture_id": cid, "captured_at": "2026-07-22T10:31:41.942809+00:00",
            "close_time": close_time, "source": "live_settled_markets",
            "price_source_tag": "broker_truth"}


def _write_settlement_tape(tape_root, day, records):
    fam = tape_root / "settlement_ledger"
    fam.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(fam / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        for rec in records:
            f.write(_json.dumps(rec) + "\n")


def _narrow_capture(cid, start_hour, span_hours, n_rows):
    """n_rows rows spread over span_hours of close_time on 2026-07-22, bare-Z formatted."""
    import datetime as _dt
    start = _dt.datetime(2026, 7, 22, start_hour, 0, tzinfo=_dt.timezone.utc)
    out = []
    for i in range(n_rows):
        ts = start + _dt.timedelta(hours=span_hours * i / max(1, n_rows - 1))
        out.append(_sl_line(cid, ts.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return out


def test_capped_pagination_span_issues_missing_tape_root_is_empty_L185(tmp_path):
    assert inv._capped_pagination_span_issues(tmp_path / "nope") == []


def test_capped_pagination_span_issues_wide_span_is_no_issue_L185(tmp_path):
    _write_settlement_tape(tmp_path, "2026-07-22", _narrow_capture("wide", 0, 20.0, 200))
    assert inv._capped_pagination_span_issues(tmp_path) == []


def test_capped_pagination_span_issues_finds_narrow_capture_L185(tmp_path):
    _write_settlement_tape(tmp_path, "2026-07-22", _narrow_capture("narrow", 7, 3.25, 200))
    issues = inv._capped_pagination_span_issues(tmp_path)
    assert len(issues) == 1
    assert issues[0]["family"] == "settlement_ledger"
    assert issues[0]["n_captures_narrow"] == 1
    assert issues[0]["cadence_hours"] == 24.0


def test_capped_pagination_span_warning_none_when_empty_L185():
    assert inv.capped_pagination_span_warning([]) is None


def test_capped_pagination_span_warning_message_content_L185(tmp_path):
    _write_settlement_tape(tmp_path, "2026-07-22", _narrow_capture("narrow", 7, 3.25, 200))
    msg = inv.capped_pagination_span_warning(inv._capped_pagination_span_issues(tmp_path))
    assert msg is not None
    assert "non-gating" in msg
    assert "settlement_ledger" in msg
    assert "close_time" in msg
    assert "24h" in msg
    assert "coverage ceiling" in msg
    assert "L185" in msg


def test_capped_pagination_span_warning_never_gates_exit_code_L185(monkeypatch, capsys):
    # ABSENCE OF EFFECT only. Whether this advisory prints on a real-tree run depends on LIVE
    # tape/settlement_ledger/ state that an hourly collector pass may write during the same run
    # (the same failure mode that turned the L152 advisory's real-tree text assertions red on
    # 2026-07-27, one ledger away). Its TEXT is pinned deterministically just below, and the
    # real-tape FACT it reports has its own acceptance test at the end of this section.
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "invariants: all green" in captured.out


def test_capped_pagination_span_advisory_is_wired_to_stderr_L185(monkeypatch, capsys):
    # The WIRING half of the split above, made deterministic: when the detector reports an
    # issue, --full prints the formatted advisory to STDERR and still exits 0.
    monkeypatch.setattr(
        inv, "_capped_pagination_span_issues",
        lambda *a, **kw: [{
            "family": "fake_family", "cap": 200, "cadence_hours": 24.0, "time_key": "close_time",
            "n_captures": 1, "n_captures_judged": 1, "n_captures_narrow": 1,
            "n_captures_not_judged": 0,
            "narrow_captures": [{"capture_id": "FAKECAP", "n_rows_with_time": 200,
                                 "span_hours": 1.0, "rows_per_hour": 200.0,
                                 "coverage_ceiling_fraction": 0.0417}],
        }],
    )
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "capped-pagination collector family" in captured.err
    assert "fake_family" in captured.err
    assert "invariants: all green" in captured.out


def test_capped_pagination_span_advisory_raise_cannot_flip_exit_code_L185(monkeypatch, capsys):
    """The L156 DEFECT-1 posture: even if the ISSUES COLLECTOR or the FORMATTER raises,
    the stanza's `except BaseException` guard keeps the advisory non-gating."""
    def _boom(*a, **kw):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(inv, "_capped_pagination_span_issues", _boom)
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "capped-pagination span advisory could not be computed" in captured.err
    assert "invariants: all green" in captured.out

    # And a non-str FORMATTER return, which makes the stanza's `+ "\n"` a TypeError — the
    # exact shape the L156 DEFECT-1 comment in main() warns about.
    monkeypatch.setattr(inv, "_capped_pagination_span_issues", lambda *a, **kw: [{"x": 1}])
    monkeypatch.setattr(inv, "capped_pagination_span_warning", lambda issues: 12345)
    assert inv.main() == 0


def test_acceptance_l185_settlement_ledger_real_tape_advisory_fires():
    """HARD acceptance against the real committed tape: settlement_ledger's 3 live
    captures span ~1.3-3.8h of close_time against a 24h firing interval, so the advisory
    fires and names them; the 605-row legacy backfill (span ~8 days) is NOT named."""
    fam = ROOT / "tape" / "settlement_ledger"
    if not fam.is_dir():
        pytest.skip("committed tape/settlement_ledger/ not present")
    issues = inv._capped_pagination_span_issues()
    assert len(issues) == 1, issues
    issue = issues[0]
    assert issue["family"] == "settlement_ledger"
    assert issue["n_captures"] == 4
    assert issue["n_captures_narrow"] == 3
    flagged = {c["capture_id"] for c in issue["narrow_captures"]}
    assert flagged == {"20260717T122243Z", "20260717T122302Z", "20260722T103141Z"}
    assert "20260717T122238Z" not in flagged  # the ~8-day legacy backfill
    msg = inv.capped_pagination_span_warning(issues)
    assert "20260722T103141Z" in msg
    assert "20260717T122238Z" not in msg


# ── L270: completeness-cap saturation — a leg whose completeness_ok is always False ──
#

def _write_capped_family(tape_root, family, day, cid, n_rows):
    import json as _json
    fam = tape_root / family
    fam.mkdir(parents=True, exist_ok=True)
    with open(fam / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        for _ in range(n_rows):
            f.write(_json.dumps({"capture_id": cid, "captured_at":
                                 f"{day}T00:00:00+00:00"}) + "\n")


def test_completeness_cap_saturation_issues_missing_tape_root_is_empty_L270(tmp_path):
    assert inv._completeness_cap_saturation_issues(tmp_path / "nope") == []


def test_completeness_cap_saturation_issues_below_threshold_is_no_issue_L270(tmp_path):
    for i, day in enumerate(["2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23"]):
        n = 5000 if i == 0 else 300
        _write_capped_family(tmp_path, "settlement_ledger", day, f"c{i}", n)
    assert inv._completeness_cap_saturation_issues(tmp_path) == []


def test_completeness_cap_saturation_issues_finds_saturated_family_L270(tmp_path):
    for i, day in enumerate(["2026-07-20", "2026-07-21", "2026-07-22"]):
        _write_capped_family(tmp_path, "universe_sweep", day, f"c{i}", 20000)
    issues = inv._completeness_cap_saturation_issues(tmp_path)
    assert len(issues) == 1
    assert issues[0]["family"] == "universe_sweep"
    assert issues[0]["n_at_cap"] == 3
    assert issues[0]["fraction_at_cap"] == 1.0


def test_completeness_cap_saturation_warning_none_when_empty_L270():
    assert inv.completeness_cap_saturation_warning([]) is None


def test_completeness_cap_saturation_warning_message_content_L270(tmp_path):
    for i, day in enumerate(["2026-07-20", "2026-07-21", "2026-07-22"]):
        _write_capped_family(tmp_path, "universe_sweep", day, f"c{i}", 20000)
    msg = inv.completeness_cap_saturation_warning(
        inv._completeness_cap_saturation_issues(tmp_path))
    assert msg is not None
    assert "non-gating" in msg
    assert "universe_sweep" in msg
    assert "3/3" in msg
    assert "20000" in msg
    assert "L270" in msg


def test_completeness_cap_saturation_warning_never_gates_exit_code_L270(monkeypatch, capsys):
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "invariants: all green" in captured.out


def test_completeness_cap_saturation_advisory_is_wired_to_stderr_L270(monkeypatch, capsys):
    monkeypatch.setattr(
        inv, "_completeness_cap_saturation_issues",
        lambda *a, **kw: [{"family": "fake_family", "cap": 200, "n_captures": 3,
                           "n_at_cap": 3, "fraction_at_cap": 1.0, "saturated": True}],
    )
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "STRUCTURALLY SATURATED" in captured.err
    assert "fake_family" in captured.err
    assert "invariants: all green" in captured.out


def test_completeness_cap_saturation_advisory_raise_cannot_flip_exit_code_L270(
        monkeypatch, capsys):
    """The L156 DEFECT-1 posture: even if the ISSUES COLLECTOR or the FORMATTER raises,
    the stanza's `except BaseException` guard keeps the advisory non-gating."""
    def _boom(*a, **kw):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(inv, "_completeness_cap_saturation_issues", _boom)
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "completeness-cap saturation advisory could not be computed" in captured.err
    assert "invariants: all green" in captured.out

    monkeypatch.setattr(inv, "_completeness_cap_saturation_issues", lambda *a, **kw: [{"x": 1}])
    monkeypatch.setattr(inv, "completeness_cap_saturation_warning", lambda issues: 12345)
    assert inv.main() == 0


def test_acceptance_l270_universe_sweep_real_tape_advisory_fires():
    """HARD acceptance against the real committed tape: every committed
    `universe_sweep` capture sits exactly at its 20,000-row page cap, so the
    advisory fires and names it."""
    fam = ROOT / "tape" / "universe_sweep"
    if not fam.is_dir():
        pytest.skip("committed tape/universe_sweep/ not present")
    issues = inv._completeness_cap_saturation_issues()
    matches = [i for i in issues if i["family"] == "universe_sweep"]
    assert len(matches) == 1, issues
    issue = matches[0]
    assert issue["cap"] == 20000
    assert issue["fraction_at_cap"] == 1.0
    msg = inv.completeness_cap_saturation_warning(issues)
    assert "universe_sweep" in msg


def test_acceptance_l270_settlement_ledger_real_tape_not_flagged():
    """settlement_ledger shares the bounded-cap SHAPE but is measured, not assumed,
    to sit below the saturation threshold on real tape — must not appear in the
    advisory's issue list."""
    fam = ROOT / "tape" / "settlement_ledger"
    if not fam.is_dir():
        pytest.skip("committed tape/settlement_ledger/ not present")
    issues = inv._completeness_cap_saturation_issues()
    families = {i["family"] for i in issues}
    assert "settlement_ledger" not in families, issues


# ── L205: dangling pytest node-id citations in kb/ / findings/ / LOOP-QUEUE.md ──
#
# A ledger row cites a test by node id AS ITS ENFORCEMENT EVIDENCE. The lane that owns tests
# may not edit kb/, so a rename there leaves a citation the renaming agent cannot repair and
# the kb lane cannot see. These fixtures are constructed negatives (L155): they are the
# advisory's ONLY coverage claim — a quiet real tree is never evidence of recall.


def _citation_tree(tmp_path, docs, tests):
    """Build a fake repo root: `docs` = {relpath: text}, `tests` = {filename: text}."""
    for rel, text in docs.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    tdir = tmp_path / "tests"
    tdir.mkdir(parents=True, exist_ok=True)
    for name, text in tests.items():
        (tdir / name).write_text(text)
    return tmp_path


def test_cited_test_node_resolves_when_the_test_exists_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/lessons/00-lessons.md": "pinned by `tests/test_alpha.py::test_one_thing`."},
        {"test_alpha.py": "def test_one_thing():\n    assert True\n"},
    )
    assert inv._cited_test_node_issues(tmp_path) == []


def test_cited_test_node_flags_a_renamed_test_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/lessons/00-lessons.md": "pinned by `tests/test_alpha.py::test_old_name`."},
        {"test_alpha.py": "def test_new_name():\n    assert True\n"},
    )
    issues = inv._cited_test_node_issues(tmp_path)
    assert len(issues) == 1, issues
    assert issues[0].startswith("kb/lessons/00-lessons.md:1:")
    assert "test_old_name" in issues[0]
    assert "tests/test_alpha.py" in issues[0]


def test_cited_test_node_flags_a_test_that_moved_to_another_file_L205(tmp_path):
    """Path-qualified citations are checked AGAINST THAT FILE — a move is a dangling citation."""
    _citation_tree(
        tmp_path,
        {"findings/f.md": "see `tests/test_alpha.py::test_moved`"},
        {"test_alpha.py": "def test_stayed():\n    pass\n",
         "test_beta.py": "def test_moved():\n    pass\n"},
    )
    issues = inv._cited_test_node_issues(tmp_path)
    assert len(issues) == 1, issues
    assert "test_moved" in issues[0]


def test_cited_test_node_bare_continuation_resolves_across_files_L205(tmp_path):
    """`::test_x` with no path is the ledger's second-node-id-in-one-cell shape: it resolves
    against the union of every test name (weaker, and documented as such)."""
    _citation_tree(
        tmp_path,
        {"kb/00-LOG.md": "`tests/test_alpha.py::test_one`, `::test_two`, `::test_absent`"},
        {"test_alpha.py": "def test_one():\n    pass\n",
         "test_beta.py": "def test_two():\n    pass\n"},
    )
    issues = inv._cited_test_node_issues(tmp_path)
    assert len(issues) == 1, issues
    assert "test_absent" in issues[0]


def test_cited_test_node_missing_file_is_reported_as_a_file_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/00-LOG.md": "`tests/test_gone.py::test_one`"},
        {"test_alpha.py": "def test_one():\n    pass\n"},
    )
    issues = inv._cited_test_node_issues(tmp_path)
    assert len(issues) == 1, issues
    assert "no such test file" in issues[0]


def test_cited_test_node_basename_only_path_resolves_L205(tmp_path):
    """Both `tests/test_alpha.py::x` and the bare-filename shape appear in the ledger."""
    _citation_tree(
        tmp_path,
        {"LOOP-QUEUE.md": "`test_alpha.py::test_one`"},
        {"test_alpha.py": "def test_one():\n    pass\n"},
    )
    assert inv._cited_test_node_issues(tmp_path) == []


@pytest.mark.parametrize("cited", [
    "`tests/test_alpha.py::test_parse_iso_utc_*`",
    "`tests/test_alpha.py::test_parse_iso_utc_...`",
    "`tests/test_alpha.py::test_parse_iso_utc_`",
])
def test_cited_test_node_elided_family_citation_resolves_by_prefix_L205(tmp_path, cited):
    _citation_tree(
        tmp_path,
        {"kb/lessons/00-lessons.md": f"7 cases: {cited}"},
        {"test_alpha.py": "def test_parse_iso_utc_short_fraction():\n    pass\n"},
    )
    assert inv._cited_test_node_issues(tmp_path) == []


def test_cited_test_node_elided_citation_with_no_family_is_flagged_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/lessons/00-lessons.md": "`tests/test_alpha.py::test_parse_iso_utc_*`"},
        {"test_alpha.py": "def test_something_else():\n    pass\n"},
    )
    issues = inv._cited_test_node_issues(tmp_path)
    assert len(issues) == 1, issues
    assert "test_parse_iso_utc_" in issues[0]


def test_cited_test_node_too_short_elision_is_skipped_not_vacuously_passed_L205(tmp_path):
    """`::test_*` would prefix-match nearly every test; it is skipped as uninformative."""
    _citation_tree(
        tmp_path,
        {"kb/00-LOG.md": "`::test_*` is the grammar"},
        {"test_alpha.py": "def test_one():\n    pass\n"},
    )
    assert len(inv.CITATION_PLACEHOLDER_NAMES) > 0
    assert inv.CITATION_MIN_PREFIX_LEN > len("test_")
    assert inv._cited_test_node_issues(tmp_path) == []


@pytest.mark.parametrize("placeholder", sorted(inv.CITATION_PLACEHOLDER_NAMES))
def test_cited_test_node_metasyntactic_placeholders_are_skipped_L205(tmp_path, placeholder):
    _citation_tree(
        tmp_path,
        {"kb/00-LOG.md": f"the grammar is `path/to/file.py::{placeholder}`"},
        {"test_alpha.py": "def test_one():\n    pass\n"},
    )
    assert inv._cited_test_node_issues(tmp_path) == []


def test_cited_test_node_counts_async_defs_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/00-LOG.md": "`tests/test_alpha.py::test_async_one`"},
        {"test_alpha.py": "async def test_async_one():\n    pass\n"},
    )
    assert inv._cited_test_node_issues(tmp_path) == []


def test_cited_test_node_only_scans_the_declared_doc_roots_L205(tmp_path):
    """A dangling citation in a doc OUTSIDE kb/ / findings/ / LOOP-QUEUE.md is out of scope
    (README/agent charters are not the ledger's enforcement-evidence surface)."""
    _citation_tree(
        tmp_path,
        {"docs/notes.md": "`tests/test_alpha.py::test_absent`",
         "kb/00-LOG.md": "`tests/test_alpha.py::test_one`"},
        {"test_alpha.py": "def test_one():\n    pass\n"},
    )
    assert inv._cited_test_node_issues(tmp_path) == []
    assert inv.TEST_CITATION_DOC_GLOBS == ("kb/**/*.md", "findings/**/*.md", "LOOP-QUEUE.md")


def test_cited_test_node_issues_are_deduplicated_and_sorted_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/00-LOG.md": "`tests/test_alpha.py::test_absent` and `tests/test_alpha.py::test_absent`",
         "findings/f.md": "`tests/test_alpha.py::test_absent`"},
        {"test_alpha.py": "def test_one():\n    pass\n"},
    )
    issues = inv._cited_test_node_issues(tmp_path)
    assert len(issues) == 2, issues          # one per (doc, line), not per occurrence
    assert issues == sorted(issues)


def test_cited_test_node_missing_tree_is_empty_L205(tmp_path):
    assert inv._cited_test_node_issues(tmp_path / "nope") == []


def test_dangling_test_citation_warning_none_when_empty_L205():
    assert inv.dangling_test_citation_warning([]) is None


def test_dangling_test_citation_warning_message_content_L205(tmp_path):
    _citation_tree(
        tmp_path,
        {"kb/lessons/00-lessons.md": "`tests/test_alpha.py::test_old_name`"},
        {"test_alpha.py": "def test_new_name():\n    pass\n"},
    )
    msg = inv.dangling_test_citation_warning(inv._cited_test_node_issues(tmp_path))
    assert msg is not None
    assert "non-gating" in msg
    assert "test_old_name" in msg
    assert "L205" in msg


def test_dangling_test_citation_advisory_is_wired_to_stderr_L205(monkeypatch, capsys):
    monkeypatch.setattr(
        inv, "_cited_test_node_issues",
        lambda *a, **kw: ["kb/fake.md:1: `tests/test_fake.py::test_gone` -- no `def test_gone(`"],
    )
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "pytest node-id citation" in captured.err
    assert "test_gone" in captured.err
    assert "invariants: all green" in captured.out


def test_dangling_test_citation_advisory_raise_cannot_flip_exit_code_L205(monkeypatch, capsys):
    """The L156 DEFECT-1 posture: neither a raising detector nor a non-str formatter return
    (which makes the stanza's `+ "\\n"` a TypeError) may reach the exit code."""
    def _boom(*a, **kw):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(inv, "_cited_test_node_issues", _boom)
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "dangling-test-citation advisory could not be computed" in captured.err
    assert "invariants: all green" in captured.out

    monkeypatch.setattr(inv, "_cited_test_node_issues", lambda *a, **kw: ["x"])
    monkeypatch.setattr(inv, "dangling_test_citation_warning", lambda issues: 12345)
    assert inv.main() == 0


def test_dangling_citation_real_tree_resolution_is_structural_L205():
    """LIVE-TREE half, deliberately kept STRUCTURAL (L191/L192): kb/ and findings/ grow every
    run, so pinning a hit COUNT here would make an unrelated future document turn this red.
    Asserted instead: the detector never raises, every issue names one of the declared doc
    roots, and a synthetic doc citing THIS test by node id resolves against the real tests/
    tree -- a self-referential positive control that breaks if this very test is renamed,
    which is exactly the L205 failure mode being demonstrated."""
    issues = inv._cited_test_node_issues()
    assert isinstance(issues, list)
    assert all(isinstance(i, str) for i in issues)
    assert all(
        i.startswith(("kb/", "findings/", "LOOP-QUEUE.md")) for i in issues
    ), issues
    per_file, every = inv._test_def_index(ROOT / "tests")
    assert "test_dangling_citation_real_tree_resolution_is_structural_L205" in every
    assert (
        "test_dangling_citation_real_tree_resolution_is_structural_L205"
        in per_file["test_invariants.py"]
    )


# ─── L210: colliding-capture_id advisory (non-gating) ──────────────────────────


def _write_cap_tape(tape_root, family, day, records):
    import json as _json
    fam = tape_root / family
    fam.mkdir(parents=True, exist_ok=True)
    with open(fam / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(_json.dumps(rec) + "\n")


def _perp_collision_rows():
    base = {"capture_id": "20260717T010032Z", "record_type": "funding_rates",
            "venue": "kalshi_perps"}
    return [
        dict(base, captured_at="2026-07-17T01:00:32.634200+00:00", mode="backfill",
             n_prints=1447),
        dict(base, captured_at="2026-07-17T01:00:32.886118+00:00", mode="recent",
             n_prints=39),
    ]


def test_duplicate_capture_id_issues_missing_tape_root_is_empty_L210(tmp_path):
    assert inv._duplicate_capture_id_issues(tmp_path / "nope") == []


def test_duplicate_capture_id_issues_clean_tape_is_empty_L210(tmp_path):
    _write_cap_tape(tmp_path, "perp_tape", "2026-07-17", [
        {"capture_id": "c1", "captured_at": "2026-07-17T01:00:32.6+00:00",
         "record_type": "orderbook", "ticker": "KXBTCPERP"},
        {"capture_id": "c1", "captured_at": "2026-07-17T01:00:32.6+00:00",
         "record_type": "orderbook", "ticker": "KXETHPERP"},
    ])
    assert inv._duplicate_capture_id_issues(tmp_path) == []


def test_duplicate_capture_id_issues_finds_two_invocations_L210(tmp_path):
    _write_cap_tape(tmp_path, "perp_tape", "2026-07-17", _perp_collision_rows())
    issues = inv._duplicate_capture_id_issues(tmp_path)
    assert len(issues) == 1
    assert issues[0]["family"] == "perp_tape"
    assert issues[0]["n_collisions"] == 1


def test_duplicate_capture_id_issues_ladder_walk_is_no_issue_L210(tmp_path):
    """A single pass walking a strike ladder stamps many captured_at under one
    capture_id — the advisory must stay silent (the false-positive that a naive
    uniqueness rule would produce)."""
    _write_cap_tape(tmp_path, "weather_books", "2026-07-16", [
        {"capture_id": "b1", "captured_at": f"2026-07-16T20:28:39.{i}+00:00",
         "ticker": f"KXTEMPNYCH-T8{i}.99"} for i in range(1, 6)
    ])
    assert inv._duplicate_capture_id_issues(tmp_path) == []


def test_duplicate_capture_id_warning_none_when_empty_L210():
    assert inv.duplicate_capture_id_warning([]) is None


def test_duplicate_capture_id_warning_message_content_L210(tmp_path):
    _write_cap_tape(tmp_path, "perp_tape", "2026-07-17", _perp_collision_rows())
    msg = inv.duplicate_capture_id_warning(inv._duplicate_capture_id_issues(tmp_path))
    assert msg is not None
    assert "non-gating" in msg
    assert "perp_tape" in msg
    assert "20260717T010032Z" in msg
    assert "mode" in msg
    assert "L210" in msg
    # The advisory must state its own false-positive exemption, so a reader can tell
    # what a clean report does and does not mean (L155).
    assert "capture_seq" in msg


def test_duplicate_capture_id_issues_never_raises_on_garbage_L210(tmp_path):
    """Best-effort contract: a malformed tree yields [] rather than poisoning the gate."""
    fam = tmp_path / "perp_tape"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-17.jsonl").write_bytes(b"\xff\xfe not json at all\n")
    assert inv._duplicate_capture_id_issues(tmp_path) == []


# ─── econ-prints settlement-status regression advisory (L223: non-gating) ────────

def _econ_row(series_key, captured_at, status, event_ticker=None):
    return {"series_key": series_key, "captured_at": captured_at,
            "recent_settlement": {"status": status, "event_ticker": event_ticker}}


# ─── weather_books meta duplicate-(series,group)-per-day advisory (L281, corrects L84) ──

def _write_meta_tape(tape_root, day, records):
    import json as _json
    meta = tape_root / "weather_books" / "meta"
    meta.mkdir(parents=True, exist_ok=True)
    with open(meta / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(_json.dumps(rec) + "\n")


def _meta_row(series, group, capture_id, captured_at="2026-07-27T04:00:36+00:00",
              rules_primary="rules text", sample_ticker="KX-SAMPLE"):
    return {"schema_version": "weather_series_meta.v1", "capture_id": capture_id,
            "captured_at": captured_at, "venue": "kalshi", "group": group, "series": series,
            "title": "a title", "settlement_sources": ["NWS"], "fee_type": "quadratic",
            "fee_multiplier": 1.0, "frequency": "hourly", "contract_url": "http://x",
            "rules_primary": rules_primary, "rules_secondary": None,
            "sample_ticker": sample_ticker, "detail_error": None}


def test_weather_books_meta_duplicate_issues_missing_tape_root_is_empty_L281(tmp_path):
    assert inv._weather_books_meta_duplicate_issues(tmp_path / "nope") == []


def test_weather_books_meta_duplicate_issues_missing_meta_dir_is_empty_L281(tmp_path):
    (tmp_path / "weather_books").mkdir(parents=True)
    assert inv._weather_books_meta_duplicate_issues(tmp_path) == []


def test_weather_books_meta_duplicate_issues_clean_day_is_empty_L281(tmp_path):
    """The normal, single-writer case: one row per (series, group), no duplicates."""
    _write_meta_tape(tmp_path, "2026-07-20", [
        _meta_row("KXTEMPNYCH", "hourly", "c1"),
        _meta_row("KXHIGHNY", "daily", "c1"),
    ])
    assert inv._weather_books_meta_duplicate_issues(tmp_path) == []


def test_weather_books_meta_duplicate_issues_same_series_different_group_is_not_a_dup_L281(
        tmp_path):
    """The uniqueness key is (series, group), not series alone."""
    _write_meta_tape(tmp_path, "2026-07-20", [
        _meta_row("KXFOO", "hourly", "c1"),
        _meta_row("KXFOO", "daily", "c1"),
    ])
    assert inv._weather_books_meta_duplicate_issues(tmp_path) == []


def test_weather_books_meta_duplicate_issues_finds_byte_identical_duplicate_L281(tmp_path):
    """Two branch-local passes racing the same day, both writing the identical sample."""
    _write_meta_tape(tmp_path, "2026-08-09", [
        _meta_row("KXTEMPNYCH", "hourly", "c1", rules_primary="same", sample_ticker="KX-A"),
        _meta_row("KXTEMPNYCH", "hourly", "c2", rules_primary="same", sample_ticker="KX-A"),
    ])
    issues = inv._weather_books_meta_duplicate_issues(tmp_path, allowlist=frozenset())
    assert len(issues) == 1
    issue = issues[0]
    assert issue["day"] == "2026-08-09"
    assert issue["n_duplicate_keys"] == 1
    assert issue["n_keys"] == 1
    assert issue["allowlisted"] is False
    dup = issue["duplicates"][0]
    assert dup["series"] == "KXTEMPNYCH" and dup["group"] == "hourly"
    assert dup["n"] == 2
    assert dup["capture_ids"] == ["c1", "c2"]
    assert dup["differing_fields"] == []  # byte-identical modulo capture_id/captured_at


def test_weather_books_meta_duplicate_issues_content_differs_is_reported_L281(tmp_path):
    """The real 2026-07-27 shape: two racing passes sample DIFFERENT contract instances, so
    rules_primary/sample_ticker genuinely disagree, not just capture_id/captured_at."""
    _write_meta_tape(tmp_path, "2026-08-09", [
        _meta_row("KXTEMPAUSH", "hourly", "c1", rules_primary="above 82.99", sample_ticker="A"),
        _meta_row("KXTEMPAUSH", "hourly", "c2", rules_primary="above 83.99", sample_ticker="B"),
    ])
    issues = inv._weather_books_meta_duplicate_issues(tmp_path, allowlist=frozenset())
    assert len(issues) == 1
    dup = issues[0]["duplicates"][0]
    assert set(dup["differing_fields"]) == {"rules_primary", "sample_ticker"}


def test_weather_books_meta_duplicate_issues_allowlisted_day_is_flagged_L281(tmp_path):
    _write_meta_tape(tmp_path, "2026-07-27", [
        _meta_row("KXTEMPNYCH", "hourly", "c1"),
        _meta_row("KXTEMPNYCH", "hourly", "c2"),
    ])
    issues = inv._weather_books_meta_duplicate_issues(
        tmp_path, allowlist=frozenset({"2026-07-27"}))
    assert len(issues) == 1
    assert issues[0]["allowlisted"] is True


def test_weather_books_meta_duplicate_issues_never_raises_on_garbage_L281(tmp_path):
    meta = tmp_path / "weather_books" / "meta"
    meta.mkdir(parents=True)
    (meta / "dt=2026-07-27.jsonl").write_bytes(b"\xff\xfe not json at all\n")
    assert inv._weather_books_meta_duplicate_issues(tmp_path) == []


def test_weather_books_meta_duplicate_issues_missing_series_field_is_skipped_L281(tmp_path):
    _write_meta_tape(tmp_path, "2026-07-27", [
        {"group": "hourly", "capture_id": "c1"},   # no "series" — must not KeyError
        {"group": "hourly", "capture_id": "c2"},
    ])
    assert inv._weather_books_meta_duplicate_issues(tmp_path) == []


def test_weather_books_meta_duplicate_warning_none_when_empty_L281():
    assert inv.weather_books_meta_duplicate_warning([]) is None


def test_weather_books_meta_duplicate_warning_new_regression_content_L281(tmp_path):
    _write_meta_tape(tmp_path, "2026-08-09", [
        _meta_row("KXTEMPNYCH", "hourly", "c1"),
        _meta_row("KXTEMPNYCH", "hourly", "c2"),
    ])
    issues = inv._weather_books_meta_duplicate_issues(tmp_path, allowlist=frozenset())
    msg = inv.weather_books_meta_duplicate_warning(issues)
    assert msg is not None
    assert "non-gating" in msg
    assert "NEW regression" in msg
    assert "2026-08-09" in msg
    assert "L281" in msg


def test_weather_books_meta_duplicate_warning_known_incident_content_L281(tmp_path):
    _write_meta_tape(tmp_path, "2026-07-27", [
        _meta_row("KXTEMPNYCH", "hourly", "c1"),
        _meta_row("KXTEMPNYCH", "hourly", "c2"),
    ])
    issues = inv._weather_books_meta_duplicate_issues(
        tmp_path, allowlist=frozenset({"2026-07-27"}))
    msg = inv.weather_books_meta_duplicate_warning(issues)
    assert msg is not None
    assert "known historical incident" in msg
    assert "dt=2026-07-27" in msg
    assert "L84" in msg
    assert "NEW regression" not in msg   # allowlisted day is not reported as fresh


def test_weather_books_meta_duplicate_warning_never_gates_exit_code_L281(monkeypatch, capsys):
    monkeypatch.setattr(
        inv, "_weather_books_meta_duplicate_issues",
        lambda: [{"day": "2026-01-01", "n_duplicate_keys": 1, "n_keys": 1,
                  "allowlisted": False,
                  "duplicates": [{"series": "FAKE", "group": "hourly", "n": 2,
                                  "capture_ids": ["c1", "c2"], "differing_fields": []}]}])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "2026-01-01" in captured.err
    assert "invariants: all green" in captured.out


def test_acceptance_l281_real_tape_reproduces_the_2026_07_27_incident():
    """HARD acceptance against the real committed tape: dt=2026-07-27 carries exactly the
    incident this lesson names — 47 of 48 (series,group) keys duplicated, 5 with content
    that genuinely differs (not just capture metadata) — and it is reported as the KNOWN
    incident (allowlisted), never as a fresh regression."""
    fam = ROOT / "tape" / "weather_books" / "meta"
    if not fam.is_dir():
        pytest.skip("committed tape/weather_books/meta/ not present")
    issues = inv._weather_books_meta_duplicate_issues()
    by_day = {i["day"]: i for i in issues}
    assert "2026-07-27" in by_day, by_day
    issue = by_day["2026-07-27"]
    assert issue["allowlisted"] is True
    assert issue["n_duplicate_keys"] == 47
    assert issue["n_keys"] == 48
    n_content_differs = sum(1 for d in issue["duplicates"] if d["differing_fields"])
    assert n_content_differs == 5
    # every OTHER committed day-file must be clean — a second incident would be new information
    other_days_dirty = [i["day"] for i in issues if i["day"] != "2026-07-27"]
    assert other_days_dirty == [], other_days_dirty
    msg = inv.weather_books_meta_duplicate_warning(issues)
    assert msg is not None
    assert "known historical incident" in msg
    assert "NEW regression" not in msg


# ─── orderbook_depth duplicate-(capture_id,ticker) advisory (L282, corrects L84 a 3rd time) ──

def _write_ob_tape(tape_root, day, records):
    import json as _json
    fam = tape_root / "orderbook_depth"
    fam.mkdir(parents=True, exist_ok=True)
    with open(fam / f"dt={day}.jsonl", "w", encoding="utf-8") as f:
        for rec in records:
            f.write(_json.dumps(rec) + "\n")


def _ob_row(ticker, capture_id, captured_at="2026-07-28T06:56:16.273008+00:00",
            best_yes_bid=0.47, raw_sha256="deadbeef"):
    return {"schema_version": "orderbook_depth.v1", "capture_id": capture_id,
            "captured_at": captured_at, "venue": "kalshi", "ticker": ticker,
            "yes_bids": [[best_yes_bid, 10.0]], "no_bids": [[0.51, 5.0]],
            "best_yes_bid": best_yes_bid, "best_no_bid": 0.51,
            "best_yes_ask": round(1 - 0.51, 2), "best_no_ask": round(1 - best_yes_bid, 2),
            "depth": 2, "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
            "raw_sha256": raw_sha256}


def test_orderbook_depth_duplicate_issues_missing_tape_root_is_empty_L282(tmp_path):
    assert inv._orderbook_depth_duplicate_capture_issues(tmp_path / "nope") == []


def test_orderbook_depth_duplicate_issues_missing_family_dir_is_empty_L282(tmp_path):
    assert inv._orderbook_depth_duplicate_capture_issues(tmp_path) == []


def test_orderbook_depth_duplicate_issues_clean_day_is_empty_L282(tmp_path):
    """The normal, single-writer case: one row per (capture_id, ticker), no duplicates."""
    _write_ob_tape(tmp_path, "2026-07-20", [
        _ob_row("KXFOO-A", "c1"), _ob_row("KXFOO-B", "c1"), _ob_row("KXFOO-A", "c2"),
    ])
    assert inv._orderbook_depth_duplicate_capture_issues(tmp_path, allowlist=frozenset()) == []


def test_orderbook_depth_duplicate_issues_same_ticker_different_capture_is_not_a_dup_L282(
        tmp_path):
    """The uniqueness key is (capture_id, ticker) — repeat passes on the same ticker across
    DIFFERENT passes are the normal, expected shape."""
    _write_ob_tape(tmp_path, "2026-07-20", [
        _ob_row("KXFOO-A", "c1"), _ob_row("KXFOO-A", "c2"),
    ])
    assert inv._orderbook_depth_duplicate_capture_issues(tmp_path, allowlist=frozenset()) == []


def test_orderbook_depth_duplicate_issues_finds_byte_identical_duplicate_L282(tmp_path):
    """Two racing branch-local commits, each appending the same pass's row for this ticker."""
    _write_ob_tape(tmp_path, "2026-08-09", [
        _ob_row("KXFOO-A", "c1"), _ob_row("KXFOO-A", "c1"),
    ])
    issues = inv._orderbook_depth_duplicate_capture_issues(tmp_path, allowlist=frozenset())
    assert len(issues) == 1
    issue = issues[0]
    assert issue["day"] == "2026-08-09"
    assert issue["n_duplicate_keys"] == 1
    assert issue["n_keys"] == 1
    assert issue["allowlisted"] is False
    dup = issue["duplicates"][0]
    assert dup["ticker"] == "KXFOO-A" and dup["capture_id"] == "c1"
    assert dup["n"] == 2
    assert dup["differing_fields"] == []  # byte-identical


def test_orderbook_depth_duplicate_issues_content_differs_is_reported_L282(tmp_path):
    _write_ob_tape(tmp_path, "2026-08-09", [
        _ob_row("KXFOO-A", "c1", best_yes_bid=0.47, raw_sha256="aaa"),
        _ob_row("KXFOO-A", "c1", best_yes_bid=0.52, raw_sha256="bbb"),
    ])
    issues = inv._orderbook_depth_duplicate_capture_issues(tmp_path, allowlist=frozenset())
    dup = issues[0]["duplicates"][0]
    assert "best_yes_bid" in dup["differing_fields"]
    assert "raw_sha256" in dup["differing_fields"]


def test_orderbook_depth_duplicate_issues_allowlisted_day_is_flagged_L282(tmp_path):
    _write_ob_tape(tmp_path, "2026-07-28", [
        _ob_row("KXFOO-A", "c1"), _ob_row("KXFOO-A", "c1"),
    ])
    issues = inv._orderbook_depth_duplicate_capture_issues(
        tmp_path, allowlist=frozenset({"2026-07-28"}))
    assert len(issues) == 1
    assert issues[0]["allowlisted"] is True


def test_orderbook_depth_duplicate_issues_never_raises_on_garbage_L282(tmp_path):
    fam = tmp_path / "orderbook_depth"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-28.jsonl").write_bytes(b"\xff\xfe not json at all\n")
    assert inv._orderbook_depth_duplicate_capture_issues(tmp_path) == []


def test_orderbook_depth_duplicate_issues_missing_ticker_field_is_skipped_L282(tmp_path):
    _write_ob_tape(tmp_path, "2026-07-28", [
        {"capture_id": "c1"}, {"capture_id": "c1"},   # no "ticker" — must not KeyError
    ])
    assert inv._orderbook_depth_duplicate_capture_issues(tmp_path) == []


def test_orderbook_depth_duplicate_warning_none_when_empty_L282():
    assert inv.orderbook_depth_duplicate_capture_warning([]) is None


def test_orderbook_depth_duplicate_warning_new_regression_content_L282(tmp_path):
    _write_ob_tape(tmp_path, "2026-08-09", [
        _ob_row("KXFOO-A", "c1"), _ob_row("KXFOO-A", "c1"),
    ])
    issues = inv._orderbook_depth_duplicate_capture_issues(tmp_path, allowlist=frozenset())
    msg = inv.orderbook_depth_duplicate_capture_warning(issues)
    assert msg is not None
    assert "non-gating" in msg
    assert "NEW regression" in msg
    assert "2026-08-09" in msg
    assert "L282" in msg


def test_orderbook_depth_duplicate_warning_known_incident_content_L282(tmp_path):
    _write_ob_tape(tmp_path, "2026-07-28", [
        _ob_row("KXFOO-A", "c1"), _ob_row("KXFOO-A", "c1"),
    ])
    issues = inv._orderbook_depth_duplicate_capture_issues(
        tmp_path, allowlist=frozenset({"2026-07-28"}))
    msg = inv.orderbook_depth_duplicate_capture_warning(issues)
    assert msg is not None
    assert "known historical incident" in msg
    assert "dt=2026-07-28" in msg
    assert "L84" in msg
    assert "NEW regression" not in msg


def test_orderbook_depth_duplicate_warning_never_gates_exit_code_L282(monkeypatch, capsys):
    monkeypatch.setattr(
        inv, "_orderbook_depth_duplicate_capture_issues",
        lambda: [{"day": "2026-01-01", "n_duplicate_keys": 1, "n_keys": 1,
                  "allowlisted": False,
                  "duplicates": [{"ticker": "FAKE", "capture_id": "c1", "n": 2,
                                  "differing_fields": []}]}])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "2026-01-01" in captured.err
    assert "invariants: all green" in captured.out


def test_acceptance_l282_real_tape_reproduces_the_2026_07_28_incident():
    """HARD acceptance against the real committed tape: dt=2026-07-28 carries exactly the
    incident this lesson names — 1,093 duplicated (capture_id,ticker) keys, all byte-identical
    (0 with differing content) — and it is reported as the KNOWN incident (allowlisted), never
    as a fresh regression."""
    fam = ROOT / "tape" / "orderbook_depth"
    if not fam.is_dir():
        pytest.skip("committed tape/orderbook_depth/ not present")
    issues = inv._orderbook_depth_duplicate_capture_issues()
    by_day = {i["day"]: i for i in issues}
    assert "2026-07-28" in by_day, by_day
    issue = by_day["2026-07-28"]
    assert issue["allowlisted"] is True
    assert issue["n_duplicate_keys"] == 1093
    n_content_differs = sum(1 for d in issue["duplicates"] if d["differing_fields"])
    assert n_content_differs == 0
    # every OTHER committed day-file must be clean — a second incident would be new information
    other_days_dirty = [i["day"] for i in issues if i["day"] != "2026-07-28"]
    assert other_days_dirty == [], other_days_dirty
    msg = inv.orderbook_depth_duplicate_capture_warning(issues)
    assert msg is not None
    assert "known historical incident" in msg
    assert "NEW regression" not in msg


def test_econ_prints_settlement_regression_warning_none_when_empty():
    assert inv.econ_prints_settlement_regression_warning([]) is None


def test_econ_prints_settlement_regression_warning_message_content():
    msg = inv.econ_prints_settlement_regression_warning([{
        "series_key": "gdp", "last_settled_event_ticker": "KXGDP-26APR30",
        "streak": 340, "regression_since": "2026-07-06T09:24:18+00:00"}])
    assert msg is not None
    assert "gdp" in msg
    assert "KXGDP-26APR30" in msg
    assert "340" in msg
    assert "non-gating" in msg
    assert "L223" in msg


def test_econ_prints_settlement_regression_issues_finds_real_pattern(tmp_path):
    """Reproduces the real gdp-leg shape: one settlement, then a sustained regression."""
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-05", [
        _econ_row("gdp", "2026-07-05T05:17:04+00:00", "settled", "KXGDP-26APR30"),
        _econ_row("cpi_mom", "2026-07-05T05:17:04+00:00", "settled", "KXCPI-26MAY"),
    ])
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-06", [
        _econ_row("gdp", "2026-07-06T09:24:18+00:00", "no_settled_events"),
        _econ_row("cpi_mom", "2026-07-06T09:24:18+00:00", "settled", "KXCPI-26MAY"),
    ])
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-07", [
        _econ_row("gdp", "2026-07-07T09:24:18+00:00", "no_settled_events"),
        _econ_row("cpi_mom", "2026-07-07T09:24:18+00:00", "settled", "KXCPI-26MAY"),
    ])
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-08", [
        _econ_row("gdp", "2026-07-08T09:24:18+00:00", "no_settled_events"),
    ])
    issues = inv._econ_prints_settlement_regression_issues(tmp_path)
    assert issues == [{
        "series_key": "gdp", "last_settled_event_ticker": "KXGDP-26APR30",
        "streak": 3, "regression_since": "2026-07-06T09:24:18+00:00"}]


def test_econ_prints_settlement_regression_issues_below_threshold_is_empty(tmp_path):
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-05", [
        _econ_row("gdp", "2026-07-05T05:17:04+00:00", "settled", "KXGDP-26APR30"),
    ])
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-06", [
        _econ_row("gdp", "2026-07-06T09:24:18+00:00", "no_settled_events"),
        _econ_row("gdp", "2026-07-06T10:00:00+00:00", "no_settled_events"),
    ])
    assert inv._econ_prints_settlement_regression_issues(tmp_path) == []


def test_econ_prints_settlement_regression_issues_never_settled_is_not_a_regression(tmp_path):
    """A series with NO settlement history yet is the documented normal case, not a flag."""
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-05", [
        _econ_row("cpi_core_mom", "2026-07-05T05:17:04+00:00", "no_settled_events"),
        _econ_row("cpi_core_mom", "2026-07-06T05:17:04+00:00", "no_settled_events"),
        _econ_row("cpi_core_mom", "2026-07-07T05:17:04+00:00", "no_settled_events"),
    ])
    assert inv._econ_prints_settlement_regression_issues(tmp_path) == []


def test_econ_prints_settlement_regression_issues_settled_only_is_empty(tmp_path):
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-05", [
        _econ_row("payrolls", "2026-07-05T05:17:04+00:00", "settled", "KXPAYROLLS-26JUN"),
        _econ_row("payrolls", "2026-07-06T05:17:04+00:00", "settled", "KXPAYROLLS-26JUN"),
    ])
    assert inv._econ_prints_settlement_regression_issues(tmp_path) == []


def test_econ_prints_settlement_regression_issues_resets_after_resettlement(tmp_path):
    """A fresh real settlement resets the streak — only the TRAILING run counts, so a
    short post-resettlement gap below the threshold must not still read as the old
    regression."""
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-05", [
        _econ_row("cpi_yoy", "2026-07-05T00:00:00+00:00", "settled", "KXCPIYOY-26MAY"),
        _econ_row("cpi_yoy", "2026-07-06T00:00:00+00:00", "no_settled_events"),
        _econ_row("cpi_yoy", "2026-07-07T00:00:00+00:00", "no_settled_events"),
        _econ_row("cpi_yoy", "2026-07-08T00:00:00+00:00", "no_settled_events"),
        _econ_row("cpi_yoy", "2026-07-09T00:00:00+00:00", "settled", "KXCPIYOY-26JUN"),
        _econ_row("cpi_yoy", "2026-07-10T00:00:00+00:00", "no_settled_events"),
    ])
    assert inv._econ_prints_settlement_regression_issues(tmp_path) == []


def test_econ_prints_settlement_regression_issues_missing_family_dir_is_empty(tmp_path):
    tape_root = tmp_path / "tape"
    tape_root.mkdir()
    assert inv._econ_prints_settlement_regression_issues(tape_root) == []


def test_econ_prints_settlement_regression_issues_missing_tape_root_is_empty(tmp_path):
    assert inv._econ_prints_settlement_regression_issues(tmp_path / "does-not-exist") == []


def test_econ_prints_settlement_regression_issues_never_raises_on_garbage(tmp_path):
    fam = tmp_path / "econ_prints"
    fam.mkdir(parents=True)
    (fam / "dt=2026-07-05.jsonl").write_bytes(b"\xff\xfe not json at all\n")
    assert inv._econ_prints_settlement_regression_issues(tmp_path) == []


def test_econ_prints_settlement_regression_issues_min_streak_is_configurable(tmp_path):
    _write_cap_tape(tmp_path, "econ_prints", "2026-07-05", [
        _econ_row("gdp", "2026-07-05T00:00:00+00:00", "settled", "KXGDP-26APR30"),
        _econ_row("gdp", "2026-07-06T00:00:00+00:00", "no_settled_events"),
    ])
    issues = inv._econ_prints_settlement_regression_issues(tmp_path, min_streak=1)
    assert issues == [{
        "series_key": "gdp", "last_settled_event_ticker": "KXGDP-26APR30",
        "streak": 1, "regression_since": "2026-07-06T00:00:00+00:00"}]


def test_econ_prints_settlement_regression_warning_never_gates_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        inv, "_econ_prints_settlement_regression_issues",
        lambda: [{"series_key": "fake", "last_settled_event_ticker": "FAKE-1",
                  "streak": 5, "regression_since": "2026-01-01T00:00:00+00:00"}])
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "warning (non-gating)" in captured.err
    assert "fake" in captured.err
    assert "L223" in captured.err
    assert "invariants: all green" in captured.out


# ── L208: expected-window-grid coverage advisory (survivorship vs coverage) ────
#
# Detector-level behaviour is pinned in tests/test_tape_gap_monitor.py (including a
# FROZEN-slice real-tape acceptance test, L191). What is pinned HERE is the invariants
# side: issue extraction, formatting, wiring to stderr, and — the load-bearing part —
# that it can never flip the exit code.

def _write_perp_tape(tmp_path, day, records):
    fam = tmp_path / "perp_tape"
    fam.mkdir(parents=True, exist_ok=True)
    import json as _json
    with open(fam / f"dt={day}.jsonl", "a", encoding="utf-8") as f:
        for rec in records:
            f.write(_json.dumps(rec) + "\n")


def _fe_line(cid, captured_at, next_funding_time):
    return {"capture_id": cid, "captured_at": captured_at,
            "record_type": "funding_estimate", "ticker": "KXBTCPERP",
            "next_funding_time": next_funding_time, "venue": "kalshi_perps"}


def test_window_grid_issues_missing_tape_root_is_empty_L208(tmp_path):
    assert inv._window_grid_coverage_issues(tmp_path / "nope") == []


def test_window_grid_issues_full_coverage_is_no_issue_L208(tmp_path):
    _write_perp_tape(tmp_path, "2026-07-20", [
        _fe_line("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe_line("c2", "2026-07-20T09:00:00+00:00", "2026-07-20T12:00:00Z"),
        _fe_line("c3", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    assert inv._window_grid_coverage_issues(tmp_path) == []


def test_window_grid_issues_finds_zero_capture_window_L208(tmp_path):
    _write_perp_tape(tmp_path, "2026-07-20", [
        _fe_line("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe_line("c3", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    issues = inv._window_grid_coverage_issues(tmp_path)
    assert len(issues) == 1
    assert issues[0]["family"] == "perp_tape"
    assert issues[0]["n_windows_zero_capture"] == 1
    assert issues[0]["zero_capture_windows"] == ["2026-07-20T12:00:00+00:00"]


def test_window_grid_issues_offgrid_key_alone_is_an_issue_L208(tmp_path):
    """A boundary off the configured grid is reported even with full coverage — a
    cadence change would otherwise silently invalidate every window statistic."""
    _write_perp_tape(tmp_path, "2026-07-20", [
        _fe_line("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe_line("c_bad", "2026-07-20T07:00:00+00:00", "2026-07-20T08:00:00Z"),
    ])
    issues = inv._window_grid_coverage_issues(tmp_path)
    assert len(issues) == 1
    assert issues[0]["n_windows_zero_capture"] == 0
    assert issues[0]["n_offgrid_window_keys"] == 1


def test_window_grid_warning_none_when_empty_L208():
    assert inv.window_grid_coverage_warning([]) is None


def test_window_grid_warning_message_content_L208(tmp_path):
    _write_perp_tape(tmp_path, "2026-07-20", [
        _fe_line("c1", "2026-07-20T01:00:00+00:00", "2026-07-20T04:00:00Z"),
        _fe_line("c3", "2026-07-20T17:00:00+00:00", "2026-07-20T20:00:00Z"),
    ])
    msg = inv.window_grid_coverage_warning(inv._window_grid_coverage_issues(tmp_path))
    assert msg is not None
    assert "non-gating" in msg
    assert "perp_tape" in msg
    assert "next_funding_time" in msg
    assert "ZERO passes" in msg
    assert "2026-07-20T12:00:00+00:00" in msg
    assert "survivorship gap" in msg
    assert "L208" in msg


def test_window_grid_warning_caps_the_zero_window_list_L208():
    """A long outage must not flood the gate output — 5 examples, then a count."""
    zeros = [f"2026-07-{d:02d}T04:00:00+00:00" for d in range(10, 20)]
    msg = inv.window_grid_coverage_warning([{
        "family": "fake_family", "window_key": "next_funding_time", "window_hours": 8.0,
        "anchor_hour_utc": 4, "thin_max_passes": 1,
        "grid_start": "2026-07-10T04:00:00+00:00", "grid_end": "2026-07-19T04:00:00+00:00",
        "n_windows_expected": 10, "n_windows_observed": 0, "n_windows_zero_capture": 10,
        "zero_capture_windows": zeros, "n_windows_thin": 10,
        "path_inadequate_fraction": 1.0, "coverage_fraction": 0.0,
        "observed_only": {"median_passes": None, "min_passes": None, "max_passes": None},
        "grid_filled": {"median_passes": 0, "min_passes": 0, "max_passes": 0},
        "n_offgrid_window_keys": 0, "offgrid_examples": [],
        "n_rows_skipped_no_window_key": 0,
    }])
    assert "and 5 more zero-pass window(s)" in msg
    assert zeros[4] in msg and zeros[5] not in msg


def test_window_grid_advisory_is_wired_to_stderr_L208(monkeypatch, capsys):
    monkeypatch.setattr(
        inv, "_window_grid_coverage_issues",
        lambda *a, **kw: [{
            "family": "fake_family", "window_key": "next_funding_time", "window_hours": 8.0,
            "anchor_hour_utc": 4, "thin_max_passes": 1,
            "grid_start": "2026-07-20T04:00:00+00:00", "grid_end": "2026-07-20T20:00:00+00:00",
            "n_windows_expected": 3, "n_windows_observed": 2, "n_windows_zero_capture": 1,
            "zero_capture_windows": ["2026-07-20T12:00:00+00:00"], "n_windows_thin": 1,
            "path_inadequate_fraction": 0.3333, "coverage_fraction": 0.6667,
            "observed_only": {"median_passes": 1.0, "min_passes": 1, "max_passes": 1},
            "grid_filled": {"median_passes": 1, "min_passes": 0, "max_passes": 1},
            "n_offgrid_window_keys": 0, "offgrid_examples": [],
            "n_rows_skipped_no_window_key": 0,
        }],
    )
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "window-gridded tape family" in captured.err
    assert "fake_family" in captured.err
    assert "invariants: all green" in captured.out


def test_window_grid_advisory_raise_cannot_flip_exit_code_L208(monkeypatch, capsys):
    """L156 DEFECT-1 posture: a raise in the COLLECTOR or a non-str FORMATTER return
    must stay non-gating."""
    def _boom(*a, **kw):
        raise RuntimeError("detector exploded")

    monkeypatch.setattr(inv, "_window_grid_coverage_issues", _boom)
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "expected-window-grid advisory could not be computed" in captured.err
    assert "invariants: all green" in captured.out

    monkeypatch.setattr(inv, "_window_grid_coverage_issues", lambda *a, **kw: [{"x": 1}])
    monkeypatch.setattr(inv, "window_grid_coverage_warning", lambda issues: 12345)
    assert inv.main() == 0


def test_acceptance_l208_perp_tape_real_tape_advisory_fires():
    """HARD acceptance against real committed tape — STRUCTURAL only, deliberately.

    `tape/perp_tape/` is a live, still-growing family, so pinning its zero-window COUNT
    here would red-line the gate on ordinary capture with zero code change (L191). The
    exact numbers are pinned on a FROZEN day slice in
    tests/test_tape_gap_monitor.py::test_acceptance_9_l208_perp_tape_funding_grid_frozen_slice."""
    fam = ROOT / "tape" / "perp_tape"
    if not fam.is_dir():
        pytest.skip("committed tape/perp_tape/ not present")
    issues = inv._window_grid_coverage_issues()
    assert len(issues) <= 1
    if not issues:
        pytest.skip("perp_tape currently has full window coverage — nothing to assert")
    issue = issues[0]
    assert issue["family"] == "perp_tape"
    assert issue["window_key"] == "next_funding_time"
    assert issue["anchor_hour_utc"] == 4
    # Every committed boundary is on the collector's own 04/12/20Z grid.
    assert issue["n_offgrid_window_keys"] == 0
    # The survivorship point: the observed-only view can never show a 0.
    assert issue["grid_filled"]["min_passes"] == 0
    assert (issue["observed_only"]["min_passes"] or 0) >= 1
    msg = inv.window_grid_coverage_warning(issues)
    assert "perp_tape" in msg and "L208" in msg


# ─── L221: single-hour gate idempotence advisory (non-gating) ─────────────────────────

def test_l221_gate_hours_are_read_off_hourly_pass_never_redeclared():
    """The hour numbers must come from `collection/hourly_pass.py`'s own constants, so a
    collector-side hour change cannot silently desync this advisory."""
    hours = inv._single_hour_leg_gate_hours()
    assert hours, "no single-hour leg hours resolved from hourly_pass.py"
    for fam, h in hours.items():
        assert isinstance(h, int) and 0 <= h <= 23, (fam, h)
    # every registered family resolves
    registered = {f for fams in inv.SINGLE_HOUR_LEG_FAMILIES.values() for f in fams}
    assert registered == set(hours)


def test_l221_gate_hours_skip_a_constant_absent_from_the_source():
    """A registered constant that is NOT in the source is SKIPPED, never defaulted — guessing
    an hour would audit the wrong window and report a confident wrong answer."""
    out = inv._single_hour_leg_gate_hours(
        source="ECON_PRINTS_UTC_HOUR = 9\n",
        known={"ECON_PRINTS_UTC_HOUR": ("econ_prints",),
               "GONE_UTC_HOUR": ("phantom",)})
    assert out == {"econ_prints": 9}


def test_l221_gate_hours_reject_an_out_of_range_constant():
    out = inv._single_hour_leg_gate_hours(
        source="BAD_UTC_HOUR = 99\n", known={"BAD_UTC_HOUR": ("fam",)})
    assert out == {}


def test_l221_warning_is_none_when_there_are_no_issues():
    assert inv.single_hour_leg_idempotence_warning([]) is None


def test_l221_warning_names_its_limits_and_stays_non_gating_in_wording():
    msg = inv.single_hour_leg_idempotence_warning(["fam (gate hour 9Z): up to 5 pass(es)"])
    assert msg is not None
    for token in ("RATE gate", "IDEMPOTENCE gate", "does NOT affect the exit code",
                  "L221", "capture_source", "burst", "dedup KEY"):
        assert token in msg, token


def test_l221_issues_degrade_to_empty_on_a_missing_tape_root(tmp_path):
    """Best-effort/offline: an unreadable tape root can never poison the gate."""
    assert inv._single_hour_leg_idempotence_issues(tape_root=tmp_path / "nope") == []


def test_acceptance_l221_real_tape_advisory_fires_on_every_registered_leg():
    """HARD acceptance against real committed tape, STRUCTURAL (L191 — counts drift as tape
    grows, and are pinned on a FROZEN slice in tests/test_tape_gap_monitor.py
    ::test_acceptance_18_l221_econ_prints_frozen_slice_reproduces_the_recorded_54pct).

    The finding this pins: EVERY registered single-hour leg carries L221's defect — the
    hour-equality gate admitted repeat non-burst passes on the same UTC day. `econ_prints` is
    the row's own subject; `settlement_ledger` is the case a redundancy-only check would call
    clean (0.0% redundant, unique payload) and only the pass-count measure catches."""
    if not (ROOT / "tape" / "econ_prints").is_dir():
        pytest.skip("committed tape/econ_prints/ not present")
    issues = inv._single_hour_leg_idempotence_issues()
    assert issues, "expected the L221 advisory to fire on committed tape"
    joined = "\n".join(issues)
    assert "econ_prints (gate hour 9Z)" in joined
    assert "settlement_ledger (gate hour 10Z)" in joined
    msg = inv.single_hour_leg_idempotence_warning(issues)
    assert "L221" in msg and "does NOT affect the exit code" in msg

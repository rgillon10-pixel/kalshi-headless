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

def test_stale_unenforced_candidate_real_tree_is_currently_clean():
    # HARD acceptance test anchored to the real tree: as of this run, no genuinely-open
    # (enforcement column starting "**UNENFORCED**") lesson row names a backtick
    # `function_name()` candidate that already exists anywhere in the tree. This is the
    # currently-clean state, not a tautology — L105's row names an EXISTING function
    # (`_segment_bounds()`) but only in its LESSON text (background context, not a
    # candidate), which the lesson-text-exclusion below specifically must not flag.
    assert inv._stale_unenforced_candidate_issues() == []


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
    monkeypatch.setattr(inv.sys, "argv", ["invariants.py", "--full"])
    rc = inv.main()
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    assert "invariants: all green" in captured.out
    # The real tree is clean, so the advisory should not fire at all here.
    assert "UNENFORCED lesson row(s)" not in captured.err


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

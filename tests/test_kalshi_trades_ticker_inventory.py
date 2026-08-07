"""scripts/kalshi_trades_ticker_inventory.py — L292 made mechanical.

The load-bearing case is `test_acceptance_the_s81_shape_is_flagged_from_a_synthetic_registry`:
that is the exact registration L292 had to fold BY HAND on 2026-08-06 (an econ-print maker
whose markout surface does not exist), and it is the thing this detector exists to catch the
next time nobody notices.

Every real-tape acceptance test closes its window with `--max-day 2026-08-03` (L140): the
trade tape is expected to grow, and a pinned number over an open window rots into a false
failure the day the next capture lands.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = ROOT / "scripts" / "kalshi_trades_ticker_inventory.py"
_INVARIANTS = ROOT / "scripts" / "invariants.py"

# The closed window every real-tape pin below reads. The trade tape's only committed day.
M1_DAY = "2026-08-03"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


kt = _load(_SCRIPT, "_t_kt_inventory")
inv = _load(_INVARIANTS, "_t_kt_invariants")


# --------------------------------------------------------------------------- #
# series_of — refuses rather than guesses
# --------------------------------------------------------------------------- #
def test_series_of_reads_the_prefix_before_the_first_hyphen():
    assert kt.series_of("KXMLBGAME-26AUG03DETCLE-DET") == "KXMLBGAME"
    assert kt.series_of("KXAFLGAME-26AUG060530NMKBUL-BUL") == "KXAFLGAME"
    assert kt.series_of("KXBTC-26AUG0316-T113999.99") == "KXBTC"


def test_series_of_refuses_a_ticker_with_no_separable_series():
    """Inventing a series would put a fabricated family into an inventory a registration
    check then trusts — the `extract_completeness` no-signal-never-a-guess posture."""
    assert kt.series_of("KXMLBGAME") is None
    assert kt.series_of("") is None
    assert kt.series_of(None) is None
    assert kt.series_of(12345) is None


# --------------------------------------------------------------------------- #
# inventory over synthetic tape
# --------------------------------------------------------------------------- #
def _write_tape(tmp_path: Path, day: str, tickers) -> Path:
    d = tmp_path / "kalshi_trades"
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"dt={day}.jsonl", "w", encoding="utf-8") as fh:
        for t in tickers:
            fh.write(json.dumps({"ticker": t, "price_source_tag": "broker_truth",
                                 "trade_day": day}) + "\n")
    return tmp_path


def test_inventory_counts_prints_tickers_and_series(tmp_path):
    _write_tape(tmp_path, "2026-08-03",
                ["KXA-1-X", "KXA-1-X", "KXA-2-Y", "KXB-9-Z"])
    rep = kt.trade_tape_inventory(tmp_path)
    assert rep["n_lines"] == 4
    assert rep["n_series"] == 2
    assert rep["n_tickers"] == 3
    assert rep["series"]["KXA"] == {"n_prints": 3, "n_tickers": 2, "days": ["2026-08-03"]}
    assert rep["series"]["KXB"]["n_prints"] == 1


def test_inventory_series_are_ordered_by_print_count_descending(tmp_path):
    _write_tape(tmp_path, "2026-08-03", ["KXB-1-X", "KXA-1-X", "KXA-2-Y"])
    rep = kt.trade_tape_inventory(tmp_path)
    assert list(rep["series"]) == ["KXA", "KXB"]


def test_inventory_reports_malformed_and_ticker_less_lines_separately(tmp_path):
    d = tmp_path / "kalshi_trades"
    d.mkdir(parents=True)
    (d / "dt=2026-08-03.jsonl").write_text(
        '{"ticker": "KXA-1-X"}\n'
        "not json at all\n"
        '{"no_ticker_here": 1}\n'
        '{"ticker": "NOHYPHEN"}\n'
        "\n",
        encoding="utf-8",
    )
    rep = kt.trade_tape_inventory(tmp_path)
    assert rep["n_malformed"] == 1
    assert rep["n_lines_without_ticker"] == 1
    assert rep["n_tickers_without_parsable_series"] == 1
    assert rep["n_series"] == 1


def test_inventory_over_absent_family_is_an_honest_no_claim(tmp_path):
    """An un-collected family and a collected-but-empty one are different claims (L289/L296),
    so an absent family must never render as ABSENT for a token."""
    rep = kt.trade_tape_inventory(tmp_path)
    assert rep["n_days"] == 0 and rep["series"] == {}
    assert kt.series_coverage(rep, "KXCPI")["verdict"] == kt.UNKNOWN_NO_TAPE
    assert kt.series_coverage(rep, "KXCPI")["verdict"] != kt.ABSENT


def test_max_day_closes_the_window(tmp_path):
    _write_tape(tmp_path, "2026-08-03", ["KXA-1-X"])
    _write_tape(tmp_path, "2026-08-09", ["KXCPI-1-X"])
    assert kt.trade_tape_inventory(tmp_path)["n_series"] == 2
    frozen = kt.trade_tape_inventory(tmp_path, max_day="2026-08-03")
    assert frozen["n_days"] == 1 and frozen["n_series"] == 1
    assert kt.series_coverage(frozen, "KXCPI")["verdict"] == kt.ABSENT


# --------------------------------------------------------------------------- #
# coverage verdicts
# --------------------------------------------------------------------------- #
def test_coverage_is_covered_on_an_exact_series(tmp_path):
    _write_tape(tmp_path, "2026-08-03", ["KXMLBGAME-1-X"])
    rep = kt.trade_tape_inventory(tmp_path)
    v = kt.series_coverage(rep, "KXMLBGAME")
    assert v["verdict"] == kt.COVERED and v["matched_series"] == ["KXMLBGAME"]


def test_coverage_accepts_a_trailing_star_the_way_prose_writes_it(tmp_path):
    _write_tape(tmp_path, "2026-08-03", ["KXCPICORE-1-X"])
    rep = kt.trade_tape_inventory(tmp_path)
    assert kt.series_coverage(rep, "KXCPI*")["verdict"] == kt.COVERED


def test_prefix_matching_is_generous_and_that_bias_is_toward_not_flagging(tmp_path):
    """It can under-report an absence; it must never invent one."""
    _write_tape(tmp_path, "2026-08-03", ["KXBTC-1-X"])
    rep = kt.trade_tape_inventory(tmp_path)
    assert kt.series_coverage(rep, "KXB")["verdict"] == kt.COVERED   # generous, on purpose
    assert kt.series_coverage(rep, "KXETH")["verdict"] == kt.ABSENT  # never invented


def test_named_series_tokens_collapses_a_full_ticker_to_its_family():
    toks = kt.named_series_tokens(
        "targets `KXFEDDECISION-26SEP-H0` and KXCPI* but not KXFEDDECISION again")
    assert toks == ["KXCPI", "KXFEDDECISION"]


def test_named_series_tokens_on_prose_with_no_ticker_is_empty():
    assert kt.named_series_tokens("a generic series x price-bucket x regime design") == []
    assert kt.named_series_tokens(None) == []


# --------------------------------------------------------------------------- #
# the invariants advisory
# --------------------------------------------------------------------------- #
def _registry(tmp_path: Path, rows) -> Path:
    p = tmp_path / "00-index.md"
    p.write_text("| id | name |\n|---|---|\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return p


def test_acceptance_the_s81_shape_is_flagged_from_a_synthetic_registry(tmp_path):
    """L292's worked example, converted from a hand-check into a pinned regression.

    S81 (post-release econ-print spread-capture maker) named `KXCPI`/`KXNFP` as its markout
    surface on a trade tape that carries neither. It was folded by hand; this is the assert
    that catches the next one."""
    _write_tape(tmp_path, "2026-08-03", ["KXMLBGAME-1-X"])
    reg = _registry(tmp_path, [
        "| **S81** | econ-print maker | src | idea | low | markout from `tape/kalshi_trades/` "
        "on KXCPI* and KXNFP ladders |",
    ])
    rep = inv._kalshi_trades_registration_issues(registry_path=reg, tape_root=tmp_path)
    assert rep["n_anchored"] == 1
    assert [i["strategy"] for i in rep["uncovered"]] == ["S81"]
    assert dict(rep["uncovered"][0]["missing"]) == {"KXCPI": kt.ABSENT, "KXNFP": kt.ABSENT}
    msg = inv.kalshi_trades_registration_surface_warning(rep)
    assert "S81" in msg and "KXCPI" in msg and "L292" in msg


def test_a_covered_family_is_not_flagged(tmp_path):
    _write_tape(tmp_path, "2026-08-03", ["KXMLBGAME-1-X"])
    reg = _registry(tmp_path, [
        "| **S79** | flow taker | src | idea | low | `tape/kalshi_trades/` on KXMLBGAME |",
    ])
    rep = inv._kalshi_trades_registration_issues(registry_path=reg, tape_root=tmp_path)
    assert rep["uncovered"] == [] and rep["unscoped"] == [] and rep["n_covered"] == 1
    assert inv.kalshi_trades_registration_surface_warning(rep) is None


def test_an_unscoped_row_is_reported_in_its_own_class_not_as_a_defect(tmp_path):
    """L289: an absent key and a present zero are different claims. A row that names no
    series is a COVERAGE limit of this detector, never evidence the candidate is bad."""
    _write_tape(tmp_path, "2026-08-03", ["KXMLBGAME-1-X"])
    reg = _registry(tmp_path, [
        "| **S78** | toxicity maker | src | idea | low | `tape/kalshi_trades/` markout per "
        "series x price-bucket x regime |",
    ])
    rep = inv._kalshi_trades_registration_issues(registry_path=reg, tape_root=tmp_path)
    assert rep["unscoped"] == ["S78"] and rep["uncovered"] == []
    msg = inv.kalshi_trades_registration_surface_warning(rep)
    assert "NOT called a defect" in msg and "S78" in msg


def test_a_row_that_never_mentions_the_trade_tape_is_out_of_scope(tmp_path):
    _write_tape(tmp_path, "2026-08-03", ["KXMLBGAME-1-X"])
    reg = _registry(tmp_path, [
        "| **S17** | macro parity | src | data-collecting | low | KXFEDDECISION vs Polymarket |",
    ])
    rep = inv._kalshi_trades_registration_issues(registry_path=reg, tape_root=tmp_path)
    assert rep["n_anchored"] == 0
    assert inv.kalshi_trades_registration_surface_warning(rep) is None


def test_registry_row_parser_ignores_header_and_prose_lines(tmp_path):
    p = tmp_path / "00-index.md"
    p.write_text(
        "| id | name | source | status |\n|---|---|---|---|\n"
        "| **S78** | a | b | c |\n"
        "**S78 — a prose section mentioning kalshi_trades and KXCPI.**\n",
        encoding="utf-8")
    rows = inv._registry_rows(p)
    assert [sid for sid, _ in rows] == ["S78"]


def test_advisory_degrades_to_silence_and_never_gates_on_a_broken_registry(tmp_path):
    rep = inv._kalshi_trades_registration_issues(
        registry_path=tmp_path / "does-not-exist.md", tape_root=tmp_path)
    assert rep["n_anchored"] == 0
    assert inv.kalshi_trades_registration_surface_warning(rep) is None
    assert inv.kalshi_trades_registration_surface_warning({}) is None
    assert inv.kalshi_trades_registration_surface_warning(
        {"n_anchored": 3, "uncovered": [], "unscoped": [], "inventory": None}) is None


def test_advisory_is_registered_in_the_full_gate_and_stays_non_gating():
    """The stanza must be wrapped like its siblings so a formatter raise can never become a
    gate (L156 DEFECT-1), and the word `warning (non-gating)` must be in the message."""
    text = _INVARIANTS.read_text()
    assert "kalshi_trades_registration_surface_warning(" in text
    assert "kalshi_trades registration-surface advisory could not be" in text
    idx = text.index("kt_warning = kalshi_trades_registration_surface_warning")
    assert "except BaseException:" in text[idx:idx + 900]


# --------------------------------------------------------------------------- #
# real committed tape, window CLOSED at 2026-08-03 (L140)
# --------------------------------------------------------------------------- #
def test_acceptance_real_tape_reproduces_l292s_published_inventory():
    """L292's own numbers, re-derived here on this independent code path: 39,698 prints /
    42 tickers / 20 series, every one of them sports or crypto."""
    rep = kt.trade_tape_inventory(ROOT / "tape", max_day=M1_DAY)
    assert rep["n_days"] == 1 and rep["days"] == [M1_DAY]
    assert rep["n_lines"] == 39698
    assert rep["n_tickers"] == 42
    assert rep["n_series"] == 20
    assert rep["n_malformed"] == 0
    assert rep["series"]["KXNWSLGAME"]["n_prints"] == 10156
    assert rep["series"]["KXMLBGAME"]["n_prints"] == 7756
    assert rep["series"]["KXBTC"]["n_prints"] == 47
    assert rep["series"]["KXETH"]["n_prints"] == 10


@pytest.mark.parametrize("token", ["KXCPI", "KXCPICORE", "KXNFP", "KXGDP", "KXFED", "KXPCE"])
def test_acceptance_no_econ_family_has_a_committed_print(token):
    """The fact that killed S81's REGISTER. If this ever fails, the trade collector has
    started covering econ and the L292 data-gate on that family has genuinely opened."""
    rep = kt.trade_tape_inventory(ROOT / "tape", max_day=M1_DAY)
    assert kt.series_coverage(rep, token)["verdict"] == kt.ABSENT


def test_acceptance_every_committed_series_is_sports_or_crypto():
    rep = kt.trade_tape_inventory(ROOT / "tape", max_day=M1_DAY)
    crypto = {"KXBTC", "KXETH"}
    for s in rep["series"]:
        assert s in crypto or s.endswith("GAME"), s


def test_acceptance_live_registry_rows_are_read_and_classified():
    """The live reading this advisory publishes today: both `kalshi_trades`-anchored registry
    rows (S78, S79) name no series token, so neither can be coverage-checked from tape. That
    is reported as `unscoped`, and NOT as an uncovered defect."""
    rep = inv._kalshi_trades_registration_issues(max_day=M1_DAY)
    assert rep["n_anchored"] >= 2
    assert set(rep["unscoped"]) >= {"S78", "S79"}
    assert rep["uncovered"] == []


def test_cli_runs_offline_and_emits_stable_json(capsys):
    rc = kt.main(["--tape-root", str(ROOT / "tape"), "--max-day", M1_DAY,
                  "--check", "KXMLBGAME", "KXCPI", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["inventory"]["n_series"] == 20
    verdicts = {c["token"]: c["verdict"] for c in payload["checks"]}
    assert verdicts == {"KXMLBGAME": kt.COVERED, "KXCPI": kt.ABSENT}


def test_cli_human_output_always_carries_the_coverage_caveat(capsys):
    kt.main(["--tape-root", str(ROOT / "tape"), "--max-day", M1_DAY])
    out = capsys.readouterr().out
    assert "COMMITTED TAPE ONLY" in out
    assert "never 'Kalshi has no prints there'" in out

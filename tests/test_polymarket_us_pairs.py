"""collection.polymarket_us_pairs — the credential-gated, READ-ONLY Polymarket-US book
capture leg (Q33). All offline: blocked_key path touches no network / writes no file; the
credentialed path uses an injected fake discover_fn + fetch_us_book_fn (no network), asserts
`real_ask` tags, bitemporal `captured_at`, raw-bytes sha256 provenance, and honest
no_book/book_error accounting. Also asserts the module imports nothing from execution/ and
writes to tape/polymarket_us_pairs/dt=*.jsonl."""
from __future__ import annotations

import json
from pathlib import Path

from collection import polymarket_us_pairs as pus


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _matched(kalshi_ticker, us_market_id="US-M1", family="wc_round",
             match_key=None, us_token_id="UTOK1"):
    return {"family": family, "match_key": match_key, "kalshi_ticker": kalshi_ticker,
            "us_market_id": us_market_id, "us_token_id": us_token_id}


def _us_book(best_bid=0.18, best_ask=0.21, raw='{"bids":[],"asks":[]}'):
    return {"best_bid": best_bid, "best_ask": best_ask,
            "bids": [{"price": "0.18", "size": "50"}],
            "asks": [{"price": "0.21", "size": "40"}], "raw": raw}


# --------------------------------------------------------------------------- #
# blocked_key path: credential absent => no-op, zero network, zero files
# --------------------------------------------------------------------------- #
def test_blocked_key_when_credential_absent(tmp_path):
    def _boom_discover():
        raise AssertionError("discovery must NOT run when the credential is absent")

    def _boom_fetch(mm):
        raise AssertionError("fetch must NOT run when the credential is absent")

    summary = pus.run(tape_dir=tmp_path, env={}, discover_fn=_boom_discover,
                      fetch_us_book_fn=_boom_fetch)
    assert summary == {
        "status": "blocked_key",
        "family": "polymarket_us_pairs",
        "venue": "polymarket_us",
        "credential_env": "POLYMARKET_US_API_KEY",
        "reason": "POLYMARKET_US_API_KEY absent — no network, wrote nothing",
    }
    # no file written anywhere under the tape dir
    assert list(tmp_path.iterdir()) == []


def test_blocked_key_empty_string_credential_is_still_absent(tmp_path):
    summary = pus.run(tape_dir=tmp_path, env={"POLYMARKET_US_API_KEY": ""})
    assert summary["status"] == "blocked_key"
    assert list(tmp_path.iterdir()) == []


def test_credentialed_pass_never_leaks_secret_value(tmp_path, capsys):
    # even on the credentialed path, the secret VALUE never reaches stdout/stderr/tape/summary
    matched = [_matched("KXWCROUND-26QUAR-USA")]
    summary = pus.run(tape_dir=tmp_path, env={"POLYMARKET_US_API_KEY": "s3cr3t-value"},
                      discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=lambda mm: _us_book())
    assert summary["status"] == "ok"
    out = capsys.readouterr()
    assert "s3cr3t-value" not in out.out and "s3cr3t-value" not in out.err
    assert "s3cr3t-value" not in json.dumps(summary)
    tape_text = (tmp_path / f"dt={summary['day']}.jsonl").read_text()
    assert "s3cr3t-value" not in tape_text


# --------------------------------------------------------------------------- #
# credentialed path: injected fake discover + fetch, no network
# --------------------------------------------------------------------------- #
def test_credentialed_pass_captures_real_ask_with_provenance(tmp_path):
    matched = [_matched("KXWCROUND-26QUAR-USA", us_market_id="US-USA",
                        match_key="quarterfinals|USA")]

    def fake_discover():
        return matched, ["raw-discovery-page"]

    seen = {}

    def fake_fetch(mm):
        seen["mm"] = mm
        return _us_book(best_bid=0.18, best_ask=0.21, raw='{"payload":"abc"}')

    summary = pus.run(api_key="present", tape_dir=tmp_path,
                      discover_fn=fake_discover, fetch_us_book_fn=fake_fetch)

    assert summary["status"] == "ok"
    assert summary["n_matched_markets"] == 1 and summary["n_captured"] == 1
    assert summary["n_no_book"] == 0 and summary["n_book_errors"] == 0
    assert summary["completeness_ok"] is True
    assert seen["mm"]["kalshi_ticker"] == "KXWCROUND-26QUAR-USA"

    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["schema_version"] == "polymarket_us_pairs.v1"
    assert rec["venue"] == "polymarket_us"
    assert rec["family"] == "wc_round"
    assert rec["match_key"] == "quarterfinals|USA"
    assert rec["kalshi_ticker"] == "KXWCROUND-26QUAR-USA"
    # source tag correctness: a live US book is a genuine fillable quote -> real_ask
    assert rec["polymarket_us"]["price_source_tag"] == "real_ask"
    assert rec["polymarket_us"]["best_bid"] == 0.18
    assert rec["polymarket_us"]["best_ask"] == 0.21
    assert rec["polymarket_us"]["book_fetch_ok"] is True
    # bitemporal capture stamp
    assert rec["captured_at"] == summary["captured_at"]
    assert "T" in rec["captured_at"]
    # raw-bytes sha256 provenance == sha256 of the fetched payload bytes
    from core.canonical import sha256_hex
    assert rec["raw_sha256"] == sha256_hex('{"payload":"abc"}')
    assert summary["raw_discovery_sha256"] == sha256_hex(b"raw-discovery-page")


def test_credentialed_pass_reads_env_credential(tmp_path):
    def fake_discover():
        return [_matched("KXWCROUND-26SEMI-FRA")], ["raw"]

    summary = pus.run(tape_dir=tmp_path, env={"POLYMARKET_US_API_KEY": "k"},
                      discover_fn=fake_discover, fetch_us_book_fn=lambda mm: _us_book())
    assert summary["status"] == "ok" and summary["n_captured"] == 1


def test_no_book_recorded_not_dropped_and_does_not_gate_completeness(tmp_path):
    matched = [_matched("KXWCROUND-26QUAR-USA", us_market_id="US-USA"),
               _matched("KXWCROUND-26SEMI-FRA", us_market_id="US-FRA")]

    def fake_fetch(mm):
        # US venue lists USA but NOT FRA -> None for FRA (a no_book, recorded not dropped)
        if mm["kalshi_ticker"] == "KXWCROUND-26SEMI-FRA":
            return None
        return _us_book()

    summary = pus.run(api_key="present", tape_dir=tmp_path,
                      discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=fake_fetch)
    assert summary["n_matched_markets"] == 2 and summary["n_captured"] == 1
    assert summary["n_no_book"] == 1
    assert summary["no_book"] == ["KXWCROUND-26SEMI-FRA"]
    # a US-venue coverage gap is a structural non-issue, NOT a capture fault
    assert summary["completeness_ok"] is True
    lines = (tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 1  # only the market that had a US book


def test_empty_ladder_is_data_not_a_drop(tmp_path):
    # a fully empty / one-sided US book (far-from-strike/thin shape, L23) is written as a
    # normal line with None best_bid/best_ask, book_fetch_ok True, and does not gate.
    matched = [_matched("KXWCROUND-26FINAL-BRA")]

    def fake_fetch(mm):
        return {"best_bid": None, "best_ask": None, "bids": [], "asks": [], "raw": "{}"}

    summary = pus.run(api_key="present", tape_dir=tmp_path,
                      discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=fake_fetch)
    assert summary["n_captured"] == 1 and summary["completeness_ok"] is True
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["polymarket_us"]["best_bid"] is None
    assert rec["polymarket_us"]["best_ask"] is None
    assert rec["polymarket_us"]["book_fetch_ok"] is True


def test_book_fetch_exception_is_a_book_error_and_gates(tmp_path):
    matched = [_matched("KXWCROUND-26QUAR-USA")]

    def raising_fetch(mm):
        raise RuntimeError("simulated US CLOB timeout")

    summary = pus.run(api_key="present", tape_dir=tmp_path,
                      discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=raising_fetch)
    assert summary["n_book_errors"] == 1
    assert summary["book_errors"][0]["market"] == "KXWCROUND-26QUAR-USA"
    assert "simulated US CLOB timeout" in summary["book_errors"][0]["error"]
    assert summary["completeness_ok"] is False
    # nothing to snapshot -> no file written
    assert not (tmp_path / f"dt={summary['day']}.jsonl").exists()


def test_discovery_exception_isolated_not_fatal_and_gates(tmp_path):
    def raising_discover():
        raise RuntimeError("simulated discovery failure")

    summary = pus.run(api_key="present", tape_dir=tmp_path,
                      discover_fn=raising_discover, fetch_us_book_fn=lambda mm: _us_book())
    assert summary["status"] == "ok"  # the pass itself never raises
    assert summary["discovery_error"] == "simulated discovery failure"
    assert summary["n_captured"] == 0
    assert summary["completeness_ok"] is False


def test_fed_decision_family_match_key_folding(tmp_path):
    matched = [{"family": "fed_decision", "meeting": "2026-07", "bucket": "hike_25",
                "kalshi_ticker": "KXFEDDECISION-26JUL-H25", "us_market_id": "US-FED-1"}]
    summary = pus.run(api_key="present", tape_dir=tmp_path,
                      discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=lambda mm: _us_book())
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["family"] == "fed_decision"
    assert rec["match_key"] == "2026-07|hike_25"


def test_append_only_across_two_passes(tmp_path):
    matched = [_matched("KXWCROUND-26QUAR-USA")]
    s1 = pus.run(api_key="present", tape_dir=tmp_path,
                 discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=lambda mm: _us_book())
    s2 = pus.run(api_key="present", tape_dir=tmp_path,
                 discover_fn=lambda: (matched, ["raw"]), fetch_us_book_fn=lambda mm: _us_book())
    assert s1["day"] == s2["day"]
    lines = (tmp_path / f"dt={s1['day']}.jsonl").read_text().splitlines()
    assert len(lines) == 2  # appended, not rewritten


# --------------------------------------------------------------------------- #
# write path + no execution import (static discipline)
# --------------------------------------------------------------------------- #
def test_default_tape_path_is_the_distinct_us_family():
    assert pus.TAPE.parts[-2:] == ("tape", "polymarket_us_pairs")


def test_module_imports_nothing_from_execution():
    src = Path(pus.__file__).read_text(encoding="utf-8")
    assert "import execution" not in src
    assert "from execution" not in src


def test_default_network_callables_are_vps_bringup_stubs():
    # never exercised in tests or cloud passes; a stub reached on a credentialed path surfaces
    # honestly (NotImplementedError), never a fake success.
    import pytest
    with pytest.raises(NotImplementedError):
        pus._default_discover()
    with pytest.raises(NotImplementedError):
        pus._default_fetch_us_book({"kalshi_ticker": "X"})

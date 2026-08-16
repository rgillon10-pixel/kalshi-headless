"""Tests for `scripts/anomaly_sweep_population_rotation_audit.py` (idle-run policy (c), 2026-08-16).

Two tiers, per the repo's audit-script convention:
  * SYNTHETIC — a hand-built tape root, so every branch (frozen population, total rotation,
    empty family, single capture, junk-only prefix, unreachable series, empty denominator)
    is exercised deterministically.
  * REAL-TAPE ACCEPTANCE — asserted with FLOORS AND DIRECTIONS ONLY, never frozen equalities
    (L320/L191): `tape/` is append-only and every count below can still grow.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location(
        "_anomaly_sweep_population_rotation_audit",
        REPO / "scripts" / "anomaly_sweep_population_rotation_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


aud = _load()


# ─── helpers ──────────────────────────────────────────────────────────────────────────
def _write(root: Path, family: str, day: str, records) -> None:
    d = root / family
    d.mkdir(parents=True, exist_ok=True)
    with open(d / f"dt={day}.jsonl", "a", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _u(capture_id, captured_at, ticker, series, event):
    return {"capture_id": capture_id, "captured_at": captured_at, "ticker": ticker,
            "series": series, "event_ticker": event}


def _capture(root, day, cid, ts, tickers):
    _write(root, "universe_sweep", day,
           [_u(cid, ts, t, t.split("-")[0], "-".join(t.split("-")[:2])) for t in tickers])


# ─── set-similarity primitives ────────────────────────────────────────────────────────
def test_jaccard_is_none_when_undefined_never_a_fabricated_zero():
    """L357: an undefined statistic must be None, and every caller must carry the None."""
    assert aud.jaccard([], []) is None
    assert aud.containment([], ["a"]) is None


def test_jaccard_and_containment_disagree_on_a_subset():
    assert aud.jaccard(["a"], ["a", "b"]) == pytest.approx(0.5)
    assert aud.containment(["a"], ["a", "b"]) == pytest.approx(1.0)


def test_rule_of_three_is_none_on_an_empty_denominator():
    """L296: 0 hits over 0 trials bounds nothing."""
    assert aud.rule_of_three_upper(0) is None
    assert aud.rule_of_three_upper(-3) is None
    assert aud.rule_of_three_upper(300) == pytest.approx(0.01)


# ─── the load-bearing claim about the digest ──────────────────────────────────────────
def test_one_ticker_change_flips_the_sorted_unique_digest():
    """The whole point of block 1: the digest is a one-bit identity test, so it cannot
    distinguish 100% rotation from a 99.995%-overlapping slice."""
    big = [f"KXA-26AUG01-B{i}" for i in range(5000)]
    assert aud.sorted_unique_digest(big) != aud.sorted_unique_digest(big[:-1])
    assert aud.jaccard(big, big[:-1]) > 0.999


def test_digest_is_order_and_duplicate_independent():
    a = ["T2", "T1", "T1", "T3"]
    assert aud.sorted_unique_digest(a) == aud.sorted_unique_digest(["T3", "T1", "T2"])


def test_digest_answerability_reports_the_flip_demo_from_real_shaped_captures(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00",
             [f"KXA-26JAN01-B{i}" for i in range(10)])
    caps = aud.load_universe_captures(str(tmp_path))
    rep = aud.digest_answerability([], caps)
    assert rep["one_ticker_flip_demo"]["one_ticker_flips_digest"] is True
    assert rep["one_ticker_flip_demo"]["jaccard_of_the_two_sets"] > 0.8
    assert "DIGEST-CANNOT-DECIDE" in rep["verdict"]


def test_digest_answerability_survives_a_capture_too_small_to_demo(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXA-26JAN01-B1"])
    caps = aud.load_universe_captures(str(tmp_path))
    rep = aud.digest_answerability([], caps)
    assert rep["one_ticker_flip_demo"]["available"] is False


# ─── rotation ─────────────────────────────────────────────────────────────────────────
def test_rotation_detects_a_frozen_population(tmp_path):
    same = [f"KXA-26JAN01-B{i}" for i in range(5)]
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", same)
    _capture(tmp_path, "2026-01-02", "C2", "2026-01-02T00:00:00+00:00", same)
    rep = aud.rotation(aud.load_universe_captures(str(tmp_path)))
    assert rep["consecutive_jaccard"]["median"] == pytest.approx(1.0)
    assert rep["union_distinct_tickers"] == 5
    assert rep["steps"][-1]["marginal_new"] == 0


def test_rotation_detects_total_turnover(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00",
             [f"KXA-26JAN01-B{i}" for i in range(5)])
    _capture(tmp_path, "2026-01-02", "C2", "2026-01-02T00:00:00+00:00",
             [f"KXA-26JAN02-B{i}" for i in range(5)])
    rep = aud.rotation(aud.load_universe_captures(str(tmp_path)))
    assert rep["consecutive_jaccard"]["median"] == 0.0
    assert rep["consecutive_jaccard"]["n_exactly_zero"] == 1
    assert rep["union_distinct_tickers"] == 10
    assert rep["max_captures_any_ticker_appears_in"] == 1


def test_rotation_on_a_single_capture_reports_no_similarity_rather_than_zero(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXA-26JAN01-B1"])
    rep = aud.rotation(aud.load_universe_captures(str(tmp_path)))
    assert rep["consecutive_jaccard"]["n"] == 0
    assert rep["consecutive_jaccard"]["median"] is None
    assert rep["first_vs_last_capture_jaccard"] is None


def test_rotation_on_an_empty_family_is_empty_not_an_exception(tmp_path):
    rep = aud.rotation(aud.load_universe_captures(str(tmp_path)))
    assert rep["n_captures"] == 0 and rep["union_distinct_tickers"] == 0


def test_captures_are_ordered_by_captured_at_not_by_filename(tmp_path):
    _capture(tmp_path, "2026-01-02", "CLATE", "2026-01-02T00:00:00+00:00", ["KXA-26JAN02-B1"])
    _capture(tmp_path, "2026-01-01", "CEARLY", "2026-01-01T00:00:00+00:00", ["KXA-26JAN01-B1"])
    caps = aud.load_universe_captures(str(tmp_path))
    assert [c["capture_id"] for c in caps] == ["CEARLY", "CLATE"]


# ─── composition + denominator ────────────────────────────────────────────────────────
def test_composition_splits_the_auto_generated_families_from_real_markets(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00",
             [f"KXMVESPORTSMULTIGAMEEXTENDED-S{i}-L{i}" for i in range(9)]
             + ["KXBTC-26JAN0112-B1"])
    rep = aud.composition(aud.load_universe_captures(str(tmp_path)))
    assert rep["distinct_junk_tickers"] == 9
    assert rep["distinct_non_junk_tickers"] == 1
    assert rep["junk_share_of_distinct_tickers"] == pytest.approx(0.9)


def test_denominator_counts_only_ladder_capable_non_junk_groups(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00",
             ["KXBTC-26JAN0112-B1", "KXBTC-26JAN0112-B2",   # a ladder: 2 markets, 1 event
              "KXETH-26JAN0112-B1",                          # a singleton event
              "KXMVECROSSCATEGORY-S1-L1", "KXMVECROSSCATEGORY-S1-L2"])  # junk ladder, excluded
    rep = aud.denominator(aud.load_universe_captures(str(tmp_path)), [])
    assert rep["distinct_non_junk_event_groups_ever"] == 2
    assert rep["distinct_ladder_capable_groups_ever"] == 1
    per_unit = {c["unit"]: c for c in rep["candidates"]}
    assert per_unit["distinct ticker ever scanned (proxy)"]["n"] == 3
    assert per_unit["market-observation (proxy tape rows)"]["n"] == 5


def test_every_denominator_carries_its_own_rule_of_three_bound(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXBTC-26JAN0112-B1"])
    rep = aud.denominator(aud.load_universe_captures(str(tmp_path)), [])
    for c in rep["candidates"]:
        assert "rule_of_three_95_upper_per_unit" in c
        assert "unit" in c and "comment" in c
        if c["n"] > 0:
            assert c["rule_of_three_95_upper_per_unit"] == pytest.approx(3.0 / c["n"])
        else:
            assert c["rule_of_three_95_upper_per_unit"] is None


def test_a_junk_only_prefix_yields_an_empty_non_junk_denominator(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00",
             [f"KXMVECROSSCATEGORY-S{i}-L1" for i in range(4)])
    rep = aud.denominator(aud.load_universe_captures(str(tmp_path)), [])
    per_unit = {c["unit"]: c for c in rep["candidates"]}
    assert per_unit["distinct ticker ever scanned (proxy)"]["n"] == 0
    assert per_unit["distinct ticker ever scanned (proxy)"][
        "rule_of_three_95_upper_per_unit"] is None


# ─── series reachability ──────────────────────────────────────────────────────────────
def test_series_reachability_reports_absence_as_absence(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXBTC-26JAN0112-B1"])
    caps = aud.load_universe_captures(str(tmp_path))
    rep = aud.series_reachability(caps, ("KXMARMADROUND", "KXBTC"))
    assert rep["KXMARMADROUND"]["reachable_under_cap"] is False
    assert rep["KXMARMADROUND"]["n_captures_containing_it"] == 0
    assert rep["KXBTC"]["reachable_under_cap"] is True


# ─── end-to-end ───────────────────────────────────────────────────────────────────────
def test_audit_end_to_end_never_emits_a_price_or_a_ci(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXBTC-26JAN0112-B1"])
    rep = aud.audit(str(tmp_path))
    assert rep["price_provenance"]["prices_quoted"] is False
    assert rep["price_provenance"]["price_source_tag"] is None
    assert rep["verdict"]["class"] == "DATA-ADEQUACY"
    assert rep["verdict"]["registry_flip"] is False
    assert rep["verdict"]["ci_or_pnl"] is False


def test_verdict_does_not_cry_rotation_on_a_frozen_prefix(tmp_path):
    same = [f"KXBTC-26JAN0112-B{i}" for i in range(4)]
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", same)
    _capture(tmp_path, "2026-01-02", "C2", "2026-01-02T00:00:00+00:00", same)
    rep = aud.audit(str(tmp_path))
    assert not any(f.startswith("PREFIX-NOT-FROZEN") for f in rep["verdict"]["findings"])
    assert not any(f.startswith("ROTATION-IS-CHURN") for f in rep["verdict"]["findings"])


def test_main_runs_offline_and_writes_its_report(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXBTC-26JAN0112-B1"])
    out = tmp_path / "rep.json"
    assert aud.main(["--tape-root", str(tmp_path), "--json-out", str(out)]) == 0
    assert json.loads(out.read_text())["schema_version"].startswith(
        "anomaly_sweep_population_rotation_audit")


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    _capture(tmp_path, "2026-01-01", "C1", "2026-01-01T00:00:00+00:00", ["KXBTC-26JAN0112-B1"])
    with open(tmp_path / "universe_sweep" / "dt=2026-01-01.jsonl", "a") as fh:
        fh.write("{not json\n\n")
        fh.write(json.dumps({"capture_id": "C1"}) + "\n")  # no ticker -> skipped
    caps = aud.load_universe_captures(str(tmp_path))
    assert len(caps) == 1 and caps[0]["n_distinct"] == 1


# ─── L345 root anchoring ──────────────────────────────────────────────────────────────
def test_default_tape_root_is_absolute_and_repo_anchored():
    """L345: a relative default root resolves against os.getcwd(), so this audit would report
    0 captures at exit code 0 from any other working directory — an empty population that
    reads exactly like a real data gate."""
    assert os.path.isabs(aud.DEFAULT_TAPE_ROOT)
    assert aud.DEFAULT_TAPE_ROOT == str(REPO / "tape")


@pytest.mark.skipif(not (REPO / "tape" / "universe_sweep").is_dir(),
                    reason="committed universe_sweep tape absent")
def test_the_default_root_resolves_the_same_population_from_another_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    caps = aud.load_universe_captures()
    assert len(caps) >= 50


# ─── REAL-TAPE ACCEPTANCE (directions and floors only — L320/L191) ────────────────────
@pytest.mark.skipif(not (REPO / "tape" / "universe_sweep").is_dir(),
                    reason="committed universe_sweep tape absent")
class TestRealTapeAcceptance:
    @classmethod
    def setup_class(cls):
        cls.rep = aud.audit(str(REPO / "tape"))

    def test_the_deferred_digest_comparison_cannot_decide_the_question(self):
        """Q55's status line deferred exactly this comparison and assigned it a reading the
        field cannot support. Pin BOTH halves: the digests really are all distinct, AND a
        one-ticker edit on the real 20,000-ticker prefix flips a digest while leaving the
        sets ~identical — so distinctness is not evidence of coverage."""
        d = self.rep["digest_answerability"]
        assert d["n_passes_carrying_a_digest"] >= 5
        assert d["all_digests_distinct"] is True
        demo = d["one_ticker_flip_demo"]
        assert demo["one_ticker_flips_digest"] is True
        assert demo["jaccard_of_the_two_sets"] > 0.999

    def test_the_universe_sweep_proxy_reproduces_the_anomaly_tapes_own_group_density(self):
        """The proxy premise is TESTED, not assumed: two different collectors, different
        processes, different gate hours, same endpoint — their per-capture event-group
        densities must agree closely or every number downstream is void."""
        p = self.rep["proxy_validation"]
        assert p["anomaly_n_event_groups_per_at_cap_pass"]["n"] >= 200
        assert p["proxy_n_event_groups_per_at_cap_capture"]["n"] >= 20
        assert p["relative_gap_of_medians"] < 0.10

    def test_the_capped_prefix_is_not_a_frozen_slice(self):
        r = self.rep["rotation"]
        assert r["n_captures"] >= 50
        assert r["consecutive_jaccard"]["median"] == 0.0
        assert r["first_vs_last_capture_jaccard"] == 0.0

    def test_no_ticker_is_ever_re_observed_across_separated_captures(self):
        """The sharp half: the only repeats in the whole committed history come from
        near-duplicate captures minutes apart, so the sweep never watches a market twice."""
        r = self.rep["rotation"]
        assert r["max_captures_any_ticker_appears_in"] <= 2
        hist = r["ticker_recurrence_histogram"]
        assert int(hist["1"]) > 10 * int(hist.get("2", 1))

    def test_rotation_is_churn_in_auto_generated_families_not_coverage(self):
        c = self.rep["composition"]
        assert c["junk_share_of_distinct_tickers"] > 0.95
        assert c["junk_share_per_capture"]["min"] > 0.90
        # the population that matters is small and is NOT the 20,000-row headline
        assert c["distinct_non_junk_tickers"] < 0.01 * c["population_distinct_tickers"]

    def test_the_non_junk_denominator_is_orders_of_magnitude_below_the_observation_count(self):
        d = self.rep["denominator"]
        per_unit = {c["unit"]: c for c in d["candidates"]}
        obs = per_unit["market-observation (proxy tape rows)"]["n"]
        lad = per_unit["distinct ladder-capable event group ever scanned (proxy)"]["n"]
        assert obs > 100 * lad
        assert lad >= 1
        assert (per_unit["distinct ladder-capable event group ever scanned (proxy)"][
            "rule_of_three_95_upper_per_unit"]
            > 100 * per_unit["market-observation (proxy tape rows)"][
                "rule_of_three_95_upper_per_unit"])

    def test_s15s_only_live_implication_family_is_never_inside_the_cap(self):
        """Q55 milestone 2 added KXMARMADROUND so S15's kill clause could fire; its first
        live pass still read n_implication_pairs_checked: 0. This pins WHY."""
        r = self.rep["series_reachability"]["KXMARMADROUND"]
        assert r["reachable_under_cap"] is False
        assert r["n_captures_scanned"] >= 50

    def test_the_verdict_is_data_adequacy_and_flips_nothing(self):
        v = self.rep["verdict"]
        assert v["class"] == "DATA-ADEQUACY"
        assert v["registry_flip"] is False and v["ci_or_pnl"] is False
        assert any(f.startswith("SERIES-UNREACHABLE-UNDER-CAP") for f in v["findings"])

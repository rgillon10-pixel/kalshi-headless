"""scripts.polymarket_pair_terms_audit — L214 terms-auditability census.

Offline, deterministic: every fixture is a hand-written JSONL tape directory under tmp_path.
The audit is read-only and makes no network call, so nothing is monkeypatched.
"""
from __future__ import annotations

import json
import subprocess

from scripts.polymarket_pair_terms_audit import (
    audit,
    classify_record,
    count_pair_records_at_ref,
    main,
    resolve_git_ref,
)


# --------------------------------------------------------------------------- #
# fixture builders — v1 (IDs only) and v2 (IDs + matched text + bucket_terms)
# --------------------------------------------------------------------------- #
def _v1(bucket="hike_50plus", capture_id="20260720T060000Z", market_id="M1"):
    return {
        "schema_version": "polymarket_macro_pairs.v1",
        "capture_id": capture_id,
        "captured_at": "2026-07-20T06:00:00+00:00",
        "family": "fed_decision",
        "meeting": "2026-07",
        "bucket": bucket,
        "kalshi": {"ticker": "KXFEDDECISION-26JUL-H26", "yes_ask": 0.03, "yes_bid": 0.02,
                   "no_ask": 0.98, "no_bid": 0.97, "price_source_tag": "real_ask"},
        "polymarket": {"event_id": "E1", "market_id": market_id, "best_bid": 0.01,
                       "best_ask": 0.02, "book_fetch_ok": True, "price_source_tag": "real_ask"},
        "price_gap_yes_ask": 0.01,
    }


def _v2(bucket="hike_50plus", *, kalshi_title="Will the Federal Reserve Hike rates by >25bps "
                                              "at their July 2026 meeting?",
        group_item_title="50+ bps increase", terms=None, capture_id="20260721T060000Z"):
    rec = _v1(bucket=bucket, capture_id=capture_id)
    rec["schema_version"] = "polymarket_macro_pairs.v2"
    rec["kalshi"]["title"] = kalshi_title
    rec["kalshi"]["resolution_basis"] = "kalshi_rulebook"
    rec["polymarket"]["question"] = "Will the Fed increase rates ... after the July 2026 meeting?"
    rec["polymarket"]["group_item_title"] = group_item_title
    rec["polymarket"]["resolution_basis"] = "uma_oracle"
    rec["bucket_terms"] = terms if terms is not None else {
        "compares": "bps_region+meeting_key", "meeting_key_checked": True,
        "kalshi_basis": "hike_gt_25bps", "polymarket_basis": "increase_gte_50bps",
        "terms_equivalent": False,
        "note": "resolution terms differ: kalshi title 'hike_gt_25bps' settles YES over "
                "[26, inf)bps, polymarket 'increase_gte_50bps' over [50, inf)bps",
    }
    return rec


def _summary():
    return {"schema_version": "polymarket_macro_pairs_summary.v1", "family": "capture_summary",
            "capture_id": "20260720T060000Z", "completeness_ok": True}


def _write(tape_dir, day, records):
    tape_dir.mkdir(parents=True, exist_ok=True)
    with (tape_dir / f"dt={day}.jsonl").open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, sort_keys=True) + "\n")


# --------------------------------------------------------------------------- #
def test_v1_only_tape_is_unauditable_by_construction_not_fine(tmp_path):
    """The whole point of L214: a v1 record is not 'checked and equivalent', it is NOT
    CHECKABLE — no title/label text and no resolution_basis ever reached tape."""
    _write(tmp_path, "2026-07-20", [_v1("hike_50plus"), _v1("cut_50plus"), _v1("no_change")])
    rep = audit(tmp_path)
    assert rep["n_pair_records"] == 3
    assert rep["n_by_schema_version"] == {"polymarket_macro_pairs.v1": 3}
    assert rep["n_with_terms"] == 0
    assert rep["n_without_terms"] == 3
    assert rep["n_terms_unauditable"] == 3
    assert rep["n_terms_auditable"] == 0
    assert rep["n_terms_equivalent_true"] == 0
    assert rep["pre_v2"]["n_records"] == 3
    assert rep["pre_v2"]["status"] == "UNAUDITABLE-BY-CONSTRUCTION"


def test_mixed_v1_v2_tape_counts_each_version_and_the_asymmetry(tmp_path):
    _write(tmp_path, "2026-07-20", [_v1("hike_50plus"), _v1("hike_25"), _summary()])
    _write(tmp_path, "2026-07-21", [
        _v2("hike_50plus"),
        _v2("no_change", kalshi_title="Will the Federal Reserve Hike rates by 0bps at their "
                                      "July 2026 meeting?",
            group_item_title="No change",
            terms={"kalshi_basis": "no_change_0bps", "polymarket_basis": "no_change",
                   "terms_equivalent": True, "note": None}),
        _summary(),
    ])
    rep = audit(tmp_path)
    assert rep["n_files"] == 2
    assert rep["n_pair_records"] == 4
    assert rep["n_summary_records"] == 2
    assert rep["n_by_schema_version"] == {"polymarket_macro_pairs.v1": 2,
                                          "polymarket_macro_pairs.v2": 2}
    assert rep["n_with_terms"] == 2
    assert rep["n_without_terms"] == 2
    assert rep["n_terms_unauditable"] == 2          # the two v1 rows
    assert rep["n_terms_equivalent_false"] == 1
    assert rep["n_terms_equivalent_true"] == 1
    assert rep["n_terms_verdict_null"] == 0         # no v2 row came back undecidable
    assert rep["n_no_terms_block"] == 2             # the v1 rows were never asked at all


def test_fifty_plus_buckets_are_broken_out(tmp_path):
    _write(tmp_path, "2026-07-20", [_v1("hike_50plus"), _v1("cut_50plus"), _v1("hike_25")])
    _write(tmp_path, "2026-07-21", [_v2("hike_50plus"), _v2("cut_50plus")])
    rep = audit(tmp_path)
    fifty = rep["fifty_plus_buckets"]
    assert fifty["n_records"] == 4
    assert fifty["n_unauditable"] == 2              # the two v1 50plus rows
    assert fifty["n_terms_equivalent_false"] == 2   # both v2 50plus rows are provably unequal
    assert fifty["per_bucket"]["hike_50plus"]["n"] == 2
    assert fifty["per_bucket"]["cut_50plus"]["n"] == 2
    assert rep["by_bucket"]["hike_25"]["n"] == 1
    assert set(rep["by_bucket"]) == {"hike_50plus", "cut_50plus", "hike_25"}
    assert rep["example_asymmetry"]["bucket"] in ("hike_50plus", "cut_50plus")


def test_v2_record_with_null_verdict_is_still_unauditable(tmp_path):
    """A v2 row whose collector could not derive a basis (missing/garbage text) reports
    `terms_equivalent: null` — it counts as UNAUDITABLE, never as agreement."""
    rec = _v2("hike_50plus", group_item_title="",
              terms={"kalshi_basis": "hike_gt_25bps", "polymarket_basis": None,
                     "terms_equivalent": None, "note": None})
    rec["polymarket"].pop("question")
    _write(tmp_path, "2026-07-21", [rec])
    rep = audit(tmp_path)
    assert rep["n_pair_records"] == 1
    assert rep["n_with_terms"] == 0                 # no leg text -> the block isn't evidenced
    assert rep["n_terms_unauditable"] == 1
    assert rep["n_terms_equivalent_true"] == 0
    assert rep["n_terms_verdict_null"] == 1         # the block exists, its verdict is null
    assert rep["n_no_terms_block"] == 0


def test_summary_lines_and_foreign_records_are_not_counted_as_pairs(tmp_path):
    _write(tmp_path, "2026-07-20", [_v1(), _summary(),
                                    {"schema_version": "polymarket_cpi_pairs.v1", "family": "cpi"}])
    with (tmp_path / "dt=2026-07-20.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
        fh.write("\n")
    rep = audit(tmp_path)
    assert rep["n_pair_records"] == 1
    assert rep["n_summary_records"] == 1
    assert rep["n_other_records"] == 1
    assert rep["n_bad_json"] == 1
    assert rep["n_lines"] == 4


def test_missing_tape_dir_is_an_empty_report_not_a_crash(tmp_path):
    rep = audit(tmp_path / "nope")
    assert rep["n_files"] == 0 and rep["n_pair_records"] == 0
    assert rep["n_terms_unauditable"] == 0
    assert rep["n_by_schema_version"] == {}


def test_classify_record_requires_both_the_block_and_its_evidence():
    with_text = classify_record(_v2("hike_50plus"))
    assert with_text["has_terms"] is True and with_text["auditable"] is True
    assert with_text["terms_equivalent"] is False
    assert with_text["kalshi_resolution_basis"] == "kalshi_rulebook"
    assert with_text["polymarket_resolution_basis"] == "uma_oracle"

    no_block = classify_record(_v1())
    assert no_block["has_terms"] is False and no_block["auditable"] is False
    assert no_block["terms_equivalent"] is None


def test_question_text_alone_is_not_evidence_of_a_checked_basis(tmp_path):
    """D3 regression. `fed_bucket_terms` derives the Polymarket basis from `group_item_title`
    ONLY. A record with a null `group_item_title` but a fat `question` string therefore has NO
    evidence for its verdict — reporting `has_terms: True` off `question` would manufacture a
    'checked' out of a field the derivation never reads."""
    rec = _v2("hike_50plus", group_item_title=None,
              terms={"compares": "bps_region+meeting_key", "meeting_key_checked": True,
                     "kalshi_basis": "hike_gt_25bps", "polymarket_basis": None,
                     "terms_equivalent": None, "note": None})
    rec["polymarket"]["question"] = ("Will the Fed increase interest rates by 50+ bps after "
                                     "the July 2026 meeting?")
    assert rec["polymarket"]["group_item_title"] is None
    assert rec["polymarket"]["question"]

    info = classify_record(rec)
    assert info["poly_text_ok"] is False        # keyed on group_item_title alone
    assert info["poly_question_present"] is True  # visible, but does NOT feed has_terms
    assert info["has_terms"] is False
    assert info["auditable"] is False

    _write(tmp_path, "2026-07-21", [rec])
    rep = audit(tmp_path)
    assert rep["n_with_terms"] == 0
    assert rep["n_without_terms"] == 1
    assert rep["n_terms_unauditable"] == 1


def test_no_terms_block_and_null_verdict_are_counted_separately(tmp_path):
    """D4 regression: a v1 record has NO `bucket_terms` field (never asked) — that is a
    different ignorance from a v2 block whose verdict came back undecidable. Pooling them
    would let a finding quote 'N null verdicts' for records that were never evaluated."""
    v2_true = _v2("no_change", kalshi_title="Will the Federal Reserve Hike rates by 0bps at "
                                            "their July 2026 meeting?",
                  group_item_title="No change",
                  terms={"compares": "bps_region+meeting_key", "meeting_key_checked": True,
                         "kalshi_basis": "no_change_0bps", "polymarket_basis": "no_change",
                         "terms_equivalent": True, "note": None})
    v2_false = _v2("hike_50plus")
    v2_null = _v2("cut_50plus", group_item_title="mystery label",
                  terms={"compares": "bps_region+meeting_key", "meeting_key_checked": True,
                         "kalshi_basis": "cut_gt_25bps", "polymarket_basis": None,
                         "terms_equivalent": None, "note": None})
    _write(tmp_path, "2026-07-21", [_v1("hike_25"), v2_true, v2_false, v2_null])

    rep = audit(tmp_path)
    assert rep["n_pair_records"] == 4
    assert rep["n_terms_equivalent_true"] == 1
    assert rep["n_terms_equivalent_false"] == 1
    assert rep["n_terms_verdict_null"] == 1     # v2, block present, undecidable
    assert rep["n_no_terms_block"] == 1         # v1, no bucket_terms field at all
    assert "n_terms_equivalent_null" not in rep  # the conflated counter is gone
    # exact partition, top level ...
    assert (rep["n_terms_equivalent_true"] + rep["n_terms_equivalent_false"]
            + rep["n_terms_verdict_null"] + rep["n_no_terms_block"]) == rep["n_pair_records"]
    # ... and per bucket
    for bucket, row in rep["by_bucket"].items():
        assert (row["n_terms_equivalent_true"] + row["n_terms_equivalent_false"]
                + row["n_terms_verdict_null"] + row["n_no_terms_block"]) == row["n"], bucket
        assert "n_terms_equivalent_null" not in row
    assert rep["by_bucket"]["hike_25"]["n_no_terms_block"] == 1
    assert rep["by_bucket"]["hike_25"]["n_terms_verdict_null"] == 0
    assert rep["by_bucket"]["cut_50plus"]["n_terms_verdict_null"] == 1
    assert rep["by_bucket"]["cut_50plus"]["n_no_terms_block"] == 0


def test_older_v2_block_without_compares_keys_still_classifies(tmp_path):
    """The first 20 committed v2 lines predate `compares`/`meeting_key_checked` (D5). Tape is
    append-only and never rewritten, so the audit must read that older block shape without
    crashing and without mis-counting it."""
    old = _v2("hike_50plus",
              terms={"kalshi_basis": "hike_gt_25bps", "polymarket_basis": "increase_gte_50bps",
                     "terms_equivalent": False, "note": "resolution terms differ: ..."})
    assert "compares" not in old["bucket_terms"]
    info = classify_record(old)
    assert info["has_terms"] is True and info["auditable"] is True
    assert info["terms_compares"] is None
    assert info["meeting_key_checked"] is None

    _write(tmp_path, "2026-07-30", [old, _v2("cut_50plus")])
    rep = audit(tmp_path)
    assert rep["n_pair_records"] == 2
    assert rep["n_terms_equivalent_false"] == 2
    assert rep["n_terms_verdict_null"] == 0 and rep["n_no_terms_block"] == 0
    assert rep["n_terms_auditable"] == 2


def test_cli_prints_json_and_exits_zero(tmp_path, capsys):
    _write(tmp_path, "2026-07-20", [_v1()])
    _write(tmp_path, "2026-07-21", [_v2()])
    assert main(["--tape-dir", str(tmp_path)]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["n_pair_records"] == 2
    assert rep["tape_dir"] == str(tmp_path)
    assert "DESCRIPTIVE ONLY" in rep["scope"]


# --------------------------------------------------------------------------- #
# L242 — git_ref / n_records_at_head: a working-tree-only census must never be
# quotable as "committed" (see kb/lessons/00-lessons.md L242).
# --------------------------------------------------------------------------- #
def _init_git_repo(root):
    """A throwaway, fully local git repo — no network, isolated identity so this never
    depends on (or pollutes) the caller's global git config."""
    env_args = ["-c", "user.name=test", "-c", "user.email=test@example.com",
                "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git"] + env_args + ["-C", str(root), "commit", "-q", "--allow-empty",
                    "-m", "init"], check=True)


def _git_commit_all(root, message):
    env_args = ["-c", "user.name=test", "-c", "user.email=test@example.com",
                "-c", "commit.gpgsign=false"]
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git"] + env_args + ["-C", str(root), "commit", "-q", "-m", message],
                    check=True)


def _git_head(root):
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                           capture_output=True, text=True).stdout.strip()


def test_resolve_git_ref_none_when_git_runner_fails(tmp_path):
    def _raising_runner(args, cwd=None):
        raise RuntimeError("git not found")
    assert resolve_git_ref(tmp_path, run_git=_raising_runner) is None


def test_resolve_git_ref_returns_head_sha_of_a_real_repo(tmp_path):
    _init_git_repo(tmp_path)
    sha = resolve_git_ref(tmp_path)
    assert sha == _git_head(tmp_path)
    assert len(sha) == 40 and all(c in "0123456789abcdef" for c in sha)


def test_count_pair_records_at_ref_ignores_uncommitted_lines(tmp_path):
    """The whole point of L242: an appended-but-uncommitted line must NOT be counted."""
    _init_git_repo(tmp_path)
    tape_dir = tmp_path / "tape" / "polymarket_macro_pairs"
    _write(tape_dir, "2026-07-20", [_v1(market_id="M1"), _v1(market_id="M2")])
    _git_commit_all(tmp_path, "committed tape")
    head = _git_head(tmp_path)

    # Uncommitted third record — present in the working tree, absent from git_ref.
    _write(tape_dir, "2026-07-20", [_v1(market_id="M3")])

    rep = audit(tape_dir, repo_root=tmp_path)
    assert rep["n_pair_records"] == 3          # working tree: sees all 3
    assert rep["git_ref"] == head
    assert rep["n_records_at_head"] == 2       # committed only: sees 2


def test_count_pair_records_at_ref_none_when_tape_dir_outside_repo_root(tmp_path):
    repo_root = tmp_path / "repo"
    outside = tmp_path / "elsewhere"
    _init_git_repo(repo_root)
    _write(outside, "2026-07-20", [_v1()])
    assert count_pair_records_at_ref(outside, "HEAD", repo_root=repo_root) is None


def test_count_pair_records_at_ref_none_on_bad_ref(tmp_path):
    _init_git_repo(tmp_path)
    tape_dir = tmp_path / "tape" / "polymarket_macro_pairs"
    _write(tape_dir, "2026-07-20", [_v1()])
    _git_commit_all(tmp_path, "committed tape")
    assert count_pair_records_at_ref(tape_dir, "not-a-real-ref", repo_root=tmp_path) is None


def test_audit_git_fields_are_null_when_git_runner_fails(tmp_path):
    def _raising_runner(args, cwd=None):
        raise RuntimeError("git not found")
    _write(tmp_path, "2026-07-20", [_v1()])
    rep = audit(tmp_path, repo_root=tmp_path, run_git=_raising_runner)
    assert rep["git_ref"] is None
    assert rep["n_records_at_head"] is None
    assert rep["n_pair_records"] == 1          # the rest of the report is unaffected


def test_audit_on_the_real_repo_reports_a_live_head_sha():
    """Real-tree acceptance test: run the default `audit()` (real committed tape dir,
    real repo root) and check `git_ref` against a freshly-queried `git rev-parse HEAD` —
    never hardcoded, so it stays correct as the repo moves forward."""
    live_head = subprocess.run(["git", "rev-parse", "HEAD"], check=True,
                                capture_output=True, text=True).stdout.strip()
    rep = audit()
    assert rep["git_ref"] == live_head
    assert rep["n_records_at_head"] is not None
    assert rep["n_records_at_head"] <= rep["n_pair_records"]

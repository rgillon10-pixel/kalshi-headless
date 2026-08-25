"""scripts/monitor_ingest.py — tape -> monitor.db, with the two idempotence layers proven:
re-running over the same files adds zero rows, appended lines land incrementally, and a
rewritten (shrunk) append-only file is detected, re-read, and COUNTED as a reset."""
from __future__ import annotations

import json
import sqlite3

from scripts import monitor_ingest as mi


def _ws_lines():
    return [
        {"schema_version": "ws_depth.v1", "capture_id": "c1", "captured_at": "t1",
         "venue": "kalshi", "channel": "orderbook_delta", "msg_type": "orderbook_delta",
         "market_ticker": "T", "seq": 2, "raw_sha256": "a" * 64, "price_source_tag":
         "real_ask", "raw": {"msg": {"market_ticker": "T", "price_dollars": "0.41",
                                     "delta_fp": "5", "side": "yes"}}},
        {"schema_version": "ws_depth.v1", "capture_id": "c2", "captured_at": "t2",
         "venue": "kalshi", "channel": "trade", "msg_type": "trade", "market_ticker": "T",
         "seq": None, "raw_sha256": "b" * 64, "price_source_tag": "broker_truth",
         "raw": {"msg": {"market_ticker": "T", "yes_price_dollars": "0.44",
                         "count_fp": "25", "taker_side": "yes", "ts": 175}}},
        {"schema_version": "ws_depth.snapshot60.v1", "capture_id": "c3",
         "captured_at": "t3", "market_ticker": "T", "yes_bid": 0.41, "yes_ask": 0.42,
         "no_bid": 0.58, "mid": 0.415, "spread": 0.01, "yes_depth_top": 105.0,
         "no_depth_top": 80.0, "yes_bids_top": [[0.41, 105]], "no_bids_top": [[0.58, 80]],
         "price_source_tag": "real_ask"},
        {"schema_version": "ws_depth.gap.v1", "capture_id": "c4:gap", "captured_at": "t4",
         "market_ticker": "T", "expected_seq": 3, "got_seq": 9, "missed": 6},
        {"schema_version": "ws_depth.session.v1", "capture_id": "c5",
         "captured_at": "t5", "type": "session_open", "n_tickers": 1},
    ]


def _tape(tmp_path, ws_extra=()):
    root = tmp_path / "tape"
    (root / "ws_depth").mkdir(parents=True)
    (root / "monitor_markets").mkdir()
    (root / "settlement_ledger").mkdir()
    ws = list(_ws_lines()) + list(ws_extra)
    (root / "ws_depth" / "dt=2026-08-24.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in ws))
    (root / "monitor_markets" / "dt=2026-08-24.jsonl").write_text(json.dumps(
        {"schema_version": "monitor_scope.v1", "capture_id": "m1", "captured_at": "t1",
         "ticker": "T", "event_ticker": "E", "series": "KXT", "category": "Mentions",
         "title": "x", "status": "active", "open_time": "o", "close_time": "c",
         "expected_expiration_time": None, "volume_24h": 5.0, "open_interest": 1.0,
         "ws_selected": True}) + "\n")
    (root / "settlement_ledger" / "dt=2026-08-24.jsonl").write_text(json.dumps(
        {"schema_version": "settlement_ledger.v1", "capture_id": "s1", "captured_at": "t9",
         "ticker": "T", "close_time": "c", "result": "yes", "settlement_value": 1.0,
         "series": "KXT", "settlement_ts": "st", "price_source_tag": "broker_truth"}
    ) + "\n")
    return root


def _counts(db):
    conn = sqlite3.connect(db)
    try:
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ("markets", "book_events", "snapshots", "trades", "gaps",
                          "settlements")}
    finally:
        conn.close()


def test_ingest_routes_every_family_and_reruns_add_nothing(tmp_path):
    root = _tape(tmp_path)
    db = tmp_path / "monitor.db"
    s1 = mi.run(db_path=db, tape_root=root)
    assert s1["completeness_ok"] is True and s1["n_bad_lines"] == 0
    expected = {"markets": 1, "book_events": 1, "snapshots": 1, "trades": 1, "gaps": 1,
                "settlements": 1}
    assert s1["rows"] == expected and _counts(db) == expected
    s2 = mi.run(db_path=db, tape_root=root)      # idempotence layer 1: offsets
    assert s2["n_new_lines"] == 0 and s2["rows"] == expected


def test_appended_lines_ingest_incrementally(tmp_path):
    root = _tape(tmp_path)
    db = tmp_path / "monitor.db"
    mi.run(db_path=db, tape_root=root)
    extra = dict(_ws_lines()[1])
    extra.update(capture_id="c9", raw_sha256="d" * 64)
    with open(root / "ws_depth" / "dt=2026-08-24.jsonl", "a") as fh:
        fh.write(json.dumps(extra) + "\n")
    s = mi.run(db_path=db, tape_root=root)
    assert s["n_new_lines"] == 1 and s["rows"]["trades"] == 2


def test_shrunk_file_resets_rereads_and_dedupes(tmp_path):
    root = _tape(tmp_path)
    db = tmp_path / "monitor.db"
    mi.run(db_path=db, tape_root=root)
    p = root / "ws_depth" / "dt=2026-08-24.jsonl"
    lines = p.read_text().splitlines()
    p.write_text("".join(l + "\n" for l in lines[:3]))     # rewrite violation: shrunk
    s = mi.run(db_path=db, tape_root=root)
    assert s["n_reset_files"] == 1
    assert s["completeness_ok"] is False                    # a rewrite is FLAGGED, not ok
    # idempotence layer 2: the replayed lines were INSERT OR IGNOREd, no duplicates
    assert _counts(db)["trades"] == 1 and _counts(db)["book_events"] == 1


def test_bad_line_counted_and_recorded_never_dropped(tmp_path):
    root = _tape(tmp_path, ws_extra=())
    with open(root / "ws_depth" / "dt=2026-08-24.jsonl", "a") as fh:
        fh.write("{not json\n")
    db = tmp_path / "monitor.db"
    s = mi.run(db_path=db, tape_root=root)
    assert s["n_bad_lines"] == 1 and s["completeness_ok"] is False
    conn = sqlite3.connect(db)
    bad = conn.execute("SELECT path, line_no FROM ingest_bad_lines").fetchall()
    conn.close()
    assert len(bad) == 1 and bad[0][1] == 5                 # file + offset recorded

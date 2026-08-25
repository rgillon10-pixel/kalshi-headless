#!/usr/bin/env python3
"""Idempotent tape -> data/monitor.db ingest (the monitor's queryable layer).

Raw truth stays on tape (append-only JSONL, the house record). This script folds three
families into one VPS-local SQLite DB so Layer 2/3/4 can query by market and time without
re-streaming gzipped days:

  tape/ws_depth/dt=*.jsonl[.gz]      -> book_events, snapshots, trades
  tape/monitor_markets/dt=*.jsonl    -> markets            (lifecycle: open/close times)
  tape/settlement_ledger/dt=*.jsonl  -> settlements        (broker_truth labels)

Idempotence, two layers (safe to re-run over the same files any number of times):
  1. per-file line offsets in `ingest_files` — a re-run reads only lines it has not seen
     (tape files are append-only; a shrunk file is a REWRITE violation and is re-read from
     zero, counted in `n_reset_files`, never silently trusted);
  2. INSERT OR IGNORE on natural keys — replayed lines (e.g. after an offset reset) land
     as no-ops, so duplicates are structurally impossible, not just unlikely.

The DB is derived state, VPS-local and gitignored: losing it costs a re-ingest, never data.
Every price row keeps its `price_source_tag`. Malformed lines are counted (`n_bad_lines`)
and appended to `ingest_bad_lines` with their file/offset — never silently dropped.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from core.canonical import canonical_json  # noqa: E402

DB_PATH_DEFAULT = REPO_ROOT / "data" / "monitor.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS markets (
  ticker TEXT PRIMARY KEY, event_ticker TEXT, series TEXT, category TEXT, title TEXT,
  open_time TEXT, close_time TEXT, expected_expiration_time TEXT,
  volume_24h REAL, open_interest REAL, ws_selected INTEGER,
  first_seen TEXT, last_seen TEXT);
CREATE TABLE IF NOT EXISTS book_events (
  capture_id TEXT, raw_sha256 TEXT, market_ticker TEXT, msg_type TEXT, seq INTEGER,
  captured_at TEXT, side TEXT, price REAL, delta REAL, price_source_tag TEXT,
  PRIMARY KEY (capture_id, raw_sha256));
CREATE TABLE IF NOT EXISTS snapshots (
  capture_id TEXT, market_ticker TEXT, captured_at TEXT,
  yes_bid REAL, yes_ask REAL, no_bid REAL, mid REAL, spread REAL,
  yes_depth_top REAL, no_depth_top REAL,
  yes_bids_top TEXT, no_bids_top TEXT, price_source_tag TEXT,
  PRIMARY KEY (capture_id, market_ticker));
CREATE TABLE IF NOT EXISTS trades (
  capture_id TEXT, raw_sha256 TEXT, market_ticker TEXT, captured_at TEXT,
  yes_price REAL, count REAL, taker_side TEXT, exchange_ts TEXT, price_source_tag TEXT,
  PRIMARY KEY (capture_id, raw_sha256));
CREATE TABLE IF NOT EXISTS gaps (
  capture_id TEXT PRIMARY KEY, market_ticker TEXT, captured_at TEXT,
  expected_seq INTEGER, got_seq INTEGER, missed INTEGER);
CREATE TABLE IF NOT EXISTS settlements (
  ticker TEXT, close_time TEXT, result TEXT, settlement_value REAL,
  series TEXT, settlement_ts TEXT, captured_at TEXT, price_source_tag TEXT,
  PRIMARY KEY (ticker, close_time, result));
CREATE TABLE IF NOT EXISTS ingest_files (
  path TEXT PRIMARY KEY, lines_done INTEGER NOT NULL, bytes_seen INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS ingest_bad_lines (
  path TEXT, line_no INTEGER, error TEXT, PRIMARY KEY (path, line_no));
CREATE INDEX IF NOT EXISTS idx_snapshots_mkt_t ON snapshots (market_ticker, captured_at);
CREATE INDEX IF NOT EXISTS idx_trades_mkt_t ON trades (market_ticker, captured_at);
CREATE INDEX IF NOT EXISTS idx_book_mkt_t ON book_events (market_ticker, captured_at);
"""


def _open_db(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def _iter_lines(path: Path) -> Iterator[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            yield line.rstrip("\n")


def _body(rec: Dict[str, Any]) -> Dict[str, Any]:
    raw = rec.get("raw") or {}
    return raw.get("msg") if isinstance(raw.get("msg"), dict) else raw


def _ingest_ws_line(conn: sqlite3.Connection, rec: Dict[str, Any]) -> None:
    sv = rec.get("schema_version")
    if sv == "ws_depth.snapshot60.v1":
        conn.execute(
            "INSERT OR IGNORE INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rec["capture_id"], rec.get("market_ticker"), rec.get("captured_at"),
             rec.get("yes_bid"), rec.get("yes_ask"), rec.get("no_bid"), rec.get("mid"),
             rec.get("spread"), rec.get("yes_depth_top"), rec.get("no_depth_top"),
             canonical_json(rec.get("yes_bids_top") or []),
             canonical_json(rec.get("no_bids_top") or []),
             rec.get("price_source_tag")))
    elif sv == "ws_depth.gap.v1":
        conn.execute(
            "INSERT OR IGNORE INTO gaps VALUES (?,?,?,?,?,?)",
            (rec["capture_id"], rec.get("market_ticker"), rec.get("captured_at"),
             rec.get("expected_seq"), rec.get("got_seq"), rec.get("missed")))
    elif sv == "ws_depth.v1":
        msg_type, body = rec.get("msg_type"), _body(rec)
        if msg_type == "trade":
            price = body.get("yes_price_dollars", body.get("yes_price"))
            conn.execute(
                "INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?)",
                (rec["capture_id"], rec.get("raw_sha256"), rec.get("market_ticker"),
                 rec.get("captured_at"), _f(price), _f(body.get("count_fp",
                 body.get("count"))), body.get("taker_side"), str(body.get("ts") or ""),
                 rec.get("price_source_tag")))
        elif msg_type in ("orderbook_delta", "orderbook_snapshot"):
            conn.execute(
                "INSERT OR IGNORE INTO book_events VALUES (?,?,?,?,?,?,?,?,?,?)",
                (rec["capture_id"], rec.get("raw_sha256"), rec.get("market_ticker"),
                 msg_type, rec.get("seq"), rec.get("captured_at"), body.get("side"),
                 _f(body.get("price_dollars", body.get("price"))),
                 _f(body.get("delta_fp", body.get("delta"))),
                 rec.get("price_source_tag")))
        # session/subscribed/error control lines carry no analytic state: tape-only


def _f(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except (TypeError, ValueError):
        return None


def _ingest_market_line(conn: sqlite3.Connection, rec: Dict[str, Any]) -> None:
    if rec.get("schema_version") != "monitor_scope.v1" or not rec.get("ticker"):
        return
    conn.execute(
        """INSERT INTO markets VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(ticker) DO UPDATE SET
             volume_24h=excluded.volume_24h, open_interest=excluded.open_interest,
             ws_selected=excluded.ws_selected, last_seen=excluded.last_seen,
             close_time=excluded.close_time,
             expected_expiration_time=excluded.expected_expiration_time""",
        (rec["ticker"], rec.get("event_ticker"), rec.get("series"), rec.get("category"),
         rec.get("title"), rec.get("open_time"), rec.get("close_time"),
         rec.get("expected_expiration_time"), rec.get("volume_24h"),
         rec.get("open_interest"), 1 if rec.get("ws_selected") else 0,
         rec.get("captured_at"), rec.get("captured_at")))


def _ingest_settlement_line(conn: sqlite3.Connection, rec: Dict[str, Any]) -> None:
    if rec.get("schema_version") != "settlement_ledger.v1" or not rec.get("ticker"):
        return
    conn.execute(
        "INSERT OR IGNORE INTO settlements VALUES (?,?,?,?,?,?,?,?)",
        (rec["ticker"], rec.get("close_time"), rec.get("result"),
         rec.get("settlement_value"), rec.get("series"), rec.get("settlement_ts"),
         rec.get("captured_at"), rec.get("price_source_tag")))


FAMILIES = (
    ("ws_depth", ("dt=*.jsonl", "dt=*.jsonl.gz"), _ingest_ws_line),
    ("monitor_markets", ("dt=*.jsonl",), _ingest_market_line),
    ("settlement_ledger", ("dt=*.jsonl",), _ingest_settlement_line),
)


def _ingest_file(conn: sqlite3.Connection, path: Path, handler, rel: str
                 ) -> Tuple[int, int, bool]:
    """Returns (n_new_lines, n_bad, was_reset). Incremental by line offset; a file smaller
    than last time (rewrite of append-only tape) resets to zero and re-reads."""
    row = conn.execute("SELECT lines_done, bytes_seen FROM ingest_files WHERE path=?",
                       (rel,)).fetchone()
    lines_done = row[0] if row else 0
    size = path.stat().st_size
    was_reset = bool(row and size < row[1])
    if was_reset:
        lines_done = 0
    n_new = n_bad = 0
    for i, line in enumerate(_iter_lines(path)):
        if i < lines_done:
            continue
        n_new += 1
        try:
            handler(conn, json.loads(line))
        except (ValueError, KeyError, TypeError) as exc:
            n_bad += 1
            conn.execute("INSERT OR IGNORE INTO ingest_bad_lines VALUES (?,?,?)",
                         (rel, i, repr(exc)[:200]))
    conn.execute("INSERT OR REPLACE INTO ingest_files VALUES (?,?,?)",
                 (rel, lines_done + n_new, size))
    return n_new, n_bad, was_reset


def run(db_path: Path = DB_PATH_DEFAULT, tape_root: Path = REPO_ROOT / "tape"
        ) -> Dict[str, Any]:
    conn = _open_db(db_path)
    n_new = n_bad = n_files = n_reset = 0
    try:
        for family, globs, handler in FAMILIES:
            fam_dir = tape_root / family
            if not fam_dir.is_dir():
                continue
            for pattern in globs:
                for path in sorted(fam_dir.glob(pattern)):
                    rel = str(path.relative_to(tape_root))
                    new, bad, reset = _ingest_file(conn, path, handler, rel)
                    n_new += new
                    n_bad += bad
                    n_files += 1
                    n_reset += 1 if reset else 0
            conn.commit()
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("markets", "book_events", "snapshots", "trades", "gaps",
                            "settlements")}
    finally:
        conn.close()
    summary = {"n_files_seen": n_files, "n_new_lines": n_new, "n_bad_lines": n_bad,
               "n_reset_files": n_reset, "rows": counts,
               "completeness_ok": n_bad == 0 and n_reset == 0}
    print(f"[monitor_ingest] {canonical_json(summary)}", flush=True)
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Idempotent tape -> monitor.db ingest.")
    ap.add_argument("--db", default=str(DB_PATH_DEFAULT))
    ap.add_argument("--tape-root", default=str(REPO_ROOT / "tape"))
    args = ap.parse_args(argv)
    summary = run(Path(args.db), Path(args.tape_root))
    return 0 if summary["completeness_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

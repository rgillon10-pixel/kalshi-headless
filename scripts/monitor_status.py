#!/usr/bin/env python3
"""One-screen monitor status (`make status`). Read-only; degrades gracefully — every
section reports honestly when its source is missing (a dead service and an absent DB are
findings, not crashes). Designed to run ON the VPS; the Makefile target ssh-wraps it."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DB = REPO_ROOT / "data" / "monitor.db"
UNITS = ("kalshi-headless-wsdepth.service",)


def _unit_state(unit: str) -> str:
    try:
        out = subprocess.run(["systemctl", "is-active", unit],
                             capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "no-systemctl"


def _q(conn, sql, args=()):
    try:
        return conn.execute(sql, args).fetchall()
    except sqlite3.Error as exc:
        return [("query-error", repr(exc)[:80])]


def main() -> int:
    now = datetime.now(timezone.utc)
    print(f"MONITOR STATUS — {now.isoformat(timespec='seconds')}")

    print("\nServices:")
    for u in UNITS:
        print(f"  {u}: {_unit_state(u)}")

    ws_dir = REPO_ROOT / "tape" / "ws_depth"
    files = sorted(ws_dir.glob("dt=*")) if ws_dir.is_dir() else []
    if files:
        newest = max(f.stat().st_mtime for f in files)
        age = int(now.timestamp() - newest)
        print(f"\nws_depth tape: {len(files)} day file(s), last write {age}s ago")
    else:
        print("\nws_depth tape: NONE (daemon not yet writing)")

    if DB.exists():
        size_mb = DB.stat().st_size / 1e6
        conn = sqlite3.connect(DB)
        print(f"\nmonitor.db: {size_mb:.1f} MB")
        for table, in _q(conn, "SELECT name FROM sqlite_master WHERE type='table' "
                               "AND name NOT LIKE 'ingest_%' ORDER BY name"):
            n = _q(conn, f"SELECT COUNT(*) FROM {table}")[0][0]
            print(f"  {table:<12} {n:>10} rows")
        print("\nLast event per series (top 10 by recency):")
        rows = _q(conn, """
            SELECT m.series, MAX(s.captured_at), COUNT(*) FROM snapshots s
            JOIN markets m ON m.ticker = s.market_ticker
            GROUP BY m.series ORDER BY 2 DESC LIMIT 10""")
        for series, last, n in rows:
            print(f"  {series:<22} last={last}  n={n}")
        if not rows:
            print("  (no snapshots ingested yet)")
        conn.close()
    else:
        print(f"\nmonitor.db: MISSING ({DB})")

    nightly = sorted((REPO_ROOT / "reports" / "nightly").glob("2*.md"))
    print(f"\nLast nightly report: {nightly[-1].name if nightly else 'none yet'}")

    inv = sorted((REPO_ROOT / "tape" / "monitor_investigations").glob("dt=*.jsonl"))
    print(f"Last investigation tape: {inv[-1].name if inv else 'none yet'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

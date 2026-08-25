#!/usr/bin/env bash
# Monitor tape -> monitor.db ingest — VPS cron every 15 min.
# Canonical copy in-repo (ops/vps/); installed at /root/bin/kalshi-headless-ingest.sh via:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-ingest.sh /root/bin/kalshi-headless-ingest.sh'
#
# Idempotent by construction (scripts/monitor_ingest.py: per-file offsets + INSERT OR
# IGNORE), so an overlapping or repeated run is harmless; flock just avoids wasted work.
set -u
REPO=/root/kalshi-headless
LOCK=/root/.kalshi-headless-ingest.lock
exec 9>"$LOCK"
flock -n 9 || { echo "$(date -u +%FT%TZ) skip: previous ingest still running"; exit 0; }

cd "$REPO" || exit 1
.venv/bin/python scripts/monitor_ingest.py

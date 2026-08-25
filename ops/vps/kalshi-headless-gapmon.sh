#!/usr/bin/env bash
# Tape gap-monitor cron wrapper — VPS runner (every 6h).
# Canonical copy lives in-repo (ops/vps/); installed on the VPS at
# /root/bin/kalshi-headless-gapmon.sh. After changing this file, install with:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-gapmon.sh /root/bin/kalshi-headless-gapmon.sh'
#
# Why this exists: the hourly pass was import-dead 2026-07-28 → 2026-08-24 (27 days,
# zero tape) and nothing alerted. scripts/tape_gap_monitor.py detects exactly that
# (STALE + UNDER-CAPTURE per family) and POSTs one high-priority ntfy when a family
# alerts — but it was never wired into cron. This wrapper is that wiring.
#
# Read-only over committed tape; its only outbound call is the ntfy POST, whose URL
# comes from NTFY_TOPIC_URL in /root/.secrets/kalshi-headless.env. Per lesson L156:
# if that env var is missing the POST is silently skipped, so the wrapper fails loudly
# instead of pretending the alert path works.
set -u
REPO=/root/kalshi-headless

if [ -f /root/.secrets/kalshi-headless.env ]; then
  set -a; . /root/.secrets/kalshi-headless.env; set +a
fi
if [ -z "${NTFY_TOPIC_URL:-}" ]; then
  echo "$(date -u +%FT%TZ) ERROR: NTFY_TOPIC_URL unset — gap monitor would run alert-less (L156); aborting"
  exit 1
fi

cd "$REPO"
echo "$(date -u +%FT%TZ) gap-monitor pass"
.venv/bin/python scripts/tape_gap_monitor.py --json

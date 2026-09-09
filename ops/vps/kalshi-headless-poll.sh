#!/usr/bin/env bash
# Public-REST snapshot fallback — VPS cron every minute.
# Canonical copy in-repo (ops/vps/); installed at /root/bin/kalshi-headless-poll.sh via:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-poll.sh /root/bin/kalshi-headless-poll.sh'
#
# Runs collection/monitor_poll.py: NO credentials needed (public /markets listing). It
# stands down by itself whenever ws_depth tape is fresh, so it is always safe to leave
# scheduled. flock guards against a slow pass overlapping the next minute.
set -u
REPO=/root/kalshi-headless
LOCK=/root/.kalshi-headless-poll.lock
exec 9>"$LOCK"
flock -n 9 || exit 0

cd "$REPO" || exit 1
exec .venv/bin/python -m collection.monitor_poll

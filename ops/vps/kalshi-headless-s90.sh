#!/usr/bin/env bash
# S90 / Probe C daily PAPER pass — VPS cron. Canonical copy in-repo (ops/vps/); installed at
# /root/bin/kalshi-headless-s90.sh via:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-s90.sh /root/bin/kalshi-headless-s90.sh'
#
# crontab (UTC):
#   35 0  * * *  /root/bin/kalshi-headless-s90.sh propose >> /root/kalshi-headless-ops/s90.log 2>&1
#   10 14 * * *  /root/bin/kalshi-headless-s90.sh settle  >> /root/kalshi-headless-ops/s90.log 2>&1
#
# This script is PAPER ONLY: it never passes --live and never loads credentials. The live
# tier is a separate, Ryan-run step after LIVE-AUTH-S90.md is signed (see
# reset-2026-09/50-probes/PROBE-C-weather-favorite-taker.md, "Going live").
set -u
REPO=/root/kalshi-headless
LOCK=/root/.kalshi-headless-s90.lock
MODE="${1:-propose}"
case "$MODE" in propose|settle|report) ;; *) echo "usage: $0 propose|settle|report" >&2; exit 2;; esac
exec 9>"$LOCK"
flock -n 9 || exit 0
cd "$REPO" || exit 1

.venv/bin/python scripts/s90_daily_pass.py "$MODE"
rc=$?
# commit the day's tape + paper ledger lines (append-only provenance, like the hourly pass)
git add -A tape/s90_weather paper/ledger_s90 2>/dev/null
git -c user.name=vps -c user.email=vps@kalshi-headless commit -q -m "s90: paper $MODE $(date -u +%FT%TZ) (vps)" 2>/dev/null || true
git pull -q --rebase --autostash 2>/dev/null && git push -q 2>/dev/null || true
exit $rc

#!/usr/bin/env bash
# WS-depth liveness check — VPS cron every 5 min.
# Canonical copy in-repo (ops/vps/); installed at /root/bin/kalshi-headless-healthcheck.sh via:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-healthcheck.sh /root/bin/kalshi-headless-healthcheck.sh'
#
# Liveness signal: the newest mtime across tape/ws_depth/ AND tape/monitor_poll/ — the
# monitor is "collecting" when EITHER the WS daemon (snapshot60 every 60s even in quiet
# markets) or the public-REST fallback (one pass per minute) is writing. Escalation
# ladder (state in /root/.kalshi-headless-health):
#   fresh                 -> clear state, exit 0
#   stale (>STALE_SEC)    -> restart the WS unit once (the only restartable piece;
#                            the poller is cron-driven and has no daemon to restart)
#   still stale next run  -> ntfy HIGH (once per outage, not per check — the state file
#                            is the rate limiter; cleared the moment tape is fresh again)
set -u
REPO=/root/kalshi-headless
UNIT=kalshi-headless-wsdepth.service
STATE=/root/.kalshi-headless-health
STALE_SEC=180

if [ -f /root/.secrets/kalshi-headless.env ]; then
  set -a; . /root/.secrets/kalshi-headless.env; set +a
fi

notify_high() {
  [ -n "${NTFY_TOPIC_URL:-}" ] || return 0
  curl -s -m 10 -H "Title: Kalshi monitor healthcheck" -H "Priority: high" \
       -d "$1" "$NTFY_TOPIC_URL" >/dev/null 2>&1 || true
}

newest=$(find "$REPO/tape/ws_depth" "$REPO/tape/monitor_poll" -type f -name 'dt=*' -newermt "-${STALE_SEC} seconds" 2>/dev/null | head -1)

if [ -n "$newest" ]; then
  rm -f "$STATE"
  exit 0
fi

now=$(date -u +%FT%TZ)
if [ ! -f "$STATE" ]; then
  echo "restarted_at=$now" > "$STATE"
  echo "$now stale tape (> ${STALE_SEC}s) -> restarting $UNIT"
  systemctl restart "$UNIT"
elif ! grep -q alerted "$STATE"; then
  echo "alerted_at=$now" >> "$STATE"
  echo "$now still stale after restart -> alerting"
  notify_high "Monitor tape is stale (no ws_depth OR rest-poll writes for >${STALE_SEC}s) and a WS restart did not fix it. The monitor is NOT collecting — check the poll cron too."
else
  echo "$now still stale (already alerted)"
fi
exit 1

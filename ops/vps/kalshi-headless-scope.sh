#!/usr/bin/env bash
# Monitor scope resolver — VPS hourly cron (READ-ONLY except config/ws_depth_tickers.txt).
# Canonical copy in-repo (ops/vps/); installed at /root/bin/kalshi-headless-scope.sh via:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-scope.sh /root/bin/kalshi-headless-scope.sh'
#
# Runs collection/monitor_scope.py (config/monitor.yaml scope -> tape/monitor_markets +
# config/ws_depth_tickers.txt), then restarts the ws_depth daemon ONLY when the subscribed
# set actually changed — detected from the summary's "tickers_changed":true, so ranking
# churn alone never bounces the WS session. Offset from the hourly pass (:23) to :08 so
# the two never contend for the API in the same minute.
set -u
REPO=/root/kalshi-headless
UNIT=kalshi-headless-wsdepth.service

cd "$REPO" || exit 1
if [ -f /root/.secrets/kalshi-headless.env ]; then
  set -a; . /root/.secrets/kalshi-headless.env; set +a
fi

OUT=$(.venv/bin/python -m collection.monitor_scope 2>&1)
rc=$?
echo "$OUT"

if printf '%s' "$OUT" | grep -q '"tickers_changed":true'; then
  echo "$(date -u +%FT%TZ) ticker set changed -> restarting $UNIT"
  systemctl restart "$UNIT" || echo "$(date -u +%FT%TZ) WARN: restart of $UNIT failed"
fi
exit "$rc"

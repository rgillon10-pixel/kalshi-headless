#!/usr/bin/env bash
# kalshi.headless WS-depth daemon — VPS runner (READ-ONLY market-data collector).
# Canonical copy in-repo (ops/vps/); installed on the VPS at
# /root/bin/kalshi-headless-wsdepth.sh. After changing this file, install with:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-wsdepth.sh /root/bin/kalshi-headless-wsdepth.sh'
#
# Why a wrapper (not python straight from the unit): it sources the secrets file the SAME
# way the hourly runner does (`set -a; . file`), so any shell syntax in
# /root/.secrets/kalshi-headless.env is honored — no key -> collection.ws_depth exits
# blocked_key on its own (self-activating). The daemon writes tape/ws_depth/dt=*.jsonl.gz;
# the hourly runner's `git add tape/` commits those files on its next pass (no wiring here).
set -u
REPO=/root/kalshi-headless

cd "$REPO" || exit 1
if [ -f /root/.secrets/kalshi-headless.env ]; then
  set -a; . /root/.secrets/kalshi-headless.env; set +a
fi

# exec so systemd tracks the python process directly (clean SIGTERM -> daemon flushes+closes).
exec .venv/bin/python -m collection.ws_depth

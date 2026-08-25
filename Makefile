# kalshi.headless — operator conveniences. The monitor runs on the VPS; these targets are
# how a human checks on it without remembering paths.

VPS = root@87.99.146.250
SSH = ssh -i ~/.ssh/id_ed25519 $(VPS)

.PHONY: status status-local test

# One-screen monitor status from the VPS (services, tape freshness, DB rows, last nightly).
status:
	$(SSH) 'cd /root/kalshi-headless && .venv/bin/python scripts/monitor_status.py'

# Same, against this local checkout (useful when hacking on the ingest/analytics locally).
status-local:
	.venv/bin/python scripts/monitor_status.py

test:
	.venv/bin/python -m pytest -q

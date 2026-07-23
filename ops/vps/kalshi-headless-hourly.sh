#!/usr/bin/env bash
# Hourly kalshi.headless tape collector — VPS runner.
# Canonical copy lives in-repo (ops/vps/); installed on the VPS at
# /root/bin/kalshi-headless-hourly.sh. After changing this file, install with:
#   ssh root@87.99.146.250 'git -C /root/kalshi-headless pull -q --ff-only && \
#     install -m755 /root/kalshi-headless/ops/vps/kalshi-headless-hourly.sh /root/bin/kalshi-headless-hourly.sh'
#
# Lives outside the repo checkout so git rebases always see a clean tree.
# Push failures leave the commit local; the next hourly run carries it forward,
# so nothing ever strands on a side branch.
set -u
REPO=/root/kalshi-headless
LOCK=/root/.kalshi-headless-hourly.lock
exec 9>"$LOCK"
flock -n 9 || { echo "$(date -u +%FT%TZ) skip: previous run still holds the lock"; exit 0; }

cd "$REPO"
if [ -f /root/.secrets/kalshi-headless.env ]; then
  set -a; . /root/.secrets/kalshi-headless.env; set +a
fi

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Phone note via ntfy — topic URL comes from /root/.secrets/kalshi-headless.env (NTFY_TOPIC_URL).
# Priority "low" = silent feed entry; "high" = buzz Ryan. Never fails the run.
notify() {
  local url
  url="${NTFY_TOPIC_URL:-}"
  [ -n "$url" ] || url=$(cat "$REPO/config/notify.topic" 2>/dev/null) || return 0
  [ -n "$url" ] || return 0
  curl -s -m 10 -H "Title: Kalshi hourly scan (VPS)" -H "Priority: $1" -d "$2" "$url" >/dev/null 2>&1 || true
}

# Self-heal: a crashed rebase must never wedge the collector. A stale
# .git/rebase-merge dir blocked every run 2026-07-18→21 (3 days of tape lost)
# while the script paged Ryan hourly with no recovery path. The 2h age floor
# keeps this from killing a rebase some human is legitimately mid-flight on.
for state in "$REPO/.git/rebase-merge" "$REPO/.git/rebase-apply"; do
  if [ -d "$state" ] && [ -z "$(find "$state" -maxdepth 0 -mmin -120)" ]; then
    echo "$(ts) WARN: stale rebase state at $state — aborting it"
    git rebase --abort 2>/dev/null || rm -rf "$state"
    notify high "Hourly scan found and cleared a stuck git rebase left by a previous run. Collection resuming."
  fi
done

# Recover any tape left uncommitted by a previous failed run.
if ! git diff --quiet -- tape/ || [ -n "$(git ls-files --others --exclude-standard tape/)" ]; then
  git add tape/ && git commit -q -m "tape: recover uncommitted pass ($(ts)) (vps)" || true
fi

if ! git pull --rebase -q origin main; then
  # A failed pre-pass rebase leaves rebase state behind; clean it now so the
  # NEXT run isn't wedged (the 2026-07-18 failure mode), then union-recovery
  # below still runs against the pre-pull HEAD next hour.
  git rebase --abort 2>/dev/null || true
  echo "$(ts) ERROR: pre-pass rebase failed"
  notify high "Hourly scan hit a snag: couldn't sync with GitHub before scanning. It will retry automatically next hour."
  exit 1
fi

# Daily pipe-health check (scripts/tape_gap_monitor.py, Q44): the monitor existed but
# nothing scheduled it, so gaps (07-09 blackout, settlement_ledger freeze) sat unnoticed
# until a human ran it. Stamp-file gated at ~22h — deliberately NOT an exact-hour gate
# (L123/L124: exact-hour gates freeze silently when the cron misses that hour). It posts
# its own Priority:high ntfy note on a hard alert via NTFY_TOPIC_URL (already exported
# from /root/.secrets above); never fails the collection run.
GAPSTAMP=/root/.kalshi-headless-gapmon.stamp
if [ -z "$(find "$GAPSTAMP" -mmin -1320 2>/dev/null)" ]; then
  echo "$(ts) daily tape_gap_monitor run"
  .venv/bin/python scripts/tape_gap_monitor.py 2>&1 | sed -n '1,40p' || true
  touch "$GAPSTAMP"
fi

PASS_OUT=$(.venv/bin/python -m collection.hourly_pass 2>&1)
pass_rc=$?
echo "$PASS_OUT"
# e.g. "[hourly_pass] 645 markets, 178 lines, completeness ok"
SUMMARY=$(printf '%s\n' "$PASS_OUT" | grep -o '\[hourly_pass\].*' | tail -1 | sed 's/\[hourly_pass\] //')

git add tape/
if git diff --cached --quiet; then
  echo "$(ts) no new tape lines (pass rc=$pass_rc)"
  notify high "Hourly scan ran but captured nothing new (${SUMMARY:-no summary}). Worth a look if this repeats."
  exit "$pass_rc"
fi
git commit -q -m "tape: hourly pass $(ts) (vps)"

pushed=""
for attempt in 1 2 3; do
  if git push -q origin main; then
    echo "$(ts) pushed (pass rc=$pass_rc, attempt $attempt)"
    pushed=yes
    break
  fi
  sleep 15
  git pull --rebase -q origin main || git rebase --abort 2>/dev/null || true
done

if [ "$pass_rc" -ne 0 ]; then
  notify high "Hourly scan finished with gaps: ${SUMMARY:-completeness FAIL}. Data that was captured is saved."
elif [ -z "$pushed" ]; then
  echo "$(ts) WARN: push failed 3x; commit left local for next run to carry"
  notify high "Hourly scan worked (${SUMMARY}) but couldn't upload to GitHub — it will carry the data forward next hour."
  exit 1
else
  notify low "Hourly scan ok: ${SUMMARY}. Data saved."
fi
exit "$pass_rc"

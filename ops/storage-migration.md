# Tape storage migration — bulk families off git

`v1 · 2026-07-22` — Ryan-approved direction (background session, "build up a strong data
stream" pivot): keep collecting autonomously for months; move the bulk tape families out of
git before the repo becomes unusable, WITHOUT giving up the append-only audit trail.

## Why now

- `tape/` is **1.1 GB**, ~22× the 50 MB external-storage trigger `tape/README.md` set.
- Three families are 83% of it: `universe_sweep` (392M), `orderbook_depth` (307M),
  `sports_pairs` (218M). universe_sweep alone adds ~100 MB every few days → **5–10 GB by
  late September** on the current trajectory.
- The VPS already OOM-kills on big git fetches (memory caps); every cloud sandbox pull and
  every stranded-branch sweep pays the full clone cost.

## Target architecture

| layer | lives | holds |
|---|---|---|
| git (this repo) | GitHub | small/medium families as today · per-day **ARCHIVE-MANIFEST.jsonl** per bulk family (sha256, line count, byte size, date) · all code/docs |
| VPS disk | `/root/tape-archive/<family>/` | bulk-family dt files older than the hot window (default 14 days) |
| object storage | Backblaze B2 (or Cloudflare R2), one private bucket | nightly `rclone sync` mirror of `/root/tape-archive/` (~$1–2/mo at 10 GB) |

The **hot window stays in git** — collectors keep committing exactly as today, and probes
that read "recent tape" (paper broker, gap monitor, hourly probes) see no change. Only
cold dt files migrate. The manifest line is written BEFORE the file leaves git, so the
append-only audit trail (what was captured, its hash, its size) survives in git forever;
any analyst can verify a restored archive file byte-for-byte against the committed sha256.

Trust posture unchanged: archived bytes carry the same in-line `price_source_tag`s; the
manifest adds provenance, it never replaces per-line tags.

## Mechanism

`scripts/tape_archive.py` (this PR) does the mechanical half:

- Only touches `BULK_FAMILIES = {universe_sweep, orderbook_depth, sports_pairs}`.
- A dt file strictly older than `--age-days` (default 14, by filename date) is: hashed +
  line-counted → appended to `tape/<family>/ARCHIVE-MANIFEST.jsonl` → copied to
  `--archive-root/<family>/` → copy re-hashed and verified → source deleted from the
  working tree. Any verification mismatch aborts that file untouched.
- **Dry-run by default**; `--apply` to act. Idempotent: already-manifested files are
  skipped, already-archived identical files verify-and-continue.
- It never calls git. The runbook commits the deletions + manifest in one commit, so the
  swap is a single reviewable diff.

Git history keeps the old blobs (the repo does not shrink retroactively — acceptable; the
point is stopping the growth). If clone cost itself ever becomes the problem, a separate,
explicitly-Ryan-approved history rewrite would be needed — NOT part of this migration, and
in tension with the anti-rewind ruleset on main; treat as out of scope.

## Cutover runbook (VPS, one session, ~30 min)

1. **Ryan (one-time):** create the B2/R2 bucket + an app key; put credentials in
   `/root/.secrets/rclone.conf` (never in the repo or cloud sandbox).
2. On the VPS: `rclone sync /root/tape-archive b2:<bucket>/tape-archive --checksum` added
   to a nightly cron (`:40` on hour 02), after an initial manual run.
3. First archive pass: `python scripts/tape_archive.py --apply` on the VPS, then
   `git add -A tape/ && git commit -m "tape: archive cold bulk dt-files (manifests committed)" && git push`.
4. Add `python scripts/tape_archive.py --apply` to the VPS hourly script gated behind the
   same stamp-file pattern as the gap monitor (weekly is plenty: `-mmin -10000`).
5. Verify: `tape_gap_monitor` still green (it reads recent files only); a cloud research
   run still passes; repo size growth flattens.

## What cloud runs lose (explicit)

A cloud sandbox pull no longer sees bulk dt files older than the hot window. Any probe
needing deep history on the three bulk families must either run on the VPS or request a
restore (`rclone copy` back). This is deliberate: deep-history microstructure studies are
the exception; the hot window covers every scheduled loop's read pattern today. The
manifest tells any analyst exactly what exists and how to verify it.

## Rollback

Everything is copy-then-verify-then-delete with hashes in git: restoring = copying files
back from `/root/tape-archive/` (or the bucket) into `tape/<family>/` and checking them
against ARCHIVE-MANIFEST.jsonl. No information is destroyed anywhere in the pipeline.

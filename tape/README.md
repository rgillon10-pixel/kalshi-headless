# tape/ — cloud-collected forward tape (COMMITTED by design)

Unlike `data/` (local bulk, gitignored), everything under `tape/` is committed: cloud
routine runs are stateless, so git IS their persistence. Append-only JSONL, one line per
observation, every price tagged (`real_ask` / `synthetic` / …) per `core/source_tag.py`.

- `sports_pairs/` — Kalshi sports moneyline BBO (+ de-vigged sharp odds when key present) — S7/S11
- `crypto_hourly/` — hourly bracket books near settlement + spot + settle outcomes — S8/S10
- `anomalies/` — daily sweep: bracket-sum / monotonicity violations clearing the fee floor — S3
- `perp_tape/` — Kalshi crypto PERPETUAL futures (public `/margin` API, separate host):
  contract list + BTC/ETH L2 + per-contract live funding-rate estimates + finalized funding
  prints (`mode=recent` hourly, `mode=backfill` one-shot since launch) — Q42/Q43
- `cloud-env-check.md` — reachability of external APIs from the cloud sandbox (Q0)

If volume ever makes git impractical (>~50 MB), the fix is moving tape to external storage —
a deliberate decision for Ryan, not a silent change by a loop run.

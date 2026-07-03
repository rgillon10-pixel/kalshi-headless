# tape/ — cloud-collected forward tape (COMMITTED by design)

Unlike `data/` (local bulk, gitignored), everything under `tape/` is committed: cloud
routine runs are stateless, so git IS their persistence. Append-only JSONL, one line per
observation, every price tagged (`real_ask` / `synthetic` / …) per `core/source_tag.py`.

- `sports_pairs/` — Kalshi sports moneyline BBO (+ de-vigged sharp odds when key present) — S7/S11.
  Schema `sports_pairs.v2`: `game_start`/`outcome_name` always persisted; `odds_leg.status` ∈
  matched / blocked_key / unmapped_series / not_selected / sport_not_active / fetch_error /
  quota_floor / no_match / ambiguous / no_bookmaker (see `collection/odds_api.py`)
- `crypto_hourly/` — hourly bracket books near settlement + spot + settle outcomes — S8/S10
- `anomalies/` — daily sweep: bracket-sum / monotonicity violations clearing the fee floor — S3
- `cloud-env-check.md` — reachability of external APIs from the cloud sandbox (Q0)

If volume ever makes git impractical (>~50 MB), the fix is moving tape to external storage —
a deliberate decision for Ryan, not a silent change by a loop run.

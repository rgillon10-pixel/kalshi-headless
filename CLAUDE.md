# kalshi.headless — project contract

**Single focus:** *Generate a profitable set of strategies on Kalshi.*

Everything in this repo is in service of that one sentence. If a file does not
move us toward a strategy that makes money at **real, fillable prices**, it does
not belong here.

This project is born at **Tier 2** (per `arb-bot-v2`'s patterns): blocking
invariants, an audit trail, and a binding gate before any capital moves. It is
the new **canonical** Kalshi project. The older dirs (`arb-bot`, `arb-bot-v2`,
`kalshi.1`, `kalshi.ibkr`) are scratch experiments / reference — we mine them for
ideas and infra, we do not depend on them.

## Prime directive (inherited from arb-bot, non-negotiable)

1. **Prove edge at real asks.** No strategy ships live without a bootstrapped CI
   positive at **taker prices** (`yes_ask` / `no_ask`). A synthetic `raw_prob`
   is NEVER a fill price. The pt1 trade lost 9.6% partly because synthetic prices
   were treated as fillable — that mistake is forbidden here.
2. **Collect data where others aren't.** Archive L2 orderbook tape from day 1.
   Edges live in the data nobody else is keeping.
3. **Invariants over memory.** Every hard lesson becomes a CI assertion, not a
   note. The assert prevents the *next variant* of a bug; a memory file would not.

## Trust defaults

- **Default trust = FALSE.** Every persisted number carries a source tag:
  `real_ask` / `midpoint` / `synthetic` / `broker_truth`. Untagged → `synthetic`.
- No claim enters `kb/` without a re-runnable script (or cited source) that
  produced it. Distilled literature cites the paper; empirical claims cite code.
- Backtests persist per-trade: `raw_yes_ask`, `bracket_sum`, `overround_absorbed`,
  `member_count`, `models_json`, `price_source_tag`.

## Lane discipline

- `kb/` — the growing knowledge base (Kalshi API + quant-finance literature +
  strategy candidates). Karpathy method: first-principles, runnable, append-only
  log, grows with the project. See `kb/README.md`.
- `findings/` — output of codebase mining and edge research. Dossiers, ranked
  opportunities.
- `scripts/` — runnable reproductions and minimal examples (the "what I cannot
  create, I do not understand" half of the KB).
- `data/` — local tape/DBs (gitignored).

## Hard rules carried over (do not relax)

1. No `ncep_gefs025` in any model list (byte-identical to `gfs_seamless`).
2. No `pstdev(member_values)` without a `member_count >= 4` guard.
3. No `yes_ask` treated as probability — always `normalized_ask = yes_ask / bracket_sum`.
4. No synthetic-priced backtest may quote a P&L number without its `price_source_tag`.
5. Kelly sizing: regime-conditional ρ `{"benign":0.05,"mixed":0.25,"frontal":0.60}` — no static 0.4.
6. No FastAPI / HTTP servers.

## Working agreement

Plan first → approve → execute. One task at a time. Pause before anything
irreversible (live order, deploy, capital). Approval in one context does not
carry to the next.

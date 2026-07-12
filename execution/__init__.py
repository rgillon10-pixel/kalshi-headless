"""execution — the paper-trading execution spine (PAPER TIER ONLY).

This is the first sanctioned execution-lane code in kalshi.headless. It exists
under a Ryan-approved plan (interactive session 2026-07-12) and a parallel
Stop-rules amendment. Read that scope before extending anything here.

THREE-TIER LANE (only the first tier is built):

  paper  — THIS module. Pure simulation over already-committed tape. It never
           opens a socket, never authenticates, never touches a credential, and
           has NO code path that emits an order to any venue. A "fill" here is a
           deterministic replay of what the collected tape already recorded; it
           is a hypothesis about what WOULD have filled, tagged and caveated as
           such (see fill_models.py). Paper P&L is not a claim of realized money.

  demo   — NOT BUILT. Kalshi's demo/sandbox order API. Requires an authenticated
           client and network I/O. Out of scope for this milestone.

  live   — NOT BUILT. Real capital. Blocked by CLAUDE.md's prime directive: no
           strategy ships live without a bootstrapped CI positive at real
           (`yes_ask`/`no_ask`) taker prices. A live tier additionally requires a
           `LIVE-AUTH.md` runbook and credentials that DO NOT — and must never —
           exist in a cloud sandbox (BLOCKED(key) is the honest status there).
           Any live tier MUST import its risk caps from `execution.limits`
           (the single sanctioned caps site) and MUST NOT re-derive fee math
           (import from `core.pricing`, lesson L18).

Honesty defaults carried in from the collector lane (CLAUDE.md trust=FALSE):
a paper fill may only fill against a REAL, fillable price (`real_ask` for a buy
that lifts an ask, `real_bid` for a sell / a maker fill against the bid ladder).
A synthetic/modeled price is NEVER a fill price — the fill models reject it.
"""

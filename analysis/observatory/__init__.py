"""Observatory — bottom-up pattern mining over the committed tape (OBS-1 pilot).

First-principles GO 2026-07-21 (staged). This layer manufactures CANDIDATES for the
existing prober -> verifier pipeline; it never issues verdicts, never flips a registry
entry, and never places anything. Pre-registered kill: 14 nightly runs with zero
verifier-surviving promotions -> decommission and log the negative result in kb/.

Pilot scope: 3 real-ask families (universe_sweep, orderbook_depth, sports_pairs),
2 screens (cross-sectional outlier, day-over-day persistence), append-only pattern
ledger under findings/observatory/. Q39 lesson baked in from commit #1: every pattern
carries a fee-floor check where one is interpretable and a graveyard factor-family
tag — a pattern in a dead factor family can NEVER auto-promote (survival rationale
must be authored by a human or the edge-hunter, per the Q21 "nearest dead cousin"
rule).
"""

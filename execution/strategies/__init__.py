"""execution.strategies — the concrete paper (shadow) strategies.

Each module here defines one Strategy (see execution.strategy_api) that PROPOSES
orders over a read-only TapeContext. Strategies are pure: no network, no clock
beyond context.now_ts, no persistence. The PaperBroker owns filling and the
ledger; a strategy only decides what it WOULD place. Registration into
SHADOW_REGISTRY happens in execution.strategy_api.
"""

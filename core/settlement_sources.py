"""Settlement-source registry — the ONE place that enumerates every committed tape family
capable of answering "is this market's outcome known?".

Why this module exists (L300, 2026-08-07)
-----------------------------------------
On 2026-08-06 the S79 idea-stage registration (`kb/strategies/00-index.md`, `LOOP-QUEUE.md`
Q54) recorded its data-gate as *"no settlement coverage of the trade day —
`tape/settlement_ledger/` covers 07-07 -> 07-22 only"*. That claim is FALSE, and the
falseness was found the next day by an adversarial pass, not by any check: the 2026-08-03
trade day IS settlement-covered — just by a DIFFERENT family
(`tape/q51_settlement_cache/settlement.json`, `broker_truth`, 10 `finalized` markets, 9 of
which are tickers that actually traded that day). The gate is real but its REASON was wrong:
S79 is `below_min_units` (9 games < the L41 floor of 10), not "waiting on a settlement
collector". A wrong reason routes future work at the wrong blocker — it says "build a
collector" when the truth is "the population is one game short".

The general failure (L165-class, incomplete source): a data-gate assertion of the form
"family X does not cover day D" is only as strong as the SET of families the asserting run
looked at. This repo had NINE settlement-bearing surfaces when this module was written and
has TEN since 2026-08-11 (`q56_settlement_cache`, the Q56/S81 backfill) — quote
`declared_source_names()`, never a count remembered from a docstring — and only one of them
has "settlement" in its directory name path that a grep for `settlement_ledger` would find.
Three of them are EMBEDDED inside another family's records (`crypto_hourly`,
`weather_actuals`, `econ_prints`) and are invisible to any directory-name scan at all.

So: no probe, verdict, or registry row may claim "no settlement coverage" from a single
family again. Call `resolve_market_results()` (or `scripts/settlement_coverage_audit.py`)
and quote its per-source table.

Recall limit, published in the module rather than discovered later (L155/L189)
-----------------------------------------------------------------------------
`undeclared_settlement_dirs()` can only detect a NEW settlement family whose directory NAME
carries the word "settlement" (the `q*_settlement_cache` shape, which is how six of the ten
arrived). It structurally CANNOT detect a tenth family that hides settlement inside another
family's record schema, the way `crypto_hourly.previous_settlement` /
`weather_actuals.settled_markets` / `econ_prints.recent_settlement` do. A 0-issue report from
that function is therefore PRECISION evidence, never RECALL: it means "no undeclared
settlement-NAMED directory", not "the registry is complete". `EMBEDDED_RESULT_FAMILIES`
names the three known embedded ones so the limit is at least enumerable.

Binary classification is delegated, never re-derived (L52)
---------------------------------------------------------
A market present in a source with `result == "scalar"` is NOT resolved — it is reported under
`non_binary` so a caller can never score it as a loss. Classification goes through
`core.settlement.is_binary_result` (the existing allow-list), not a local `== "scalar"` test.
A market present with an empty/absent result (Kalshi's `status: "active"` rows in the q51
cache) is likewise NOT resolved: it is *listed*, which is a different claim from *settled*.

Provenance
----------
Every source's rows carry `broker_truth` — a settled result read back from the exchange is
the definition of broker truth. Where the tape line itself carries a `price_source_tag`, the
reader propagates the line's own value rather than the registry's declared default, so a
future source that persists something weaker cannot be silently upgraded here.

Measured composition (L162 — a count ships the command that produced it), 2026-08-07::

    python3 -c "
    from core.settlement_sources import resolve_market_results
    import json
    tk={json.loads(l)['ticker'] for l in open('tape/kalshi_trades/dt=2026-08-03.jsonl')}
    r=resolve_market_results(tk); print(r.coverage_summary())"

Output: ``42 requested / 9 resolved / 0 non-binary / 33 unresolved; hits:
q51_settlement_cache=9`` — i.e. `settlement_ledger` contributes 0 and the whole of the
08-03 coverage comes from the cache family S79's data-gate never looked at.

Pure read-only: no network, no clock, no writes.
"""
from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, Iterator, List, Mapping, Optional, Sequence, Tuple

from core.settlement import is_binary_result, normalize_result

# The tape root every settlement reader defaults to.
#
# ANCHORED TO THE REPO, NOT TO `os.getcwd()` (L345, 2026-08-13). This constant was the bare
# relative string "tape" from the day this module landed (2026-08-09, commit `2a4fb9e`) until
# 2026-08-13. Every caller that omitted `root=`
# therefore resolved it against the PROCESS working directory: run the exact same script from
# any directory other than the repo root and `resolve_market_results` returned a report with
# `n_resolved == 0`, at exit code 0, with no error and no warning — indistinguishable from a
# genuine "the tape does not cover these tickers" data gate. A `verifier` round caught it live
# on `scripts/q52_s78_split_feasibility_audit.py` (`cd /tmp && python3 <abs path>` printed
# "0 resolved" / n_train=0 / n_holdout=0 against the repo-root run's real 34/29).
#
# The fix is here, at the one shared declaration site (L100), rather than at each call site,
# because the L345 candidate enforcement ("make every caller pass an explicit `root=`") does
# NOT close the hole: 7 of the 10 fragile call sites already passed an explicit `root=`.
# `scripts/q54_s79_flow_continuation_probe.py` DOES pass `root=` at both
# of its call sites and was still cwd-fragile, because the value it passes is its own
# parameter defaulting to this constant. Anchoring here also repairs the THREE sealed /
# verdict-bearing probes (`q54_s79_flow_continuation_probe.py`, `q56_s81_funding_regime_
# settlement_probe.py`, `q56_s80_print_vwap_overshoot_maker_fade.py`) without editing a single
# byte of them — L309/L311 forbid touching a sealed probe's logic.
#
# Behaviourally this is a NO-OP for every run made from the repo root (the only way any
# committed result was ever produced): "tape" and "<repo>/tape" name the same directory.
# `scripts/invariants.py::_settlement_root_anchoring_issues` gates on this staying absolute —
# reverting it to a relative literal turns every settlement call site in the repo red.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_TAPE_ROOT = os.path.join(REPO_ROOT, "tape")

# --- source classes -------------------------------------------------------------------
MARKET_RESULT = "market_result"   # answers "did THIS ticker settle yes/no?"
EVENT_VALUE = "event_value"       # answers only "what number did the EVENT print?"

# --- reader kinds ---------------------------------------------------------------------
LEDGER_ROWS = "ledger_rows"                 # one JSONL row per settled market
CACHE_MARKETS_MAP = "cache_markets_map"     # {"markets": {ticker: {...}}} JSON blob
RECORD_RESULTS = "record_results"           # row[field]["results"] = {ticker: result}
EVENT_LIST_RESULTS = "event_list_results"   # row[field]["events"][i]["results"] = {...}


@dataclass(frozen=True)
class SettlementSource:
    """One committed tape surface that can resolve a market outcome.

    `reader_field` is the record key holding the embedded settlement block (RECORD_RESULTS /
    EVENT_LIST_RESULTS kinds only). `declared_tag` is documentation of what the family is
    expected to carry; the reader still prefers the row's OWN `price_source_tag` when present.
    """

    name: str
    path_glob: str
    kind: str
    resolves: str
    declared_tag: str
    note: str
    reader_field: Optional[str] = None


SETTLEMENT_SOURCES: Tuple[SettlementSource, ...] = (
    SettlementSource(
        name="settlement_ledger",
        path_glob="settlement_ledger/dt=*.jsonl",
        kind=LEDGER_ROWS,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="Q45 harvester. Pre-filtered to binary results at collection time "
             "(core/settlement.py docstring). Only two day-files exist (07-17, 07-22).",
    ),
    SettlementSource(
        name="q26_settlement_cache",
        path_glob="q26_settlement_cache/settlement.json",
        kind=CACHE_MARKETS_MAP,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="S22/Q26 probe cache. RAW payload: carries result=='scalar' rows (L52).",
    ),
    SettlementSource(
        name="q27_settlement_cache",
        path_glob="q27_settlement_cache/settlement.json",
        kind=CACHE_MARKETS_MAP,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="S23/Q27 probe cache. RAW payload: carries result=='scalar' rows (L52).",
    ),
    SettlementSource(
        name="q29_settlement_cache",
        path_glob="q29_settlement_cache/settlement.json",
        kind=CACHE_MARKETS_MAP,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="S28/Q29 probe cache. RAW payload: carries result=='scalar' rows (L52).",
    ),
    SettlementSource(
        name="q30_settlement_cache",
        path_glob="q30_settlement_cache/settlement.json",
        kind=CACHE_MARKETS_MAP,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="S29/Q30 probe cache. RAW payload: carries result=='scalar' rows (L52).",
    ),
    SettlementSource(
        name="q51_settlement_cache",
        path_glob="q51_settlement_cache/settlement*.json",
        kind=CACHE_MARKETS_MAP,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="Q51 milestone-2/3 cache — the ONLY family covering the 2026-08-03 "
             "kalshi_trades day. Rows carry `status`; only `finalized` ones have a result.",
    ),
    SettlementSource(
        name="q56_settlement_cache",
        path_glob="q56_settlement_cache/settlement*.json",
        kind=CACHE_MARKETS_MAP,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        note="Q56/S81 settlement backfill (2026-08-11) — public /markets/{ticker} results for "
             "the crypto-hourly bracket legs `crypto_hourly.previous_settlement` never paired "
             "(L327). RAW payload: keeps result=='scalar' and listed-but-unsettled rows (L52). "
             "Written by scripts/q56_s81_settlement_backfill.py under an exhaustive, "
             "outcome-blind selection rule.",
    ),
    SettlementSource(
        name="crypto_hourly",
        path_glob="crypto_hourly/dt=*.jsonl",
        kind=RECORD_RESULTS,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        reader_field="previous_settlement",
        note="EMBEDDED: each capture carries the PRIOR hour's settled ladder. Invisible to "
             "any directory-name scan for 'settlement'.",
    ),
    SettlementSource(
        name="weather_actuals",
        path_glob="weather_actuals/dt=*.jsonl",
        kind=EVENT_LIST_RESULTS,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        reader_field="settled_markets",
        note="EMBEDDED: `settled_markets.events[].results` is a full per-ticker yes/no map.",
    ),
    SettlementSource(
        name="econ_prints",
        path_glob="econ_prints/dt=*.jsonl",
        kind=RECORD_RESULTS,
        resolves=MARKET_RESULT,
        declared_tag="broker_truth",
        reader_field="recent_settlement",
        note="EMBEDDED: `recent_settlement.results` per settled CPI/payrolls/GDP ladder.",
    ),
)

# The three families whose settlement lives INSIDE another family's records. Named so the
# recall limit of `undeclared_settlement_dirs()` is enumerable rather than merely admitted.
EMBEDDED_RESULT_FAMILIES: Tuple[str, ...] = tuple(
    s.name for s in SETTLEMENT_SOURCES if s.kind in (RECORD_RESULTS, EVENT_LIST_RESULTS)
)

UNDECLARED_SCAN_RECALL_NOTE = (
    "undeclared_settlement_dirs() detects only settlement-NAMED directories; a family that "
    "embeds results inside another schema (see EMBEDDED_RESULT_FAMILIES) is undetectable by "
    "name. A 0-issue result is precision evidence, never recall (L155/L189/L300)."
)


@dataclass(frozen=True)
class MarketResult:
    ticker: str
    result: Optional[str]
    source: str
    path: str
    price_source_tag: str


@dataclass(frozen=True)
class ResolutionReport:
    requested: int
    resolved: Dict[str, MarketResult]
    non_binary: Dict[str, MarketResult]
    listed_unsettled: Dict[str, MarketResult]
    unresolved: Tuple[str, ...]
    per_source_hits: Dict[str, int]
    sources_scanned: Tuple[str, ...]
    sources_absent_on_disk: Tuple[str, ...]

    @property
    def n_resolved(self) -> int:
        return len(self.resolved)

    def coverage_summary(self) -> str:
        """One line, safe to paste into a finding or a queue Status note."""
        hits = ", ".join(f"{k}={v}" for k, v in sorted(self.per_source_hits.items()) if v)
        return (f"{self.requested} requested / {len(self.resolved)} resolved / "
                f"{len(self.non_binary)} non-binary / {len(self.unresolved)} unresolved; "
                f"hits: {hits or 'none'}")

    def to_json_obj(self) -> Dict[str, object]:
        return {
            "requested": self.requested,
            "n_resolved": len(self.resolved),
            "n_non_binary": len(self.non_binary),
            "n_listed_unsettled": len(self.listed_unsettled),
            "n_unresolved": len(self.unresolved),
            "per_source_hits": dict(sorted(self.per_source_hits.items())),
            "sources_scanned": list(self.sources_scanned),
            "sources_absent_on_disk": list(self.sources_absent_on_disk),
            "resolved": {t: {"result": m.result, "source": m.source,
                             "price_source_tag": m.price_source_tag}
                         for t, m in sorted(self.resolved.items())},
            "non_binary": {t: {"result": m.result, "source": m.source}
                           for t, m in sorted(self.non_binary.items())},
            "unresolved": list(self.unresolved),
            "recall_note": UNDECLARED_SCAN_RECALL_NOTE,
        }


def _tag(obj: Mapping, default: str) -> str:
    tag = obj.get("price_source_tag") if isinstance(obj, Mapping) else None
    return tag if isinstance(tag, str) and tag else default


def _iter_json_lines(path: str) -> Iterator[Mapping]:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, Mapping):
                yield obj


def _results_map_hits(results: object, wanted: Optional[frozenset], source: str,
                      path: str, tag: str) -> Iterator[MarketResult]:
    if not isinstance(results, Mapping):
        return
    for ticker, result in results.items():
        if not isinstance(ticker, str):
            continue
        if wanted is not None and ticker not in wanted:
            continue
        yield MarketResult(ticker=ticker, result=result if isinstance(result, str) else None,
                           source=source, path=path, price_source_tag=tag)


def iter_source_results(source: SettlementSource, wanted: Optional[Iterable[str]] = None,
                        root: str = DEFAULT_TAPE_ROOT) -> Iterator[MarketResult]:
    """Yield every (ticker, result) this source carries, optionally restricted to `wanted`.

    A ticker may be yielded more than once (repeated captures); callers decide precedence.
    Missing files are simply absent — never an exception, so one uncollected family cannot
    abort a coverage scan of the other eight.
    """
    want = frozenset(wanted) if wanted is not None else None
    for path in sorted(glob.glob(os.path.join(root, source.path_glob))):
        if source.kind == LEDGER_ROWS:
            for row in _iter_json_lines(path):
                ticker = row.get("ticker")
                if not isinstance(ticker, str):
                    continue
                if want is not None and ticker not in want:
                    continue
                yield MarketResult(ticker=ticker,
                                   result=row.get("result") if isinstance(row.get("result"), str) else None,
                                   source=source.name, path=path,
                                   price_source_tag=_tag(row, source.declared_tag))
        elif source.kind == CACHE_MARKETS_MAP:
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    blob = json.load(fh)
            except (ValueError, OSError):
                continue
            if not isinstance(blob, Mapping):
                continue
            tag = _tag(blob, source.declared_tag)
            markets = blob.get("markets")
            if not isinstance(markets, Mapping):
                continue
            for ticker, rec in markets.items():
                if not isinstance(ticker, str):
                    continue
                if want is not None and ticker not in want:
                    continue
                result = rec.get("result") if isinstance(rec, Mapping) else None
                yield MarketResult(ticker=ticker,
                                   result=result if isinstance(result, str) else None,
                                   source=source.name, path=path,
                                   price_source_tag=_tag(rec if isinstance(rec, Mapping) else {}, tag))
        elif source.kind == RECORD_RESULTS:
            for row in _iter_json_lines(path):
                block = row.get(source.reader_field or "")
                if not isinstance(block, Mapping):
                    continue
                yield from _results_map_hits(block.get("results"), want, source.name, path,
                                             _tag(block, source.declared_tag))
        elif source.kind == EVENT_LIST_RESULTS:
            for row in _iter_json_lines(path):
                block = row.get(source.reader_field or "")
                if not isinstance(block, Mapping):
                    continue
                events = block.get("events")
                if not isinstance(events, list):
                    continue
                for ev in events:
                    if not isinstance(ev, Mapping):
                        continue
                    yield from _results_map_hits(ev.get("results"), want, source.name, path,
                                                 _tag(ev, source.declared_tag))
        else:  # pragma: no cover - guarded by test_every_source_kind_is_readable
            raise ValueError(f"unknown reader kind {source.kind!r} for {source.name}")


def source_files_present(source: SettlementSource, root: str = DEFAULT_TAPE_ROOT) -> List[str]:
    return sorted(glob.glob(os.path.join(root, source.path_glob)))


def resolve_market_results(tickers: Iterable[str],
                           root: str = DEFAULT_TAPE_ROOT,
                           sources: Optional[Sequence[SettlementSource]] = None
                           ) -> ResolutionReport:
    """Scan EVERY declared settlement source for outcomes of `tickers`.

    A ticker counts as `resolved` only when some source carries a BINARY result for it
    (`core.settlement.is_binary_result`). `result == "scalar"` lands in `non_binary` (L52);
    a listed-but-not-settled row (empty/absent result, e.g. Kalshi `status: "active"`) lands
    in `listed_unsettled` — listed is not settled, and conflating them is how a coverage
    claim becomes a lie in the other direction.
    """
    srcs = tuple(sources) if sources is not None else SETTLEMENT_SOURCES
    want = frozenset(t for t in tickers if isinstance(t, str))
    resolved: Dict[str, MarketResult] = {}
    non_binary: Dict[str, MarketResult] = {}
    listed: Dict[str, MarketResult] = {}
    hits: Dict[str, int] = {s.name: 0 for s in srcs}
    absent: List[str] = []
    for s in srcs:
        if not source_files_present(s, root):
            absent.append(s.name)
            continue
        for m in iter_source_results(s, want, root):
            if is_binary_result(m.result):
                if m.ticker not in resolved:
                    resolved[m.ticker] = m
                    hits[s.name] += 1
            elif normalize_result(m.result):
                non_binary.setdefault(m.ticker, m)
            else:
                listed.setdefault(m.ticker, m)
    non_binary = {t: m for t, m in non_binary.items() if t not in resolved}
    listed = {t: m for t, m in listed.items() if t not in resolved and t not in non_binary}
    unresolved = tuple(sorted(t for t in want if t not in resolved))
    return ResolutionReport(requested=len(want), resolved=resolved, non_binary=non_binary,
                            listed_unsettled=listed, unresolved=unresolved,
                            per_source_hits=hits,
                            sources_scanned=tuple(s.name for s in srcs),
                            sources_absent_on_disk=tuple(absent))


def declared_source_names() -> Tuple[str, ...]:
    return tuple(s.name for s in SETTLEMENT_SOURCES)


def undeclared_settlement_dirs(root: str = DEFAULT_TAPE_ROOT) -> Tuple[str, ...]:
    """Directories under `root` whose NAME says settlement but which no source declares.

    See `UNDECLARED_SCAN_RECALL_NOTE`: this cannot see an embedded family, by construction.
    """
    declared = set(declared_source_names())
    out: List[str] = []
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return ()
    for name in entries:
        if not os.path.isdir(os.path.join(root, name)):
            continue
        if "settlement" not in name.lower():
            continue
        if name not in declared:
            out.append(name)
    return tuple(out)

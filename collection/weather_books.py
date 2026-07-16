"""collection.weather_books — forward full-depth orderbook capture for Kalshi WEATHER
markets (READ-ONLY). The weather L2 tape the revival dossier says is gone.

Weather tape collection stopped 2026-07-03 when the VPS weather stack was torn down; nothing
collects weather today (findings/2026-07-15-weather-revival-dossier.md §5). Every edge
candidate in that dossier (summer maker re-test W-A, the KXTEMPNYCH hourly nowcast W-B, the
daily late-session convergence W-C) is blocked on one thing: a fresh forward L2 tape. Kalshi
does NOT archive orderbook history, so (lesson L11) an un-collected snapshot is lost forever —
this collector starts accumulating that history now.

It captures two market GROUPS discovered fresh each pass:

  DAILY temperature ladders — the high/low series for the 20 cities in config/cities.yaml
  (KXHIGH*/KXLOWT*, incl. the newer KXHIGHT* prefix, e.g. KXHIGHTBOS/KXHIGHTDAL/KXHIGHTSEA/
  KXHIGHTMIN). Discovery is a UNION of (a) the series tickers named in config/cities.yaml and
  (b) a live "Climate and Weather" category sweep filtered to daily temperature series
  (reusing validation.v3_market._classify, which already excludes hourly/directional/monthly/
  global/US/range titles). The sweep is what keeps a NEW city/series from silently dropping —
  the pass logs config-only, sweep-only, and the captured union so the gap is always visible.

  HOURLY directional series — KXTEMPNYCH (Hourly Directional NYC Temperature, settles on The
  Weather Company value for coordinates KNYC; markets open ~1-2h windows with sub-degree
  thresholds like T80.99). Discovered via the same category sweep filtered to hourly-
  directional-temperature titles (KXTEMPNYCH plus its siblings KXTEMPMIAH/KXTEMPCHIH/...,
  and KXHIGHNYD), with KXTEMPNYCH always seeded so it can never drop. ALL open markets in each
  hourly series are captured.

Orderbook shape (verified live 2026-07-15): GET /markets/{ticker}/orderbook now returns an
`orderbook_fp` object with `yes_dollars`/`no_dollars` arrays of [price_string, dollars_string].
`_extract_snapshot` also handles the LEGACY integer-cents `orderbook` shape ({"yes"/"no":
[[cents, size], ...]}) so a venue rollback can't silently zero the capture. Kalshi books are
bids-only per side; the tradeable ask on one side is the complement of the other side's best
bid — that arithmetic lives once, in collection/normalize.normalize_snapshot (shared with
capture_orderbooks.py / orderbook_depth.py; reused, not reinvented).

Source tags (CLAUDE.md trust-default + Hard Rules #3/#4): a LIVE order-book read is a genuine
fillable quote, not a model, so each line tags `price_source_tag="real_ask"` (the task's
literal requirement for real book levels) and, granularly, `price_source_tags={"asks":
"real_ask","bids":"real_bid"}` — the same convention orderbook_depth.py established (a resting
bid is a distinct, equally-real fillable side; `real_bid` is deliberately outside the canonical
DB enum, see lesson L24).

The public /markets endpoint no longer returns yes_bid/volume unauthenticated (they come back
null, confirmed live 2026-07-15) — this collector NEVER reads those fields; the orderbook
endpoint is the single source of book truth.

Honest completeness (same discipline as every collection/ module): the open markets discovered
across both groups are the EXPECTED set; a per-market orderbook fetch that raises is a DROP
(recorded, never absorbed), lowering `n_captured` below `n_expected` so `completeness_ok` goes
False. A whole-series enumeration failure is a `series_error` (its markets become invisible, an
honest gap, also lowers completeness). A config series that returns ZERO open markets is NOT a
failure — off-season / renamed / no-market-yet is normal venue structure and must not gate
completeness (only exceptions do). An empty orderbook (no bids either side) is valid data
(lesson L23: empty != drop), captured with depth 0. `max_markets` caps the per-pass fetch
budget (lesson L10: Kalshi's 10k+ universe once blew 3GB RSS) and carries an honest `truncated`
flag; the weather universe is ~50 series so the cap is defensive, not expected to bite.

Market metadata (settlement source + rules) is persisted ONCE per (series, day) into a sibling
`tape/weather_books/meta/dt=<day>.jsonl`, deduped by reading the day's already-written series
keys (append-only, never rewritten). Cheap now, priceless later: the W-B settlement-basis study
needs to know KXTEMPNYCH settles on The Weather Company for KNYC, and daily highs on the NWS
Climatological Report — recorded verbatim from the series' own settlement_sources + a sample
market's rules_primary/rules_secondary, never guessed.

HONEST CADENCE CAVEAT (same as orderbook_depth.py): the recurring collector runs HOURLY. Hourly
snapshots are coarse for the sub-degree, minutes-matter W-B latency play and the W-C late-session
convergence window — those need the finer (<=5 min) VPS cadence the dossier calls for. This
collector gives the strategies a repeated-snapshot depth time-series (resting-liquidity shape and
its hour-over-hour drift), NOT a continuous order-flow tape (and, per lesson L68, it carries no
trade/volume prints — a maker toxicity study needs a separate trade tape).

Run one pass:
    python -m collection.weather_books
    python -m collection.weather_books --limit 40   # cap markets per pass (offline/dev use)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from collection.normalize import normalize_snapshot
from core.canonical import canonical_json, sha256_hex
from core.io import CONFIG, REPO_ROOT
from validation.v3_market import (WEATHER_CATEGORY, Kalshi, _classify, _load_venue_cfg)

TAPE = REPO_ROOT / "tape" / "weather_books"
ORDERBOOK_PATH = "/markets/{ticker}/orderbook"

# KXTEMPNYCH is the dossier's W-B target; seed it so a title-filter miss can never drop it.
HOURLY_SEED_SERIES: Tuple[str, ...] = ("KXTEMPNYCH",)

# Per-pass fetch-budget cap (lesson L10). The weather universe is ~50 series / a few hundred
# markets, well under this; the cap is defensive and flags honestly if it ever bites.
MAX_MARKETS_DEFAULT = 2000

# An hourly-directional-temperature series (KXTEMPNYCH, KXTEMPMIAH, ..., KXHIGHNYD): its title
# carries all three tokens. Kept as three independent word-boundary checks so a re-worded title
# still matches on intent rather than an exact string.
_HOURLY_TITLE = (re.compile(r"hourly", re.I), re.compile(r"directional", re.I),
                 re.compile(r"temp", re.I))


def _is_hourly_directional(series: Dict[str, Any]) -> bool:
    title = series.get("title") or ""
    return all(rx.search(title) for rx in _HOURLY_TITLE)


# --------------------------------------------------------------------------- #
# config series (the seed set — a city must never silently drop)
# --------------------------------------------------------------------------- #
def _config_daily_series(config_path: Optional[Path] = None) -> List[str]:
    """Every high_series + low_series ticker named in config/cities.yaml, deduped, sorted."""
    path = Path(config_path) if config_path is not None else (CONFIG / "cities.yaml")
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: set = set()
    for c in doc.get("cities") or []:
        k = c.get("kalshi") or {}
        for key in ("high_series", "low_series"):
            for s in (k.get(key) or []):
                if s:
                    out.add(s)
    return sorted(out)


# --------------------------------------------------------------------------- #
# discovery — the EXPECTED open-market set, grouped daily/hourly, with honest accounting
# --------------------------------------------------------------------------- #
def discover(client: Kalshi, config_path: Optional[Path] = None
             ) -> Tuple[Dict[str, List[Tuple[str, Dict]]], Dict[str, Any], List[Dict[str, str]]]:
    """Enumerate open weather markets in two groups.

    Returns (by_group, report, series_errors):
      by_group["daily"|"hourly"] = [(series_ticker, market_dict), ...] for every OPEN market.
      report                     = discovery accounting (config vs sweep vs union, per group).
      series_errors              = [{series, group, error}] for enumeration exceptions
                                   (a whole series invisible this pass — an honest gap).
    """
    config_daily = _config_daily_series(config_path)

    # live category sweep — the "don't silently drop a new city/series" leg
    try:
        catalog = client.series_by_category(WEATHER_CATEGORY)
    except Exception as exc:
        catalog = []
        series_errors_catalog = [{"series": "<category-sweep>", "group": "catalog",
                                  "error": str(exc)}]
    else:
        series_errors_catalog = []

    sweep_daily = sorted({s.get("ticker", "") for s in catalog
                          if _classify(s)} - {""})
    sweep_hourly = sorted({s.get("ticker", "") for s in catalog
                           if _is_hourly_directional(s)} - {""})

    daily_series = sorted(set(config_daily) | set(sweep_daily))
    hourly_series = sorted(set(sweep_hourly) | set(HOURLY_SEED_SERIES))

    report = {
        "config_daily_series": config_daily,
        "sweep_daily_series": sweep_daily,
        "daily_series_captured": daily_series,
        "config_only_daily": sorted(set(config_daily) - set(sweep_daily)),
        "sweep_only_daily": sorted(set(sweep_daily) - set(config_daily)),
        "hourly_series_captured": hourly_series,
        "n_catalog_series": len(catalog),
    }

    by_group: Dict[str, List[Tuple[str, Dict]]] = {"daily": [], "hourly": []}
    series_errors: List[Dict[str, str]] = list(series_errors_catalog)
    per_series_open: Dict[str, int] = {}

    for group, series_list in (("daily", daily_series), ("hourly", hourly_series)):
        for sticker in series_list:
            try:
                markets = client.open_markets(sticker)
            except Exception as exc:   # whole-series enumeration failure -> recorded, not hidden
                series_errors.append({"series": sticker, "group": group, "error": str(exc)})
                continue
            per_series_open[sticker] = len(markets or [])
            for m in (markets or []):
                if m.get("ticker"):
                    by_group[group].append((sticker, m))

    report["per_series_open_count"] = per_series_open
    return by_group, report, series_errors


# --------------------------------------------------------------------------- #
# orderbook extraction — both the modern orderbook_fp and legacy integer-cents shapes
# --------------------------------------------------------------------------- #
def _extract_snapshot(ticker: str, payload: Dict[str, Any]
                      ) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Return (snapshot, raw_book, book_shape) for a raw orderbook payload.

    Handles BOTH shapes so a venue rollback can't silently zero the capture:
      * modern  {"orderbook_fp": {"yes_dollars": [[p_str, sz_str], ...], "no_dollars": [...]}}
      * legacy  {"orderbook":    {"yes": [[cents_int, sz], ...], "no": [...]}}
    normalize_snapshot owns the bid->opposite-ask complement; we only pick the shape and,
    for the legacy shape, convert integer cents to the dollar strings normalize expects."""
    fp = payload.get("orderbook_fp")
    if fp is not None:
        return normalize_snapshot(ticker, fp or {}), (fp or {}), "orderbook_fp"

    legacy = payload.get("orderbook")
    if legacy is not None:
        conv = {
            "yes_dollars": [[str(float(p) / 100.0), str(sz)] for p, sz in (legacy.get("yes") or [])],
            "no_dollars": [[str(float(p) / 100.0), str(sz)] for p, sz in (legacy.get("no") or [])],
        }
        return normalize_snapshot(ticker, conv), (legacy or {}), "orderbook_legacy"

    return normalize_snapshot(ticker, {}), {}, "empty"


def _book_record(group: str, series: str, market: Dict[str, Any], payload: Dict[str, Any],
                 capture_id: str, captured_at: str, raw_sha256: str) -> Dict[str, Any]:
    ticker = market.get("ticker", "")
    snap, raw_book, book_shape = _extract_snapshot(ticker, payload)
    return {
        "schema_version": "weather_books.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "group": group,
        "series": series,
        "ticker": ticker,
        "close_time": market.get("close_time"),
        # ladder identity — from the market dict already in hand (no extra GET). NOT yes_bid/
        # volume (those are null unauthenticated); the orderbook is the source of book truth.
        "strike_type": market.get("strike_type"),
        "floor_strike": market.get("floor_strike"),
        "cap_strike": market.get("cap_strike"),
        "yes_sub_title": market.get("yes_sub_title"),
        # raw book verbatim (provenance in-line) + its byte hash
        "raw_orderbook": raw_book,
        "book_shape": book_shape,
        # full L2 ladders, best-first (normalize_snapshot's ordering) — [[price, size], ...]
        "yes_bids": snap["yes_bids"],
        "no_bids": snap["no_bids"],
        "best_yes_bid": snap["best_yes_bid"],
        "best_no_bid": snap["best_no_bid"],
        "best_yes_ask": snap["best_yes_ask"],
        "best_no_ask": snap["best_no_ask"],
        "depth": snap["depth"],
        # a live book read is a real fillable quote, not a model (CLAUDE.md Hard Rules #3/#4)
        "price_source_tag": "real_ask",
        "price_source_tags": {"asks": "real_ask", "bids": "real_bid"},
        "raw_sha256": raw_sha256,
    }


# --------------------------------------------------------------------------- #
# per-(series, day) metadata — settlement source + rules, written once, deduped by day
# --------------------------------------------------------------------------- #
def _existing_meta_series(meta_path: Path) -> set:
    """Series tickers already recorded in today's meta file (append-only dedup)."""
    if not meta_path.exists():
        return set()
    seen: set = set()
    with open(meta_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                seen.add(json.loads(line).get("series"))
            except Exception:
                continue
    return seen


def _meta_record(client: Kalshi, group: str, series: str, sample_market: Dict[str, Any],
                 capture_id: str, captured_at: str) -> Dict[str, Any]:
    """Settlement source + rules for a series, once per day. settlement_sources/fee/frequency
    come from the series detail (Kalshi's own spec); rules_primary/secondary from a sample open
    market. A detail fetch failure degrades to nulls with an error note, never fabricates."""
    detail: Dict[str, Any] = {}
    detail_error: Optional[str] = None
    try:
        detail = client.series_detail(series) or {}
    except Exception as exc:
        detail_error = str(exc)
    return {
        "schema_version": "weather_series_meta.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "group": group,
        "series": series,
        "title": detail.get("title"),
        "settlement_sources": detail.get("settlement_sources"),
        "fee_type": detail.get("fee_type"),
        "fee_multiplier": detail.get("fee_multiplier"),
        "frequency": detail.get("frequency"),
        "contract_url": detail.get("contract_url"),
        # rules live on the market, not the series (verified live 2026-07-15)
        "rules_primary": sample_market.get("rules_primary"),
        "rules_secondary": sample_market.get("rules_secondary"),
        "sample_ticker": sample_market.get("ticker"),
        "detail_error": detail_error,
    }


# --------------------------------------------------------------------------- #
# capture — one JSONL line per open market per pass
# --------------------------------------------------------------------------- #
def run(min_interval: float = 0.2, client: Optional[Kalshi] = None,
        store: Optional[Path] = None, config_path: Optional[Path] = None,
        max_markets: int = MAX_MARKETS_DEFAULT, limit: Optional[int] = None) -> Dict[str, Any]:
    """One read-only weather-book capture pass over both groups.

    `client`/`store`/`config_path` are injectable for offline testing. `limit` caps markets per
    pass (dev use); `max_markets` is the defensive memory cap (lesson L10). Returns a summary
    dict (n_expected/n_captured/n_lines/completeness_ok/truncated/dropped/series_errors/
    discovery/path/meta_path) — hourly_pass reads n_captured + completeness_ok.
    """
    store = Path(store) if store is not None else TAPE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    by_group, report, series_errors = discover(client, config_path=config_path)

    # flatten to the ordered expected set: [(group, series, market), ...]
    expected: List[Tuple[str, str, Dict]] = []
    for group in ("daily", "hourly"):
        for series, market in by_group[group]:
            expected.append((group, series, market))

    effective_cap = min(max_markets, limit) if limit is not None else max_markets
    truncated = len(expected) > effective_cap
    if truncated:
        expected = expected[:effective_cap]

    lines: List[str] = []
    captured: List[str] = []
    dropped: List[str] = []
    shapes: Dict[str, int] = {}
    # first open market seen per (group, series) — the sample the meta record's rules come from
    first_market: Dict[Tuple[str, str], Dict] = {}

    for group, series, market in expected:
        ticker = market.get("ticker", "")
        first_market.setdefault((group, series), market)
        try:
            text = client.get_text(ORDERBOOK_PATH.format(ticker=ticker))
        except Exception:            # a failed fetch is a DROP -> lowers completeness, never hidden
            dropped.append(ticker)
            continue
        payload = json.loads(text) if text else {}
        raw_sha256 = sha256_hex((text or "").encode("utf-8"))
        record = _book_record(group, series, market, payload or {}, capture_id, captured_at,
                              raw_sha256)
        shapes[record["book_shape"]] = shapes.get(record["book_shape"], 0) + 1
        captured.append(ticker)
        lines.append(canonical_json(record))

    completeness_ok = (
        len(captured) == len(expected)
        and not truncated
        and not series_errors)

    path: Optional[str] = None
    meta_path_str: Optional[str] = None
    n_meta_written = 0
    if lines:
        store.mkdir(parents=True, exist_ok=True)
        out_path = store / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        path = str(out_path)

        # metadata once per (series, day) — sibling meta/ dir, deduped against the day's file
        meta_dir = store / "meta"
        meta_dir.mkdir(parents=True, exist_ok=True)
        meta_path = meta_dir / f"dt={day}.jsonl"
        already = _existing_meta_series(meta_path)
        new_meta: List[str] = []
        for (group, series), sample in sorted(first_market.items()):
            if series in already:
                continue
            already.add(series)
            new_meta.append(canonical_json(
                _meta_record(client, group, series, sample, capture_id, captured_at)))
        if new_meta:
            with open(meta_path, "a", encoding="utf-8") as f:
                for ln in new_meta:
                    f.write(ln + "\n")
        n_meta_written = len(new_meta)
        meta_path_str = str(meta_path)

    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_series_daily": len(report["daily_series_captured"]),
        "n_series_hourly": len(report["hourly_series_captured"]),
        "n_expected": len(expected), "n_captured": len(captured), "n_lines": len(lines),
        "n_dropped": len(dropped), "dropped": dropped,
        "n_series_errors": len(series_errors), "series_errors": series_errors,
        "n_meta_written": n_meta_written,
        "book_shapes": shapes,
        "truncated": truncated,
        "completeness_ok": completeness_ok,
        "discovery": report,
        "path": path, "meta_path": meta_path_str,
    }
    print(f"[weather_books] {capture_id}: {len(captured)}/{len(expected)} books "
          f"(daily {summary['n_series_daily']} series, hourly {summary['n_series_hourly']} series), "
          f"{len(dropped)} dropped, {len(series_errors)} series-errors, "
          f"{n_meta_written} meta, shapes={shapes}, "
          f"completeness {'ok' if completeness_ok else 'FAIL'}"
          + (" (TRUNCATED)" if truncated else ""))
    if report["sweep_only_daily"]:
        print(f"[weather_books] NOTE {len(report['sweep_only_daily'])} daily series in the live "
              f"sweep were NOT in config/cities.yaml (captured anyway): "
              f"{report['sweep_only_daily']}")
    if dropped:
        print(f"[weather_books] WARN dropped {len(dropped)} ticker(s) -> completeness_ok=False",
              file=sys.stderr)
    if series_errors:
        print(f"[weather_books] WARN {len(series_errors)} series failed enumeration "
              f"-> completeness_ok=False", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Weather full-depth orderbook capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap markets per pass (dev use)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    ap.add_argument("--max-markets", type=int, default=MAX_MARKETS_DEFAULT)
    args = ap.parse_args(argv)
    run(min_interval=args.min_interval, max_markets=args.max_markets, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(main())

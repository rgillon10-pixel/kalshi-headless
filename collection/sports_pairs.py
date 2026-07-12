"""Sports moneyline paired-odds collector (READ-ONLY) — Kalshi BBO + de-vigged sharp odds.

LOOP-QUEUE.md Q1: serves S7 (sports CLV harvest) and S11 (sharp-anchored maker quoting).
Mirrors `collection/capture_orderbooks.py` discipline: bitemporal `captured_at`, raw-bytes
sha256 provenance, honest expected-vs-captured completeness (a fetch failure lowers
`completeness_ok`, it never silently drops a game).

Discovery: Kalshi has no "moneyline" category flag, so candidate series are found by a
title heuristic (`*Game(s)*`, minus known prop-bet keywords), then EVERY candidate group is
confirmed structurally (2-3 outcomes, every market titled "<A> vs <B> ... Winner?") before
capture — the heuristic only narrows the API-call budget, it never decides what gets
persisted. Soccer/World Cup is the first live target (Kalshi's `KXWCGAME` series) but the
same discovery + capture path picks up any other sport listed the same way (Hard Rule
discipline: no venue-specific special-casing beyond the shared ticker grammar).

Each open game is one outcome-group: Kalshi already prices it as a coherent bracket (the
per-outcome `yes_ask_dollars` sum to a bracket_sum > 1.0, the same overround structure as
the weather ladders — core/pricing.py is the one sanctioned site for that arithmetic, so
Hard Rule #3 applies here unchanged).

The odds-api leg (matched sportsbook moneylines, de-vigged to a fair probability) lives in
`collection/odds_api.py` and requires `ODDS_API_KEY`; absent that, the Kalshi leg is still
captured and the game's `odds_leg` is recorded as `{"status": "blocked_key"}` (Q1 spec)
rather than silently omitted. With a key present the enrichment self-activates: game start
(`occurrence_datetime`) + per-outcome team name (`yes_sub_title`) — persisted on every v2
record either way — anchor the match to the odds-api event, and the paired sharp line is
de-vigged to a fair prob tagged `synthetic` (a de-vig is a model, not a fill).

Run one pass:
    python -m collection.sports_pairs
    python -m collection.sports_pairs --limit 3    # cap candidate series (offline/dev use)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from collection import odds_api
from collection.odds_api import devig_multiplicative  # noqa: F401 — sanctioned de-vig site
from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from core.pricing import bracket_sum, overround
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "sports_pairs"
SPORTS_CATEGORY = "Sports"

# SERIES-EVENTCODE-OUTCOME, e.g. KXWCGAME-26JUL06USABEL-USA. EVENTCODE is a YYMonDD date
# token immediately followed by concatenated team codes (empirically observed on
# KXWCGAME/KXNFLGAME/KXMLBGAME/... — the same grammar family as validation/v3_market.py's
# weather TICKER_RE, just without the T/B strike suffix).
TICKER_RE = re.compile(
    r"^(?P<series>[A-Z0-9]+)-(?P<event>(?P<yy>\d{2})(?P<mon>[A-Z]{3})(?P<dd>\d{2})"
    r"(?P<teams>[A-Z0-9]+))-(?P<outcome>[A-Z0-9]+)$"
)

# A confirmed moneyline market title: "<A> vs[.] <B> ... Winner?" (Kalshi's own title
# grammar for every game-winner market observed).
_MONEYLINE_TITLE_RE = re.compile(r"\bvs\.?\b.+\bwinner\??\s*$", re.I)

# Series-title heuristic: candidates end up here only to narrow the API-call budget over
# ~2300 Sports series; every candidate is re-confirmed per-game by is_moneyline_group().
_SERIES_TITLE_RE = re.compile(r"\bgames?\b", re.I)
_EXCLUDE_SERIES_RE = re.compile(
    r"goal|score|corner|shot|total|spread|method|first|hat.?trick|save|assist|award|"
    r"penalt|record|delay|location|start|matchup|leader|streak|combo|celebrity|"
    r"pro.?bowl|all.?star|3.?pointer|played|round|series|parlay|comeback|mvp", re.I)


def parse_sports_ticker(ticker: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Parse SERIES-EVENTCODE-OUTCOME. Returns (fields, error); error is None on success."""
    m = TICKER_RE.match(ticker.upper())
    if not m:
        return None, "no_regex_match"
    try:
        game_date = datetime.strptime(f"{m['yy']}{m['mon']}{m['dd']}", "%y%b%d").date()
    except ValueError:
        return None, f"bad_date_token:{m['yy']}{m['mon']}{m['dd']}"
    return {
        "series": m["series"], "event": m["event"], "game_date": game_date.isoformat(),
        "teams_code": m["teams"], "outcome": m["outcome"],
    }, None


# --------------------------------------------------------------------------- #
# discovery
# --------------------------------------------------------------------------- #
def discover_moneyline_series(client: Kalshi) -> List[str]:
    """Sports-category series whose title marks them a candidate game-level moneyline."""
    out = []
    for s in client.series_by_category(SPORTS_CATEGORY):
        title = s.get("title") or ""
        if _SERIES_TITLE_RE.search(title) and not _EXCLUDE_SERIES_RE.search(title):
            ticker = s.get("ticker", "")
            if ticker:
                out.append(ticker)
    return sorted(out)


def is_moneyline_group(markets: List[Dict]) -> bool:
    """A real moneyline game group: 2-3 mutually exclusive outcomes, every market titled
    '<A> vs <B> ... Winner?'. The structural confirmation the series-title heuristic needs."""
    if not (2 <= len(markets) <= 3):
        return False
    return all(_MONEYLINE_TITLE_RE.search(m.get("title") or "") for m in markets)


def _fetch_open_markets_raw(client: Kalshi, series_ticker: str) -> Tuple[List[Dict], List[str]]:
    """Manually paginate /markets for one series, keeping the verbatim raw page bytes
    alongside the parsed list (raw-bytes provenance, same discipline as capture_orderbooks)."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"series_ticker": series_ticker, "status": "open", "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        text = client.get_text("/markets", **params)
        raw_pages.append(text)
        j = json.loads(text)
        items = j.get("markets") or []
        markets.extend(items)
        cursor = j.get("cursor")
        if not cursor or not items:
            break
    return markets, raw_pages


def discover_groups(client: Kalshi, series_list: List[str]
                    ) -> Tuple[Dict[str, Dict], Dict[str, List[str]], List[Dict[str, str]]]:
    """Fetch open markets for each candidate series, group by event_ticker, keep only
    confirmed moneyline groups. Returns (groups, raw_pages_by_series, series_errors)."""
    groups: Dict[str, Dict] = {}
    raw_pages_by_series: Dict[str, List[str]] = {}
    series_errors: List[Dict[str, str]] = []
    for sticker in series_list:
        try:
            markets, raw_pages = _fetch_open_markets_raw(client, sticker)
        except Exception as exc:
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        raw_pages_by_series[sticker] = raw_pages
        by_event: Dict[str, List[Dict]] = {}
        for m in markets:
            by_event.setdefault(m.get("event_ticker", ""), []).append(m)
        for event_ticker, group_markets in by_event.items():
            if event_ticker and is_moneyline_group(group_markets):
                groups[event_ticker] = {"series": sticker, "markets": group_markets}
    return groups, raw_pages_by_series, series_errors


# --------------------------------------------------------------------------- #
# capture — one JSONL line per confirmed moneyline game
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, tape_dir: Optional[Path] = None,
        odds_api_key: Optional[str] = None,
        odds_http_get: Optional[Callable] = None) -> Dict:
    """One read-only capture pass. `client`/`tape_dir`/`odds_http_get` injectable for
    offline testing. The odds enrichment runs strictly AFTER the Kalshi leg is built —
    an odds-side failure can never cost a Kalshi capture."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    series_list = discover_moneyline_series(client)
    if limit:
        series_list = series_list[:limit]
    groups, raw_pages_by_series, series_errors = discover_groups(client, series_list)

    records: List[Dict] = []
    for event_ticker in sorted(groups):
        g = groups[event_ticker]
        markets = sorted(g["markets"], key=lambda m: m.get("ticker", ""))
        expected = len(markets)

        outcomes: List[Dict] = []
        yes_asks: List[float] = []
        for m in markets:
            ticker = m.get("ticker", "")
            fields, err = parse_sports_ticker(ticker)
            yes_ask_dollars = m.get("yes_ask_dollars")
            if yes_ask_dollars is None:
                continue   # no live ask -> dropped from this outcome, lowers completeness below
            ya = float(yes_ask_dollars)
            yes_asks.append(ya)
            outcomes.append({
                "ticker": ticker,
                "outcome_code": (fields or {}).get("outcome", ""),
                "outcome_name": odds_api.parse_outcome_name(m.get("yes_sub_title")),
                "ticker_parse_error": err,
                "title": m.get("title", ""),
                "yes_ask": ya,
                "yes_bid": float(m["yes_bid_dollars"]) if m.get("yes_bid_dollars") is not None else None,
                "no_ask": float(m["no_ask_dollars"]) if m.get("no_ask_dollars") is not None else None,
                "no_bid": float(m["no_bid_dollars"]) if m.get("no_bid_dollars") is not None else None,
                "price_source_tag": "real_ask",
            })

        captured = len(outcomes)
        member_count = captured
        bsum = bracket_sum(yes_asks) if yes_asks else None
        records.append({
            "schema_version": "sports_pairs.v2",
            "capture_id": capture_id,
            "captured_at": captured_at,
            "venue": "kalshi",
            "series": g["series"],
            "event_ticker": event_ticker,
            "game_date": (parse_sports_ticker(markets[0]["ticker"])[0] or {}).get("game_date"),
            "game_start": markets[0].get("occurrence_datetime"),
            "game_title": markets[0].get("title", ""),
            "outcomes": outcomes,
            "expected_outcomes": expected,
            "captured_outcomes": captured,
            "member_count": member_count,
            "completeness_ok": captured == expected,
            "bracket_sum": bsum,
            "overround_absorbed": overround(yes_asks) if yes_asks else None,
            "price_source_tag": "real_ask",
            "odds_leg": {"status": "blocked_key"},
        })

    odds_summary: Optional[Dict] = None
    if odds_api_key and records:
        odds_summary = odds_api.enrich_records(records, odds_api_key,
                                               http_get=odds_http_get)

    n_complete = sum(1 for rec in records if rec["completeness_ok"])
    raw_index = sorted(
        [sticker, sha256_hex("".join(pages).encode("utf-8"))]
        for sticker, pages in raw_pages_by_series.items()
    )
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_candidate_series": len(series_list),
        "n_games": len(records), "n_complete": n_complete,
        "n_series_errors": len(series_errors),
        "raw_sha256": sha256_hex(canonical_json(raw_index)),
        "odds_api_key_present": bool(odds_api_key),
        "odds": odds_summary,
    }

    if records:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for rec in records:
                f.write(canonical_json(rec) + "\n")
        summary["path"] = str(out_path)

    odds_note = "ABSENT (blocked_key)"
    if odds_api_key:
        odds_note = "present"
        if odds_summary:
            odds_note += (f" ({odds_summary['n_matched']} matched, "
                          f"quota_remaining={odds_summary['quota_remaining']})")
    print(f"[sports_pairs] {capture_id}: {summary['n_candidate_series']} candidate series, "
          f"{summary['n_games']} moneyline games, {n_complete} complete, "
          f"odds_api_key={odds_note}")
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed enumeration",
              file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    import os
    ap = argparse.ArgumentParser(description="Sports moneyline paired-odds capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap candidate series per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval,
        odds_api_key=os.environ.get("ODDS_API_KEY"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

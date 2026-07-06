"""Cross-venue paired-quotes collector (READ-ONLY) — Kalshi vs Polymarket World Cup
"team to reach round" markets.

LOOP-QUEUE.md Q8 (new, 2026-07-04): first data cut for S9 (Kalshi<->Polymarket
same-question lead-lag). Mirrors `collection/sports_pairs.py` discipline: bitemporal
`captured_at`, raw-bytes sha256 provenance on the Kalshi leg, honest match/no-match/
ambiguous accounting (a missing pair is recorded, never silently dropped).

Why this pair, structurally (no venue-specific ID hardcoding): Kalshi's `KXWCROUND`
series ("Will <team> qualify for FIFA World Cup <round>?") and Polymarket's "World Cup:
Nation To Reach <round>" events are the SAME question shape on both venues — one binary
Yes/No market per (round, team), no de-vig needed (unlike S7's moneyline vs sportsbook
odds), because both sides are already a single fillable Yes/No price. Round events are
found via Polymarket's public-search endpoint (a keyword narrows the API-call budget,
same role `_SERIES_TITLE_RE` plays in sports_pairs.py) and then structurally confirmed by
title regex before anything is trusted; (round, team) pairs that don't line up 1:1 are
left `unmatched`/`ambiguous`, never guessed.

Polymarket prices come off the real CLOB order book (`clob.polymarket.com/book`) — best
bid/ask off a live book, tagged `real_ask` (a real, fillable price) same as the Kalshi
leg, NOT `outcomePrices` from the gamma market list (that field is a last/mid reference,
not a book — never treated as fillable here).

LOOP-QUEUE.md Q12 (2026-07-06): second discovery family, `run_fed_decision()`, retargets
the same matching discipline at Fed rate-decision meetings so cross-venue collection
outlives the World Cup (serves S17). Kalshi's `KXFEDDECISION-<yymon>-<H|C><bps>` markets
("Will the Federal Reserve Hike/Cut rates by <0|25|>25>bps at their <Month> <Year>
meeting?") and Polymarket's "Fed Decision in <Month>?" events ("Will the Fed
increase/decrease interest rates by <N> bps after the <Month> <Year> meeting?", plus a
"No change" bucket) are the same 5-bucket partition on both venues for a given meeting —
matched by (meeting month+year, bucket), confirmed via each side's own title/question text
(never the Kalshi ticker's bps suffix alone, which uses "26" as a stand-in for ">25" —
same "don't trust the ticker suffix alone" lesson the Q1 reconciliation note already
carries). Multi-month bundle events (e.g. "Fed decisions (Jul-Oct)") and off-topic hits
(e.g. the FOMC dissent-count market) are a different shape and are structurally excluded,
not guessed at. Written to a separate tape family (`tape/polymarket_macro_pairs/`) since
it's a distinct market shape from the WC-round pairs above. CPI/inflation matching is
explicitly OUT of scope here: Kalshi's CPI ladder prices a cumulative ">= threshold T"
(see `collection/econ_prints.py`) while Polymarket prices an exact bucket — pairing those
would require a derived/synthetic transform (differencing adjacent Kalshi thresholds),
not a same-question real_ask pair, so it's left for a follow-up rather than faked here.

Run one pass:
    python -m collection.polymarket_pairs
    python -c "from collection import polymarket_pairs as p; print(p.run_fed_decision())"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT
from validation.v3_market import Kalshi, _load_venue_cfg

TAPE = REPO_ROOT / "tape" / "polymarket_pairs"

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
_UA = {"User-Agent": "kalshi-headless/0.0 (research)"}

KALSHI_ROUND_SERIES = "KXWCROUND"

# KXWCROUND-<round_raw>-<team_code>, round_raw = 2-digit year token + round abbreviation,
# e.g. KXWCROUND-26QUAR-USA, KXWCROUND-26SEMI-SUI, KXWCROUND-26FINAL-FRA (empirically
# observed live 2026-07-04 — the same SERIES-EVENT-OUTCOME grammar family as sports_pairs).
_KALSHI_TICKER_RE = re.compile(r"^(?P<series>[A-Z0-9]+)-(?P<round_raw>\d{2}[A-Z]+)-(?P<team_code>[A-Z]+)$")
_KALSHI_TITLE_RE = re.compile(r"^Will (?P<team>.+?) qualify for FIFA World Cup (?P<round>\w+)\??$", re.I)
_ROUND_TOKEN_ALIASES = {"QUAR": "quarterfinals", "SEMI": "semifinals", "FINAL": "final"}

# Search queries only narrow which events public-search returns; every hit is
# re-confirmed structurally by _PM_EVENT_TITLE_RE / _PM_ROUND_RE before being trusted.
PM_SEARCH_QUERIES: Tuple[str, ...] = (
    "World Cup Nation to Reach Quarterfinals",
    "World Cup Nation to Reach Semifinals",
    "World Cup Nation to Reach Final",
)
_PM_EVENT_TITLE_RE = re.compile(r"world cup.*reach", re.I)
_PM_ROUND_RE = re.compile(r"reach\s+(?P<round>quarterfinals|semifinals|final)\b", re.I)


def _normalize_team(name: str) -> str:
    """Lowercase, alnum-only fold — good enough while both venues spell team names the
    same common-English way (confirmed live 2026-07-04: 'USA', 'Switzerland', ... match
    verbatim on both sides for every currently-open KXWCROUND team)."""
    return re.sub(r"[^a-z0-9]+", "", (name or "").strip().lower())


# --------------------------------------------------------------------------- #
# Kalshi leg
# --------------------------------------------------------------------------- #
def parse_kalshi_round_ticker(ticker: str) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """Parse SERIES-ROUNDRAW-TEAMCODE. Returns (fields, error); error is None on success."""
    m = _KALSHI_TICKER_RE.match(ticker.upper())
    if not m:
        return None, "no_regex_match"
    round_token = re.sub(r"^\d+", "", m["round_raw"])
    round_name = _ROUND_TOKEN_ALIASES.get(round_token)
    if round_name is None:
        return None, f"unknown_round_token:{round_token}"
    return {"series": m["series"], "round": round_name, "team_code": m["team_code"]}, None


def discover_kalshi_round_markets(client: Kalshi) -> Tuple[List[Dict], List[str]]:
    """Fetch every open KXWCROUND market. Returns (parsed_markets, raw_pages)."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"series_ticker": KALSHI_ROUND_SERIES, "status": "open", "limit": 1000}
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

    out = []
    for m in markets:
        ticker = m.get("ticker", "")
        fields, err = parse_kalshi_round_ticker(ticker)
        title = m.get("title") or ""
        title_m = _KALSHI_TITLE_RE.match(title)
        yes_ask = m.get("yes_ask_dollars")
        out.append({
            "ticker": ticker,
            "ticker_parse_error": err,
            "round": (fields or {}).get("round"),
            "team_code": (fields or {}).get("team_code"),
            "team_name": title_m["team"] if title_m else None,
            "title": title,
            "yes_ask": float(yes_ask) if yes_ask is not None else None,
            "yes_bid": float(m["yes_bid_dollars"]) if m.get("yes_bid_dollars") is not None else None,
            "no_ask": float(m["no_ask_dollars"]) if m.get("no_ask_dollars") is not None else None,
            "no_bid": float(m["no_bid_dollars"]) if m.get("no_bid_dollars") is not None else None,
            "price_source_tag": "real_ask",
        })
    return out, raw_pages


# --------------------------------------------------------------------------- #
# Polymarket leg
# --------------------------------------------------------------------------- #
def _pm_get_json(path: str, **params: Any) -> Dict:
    r = requests.get(f"{GAMMA_BASE}{path}", params=params, headers=_UA, timeout=20)
    r.raise_for_status()
    return r.json()


def discover_polymarket_round_events(
        queries: Tuple[str, ...] = PM_SEARCH_QUERIES) -> Tuple[List[Dict], List[str]]:
    """Structural discovery: public-search narrows candidates, title/round regexes confirm
    before anything is used. Returns (parsed_markets, raw_pages)."""
    seen_event_ids: set = set()
    markets_out: List[Dict] = []
    raw_pages: List[str] = []
    for q in queries:
        resp = _pm_get_json("/public-search", q=q)
        raw_pages.append(canonical_json(resp))
        for event in (resp.get("events") or []):
            title = event.get("title") or ""
            if not _PM_EVENT_TITLE_RE.search(title):
                continue
            round_m = _PM_ROUND_RE.search(title)
            if not round_m:
                continue
            event_id = event.get("id")
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            round_name = round_m["round"].lower()
            for mkt in (event.get("markets") or []):
                team_name = mkt.get("groupItemTitle")
                if not team_name:
                    continue
                try:
                    token_ids = json.loads(mkt.get("clobTokenIds") or "[]")
                    outcomes = json.loads(mkt.get("outcomes") or "[]")
                except json.JSONDecodeError:
                    token_ids, outcomes = [], []
                yes_token = None
                if "Yes" in outcomes:
                    idx = outcomes.index("Yes")
                    if idx < len(token_ids):
                        yes_token = token_ids[idx]
                markets_out.append({
                    "event_id": event_id,
                    "market_id": mkt.get("id"),
                    "round": round_name,
                    "team_name": team_name,
                    "question": mkt.get("question"),
                    "yes_token_id": yes_token,
                })
    return markets_out, raw_pages


def fetch_clob_book(token_id: str) -> Dict[str, Any]:
    """Real order-book top-of-book off Polymarket's CLOB. `real_ask` grade: a live,
    fillable book, not a last-trade/mid reference."""
    r = requests.get(f"{CLOB_BASE}/book", params={"token_id": token_id}, headers=_UA, timeout=20)
    r.raise_for_status()
    j = r.json()
    bids = j.get("bids") or []
    asks = j.get("asks") or []
    best_bid = max((float(b["price"]) for b in bids), default=None)
    best_ask = min((float(a["price"]) for a in asks), default=None)
    return {"best_bid": best_bid, "best_ask": best_ask}


# --------------------------------------------------------------------------- #
# matching — exact (round, normalized team) only; ambiguous/no-match never guessed
# --------------------------------------------------------------------------- #
def match_pairs(kalshi_markets: List[Dict], polymarket_markets: List[Dict]
               ) -> Tuple[List[Tuple[Dict, Dict]], List[str], List[str]]:
    """Returns (matched pairs, unmatched kalshi tickers, ambiguous kalshi tickers)."""
    pm_index: Dict[Tuple[str, str], List[Dict]] = {}
    for pm in polymarket_markets:
        key = (pm["round"], _normalize_team(pm["team_name"]))
        pm_index.setdefault(key, []).append(pm)

    matched: List[Tuple[Dict, Dict]] = []
    unmatched: List[str] = []
    ambiguous: List[str] = []
    for km in kalshi_markets:
        if not km.get("round") or not km.get("team_name"):
            unmatched.append(km["ticker"])
            continue
        key = (km["round"], _normalize_team(km["team_name"]))
        candidates = pm_index.get(key, [])
        if len(candidates) == 1:
            matched.append((km, candidates[0]))
        elif len(candidates) == 0:
            unmatched.append(km["ticker"])
        else:
            ambiguous.append(km["ticker"])
    return matched, unmatched, ambiguous


# --------------------------------------------------------------------------- #
# capture — one JSONL line per matched (round, team) pair
# --------------------------------------------------------------------------- #
def run(client: Optional[Kalshi] = None, tape_dir: Optional[Path] = None,
        min_interval: float = 0.2,
        pm_discover: Callable[[], Tuple[List[Dict], List[str]]] = discover_polymarket_round_events,
        fetch_book: Callable[[str], Dict[str, Any]] = fetch_clob_book) -> Dict:
    """One read-only capture pass. `client`/`pm_discover`/`fetch_book`/`tape_dir` injectable
    for offline testing."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    kalshi_markets, kalshi_raw = discover_kalshi_round_markets(client)

    pm_error: Optional[str] = None
    try:
        pm_markets, _pm_raw = pm_discover()
    except Exception as exc:
        pm_markets, pm_error = [], str(exc)

    matched, unmatched_kalshi, ambiguous_kalshi = match_pairs(kalshi_markets, pm_markets)

    lines: List[str] = []
    book_errors: List[Dict[str, str]] = []
    for km, pm in matched:
        book = None
        if pm.get("yes_token_id"):
            try:
                book = fetch_book(pm["yes_token_id"])
            except Exception as exc:
                book_errors.append({"market_id": str(pm.get("market_id")), "error": str(exc)})
        pm_best_ask = (book or {}).get("best_ask")
        record = {
            "schema_version": "polymarket_pairs.v1",
            "capture_id": capture_id,
            "captured_at": captured_at,
            "round": km["round"],
            "team": km["team_name"],
            "kalshi": {
                "ticker": km["ticker"],
                "yes_ask": km["yes_ask"], "yes_bid": km["yes_bid"],
                "no_ask": km["no_ask"], "no_bid": km["no_bid"],
                "price_source_tag": "real_ask",
            },
            "polymarket": {
                "event_id": pm["event_id"], "market_id": pm["market_id"],
                "best_bid": (book or {}).get("best_bid"), "best_ask": pm_best_ask,
                "book_fetch_ok": book is not None,
                "price_source_tag": "real_ask",
            },
            "price_gap_yes_ask": (
                km["yes_ask"] - pm_best_ask
                if km["yes_ask"] is not None and pm_best_ask is not None else None
            ),
        }
        lines.append(canonical_json(record))

    n_kalshi = len(kalshi_markets)
    n_matched = len(matched)
    completeness_ok = (
        pm_error is None and not book_errors and not ambiguous_kalshi and n_matched == n_kalshi
    )
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_kalshi_markets": n_kalshi,
        "n_polymarket_markets": len(pm_markets),
        "n_matched": n_matched,
        "unmatched_kalshi": unmatched_kalshi,
        "ambiguous_kalshi": ambiguous_kalshi,
        "n_book_errors": len(book_errors),
        "book_errors": book_errors,
        "polymarket_discovery_error": pm_error,
        "completeness_ok": completeness_ok,
        "raw_kalshi_sha256": sha256_hex("".join(kalshi_raw).encode("utf-8")),
    }

    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)

    print(f"[polymarket_pairs] {capture_id}: {n_kalshi} kalshi round markets, "
          f"{n_matched} matched to polymarket, "
          f"completeness={'ok' if completeness_ok else 'FAIL'}")
    if pm_error:
        print(f"[polymarket_pairs] WARN polymarket discovery failed: {pm_error}", file=sys.stderr)
    if book_errors:
        print(f"[polymarket_pairs] WARN {len(book_errors)} CLOB book fetches failed", file=sys.stderr)
    return summary


# --------------------------------------------------------------------------- #
# Fed-decision leg (Q12/S17) — same discipline, a different (meeting, bucket) key
# --------------------------------------------------------------------------- #
TAPE_FED = REPO_ROOT / "tape" / "polymarket_macro_pairs"

KALSHI_FED_SERIES = "KXFEDDECISION"

# Identity only (grouping/logging) — the bps suffix is NOT trusted for matching semantics,
# see module docstring. e.g. KXFEDDECISION-26JUL-H25, KXFEDDECISION-26JUL-C26.
_KALSHI_FED_TICKER_RE = re.compile(r"^[A-Z0-9]+-\d{2}[A-Z]{3}-[HC]\d+$")
_KALSHI_FED_TITLE_RE = re.compile(
    r"^Will the Federal Reserve (?P<verb>Hike|Cut) rates by (?P<mag>>?\d+)bps "
    r"at their (?P<month>\w+) (?P<year>\d{4}) meeting\??$", re.I)

_MONTH_NUM = {m: i + 1 for i, m in enumerate((
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"))}
_MONTH_NUM.update({m[:3]: n for m, n in list(_MONTH_NUM.items())})


def _month_num(name: str) -> Optional[int]:
    return _MONTH_NUM.get((name or "").strip().lower())


def _fed_bucket_from_verb_mag(verb: str, mag: str) -> Optional[str]:
    """0bps is a single no-change bucket regardless of verb (Kalshi lists it once, as
    'Hike ... 0bps'); 25bps and >25bps split by verb into hike_25/cut_25/hike_50plus/
    cut_50plus (Polymarket's own bucket names, '25 bps'/'50+ bps' <in>crease/decrease)."""
    mag = mag.strip()
    if mag == "0":
        return "no_change"
    side = "hike" if verb.lower() == "hike" else "cut"
    if mag == "25":
        return f"{side}_25"
    if mag.startswith(">") and mag[1:].isdigit() and int(mag[1:]) >= 25:
        return f"{side}_50plus"
    return None


def parse_kalshi_fed_ticker(ticker: str, title: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Ticker regex confirms shape/identity; the title (verb/magnitude/month/year) supplies
    the actual matching semantics — never the ticker's bps suffix alone (see docstring)."""
    if not _KALSHI_FED_TICKER_RE.match(ticker.upper()):
        return None, "no_regex_match"
    m = _KALSHI_FED_TITLE_RE.match((title or "").strip())
    if not m:
        return None, "title_no_regex_match"
    month = _month_num(m["month"])
    if month is None:
        return None, f"unknown_month:{m['month']}"
    bucket = _fed_bucket_from_verb_mag(m["verb"], m["mag"])
    if bucket is None:
        return None, f"unknown_magnitude:{m['mag']}"
    return {"meeting_key": f"{m['year']}-{month:02d}", "bucket": bucket}, None


def discover_kalshi_fed_markets(client: Kalshi) -> Tuple[List[Dict], List[str]]:
    """Fetch every open KXFEDDECISION market. Returns (parsed_markets, raw_pages)."""
    markets: List[Dict] = []
    raw_pages: List[str] = []
    cursor: Optional[str] = None
    while True:
        params: Dict[str, Any] = {"series_ticker": KALSHI_FED_SERIES, "status": "open", "limit": 1000}
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

    out = []
    for m in markets:
        ticker = m.get("ticker", "")
        title = m.get("title") or ""
        fields, err = parse_kalshi_fed_ticker(ticker, title)
        yes_ask = m.get("yes_ask_dollars")
        out.append({
            "ticker": ticker,
            "ticker_parse_error": err,
            "meeting_key": (fields or {}).get("meeting_key"),
            "bucket": (fields or {}).get("bucket"),
            "title": title,
            "yes_ask": float(yes_ask) if yes_ask is not None else None,
            "yes_bid": float(m["yes_bid_dollars"]) if m.get("yes_bid_dollars") is not None else None,
            "no_ask": float(m["no_ask_dollars"]) if m.get("no_ask_dollars") is not None else None,
            "no_bid": float(m["no_bid_dollars"]) if m.get("no_bid_dollars") is not None else None,
            "price_source_tag": "real_ask",
        })
    return out, raw_pages


PM_FED_SEARCH_QUERIES: Tuple[str, ...] = ("Fed Decision",)
_PM_FED_EVENT_TITLE_RE = re.compile(r"^Fed [Dd]ecision in \w+\??$")
_PM_FED_QUESTION_RE = re.compile(r"after the (?P<month>\w+) (?P<year>\d{4}) meeting", re.I)


def _normalize_fed_bucket(group_item_title: str) -> Optional[str]:
    t = (group_item_title or "").strip().lower()
    if "no change" in t:
        return "no_change"
    m = re.search(r"(\d+)\+?\s*bps\s*(increase|decrease)", t)
    if not m:
        return None
    bps, direction = int(m[1]), m[2]
    side = "hike" if direction == "increase" else "cut"
    if bps >= 50:
        return f"{side}_50plus"
    if bps == 25:
        return f"{side}_25"
    return None


def discover_polymarket_fed_events(
        queries: Tuple[str, ...] = PM_FED_SEARCH_QUERIES) -> Tuple[List[Dict], List[str]]:
    """Structural discovery of single-meeting Fed-decision events only — skips multi-month
    bundle events (e.g. 'Fed decisions (Jul-Oct)') and off-topic hits (e.g. the FOMC
    dissent-count market): neither is the same one-meeting/5-bucket shape as Kalshi's
    KXFEDDECISION event, so matching them would mean guessing, not confirming."""
    seen_event_ids: set = set()
    markets_out: List[Dict] = []
    raw_pages: List[str] = []
    for q in queries:
        resp = _pm_get_json("/public-search", q=q, limit_per_type=20, events_status="active")
        raw_pages.append(canonical_json(resp))
        for event in (resp.get("events") or []):
            title = (event.get("title") or "").strip()
            if not _PM_FED_EVENT_TITLE_RE.match(title):
                continue
            event_id = event.get("id")
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            for mkt in (event.get("markets") or []):
                question = mkt.get("question") or ""
                qm = _PM_FED_QUESTION_RE.search(question)
                if not qm:
                    continue
                month = _month_num(qm["month"])
                if month is None:
                    continue
                bucket = _normalize_fed_bucket(mkt.get("groupItemTitle"))
                if bucket is None:
                    continue
                try:
                    token_ids = json.loads(mkt.get("clobTokenIds") or "[]")
                    outcomes = json.loads(mkt.get("outcomes") or "[]")
                except json.JSONDecodeError:
                    token_ids, outcomes = [], []
                yes_token = None
                if "Yes" in outcomes:
                    idx = outcomes.index("Yes")
                    if idx < len(token_ids):
                        yes_token = token_ids[idx]
                markets_out.append({
                    "event_id": event_id,
                    "market_id": mkt.get("id"),
                    "meeting_key": f"{qm['year']}-{month:02d}",
                    "bucket": bucket,
                    "question": question,
                    "yes_token_id": yes_token,
                })
    return markets_out, raw_pages


def match_fed_pairs(kalshi_markets: List[Dict], polymarket_markets: List[Dict]
               ) -> Tuple[List[Tuple[Dict, Dict]], List[str], List[str]]:
    """Same exact-key-only discipline as `match_pairs`, keyed by (meeting_key, bucket)."""
    pm_index: Dict[Tuple[str, str], List[Dict]] = {}
    for pm in polymarket_markets:
        key = (pm["meeting_key"], pm["bucket"])
        pm_index.setdefault(key, []).append(pm)

    matched: List[Tuple[Dict, Dict]] = []
    unmatched: List[str] = []
    ambiguous: List[str] = []
    for km in kalshi_markets:
        if not km.get("meeting_key") or not km.get("bucket"):
            unmatched.append(km["ticker"])
            continue
        key = (km["meeting_key"], km["bucket"])
        candidates = pm_index.get(key, [])
        if len(candidates) == 1:
            matched.append((km, candidates[0]))
        elif len(candidates) == 0:
            unmatched.append(km["ticker"])
        else:
            ambiguous.append(km["ticker"])
    return matched, unmatched, ambiguous


def run_fed_decision(client: Optional[Kalshi] = None, tape_dir: Optional[Path] = None,
        min_interval: float = 0.2,
        pm_discover: Callable[[], Tuple[List[Dict], List[str]]] = discover_polymarket_fed_events,
        fetch_book: Callable[[str], Dict[str, Any]] = fetch_clob_book) -> Dict:
    """One read-only capture pass over Fed-decision meetings (Q12/S17) — mirrors `run()`'s
    WC-round discipline (structural title confirmation, real CLOB book, honest unmatched/
    ambiguous accounting) for a family that outlives the World Cup."""
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE_FED
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    kalshi_markets, kalshi_raw = discover_kalshi_fed_markets(client)

    pm_error: Optional[str] = None
    try:
        pm_markets, _pm_raw = pm_discover()
    except Exception as exc:
        pm_markets, pm_error = [], str(exc)

    matched, unmatched_kalshi, ambiguous_kalshi = match_fed_pairs(kalshi_markets, pm_markets)

    lines: List[str] = []
    book_errors: List[Dict[str, str]] = []
    for km, pm in matched:
        book = None
        if pm.get("yes_token_id"):
            try:
                book = fetch_book(pm["yes_token_id"])
            except Exception as exc:
                book_errors.append({"market_id": str(pm.get("market_id")), "error": str(exc)})
        pm_best_ask = (book or {}).get("best_ask")
        record = {
            "schema_version": "polymarket_macro_pairs.v1",
            "capture_id": capture_id,
            "captured_at": captured_at,
            "family": "fed_decision",
            "meeting": km["meeting_key"],
            "bucket": km["bucket"],
            "kalshi": {
                "ticker": km["ticker"],
                "yes_ask": km["yes_ask"], "yes_bid": km["yes_bid"],
                "no_ask": km["no_ask"], "no_bid": km["no_bid"],
                "price_source_tag": "real_ask",
            },
            "polymarket": {
                "event_id": pm["event_id"], "market_id": pm["market_id"],
                "best_bid": (book or {}).get("best_bid"), "best_ask": pm_best_ask,
                "book_fetch_ok": book is not None,
                "price_source_tag": "real_ask",
            },
            "price_gap_yes_ask": (
                km["yes_ask"] - pm_best_ask
                if km["yes_ask"] is not None and pm_best_ask is not None else None
            ),
        }
        lines.append(canonical_json(record))

    # Completeness is judged against Polymarket's side, not Kalshi's: Kalshi lists
    # KXFEDDECISION meetings up to ~18 months out (confirmed live 2026-07-06: open events
    # ran to January 2028) while Polymarket only creates a meeting's event closer to it —
    # grading against "every open Kalshi market must match" would make this leg report
    # FAIL forever, poisoning `hourly_pass.py`'s overall completeness signal with a
    # structural non-issue rather than a real one. `unmatched_kalshi` is still recorded in
    # full for visibility — it just isn't what completeness gates on. What DOES gate:
    # every market Polymarket actually offered right now either matched 1:1 or is
    # accounted for as ambiguous.
    n_kalshi = len(kalshi_markets)
    n_polymarket = len(pm_markets)
    n_matched = len(matched)
    matched_pm_ids = {id(pm) for _, pm in matched}
    unmatched_polymarket = [pm.get("market_id") for pm in pm_markets if id(pm) not in matched_pm_ids]
    completeness_ok = (
        pm_error is None and not book_errors and not ambiguous_kalshi and not unmatched_polymarket
    )
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_kalshi_markets": n_kalshi,
        "n_polymarket_markets": n_polymarket,
        "n_matched": n_matched,
        "unmatched_kalshi": unmatched_kalshi,
        "unmatched_polymarket": unmatched_polymarket,
        "ambiguous_kalshi": ambiguous_kalshi,
        "n_book_errors": len(book_errors),
        "book_errors": book_errors,
        "polymarket_discovery_error": pm_error,
        "completeness_ok": completeness_ok,
        "raw_kalshi_sha256": sha256_hex("".join(kalshi_raw).encode("utf-8")),
    }

    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)

    print(f"[polymarket_macro_pairs] {capture_id}: {n_kalshi} kalshi fed-decision markets, "
          f"{n_matched} matched to polymarket, "
          f"completeness={'ok' if completeness_ok else 'FAIL'}")
    if pm_error:
        print(f"[polymarket_macro_pairs] WARN polymarket discovery failed: {pm_error}", file=sys.stderr)
    if book_errors:
        print(f"[polymarket_macro_pairs] WARN {len(book_errors)} CLOB book fetches failed", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Kalshi<->Polymarket World Cup round-market capture (read-only)")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())

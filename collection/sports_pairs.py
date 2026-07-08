"""Forward sports moneyline paired-odds capture (READ-ONLY) — bitemporal, schema-validated.

Serves S7 (Kalshi moneyline CLV vs de-vigged sharp line) and S11. Mirrors
collection/capture_orderbooks.py's discipline — bitemporal fetch_ts, raw-bytes sha256,
honest expected-vs-captured completeness — but groups by sports EVENT (one game), not
(city, contract-day).

A Kalshi moneyline event is N outcome markets sharing one ticker prefix
`<SERIES>-<EVENT>` (2-way: TEAM_A/TEAM_B; 3-way soccer: TEAM_A/TEAM_B/TIE), each an
independent binary YES/NO market. Moneyline markets are identified by market TITLE
shape "<A> vs <B> ... Winner?" (verified empirically against live KXWCGAME/KXMLBGAME
tickers) rather than by series alone — a `*GAME` series ticker can also carry
non-moneyline prop markets (e.g. KXWCTEAMSINGAME) that must not be swept in.

Unlike capture_orderbooks.py (writes to the gitignored `data/processed/`, for a
continuously-running laptop cron), this collector writes append-only JSONL directly
under the git-COMMITTED `tape/sports_pairs/` (see tape/README.md): a stateless cloud
run's only persistence is what it commits. Each line embeds the normalized BBO
snapshot inline; raw_sha256 is a tamper-evidence content-hash of the exact bytes
fetched, not a separate on-disk blob (see core/manifest_schema.py's "signature is
tamper-EVIDENCE, not tamper-proof" note — the same honesty applies here).

If `ODDS_API_KEY` is present, a future pass can fetch matched sportsbook odds too (a
de-vig is a MODEL, tag `synthetic` — never a fill price, never `real_ask`). No key ->
capture the Kalshi leg only; `odds_status` records `no_key` per event rather than
inventing a line. Building the actual sportsbook-matching integration is deferred
until a key exists to validate it against (Q1's own stop rule: no untested machinery).

Run one pass:
    python -m collection.sports_pairs                # all discoverable *GAME series
    python -m collection.sports_pairs --limit 40      # cap discovered outcome markets
Then schedule it (Q3's hourly_pass) to accumulate a CLV history.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.canonical import canonical_json, sha256_hex
from core.manifest_schema import sign, verify_signature
from collection.normalize import normalize_snapshot
from validation.v3_market import Kalshi, _load_venue_cfg

REPO_ROOT = Path(__file__).resolve().parent.parent
STORE = REPO_ROOT / "tape" / "sports_pairs"
ORDERBOOK_PATH = "/markets/{ticker}/orderbook"
SCHEMA_VERSION = "sports_pairs.v1"
SPORTS_CATEGORY = "Sports"

# <SERIES>-<EVENT>-<OUTCOME>, derived empirically from live tickers (e.g.
# KXWCGAME-26JUL09FRAMAR-FRA, KXMLBGAME-26JUL111410ATHCWS-CWS). Kept strict so
# an unexpected shape is skipped (never silently mis-grouped), same discipline as
# V3's TICKER_RE for weather.
_TICKER_RE = re.compile(r"^(?P<series>[A-Z0-9]+)-(?P<event>[A-Z0-9]+)-(?P<outcome>[A-Z0-9]+)$")
_MONEYLINE_TITLE_RE = re.compile(r"\bvs\b.+\bwinner\??\s*$", re.I)

# World Cup first, then everything else soccer, then everything else (2026 World Cup
# is TIME-SENSITIVE: ends Jul 19) — a `--limit` truncation must drop the LEAST
# time-sensitive events first, never World Cup ones. A plain Soccer-tag tier is not
# enough: ~130 other soccer leagues alphabetically precede "KXWCGAME".
_PRIORITY_TAGS = ("Soccer",)
_WORLD_CUP_PREFIX = "KXWC"


def parse_event_ticker(ticker: str) -> Optional[Tuple[str, str, str]]:
    """(series, event_code, outcome_code), or None if `ticker` doesn't match the
    <SERIES>-<EVENT>-<OUTCOME> moneyline grammar."""
    m = _TICKER_RE.match(ticker.upper())
    return (m.group("series"), m.group("event"), m.group("outcome")) if m else None


def is_moneyline_market(title: str) -> bool:
    """True iff a market TITLE has the "<A> vs <B> ... Winner?" moneyline shape."""
    return bool(_MONEYLINE_TITLE_RE.search(title or ""))


def devig_two_way(price_a: float, price_b: float) -> Tuple[float, float]:
    """Proportional de-vig of two complementary implied probabilities (1/decimal_odds)
    for a 2-way sportsbook market. Returns (fair_a, fair_b) summing to exactly 1.0.
    A MODEL, not a fill price -> callers must tag the result `synthetic`."""
    total = price_a + price_b
    if total <= 0:
        raise ValueError(f"non-positive implied-probability sum: {price_a} + {price_b}")
    return price_a / total, price_b / total


def devig_n_way(prices: List[float]) -> List[float]:
    """Proportional de-vig for an N-way market (e.g. 3-way soccer incl. draw)."""
    total = sum(prices)
    if total <= 0:
        raise ValueError(f"non-positive implied-probability sum: {prices}")
    return [p / total for p in prices]


def odds_status() -> str:
    """`no_key` (nothing else is implemented until a key exists to test against —
    building an untested sportsbook-matching integration is exactly the kind of
    speculative machinery this project's stop rules forbid) or `not_fetched` once a
    key is present but this pass hasn't wired the fetch in yet."""
    return "fetched" if os.environ.get("ODDS_API_KEY") else "no_key"


# --------------------------------------------------------------------------- #
# discovery — the EXPECTED set, grouped by (series, event)
# --------------------------------------------------------------------------- #
def discover_moneyline_series(client: Kalshi) -> List[dict]:
    """Sports series whose ticker looks like a per-game moneyline family (ends in
    'GAME'), soccer first (World Cup time-sensitivity) then everything else,
    alphabetically within each group. A cheap ticker-level filter before the
    expensive per-series open_markets() call; the market-TITLE filter
    (is_moneyline_market) is what actually decides moneyline-ness."""
    series = client.series_by_category(SPORTS_CATEGORY)
    candidates = [s for s in series if (s.get("ticker") or "").endswith("GAME")]

    def _rank(s: dict) -> Tuple[int, str]:
        ticker = s.get("ticker", "")
        tags = s.get("tags") or []
        if ticker.startswith(_WORLD_CUP_PREFIX):
            tier = 0
        elif any(t in _PRIORITY_TAGS for t in tags):
            tier = 1
        else:
            tier = 2
        return (tier, ticker)

    return sorted(candidates, key=_rank)


def discover_events(client: Kalshi, limit: Optional[int] = None
                    ) -> Tuple[Dict[Tuple[str, str], Dict], List[Dict[str, str]]]:
    """Enumerate open moneyline markets grouped by (series, event_code).

    Returns (events, series_errors). events[(series, event)] = {"sport": tag,
    "title": sample market title, "outcomes": [ticker, ...]}. series_errors records
    series whose market enumeration failed (a completeness gap surfaced, not hidden).
    """
    events: Dict[Tuple[str, str], Dict] = {}
    series_errors: List[Dict[str, str]] = []
    seen = 0
    for s in discover_moneyline_series(client):
        sticker = s.get("ticker", "")
        sport = (s.get("tags") or [None])[0]
        try:
            markets = client.open_markets(sticker)
        except Exception as exc:  # whole-series enumeration failure -> recorded, not hidden
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        for m in markets:
            ticker = m.get("ticker", "")
            title = m.get("title", "")
            if not is_moneyline_market(title):
                continue
            parsed = parse_event_ticker(ticker)
            if parsed is None:
                continue
            pseries, event, _outcome = parsed
            ev = events.setdefault((pseries, event),
                                   {"sport": sport, "title": title, "outcomes": []})
            ev["outcomes"].append(ticker)
            seen += 1
            if limit and seen >= limit:
                return events, series_errors
    return events, series_errors


# --------------------------------------------------------------------------- #
# manifest — one signed bitemporal line per (series, event)
# --------------------------------------------------------------------------- #
_REQUIRED: Dict[str, type] = {
    "schema_version": str, "capture_id": str, "venue": str, "sport": str,
    "series": str, "event": str, "event_title": str,
    "as_of": str, "captured_at": str, "source_endpoint": str,
    "raw_sha256": str, "normalized_sha256": str,
    "n_outcomes": int, "expected_outcomes": int, "n_with_book": int, "total_levels": int,
    "outcomes": list, "snapshots": list, "completeness_ok": bool, "warmup": bool,
    "odds_status": str, "signature": str,
}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SIG = re.compile(r"^sha256:[0-9a-f]{64}$")


def validate_manifest(record: Dict[str, Any]) -> List[str]:
    """Return human-readable errors; empty == valid. Same shape of checks as
    core.manifest_schema.validate (presence/type, hash format, completeness
    consistency, warm-up invariant, self-hash), adapted to the event grouping."""
    errs: List[str] = []
    if not isinstance(record, dict):
        return ["record is not a dict"]

    for name, typ in _REQUIRED.items():
        if name not in record:
            errs.append(f"missing field: {name}")
            continue
        val = record[name]
        if typ is int and isinstance(val, bool):
            errs.append(f"{name}: expected int, got bool")
        elif not isinstance(val, typ):
            errs.append(f"{name}: expected {typ.__name__}, got {type(val).__name__}")
    if errs:
        return errs

    if record["schema_version"] != SCHEMA_VERSION:
        errs.append(f"schema_version: expected {SCHEMA_VERSION!r}, got {record['schema_version']!r}")
    for name in ("capture_id", "venue", "series", "event", "source_endpoint"):
        if not record[name].strip():
            errs.append(f"{name}: must be non-empty")
    outcomes = record["outcomes"]
    if not outcomes:
        errs.append("outcomes: must be a non-empty list")
    elif not all(isinstance(o, str) and o.strip() for o in outcomes):
        errs.append("outcomes: every entry must be a non-empty string")
    snapshots = record["snapshots"]
    if not snapshots:
        errs.append("snapshots: must be a non-empty list")
    elif not all(isinstance(s, dict) for s in snapshots):
        errs.append("snapshots: every entry must be a dict")
    for name in ("raw_sha256", "normalized_sha256"):
        if not _HEX64.match(record[name]):
            errs.append(f"{name}: not a 64-char lowercase hex sha256")

    for name in ("n_outcomes", "expected_outcomes", "n_with_book", "total_levels"):
        if record[name] < 0:
            errs.append(f"{name}: must be >= 0")
    if record["expected_outcomes"] <= 0:
        errs.append("expected_outcomes must be >= 1 (an empty capture is not a capture)")
    if record["n_outcomes"] <= 0:
        errs.append("n_outcomes must be >= 1 (a capture with zero outcomes is degenerate)")
    if record["n_with_book"] > record["n_outcomes"]:
        errs.append("n_with_book cannot exceed n_outcomes")
    if record["n_outcomes"] > record["expected_outcomes"]:
        errs.append("n_outcomes cannot exceed expected_outcomes")
    if (record["n_with_book"] == 0) != (record["total_levels"] == 0):
        errs.append("n_with_book and total_levels disagree on emptiness")
    if record["completeness_ok"] != (record["n_outcomes"] == record["expected_outcomes"]):
        errs.append("completeness_ok inconsistent with n_outcomes == expected_outcomes")
    if record["warmup"] is not True:
        errs.append("warmup must be True (pre-temporal-contract capture)")
    if not _SIG.match(record["signature"]):
        errs.append("signature: must match 'sha256:<64 hex>'")
    elif not verify_signature(record):
        errs.append("signature: self-hash does not match record content")
    return errs


# --------------------------------------------------------------------------- #
# capture
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, store: Optional[Path] = None) -> Dict:
    """One read-only capture pass. `client`/`store` are injectable for offline testing;
    in production both default to the live Kalshi client and tape/sports_pairs/."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    source_endpoint = getattr(client, "base", "") + ORDERBOOK_PATH

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")
    ostatus = odds_status()

    events, series_errors = discover_events(client, limit=limit)

    manifests: List[Dict] = []
    degenerate: List[Dict] = []
    invalid: List[Dict] = []

    out_path = store / f"dt={day}.jsonl"

    for (sname, event), ev in sorted(events.items()):
        expected = sorted(set(ev["outcomes"]))
        raw_index: List[List[str]] = []
        snapshots: List[Dict] = []
        dropped: List[str] = []
        n_with_book = total_levels = 0

        for ticker in expected:
            try:
                text = client.get_text(ORDERBOOK_PATH.format(ticker=ticker))
            except Exception:  # a failed fetch -> a DROP -> completeness_ok goes False
                dropped.append(ticker)
                continue
            raw_index.append([ticker, sha256_hex(text.encode("utf-8"))])
            ob = (json.loads(text) or {}).get("orderbook_fp") or {}
            snap = normalize_snapshot(ticker, ob)
            snap["source_tag"] = "real_ask"
            snapshots.append(snap)
            n_with_book += snap["depth"] > 0
            total_levels += snap["depth"]

        captured = sorted(s["ticker"] for s in snapshots)
        if not captured:
            degenerate.append({"series": sname, "event": event, "expected": len(expected)})
            continue

        normalized = {"venue": "kalshi", "series": sname, "event": event,
                      "outcomes": sorted(snapshots, key=lambda s: s["ticker"])}
        normalized_str = canonical_json(normalized)

        manifest_body = {
            "schema_version": SCHEMA_VERSION, "capture_id": capture_id,
            "venue": "kalshi", "sport": ev["sport"] or "unknown",
            "series": sname, "event": event, "event_title": ev["title"],
            "as_of": captured_at, "captured_at": captured_at,
            "source_endpoint": source_endpoint,
            "raw_sha256": sha256_hex(canonical_json(sorted(raw_index))),
            "normalized_sha256": sha256_hex(normalized_str),
            "n_outcomes": len(captured), "expected_outcomes": len(expected),
            "n_with_book": n_with_book, "total_levels": total_levels,
            "outcomes": captured, "snapshots": normalized["outcomes"],
            "completeness_ok": (len(captured) == len(expected)),
            "warmup": True, "odds_status": ostatus,
        }
        manifest = sign(manifest_body)
        errs = validate_manifest(manifest)
        if errs:
            print(f"[sports_pairs] WARN {sname} {event}: manifest invalid, not written: "
                  f"{errs}", file=sys.stderr)
            invalid.append({"series": sname, "event": event, "errors": errs})
            continue

        store.mkdir(parents=True, exist_ok=True)
        with open(out_path, "a") as f:
            f.write(canonical_json(manifest) + "\n")
        manifests.append(manifest)
        if dropped:
            print(f"[sports_pairs] {sname} {event}: {len(captured)}/{len(expected)} books "
                  f"(DROPPED {len(dropped)} -> completeness_ok=False)")

    n_complete = sum(1 for m in manifests if m["completeness_ok"])
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_events": len(manifests), "n_complete": n_complete,
        "n_degenerate": len(degenerate), "n_invalid": len(invalid),
        "n_series_errors": len(series_errors),
        "total_outcomes": sum(m["n_outcomes"] for m in manifests),
        "total_levels": sum(m["total_levels"] for m in manifests),
        "odds_status": ostatus,
    }
    print(f"[sports_pairs] {capture_id}: {summary['n_events']} events, "
          f"{n_complete} complete, {summary['total_outcomes']} outcome markets, "
          f"odds={ostatus} -> {out_path}")
    if degenerate:
        print(f"[sports_pairs] WARN {len(degenerate)} discovered event(s) captured zero "
              f"books (gap recorded, no line emitted)", file=sys.stderr)
    if series_errors:
        print(f"[sports_pairs] WARN {len(series_errors)} series failed enumeration "
              f"(may be missing events this pass)", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Forward sports moneyline paired-odds capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap discovered outcome markets per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())

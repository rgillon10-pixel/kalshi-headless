"""Forward full-depth orderbook capture (READ-ONLY) — bitemporal, schema-validated.

Builds the time-series of Kalshi temperature-market depth that H1 (ladder coherence)
and H3 (nowcast lead) need — and that Kalshi does NOT archive, so it cannot be
backfilled. This is why capture must start now.

This is NOT an order path (D5/C1): it only GETs public market data. Each pass emits one
*signed CaptureManifest line per (city, contract-day)* — the same locked m1.v0 schema the
Milestone-1 dry-run mints (collection/m1_capture.py), so the forward stream inherits the
bitemporal contract (D3): every line carries `event_time` (the contract-day described),
`as_of`/`captured_at` (when we first received these exact bytes), content hashes that pin
the bytes, and `warmup=True` (C7 — pre-temporal-contract capture is excluded from every
holdout; flipping warm-up off is a later, deliberate Phase-0/seal step, not this script's).

Completeness, not just liveness (D3): the discovered open-market set is the *expected*
set; a per-market orderbook fetch that fails is recorded as a DROP, lowering `n_markets`
below `expected_markets` so `completeness_ok` goes False. A throttled/truncated response
that silently drops markets can therefore never masquerade as a complete capture — that
silent drop is exactly the survivorship / corrupted-actuals failure mode this repo exists
to prevent. (Series-enumeration failures — a whole city invisible for a pass — are recorded
in the pass summary and surface later as a missing (city, day) line; per-market completeness
is what this layer pins. Density-based expected counts are a Phase-1 deepening.)

Kalshi books are bids-only per outcome, so the opposite side's best ask is derived as
1 - opposite_best_bid (the value H1 actually trades on); see collection/normalize.py.

Run one pass:
    python -m collection.capture_orderbooks            # all active temp markets (~480, ~2 min)
    python -m collection.capture_orderbooks --limit 120
Then schedule it (cron / the schedule skill) every ~15-30 min to accumulate history.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import DATA_PROCESSED
from core.manifest_schema import CaptureManifest, validate
from collection.normalize import normalize_snapshot  # re-exported for back-compat
from validation.v3_market import (CODE_TO_CITY, WEATHER_CATEGORY, Kalshi,
                                  _classify, _code_of, _load_venue_cfg)

STORE = DATA_PROCESSED / "orderbooks"
ORDERBOOK_PATH = "/markets/{ticker}/orderbook"
_DATE_TOKEN = re.compile(r"-(\d{2}[A-Z]{3}\d{2})-")


def _slug(text: str) -> str:
    return "".join(c for c in text.lower() if c.isalnum())


def _ticker_date(ticker: str) -> Optional[date]:
    m = _DATE_TOKEN.search(ticker.upper())
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%y%b%d").date()
    except ValueError:
        return None


def _city_of_series(series_ticker: str) -> str:
    """City for a series from its ticker code (authoritative CODE_TO_CITY, V3). Falls back
    to the raw code so an unmapped series still yields a non-empty city rather than crashing."""
    code = _code_of(series_ticker)
    return CODE_TO_CITY.get(code, code)


def _group_stem(city: str, target_date: str) -> str:
    return f"{_slug(city)}__{target_date}"


# --------------------------------------------------------------------------- #
# discovery — the EXPECTED set, grouped by (city, contract-day)
# --------------------------------------------------------------------------- #
def discover_groups(client: Kalshi, limit: Optional[int] = None
                    ) -> Tuple[Dict[Tuple[str, str], Dict], List[Dict[str, str]]]:
    """Enumerate open temp markets grouped by (city, target_date).

    Returns (groups, series_errors). groups[(city, date)] = {"series": set, "tickers": [..]}.
    series_errors records series whose market enumeration failed (a completeness gap that
    can't be priced from what we *did* see — surfaced, never silently swallowed)."""
    groups: Dict[Tuple[str, str], Dict] = {}
    series_errors: List[Dict[str, str]] = []
    seen = 0
    for s in client.series_by_category(WEATHER_CATEGORY):
        if not _classify(s):
            continue
        sticker = s.get("ticker", "")
        try:
            markets = client.open_markets(sticker)
        except Exception as exc:  # whole-series enumeration failure -> recorded, not hidden
            series_errors.append({"series": sticker, "error": str(exc)})
            continue
        city = _city_of_series(sticker)
        for m in markets:
            ticker = m.get("ticker", "")
            d = _ticker_date(ticker)
            if d is None:
                continue
            g = groups.setdefault((city, d.isoformat()), {"series": set(), "tickers": []})
            g["series"].add(sticker)
            g["tickers"].append(ticker)
            seen += 1
            if limit and seen >= limit:
                return groups, series_errors
    return groups, series_errors


# --------------------------------------------------------------------------- #
# capture — one signed bitemporal manifest line per (city, contract-day)
# --------------------------------------------------------------------------- #
def run(limit: Optional[int] = None, min_interval: float = 0.2,
        client: Optional[Kalshi] = None, store: Optional[Path] = None) -> Dict:
    """One read-only capture pass. `client`/`store` are injectable for offline testing;
    in production both default to the live Kalshi client and the real processed store."""
    store = Path(store) if store is not None else STORE
    if client is None:
        cfg = _load_venue_cfg()
        client = Kalshi(cfg["api_base"], min_interval=min_interval)
    source_endpoint = getattr(client, "base", "") + ORDERBOOK_PATH

    # the wall-clock is read ONCE per pass and frozen into every line (D3 receipt instant)
    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    groups, series_errors = discover_groups(client, limit=limit)
    capture_dir = store / f"dt={day}" / f"capture-{capture_id}"

    manifests: List[Dict] = []
    degenerate: List[Dict] = []   # discovered groups where zero books could be captured
    invalid: List[Dict] = []      # groups whose manifest failed schema validation (never written)

    for (city, target_date), g in sorted(groups.items()):
        expected = sorted(set(g["tickers"]))
        raw_by_ticker: Dict[str, str] = {}
        raw_index: List[List[str]] = []
        snapshots: List[Dict] = []
        dropped: List[str] = []
        n_with_book = total_levels = 0

        for ticker in expected:
            try:
                text = client.get_text(ORDERBOOK_PATH.format(ticker=ticker))
            except Exception:           # a failed fetch -> a DROP -> completeness_ok goes False
                dropped.append(ticker)
                continue
            raw_by_ticker[ticker] = text
            raw_index.append([ticker, sha256_hex(text.encode("utf-8"))])
            ob = (json.loads(text) or {}).get("orderbook_fp") or {}
            snap = normalize_snapshot(ticker, ob)
            snapshots.append(snap)
            n_with_book += snap["depth"] > 0
            total_levels += snap["depth"]

        captured = sorted(raw_by_ticker)
        if not captured:
            # a discovered group we captured NOTHING from is degenerate: emitting a manifest
            # would mean validating a zero-market capture (the survivorship mode). Record the
            # gap loudly instead — never write an invalid/empty "complete" line.
            degenerate.append({"city": city, "target_date": target_date,
                               "expected": len(expected)})
            continue

        normalized = {"venue": "kalshi", "city": city, "target_date": target_date,
                      "snapshots": sorted(snapshots, key=lambda s: s["ticker"])}
        normalized_str = canonical_json(normalized)

        manifest = CaptureManifest(
            capture_id=capture_id, venue="kalshi", city=city, target_date=target_date,
            event_time=target_date + "T00:00:00+00:00",   # the contract-day described
            as_of=captured_at, captured_at=captured_at,    # warm-up: observability == receipt
            source_endpoint=source_endpoint,
            raw_sha256=sha256_hex(canonical_json(sorted(raw_index))),
            normalized_sha256=sha256_hex(normalized_str),
            n_markets=len(captured), expected_markets=len(expected),
            n_with_book=n_with_book, total_levels=total_levels,
            series=sorted(g["series"]),
            completeness_ok=(len(captured) == len(expected)),
            warmup=True,
        ).signed()

        errs = validate(manifest)
        if errs:
            print(f"[capture] WARN {city} {target_date}: manifest invalid, not written: "
                  f"{errs}", file=sys.stderr)
            invalid.append({"city": city, "target_date": target_date, "errors": errs})
            continue

        # persist provenance (verbatim raw bytes + canonical normalized) then the manifest line
        capture_dir.mkdir(parents=True, exist_ok=True)
        stem = _group_stem(city, target_date)
        (capture_dir / f"{stem}.raw.json").write_text(
            canonical_json(raw_by_ticker), encoding="utf-8")
        (capture_dir / f"{stem}.normalized.json").write_text(normalized_str, encoding="utf-8")
        store.mkdir(parents=True, exist_ok=True)
        with open(store / "_manifest.jsonl", "a") as mf:
            mf.write(canonical_json(manifest) + "\n")
        manifests.append(manifest)
        if dropped:
            print(f"[capture] {city} {target_date}: {len(captured)}/{len(expected)} books "
                  f"(DROPPED {len(dropped)} -> completeness_ok=False)")

    n_complete = sum(1 for m in manifests if m["completeness_ok"])
    summary = {
        "capture_id": capture_id, "day": day, "captured_at": captured_at,
        "n_groups": len(manifests), "n_complete": n_complete,
        "n_degenerate": len(degenerate), "n_invalid": len(invalid),
        "n_series_errors": len(series_errors),
        "total_markets": sum(m["n_markets"] for m in manifests),
        "total_levels": sum(m["total_levels"] for m in manifests),
    }
    print(f"[capture] {capture_id}: {summary['n_groups']} (city,day) groups, "
          f"{n_complete} complete, {summary['total_markets']} markets, "
          f"{summary['total_levels']} levels -> {capture_dir}")
    if degenerate:
        print(f"[capture] WARN {len(degenerate)} discovered group(s) captured zero books "
              f"(gap recorded, no line emitted)", file=sys.stderr)
    if series_errors:
        print(f"[capture] WARN {len(series_errors)} series failed enumeration "
              f"(city/day may be missing this pass)", file=sys.stderr)
    return summary


def verify_against_dir(manifest: Dict, capture_dir: Path) -> List[str]:
    """Recompute the manifest's content hashes from the ON-DISK provenance and confirm they
    match. Binds raw_sha256/normalized_sha256 to the actual written bytes, so a self-consistent
    but fabricated manifest is caught (provenance, not just structural validity). Empty == OK."""
    capture_dir = Path(capture_dir)
    errs: List[str] = []
    stem = _group_stem(manifest["city"], manifest["target_date"])

    raw_file = capture_dir / f"{stem}.raw.json"
    if not raw_file.exists():
        errs.append(f"raw provenance missing: {stem}.raw.json")
    else:
        raw_by_ticker = json.loads(raw_file.read_text(encoding="utf-8"))
        raw_index = sorted([t, sha256_hex(text.encode("utf-8"))]
                           for t, text in raw_by_ticker.items())
        if sha256_hex(canonical_json(raw_index)) != manifest.get("raw_sha256"):
            errs.append("raw_sha256 does not match on-disk raw bytes")

    norm_file = capture_dir / f"{stem}.normalized.json"
    if not norm_file.exists():
        errs.append(f"normalized provenance missing: {stem}.normalized.json")
    elif sha256_hex(norm_file.read_bytes()) != manifest.get("normalized_sha256"):
        errs.append("normalized_sha256 does not match on-disk normalized.json")
    return errs


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Forward orderbook depth capture (read-only)")
    ap.add_argument("--limit", type=int, default=None, help="cap markets per pass")
    ap.add_argument("--min-interval", type=float, default=0.2)
    args = ap.parse_args(argv)
    run(limit=args.limit, min_interval=args.min_interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())

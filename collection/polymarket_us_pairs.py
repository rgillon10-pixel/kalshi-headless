"""Polymarket US (QCEX) book-capture leg (READ-ONLY, credential-gated) — LOOP-QUEUE.md Q33.

Our existing `collection/polymarket_pairs.py` families capture the INTERNATIONAL Polymarket
book (`clob.polymarket.com`). The venue Ryan actually trades is Polymarket US (QCEX), which
may quote different prices/liquidity. Every cross-venue finding (Q31/Q32) currently carries a
"not a Polymarket-US fill" provenance caveat BECAUSE we lack this tape. This collector closes
that caveat for the lines it writes: they ARE the Polymarket-US venue's own order book, a
distinct tape family (`tape/polymarket_us_pairs/`) from the international `polymarket_pairs`
tape, tagged `real_ask` because a live US order book is a genuine, fillable quote.

Credential gate (mirrors `collection/odds_api.py`'s `ODDS_API_KEY` no-op pattern EXACTLY):
this leg is a no-op unless a Polymarket-US credential is present in the environment. The
presence signal is a single documented env var, `POLYMARKET_US_API_KEY`. When it is ABSENT
(the ONLY state a cloud sandbox can ever be in — see the Stop rules and Q33's own text), `run`
makes NO network call, writes NO file, and returns `{"status": "blocked_key", ...}`. The
secret's VALUE is never printed, logged, or persisted; only its presence is checked.

Why the live fetch is not built here: real Polymarket-US auth is Ed25519 + a KYC'd account,
and the live-client bring-up is Ryan-supervised VPS/local work (creds live only in the VPS
env, never in this repo, never in a cloud sandbox). This module is therefore the disciplined,
offline-tested COLLECTOR skeleton that self-activates the moment the credential lands: it
resolves the credential, then delegates the two network operations to INJECTABLE callables —
  * `discover_fn()`   -> the matched-market set to snapshot (the SAME (round, team) /
                         (meeting, bucket) questions we already pair on the international side),
  * `fetch_us_book_fn(matched_market)` -> that market's Polymarket-US order book.
The default implementations are documented VPS-bring-up stubs (`_default_discover`,
`_default_fetch_us_book`) that raise `NotImplementedError`: they are NEVER exercised in tests
or in a cloud pass (the credential is absent there, so `run` returns `blocked_key` before
reaching them), and on the VPS Ryan injects the real Ed25519 client. A stub reached on a
credentialed path surfaces HONESTLY as a `discovery_error` / `book_error` — never a fake
success. (Judgment call, flagged: mapping the venue-neutral question identity to a
Polymarket-US market/token id needs the real KYC'd client, so the default discovery cannot be
wired autonomously; the collector's job per Q33 is the ready-to-activate skeleton, not the
bring-up.)

Provenance / tags, per captured US-book line:
  * `price_source_tag: "real_ask"` — a live US order book, a genuine fillable quote.
  * bitemporal `captured_at` (fetch/capture wall-clock, ISO-8601 UTC) + `capture_id`.
  * raw-bytes `sha256` of the fetched US-book payload (`raw_sha256`), when the fetch returns
    the raw bytes/text alongside the parsed book.

Honest match/no-book accounting (never a silent drop):
  * a discovered matched market whose US book the fetch returns as `None` (the US venue does
    not list it) is recorded in `no_book`, no line written.
  * a fetch that RAISES is a `book_error` (a genuine fetch/parse failure) — recorded and it
    LOWERS `completeness_ok`.
  * an EMPTY book (one-sided or fully empty ladder) is DATA, not a drop — it is written as a
    normal line with `best_bid`/`best_ask` possibly `None` (far-from-strike/thin shape, per
    lesson L23), and never counts against completeness.

Completeness judgment (flagged): `completeness_ok` gates on discovery succeeding and on zero
fetch EXCEPTIONS. A `no_book` (US venue simply doesn't list an internationally-matched
question) is recorded but does NOT gate — Polymarket-US (a US-regulated subset) plausibly
lists fewer markets than the international book, a structural non-issue analogous to Kalshi's
18-month forward calendar vs Polymarket's short one; grading it as a failure would poison the
hourly signal with a structural difference, not a real capture fault. It is still recorded in
full for visibility.

Run one pass (a cloud/no-credential pass just prints/returns blocked_key):
    python -m collection.polymarket_us_pairs
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from core.canonical import canonical_json, sha256_hex
from core.io import REPO_ROOT

TAPE = REPO_ROOT / "tape" / "polymarket_us_pairs"

FAMILY = "polymarket_us_pairs"
VENUE = "polymarket_us"
SCHEMA_VERSION = "polymarket_us_pairs.v1"

# Single documented presence signal — same role ODDS_API_KEY plays for the odds leg. Its
# VALUE is never read into a tape line, printed, or logged; only its truthiness is checked.
CREDENTIAL_ENV_VAR = "POLYMARKET_US_API_KEY"


# --------------------------------------------------------------------------- #
# VPS-bring-up default stubs (NEVER exercised in tests or a cloud pass — the credential is
# absent there, so run() returns blocked_key before reaching these). Ryan injects the real
# Ed25519 client's discovery + book fetch on the VPS.
# --------------------------------------------------------------------------- #
def _default_discover() -> Tuple[List[Dict[str, Any]], List[str]]:
    raise NotImplementedError(
        "polymarket_us_pairs default discovery is a VPS-bring-up stub — inject discover_fn "
        "(the real Ed25519/KYC'd Polymarket-US client resolves the matched-question set to "
        "US market/token ids). This is never called on a cloud pass (credential absent).")


def _default_fetch_us_book(matched_market: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    raise NotImplementedError(
        "polymarket_us_pairs default book fetch is a VPS-bring-up stub — inject "
        "fetch_us_book_fn (the real Ed25519/KYC'd Polymarket-US client). This is never called "
        "on a cloud pass (credential absent).")


def _blocked_key(reason: str) -> Dict[str, Any]:
    """The no-op contract when the credential is absent: no network, no file, just this dict.
    Mirrors odds_api.py — the ONLY path a cloud run can ever hit."""
    return {
        "status": "blocked_key",
        "family": FAMILY,
        "venue": VENUE,
        "credential_env": CREDENTIAL_ENV_VAR,
        "reason": reason,
    }


def _raw_sha256(raw: Any) -> Optional[str]:
    """sha256 of the fetched US-book raw payload (str/bytes), else None. The raw bytes are the
    provenance anchor — a caller that returns only a parsed book (no `raw`) yields None here,
    recorded honestly rather than faked."""
    if isinstance(raw, (str, bytes, bytearray)):
        return sha256_hex(raw)
    return None


def _match_key(mm: Dict[str, Any]) -> Optional[str]:
    """A stable human-readable key for the matched question (grouping/logging only). Prefer an
    explicit `match_key`; else fold the family's own key fields."""
    if mm.get("match_key") is not None:
        return str(mm["match_key"])
    if mm.get("round") is not None and mm.get("team") is not None:
        return f"{mm['round']}|{mm['team']}"
    if mm.get("meeting") is not None and mm.get("bucket") is not None:
        return f"{mm['meeting']}|{mm['bucket']}"
    return None


# --------------------------------------------------------------------------- #
# one read-only capture pass
# --------------------------------------------------------------------------- #
def run(api_key: Optional[str] = None,
        tape_dir: Optional[Path] = None,
        discover_fn: Optional[Callable[[], Tuple[List[Dict[str, Any]], List[str]]]] = None,
        fetch_us_book_fn: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None,
        env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """One credential-gated, READ-ONLY Polymarket-US book-capture pass.

    Absent credential (`POLYMARKET_US_API_KEY`) => no network, no file, `{"status":
    "blocked_key", ...}` (the only path a cloud run can hit). Present credential => snapshot
    each matched market's US order book (best bid/ask + depth, tag `real_ask`) into
    `tape/polymarket_us_pairs/dt=<day>.jsonl`, with bitemporal `captured_at`, raw-bytes
    `sha256` provenance, and honest no_book/book_error accounting.

    `api_key`/`tape_dir`/`discover_fn`/`fetch_us_book_fn`/`env` are injectable for offline
    testing; the two network callables default to VPS-bring-up stubs (see module docstring).
    """
    if env is None:
        env = os.environ
    if api_key is None:
        api_key = env.get(CREDENTIAL_ENV_VAR)
    if not api_key:
        # No credential: the whole leg is a no-op. NEVER touches the network or the tape.
        print(f"[{FAMILY}] blocked_key: {CREDENTIAL_ENV_VAR} absent — no network, wrote nothing")
        return _blocked_key(f"{CREDENTIAL_ENV_VAR} absent — no network, wrote nothing")

    discover_fn = discover_fn or _default_discover
    fetch_us_book_fn = fetch_us_book_fn or _default_fetch_us_book
    tape_dir = Path(tape_dir) if tape_dir is not None else TAPE

    cap_ts = datetime.now(timezone.utc)
    captured_at = cap_ts.isoformat()
    capture_id = cap_ts.strftime("%Y%m%dT%H%M%SZ")
    day = cap_ts.strftime("%Y-%m-%d")

    discovery_error: Optional[str] = None
    discovery_raw: List[str] = []
    try:
        matched, discovery_raw = discover_fn()
    except Exception as exc:
        matched, discovery_error = [], str(exc)

    lines: List[str] = []
    book_errors: List[Dict[str, str]] = []
    no_book: List[Optional[str]] = []
    for mm in matched:
        ident = mm.get("kalshi_ticker") or mm.get("us_market_id") or _match_key(mm)
        try:
            book = fetch_us_book_fn(mm)
        except Exception as exc:
            book_errors.append({"market": str(ident), "error": str(exc)})
            continue
        if book is None:
            # US venue does not list this internationally-matched question — recorded, not a
            # fetch failure (see completeness judgment in the module docstring).
            no_book.append(ident)
            continue
        record = {
            "schema_version": SCHEMA_VERSION,
            "capture_id": capture_id,
            "captured_at": captured_at,
            "venue": VENUE,
            "family": mm.get("family"),
            "match_key": _match_key(mm),
            "kalshi_ticker": mm.get("kalshi_ticker"),
            "polymarket_us": {
                "market_id": mm.get("us_market_id"),
                # empty/one-sided ladder is DATA (L23): best_bid/best_ask may be None, never a drop.
                "best_bid": book.get("best_bid"),
                "best_ask": book.get("best_ask"),
                "bids": book.get("bids"),
                "asks": book.get("asks"),
                "book_fetch_ok": True,
                "price_source_tag": "real_ask",
            },
            "raw_sha256": _raw_sha256(book.get("raw")),
        }
        lines.append(canonical_json(record))

    # Gates on discovery succeeding and zero fetch EXCEPTIONS. no_book (US venue doesn't list a
    # matched question) is a documented structural non-issue and does NOT gate — see docstring.
    completeness_ok = discovery_error is None and not book_errors
    summary: Dict[str, Any] = {
        "status": "ok",
        "capture_id": capture_id,
        "day": day,
        "captured_at": captured_at,
        "family": FAMILY,
        "venue": VENUE,
        "n_matched_markets": len(matched),
        "n_captured": len(lines),
        "n_no_book": len(no_book),
        "no_book": no_book,
        "n_book_errors": len(book_errors),
        "book_errors": book_errors,
        "discovery_error": discovery_error,
        "completeness_ok": completeness_ok,
        "raw_discovery_sha256": sha256_hex("".join(discovery_raw).encode("utf-8")) if discovery_raw else None,
    }

    if lines:
        tape_dir.mkdir(parents=True, exist_ok=True)
        out_path = tape_dir / f"dt={day}.jsonl"
        with open(out_path, "a", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")
        summary["path"] = str(out_path)

    print(f"[{FAMILY}] {capture_id}: {len(matched)} matched markets, "
          f"{len(lines)} US books captured, {len(no_book)} no_book, "
          f"completeness={'ok' if completeness_ok else 'FAIL'}")
    if discovery_error:
        print(f"[{FAMILY}] WARN discovery failed: {discovery_error}", file=sys.stderr)
    if book_errors:
        print(f"[{FAMILY}] WARN {len(book_errors)} US book fetches failed", file=sys.stderr)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Polymarket US book-capture leg (read-only, credential-gated)")
    ap.parse_args(argv)
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

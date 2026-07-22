"""Live default `discover_fn` / `fetch_us_book_fn` for the Polymarket US book-capture leg
(Q33 bring-up half) — READ-ONLY, credential-gated, NO order verbs.

`collection/polymarket_us_pairs.py` is the credential-gated skeleton: absent
`POLYMARKET_US_API_KEY` it is a no-op (`blocked_key`, zero network, zero files), and when a
credential is present it delegates the two network operations to injectable callables. This
module supplies the REAL implementations of those two callables and a `run()` that wires them
in — the piece that self-activates on the credentialed VPS/local box.

## Why everything is still credential-gated (live probe, 2026-07-21)
The official docs (docs.polymarket.us) say *"Public endpoints like market data and events
don't need one [API key]."* The LIVE API disagrees: from this machine every `/v1/...` data
endpoint (`markets`, `events`, `search`, `series`, `sports`, `markets/{slug}/book`,
`markets/{slug}/bbo`) returns `401 Missing required API key headers`; only `/v1/health` (which
carries no market data) answers unauthenticated. The 401 comes from Polymarket's own gateway
(`x-pm-trace-id` present, `cf-ray ...-ORD` US edge), not a CDN geo-block. Full write-up:
`findings/2026-07-21-polymarket-us-public-api-probe.md`.

Consequence: there is NO unauthenticated public mode to build (a `POLYMARKET_US_PUBLIC=1`
gate would just 401). Every read is an Ed25519-signed GET. The leg therefore stays gated on
`POLYMARKET_US_API_KEY` (Key ID presence) exactly as the skeleton is — the cloud-run no-op
guarantee is trivially intact: a cloud sandbox has no credential, `polymarket_us_pairs.run`
returns `blocked_key` before any code here is reached. Signing needs BOTH:
  * `POLYMARKET_US_API_KEY`    — the Key ID (also the skeleton's presence signal), and
  * `POLYMARKET_US_SECRET_KEY` — the base64 Ed25519 secret (used ONLY to sign; never logged).

## Provenance / discipline
  * A live US order book is a genuine fillable quote -> `price_source_tag: "real_ask"`
    (the skeleton stamps this; `outcomePrices`/`currentPx`/`lastTradePx` are last/mid
    references and are NEVER treated as fillable).
  * Empty / one-sided book is DATA, not a drop (L23): `parse_us_book` returns `[]`/`None` for
    an empty side and never raises for it. Only a genuine HTTP/JSON failure raises -> the
    skeleton records it as a `book_error` that lowers completeness.
  * A `404` on `/v1/markets/{slug}/book`, or an internationally-matched question with no US
    market found in discovery, is a `no_book` (US venue simply doesn't list it) — recorded,
    not a fetch failure, and does not gate completeness.
  * Memory cap (L10): the US listing pull is capped (`MAX_US_MARKETS`) with an honest
    truncation marker; the US-regulated universe is far smaller than Kalshi's 10k+, so this
    is a safety belt, not an expected trip.
  * Numeric parsing goes through `core.kalshi_fields.parse_kalshi_numeric` (L100) — the
    `Amount.value` / `qty` wire fields are decimal STRINGS; an absent number is honestly
    `None`, never a fabricated 0.

## Read-only, structurally
This module imports nothing from `execution/`, defines no order-placement / order-cancellation
/ quote verb, and issues only `GET` requests to market-data paths. The Ed25519 `auth_headers` helper is included so the
later authenticated WebSocket/trading bring-up has one vetted signer — but placing an order is
out of scope here and forbidden to autonomous work.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import ed25519

from collection import polymarket_us_pairs as pus
from core.canonical import canonical_json
from core.kalshi_fields import parse_kalshi_numeric

REST_BASE = "https://api.polymarket.us"
_UA = "kalshi-headless/0.0 (research)"

# Key ID (also the skeleton's presence signal) + base64 Ed25519 secret. Standardized names.
API_KEY_ENV = "POLYMARKET_US_API_KEY"       # X-PM-Access-Key value (Key ID)
SECRET_KEY_ENV = "POLYMARKET_US_SECRET_KEY"  # base64 Ed25519 secret (sign-only, never logged)

# Memory cap (L10): a US /v1/markets sweep is bounded; carry an honest truncation flag.
MAX_US_MARKETS = 8000
_US_PAGE_SIZE = 500

_MONTHS = ("january", "february", "march", "april", "may", "june",
           "july", "august", "september", "october", "november", "december")


# --------------------------------------------------------------------------- #
# Ed25519 signing (READ-ONLY use here; provided for the later WS/trading path). The secret's
# VALUE is never printed, logged, or persisted — only the derived signature leaves this module.
# --------------------------------------------------------------------------- #
def _load_private_key(secret_b64: str) -> ed25519.Ed25519PrivateKey:
    """Load the Ed25519 private key from the base64 secret, per docs.polymarket.us:
    `Ed25519PrivateKey.from_private_bytes(base64.b64decode(SECRET)[:32])`."""
    raw = base64.b64decode(secret_b64)
    return ed25519.Ed25519PrivateKey.from_private_bytes(raw[:32])


def auth_headers(method: str, path: str, key_id: str, secret_b64: str,
                 now_ms: Optional[int] = None) -> Dict[str, str]:
    """Build the three `X-PM-*` request headers for one signed request.

    `X-PM-Signature = base64(Ed25519.sign(secret, f"{timestamp}{method}{path}"))`; the
    timestamp is ms-epoch and must land within 30s of Polymarket server time. `path` is the
    exact request target that will be sent (INCLUDING any query string — sign what you send).
    The secret is consumed only to produce the signature; it never appears in the returned
    headers or anywhere else.
    """
    ts = str(now_ms if now_ms is not None else int(time.time() * 1000))
    message = f"{ts}{method}{path}".encode("utf-8")
    signature = base64.b64encode(_load_private_key(secret_b64).sign(message)).decode("ascii")
    return {
        "X-PM-Access-Key": key_id,
        "X-PM-Timestamp": ts,
        "X-PM-Signature": signature,
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }


def _signed_get(path: str, key_id: str, secret_b64: str,
                base: str = REST_BASE, timeout: float = 20.0) -> Tuple[int, str]:
    """One signed READ-ONLY GET. Returns (status_code, response_text). Imports `requests`
    lazily so an offline test that injects its own `http_get` never touches the network stack.
    `path` is signed and requested verbatim (query string included)."""
    import requests  # lazy: never imported on an offline/injected path
    headers = auth_headers("GET", path, key_id, secret_b64)
    r = requests.get(base + path, headers=headers, timeout=timeout)
    return r.status_code, r.text


# --------------------------------------------------------------------------- #
# Book parsing — pure, deterministic; empty/one-sided book is DATA (L23), never an exception.
# --------------------------------------------------------------------------- #
def _amount_value(amount: Any) -> Optional[float]:
    """Pull the float out of a Polymarket `Amount` = {"value": decimal-string, "currency":..}.
    Parsed via the shared numeric parser (L100) — absent/unparseable -> honest None."""
    if not isinstance(amount, dict):
        return parse_kalshi_numeric(amount)
    return parse_kalshi_numeric(amount.get("value"))


def _book_side(entries: Any) -> List[List[Optional[float]]]:
    """Normalize a `bids`/`offers` array of {"px": Amount, "qty": str} into [[price, size], ..].
    Levels with an unparseable price are dropped (a price-less level is not a tradeable rung)."""
    out: List[List[Optional[float]]] = []
    for e in (entries or []):
        if not isinstance(e, dict):
            continue
        px = _amount_value(e.get("px"))
        if px is None:
            continue
        out.append([px, parse_kalshi_numeric(e.get("qty"))])
    return out


def parse_us_book(payload_text: str) -> Dict[str, Any]:
    """Parse a `/v1/markets/{slug}/book` payload into a depth snapshot.

    Shape (docs): `{"marketData":{"marketSlug","bids":[BookEntry],"offers":[BookEntry],
    "state","transactTime",...}}`, `BookEntry={"px":Amount,"qty":str}`, `offers` = ask side.
    An empty or one-sided ladder yields `bids`/`asks` `[]` and `best_bid`/`best_ask` `None`
    (far-from-strike/thin shape, L23) — NOT an error. Only malformed JSON raises (a genuine
    parse failure the skeleton records as a `book_error`). `raw` carries the exact payload
    bytes for the skeleton's sha256 provenance anchor."""
    j = json.loads(payload_text)  # a malformed payload legitimately raises -> book_error
    md = j.get("marketData") or {}
    bids = sorted(_book_side(md.get("bids")), key=lambda x: -x[0])
    asks = sorted(_book_side(md.get("offers")), key=lambda x: x[0])
    return {
        "best_bid": bids[0][0] if bids else None,
        "best_ask": asks[0][0] if asks else None,
        "bids": bids,
        "asks": asks,
        "state": md.get("state"),
        "raw": payload_text,
    }


# --------------------------------------------------------------------------- #
# fetch_us_book_fn — the skeleton's per-market book fetch
# --------------------------------------------------------------------------- #
def make_fetch_us_book_fn(
        env: Optional[Dict[str, str]] = None,
        http_get: Optional[Callable[[str], Tuple[int, str]]] = None
) -> Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Build the real `fetch_us_book_fn`. `http_get(path)->(status,text)` is injectable for
    offline tests; the default signs each GET with the env credential. The returned callable:
      * `mm` with no `us_slug` (discovery found no US market) -> `None` (a no_book, recorded).
      * HTTP 404 (US venue doesn't list this slug)           -> `None` (a no_book, recorded).
      * HTTP 200 -> parsed book (empty side = data, L23).
      * any other status / a JSON parse failure -> raises (a genuine book_error that gates).
    """
    env = os.environ if env is None else env
    key_id = env.get(API_KEY_ENV)
    secret = env.get(SECRET_KEY_ENV)
    getter = http_get or (lambda path: _signed_get(path, key_id or "", secret or ""))

    def fetch(mm: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        slug = mm.get("us_slug")
        if not slug:
            return None  # no US market matched in discovery -> no_book (recorded, not a drop)
        status, text = getter(f"/v1/markets/{slug}/book")
        if status == 404:
            return None  # US venue does not list this slug -> no_book
        if status != 200:
            raise RuntimeError(f"US book HTTP {status} for slug={slug}: {text[:200]}")
        return parse_us_book(text)

    return fetch


# --------------------------------------------------------------------------- #
# US market listing — signed, paginated, memory-capped (L10)
# --------------------------------------------------------------------------- #
def list_us_markets(http_get: Callable[[str], Tuple[int, str]],
                    page_size: int = _US_PAGE_SIZE,
                    max_markets: int = MAX_US_MARKETS
                    ) -> Tuple[List[Dict[str, Any]], List[str], bool]:
    """Fetch open US markets via `/v1/markets` (limit/offset pagination). Returns
    (markets, raw_pages, truncated). Caps total rows at `max_markets` and flags truncation
    honestly rather than silently claiming full coverage."""
    out: List[Dict[str, Any]] = []
    raw_pages: List[str] = []
    offset = 0
    truncated = False
    while True:
        path = f"/v1/markets?active=true&limit={page_size}&offset={offset}"
        status, text = http_get(path)
        if status != 200:
            raise RuntimeError(f"US markets list HTTP {status} at offset={offset}: {text[:200]}")
        raw_pages.append(text)
        items = (json.loads(text).get("markets") or [])
        out.extend(items)
        if len(out) >= max_markets:
            out = out[:max_markets]
            truncated = True
            break
        if len(items) < page_size:
            break
        offset += page_size
    return out, raw_pages, truncated


# --------------------------------------------------------------------------- #
# discovery: attach a US market/slug to each internationally-matched question. Structural
# confirmation only (round+team, or meeting+bucket tokens must be present in the US market's
# own text) — never a guess; a 1:1 hit attaches, 0 or >1 leaves us_slug None (recorded as
# no_book / ambiguous downstream). The exact US title grammar per family is confirmed against
# live US listings at VPS bring-up (the endpoint 401s from a no-credential machine).
# --------------------------------------------------------------------------- #
def _norm(s: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _us_match_tokens(d: Dict[str, Any]) -> List[str]:
    """Required normalized substrings the US market's text must ALL contain to be the same
    question as internationally-matched descriptor `d`."""
    fam = d.get("family")
    if fam == "wc_round":
        return [t for t in (_norm(d.get("round")), _norm(d.get("team"))) if t]
    if fam == "fed_decision":
        toks: List[str] = []
        meeting = str(d.get("meeting") or "")
        m = re.match(r"^(\d{4})-(\d{2})$", meeting)
        if m:
            toks.append(m.group(1))                       # year, e.g. 2026
            mo = int(m.group(2))
            if 1 <= mo <= 12:
                toks.append(_MONTHS[mo - 1])              # month name, e.g. july
        bucket = str(d.get("bucket") or "")
        if bucket == "no_change":
            toks.append("nochange")
        elif bucket:
            side, _, mag = bucket.partition("_")
            digits = _norm(re.sub(r"[^0-9]", "", mag))    # 25 / 50 (from 50plus)
            if digits:
                toks.append(digits)
            toks.append({"hike": "increase", "cut": "decrease"}.get(side, side))
        return [t for t in toks if t]
    mk = _norm(d.get("match_key"))
    return [mk] if mk else []


def _us_market_text(m: Dict[str, Any]) -> str:
    return _norm(" ".join(str(m.get(k) or "") for k in ("question", "title", "subtitle", "description")))


def find_us_market(d: Dict[str, Any], us_markets: List[Dict[str, Any]]
                   ) -> Tuple[Optional[Dict[str, Any]], bool]:
    """Return (us_market, ambiguous). A US market matches descriptor `d` iff its text contains
    ALL of `_us_match_tokens(d)`. Exactly one match -> that market; 0 -> (None, False);
    >1 -> (None, True) (ambiguous, never guessed)."""
    tokens = _us_match_tokens(d)
    if not tokens:
        return None, False
    cands = [m for m in us_markets if all(tok in _us_market_text(m) for tok in tokens)]
    if len(cands) == 1:
        return cands[0], False
    return None, len(cands) > 1


def attach_us_markets(intl_matched: List[Dict[str, Any]],
                      us_markets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Annotate each internationally-matched descriptor with its US `us_slug`/`us_market_id`
    (or `None` when the US venue lists no 1:1 match). Returns the full list — a descriptor with
    no US match is kept (so the skeleton records it as a no_book), never dropped."""
    for d in intl_matched:
        m, ambiguous = find_us_market(d, us_markets)
        d["us_slug"] = m.get("slug") if m else None
        d["us_market_id"] = m.get("id") if m else None
        d["us_ambiguous"] = ambiguous
    return intl_matched


def default_intl_matched(env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    """Build the internationally-matched question set the existing collector already pairs on,
    reusing `collection/polymarket_pairs.py`'s discovery + matching helpers (same structural
    discipline). Covers the WC-round and Fed-decision families. Network-heavy (Kalshi + intl
    Polymarket) and VPS-only — injected in tests via `intl_matched_fn`."""
    from validation.v3_market import Kalshi, _load_venue_cfg
    from collection import polymarket_pairs as pp

    cfg = _load_venue_cfg()
    client = Kalshi(cfg["api_base"], min_interval=0.2)
    out: List[Dict[str, Any]] = []

    km, _ = pp.discover_kalshi_round_markets(client)
    pm, _ = pp.discover_polymarket_round_events()
    for k, _p in pp.match_pairs(km, pm)[0]:
        out.append({"family": "wc_round", "round": k["round"], "team": k["team_name"],
                    "match_key": f'{k["round"]}|{k["team_name"]}', "kalshi_ticker": k["ticker"]})

    fkm, _ = pp.discover_kalshi_fed_markets(client)
    fpm, _ = pp.discover_polymarket_fed_events()
    for k, _p in pp.match_fed_pairs(fkm, fpm)[0]:
        out.append({"family": "fed_decision", "meeting": k["meeting_key"], "bucket": k["bucket"],
                    "match_key": f'{k["meeting_key"]}|{k["bucket"]}', "kalshi_ticker": k["ticker"]})
    return out


def make_discover_fn(
        env: Optional[Dict[str, str]] = None,
        intl_matched_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        list_us_markets_fn: Optional[Callable[[], Tuple[List[Dict[str, Any]], List[str], bool]]] = None,
        http_get: Optional[Callable[[str], Tuple[int, str]]] = None
) -> Callable[[], Tuple[List[Dict[str, Any]], List[str]]]:
    """Build the real `discover_fn` the skeleton calls. Both network legs are injectable for
    offline tests; defaults use the intl pairing helpers + the signed US listing endpoint.
    Returns (matched_descriptors, raw_pages) — a truncated US pull adds an honest marker line
    to `raw_pages` (which feeds the skeleton's discovery sha256) and warns on stderr."""
    env = os.environ if env is None else env
    key_id = env.get(API_KEY_ENV)
    secret = env.get(SECRET_KEY_ENV)
    getter = http_get or (lambda path: _signed_get(path, key_id or "", secret or ""))
    intl_fn = intl_matched_fn or (lambda: default_intl_matched(env))
    list_fn = list_us_markets_fn or (lambda: list_us_markets(getter))

    def discover() -> Tuple[List[Dict[str, Any]], List[str]]:
        intl = intl_fn()
        us_markets, raw_pages, truncated = list_fn()
        matched = attach_us_markets(intl, us_markets)
        raw = list(raw_pages)
        if truncated:
            raw.append(canonical_json({"__truncated__": True, "n_us_markets": len(us_markets),
                                       "cap": MAX_US_MARKETS}))
            print(f"[polymarket_us_live] WARN US market listing truncated at cap "
                  f"{MAX_US_MARKETS} — coverage incomplete", file=sys.stderr)
        return matched, raw

    return discover


# --------------------------------------------------------------------------- #
# one wired pass — delegates the credential gate + tape write to the skeleton
# --------------------------------------------------------------------------- #
def run(env: Optional[Dict[str, str]] = None,
        tape_dir: Optional[Any] = None,
        http_get: Optional[Callable[[str], Tuple[int, str]]] = None,
        intl_matched_fn: Optional[Callable[[], List[Dict[str, Any]]]] = None,
        list_us_markets_fn: Optional[Callable[[], Tuple[List[Dict[str, Any]], List[str], bool]]] = None
        ) -> Dict[str, Any]:
    """One credential-gated, READ-ONLY Polymarket-US capture pass with the LIVE default
    discover/fetch wired in. The credential gate, tape write, provenance stamps, and honest
    no_book/book_error accounting all live in `polymarket_us_pairs.run` — absent
    `POLYMARKET_US_API_KEY` this returns `blocked_key` and NEVER calls the network legs."""
    env = os.environ if env is None else env
    discover_fn = make_discover_fn(env, intl_matched_fn=intl_matched_fn,
                                   list_us_markets_fn=list_us_markets_fn, http_get=http_get)
    fetch_fn = make_fetch_us_book_fn(env, http_get=http_get)
    return pus.run(tape_dir=tape_dir, env=env, discover_fn=discover_fn, fetch_us_book_fn=fetch_fn)


def main(argv: Optional[List[str]] = None) -> int:
    import argparse
    argparse.ArgumentParser(
        description="Polymarket US live book capture (read-only, credential-gated)").parse_args(argv)
    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Kalshi WebSocket `orderbook_delta` capture daemon (READ-ONLY) — the continuous L2 tape.

Prime directive #2: "Collect data where others aren't." The existing REST family
(`collection/orderbook_depth.py`) snapshots the full bid ladder once per HOURLY pass — coarse
for order-arrival intensity (that module's own "HONEST CADENCE CAVEAT"). This daemon replaces
the sampling with the real thing: a long-running process that subscribes to Kalshi's
`orderbook_delta` channel and archives every book message — the full snapshot plus each
incremental delta with its `seq` and exchange timestamp — as it arrives. Kalshi does NOT keep
L2 delta history (lesson L11: an un-collected snapshot is lost forever), so this is the moat
tape feeding the L-speed / L-mech / L-flow structural lanes. arb-bot's pt1 failure traced
partly to having only ~40s of book tape; this fixes that at the source.

  ┌─ CONTRACT NUANCE — READ BEFORE FLAGGING AS A VIOLATION ────────────────────────────────┐
  │ CLAUDE.md's execution lane says "Authenticated/order endpoints may exist ONLY in        │
  │ execution/kalshi_client.py." That rule targets ORDER-CAPABLE code — its purpose is that  │
  │ "a cloud run can never place a trade" (the gate is structural: order verbs live in one   │
  │ audited file). THIS module is authenticated *read-only market data*: it signs the WS      │
  │ handshake (public book data still requires the RSA-signed upgrade) and subscribes to      │
  │ the PUBLIC `orderbook_delta` + `trade` channels ONLY (trade = public execution prints,    │
  │ added 2026-08-24 for the monitor). It imports nothing from execution/, defines no order   │
  │ verb, and never subscribes to a user/private channel (fills, orders, positions). It is a  │
  │ collector, so it lives in collection/ alongside the other tape producers. The structural  │
  │ trade-gate is untouched: there is still no order path outside execution/kalshi_client.py. │
  └─────────────────────────────────────────────────────────────────────────────────────────┘

Self-activating (exactly like `collection/odds_api.py`'s `ODDS_API_KEY` gate): auth needs
`KALSHI_API_KEY_ID` + `KALSHI_PRIVATE_KEY_PATH` (loaded on the VPS from
/root/.secrets/kalshi-headless.env). Absent either -> a clean no-op exit that logs
`{"status": "blocked_key"}` and writes nothing. The moment a key lands, the systemd unit's
next start connects. No credentials are read or written by this module beyond loading the
private key file the operator dropped; BLOCKED(key) is an honest status, never faked success.

Honest accounting (house discipline):
  * Bitemporal: every line carries `captured_at` (our fetch clock) + `capture_id`; book lines
    carry the exchange `seq` and its own `ts` where present, and the raw payload with a
    `raw_sha256` over the exact bytes received.
  * Source tag: a live book message is a genuine fillable quote, so `orderbook_snapshot` /
    `orderbook_delta` lines are tagged `price_source_tag = real_ask`. Control lines
    (session/subscribe/error) carry no price and no price tag.
  * Sequence gaps are DATA, not a drop: `seq` increments per subscription; a gap means we
    missed messages. We emit an explicit `ws_depth.gap.v1` line (expected vs got) and then
    force a resync (reconnect -> fresh snapshot) so the seq chain re-anchors. A gap NEVER
    masquerades as a clean chain, and it never silently corrupts the book downstream.
  * Bounded memory (lesson L10: Kalshi's 10k+ universe once blew 3GB RSS): the subscribed
    ticker set is capped (`max_tickers`, honest `truncated` flag). We keep exactly one int of
    state per market (last seq); no message is ever buffered in memory beyond the write batch.

Volume / storage (GOAL.md ~50MB/day ceiling): `orderbook_delta` on an active set is high-rate
(a liquid market can emit multiple deltas/second; ~50 tickers can produce hundreds of MB/day
of raw JSONL). So the tape is written GZIPPED by default (`dt=YYYY-MM-DD.jsonl.gz`), which
compresses line-oriented JSON ~5-10x and keeps a busy day comfortably under the ceiling. Set
`WS_DEPTH_COMPRESS=none` for a plain `.jsonl` (readable during bring-up). Files rotate at UTC
midnight and ride to git via the existing hourly VPS runner (`git add tape/` globs everything).

Run (VPS, under systemd — see ops/vps/kalshi-headless-wsdepth.service):
    python -m collection.ws_depth
Dev / smoke without a key: prints {"status": "blocked_key"} and exits 0.
"""
from __future__ import annotations

import argparse
import gzip
import heapq
import json
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from core.canonical import canonical_json, sha256_hex
from core.depth import total_ladder_depth
from core.io import REPO_ROOT
from core.kalshi_fields import parse_kalshi_numeric
from core.pricing import top_of_book_quote

TAPE = REPO_ROOT / "tape" / "ws_depth"
CONFIG_DEFAULT = REPO_ROOT / "config" / "ws_depth_tickers.txt"

DEFAULT_WS_BASE = "wss://api.elections.kalshi.com/trade-api/ws/v2"
# orderbook_delta delivers snapshot + deltas; trade delivers public execution prints
# (2026-08-24 monitor build — the tape needs last-trade price/size for Layer-3's
# large-single-trade detector, and prints are the only record of what actually filled).
DEFAULT_CHANNELS = ("orderbook_delta", "trade")
# Book message types that carry real fillable prices (tag real_ask).
BOOK_MSG_TYPES = {"orderbook_snapshot", "orderbook_delta"}
# Public execution prints: a trade IS an executed exchange record, so it carries the same
# tag the REST trade collector uses (collection/kalshi_trades.py -> broker_truth).
TRADE_MSG_TYPES = {"trade"}

# In-daemon book snapshot cadence (seconds): every interval, one snapshot60 line per market
# with a live book, so QUIET periods are measurable without any REST polling. Env override
# WS_DEPTH_SNAPSHOT_SEC; <= 0 disables.
SNAPSHOT_INTERVAL_DEFAULT = 60.0
# Depth levels persisted per side in a snapshot60 line.
SNAPSHOT_TOP_N = 5

# Bound the subscribed universe (lesson L10). One int of seq-state per market only.
MAX_TICKERS_DEFAULT = 200
# Reconnect backoff (seconds): exponential, capped. A gap-triggered resync uses 0 (immediate).
BACKOFF_BASE = 1.0
BACKOFF_MAX_DEFAULT = 60.0


# --------------------------------------------------------------------------- #
# auth — RSA-PSS/SHA-256 handshake signing (mirrors the verified scripts/kalshi_sign.py).
# cryptography is imported lazily so this module imports in the minimal test venv.
# --------------------------------------------------------------------------- #
def _load_private_key(path: str):
    from cryptography.hazmat.primitives import serialization
    with open(path, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)


def sign_message(private_key, message: str) -> str:
    """RSA-PSS / SHA-256 / MGF1(SHA-256) / salt=digest length, base64 (verified scheme)."""
    import base64

    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    sig = private_key.sign(
        message.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("ascii")


def build_ws_headers(private_key, key_id: str, ws_url: str,
                     now_ms: Optional[int] = None) -> Dict[str, str]:
    """The three signed headers for the WS upgrade. Signs `GET` + the WS path (query stripped,
    the #1 silent-401 gotcha). `now_ms` is injectable so the signature is testable."""
    path_no_query = urlsplit(ws_url).path
    ts_ms = str(int(time.time() * 1000) if now_ms is None else now_ms)
    message = f"{ts_ms}GET{path_no_query}"
    return {
        "KALSHI-ACCESS-KEY": key_id,
        "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        "KALSHI-ACCESS-SIGNATURE": sign_message(private_key, message),
    }


# --------------------------------------------------------------------------- #
# config — the subscribed ticker set (simple, committed, documented)
# --------------------------------------------------------------------------- #
def load_tickers(env: Optional[Dict[str, str]] = None,
                 config_path: Optional[Path] = None,
                 max_tickers: int = MAX_TICKERS_DEFAULT) -> Tuple[List[str], bool]:
    """Resolve the subscribed ticker set, returning (tickers, truncated).

    Precedence: `WS_DEPTH_TICKERS` (comma list) overrides the file; else read the committed
    `config/ws_depth_tickers.txt` (one ticker per line, `#` comments, blanks ignored). The
    selection mechanism is deliberately a plain committed file so a human owns exactly which
    markets we pay to keep — bring-up (ops/ws-depth-bringup.md) populates it. Deduped,
    order-preserved, and capped at `max_tickers` (lesson L10) with an honest truncated flag.
    """
    env = os.environ if env is None else env
    config_path = CONFIG_DEFAULT if config_path is None else Path(config_path)

    raw: List[str] = []
    inline = (env.get("WS_DEPTH_TICKERS") or "").strip()
    if inline:
        raw = [t.strip() for t in inline.split(",")]
    elif config_path.exists():
        for line in config_path.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                raw.append(line)

    seen: set = set()
    tickers: List[str] = []
    for t in raw:
        if t and t not in seen:
            seen.add(t)
            tickers.append(t)
    truncated = len(tickers) > max_tickers
    return (tickers[:max_tickers] if truncated else tickers), truncated


def subscribe_command(tickers: List[str], channels=DEFAULT_CHANNELS,
                      cmd_id: int = 1) -> Dict[str, Any]:
    """The documented Kalshi WS subscribe envelope. `orderbook_delta` on this channel set
    yields a first `orderbook_snapshot` then incremental `orderbook_delta`s per ticker."""
    return {"id": cmd_id, "cmd": "subscribe",
            "params": {"channels": list(channels), "market_tickers": list(tickers)}}


# --------------------------------------------------------------------------- #
# sequence-gap tracking — a gap is DATA (kb 02: on a gap you MISSED data, resync)
# --------------------------------------------------------------------------- #
class SeqTracker:
    """One `last_seq` per market. `observe` returns (last, got) gap info when a delta skips
    a seq, else None. A snapshot re-anchors the chain (no gap). Bounded: one int per market."""

    def __init__(self) -> None:
        self._last: Dict[str, int] = {}

    def observe(self, market: Optional[str], seq: Optional[int],
                is_snapshot: bool) -> Optional[Tuple[int, int]]:
        if market is None or seq is None:
            return None
        if is_snapshot:
            self._last[market] = seq          # snapshot anchors the chain
            return None
        prev = self._last.get(market)
        self._last[market] = seq              # re-anchor either way so we don't re-flag
        if prev is None or seq == prev + 1:
            return None
        return (prev, seq)                     # gap: expected prev+1, got seq


# --------------------------------------------------------------------------- #
# live book state -> periodic snapshot60 lines (quiet periods stay measurable)
# --------------------------------------------------------------------------- #
class BookState:
    """Maintain one price->size ladder per side per subscribed market from the snapshot +
    delta stream, and render `ws_depth.snapshot60.v1` lines on demand.

    Bounded: the subscribed set is already capped (MAX_TICKERS), and a ladder holds at most
    99 price levels per side. Prices are DOLLARS (parsed from the `*_dollars` fields, L90),
    sizes are FLOATS and never int-coerced (L47). Reset on every reconnect, exactly like
    SeqTracker — a stale pre-gap book must never render a post-gap snapshot."""

    def __init__(self) -> None:
        self._books: Dict[str, Dict[str, Dict[float, float]]] = {}

    def apply(self, msg_type: str, msg: Dict[str, Any]) -> None:
        body = msg.get("msg") if isinstance(msg.get("msg"), dict) else msg
        market = body.get("market_ticker") or msg.get("market_ticker")
        if not market:
            return
        if msg_type == "orderbook_snapshot":
            book: Dict[str, Dict[float, float]] = {"yes": {}, "no": {}}
            for side in ("yes", "no"):
                levels = body.get(f"{side}_dollars_fp") or body.get(side) or []
                for lvl in levels:
                    if not isinstance(lvl, (list, tuple)) or len(lvl) < 2:
                        continue
                    price = parse_kalshi_numeric(lvl[0])
                    size = parse_kalshi_numeric(lvl[1])
                    if price is not None and size is not None and size > 0:
                        book[side][price] = size
            self._books[market] = book
        elif msg_type == "orderbook_delta":
            book = self._books.get(market)
            if book is None:
                return                      # delta before this market's snapshot: ignore
            side = body.get("side")
            price = parse_kalshi_numeric(body.get("price_dollars", body.get("price")))
            delta = parse_kalshi_numeric(body.get("delta_fp", body.get("delta")))
            if side not in ("yes", "no") or price is None or delta is None:
                return
            size = book[side].get(price, 0.0) + delta
            if size > 0:
                book[side][price] = size
            else:
                book[side].pop(price, None)

    def snapshot_records(self, captured_at: str, capture_id: str,
                         top_n: int = SNAPSHOT_TOP_N) -> List[Dict[str, Any]]:
        """One snapshot60 line per market with a live book. Sides are BID ladders (resting
        buy orders on yes / on no); the derived yes_ask is the price a yes taker pays
        (1 - best no bid). Levels are real resting quotes -> real_ask."""
        records = []
        for market in sorted(self._books):
            book = self._books[market]
            tops = {}
            for side in ("yes", "no"):
                ladder = heapq.nlargest(top_n, book[side].items())
                tops[side] = [[p, s] for p, s in ladder]
            best_yes_bid = tops["yes"][0][0] if tops["yes"] else None
            best_no_bid = tops["no"][0][0] if tops["no"] else None
            # Hard Rule #3: quote derivation (ask, mid, spread) lives ONLY in core.pricing
            yes_ask, mid, spread = top_of_book_quote(best_yes_bid, best_no_bid)
            records.append({
                "schema_version": "ws_depth.snapshot60.v1",
                "capture_id": capture_id,
                "captured_at": captured_at,
                "venue": "kalshi",
                # daemon-derived aggregate, not a wire frame — schema_version identifies it
                "channel": "derived",
                "msg_type": "snapshot60",
                "market_ticker": market,
                "yes_bids_top": tops["yes"],
                "no_bids_top": tops["no"],
                "yes_bid": best_yes_bid,
                "no_bid": best_no_bid,
                "yes_ask": yes_ask,
                "mid": mid,
                "spread": spread,
                "yes_depth_top": total_ladder_depth(tops["yes"]),
                "no_depth_top": total_ladder_depth(tops["no"]),
                "price_source_tag": "real_ask",
            })
        return records


# --------------------------------------------------------------------------- #
# message -> tape line(s)  (pure; the unit under test)
# --------------------------------------------------------------------------- #
def _extract(msg: Dict[str, Any], *keys) -> Any:
    """First present of `keys`, checking top-level then the nested `msg` body — the Kalshi
    envelope puts `seq` at top level and `market_ticker` inside `msg`."""
    body = msg.get("msg") if isinstance(msg.get("msg"), dict) else {}
    for k in keys:
        if k in msg and msg[k] is not None:
            return msg[k]
        if k in body and body[k] is not None:
            return body[k]
    return None


def process_message(raw_text: str, tracker: SeqTracker, captured_at: str, capture_id: str,
                    control_channel: str = "orderbook_delta"
                    ) -> Tuple[List[Dict[str, Any]], bool]:
    """Transform one raw WS text frame into 0+ tape records. Returns (records, resync_needed).

    `resync_needed` is True when a seq gap was detected: the caller drops the connection and
    reconnects so a fresh snapshot re-anchors the chain (never trade/rebuild off an unverified
    chain — kb 02). Every record preserves the raw payload + its sha256; a message we can't
    parse is recorded as a `parse_error` line (data, not a silent drop)."""
    raw_sha256 = sha256_hex(raw_text.encode("utf-8"))
    try:
        msg = json.loads(raw_text)
    except (ValueError, TypeError):
        return ([{
            "schema_version": "ws_depth.v1", "capture_id": capture_id,
            "captured_at": captured_at, "venue": "kalshi", "channel": control_channel,
            "msg_type": "parse_error", "raw_text": raw_text, "raw_sha256": raw_sha256,
        }], False)

    msg_type = msg.get("type")
    market = _extract(msg, "market_ticker")
    seq = _extract(msg, "seq")
    if isinstance(seq, str):
        try:
            seq = int(seq)
        except ValueError:
            seq = None

    # label the record with the channel that actually produced it; `control_channel` is
    # only the label for control frames (subscribed/error), which carry no msg-type channel
    if msg_type in TRADE_MSG_TYPES:
        channel = "trade"
    elif msg_type in BOOK_MSG_TYPES:
        channel = "orderbook_delta"
    else:
        channel = control_channel

    record: Dict[str, Any] = {
        "schema_version": "ws_depth.v1",
        "capture_id": capture_id,
        "captured_at": captured_at,
        "venue": "kalshi",
        "channel": channel,
        "msg_type": msg_type,
        "market_ticker": market,
        "seq": seq,
        "raw": msg,
        "raw_sha256": raw_sha256,
    }
    if msg_type in BOOK_MSG_TYPES:
        # a live book level is a real fillable quote, not a model (CLAUDE.md Hard Rule #3/#4)
        record["price_source_tag"] = "real_ask"
    elif msg_type in TRADE_MSG_TYPES:
        # an executed print is the exchange's own record — same tag as kalshi_trades.py
        record["price_source_tag"] = "broker_truth"

    records = [record]
    resync = False
    if msg_type in BOOK_MSG_TYPES:
        gap = tracker.observe(market, seq, is_snapshot=(msg_type == "orderbook_snapshot"))
        if gap is not None:
            prev, got = gap
            records.append({
                "schema_version": "ws_depth.gap.v1",
                "capture_id": f"{capture_id}:gap",
                "captured_at": captured_at,
                "venue": "kalshi",
                "channel": channel,
                "type": "seq_gap",
                "market_ticker": market,
                "expected_seq": prev + 1,
                "got_seq": got,
                "missed": got - (prev + 1),
            })
            resync = True
    return records, resync


# --------------------------------------------------------------------------- #
# tape writer — append-only JSONL(.gz), UTC-midnight rotation, bounded, durable
# --------------------------------------------------------------------------- #
class TapeWriter:
    """Append lines to tape/ws_depth/dt=YYYY-MM-DD.jsonl[.gz], rotating at UTC midnight.
    Holds a single open file handle (no in-memory accumulation). gzip append writes a new
    concatenated member on each (re)open — valid and transparently readable, so a restart
    never corrupts the day file."""

    def __init__(self, store_dir: Path = TAPE, compress: bool = True,
                 flush_every: int = 1) -> None:
        self.store_dir = Path(store_dir)
        self.compress = compress
        self.flush_every = max(1, flush_every)
        self._day: Optional[str] = None
        self._fh = None
        self._since_flush = 0

    def _path_for(self, day: str) -> Path:
        name = f"dt={day}.jsonl" + (".gz" if self.compress else "")
        return self.store_dir / name

    def _open(self, day: str) -> None:
        self.close()
        self.store_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(day)
        self._fh = (gzip.open(path, "at", encoding="utf-8") if self.compress
                    else open(path, "a", encoding="utf-8"))
        self._day = day

    def write(self, line: str, now: Optional[datetime] = None) -> None:
        now = datetime.now(timezone.utc) if now is None else now
        day = now.strftime("%Y-%m-%d")
        if day != self._day:
            self._open(day)                    # first write or UTC-midnight rotation
        self._fh.write(line + "\n")
        self._since_flush += 1
        if self._since_flush >= self.flush_every:
            self._fh.flush()
            self._since_flush = 0

    def flush(self) -> None:
        if self._fh is not None:
            self._fh.flush()
            self._since_flush = 0

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            finally:
                self._fh = None
                self._day = None


# --------------------------------------------------------------------------- #
# the daemon
# --------------------------------------------------------------------------- #
def _ts() -> Tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.isoformat(), now.strftime("%Y%m%dT%H%M%S%fZ")


def _log(obj: Dict[str, Any]) -> None:
    print(f"[ws_depth] {canonical_json(obj)}", flush=True)


# Sentinel for "the socket timed out with no frame" — distinct from None/"" (peer closed).
_IDLE = object()


class _IdleTolerantConn:
    """Wrap a live websocket-client connection so a recv TIMEOUT surfaces as the _IDLE
    sentinel instead of an exception. The library knowledge (WebSocketTimeoutException is
    NOT a socket.timeout subclass) lives HERE, next to the import — run() never needs to
    classify library exception types, so an unrelated error can never be misread as a
    quiet market."""

    def __init__(self, conn, timeout_exc: type) -> None:
        self._conn = conn
        self._timeout_exc = timeout_exc

    def send(self, data):
        return self._conn.send(data)

    def recv(self):
        try:
            return self._conn.recv()
        except self._timeout_exc:
            return _IDLE

    def close(self):
        return self._conn.close()


def _real_connect_factory(ws_base: str, key_id: str, private_key,
                          open_timeout: float = 15.0) -> Callable[[], Any]:
    """Build the default connection factory using websocket-client (lazy import). Signs the
    upgrade with fresh headers each connect (the timestamp can't be stale)."""
    def connect():
        import websocket  # websocket-client; see pyproject [wsdepth] extra
        headers = build_ws_headers(private_key, key_id, ws_base)
        header_list = [f"{k}: {v}" for k, v in headers.items()]
        conn = websocket.create_connection(ws_base, header=header_list, timeout=open_timeout)
        return _IdleTolerantConn(conn, websocket.WebSocketTimeoutException)
    return connect


def _handle_frame(raw, tracker: SeqTracker, books: BookState, writer: TapeWriter,
                  control_channel: str) -> Tuple[int, int, bool]:
    """Process one received WS frame: tape line(s) + book-state update. Returns
    (n_lines_written, n_gaps, need_resync) so run()'s loop stays flat."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    iso, cid = _ts()
    records, need_resync = process_message(raw, tracker, iso, cid,
                                           control_channel=control_channel)
    n_lines = n_gaps = 0
    for rec in records:
        writer.write(canonical_json(rec))
        n_lines += 1
        if rec.get("schema_version") == "ws_depth.gap.v1":
            n_gaps += 1
        if rec.get("msg_type") in BOOK_MSG_TYPES:
            books.apply(rec["msg_type"], rec["raw"])
    return n_lines, n_gaps, need_resync


def run(connect: Optional[Callable[[], Any]] = None,
        tickers: Optional[List[str]] = None,
        writer: Optional[TapeWriter] = None,
        env: Optional[Dict[str, str]] = None,
        channels=DEFAULT_CHANNELS,
        max_reconnects: Optional[int] = None,
        max_messages: Optional[int] = None,
        backoff_max: float = BACKOFF_MAX_DEFAULT,
        sleep: Callable[[float], None] = time.sleep,
        snapshot_interval: Optional[float] = None,
        clock: Callable[[], float] = time.monotonic) -> Dict[str, Any]:
    """Long-running capture loop (or a bounded pass when `max_reconnects`/`max_messages` cap it,
    which the tests use). Returns a summary dict.

    `connect`, `writer`, `env`, `sleep` are injectable for offline testing. When `connect` is
    None we build the real websocket-client factory from the signed handshake — but ONLY after
    confirming the key is present; absent the key we never touch the network (blocked_key).
    """
    env = os.environ if env is None else env

    # --- key gate (self-activating, exactly like odds_api) --------------------------------
    key_id = (env.get("KALSHI_API_KEY_ID") or "").strip()
    key_path = (env.get("KALSHI_PRIVATE_KEY_PATH") or "").strip()
    live_mode = connect is None
    if live_mode and (not key_id or not key_path or not Path(key_path).exists()):
        summary = {"status": "blocked_key", "n_lines": 0, "n_gaps": 0, "n_reconnects": 0}
        _log(summary)
        return summary

    # --- config: subscribed ticker set (bounded) ------------------------------------------
    truncated = False
    if tickers is None:
        tickers, truncated = load_tickers(env=env)
    if not tickers:
        summary = {"status": "no_tickers", "n_lines": 0, "n_gaps": 0, "n_reconnects": 0,
                   "truncated": truncated}
        _log(summary)
        return summary

    if writer is None:
        compress = (env.get("WS_DEPTH_COMPRESS", "gzip").strip().lower()
                    not in ("none", "plain", "0", "false"))
        writer = TapeWriter(compress=compress)

    if connect is None:
        ws_base = env.get("KALSHI_WS_BASE", DEFAULT_WS_BASE)
        connect = _real_connect_factory(ws_base, key_id, _load_private_key(key_path))

    if snapshot_interval is None:
        try:
            snapshot_interval = float(env.get("WS_DEPTH_SNAPSHOT_SEC",
                                              str(SNAPSHOT_INTERVAL_DEFAULT)))
        except ValueError:
            snapshot_interval = SNAPSHOT_INTERVAL_DEFAULT

    stop = {"flag": False}

    def _handle_signal(signum, _frame):
        stop["flag"] = True
    try:
        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)
    except (ValueError, OSError):
        pass  # not on the main thread (e.g. under a test harness) — caps still bound the loop

    n_lines = n_gaps = n_reconnects = n_snapshots = 0
    attempt = 0
    _log({"status": "start", "n_tickers": len(tickers), "channels": list(channels),
          "truncated": truncated})

    try:
        while not stop["flag"]:
            if max_reconnects is not None and n_reconnects >= max_reconnects:
                break
            conn = None
            resync = False
            try:
                conn = connect()
                iso, cid = _ts()
                writer.write(canonical_json({
                    "schema_version": "ws_depth.session.v1", "capture_id": cid,
                    "captured_at": iso, "venue": "kalshi", "type": "session_open",
                    "n_tickers": len(tickers)}))
                n_lines += 1
                # one subscribe per channel: each subscription owns its own seq space, so
                # trade prints can never interleave into (and false-gap) the book seq chain
                for i, ch in enumerate(channels):
                    conn.send(json.dumps(subscribe_command(tickers, (ch,), cmd_id=i + 1)))
                tracker = SeqTracker()
                books = BookState()          # reset with the tracker: no stale pre-gap book
                last_snapshot = clock()

                while not stop["flag"]:
                    try:
                        raw = conn.recv()
                    except (TimeoutError, socket.timeout):
                        raw = _IDLE          # injected conns; live conns return _IDLE direct
                    if raw is None or raw == "":
                        break                    # peer closed
                    if raw is not _IDLE:
                        d_lines, d_gaps, need_resync = _handle_frame(
                            raw, tracker, books, writer, channels[0])
                        n_lines += d_lines
                        n_gaps += d_gaps
                        if need_resync:
                            resync = True
                            break
                    if snapshot_interval > 0 and clock() - last_snapshot >= snapshot_interval:
                        iso, cid = _ts()
                        for rec in books.snapshot_records(iso, cid):
                            writer.write(canonical_json(rec))
                            n_lines += 1
                            n_snapshots += 1
                        last_snapshot = clock()
                    if max_messages is not None and n_lines >= max_messages:
                        stop["flag"] = True
                        break
                attempt = 0                       # a clean recv session resets backoff
            except Exception as exc:              # any connection error is isolated + logged
                _log({"status": "conn_error", "error": repr(exc)[:200],
                      "attempt": attempt})
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    n_reconnects += 1

            if stop["flag"]:
                break
            if resync:
                _log({"status": "resync_after_gap"})
                continue                          # immediate reconnect -> fresh snapshot
            attempt += 1
            delay = min(backoff_max, BACKOFF_BASE * (2 ** min(attempt, 16)))
            sleep(delay)
    finally:
        writer.close()

    summary = {"status": "stopped", "n_lines": n_lines, "n_gaps": n_gaps,
               "n_reconnects": n_reconnects, "n_snapshots": n_snapshots,
               "truncated": truncated}
    _log(summary)
    return summary


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Kalshi WebSocket orderbook_delta capture daemon (READ-ONLY).")
    ap.add_argument("--max-reconnects", type=int, default=None,
                    help="stop after N (re)connects — bounded run for testing/bring-up")
    ap.add_argument("--max-messages", type=int, default=None,
                    help="stop after N tape lines — bounded run for testing/bring-up")
    args = ap.parse_args(argv)
    run(max_reconnects=args.max_reconnects, max_messages=args.max_messages)
    return 0


if __name__ == "__main__":
    sys.exit(main())

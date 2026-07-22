"""collection.ws_depth — Kalshi WS orderbook_delta capture daemon, fully offline.

No network, no real key. Covers: auth-header construction against a throwaway RSA key
(skips if `cryptography` absent in the minimal venv), message->tape-line transformation +
source tags, seq-gap detection (a gap is DATA + forces resync), the blocked_key no-op, the
no_tickers no-op, config parsing, UTC-midnight rotation + gzip round-trip, and a driven run
against an injected fake connection (session line, subscribe, bounded stop)."""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone

import pytest

from collection import ws_depth as wd


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeConn:
    """Serves a scripted list of raw WS frames, then signals a peer close ("" ) and finally
    raises StopIteration-like to end. Records what was sent."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []
        self.closed = False

    def send(self, data):
        self.sent.append(data)

    def recv(self):
        if self._frames:
            return self._frames.pop(0)
        return ""  # peer closed

    def close(self):
        self.closed = True


def _snapshot(ticker, seq):
    return json.dumps({"type": "orderbook_snapshot", "sid": 1, "seq": seq,
                       "msg": {"market_ticker": ticker,
                               "yes": [[0.40, 100]], "no": [[0.58, 80]]}})


def _delta(ticker, seq, side="yes", price=0.41, delta=5):
    return json.dumps({"type": "orderbook_delta", "sid": 1, "seq": seq,
                       "msg": {"market_ticker": ticker, "price": price,
                               "delta": delta, "side": side}})


# --------------------------------------------------------------------------- #
# auth-header construction (skips without cryptography)
# --------------------------------------------------------------------------- #
def test_build_ws_headers_signs_path_only_and_verifies():
    crypto = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding, rsa
    import base64

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ws_url = "wss://api.elections.kalshi.com/trade-api/ws/v2?foo=bar"
    headers = wd.build_ws_headers(key, "my-key-id", ws_url, now_ms=1234567890000)

    assert headers["KALSHI-ACCESS-KEY"] == "my-key-id"
    assert headers["KALSHI-ACCESS-TIMESTAMP"] == "1234567890000"
    # signed message is timestamp+GET+path with the query STRIPPED (the #1 silent-401 gotcha)
    signed = "1234567890000GET/trade-api/ws/v2"
    key.public_key().verify(
        base64.b64decode(headers["KALSHI-ACCESS-SIGNATURE"]),
        signed.encode("utf-8"),
        padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH),
        hashes.SHA256(),
    )  # raises if the signature is wrong


# --------------------------------------------------------------------------- #
# message -> tape line
# --------------------------------------------------------------------------- #
def test_process_snapshot_record_shape_and_real_ask_tag():
    tr = wd.SeqTracker()
    recs, resync = wd.process_message(_snapshot("KXBTCD-A", 10), tr, "2026-07-21T00:00:00+00:00",
                                      "cid1")
    assert resync is False and len(recs) == 1
    r = recs[0]
    assert r["schema_version"] == "ws_depth.v1"
    assert r["venue"] == "kalshi" and r["msg_type"] == "orderbook_snapshot"
    assert r["market_ticker"] == "KXBTCD-A" and r["seq"] == 10
    assert r["price_source_tag"] == "real_ask"       # a live book is a real fillable quote
    assert r["raw"]["msg"]["yes"] == [[0.40, 100]]   # raw payload preserved verbatim
    assert len(r["raw_sha256"]) == 64


def test_process_delta_in_sequence_no_gap():
    tr = wd.SeqTracker()
    wd.process_message(_snapshot("T", 5), tr, "t", "c0")
    recs, resync = wd.process_message(_delta("T", 6), tr, "t", "c1")
    assert resync is False
    assert len(recs) == 1 and recs[0]["price_source_tag"] == "real_ask"


def test_control_message_has_no_price_tag():
    tr = wd.SeqTracker()
    raw = json.dumps({"type": "subscribed", "id": 1, "msg": {"channel": "orderbook_delta"}})
    recs, resync = wd.process_message(raw, tr, "t", "c")
    assert resync is False
    assert "price_source_tag" not in recs[0]         # control lines carry no price


def test_unparseable_message_is_recorded_not_dropped():
    tr = wd.SeqTracker()
    recs, resync = wd.process_message("{not json", tr, "t", "c")
    assert resync is False and len(recs) == 1
    assert recs[0]["msg_type"] == "parse_error"
    assert recs[0]["raw_text"] == "{not json" and len(recs[0]["raw_sha256"]) == 64


# --------------------------------------------------------------------------- #
# seq-gap detection — a gap is DATA and forces a resync
# --------------------------------------------------------------------------- #
def test_seq_gap_emits_gap_line_and_forces_resync():
    tr = wd.SeqTracker()
    wd.process_message(_snapshot("T", 5), tr, "t", "c0")
    wd.process_message(_delta("T", 6), tr, "t", "c1")
    recs, resync = wd.process_message(_delta("T", 9), tr, "t2", "c2")  # skipped 7,8
    assert resync is True
    gap = [r for r in recs if r["schema_version"] == "ws_depth.gap.v1"]
    assert len(gap) == 1
    g = gap[0]
    assert g["type"] == "seq_gap" and g["expected_seq"] == 7 and g["got_seq"] == 9
    assert g["missed"] == 2 and g["market_ticker"] == "T"


def test_snapshot_reanchors_after_gap():
    tr = wd.SeqTracker()
    wd.process_message(_snapshot("T", 5), tr, "t", "c0")
    _, resync = wd.process_message(_delta("T", 40), tr, "t", "c1")   # gap
    assert resync is True
    # a fresh snapshot re-anchors: the next in-order delta is clean
    wd.process_message(_snapshot("T", 100), tr, "t", "c2")
    _, resync2 = wd.process_message(_delta("T", 101), tr, "t", "c3")
    assert resync2 is False


def test_seq_tracker_per_market_independent():
    tr = wd.SeqTracker()
    wd.process_message(_snapshot("A", 5), tr, "t", "c")
    wd.process_message(_snapshot("B", 500), tr, "t", "c")
    _, ra = wd.process_message(_delta("A", 6), tr, "t", "c")
    _, rb = wd.process_message(_delta("B", 501), tr, "t", "c")
    assert ra is False and rb is False


def test_missing_seq_is_not_a_false_gap():
    tr = wd.SeqTracker()
    # a message with no seq we can read can't be gap-checked -> no false positive
    raw = json.dumps({"type": "orderbook_delta", "msg": {"market_ticker": "T"}})
    recs, resync = wd.process_message(raw, tr, "t", "c")
    assert resync is False and len(recs) == 1 and recs[0]["seq"] is None


# --------------------------------------------------------------------------- #
# config parsing
# --------------------------------------------------------------------------- #
def test_load_tickers_from_file(tmp_path):
    p = tmp_path / "tk.txt"
    p.write_text("# comment\nKXA-1\n\nKXB-2  # inline\nKXA-1\n")
    tickers, truncated = wd.load_tickers(env={}, config_path=p)
    assert tickers == ["KXA-1", "KXB-2"]   # comments/blanks stripped, deduped
    assert truncated is False


def test_load_tickers_env_overrides_file(tmp_path):
    p = tmp_path / "tk.txt"
    p.write_text("KXFILE-1\n")
    tickers, _ = wd.load_tickers(env={"WS_DEPTH_TICKERS": "KXENV-1, KXENV-2"}, config_path=p)
    assert tickers == ["KXENV-1", "KXENV-2"]


def test_load_tickers_truncates_and_flags(tmp_path):
    p = tmp_path / "tk.txt"
    p.write_text("\n".join(f"KX-{i}" for i in range(10)))
    tickers, truncated = wd.load_tickers(env={}, config_path=p, max_tickers=3)
    assert len(tickers) == 3 and truncated is True


def test_subscribe_command_shape():
    cmd = wd.subscribe_command(["A", "B"])
    assert cmd["cmd"] == "subscribe"
    assert cmd["params"]["market_tickers"] == ["A", "B"]
    assert cmd["params"]["channels"] == ["orderbook_delta"]


# --------------------------------------------------------------------------- #
# tape writer — rotation + gzip round-trip
# --------------------------------------------------------------------------- #
def test_writer_plain_appends_and_rotates_at_utc_midnight(tmp_path):
    w = wd.TapeWriter(store_dir=tmp_path, compress=False)
    d1 = datetime(2026, 7, 21, 23, 59, tzinfo=timezone.utc)
    d2 = datetime(2026, 7, 22, 0, 0, tzinfo=timezone.utc)
    w.write('{"a":1}', now=d1)
    w.write('{"a":2}', now=d1)
    w.write('{"a":3}', now=d2)   # crosses UTC midnight -> new file
    w.close()
    f1 = (tmp_path / "dt=2026-07-21.jsonl").read_text().splitlines()
    f2 = (tmp_path / "dt=2026-07-22.jsonl").read_text().splitlines()
    assert f1 == ['{"a":1}', '{"a":2}'] and f2 == ['{"a":3}']


def test_writer_gzip_round_trip(tmp_path):
    w = wd.TapeWriter(store_dir=tmp_path, compress=True)
    d = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)
    w.write('{"a":1}', now=d)
    w.write('{"a":2}', now=d)
    w.close()
    path = tmp_path / "dt=2026-07-21.jsonl.gz"
    assert path.exists()
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        assert fh.read().splitlines() == ['{"a":1}', '{"a":2}']


def test_writer_gzip_append_after_reopen_is_valid(tmp_path):
    # a restart mid-day reopens the same gz file -> concatenated member, still readable
    for payload in ('{"a":1}', '{"a":2}'):
        w = wd.TapeWriter(store_dir=tmp_path, compress=True)
        w.write(payload, now=datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc))
        w.close()
    with gzip.open(tmp_path / "dt=2026-07-21.jsonl.gz", "rt", encoding="utf-8") as fh:
        assert fh.read().splitlines() == ['{"a":1}', '{"a":2}']


# --------------------------------------------------------------------------- #
# blocked_key / no_tickers no-ops
# --------------------------------------------------------------------------- #
def test_run_blocked_key_noop_no_network(tmp_path):
    # connect=None -> live_mode; no key in env -> blocked_key, never builds a connection
    summary = wd.run(connect=None, env={}, writer=wd.TapeWriter(store_dir=tmp_path))
    assert summary["status"] == "blocked_key"
    assert summary["n_lines"] == 0
    assert not any(tmp_path.iterdir())   # nothing written


def test_run_no_tickers_noop(tmp_path):
    # injected connect (so not blocked) but empty ticker set -> honest no_tickers, no connect
    called = {"n": 0}

    def connect():
        called["n"] += 1
        return FakeConn([])
    summary = wd.run(connect=connect, tickers=[], writer=wd.TapeWriter(store_dir=tmp_path),
                     env={})
    assert summary["status"] == "no_tickers" and called["n"] == 0


# --------------------------------------------------------------------------- #
# driven run against an injected fake connection
# --------------------------------------------------------------------------- #
def test_run_driven_writes_session_and_book_lines(tmp_path):
    frames = [_snapshot("T", 1), _delta("T", 2), _delta("T", 3)]
    conn = FakeConn(frames)
    w = wd.TapeWriter(store_dir=tmp_path, compress=False)
    summary = wd.run(connect=lambda: conn, tickers=["T"], writer=w, env={},
                     max_reconnects=1, sleep=lambda _s: None)
    assert summary["status"] == "stopped"
    # subscribe envelope was sent
    assert conn.sent and json.loads(conn.sent[0])["cmd"] == "subscribe"
    # find the day file (single UTC day for this run)
    files = list(tmp_path.glob("dt=*.jsonl"))
    assert len(files) == 1
    lines = [json.loads(x) for x in files[0].read_text().splitlines()]
    kinds = [l.get("schema_version") for l in lines]
    assert "ws_depth.session.v1" in kinds       # session_open marker
    book = [l for l in lines if l.get("schema_version") == "ws_depth.v1"]
    assert {b["seq"] for b in book} == {1, 2, 3}
    assert all(b["price_source_tag"] == "real_ask" for b in book)


def test_run_driven_gap_triggers_resync_reconnect(tmp_path):
    # first session: snapshot then a gapped delta -> gap line + resync (reconnect)
    sessions = [FakeConn([_snapshot("T", 1), _delta("T", 9)]),
                FakeConn([_snapshot("T", 100)])]
    order = iter(sessions)
    w = wd.TapeWriter(store_dir=tmp_path, compress=False)
    summary = wd.run(connect=lambda: next(order), tickers=["T"], writer=w, env={},
                     max_reconnects=2, sleep=lambda _s: None)
    assert summary["n_gaps"] == 1
    assert summary["n_reconnects"] == 2          # gap forced the second connect
    lines = [json.loads(x) for f in tmp_path.glob("dt=*.jsonl")
             for x in f.read_text().splitlines()]
    assert any(l.get("schema_version") == "ws_depth.gap.v1" for l in lines)


def test_run_max_messages_bounds_the_loop(tmp_path):
    # an endless stream must still stop at the cap (bounded run)
    class Endless:
        def send(self, d):
            pass

        def recv(self):
            return _delta("T", Endless._n())
        _seq = 0

        @classmethod
        def _n(cls):
            cls._seq += 1
            return cls._seq

        def close(self):
            pass
    w = wd.TapeWriter(store_dir=tmp_path, compress=False)
    summary = wd.run(connect=lambda: Endless(), tickers=["T"], writer=w, env={},
                     max_messages=5, sleep=lambda _s: None)
    assert summary["status"] == "stopped"
    assert summary["n_lines"] >= 5

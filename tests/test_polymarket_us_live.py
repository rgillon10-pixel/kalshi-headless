"""collection.polymarket_us_live — the LIVE default discover_fn/fetch_us_book_fn for the
Polymarket US book-capture leg (Q33 bring-up). All offline: signing is verified against a
locally-generated Ed25519 keypair, and every network op is exercised through an injected
`http_get(path)->(status,text)` fake built from fixtures recorded off the live probe's
documented shapes (findings/2026-07-21-polymarket-us-public-api-probe.md). No network here.

Asserts: Ed25519 signature correctness + 30s-window timestamp + secret never in headers;
book parsing with empty/one-sided ladders as DATA (L23); 404/no-slug -> no_book; non-200 ->
book_error; paginated listing with memory cap + truncation (L10); structural US<->intl
matching (1:1 attaches, 0/ambiguous leaves us_slug None); end-to-end wiring through
polymarket_us_pairs.run incl. the blocked_key no-network guarantee; and read-only discipline
(no execution import, no order verbs)."""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from collection import polymarket_us_live as live


# --------------------------------------------------------------------------- #
# fixtures — recorded from the documented live shapes (markets-schema.json)
# --------------------------------------------------------------------------- #
def _amount(v, cur="USD"):
    return {"value": str(v), "currency": cur}


def _book_payload(bids, offers, state="MARKET_STATE_OPEN"):
    """bids/offers are [(price, size), ...] tuples -> documented BookEntry shape."""
    return json.dumps({"marketData": {
        "marketSlug": "usa-reach-quarterfinals",
        "bids": [{"px": _amount(p), "qty": str(q)} for p, q in bids],
        "offers": [{"px": _amount(p), "qty": str(q)} for p, q in offers],
        "state": state, "transactTime": "2026-07-21T02:00:00Z"}})


def _us_market(mid, slug, question, title=""):
    return {"id": mid, "slug": slug, "question": question, "title": title, "active": True}


def _gen_keypair():
    """A throwaway Ed25519 keypair; secret_b64 mirrors the docs' base64(secret)[:32] loader."""
    sk = ed25519.Ed25519PrivateKey.generate()
    from cryptography.hazmat.primitives import serialization
    raw = sk.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption())
    return base64.b64encode(raw).decode(), sk.public_key()


# --------------------------------------------------------------------------- #
# Ed25519 signing
# --------------------------------------------------------------------------- #
def test_auth_headers_signature_verifies_and_has_all_headers():
    secret_b64, pub = _gen_keypair()
    now_ms = 1784687304000
    h = live.auth_headers("GET", "/v1/markets", "KEY-ID-123", secret_b64, now_ms=now_ms)
    assert h["X-PM-Access-Key"] == "KEY-ID-123"
    assert h["X-PM-Timestamp"] == str(now_ms)
    # the signature must verify over f"{ts}{method}{path}" with the matching public key
    msg = f"{now_ms}GET/v1/markets".encode()
    pub.verify(base64.b64decode(h["X-PM-Signature"]), msg)  # raises InvalidSignature on failure


def test_auth_headers_timestamp_is_ms_within_30s_window_by_default():
    secret_b64, _ = _gen_keypair()
    before = int(time.time() * 1000)
    h = live.auth_headers("GET", "/v1/markets/x/book", "K", secret_b64)
    after = int(time.time() * 1000)
    ts = int(h["X-PM-Timestamp"])
    assert before <= ts <= after
    assert abs(ts - before) < 30_000  # within the documented 30s server-time window


def test_auth_headers_never_leak_the_secret_value():
    secret_b64, _ = _gen_keypair()
    h = live.auth_headers("GET", "/v1/markets", "K", secret_b64, now_ms=1)
    assert secret_b64 not in json.dumps(h)
    assert all(secret_b64 not in v for v in h.values())


def test_signature_binds_method_and_path():
    secret_b64, pub = _gen_keypair()
    h = live.auth_headers("GET", "/v1/markets", "K", secret_b64, now_ms=5)
    # a signature made for one path must NOT verify against a different path
    with pytest.raises(Exception):
        pub.verify(base64.b64decode(h["X-PM-Signature"]), b"5GET/v1/events")


# --------------------------------------------------------------------------- #
# book parsing — empty/one-sided is DATA (L23)
# --------------------------------------------------------------------------- #
def test_parse_us_book_two_sided():
    b = live.parse_us_book(_book_payload([(0.18, 50), (0.17, 100)], [(0.21, 40), (0.22, 60)]))
    assert b["best_bid"] == 0.18 and b["best_ask"] == 0.21
    assert b["bids"][0] == [0.18, 50.0] and b["asks"][0] == [0.21, 40.0]
    assert b["state"] == "MARKET_STATE_OPEN"


def test_parse_us_book_sorts_levels():
    # unsorted input -> best_bid is the max bid, best_ask the min offer
    b = live.parse_us_book(_book_payload([(0.15, 1), (0.19, 2)], [(0.25, 1), (0.21, 2)]))
    assert b["best_bid"] == 0.19 and b["best_ask"] == 0.21


def test_parse_us_book_empty_is_data_not_error():
    b = live.parse_us_book(_book_payload([], []))
    assert b["bids"] == [] and b["asks"] == []
    assert b["best_bid"] is None and b["best_ask"] is None


def test_parse_us_book_one_sided_is_data():
    b = live.parse_us_book(_book_payload([(0.30, 10)], []))
    assert b["best_bid"] == 0.30 and b["best_ask"] is None
    assert b["asks"] == []


def test_parse_us_book_malformed_json_raises():
    with pytest.raises(json.JSONDecodeError):
        live.parse_us_book("not json{")


def test_parse_us_book_drops_priceless_level():
    payload = json.dumps({"marketData": {"bids": [{"px": {"value": None}, "qty": "5"},
                                                  {"px": _amount(0.4), "qty": "9"}], "offers": []}})
    b = live.parse_us_book(payload)
    assert b["bids"] == [[0.4, 9.0]]


def test_parse_us_book_raw_is_exact_payload():
    payload = _book_payload([(0.1, 1)], [])
    assert live.parse_us_book(payload)["raw"] == payload


# --------------------------------------------------------------------------- #
# fetch_us_book_fn
# --------------------------------------------------------------------------- #
def test_fetch_no_slug_is_no_book():
    fetch = live.make_fetch_us_book_fn(env={}, http_get=lambda p: (_ for _ in ()).throw(
        AssertionError("must not GET when us_slug is missing")))
    assert fetch({"kalshi_ticker": "X"}) is None


def test_fetch_200_returns_parsed_book():
    payload = _book_payload([(0.18, 50)], [(0.21, 40)])
    fetch = live.make_fetch_us_book_fn(env={}, http_get=lambda p: (200, payload))
    book = fetch({"us_slug": "usa-reach-quarterfinals"})
    assert book["best_bid"] == 0.18 and book["best_ask"] == 0.21


def test_fetch_404_is_no_book():
    fetch = live.make_fetch_us_book_fn(env={}, http_get=lambda p: (404, "not found"))
    assert fetch({"us_slug": "not-on-us"}) is None


def test_fetch_500_is_book_error():
    fetch = live.make_fetch_us_book_fn(env={}, http_get=lambda p: (500, "boom"))
    with pytest.raises(RuntimeError):
        fetch({"us_slug": "s"})


def test_fetch_requests_correct_book_path():
    seen = {}

    def http_get(path):
        seen["path"] = path
        return 200, _book_payload([], [])

    live.make_fetch_us_book_fn(env={}, http_get=http_get)({"us_slug": "abc-def"})
    assert seen["path"] == "/v1/markets/abc-def/book"


# --------------------------------------------------------------------------- #
# US market listing — pagination + memory cap (L10)
# --------------------------------------------------------------------------- #
def test_list_us_markets_paginates_until_short_page():
    pages = {
        0: json.dumps({"markets": [_us_market(str(i), f"s{i}", "q") for i in range(500)]}),
        500: json.dumps({"markets": [_us_market("x", "sx", "q")]}),  # short page -> stop
    }

    def http_get(path):
        off = int(path.split("offset=")[1])
        return 200, pages[off]

    markets, raw, truncated = live.list_us_markets(http_get, page_size=500)
    assert len(markets) == 501 and truncated is False and len(raw) == 2


def test_list_us_markets_honours_memory_cap_and_flags_truncation():
    full = json.dumps({"markets": [_us_market(str(i), f"s{i}", "q") for i in range(500)]})
    markets, raw, truncated = live.list_us_markets(lambda p: (200, full),
                                                   page_size=500, max_markets=500)
    assert len(markets) == 500 and truncated is True


def test_list_us_markets_non_200_raises():
    with pytest.raises(RuntimeError):
        live.list_us_markets(lambda p: (503, "unavailable"))


# --------------------------------------------------------------------------- #
# discovery matching — structural, 1:1 only, never guessed
# --------------------------------------------------------------------------- #
def _round_desc(team="USA"):
    return {"family": "wc_round", "round": "quarterfinals", "team": team,
            "match_key": f"quarterfinals|{team}", "kalshi_ticker": f"KXWCROUND-26QUAR-{team}"}


def test_find_us_market_exact_single_match():
    us = [_us_market("1", "usa-reach-quarterfinals", "Will USA reach the Quarterfinals?"),
          _us_market("2", "fra-reach-quarterfinals", "Will France reach the Quarterfinals?")]
    m, ambiguous = live.find_us_market(_round_desc("USA"), us)
    assert m["slug"] == "usa-reach-quarterfinals" and ambiguous is False


def test_find_us_market_no_match_returns_none():
    us = [_us_market("2", "fra-reach-quarterfinals", "Will France reach the Quarterfinals?")]
    m, ambiguous = live.find_us_market(_round_desc("USA"), us)
    assert m is None and ambiguous is False


def test_find_us_market_ambiguous_when_multiple():
    us = [_us_market("1", "a", "Will USA reach the Quarterfinals?"),
          _us_market("1b", "b", "USA to reach Quarterfinals — will USA advance?")]
    m, ambiguous = live.find_us_market(_round_desc("USA"), us)
    assert m is None and ambiguous is True


def test_find_us_market_fed_family_tokens():
    d = {"family": "fed_decision", "meeting": "2026-07", "bucket": "hike_25",
         "match_key": "2026-07|hike_25", "kalshi_ticker": "KXFEDDECISION-26JUL-H25"}
    us = [_us_market("f1", "fed-jul-2026-25-increase",
                     "Will the Fed increase rates by 25 bps after the July 2026 meeting?"),
          _us_market("f2", "fed-jul-2026-nochange",
                     "Will there be no change to rates after the July 2026 meeting?")]
    m, ambiguous = live.find_us_market(d, us)
    assert m["slug"] == "fed-jul-2026-25-increase" and ambiguous is False


def test_attach_us_markets_keeps_unmatched_as_none():
    intl = [_round_desc("USA"), _round_desc("BRA")]
    us = [_us_market("1", "usa-reach-quarterfinals", "Will USA reach the Quarterfinals?")]
    out = live.attach_us_markets(intl, us)
    assert out[0]["us_slug"] == "usa-reach-quarterfinals" and out[0]["us_market_id"] == "1"
    assert out[1]["us_slug"] is None and out[1]["us_market_id"] is None  # kept, not dropped


# --------------------------------------------------------------------------- #
# discover_fn assembly
# --------------------------------------------------------------------------- #
def test_make_discover_fn_attaches_and_carries_raw():
    us_page = json.dumps({"markets": [
        _us_market("1", "usa-reach-quarterfinals", "Will USA reach the Quarterfinals?")]})
    discover = live.make_discover_fn(
        env={},
        intl_matched_fn=lambda: [_round_desc("USA")],
        list_us_markets_fn=lambda: ([json.loads(us_page)["markets"][0]], [us_page], False))
    matched, raw = discover()
    assert matched[0]["us_slug"] == "usa-reach-quarterfinals"
    assert raw == [us_page]


def test_make_discover_fn_truncation_adds_marker(capsys):
    discover = live.make_discover_fn(
        env={},
        intl_matched_fn=lambda: [_round_desc("USA")],
        list_us_markets_fn=lambda: ([], ["p"], True))
    _matched, raw = discover()
    assert any("__truncated__" in r for r in raw)
    assert "truncated" in capsys.readouterr().err.lower()


# --------------------------------------------------------------------------- #
# end-to-end wiring through polymarket_us_pairs.run
# --------------------------------------------------------------------------- #
def test_run_blocked_key_makes_no_network_call(tmp_path):
    def _boom(path):
        raise AssertionError("no network call may happen without a credential")

    summary = live.run(env={}, tape_dir=tmp_path, http_get=_boom,
                       intl_matched_fn=lambda: (_ for _ in ()).throw(
                           AssertionError("discovery must not run either")))
    assert summary["status"] == "blocked_key"
    assert list(tmp_path.iterdir()) == []


def test_run_credentialed_captures_real_ask_book(tmp_path):
    us_market = _us_market("1", "usa-reach-quarterfinals", "Will USA reach the Quarterfinals?")

    def http_get(path):
        if path.endswith("/book"):
            return 200, _book_payload([(0.18, 50)], [(0.21, 40)])
        raise AssertionError(f"unexpected path {path}")

    summary = live.run(
        env={"POLYMARKET_US_API_KEY": "keyid", "POLYMARKET_US_SECRET_KEY": "c2VjcmV0"},
        tape_dir=tmp_path, http_get=http_get,
        intl_matched_fn=lambda: [_round_desc("USA")],
        list_us_markets_fn=lambda: ([us_market], ["rawpage"], False))

    assert summary["status"] == "ok"
    assert summary["n_captured"] == 1 and summary["completeness_ok"] is True
    rec = json.loads((tmp_path / f"dt={summary['day']}.jsonl").read_text().splitlines()[0])
    assert rec["polymarket_us"]["price_source_tag"] == "real_ask"
    assert rec["polymarket_us"]["best_bid"] == 0.18 and rec["polymarket_us"]["best_ask"] == 0.21
    assert rec["polymarket_us"]["market_id"] == "1"
    assert rec["kalshi_ticker"] == "KXWCROUND-26QUAR-USA"


def test_run_unlisted_us_market_is_no_book_not_gate(tmp_path):
    # intl question matched, but the US venue lists nothing for it -> us_slug None -> no_book
    def http_get(path):
        raise AssertionError("no book GET when there is no us_slug")

    summary = live.run(
        env={"POLYMARKET_US_API_KEY": "keyid", "POLYMARKET_US_SECRET_KEY": "c2VjcmV0"},
        tape_dir=tmp_path, http_get=http_get,
        intl_matched_fn=lambda: [_round_desc("BRA")],
        list_us_markets_fn=lambda: ([], ["rawpage"], False))
    assert summary["n_captured"] == 0 and summary["n_no_book"] == 1
    assert summary["completeness_ok"] is True  # US coverage gap is structural, not a fault


def test_run_book_http_error_gates_completeness(tmp_path):
    us_market = _us_market("1", "usa-reach-quarterfinals", "Will USA reach the Quarterfinals?")
    summary = live.run(
        env={"POLYMARKET_US_API_KEY": "keyid", "POLYMARKET_US_SECRET_KEY": "c2VjcmV0"},
        tape_dir=tmp_path, http_get=lambda p: (500, "boom"),
        intl_matched_fn=lambda: [_round_desc("USA")],
        list_us_markets_fn=lambda: ([us_market], ["rawpage"], False))
    assert summary["n_book_errors"] == 1 and summary["completeness_ok"] is False


# --------------------------------------------------------------------------- #
# read-only / no-execution discipline (static)
# --------------------------------------------------------------------------- #
def test_module_imports_nothing_from_execution():
    src = Path(live.__file__).read_text(encoding="utf-8")
    assert "import execution" not in src and "from execution" not in src


def test_module_has_no_order_verbs():
    src = Path(live.__file__).read_text(encoding="utf-8")
    # read-only market data only: no order/cancel/quote POST call paths anywhere
    for forbidden in ("/v1/orders", "/v1/order/", "/v1/trading/", "place_order",
                      "requests.post", ".post(", "/cancel"):
        assert forbidden not in src, f"forbidden order-path token present: {forbidden}"

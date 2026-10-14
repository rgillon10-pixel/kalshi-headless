"""execution.kalshi_client — signing, gating and fill adaptation, with a fake transport.
No network: the session is a stub that records requests and returns canned bodies."""
from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from execution import kalshi_client as kc
from execution.schema import Order


class FakeResp:
    def __init__(self, status, body):
        self.status_code = status
        self.text = json.dumps(body)

    def json(self):
        return json.loads(self.text)


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def request(self, method, url, headers=None, data=None, params=None, timeout=None):
        self.calls.append({"method": method, "url": url, "headers": headers, "data": data, "params": params})
        key = (method, url.split("?")[0].split("/trade-api/v2")[1].split("/", 3)[1:])
        for (m, path), body in self.routes.items():
            if m == method and url.endswith(path):
                return FakeResp(200, body)
        return FakeResp(404, {"error": "no route"})


@pytest.fixture
def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def order():
    return Order(order_id="s90:20261015:KXHIGHTDAL-26OCT15-B72", ts="2026-10-15T00:35:00+00:00",
                 ticker="KXHIGHTDAL-26OCT15-B72", side="yes", action="buy", limit_price=0.62,
                 qty=20, tif="ioc", strategy="s90", event_ticker="KXHIGHTDAL-26OCT15")


def test_signature_verifies_against_public_key(key):
    sig = kc.sign(key, "1700000000000", "GET", "/trade-api/v2/portfolio/balance")
    key.public_key().verify(base64.b64decode(sig), b"1700000000000GET/trade-api/v2/portfolio/balance",
                            padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.DIGEST_LENGTH),
                            hashes.SHA256())


def test_from_env_refuses_without_credentials(monkeypatch):
    monkeypatch.delenv("KALSHI_API_KEY_ID", raising=False)
    monkeypatch.delenv("KALSHI_PRIVATE_KEY_PATH", raising=False)
    with pytest.raises(RuntimeError):
        kc.KalshiOrderClient.from_env()


def test_from_env_loads_pem(monkeypatch, tmp_path, key):
    pem = tmp_path / "k.pem"
    pem.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    monkeypatch.setenv("KALSHI_API_KEY_ID", "abc")
    monkeypatch.setenv("KALSHI_PRIVATE_KEY_PATH", str(pem))
    c = kc.KalshiOrderClient.from_env()
    assert c.key_id == "abc"


def test_ioc_order_body_and_headers(key):
    s = FakeSession({("POST", "/portfolio/orders"): {"order": {"order_id": "o1", "status": "executed"}},
                     ("GET", "/portfolio/fills"): {"fills": [{"count": 12, "yes_price_dollars": "0.6200", "fee_dollars": "0.24"}]}})
    c = kc.KalshiOrderClient("kid", key, session=s)
    fill = kc.live_fill_fn(c)(order(), [])
    post = s.calls[0]
    body = json.loads(post["data"])
    assert body["time_in_force"] == "immediate_or_cancel" and body["type"] == "limit"
    assert body["count"] == 20 and body["yes_price_dollars"] == "0.62" and body["side"] == "yes"
    assert post["headers"]["KALSHI-ACCESS-KEY"] == "kid" and post["headers"]["KALSHI-ACCESS-TIMESTAMP"].isdigit()
    assert fill.qty == 12 and fill.price == 0.62 and fill.fee == 0.24 and fill.fill_model == "live_ioc"
    assert fill.price_source_tag == "real_ask" and not fill.validate()


def test_unfilled_ioc_yields_no_fill(key):
    s = FakeSession({("POST", "/portfolio/orders"): {"order": {"order_id": "o2", "status": "canceled", "filled_count": 0}},
                     ("GET", "/portfolio/fills"): {"fills": []},
                     ("GET", "/portfolio/orders/o2"): {"order": {"order_id": "o2", "filled_count": 0}}})
    c = kc.KalshiOrderClient("kid", key, session=s)
    assert kc.live_fill_fn(c)(order(), []) is None


def test_fee_modeled_when_venue_omits_it(key):
    f = kc.fill_from_venue(order(), {"order_id": "o3"}, [{"count": 5, "yes_price_dollars": "0.6000"}], "t")
    assert f.qty == 5 and "fee_modeled_not_reported" in f.caveats and f.fee == pytest.approx(0.02 * 5, abs=0.001)


def test_http_error_raises_and_never_retries(key):
    s = FakeSession({})
    c = kc.KalshiOrderClient("kid", key, session=s)
    with pytest.raises(RuntimeError):
        c.create_ioc_limit_buy(order())
    assert len(s.calls) == 1

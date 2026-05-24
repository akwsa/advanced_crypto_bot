# Tujuan: Regression tests for Indodax private order parameter formatting.
# Caller: scripts/test.sh focused API tests.
# Dependensi: api.indodax_api.IndodaxAPI with fake HTTP session.
# Main Functions: TestIndodaxOrderParams.
# Side Effects: None; no real network/API calls.
from urllib.parse import parse_qs
import unittest

from api.indodax_api import IndodaxAPI


class _FakeResponse:
    status_code = 200
    text = '{"success": 1}'

    def json(self):
        return {"success": 1, "return": {"order_id": "123"}}


class _FakeSession:
    def __init__(self):
        self.post_calls = []

    def post(self, url, headers=None, data=None, timeout=None):
        self.post_calls.append({
            "url": url,
            "headers": headers,
            "data": data,
            "timeout": timeout,
        })
        return _FakeResponse()


class TestIndodaxOrderParams(unittest.TestCase):
    def test_create_order_formats_concatenated_idr_pair_for_private_trade_api(self):
        api = IndodaxAPI(api_key="key", secret_key="secret")
        api.session = _FakeSession()
        api.get_ticker = lambda pair: {"last": 1124.0}

        result = api.create_order("jellyjellyidr", "buy", price=1124, amount=44.35)

        self.assertEqual(result["success"], 1)
        self.assertEqual(len(api.session.post_calls), 1)
        params = parse_qs(api.session.post_calls[0]["data"])
        flattened = {key: values[0] for key, values in params.items()}
        self.assertEqual(flattened["method"], "trade")
        self.assertEqual(flattened["pair"], "jellyjelly_idr")
        self.assertEqual(flattened["type"], "buy")
        self.assertEqual(flattened["idr"], str(int(1124 * 44.35)))
        self.assertIn("jellyjelly", flattened)
        self.assertNotIn("jellyjellyidr", flattened)


if __name__ == "__main__":
    unittest.main()

import asyncio

from scalper.scalper_module import ScalperModule


class DummyResponse:
    def __init__(self, status_code=200, data=None):
        self.status_code = status_code
        self._data = data if data is not None else []

    def json(self):
        return self._data


def _trade(ts, price="100", amount="1"):
    return {"date": ts, "price": price, "amount": amount}


def test_fetch_historical_data_uses_compact_lowercase_pair_first(monkeypatch):
    called_urls = []
    trades = [_trade(1_700_000_000 + i * 60, str(100 + i), "2") for i in range(3)]

    def fake_get(url, timeout, headers):
        called_urls.append(url)
        assert timeout == 10
        assert headers["User-Agent"]
        return DummyResponse(200, trades)

    monkeypatch.setattr("scalper.scalper_module.requests.get", fake_get)

    df = asyncio.run(ScalperModule._fetch_historical_data(None, "EDENIDR", timeframe="1m"))

    assert called_urls == ["https://indodax.com/api/trades/edenidr"]
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 3
    assert df["close"].iloc[-1] == 102.0


def test_fetch_historical_data_falls_back_to_underscore_pair_when_compact_invalid(monkeypatch):
    called_urls = []
    trades = [_trade(1_700_000_000 + i * 60, str(200 + i), "1") for i in range(2)]

    def fake_get(url, timeout, headers):
        called_urls.append(url)
        if url.endswith("edenidr"):
            return DummyResponse(200, {"error": "invalid_pair"})
        return DummyResponse(200, trades)

    monkeypatch.setattr("scalper.scalper_module.requests.get", fake_get)

    df = asyncio.run(ScalperModule._fetch_historical_data(None, "edenidr", timeframe="1m"))

    assert called_urls == [
        "https://indodax.com/api/trades/edenidr",
        "https://indodax.com/api/trades/eden_idr",
    ]
    assert len(df) == 2
    assert df["close"].iloc[-1] == 201.0


def test_fetch_historical_data_returns_none_for_empty_all_candidates(monkeypatch):
    called_urls = []

    def fake_get(url, timeout, headers):
        called_urls.append(url)
        return DummyResponse(200, [])

    monkeypatch.setattr("scalper.scalper_module.requests.get", fake_get)

    df = asyncio.run(ScalperModule._fetch_historical_data(None, "EDENIDR"))

    assert df is None
    assert called_urls == [
        "https://indodax.com/api/trades/edenidr",
        "https://indodax.com/api/trades/eden_idr",
    ]

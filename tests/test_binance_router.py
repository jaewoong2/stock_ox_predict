import pytest
from fastapi.testclient import TestClient

from myapi.deps import get_binance_service
from myapi.main import app
from myapi.schemas.auth import ErrorCode
from myapi.schemas.binance import BinanceKline, BinanceKlinesResponse
from myapi.services.binance_service import BinanceAPIError


@pytest.fixture(autouse=True)
def clear_overrides():
    app.dependency_overrides.clear()
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)


class _StubBinanceService:
    async def fetch_klines(self, symbol, interval, limit, start_time=None, end_time=None):
        kline = BinanceKline(
            openTime=1640995200000,
            open="46000.00",
            high="47500.00",
            low="45800.00",
            close="47200.00",
            volume="1234.56789",
            closeTime=1640998799999,
            quoteAssetVolume="56789012.34",
            numberOfTrades=12345,
            takerBuyBaseAssetVolume="678.90123",
            takerBuyQuoteAssetVolume="31234567.89",
        )
        return (
            BinanceKlinesResponse(
                klines=[kline], symbol=symbol, interval=interval, count=1
            ),
            {"binanceResponseTime": 50},
        )


def test_get_binance_klines_success(client):
    app.dependency_overrides[get_binance_service] = lambda: _StubBinanceService()

    response = client.get(
        "/api/v1/binance/klines?symbol=BTCUSDT&interval=1h&limit=1"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["symbol"] == "BTCUSDT"
    assert body["data"]["interval"] == "1h"
    assert body["data"]["count"] == 1
    assert len(body["data"]["klines"]) == 1
    assert body["meta"]["binanceResponseTime"] == 50


def test_get_binance_klines_invalid_params(client):
    response = client.get("/api/v1/binance/klines?interval=1h")

    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.BINANCE_INVALID_PARAMS.value


def test_get_binance_klines_rate_limited(client):
    class _RateLimitedService:
        async def fetch_klines(self, *args, **kwargs):
            raise BinanceAPIError(
                status_code=429,
                error_code=ErrorCode.BINANCE_RATE_LIMIT,
                message="rate limited",
            )

    app.dependency_overrides[get_binance_service] = lambda: _RateLimitedService()

    response = client.get(
        "/api/v1/binance/klines?symbol=ETHUSDT&interval=1h&limit=5"
    )

    assert response.status_code == 429
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == ErrorCode.BINANCE_RATE_LIMIT.value

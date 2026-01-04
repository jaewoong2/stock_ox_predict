from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class BinanceKline(BaseModel):
    openTime: int = Field(..., description="Candle open time (Unix ms)")
    open: str = Field(..., description="Open price")
    high: str = Field(..., description="High price")
    low: str = Field(..., description="Low price")
    close: str = Field(..., description="Close price")
    volume: str = Field(..., description="Base asset volume")
    closeTime: int = Field(..., description="Candle close time (Unix ms)")
    quoteAssetVolume: str = Field(..., description="Quote asset volume")
    numberOfTrades: int = Field(..., description="Number of trades")
    takerBuyBaseAssetVolume: str = Field(
        ..., description="Taker buy base asset volume"
    )
    takerBuyQuoteAssetVolume: str = Field(
        ..., description="Taker buy quote asset volume"
    )


class BinanceKlinesResponse(BaseModel):
    klines: List[BinanceKline]
    symbol: str
    interval: str
    count: int

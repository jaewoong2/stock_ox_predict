from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional, List

from pydantic import BaseModel, Field


class StockPrice(BaseModel):
    """실시간 주식 가격 정보"""
    symbol: str = Field(..., description="종목 심볼")
    current_price: Decimal = Field(..., description="현재 가격")
    previous_close: Decimal = Field(..., description="전일 종가")
    change: Decimal = Field(..., description="가격 변동")
    change_percent: Decimal = Field(..., description="변동률 (%)")
    volume: Optional[int] = Field(None, description="거래량")
    market_status: str = Field(..., description="장 상태 (OPEN/CLOSED/PRE_MARKET/AFTER_HOURS)")
    last_updated: datetime = Field(..., description="마지막 업데이트 시간")
    

class EODPrice(BaseModel):
    """장 마감 가격 정보"""
    symbol: str = Field(..., description="종목 심볼")
    trading_date: str = Field(..., description="거래일 (YYYY-MM-DD)")
    close_price: Decimal = Field(..., description="종가")
    previous_close: Decimal = Field(..., description="전일 종가")
    change: Decimal = Field(..., description="가격 변동")
    change_percent: Decimal = Field(..., description="변동률 (%)")
    high: Decimal = Field(..., description="고가")
    low: Decimal = Field(..., description="저가")
    open_price: Decimal = Field(..., description="시가")
    volume: int = Field(..., description="거래량")
    fetched_at: datetime = Field(..., description="데이터 수집 시간")


class PriceComparisonResult(BaseModel):
    """가격 비교 결과"""
    symbol: str = Field(..., description="종목 심볼")
    trading_date: str = Field(..., description="거래일")
    current_price: Decimal = Field(..., description="현재 가격")
    previous_price: Decimal = Field(..., description="이전 가격")
    price_movement: str = Field(..., description="가격 움직임 (UP/DOWN/FLAT)")
    change_percent: Decimal = Field(..., description="변동률 (%)")
    prediction_outcome: str = Field(..., description="예측 결과 (CORRECT/INCORRECT)")
    

class UniversePriceResponse(BaseModel):
    """오늘의 유니버스 가격 정보"""
    trading_day: str = Field(..., description="거래일")
    prices: list[StockPrice] = Field(..., description="종목별 가격 정보")
    last_updated: datetime = Field(..., description="마지막 업데이트 시간")


class SettlementPriceData(BaseModel):
    """정산용 가격 데이터"""
    symbol: str = Field(..., description="종목 심볼") 
    trading_date: str = Field(..., description="거래일")
    settlement_price: Decimal = Field(..., description="정산 기준 가격 (보통 종가)")
    reference_price: Decimal = Field(..., description="기준 가격 (보통 전일 종가)")
    price_movement: str = Field(..., description="가격 움직임 (UP/DOWN/FLAT)")
    change_percent: Decimal = Field(..., description="변동률 (%)")
    is_valid_settlement: bool = Field(..., description="정산 가능 여부")
    void_reason: Optional[str] = Field(None, description="정산 무효 사유")


class EODCollectionDetail(BaseModel):
    """EOD 데이터 수집 상세 결과"""
    symbol: str = Field(..., description="종목 심볼")
    success: bool = Field(..., description="수집 성공 여부")
    error_message: Optional[str] = Field(None, description="실패 시 오류 메시지")
    eod_data: Optional[EODPrice] = Field(None, description="수집된 EOD 데이터")


class EODCollectionResult(BaseModel):
    """EOD 데이터 수집 전체 결과"""
    trading_day: str = Field(..., description="거래일")
    total_symbols: int = Field(..., description="총 종목 수")
    successful_collections: int = Field(..., description="성공적으로 수집된 종목 수")
    failed_collections: int = Field(..., description="실패한 종목 수")
    details: List[EODCollectionDetail] = Field(..., description="종목별 상세 결과")
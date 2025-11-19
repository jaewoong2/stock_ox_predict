from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Any

from pydantic import BaseModel, Field


class StockPrice(BaseModel):
    """실시간 주식 가격 정보"""

    symbol: str = Field(..., description="종목 심볼")
    current_price: Decimal = Field(..., description="현재 가격")
    previous_close: Decimal = Field(..., description="전일 종가")
    change: Decimal = Field(..., description="가격 변동")
    change_percent: Decimal = Field(..., description="변동률 (%)")
    volume: Optional[int] = Field(None, description="거래량")
    market_status: str = Field(
        ..., description="장 상태 (OPEN/CLOSED/PRE_MARKET/AFTER_HOURS)"
    )
    last_updated: datetime = Field(..., description="마지막 업데이트 시간")


class TradingDayPriceSummary(BaseModel):
    """거래일 가격 요약 정보 (종가 + 현재가)"""

    symbol: str = Field(..., description="종목 심볼")
    trading_day: str = Field(..., description="거래일 (YYYY-MM-DD)")

    # 금일 종가 정보 (06:00 KST 수집, 전일 대비)
    closing_price: Decimal = Field(..., description="금일 종가")
    previous_close: Decimal = Field(..., description="전일 종가")
    close_change_amount: Decimal = Field(..., description="종가 변동액 (전일 대비)")
    close_change_percent: Decimal = Field(..., description="종가 변동률 (전일 대비, %)")

    # 현재가 정보 (15분마다 갱신, 금일 종가 대비)
    current_price: Decimal = Field(..., description="현재가")
    current_change_amount: Decimal = Field(..., description="현재가 변동액 (종가 대비)")
    current_change_percent: Decimal = Field(
        ..., description="현재가 변동률 (종가 대비, %)"
    )

    market_status: str = Field(
        ..., description="장 상태 (OPEN/CLOSED/PRE_MARKET/AFTER_HOURS)"
    )
    last_price_updated: datetime = Field(..., description="현재가 마지막 업데이트 시각")


class EODPriceSnapshot(BaseModel):
    """EOD 가격 스냅샷 (DB → Service 변환용)"""

    symbol: str
    close_price: Decimal
    previous_close: Decimal
    change_amount: Decimal
    change_percent: Decimal

    @classmethod
    def from_db_model(cls, db_model: Any) -> "EODPriceSnapshot":
        """SQLAlchemy 모델에서 변환"""
        return cls(
            symbol=str(db_model.symbol),
            close_price=Decimal(str(db_model.close_price)),
            previous_close=Decimal(str(db_model.previous_close)),
            change_amount=Decimal(str(db_model.change_amount)),
            change_percent=Decimal(str(db_model.change_percent)),
        )


class CurrentPriceSnapshot(BaseModel):
    """현재가 스냅샷 (DB → Service 변환용)"""

    symbol: str
    current_price: Decimal
    market_status: str
    last_price_updated: datetime
    seq: int

    @classmethod
    def from_db_model(cls, db_model: Any) -> "CurrentPriceSnapshot":
        """SQLAlchemy 모델에서 변환"""
        return cls(
            symbol=str(db_model.symbol),
            current_price=Decimal(str(db_model.current_price)),
            market_status=(
                str(db_model.market_status) if db_model.market_status else "UNKNOWN"
            ),
            last_price_updated=(
                db_model.last_price_updated
                if db_model.last_price_updated
                else datetime.now(timezone.utc)
            ),
            seq=int(db_model.seq) if db_model.seq is not None else 9999,
        )


class EODPrice(BaseModel):
    """장 마감 가격 정보"""

    symbol: str = Field(..., description="종목 심볼")
    trading_date: str = Field(..., description="거래일 (YYYY-MM-DD)")
    close_price: Decimal = Field(..., description="종가")
    previous_close: Decimal = Field(..., description="전일 종가")
    change_amount: Decimal = Field(..., description="가격 변동")
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
    # Optional: additional context
    prediction_id: Optional[int] = Field(None, description="예측 ID")
    base_price_source: Optional[str] = Field(
        None, description="기준 가격 소스 (snapshot/previous_close)"
    )


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

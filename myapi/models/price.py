"""
EOD 가격 데이터 모델

이 파일은 EOD(End of Day) 가격 데이터를 저장하기 위한 SQLAlchemy 모델을 정의합니다.
정산 시스템에서 사용되는 가격 데이터의 영구 저장을 담당합니다.
"""

from datetime import date, datetime
from decimal import Decimal
import uuid
from typing import Optional

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from myapi.models.base import Base, TimestampMixin


class EODPrice(Base, TimestampMixin):
    """
    EOD(End of Day) 가격 데이터 모델

    Yahoo Finance API를 통해 수집된 종목별 일일 가격 데이터를 저장합니다.
    정산 시스템에서 예측 결과를 판정하는데 사용됩니다.
    """

    __tablename__ = "eod_prices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    symbol: Mapped[str] = mapped_column(String(10), nullable=False, comment="종목 심볼")
    trading_date: Mapped[date] = mapped_column(Date, nullable=False, comment="거래일")

    # 가격 정보
    open_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, comment="시가")
    high_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, comment="고가")
    low_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, comment="저가")
    close_price: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, comment="종가")
    adjusted_close: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 4), nullable=True, comment="수정 종가"
    )
    previous_close: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, comment="전일 종가"
    )

    # 변동 정보
    change_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, comment="가격 변동액"
    )
    change_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 4), nullable=False, comment="변동률 (%)"
    )

    # 거래 정보
    volume: Mapped[int] = mapped_column(Integer, nullable=False, comment="거래량")

    # 메타데이터
    data_source: Mapped[str] = mapped_column(
        String(50), nullable=False, default="yfinance", comment="데이터 출처"
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, comment="데이터 수집 시각"
    )

    # 인덱스 설정
    __table_args__ = (
        # 종목별 날짜 조회용 복합 인덱스 (고유)
        Index("ix_eod_prices_symbol_date", "symbol", "trading_date", unique=True),
        # 날짜별 전체 종목 조회용
        Index("ix_eod_prices_trading_date", "trading_date"),
        # 최신 데이터 조회용
        Index("ix_eod_prices_fetched_at", "fetched_at"),
    )

    def __repr__(self):
        return f"<EODPrice(symbol='{self.symbol}', date='{self.trading_date}', close={self.close_price})>"

    @property
    def price_movement(self) -> str:
        """가격 움직임 방향 반환 (UP/DOWN/FLAT)"""
        if self.change_amount > 0:
            return "UP"
        elif self.change_amount < 0:
            return "DOWN"
        else:
            return "FLAT"

    def to_dict(self) -> dict:
        """딕셔너리 형태로 변환"""
        return {
            "id": str(self.id),
            "symbol": self.symbol,
            "trading_date": self.trading_date.isoformat(),
            "open_price": float(self.open_price),
            "high_price": float(self.high_price),
            "low_price": float(self.low_price),
            "close_price": float(self.close_price),
            "adjusted_close": (
                float(self.adjusted_close) if self.adjusted_close is not None else None
            ),
            "previous_close": float(self.previous_close),
            "change_amount": float(self.change_amount),
            "change_percent": float(self.change_percent),
            "volume": self.volume,
            "price_movement": self.price_movement,
            "data_source": self.data_source,
            "fetched_at": self.fetched_at.isoformat(),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

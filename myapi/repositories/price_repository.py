"""
EOD 가격 데이터 리포지토리

이 파일은 EOD(End of Day) 가격 데이터의 데이터베이스 접근을 담당합니다.
Yahoo Finance API로 수집된 가격 데이터의 저장, 조회, 업데이트를 처리합니다.
"""

from decimal import Decimal
from typing import List, Optional

from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session
from datetime import date, datetime

from myapi.models.price import EODPrice as EODPriceModel
from myapi.schemas.price import EODPrice as EODPriceSchema
from myapi.repositories.base import BaseRepository


class PriceRepository(BaseRepository[EODPriceModel, EODPriceSchema]):
    """
    EOD 가격 데이터 리포지토리

    주요 기능:
    1. EOD 가격 데이터 저장 및 조회
    2. 종목별, 날짜별 가격 데이터 검색
    3. 정산용 가격 데이터 제공
    4. 데이터 중복 방지 및 업데이트
    """

    def __init__(self, db: Session):
        super().__init__(EODPriceModel, EODPriceSchema, db)

    def _to_eod_price_schema(self, model_instance: EODPriceModel) -> EODPriceSchema:
        """EOD 가격 모델을 스키마로 변환"""
        return EODPriceSchema(
            symbol=model_instance.symbol,
            trading_date=model_instance.trading_date.isoformat(),
            close_price=model_instance.close_price,
            previous_close=model_instance.previous_close,
            change=model_instance.change_amount,
            change_percent=model_instance.change_percent,
            high=model_instance.high_price,
            low=model_instance.low_price,
            open_price=model_instance.open_price,
            volume=model_instance.volume,
            fetched_at=model_instance.fetched_at,
        )

    def save_eod_price(
        self,
        symbol: str,
        trading_date: date,
        open_price: float,
        high_price: float,
        low_price: float,
        close_price: float,
        previous_close: float,
        volume: int,
        data_source: str = "yfinance",
    ) -> Optional[EODPriceSchema]:
        """
        EOD 가격 데이터를 저장합니다. 중복 시 업데이트를 수행합니다.

        Args:
            symbol: 종목 심볼
            trading_date: 거래일
            open_price: 시가
            high_price: 고가
            low_price: 저가
            close_price: 종가
            previous_close: 전일 종가
            volume: 거래량
            data_source: 데이터 출처

        Returns:
            저장된 EOD 가격 스키마 또는 None
        """
        try:
            self._ensure_clean_session()
            # float를 Decimal로 변환하여 계산 정확도 보장
            close_price_d = Decimal(str(close_price))
            previous_close_d = Decimal(str(previous_close))

            # 변동액 및 변동률 계산
            change_amount = close_price_d - previous_close_d
            change_percent = (
                (change_amount / previous_close_d * Decimal("100"))
                if previous_close_d != Decimal("0")
                else Decimal("0")
            )

            # 기존 데이터 확인
            existing = (
                self.db.query(self.model_class)
                .filter(
                    and_(
                        self.model_class.symbol == symbol,
                        self.model_class.trading_date == trading_date,
                    )
                )
                .first()
            )

            if existing:
                # 기존 데이터 업데이트
                existing.open_price = Decimal(str(open_price))
                existing.high_price = Decimal(str(high_price))
                existing.low_price = Decimal(str(low_price))
                existing.close_price = close_price_d
                existing.previous_close = previous_close_d
                existing.change_amount = change_amount
                existing.change_percent = change_percent
                existing.volume = volume
                existing.data_source = data_source
                existing.fetched_at = datetime.utcnow()
                existing.updated_at = datetime.utcnow()

                self.db.commit()
                return self._to_eod_price_schema(existing)
            else:
                # 새 데이터 생성
                new_price = self.model_class(
                    symbol=symbol,
                    trading_date=trading_date,
                    open_price=Decimal(str(open_price)),
                    high_price=Decimal(str(high_price)),
                    low_price=Decimal(str(low_price)),
                    close_price=close_price_d,
                    previous_close=previous_close_d,
                    change_amount=change_amount,
                    change_percent=change_percent,
                    volume=volume,
                    data_source=data_source,
                    fetched_at=datetime.utcnow(),
                )

                self.db.add(new_price)
                self.db.commit()
                return self._to_eod_price_schema(new_price)

        except Exception as e:
            self.db.rollback()
            raise e

    def get_eod_price(
        self, symbol: str, trading_date: date
    ) -> Optional[EODPriceSchema]:
        """
        특정 종목의 특정 날짜 EOD 가격을 조회합니다.

        Args:
            symbol: 종목 심볼
            trading_date: 거래일

        Returns:
            EOD 가격 스키마 또는 None
        """
        self._ensure_clean_session()
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.symbol == symbol,
                    self.model_class.trading_date == trading_date,
                )
            )
            .first()
        )

        return self._to_eod_price_schema(model_instance) if model_instance else None

    def get_eod_prices_for_date(self, trading_date: date) -> List[EODPriceSchema]:
        """
        특정 날짜의 모든 종목 EOD 가격을 조회합니다.

        Args:
            trading_date: 거래일

        Returns:
            EOD 가격 스키마 리스트
        """
        self._ensure_clean_session()
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_date == trading_date)
            .order_by(self.model_class.symbol)
            .all()
        )

        return [self._to_eod_price_schema(instance) for instance in model_instances]

    def get_eod_prices_for_symbols(
        self, symbols: List[str], trading_date: date
    ) -> List[EODPriceSchema]:
        """
        특정 종목들의 특정 날짜 EOD 가격을 조회합니다.

        Args:
            symbols: 종목 심볼 리스트
            trading_date: 거래일

        Returns:
            EOD 가격 스키마 리스트
        """
        self._ensure_clean_session()
        model_instances = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.symbol.in_(symbols),
                    self.model_class.trading_date == trading_date,
                )
            )
            .order_by(self.model_class.symbol)
            .all()
        )

        return [self._to_eod_price_schema(instance) for instance in model_instances]

    def get_latest_eod_prices(self, limit: int = 100) -> List[EODPriceSchema]:
        """
        최신 EOD 가격 데이터를 조회합니다.

        Args:
            limit: 조회할 최대 개수

        Returns:
            EOD 가격 스키마 리스트
        """
        self._ensure_clean_session()
        model_instances = (
            self.db.query(self.model_class)
            .order_by(desc(self.model_class.trading_date), self.model_class.symbol)
            .limit(limit)
            .all()
        )

        return [self._to_eod_price_schema(instance) for instance in model_instances]

    def eod_price_exists(self, symbol: str, trading_date: date) -> bool:
        """
        특정 종목의 특정 날짜 EOD 가격 데이터가 존재하는지 확인합니다.

        Args:
            symbol: 종목 심볼
            trading_date: 거래일

        Returns:
            존재 여부
        """
        self._ensure_clean_session()
        count = (
            self.db.query(func.count(self.model_class.id))
            .filter(
                and_(
                    self.model_class.symbol == symbol,
                    self.model_class.trading_date == trading_date,
                )
            )
            .scalar()
        )

        return count > 0

    def get_missing_eod_data(self, symbols: List[str], trading_date: date) -> List[str]:
        """
        특정 날짜에 EOD 데이터가 없는 종목들을 조회합니다.

        Args:
            symbols: 확인할 종목 심볼 리스트
            trading_date: 거래일

        Returns:
            EOD 데이터가 없는 종목 심볼 리스트
        """
        self._ensure_clean_session()
        existing_symbols = (
            self.db.query(self.model_class.symbol)
            .filter(
                and_(
                    self.model_class.symbol.in_(symbols),
                    self.model_class.trading_date == trading_date,
                )
            )
            .all()
        )

        existing_set = {symbol[0] for symbol in existing_symbols}
        return [symbol for symbol in symbols if symbol not in existing_set]

    def delete_eod_prices_for_date(self, trading_date: date) -> int:
        """
        특정 날짜의 모든 EOD 가격 데이터를 삭제합니다.

        Args:
            trading_date: 삭제할 거래일

        Returns:
            삭제된 레코드 수
        """
        try:
            self._ensure_clean_session()
            count = (
                self.db.query(self.model_class)
                .filter(self.model_class.trading_date == trading_date)
                .delete()
            )

            self.db.commit()
            return count

        except Exception as e:
            self.db.rollback()
            raise e

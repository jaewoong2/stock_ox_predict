from typing import List, Optional, Any, cast
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, and_
from datetime import date

from myapi.models.session import ActiveUniverse as ActiveUniverseModel
from myapi.schemas.universe import UniverseItem, UniverseResponse, UniverseStats
from myapi.schemas.price import StockPrice
from myapi.repositories.base import BaseRepository


class ActiveUniverseRepository(BaseRepository[ActiveUniverseModel, UniverseItem]):
    """활성 유니버스 리포지토리"""

    def __init__(self, db: Session):
        super().__init__(ActiveUniverseModel, UniverseItem, db)

    def _to_universe_item(self, model_instance: ActiveUniverseModel) -> UniverseItem:
        """ActiveUniverse 모델을 UniverseItem 스키마로 변환"""
        if model_instance is None:
            return None

        return UniverseItem.model_validate(model_instance)

    def get_universe_for_date(self, trading_day: date) -> List[UniverseItem]:
        """특정 날짜의 유니버스 조회 (seq 순서대로)"""
        self._ensure_clean_session()
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .order_by(asc(self.model_class.seq))
            .all()
        )

        return [self._to_universe_item(instance) for instance in model_instances]

    def get_universe_models_for_date(
        self, trading_day: date
    ) -> List[ActiveUniverseModel]:
        """특정 날짜의 유니버스 Raw 모델 조회 (가격 포함)"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .order_by(asc(self.model_class.seq))
            .all()
        )

    def get_universe_item_model(
        self, trading_day: date, symbol: str
    ) -> Optional[ActiveUniverseModel]:
        """특정 날짜+심볼의 Raw 모델 조회"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol == symbol,
                )
            )
            .first()
        )

    def update_symbol_price(
        self, trading_day: date, symbol: str, price: StockPrice
    ) -> bool:
        """유니버스 항목에 현재가 정보를 저장/업데이트"""
        try:
            self._ensure_clean_session()
            instance = self.get_universe_item_model(trading_day, symbol)
            if not instance:
                return False

            # Use setattr to avoid static type errors with SQLAlchemy Column typing
            inst: Any = cast(Any, instance)
            setattr(inst, "current_price", price.current_price)
            setattr(inst, "previous_close", price.previous_close)
            setattr(inst, "change_amount", price.change_amount)
            setattr(inst, "change_percent", price.change_percent)
            setattr(inst, "volume", price.volume)
            setattr(inst, "market_status", price.market_status)
            setattr(inst, "last_price_updated", price.last_updated)

            self.db.add(instance)
            self.db.flush()
            self.db.refresh(instance)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise e

    def get_current_universe(self) -> List[UniverseItem]:
        """현재(가장 최근) 유니버스 조회"""
        self._ensure_clean_session()
        # 가장 최근 거래일 찾기
        latest_date = (
            self.db.query(self.model_class.trading_day)
            .order_by(desc(self.model_class.trading_day))
            .first()
        )

        if not latest_date:
            return []

        return self.get_universe_for_date(latest_date[0])

    def get_universe_response(self, trading_day: date) -> UniverseResponse:
        """API 응답용 유니버스 정보 조회"""
        self._ensure_clean_session()
        universe_items = self.get_universe_for_date(trading_day)

        return UniverseResponse(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            symbols=universe_items,
            total_count=len(universe_items),
        )

    def get_universe_items_not_in_list(
        self, trading_day: date, universe_items: List[UniverseItem]
    ):
        """유니버스 항목 없는 애들 조회"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol.not_in(
                        [item.symbol for item in universe_items]
                    ),
                )
            )
            .all()
        )

    def set_universe_for_date(
        self, trading_day: date, universe_items: List[UniverseItem]
    ) -> dict:
        """특정 날짜의 유니버스를 입력 리스트 기준으로 업서트합니다.

        - 삭제: DB에 있으나 입력에 없는 심볼 삭제
        - 삽입: 입력에 있으나 DB에 없는 심볼 삽입
        - 수정: 공존 심볼은 seq 변경 시 업데이트

        Returns:
            dict: {"added": int, "updated": int, "removed": int}
        """
        try:
            self._ensure_clean_session()
            # 현재 DB 상태 조회 (심볼 -> 모델)
            existing_models = (
                self.db.query(self.model_class)
                .filter(self.model_class.trading_day == trading_day)
                .all()
            )

            existing_by_symbol = {str(m.symbol): m for m in existing_models}
            desired_by_symbol = {item.symbol: item for item in universe_items}

            existing_symbols = set(existing_by_symbol.keys())
            desired_symbols = set(desired_by_symbol.keys())

            to_insert = desired_symbols - existing_symbols
            to_consider_update = existing_symbols & desired_symbols

            created_items: List[UniverseItem] = []
            updated_count = 0

            # 삽입
            for symbol in to_insert:
                item = desired_by_symbol[symbol]
                model_instance = self.model_class(
                    trading_day=trading_day, symbol=item.symbol, seq=item.seq
                )
                self.db.add(model_instance)
                created_items.append(item)

            # 업데이트 (seq 변경 시)
            for symbol in to_consider_update:
                model_instance = existing_by_symbol[symbol]
                desired_item = desired_by_symbol[symbol]
                if getattr(model_instance, "seq", None) != desired_item.seq:
                    setattr(model_instance, "seq", desired_item.seq)
                    self.db.add(model_instance)
                    updated_count += 1

            self.db.flush()
            self.db.commit()
            return {
                "added": len(created_items),
                "updated": updated_count,
            }

        except Exception as e:
            self.db.rollback()
            raise e

    def add_symbol_to_universe(
        self, trading_day: date, symbol: str, seq: int
    ) -> UniverseItem:
        """유니버스에 심볼 추가"""
        try:
            self._ensure_clean_session()
            # 중복 확인
            if self.symbol_exists_in_universe(trading_day, symbol):
                raise ValueError(
                    f"Symbol {symbol} already exists in universe for {trading_day}"
                )

            # 시퀀스 중복 확인
            if self.sequence_exists_in_universe(trading_day, seq):
                raise ValueError(
                    f"Sequence {seq} already exists in universe for {trading_day}"
                )

            # BaseRepository의 create 메서드 활용
            model_instance = self.model_class(
                trading_day=trading_day, symbol=symbol, seq=seq
            )
            self.db.add(model_instance)
            self.db.flush()
            self.db.refresh(model_instance)
            self.db.commit()

            return self._to_universe_item(model_instance)

        except Exception as e:
            self.db.rollback()
            raise e

    def remove_symbol_from_universe(self, trading_day: date, symbol: str) -> bool:
        """유니버스에서 심볼 제거"""
        try:
            self._ensure_clean_session()
            deleted_count = (
                self.db.query(self.model_class)
                .filter(
                    and_(
                        self.model_class.trading_day == trading_day,
                        self.model_class.symbol == symbol,
                    )
                )
                .delete()
            )

            self.db.commit()
            return deleted_count > 0

        except Exception as e:
            self.db.rollback()
            raise e

    def symbol_exists_in_universe(self, trading_day: date, symbol: str) -> bool:
        """특정 날짜 유니버스에서 심볼 존재 여부 확인"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol == symbol,
                )
            )
            .first()
            is not None
        )

    def sequence_exists_in_universe(self, trading_day: date, seq: int) -> bool:
        """특정 날짜 유니버스에서 시퀀스 존재 여부 확인"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.seq == seq,
                )
            )
            .first()
            is not None
        )

    def get_symbol_by_sequence(self, trading_day: date, seq: int) -> Optional[str]:
        """시퀀스 번호로 심볼 조회"""
        self._ensure_clean_session()
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.seq == seq,
                )
            )
            .first()
        )

        return getattr(model_instance, "symbol", None) if model_instance else None

    def get_sequence_by_symbol(self, trading_day: date, symbol: str) -> Optional[int]:
        """심볼로 시퀀스 번호 조회"""
        self._ensure_clean_session()
        model_instance = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.symbol == symbol,
                )
            )
            .first()
        )

        return getattr(model_instance, "seq", None) if model_instance else None

    def get_universe_stats(self, trading_day: date) -> UniverseStats:
        """유니버스 통계 조회"""
        self._ensure_clean_session()
        total_symbols = (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .count()
        )

        # TODO: 예측 정보는 PredictionRepository에서 가져와야 함
        # 여기서는 임시로 0으로 설정
        active_predictions = 0
        completion_rate = 0.0

        return UniverseStats(
            trading_day=trading_day.strftime("%Y-%m-%d"),
            total_symbols=total_symbols,
            active_predictions=active_predictions,
            completion_rate=completion_rate,
        )

    def get_available_dates(self, limit: int = 30) -> List[date]:
        """유니버스가 설정된 날짜 목록 조회 (최신순)"""
        self._ensure_clean_session()
        dates = (
            self.db.query(self.model_class.trading_day)
            .distinct()
            .order_by(desc(self.model_class.trading_day))
            .limit(limit)
            .all()
        )

        return [date_tuple[0] for date_tuple in dates]

    def universe_exists_for_date(self, trading_day: date) -> bool:
        """특정 날짜의 유니버스 존재 여부 확인"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .first()
            is not None
        )

    def get_universe_count_for_date(self, trading_day: date) -> int:
        """특정 날짜의 유니버스 심볼 개수 조회"""
        self._ensure_clean_session()
        return (
            self.db.query(self.model_class)
            .filter(self.model_class.trading_day == trading_day)
            .count()
        )

    def clear_universe_for_date(self, trading_day: date) -> int:
        """특정 날짜의 유니버스 전체 삭제"""
        try:
            self._ensure_clean_session()
            deleted_count = (
                self.db.query(self.model_class)
                .filter(self.model_class.trading_day == trading_day)
                .delete()
            )

            self.db.commit()
            return deleted_count

        except Exception as e:
            self.db.rollback()
            raise e

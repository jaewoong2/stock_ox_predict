from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.repositories.session_repository import SessionRepository
from myapi.schemas.universe import (
    UniverseItem,
    UniverseResponse,
    UniverseUpdate,
    UniverseWithPricesResponse,
)

from myapi.schemas.universe import (
    UniverseWithPricesResponse,
    UniverseItemWithPrice,
)
from datetime import datetime, timezone

from myapi.services.price_service import PriceService
import logging


class UniverseService:
    """유니버스(오늘의 종목) 관련 비즈니스 로직"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = ActiveUniverseRepository(db)
        self.session_repo = SessionRepository(db)
        self.price_service = PriceService(db)

    def get_today_universe(self) -> Optional[UniverseResponse]:
        """
        오늘의 유니버스를 조회합니다.
        `universe_router.get_today_universe` 에서 호출됩니다.
        먼저 `session_repo`를 통해 현재 세션을 조회하여 오늘 날짜를 확인한 후,
        해당 날짜의 유니버스 정보를 반환합니다.
        """
        session = self.session_repo.get_current_session()
        if not session:
            return None
        return self.repo.get_universe_response(session.trading_day)

    def get_universe_for_date(self, trading_day: date) -> UniverseResponse:
        """특정 날짜의 유니버스를 조회합니다."""
        return self.repo.get_universe_response(trading_day)

    def upsert_universe(self, update: UniverseUpdate) -> UniverseResponse:
        """
        특정 날짜의 유니버스를 생성하거나 업데이트합니다.
        `universe_router.upsert_universe` 에서 호출됩니다.
        """
        # Parse date
        trg_day = date.fromisoformat(update.trading_day)
        # Set new list
        summary = self.repo.set_universe_for_date(
            trg_day,
            [
                UniverseItem(symbol=symbol, seq=index + 1)
                for index, symbol in enumerate(update.symbols)
            ],
        )
        try:
            logger = logging.getLogger(__name__)
            logger.info(
                f"Universe upsert for {trg_day}: added={summary.get('added')}, updated={summary.get('updated')}, removed={summary.get('removed')}"
            )
        except Exception:
            pass
        # Return response
        return self.repo.get_universe_response(trg_day)

    async def get_today_universe_with_prices(
        self,
    ) -> Optional[UniverseWithPricesResponse]:
        """
        오늘의 유니버스를 가격 정보와 함께 조회합니다.
        사용자가 예측하기 전에 현재 가격과 변동률을 확인할 수 있도록 합니다.
        """

        # 현재 세션 조회
        session = self.session_repo.get_current_session()

        if not session:
            return None

        # 오늘의 유니버스 조회
        universe_response = self.repo.get_universe_response(session.trading_day)

        if not universe_response:
            return None

        # PriceService를 통해 현재 가격 정보 조회
        price_service = self.price_service

        try:
            async with price_service as service:
                universe_prices = await service.get_universe_current_prices(
                    session.trading_day
                )

                # 가격 정보와 유니버스 정보 매칭
                symbols_with_prices = []
                price_dict = {price.symbol: price for price in universe_prices.prices}

                for symbol_item in universe_response.symbols:
                    price_info = price_dict.get(symbol_item.symbol)
                    if price_info:
                        # 변동 방향 계산
                        change_direction = "FLAT"
                        if price_info.change > 0:
                            change_direction = "UP"
                        elif price_info.change < 0:
                            change_direction = "DOWN"

                        # 포맷된 변동률 문자열
                        formatted_change = f"{'+' if price_info.change_percent >= 0 else ''}{price_info.change_percent:.2f}%"

                        symbols_with_prices.append(
                            UniverseItemWithPrice(
                                symbol=symbol_item.symbol,
                                seq=symbol_item.seq,
                                company_name=price_info.symbol,  # TODO: 실제 회사명으로 교체 가능
                                current_price=float(price_info.current_price),
                                previous_close=float(price_info.previous_close),
                                change_percent=float(price_info.change_percent),
                                change_direction=change_direction,
                                formatted_change=formatted_change,
                            )
                        )

                return UniverseWithPricesResponse(
                    trading_day=universe_response.trading_day,
                    symbols=symbols_with_prices,
                    total_count=len(symbols_with_prices),
                    last_updated=datetime.now(timezone.utc).isoformat(),
                )
        except Exception:
            # 가격 조회 실패 시 None 반환 (기존 동작 유지)
            return None

from __future__ import annotations

from datetime import date
from typing import List, Optional, Any, cast
from decimal import Decimal

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
    ActiveUniverseSnapshot,
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
        오늘의 유니버스를 '스냅샷 가격'과 함께 조회합니다.

        - yfinance 호출 없이 ActiveUniverse 테이블의 저장된 필드만 사용
        - 가격 갱신은 `/universe/refresh-prices` 배치(또는 수동)에서 수행
        - 응답은 스냅샷이 존재하는 심볼만 포함 (필드가 없으면 제외)
        """

        # 현재 세션 조회
        session = self.session_repo.get_current_session()
        if not session:
            return None

        # 유니버스 Raw 모델 조회 (가격 스냅샷 포함)
        models = self.repo.get_universe_models_for_date(session.trading_day)
        if not models:
            return None

        items: list[UniverseItemWithPrice] = []
        missing_count = 0

        for m in models:
            snap = ActiveUniverseSnapshot.model_validate(m)

            # 가격 데이터가 없는 경우 기본값으로 처리
            if snap.current_price is None or snap.previous_close is None:
                missing_count += 1
                # 기본값으로 심볼 포함 (UI에서 "데이터 없음" 상태 표시 가능)
                items.append(
                    UniverseItemWithPrice(
                        symbol=snap.symbol,
                        seq=snap.seq,
                        company_name=snap.symbol,  # TODO: 회사명 컬럼/소스 추가 시 교체
                        current_price=0.0,  # 기본값
                        previous_close=0.0,  # 기본값
                        change_percent=0.0,
                        change_direction="UNKNOWN",  # 데이터 없음 상태
                        formatted_change="N/A",  # 데이터 없음 표시
                    )
                )
                continue

            # 정상 데이터가 있는 경우
            # 변동 방향
            change_dir = "FLAT"
            if snap.change_amount is not None and snap.change_amount > Decimal("0"):
                change_dir = "UP"
            elif snap.change_amount is not None and snap.change_amount < Decimal("0"):
                change_dir = "DOWN"

            # 포맷된 변동률
            cp = snap.change_percent if snap.change_percent is not None else Decimal("0.0")
            formatted = f"{cp:+.2f}%"

            items.append(
                UniverseItemWithPrice(
                    symbol=snap.symbol,
                    seq=snap.seq,
                    company_name=snap.symbol,  # TODO: 회사명 컬럼/소스 추가 시 교체
                    current_price=snap.current_price,
                    previous_close=snap.previous_close,
                    change_percent=cp,
                    change_direction=change_dir,
                    formatted_change=formatted,
                )
            )

        # 로깅: missing 심볼이 있으면 경고 로그 남기기
        if missing_count > 0:
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Price data missing for {missing_count}/{len(models)} symbols "
                f"on trading day {session.trading_day}. Using default values."
            )

        return UniverseWithPricesResponse(
            trading_day=session.trading_day.strftime("%Y-%m-%d"),
            symbols=items,
            total_count=len(items),
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

    def get_universe_snapshot_status(self, trading_day: Optional[date] = None) -> dict:
        """유니버스 스냅샷 상태 요약 (누락 카운트, 최근 갱신 시각)."""
        if trading_day is None:
            session = self.session_repo.get_current_session()
            if not session:
                from myapi.core.exceptions import NotFoundError

                raise NotFoundError(
                    message="SNAPSHOT_NOT_AVAILABLE", details={"resource": "session"}
                )
            trading_day = session.trading_day

        models = self.repo.get_universe_models_for_date(trading_day)
        if not models:
            from myapi.core.exceptions import NotFoundError

            raise NotFoundError(
                message="SNAPSHOT_NOT_AVAILABLE",
                details={
                    "resource": "universe",
                    "trading_day": trading_day.isoformat(),
                },
            )

        total = len(models)
        missing: list[str] = []
        updated_times: list[datetime] = []
        for m in models:
            snap = ActiveUniverseSnapshot.model_validate(m)
            if snap.current_price is None or snap.previous_close is None:
                missing.append(snap.symbol)
            if snap.last_price_updated is not None:
                updated_times.append(snap.last_price_updated)
        last_updated_max = max(updated_times).isoformat() if updated_times else None
        last_updated_min = min(updated_times).isoformat() if updated_times else None

        return {
            "trading_day": trading_day.strftime("%Y-%m-%d"),
            "total_symbols": total,
            "snapshots_present": total - len(missing),
            "missing_count": len(missing),
            "last_updated_max": last_updated_max,
            "last_updated_min": last_updated_min,
        }

    async def refresh_today_prices(self, trading_day: date):
        """
        오늘의 유니버스 종목들에 대한 현재가를 수집하고 DB에 반영합니다.
        PriceService.refresh_universe_prices를 사용해 강제 갱신하며,
        내부적으로 ActiveUniverseRepository.update_symbol_price를 사용해 저장합니다.
        """
        async with self.price_service as service:
            return await service.refresh_universe_prices(trading_day)

    async def refresh_today_prices_intraday(self, trading_day: date, interval: str = "30m"):
        """
        오늘의 유니버스 종목들에 대한 intraday 가격(30분봉 등)을 수집하고 DB에 반영합니다.
        PriceService.refresh_universe_prices_intraday를 사용해 봉 데이터 기반 갱신합니다.
        30분 주기 배치에서 호출하기 위한 경로입니다.
        """
        async with self.price_service as service:
            return await service.refresh_universe_prices_intraday(trading_day, interval)

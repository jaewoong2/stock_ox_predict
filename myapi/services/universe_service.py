from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy.orm import Session

from myapi.repositories.active_universe_repository import ActiveUniverseRepository
from myapi.repositories.session_repository import SessionRepository
from myapi.schemas.universe import UniverseItem, UniverseResponse, UniverseUpdate


class UniverseService:
    """유니버스(오늘의 종목) 관련 비즈니스 로직"""

    def __init__(self, db: Session):
        self.db = db
        self.repo = ActiveUniverseRepository(db)
        self.session_repo = SessionRepository(db)

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
        self.repo.set_universe_for_date(trg_day, update.symbols)
        # Return response
        return self.repo.get_universe_response(trg_day)

from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import date, datetime
from myapi.repositories.base import BaseRepository
from myapi.models.session import SessionControl, ActiveUniverse
from myapi.schemas.session import SessionStatus
from myapi.schemas.universe import ActiveUniverseResponse


class SessionRepository(BaseRepository[SessionControl, SessionStatus]):
    """세션 리포지토리 - Pydantic 응답 보장"""

    def __init__(self, db: Session):
        super().__init__(SessionControl, SessionStatus, db)

    def get_current_session(self, trading_day: date = None) -> Optional[SessionStatus]:
        """현재 세션 조회"""
        if trading_day is None:
            trading_day = date.today()
            
        session = self.db.query(SessionControl).filter(
            SessionControl.trading_day == trading_day
        ).first()
        
        if session:
            # Add computed properties to the schema response
            session_dict = {}
            for column in session.__table__.columns:
                session_dict[column.name] = getattr(session, column.name)
            
            # Add computed properties
            session_dict['is_prediction_open'] = session.is_prediction_open
            session_dict['is_settling'] = session.is_settling
            session_dict['is_closed'] = session.is_closed
            
            return SessionStatus(**session_dict)
        return None

    def create_session(self, trading_day: date, predict_open_at: datetime, 
                      predict_cutoff_at: datetime, phase: str = "CLOSED") -> SessionStatus:
        """새 세션 생성"""
        from myapi.models.session import PhaseEnum
        
        phase_enum = PhaseEnum(phase)
        session = SessionControl(
            trading_day=trading_day,
            phase=phase_enum,
            predict_open_at=predict_open_at,
            predict_cutoff_at=predict_cutoff_at
        )
        self.db.add(session)
        self.db.flush()
        self.db.refresh(session)
        
        # Convert to schema with computed properties
        session_dict = {}
        for column in session.__table__.columns:
            session_dict[column.name] = getattr(session, column.name)
            
        session_dict['is_prediction_open'] = session.is_prediction_open
        session_dict['is_settling'] = session.is_settling
        session_dict['is_closed'] = session.is_closed
        
        return SessionStatus(**session_dict)

    def update_session_phase(self, trading_day: date, new_phase: str, 
                           settle_ready_at: datetime = None, 
                           settled_at: datetime = None) -> Optional[SessionStatus]:
        """세션 상태 업데이트"""
        from myapi.models.session import PhaseEnum
        
        session = self.db.query(SessionControl).filter(
            SessionControl.trading_day == trading_day
        ).first()
        
        if not session:
            return None
            
        session.phase = PhaseEnum(new_phase)
        
        if settle_ready_at:
            session.settle_ready_at = settle_ready_at
        if settled_at:
            session.settled_at = settled_at
        
        session.updated_at = datetime.utcnow()
        self.db.add(session)
        self.db.flush()
        self.db.refresh(session)
        
        # Convert to schema with computed properties
        session_dict = {}
        for column in session.__table__.columns:
            session_dict[column.name] = getattr(session, column.name)
            
        session_dict['is_prediction_open'] = session.is_prediction_open
        session_dict['is_settling'] = session.is_settling
        session_dict['is_closed'] = session.is_closed
        
        return SessionStatus(**session_dict)

    def get_sessions_by_date_range(self, start_date: date, end_date: date) -> List[SessionStatus]:
        """날짜 범위로 세션 조회"""
        sessions = self.db.query(SessionControl).filter(
            SessionControl.trading_day.between(start_date, end_date)
        ).order_by(SessionControl.trading_day).all()
        
        result = []
        for session in sessions:
            session_dict = {}
            for column in session.__table__.columns:
                session_dict[column.name] = getattr(session, column.name)
                
            session_dict['is_prediction_open'] = session.is_prediction_open
            session_dict['is_settling'] = session.is_settling
            session_dict['is_closed'] = session.is_closed
            
            result.append(SessionStatus(**session_dict))
        
        return result


class ActiveUniverseRepository(BaseRepository[ActiveUniverse, ActiveUniverseResponse]):
    """활성 종목 리포지토리 - Pydantic 응답 보장"""

    def __init__(self, db: Session):
        super().__init__(ActiveUniverse, ActiveUniverseResponse, db)

    def get_today_universe(self, trading_day: date = None) -> List[ActiveUniverseResponse]:
        """오늘의 종목 조회"""
        if trading_day is None:
            trading_day = date.today()
            
        universe = self.db.query(ActiveUniverse).filter(
            ActiveUniverse.trading_day == trading_day
        ).order_by(ActiveUniverse.seq).all()
        
        return [self._to_schema(item) for item in universe]

    def upsert_universe(self, trading_day: date, symbols: List[dict]) -> List[ActiveUniverseResponse]:
        """종목 목록 업서트"""
        # 기존 종목 삭제
        self.db.query(ActiveUniverse).filter(
            ActiveUniverse.trading_day == trading_day
        ).delete()
        
        # 새 종목 추가
        universe_items = []
        for symbol_data in symbols:
            item = ActiveUniverse(
                trading_day=trading_day,
                symbol=symbol_data['symbol'],
                seq=symbol_data['seq']
            )
            self.db.add(item)
            universe_items.append(item)
        
        self.db.flush()
        
        # 새로고침 후 스키마 변환
        for item in universe_items:
            self.db.refresh(item)
            
        return [self._to_schema(item) for item in universe_items]

    def is_symbol_in_universe(self, trading_day: date, symbol: str) -> bool:
        """종목이 오늘의 유니버스에 포함되어 있는지 확인"""
        exists = self.db.query(ActiveUniverse).filter(
            ActiveUniverse.trading_day == trading_day,
            ActiveUniverse.symbol == symbol
        ).first()
        return exists is not None

    def get_universe_symbols(self, trading_day: date = None) -> List[str]:
        """오늘의 종목 심볼 목록만 조회"""
        if trading_day is None:
            trading_day = date.today()
            
        symbols = self.db.query(ActiveUniverse.symbol).filter(
            ActiveUniverse.trading_day == trading_day
        ).order_by(ActiveUniverse.seq).all()
        
        return [symbol[0] for symbol in symbols]
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, Date, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from myapi.models.base import BaseModel


class ErrorLog(BaseModel):
    """
    시스템 에러 및 실패 상황 추적용 모델

    정산 실패, EOD 데이터 수집 실패, 배치 작업 실패 등의
    모든 실패 상황을 통합하여 추적합니다.
    """

    __tablename__ = "error_logs"
    __table_args__ = {"schema": "crypto", "extend_existing": True}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    check_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="에러 타입 (SETTLEMENT_FAILED, EOD_FETCH_FAILED, BATCH_FAILED 등)",
    )
    trading_day: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, comment="관련 거래일 (해당되는 경우)"
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="FAILED", comment="상태 (FAILED 고정)"
    )
    details: Mapped[Optional[dict[str, Any]]] = mapped_column(
        JSON, nullable=True, comment="에러 상세 정보 (실패 종목, 에러 메시지, 컨텍스트 등)"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), comment="에러 발생 시각"
    )

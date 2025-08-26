
"""
포인트 시스템 데이터 모델

이 파일은 사용자 포인트의 모든 거래 내역을 저장하는 원장(Ledger) 테이블을 정의합니다.
포인트의 추가/차감은 모두 이 테이블에 기록되어 완전한 감사 추적(Audit Trail)을 제공합니다.
"""

from sqlalchemy import Column, BigInteger, Text, Date, ForeignKey
from sqlalchemy.schema import UniqueConstraint
from myapi.models.base import BaseModel


class PointsLedger(BaseModel):
    """
    포인트 원장 테이블 - 모든 포인트 거래 내역을 저장
    
    이 테이블은 다음 원칙을 따릅니다:
    1. 불변성(Immutable): 한번 생성된 레코드는 수정되지 않음
    2. 완전성(Complete): 모든 포인트 변동사항이 기록됨
    3. 멱등성(Idempotent): ref_id를 통해 중복 처리 방지
    4. 정합성(Integrity): balance_after 필드로 잔액 추적
    
    특징:
    - crypto 스키마에 저장
    - ref_id는 유니크해야 함 (중복 거래 방지)
    - 각 거래마다 거래 후 잔액을 저장하여 빠른 잔액 조회 가능
    """
    
    __tablename__ = 'points_ledger'
    __table_args__ = (
        UniqueConstraint('ref_id'),  # 중복 거래 방지를 위한 유니크 제약
        {'schema': 'crypto'}  # crypto 스키마에 테이블 생성
    )

    # 기본 키 - 자동 증가하는 고유 식별자
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    
    # 사용자 ID - users 테이블과의 외래키 관계
    user_id = Column(BigInteger, ForeignKey('crypto.users.id'), nullable=False)
    
    # 거래일 - 포인트가 적용되는 거래일 (통계 및 리포팅용)
    trading_day = Column(Date)
    
    # 심볼 - 포인트 적용 대상 종목 (예: BTC, ETH 등, 예측 관련 포인트인 경우)
    symbol = Column(Text)
    
    # 포인트 변동량 - 양수면 증가, 음수면 감소
    delta_points = Column(BigInteger, nullable=False)
    
    # 거래 사유 - 포인트 변동 이유 (예: "예측 성공 보상", "예측 수수료" 등)
    reason = Column(Text, nullable=False)
    
    # 참조 ID - 중복 처리 방지용 고유 식별자 (멱등성 보장)
    # 형식 예시: "prediction_123", "admin_adjustment_456_1640995200"
    ref_id = Column(Text, nullable=False)
    
    # 거래 후 잔액 - 이 거래 완료 후의 총 포인트 잔액
    # 이 필드 덕분에 복잡한 SUM 쿼리 없이 빠르게 현재 잔액 조회 가능
    balance_after = Column(BigInteger, nullable=False)

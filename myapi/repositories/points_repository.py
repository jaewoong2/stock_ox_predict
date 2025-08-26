"""
포인트 리포지토리 - 데이터베이스 접근 및 비즈니스 로직

이 파일은 포인트 시스템의 핵심 비즈니스 로직을 담당합니다:
1. 포인트 추가/차감 처리
2. 멱등성 보장 (중복 처리 방지)
3. 잔액 부족 검증
4. 거래 내역 조회
5. 데이터 정합성 검증

핵심 특징:
- 모든 포인트 거래는 ref_id를 통해 중복 처리가 방지됩니다
- 잔액 부족 시 거래가 실패하여 음수 잔액을 방지합니다
- 각 거래 후 새로운 잔액이 계산되어 저장됩니다
"""

from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, func, and_
from sqlalchemy.exc import IntegrityError
from datetime import date, datetime, timezone

from myapi.models.points import PointsLedger as PointsLedgerModel
from myapi.schemas.points import (
    PointsBalanceResponse,
    PointsLedgerEntry,
    PointsLedgerResponse,
    PointsTransactionResponse,
    PointsIntegrityCheckResponse,
)
from myapi.repositories.base import BaseRepository


class PointsRepository(BaseRepository[PointsLedgerModel, PointsLedgerEntry]):
    """
    포인트 리포지토리 - 포인트 관련 모든 데이터베이스 작업 처리
    
    주요 기능:
    1. 멱등성 보장 - ref_id를 통한 중복 거래 방지
    2. 원자성 - 트랜잭션을 통한 데이터 일관성 보장
    3. 성능 최적화 - balance_after를 통한 빠른 잔액 조회
    4. 완전한 감사 추적 - 모든 포인트 변동 기록
    """

    def __init__(self, db: Session):
        super().__init__(PointsLedgerModel, PointsLedgerEntry, db)

    def _to_ledger_entry(self, model_instance: PointsLedgerModel) -> PointsLedgerEntry:
        """
        SQLAlchemy 모델을 Pydantic 스키마로 변환
        
        Args:
            model_instance: 데이터베이스에서 조회한 PointsLedger 모델 인스턴스
            
        Returns:
            PointsLedgerEntry: API 응답용 Pydantic 스키마 객체
            
        Note:
            - delta_points의 부호에 따라 거래 유형(CREDIT/DEBIT) 자동 결정
            - getattr를 사용하여 안전한 속성 접근
        """
        if model_instance is None:
            return None

        # SQLAlchemy 모델의 속성들을 안전하게 추출
        delta_points = getattr(model_instance, "delta_points", 0)
        transaction_type = "CREDIT" if delta_points > 0 else "DEBIT"

        data = {
            "id": getattr(model_instance, "id", 0),
            "transaction_type": transaction_type,
            "delta_points": delta_points,
            "balance_after": getattr(model_instance, "balance_after", 0),
            "reason": getattr(model_instance, "reason", ""),
            "ref_id": getattr(model_instance, "ref_id", ""),
            "created_at": (
                model_instance.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if model_instance.created_at
                else ""
            ),
        }
        return PointsLedgerEntry(**data)

    def get_user_balance(self, user_id: int) -> int:
        """
        사용자의 현재 포인트 잔액 조회 (O(1) 성능)
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            int: 현재 포인트 잔액 (거래 내역이 없으면 0)
            
        Performance:
            - balance_after 필드를 사용하여 최신 거래만 조회
            - SUM 연산 없이 단일 레코드 조회로 O(1) 성능
        """
        latest_entry = (
            self.db.query(self.model_class)
            .filter(self.model_class.user_id == user_id)
            .order_by(desc(self.model_class.id))
            .first()
        )

        return getattr(latest_entry, "balance_after", 0) if latest_entry else 0

    def add_points(
        self,
        user_id: int,
        points: int,
        reason: str,
        ref_id: str,
        trading_day: date = date.today(),
        symbol: str = "",
    ) -> PointsTransactionResponse:
        """포인트 추가 (멱등성 보장)"""
        return self._transact_points(
            user_id, points, reason, ref_id, trading_day, symbol
        )

    def deduct_points(
        self,
        user_id: int,
        points: int,
        reason: str,
        ref_id: str,
        trading_day: date = date.today(),
        symbol: str = "",
    ) -> PointsTransactionResponse:
        """포인트 차감 (멱등성 보장)"""
        return self._transact_points(
            user_id, -points, reason, ref_id, trading_day, symbol
        )

    def _transact_points(
        self,
        user_id: int,
        delta_points: int,
        reason: str,
        ref_id: str,
        trading_day: date = date.today(),
        symbol: str = "",
    ) -> PointsTransactionResponse:
        """
        포인트 거래 처리의 핵심 로직 - 멱등성과 원자성 보장
        
        Args:
            user_id: 대상 사용자 ID
            delta_points: 포인트 변동량 (양수=증가, 음수=감소)
            reason: 거래 사유
            ref_id: 중복 방지용 고유 참조 ID
            trading_day: 거래일
            symbol: 관련 심볼 (선택사항)
            
        Returns:
            PointsTransactionResponse: 거래 결과 (성공/실패, 잔액 정보)
            
        핵심 로직:
        1. ref_id 중복 체크 (멱등성 보장)
        2. 현재 잔액 조회
        3. 잔액 부족 검증 (차감 시)
        4. 새 잔액 계산
        5. 원장에 거래 기록
        6. IntegrityError 처리 (동시성 문제 해결)
        
        멱등성:
        - 동일한 ref_id로 여러 번 호출해도 한 번만 처리됨
        - 기존 거래가 있으면 해당 결과를 반환
        
        원자성:
        - 트랜잭션 내에서 처리되어 부분 실패 방지
        - 에러 발생 시 롤백으로 데이터 일관성 보장
        """
        try:
            # 중복 처리 방지를 위한 ref_id 체크
            existing_entry = (
                self.db.query(self.model_class)
                .filter(self.model_class.ref_id == ref_id)
                .first()
            )

            if existing_entry:
                return PointsTransactionResponse(
                    success=True,
                    transaction_id=getattr(existing_entry, "id", None),
                    delta_points=getattr(existing_entry, "delta_points", 0),
                    balance_after=getattr(existing_entry, "balance_after", 0),
                    message="Transaction already processed (idempotent)",
                )

            # 현재 잔액 조회
            current_balance = self.get_user_balance(user_id)

            # 차감 시 잔액 부족 체크
            if delta_points < 0 and current_balance + delta_points < 0:
                return PointsTransactionResponse(
                    success=False,
                    transaction_id=None,
                    delta_points=0,
                    balance_after=current_balance,
                    message="Insufficient balance",
                )

            # 새 잔액 계산
            new_balance = current_balance + delta_points

            # 원장 항목 생성
            ledger_entry = self.model_class(
                user_id=user_id,
                trading_day=trading_day,
                symbol=symbol,
                delta_points=delta_points,
                reason=reason,
                ref_id=ref_id,
                balance_after=new_balance,
            )

            self.db.add(ledger_entry)
            self.db.flush()
            self.db.refresh(ledger_entry)
            self.db.commit()

            return PointsTransactionResponse(
                success=True,
                transaction_id=getattr(ledger_entry, "id", None),
                delta_points=delta_points,
                balance_after=new_balance,
                message="Transaction completed successfully",
            )

        except IntegrityError as e:
            self.db.rollback()
            # ref_id 중복 에러인 경우 기존 항목 반환
            if "ref_id" in str(e):
                existing_entry = (
                    self.db.query(self.model_class)
                    .filter(self.model_class.ref_id == ref_id)
                    .first()
                )

                if existing_entry:
                    return PointsTransactionResponse(
                        success=True,
                        transaction_id=getattr(existing_entry, "id", None),
                        delta_points=getattr(existing_entry, "delta_points", 0),
                        balance_after=getattr(existing_entry, "balance_after", 0),
                        message="Transaction already processed (idempotent, integrity error handled)",
                    )

            return PointsTransactionResponse(
                success=False,
                transaction_id=None,
                delta_points=0,
                balance_after=self.get_user_balance(user_id),
                message=f"Transaction failed: {str(e)}",
            )

    def get_user_ledger(
        self, user_id: int, limit: int = 50, offset: int = 0
    ) -> PointsLedgerResponse:
        """사용자 포인트 원장 조회 (페이징)"""
        # 총 항목 수 조회
        total_count = (
            self.db.query(self.model_class)
            .filter(self.model_class.user_id == user_id)
            .count()
        )

        # 원장 항목 조회 (최신순)
        model_instances = (
            self.db.query(self.model_class)
            .filter(self.model_class.user_id == user_id)
            .order_by(desc(self.model_class.id))
            .limit(limit)
            .offset(offset)
            .all()
        )

        entries = [self._to_ledger_entry(instance) for instance in model_instances]

        # 현재 잔액 조회
        current_balance = self.get_user_balance(user_id)

        # 다음 페이지 존재 여부
        has_next = offset + limit < total_count

        return PointsLedgerResponse(
            balance=current_balance,
            entries=entries,
            total_count=total_count,
            has_next=has_next,
        )

    def get_balance_response(self, user_id: int) -> PointsBalanceResponse:
        """포인트 잔액 응답"""
        balance = self.get_user_balance(user_id)
        return PointsBalanceResponse(balance=balance)

    def award_prediction_points(
        self,
        user_id: int,
        prediction_id: int,
        points: int,
        trading_day: date,
        symbol: str,
    ) -> PointsTransactionResponse:
        """예측 성공 포인트 지급"""
        ref_id = f"prediction_{prediction_id}"
        reason = f"Correct prediction reward for {symbol}"

        return self.add_points(
            user_id=user_id,
            points=points,
            reason=reason,
            ref_id=ref_id,
            trading_day=trading_day,
            symbol=symbol,
        )

    def charge_prediction_fee(
        self, user_id: int, prediction_id: int, fee: int, trading_day: date, symbol: str
    ) -> PointsTransactionResponse:
        """예측 수수료 차감"""
        ref_id = f"prediction_fee_{prediction_id}"
        reason = f"Prediction fee for {symbol}"

        return self.deduct_points(
            user_id=user_id,
            points=fee,
            reason=reason,
            ref_id=ref_id,
            trading_day=trading_day,
            symbol=symbol,
        )

    def admin_adjust_points(
        self, user_id: int, adjustment: int, reason: str, admin_id: int
    ) -> PointsTransactionResponse:
        """관리자 포인트 조정"""
        ref_id = f"admin_adjustment_{admin_id}_{datetime.now(timezone.utc).timestamp()}"
        admin_reason = f"Admin adjustment by {admin_id}: {reason}"

        return self._transact_points(
            user_id=user_id, delta_points=adjustment, reason=admin_reason, ref_id=ref_id
        )

    def get_transactions_by_date_range(
        self, user_id: int, start_date: date, end_date: date
    ) -> List[PointsLedgerEntry]:
        """날짜 범위별 거래 내역 조회"""
        model_instances = (
            self.db.query(self.model_class)
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day.between(start_date, end_date),
                )
            )
            .order_by(desc(self.model_class.id))
            .all()
        )

        return [self._to_ledger_entry(instance) for instance in model_instances]

    def get_total_points_awarded_today(self, trading_day: date) -> int:
        """특정일 총 지급 포인트 조회"""
        result = (
            self.db.query(func.sum(self.model_class.delta_points))
            .filter(
                and_(
                    self.model_class.trading_day == trading_day,
                    self.model_class.delta_points > 0,  # 지급분만
                )
            )
            .scalar()
        )

        return result or 0

    def verify_integrity_for_user(self, user_id: int) -> PointsIntegrityCheckResponse:
        """
        특정 사용자의 포인트 정합성 검증
        
        검증 방식:
        1. 모든 거래의 delta_points 합계 계산
        2. 최신 거래의 balance_after와 비교
        3. 일치하지 않으면 데이터 무결성 문제 감지
        
        Args:
            user_id: 검증할 사용자 ID
            
        Returns:
            PointsIntegrityCheckResponse: 검증 결과 (OK/MISMATCH)
            
        용도:
        - 데이터 무결성 모니터링
        - 버그 또는 동시성 문제 감지
        - 정기적인 데이터 검증
        """
        # 모든 거래 내역 조회
        entries = (
            self.db.query(self.model_class)
            .filter(self.model_class.user_id == user_id)
            .order_by(asc(self.model_class.id))
            .all()
        )

        if not entries:
            return PointsIntegrityCheckResponse(
                status="OK",
                user_id=user_id,
                calculated_balance=0,
                recorded_balance=0,
                total_balance_from_latest=None,
                total_deltas=None,
                user_count=None,
                total_entries=None,
                entry_count=0,
                error=None,
                entry_id=None,
                verified_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            )

        # 델타 합계로 잔액 계산
        calculated_balance = sum(getattr(entry, "delta_points", 0) for entry in entries)

        # 최신 기록된 잔액
        recorded_balance = getattr(entries[-1], "balance_after", 0)

        status = "OK" if calculated_balance == recorded_balance else "MISMATCH"

        return PointsIntegrityCheckResponse(
            status=status,
            user_id=user_id,
            calculated_balance=calculated_balance,
            recorded_balance=recorded_balance,
            total_balance_from_latest=None,
            total_deltas=None,
            user_count=None,
            total_entries=None,
            entry_count=len(entries),
            error=None,
            entry_id=None,
            verified_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def verify_global_integrity(self) -> PointsIntegrityCheckResponse:
        """
        전체 시스템의 포인트 정합성 검증
        
        검증 방식:
        1. 모든 사용자의 최신 잔액 합계
        2. 모든 거래의 delta_points 총합
        3. 두 값이 일치해야 함 (제로섬 원칙)
        
        Returns:
            PointsIntegrityCheckResponse: 전체 시스템 검증 결과
            
        중요성:
        - 시스템 전체의 포인트 발행량 검증
        - 포인트가 허공에서 생성되거나 소멸되지 않음을 보장
        - 대규모 데이터 손상 감지
        
        성능:
        - 대량 데이터에서는 시간이 걸릴 수 있음
        - 정기적인 배치 작업으로 실행 권장
        """
        # 모든 사용자의 최신 잔액 합계
        latest_balances = (
            self.db.query(func.sum(self.model_class.balance_after))
            .filter(
                self.model_class.id.in_(
                    self.db.query(func.max(self.model_class.id)).group_by(
                        self.model_class.user_id
                    )
                )
            )
            .scalar()
        )

        # 모든 델타의 합계
        total_deltas = self.db.query(func.sum(self.model_class.delta_points)).scalar()

        # 사용자 수
        user_count = self.db.query(
            func.count(func.distinct(self.model_class.user_id))
        ).scalar()

        # 전체 항목 수
        total_entries = self.db.query(func.count(self.model_class.id)).scalar()

        status = "OK" if (latest_balances or 0) == (total_deltas or 0) else "MISMATCH"

        return PointsIntegrityCheckResponse(
            status=status,
            user_id=None,
            calculated_balance=None,
            recorded_balance=None,
            total_balance_from_latest=latest_balances or 0,
            total_deltas=total_deltas or 0,
            user_count=user_count or 0,
            total_entries=total_entries or 0,
            entry_count=None,
            error=None,
            entry_id=None,
            verified_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        )

    def transaction_exists(self, ref_id: str) -> bool:
        """거래 존재 여부 확인 (멱등성 체크용)"""
        return (
            self.db.query(self.model_class)
            .filter(self.model_class.ref_id == ref_id)
            .first()
            is not None
        )

    def get_user_points_earned_today(self, user_id: int, trading_day: date) -> int:
        """사용자가 오늘 획득한 포인트 총합"""
        result = (
            self.db.query(func.sum(self.model_class.delta_points))
            .filter(
                and_(
                    self.model_class.user_id == user_id,
                    self.model_class.trading_day == trading_day,
                    self.model_class.delta_points > 0,  # 획득분만
                )
            )
            .scalar()
        )

        return result or 0

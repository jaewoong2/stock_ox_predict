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
    """포인트 리포지토리 - 멱등성 보장"""

    def __init__(self, db: Session):
        super().__init__(PointsLedgerModel, PointsLedgerEntry, db)

    def _to_ledger_entry(self, model_instance: PointsLedgerModel) -> PointsLedgerEntry:
        """PointsLedger 모델을 PointsLedgerEntry 스키마로 변환"""
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
        """사용자 포인트 잔액 조회"""
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
        """포인트 거래 처리 (멱등성 보장)"""
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
        """사용자별 포인트 정합성 검증"""
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
        """전체 포인트 정합성 검증"""
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

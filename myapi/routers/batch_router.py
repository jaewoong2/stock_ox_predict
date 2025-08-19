import datetime as dt
import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
import logging

from myapi.database.session import get_db
from myapi.services.aws_service import AwsService
from myapi.services.eod_service import EODService
from myapi.services.settlement_service import SettlementService
from myapi.services.session_service import SessionService
from myapi.services.universe_service import UniverseService
from myapi.services.scheduler_service import batch_scheduler
from myapi.api.deps import get_current_admin_user
from myapi.models.user import User
from myapi.config import get_settings
from myapi.schemas.session import SessionPhase

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(
    prefix="/batch", tags=["batch"], dependencies=[Depends(get_current_admin_user)]
)


@router.post("/universe/setup")
async def setup_daily_universe(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    일일 종목 유니버스 설정 및 세션 OPEN 전환
    - 매일 오전 6:00 KST 실행
    """
    try:
        universe_service = UniverseService(db)
        session_service = SessionService(db)
        aws_service = AwsService(settings)

        today = dt.date.today()

        # 1. 기본 종목 목록 설정 (실제로는 더 복잡한 로직)
        default_symbols = [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "TSLA",
            "NVDA",
            "META",
            "NFLX",
            "CRM",
            "UBER",
        ]

        # 2. 종목 유니버스 업데이트
        result = universe_service.update_daily_universe(today, default_symbols)

        # 3. 세션을 OPEN으로 전환
        session_result = session_service.transition_session(SessionPhase.OPEN)

        logger.info(
            f"Daily universe setup completed: {len(default_symbols)} symbols, session: {session_result.current_phase}"
        )

        return {
            "success": True,
            "message": "Daily universe setup completed",
            "universe_count": len(default_symbols),
            "session_phase": session_result.current_phase,
            "symbols": default_symbols,
        }

    except Exception as e:
        logger.error(f"Universe setup failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Universe setup failed: {str(e)}")


@router.post("/session/close")
async def close_prediction_session(
    db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)
):
    """
    예측 세션 마감
    - 매일 오후 10:25 KST 실행
    """
    try:
        session_service = SessionService(db)

        # 세션을 CLOSED로 전환
        result = session_service.transition_session(SessionPhase.CLOSED)

        logger.info(f"Prediction session closed: {result.current_phase}")

        return {
            "success": True,
            "message": "Prediction session closed",
            "session_phase": result.current_phase,
            "closed_at": result.updated_at,
        }

    except Exception as e:
        logger.error(f"Session close failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Session close failed: {str(e)}")


@router.post("/eod/fetch")
async def trigger_eod_fetch(
    symbols: Optional[List[str]] = None,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    EOD 데이터 수집 트리거
    - 매일 오전 6:15 KST 실행
    """
    try:
        eod_service = EODService(db)
        universe_service = UniverseService(db)

        trading_day = dt.date.today()

        # 심볼이 지정되지 않으면 오늘의 유니버스에서 가져오기
        if not symbols:
            universe = universe_service.get_today_universe()
            symbols = [item.symbol for item in universe.symbols] if universe else []

        if not symbols:
            raise HTTPException(
                status_code=400, detail="No symbols found for EOD fetch"
            )

        # EOD 데이터 수집 배치 트리거
        result = eod_service.trigger_eod_fetch_batch(trading_day, symbols)

        logger.info(f"EOD fetch triggered for {len(symbols)} symbols")

        return {
            "success": True,
            "message": "EOD fetch batch triggered",
            "trading_day": trading_day.strftime("%Y-%m-%d"),
            "symbols": symbols,
            "message_id": result.get("message_id"),
        }

    except Exception as e:
        logger.error(f"EOD fetch trigger failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"EOD fetch trigger failed: {str(e)}"
        )


@router.post("/settlement/run")
async def run_settlement(
    trading_day: Optional[str] = None,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    정산 실행
    - 매일 오전 6:30 KST 실행 (EOD 수집 완료 후)
    """
    try:
        settlement_service = SettlementService(db)
        session_service = SessionService(db)

        # 거래일 설정 (기본값: 오늘)
        if trading_day:
            target_date = dt.datetime.strptime(trading_day, "%Y-%m-%d").date()
        else:
            target_date = dt.date.today()

        # 1. 세션을 SETTLING으로 전환
        session_result = session_service.transition_session(SessionPhase.SETTLING)

        # 2. 정산 실행
        settlement_result = settlement_service.run_manual_settlement(target_date)

        logger.info(
            f"Settlement completed for {target_date}: {settlement_result['settled_count']} predictions"
        )

        return {
            "success": True,
            "message": "Settlement completed",
            "trading_day": target_date.strftime("%Y-%m-%d"),
            "session_phase": session_result.current_phase,
            "settled_predictions": settlement_result["settled_count"],
            "settlement_summary": settlement_result,
        }

    except Exception as e:
        logger.error(f"Settlement failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Settlement failed: {str(e)}")


@router.post("/complete-daily-cycle")
async def complete_daily_cycle(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    일일 전체 사이클 완료
    - EOD 수집 → 정산 → 포인트 지급 → 다음날 준비
    """
    try:
        eod_service = EODService(db)
        settlement_service = SettlementService(db)
        session_service = SessionService(db)
        universe_service = UniverseService(db)

        today = dt.date.today()
        results = {}

        # 1. EOD 데이터 확인
        universe = universe_service.get_today_universe()
        symbols = [item.symbol for item in universe.symbols] if universe else []

        if symbols:
            # 2. EOD 데이터 완성도 검증
            eod_validation = eod_service.validate_eod_data_completeness(today, symbols)
            results["eod_validation"] = eod_validation

            # 완성도가 80% 미만이면 재수집 시도
            if eod_validation["completeness_rate"] < 80:
                retry_result = eod_service.retry_failed_fetches(
                    today, eod_validation["missing_symbols"]
                )
                results["eod_retry"] = retry_result

        # 3. 정산 실행
        session_service.transition_session(SessionPhase.SETTLING)
        settlement_result = settlement_service.run_manual_settlement(today)
        results["settlement"] = settlement_result

        logger.info(f"Daily cycle completed for {today}")

        return {
            "success": True,
            "message": "Daily cycle completed successfully",
            "trading_day": today.strftime("%Y-%m-%d"),
            "results": results,
        }

    except Exception as e:
        logger.error(f"Daily cycle completion failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Daily cycle failed: {str(e)}")


@router.get("/status")
async def get_batch_status(
    db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin_user)
):
    """
    배치 작업 상태 조회
    """
    try:
        session_service = SessionService(db)
        universe_service = UniverseService(db)
        eod_service = EODService(db)

        today = dt.date.today()

        # 현재 세션 상태
        session_status = session_service.get_current_session()

        # 오늘의 유니버스
        universe = universe_service.get_today_universe()
        universe_symbols = (
            [item.symbol for item in universe.symbols] if universe else []
        )

        # EOD 데이터 완성도
        eod_status = None
        if universe_symbols:
            eod_status = eod_service.validate_eod_data_completeness(
                today, universe_symbols
            )

        return {
            "success": True,
            "trading_day": today.strftime("%Y-%m-%d"),
            "session": {
                "phase": session_status.current_phase if session_status else None,
                "updated_at": session_status.updated_at if session_status else None,
            },
            "universe": {
                "symbol_count": len(universe_symbols),
                "symbols": universe_symbols,
            },
            "eod_data": eod_status,
        }

    except Exception as e:
        logger.error(f"Batch status check failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Batch status check failed: {str(e)}"
        )


@router.post("/maintenance/cleanup")
async def maintenance_cleanup(
    days_to_keep: int = 90,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user),
):
    """
    오래된 데이터 정리
    - 주간 실행 권장
    """
    try:
        eod_service = EODService(db)

        # EOD 데이터 정리
        deleted_count = eod_service.cleanup_old_eod_data(days_to_keep)

        logger.info(
            f"Maintenance cleanup completed: {deleted_count} old records deleted"
        )

        return {
            "success": True,
            "message": "Maintenance cleanup completed",
            "deleted_eod_records": deleted_count,
            "days_kept": days_to_keep,
        }

    except Exception as e:
        logger.error(f"Maintenance cleanup failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Maintenance cleanup failed: {str(e)}"
        )


# 스케줄러 관련 엔드포인트


@router.get("/scheduler/status")
async def get_scheduler_status(
    date_filter: Optional[str] = None,
    current_admin: User = Depends(get_current_admin_user),
):
    """
    배치 스케줄러 상태 조회
    """
    try:
        # 실행된 작업 상태
        task_status = batch_scheduler.get_task_status(date_filter)

        # 다음 예정된 작업들
        next_tasks = batch_scheduler.get_next_scheduled_tasks()

        return {
            "success": True,
            "scheduler_running": batch_scheduler.running,
            "executed_tasks": task_status,
            "next_scheduled_tasks": next_tasks,
        }

    except Exception as e:
        logger.error(f"Scheduler status check failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Scheduler status check failed: {str(e)}"
        )


@router.post("/scheduler/start")
async def start_scheduler(
    background_tasks: BackgroundTasks,
    current_admin: User = Depends(get_current_admin_user),
):
    """
    배치 스케줄러 시작
    """
    try:
        if batch_scheduler.running:
            return {"success": True, "message": "Scheduler is already running"}

        background_tasks.add_task(batch_scheduler.start_scheduler)

        return {"success": True, "message": "Batch scheduler started successfully"}

    except Exception as e:
        logger.error(f"Scheduler start failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scheduler start failed: {str(e)}")


@router.post("/scheduler/stop")
async def stop_scheduler(current_admin: User = Depends(get_current_admin_user)):
    """
    배치 스케줄러 중지
    """
    try:
        batch_scheduler.stop_scheduler()

        return {"success": True, "message": "Batch scheduler stopped successfully"}

    except Exception as e:
        logger.error(f"Scheduler stop failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Scheduler stop failed: {str(e)}")


@router.get("/scheduler/next-tasks")
async def get_next_scheduled_tasks(
    current_admin: User = Depends(get_current_admin_user),
):
    """
    다음 예정된 배치 작업들 조회
    """
    try:
        next_tasks = batch_scheduler.get_next_scheduled_tasks()

        return {"success": True, "next_tasks": next_tasks}

    except Exception as e:
        logger.error(f"Next tasks check failed: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Next tasks check failed: {str(e)}"
        )

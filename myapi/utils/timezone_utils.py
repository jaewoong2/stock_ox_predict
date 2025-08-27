"""
타임존 유틸리티

한국 시간(KST) 기준 시간 처리를 위한 유틸리티 함수들
"""

from datetime import datetime, timezone, timedelta
from typing import Optional

# 한국 표준시 (KST = UTC+9)
KST = timezone(timedelta(hours=9))


def get_kst_now() -> datetime:
    """현재 KST 시간을 반환합니다."""
    return datetime.now(KST)


def get_current_kst_date():
    """현재 KST 날짜를 반환합니다."""
    return get_kst_now().date()


def get_current_kst_time():
    """현재 KST 시간을 반환합니다."""
    return get_kst_now()


def to_kst(dt: datetime) -> datetime:
    """UTC 또는 다른 타임존의 datetime을 KST로 변환합니다."""
    if dt.tzinfo is None:
        # naive datetime은 UTC로 가정
        dt = dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(KST)


def to_utc(dt: datetime) -> datetime:
    """KST 또는 다른 타임존의 datetime을 UTC로 변환합니다."""
    if dt.tzinfo is None:
        # naive datetime은 KST로 가정
        dt = dt.replace(tzinfo=KST)
    
    return dt.astimezone(timezone.utc)


def kst_to_utc_timestamp(kst_dt: datetime) -> int:
    """KST datetime을 UTC 타임스탬프로 변환합니다."""
    if kst_dt.tzinfo is None:
        kst_dt = kst_dt.replace(tzinfo=KST)
    
    utc_dt = kst_dt.astimezone(timezone.utc)
    return int(utc_dt.timestamp())


def is_market_hours_kst(dt: Optional[datetime] = None) -> bool:
    """
    KST 기준으로 예측 가능 시간(06:00-23:59)인지 확인합니다.
    
    Args:
        dt: 확인할 datetime (None이면 현재 시간)
        
    Returns:
        bool: 예측 가능 시간 여부
    """
    if dt is None:
        dt = get_kst_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    else:
        dt = dt.astimezone(KST)
    
    hour = dt.hour
    minute = dt.minute
    
    # 06:00 이상 23:59 이하
    if hour < 6:
        return False
    elif hour >= 24:
        return False
    elif hour == 23 and minute > 59:
        return False
    
    return True


def get_next_settlement_time_kst() -> datetime:
    """다음 정산 시간(06:00 KST)을 반환합니다."""
    now = get_kst_now()
    
    # 오늘 06:00
    today_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)
    
    if now < today_6am:
        return today_6am
    else:
        # 내일 06:00
        tomorrow = now + timedelta(days=1)
        return tomorrow.replace(hour=6, minute=0, second=0, microsecond=0)


def get_session_end_time_kst() -> datetime:
    """오늘의 세션 종료 시간(23:59 KST)을 반환합니다."""
    now = get_kst_now()
    return now.replace(hour=23, minute=59, second=0, microsecond=0)


def format_kst_time(dt: datetime, include_date: bool = True) -> str:
    """KST datetime을 한국어 포맷으로 출력합니다."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=KST)
    else:
        dt = dt.astimezone(KST)
    
    if include_date:
        return dt.strftime("%Y년 %m월 %d일 %H:%M:%S KST")
    else:
        return dt.strftime("%H:%M:%S KST")
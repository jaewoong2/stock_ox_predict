from datetime import date, datetime, time, timedelta
from typing import Optional, Tuple
import pytz


class USMarketHours:
    """미국 증시 거래 시간 및 거래일 판단 유틸리티 (ET/KST)"""

    US_HOLIDAYS_2025 = {
        date(2025, 1, 1),   # New Year's Day
        date(2025, 1, 20),  # Martin Luther King Jr. Day
        date(2025, 2, 17),  # Presidents' Day
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 26),  # Memorial Day
        date(2025, 6, 19),  # Juneteenth
        date(2025, 7, 4),   # Independence Day
        date(2025, 9, 1),   # Labor Day
        date(2025, 11, 27), # Thanksgiving Day
        date(2025, 12, 25), # Christmas Day
    }
    ET_TZ = pytz.timezone("America/New_York")
    KST_TZ = pytz.timezone("Asia/Seoul")
    MARKET_OPEN_TIME = time(9, 30)
    MARKET_CLOSE_TIME = time(16, 0)

    @classmethod
    def get_current_et_time(cls) -> datetime:
        """현재 미국 동부(ET) 시간을 타임존 정보와 함께 반환"""
        return datetime.now(cls.ET_TZ)

    @classmethod
    def get_current_kst_time(cls) -> datetime:
        """현재 한국(KST) 시간을 타임존 정보와 함께 반환"""
        return datetime.now(cls.KST_TZ)

    @classmethod
    def is_us_trading_day(cls, check_date: date) -> bool:
        """주어진 날짜(ET 기준)가 미국 증시 거래일인지 확인"""
        if check_date.weekday() >= 5:  # 주말 (토, 일) 제외
            return False
        if check_date in cls.US_HOLIDAYS_2025:  # 공휴일 제외
            return False
        return True

    @classmethod
    def get_market_open_close_kst(cls, trading_date: date) -> Tuple[datetime, datetime]:
        """특정 거래일(ET 기준)의 개장/마감 시간을 KST로 변환하여 반환"""
        if not cls.is_us_trading_day(trading_date):
            raise ValueError(f"{trading_date}는 거래일이 아닙니다.")

        # ET 기준 개장/마감 시간 생성
        et_open = cls.ET_TZ.localize(datetime.combine(trading_date, cls.MARKET_OPEN_TIME))
        et_close = cls.ET_TZ.localize(datetime.combine(trading_date, cls.MARKET_CLOSE_TIME))

        # KST로 변환
        kst_open = et_open.astimezone(cls.KST_TZ)
        kst_close = et_close.astimezone(cls.KST_TZ)

        return kst_open, kst_close

    @classmethod
    def get_prediction_session_kst(cls, trading_date: date) -> Tuple[datetime, datetime]:
        """특정 거래일의 예측 세션 시간(KST)을 반환 (06:00 ~ 23:59)"""
        # 예측 세션은 KST 기준으로 해당 거래일의 06:00부터 23:59까지
        session_start = cls.KST_TZ.localize(datetime.combine(trading_date, time(6, 0)))
        session_end = cls.KST_TZ.localize(datetime.combine(trading_date, time(23, 59, 59)))
        return session_start, session_end

    @classmethod
    def get_kst_trading_day(cls) -> date:
        """
        현재 KST 시간을 기준으로 미국 증시의 '거래일'을 반환합니다.
        KST 00:00 ~ 06:00는 전날 거래일에 속합니다.
        """
        current_kst = cls.get_current_kst_time()
        if current_kst.time() < time(6, 0):
            return current_kst.date() - timedelta(days=1)
        return current_kst.date()

    @classmethod
    def is_prediction_window(cls) -> bool:
        """
        현재 KST 시간이 예측 가능한 시간 창(06:00-23:59)에 있는지 확인합니다.
        """
        current_kst = cls.get_current_kst_time()
        start_time, end_time = cls.get_prediction_session_kst(current_kst.date())
        return start_time <= current_kst <= end_time

    @classmethod
    def get_next_trading_day(cls, from_date: date) -> date:
        """주어진 날짜(ET 기준)로부터 가장 가까운 다음 거래일을 찾습니다."""
        next_day = from_date + timedelta(days=1)
        while not cls.is_us_trading_day(next_day):
            next_day += timedelta(days=1)
        return next_day

    @classmethod
    def get_prev_trading_day(cls, from_date: date) -> date:
        """주어진 날짜(ET 기준)로부터 가장 가까운 이전 거래일을 찾습니다."""
        prev_day = from_date - timedelta(days=1)
        while not cls.is_us_trading_day(prev_day):
            prev_day -= timedelta(days=1)
        return prev_day

    @classmethod
    def get_market_status(cls, check_date: date):
        """특정 날짜의 시장 상태 정보를 반환합니다."""
        from myapi.schemas.market import MarketStatusResponse
        is_trading_day = cls.is_us_trading_day(check_date)
        current_kst = cls.get_current_kst_time()
        
        if not is_trading_day:
            if check_date.weekday() >= 5:
                message = f"{check_date.strftime('%Y-%m-%d')} is weekend (No trading)"
            else:
                message = f"{check_date.strftime('%Y-%m-%d')} is US holiday (No trading)"
        else:
            # 거래일인 경우 예측 가능 시간대인지 확인
            if cls.is_prediction_window():
                message = f"{check_date.strftime('%Y-%m-%d')} is trading day (Predictions open)"
            else:
                message = f"{check_date.strftime('%Y-%m-%d')} is trading day (Predictions closed)"
        
        return MarketStatusResponse(
            is_trading_day=is_trading_day,
            message=message,
            current_kst=current_kst.strftime("%Y-%m-%d %H:%M:%S"),
            is_prediction_window=cls.is_prediction_window() if is_trading_day else False,
        )

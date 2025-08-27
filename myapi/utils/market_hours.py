from datetime import date, datetime, time
from typing import Optional
import pytz


class USMarketHours:
    """미국 증시 거래 시간 및 거래일 판단 유틸리티 (KST 기준)"""

    # 미국 증시 공휴일 2025
    US_HOLIDAYS_2025 = {
        date(2025, 1, 1),  # New Year's Day
        date(2025, 1, 20),  # Martin Luther King Jr. Day (3rd Monday in January)
        date(2025, 2, 17),  # Presidents Day (3rd Monday in February)
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 26),  # Memorial Day (last Monday in May)
        date(2025, 6, 19),  # Juneteenth National Independence Day
        date(2025, 7, 4),  # Independence Day
        date(2025, 9, 1),  # Labor Day (1st Monday in September)
        date(2025, 11, 27),  # Thanksgiving Day (4th Thursday in November)
        date(2025, 12, 25),  # Christmas Day
    }

    @classmethod
    def is_us_trading_day(cls, check_date: date) -> bool:
        """
        주어진 날짜가 미국 증시 거래일인지 확인

        Args:
            check_date: 확인할 날짜

        Returns:
            bool: 거래일이면 True, 아니면 False
        """
        # 주말 제외 (토요일=5, 일요일=6)
        if check_date.weekday() >= 5:
            return False

        # 미국 공휴일 제외
        if check_date in cls.US_HOLIDAYS_2025:
            return False

        return True

    @classmethod
    def get_market_open_close_kst(cls, trading_date: date) -> tuple[datetime, datetime]:
        """
        미국 증시 개장/마감 시간을 KST로 반환

        Args:
            trading_date: 거래일

        Returns:
            tuple: (개장시간 KST, 마감시간 KST)
        """
        # 미국 동부시간 기준 9:30 AM - 4:00 PM
        # 서머타임 고려 (3월 둘째주 일요일 ~ 11월 첫째주 일요일)

        # 간단한 서머타임 판단 (실제로는 더 정확한 로직 필요)
        is_dst = cls._is_dst(trading_date)

        if is_dst:
            # 서머타임: EDT (UTC-4) -> KST는 UTC+9이므로 +13시간
            market_open_kst = datetime.combine(trading_date, time(22, 30))  # 전날 22:30
            market_close_kst = datetime.combine(trading_date, time(5, 0))  # 당일 05:00
        else:
            # 표준시간: EST (UTC-5) -> KST는 UTC+9이므로 +14시간
            market_open_kst = datetime.combine(trading_date, time(23, 30))  # 전날 23:30
            market_close_kst = datetime.combine(trading_date, time(6, 0))  # 당일 06:00

        return market_open_kst, market_close_kst

    @classmethod
    def _is_dst(cls, check_date: date) -> bool:
        """
        서머타임 여부 판단 (간소화된 버전)
        실제로는 더 정확한 로직이 필요함
        """
        # 대략 3월 중순 ~ 11월 초순이 서머타임
        if check_date.month >= 4 and check_date.month <= 10:
            return True
        elif check_date.month == 3 and check_date.day >= 15:
            return True
        elif check_date.month == 11 and check_date.day <= 7:
            return True
        return False

    @classmethod
    def get_current_kst_time(cls) -> datetime:
        """현재 KST 시간 반환"""
        kst = pytz.timezone("Asia/Seoul")
        return datetime.now(kst).replace(tzinfo=None)

    @classmethod
    def is_market_session_valid(cls, trading_date: date) -> dict:
        """
        세션이 유효한지 종합 판단

        Returns:
            dict: {
                'is_valid': bool,
                'is_trading_day': bool,
                'is_before_open': bool,
                'is_after_close': bool,
                'message': str
            }
        """
        current_kst = cls.get_current_kst_time()
        current_date = current_kst.date()

        # 거래일 확인
        if not cls.is_us_trading_day(trading_date):
            return {
                "is_valid": False,
                "is_trading_day": False,
                "is_before_open": False,
                "is_after_close": False,
                "message": f"{trading_date}는 미국 증시 휴장일입니다.",
            }

        market_open, market_close = cls.get_market_open_close_kst(trading_date)

        # 시간 판단
        if current_kst < market_open:
            return {
                "is_valid": True,
                "is_trading_day": True,
                "is_before_open": True,
                "is_after_close": False,
                "message": f'장 개장 전입니다. 개장시간: {market_open.strftime("%H:%M")}',
            }
        elif current_kst > market_close:
            return {
                "is_valid": False,
                "is_trading_day": True,
                "is_before_open": False,
                "is_after_close": True,
                "message": f'장 마감 후입니다. 마감시간: {market_close.strftime("%H:%M")}',
            }
        else:
            return {
                "is_valid": True,
                "is_trading_day": True,
                "is_before_open": False,
                "is_after_close": False,
                "message": "장 운영 중입니다.",
            }

    @classmethod
    def get_next_trading_day(cls, from_date: Optional[date] = None) -> date:
        """다음 거래일 반환"""
        if from_date is None:
            from_date = cls.get_current_kst_time().date()

        next_date = from_date
        while True:
            next_date = date(next_date.year, next_date.month, next_date.day + 1)
            if cls.is_us_trading_day(next_date):
                return next_date

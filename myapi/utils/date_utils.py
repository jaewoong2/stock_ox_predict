from datetime import date, datetime
from typing import Optional, Union, Any
import logging

# 로거 설정
logger = logging.getLogger(__name__)


def to_date(value: Any) -> Optional[date]:
    """
    SQLAlchemy Date 컬럼 값을 안전하게 Python date 타입으로 변환

    Args:
        value: 변환할 값 (datetime, date, str, None 등)

    Returns:
        Optional[date]: 변환된 date 객체 또는 None

    Examples:
        >>> to_date(datetime(2023, 12, 25, 10, 30))
        date(2023, 12, 25)

        >>> to_date(date(2023, 12, 25))
        date(2023, 12, 25)

        >>> to_date("2023-12-25")
        date(2023, 12, 25)

        >>> to_date(None)
        None
    """
    try:
        # None 체크
        if value is None:
            return None

        # 이미 date 타입인 경우
        if isinstance(value, date) and not isinstance(value, datetime):
            return value

        # datetime 타입인 경우
        if isinstance(value, datetime):
            return value.date()

        # 문자열인 경우
        if isinstance(value, str):
            # 빈 문자열 체크
            if not value.strip():
                return None

            # ISO 형식 파싱 시도
            try:
                # YYYY-MM-DD 형식
                if len(value) == 10 and value.count("-") == 2:
                    year, month, day = map(int, value.split("-"))
                    return date(year, month, day)

                # datetime 문자열을 파싱 후 date 추출
                parsed_datetime = datetime.fromisoformat(value.replace("Z", "+00:00"))
                return parsed_datetime.date()

            except ValueError:
                logger.warning(f"날짜 문자열 파싱 실패: {value}")
                return None

        # 기타 타입 (숫자 등)
        logger.warning(f"지원하지 않는 타입: {type(value)} - {value}")
        return None

    except Exception as e:
        logger.error(f"날짜 변환 중 오류 발생: {e} - 입력값: {value}")
        return None


def to_date_string(value: Any, format: str = "%Y-%m-%d") -> Optional[str]:
    """
    SQLAlchemy Date 컬럼 값을 안전하게 문자열로 변환

    Args:
        value: 변환할 값
        format: 날짜 포맷 (기본값: "%Y-%m-%d")

    Returns:
        Optional[str]: 포맷된 날짜 문자열 또는 None

    Examples:
        >>> to_date_string(datetime(2023, 12, 25))
        "2023-12-25"

        >>> to_date_string(date(2023, 12, 25), "%Y/%m/%d")
        "2023/12/25"
    """
    try:
        converted_date = to_date(value)
        return converted_date.strftime(format) if converted_date else None
    except Exception as e:
        logger.error(f"날짜 문자열 변환 중 오류 발생: {e} - 입력값: {value}")
        return None


def safe_date_comparison(date1: Any, date2: Any) -> Optional[int]:
    """
    두 날짜를 안전하게 비교

    Args:
        date1, date2: 비교할 날짜 값들

    Returns:
        Optional[int]: -1 (date1 < date2), 0 (같음), 1 (date1 > date2), None (비교 불가)

    Examples:
        >>> safe_date_comparison("2023-12-25", date(2023, 12, 24))
        1
    """
    try:
        d1 = to_date(date1)
        d2 = to_date(date2)

        if d1 is None or d2 is None:
            return None

        if d1 < d2:
            return -1
        elif d1 > d2:
            return 1
        else:
            return 0

    except Exception as e:
        logger.error(f"날짜 비교 중 오류 발생: {e}")
        return None


class DateConverter:
    """날짜 변환을 위한 클래스 기반 유틸"""

    @staticmethod
    def convert_model_dates(model_instance: Any, date_fields: list[str]) -> dict:
        """
        SQLAlchemy 모델 인스턴스의 여러 날짜 필드를 한번에 변환

        Args:
            model_instance: SQLAlchemy 모델 인스턴스
            date_fields: 변환할 날짜 필드명 리스트

        Returns:
            dict: 변환된 날짜 필드들의 딕셔너리

        Example:
            >>> user = session.query(User).first()
            >>> dates = DateConverter.convert_model_dates(user, ['created_at', 'updated_at', 'birth_date'])
        """
        result = {}

        for field_name in date_fields:
            try:
                if hasattr(model_instance, field_name):
                    field_value = getattr(model_instance, field_name)
                    result[field_name] = to_date(field_value)
                else:
                    logger.warning(f"모델에 '{field_name}' 필드가 존재하지 않습니다.")
                    result[field_name] = None

            except Exception as e:
                logger.error(f"필드 '{field_name}' 변환 중 오류: {e}")
                result[field_name] = None

        return result

    @staticmethod
    def bulk_convert(data_list: list[dict], date_fields: list[str]) -> list[dict]:
        """
        딕셔너리 리스트의 날짜 필드들을 일괄 변환

        Args:
            data_list: 변환할 딕셔너리 리스트
            date_fields: 변환할 날짜 필드명 리스트

        Returns:
            list[dict]: 날짜가 변환된 딕셔너리 리스트
        """
        result = []

        for data in data_list:
            converted_data = data.copy()

            for field_name in date_fields:
                if field_name in converted_data:
                    converted_data[field_name] = to_date(converted_data[field_name])

            result.append(converted_data)

        return result

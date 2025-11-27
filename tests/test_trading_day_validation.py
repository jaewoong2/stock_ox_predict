"""
Trading Day Validation Tests

Tests for trading day validation dependencies and exception handling.
"""

import pytest
from datetime import date, timedelta
from fastapi import Request
from fastapi.datastructures import QueryParams

from myapi.deps import require_trading_day, require_current_trading_day, _get_day_type
from myapi.core.exceptions import NonTradingDayError
from myapi.utils.market_hours import USMarketHours


class MockRequest:
    """Mock Request object for testing dependencies"""

    def __init__(self, trading_day: str = ""):
        self.query_params = QueryParams({"trading_day": trading_day} if trading_day else {})


class TestDayTypeHelper:
    """Tests for _get_day_type helper function"""

    def test_weekend_saturday(self):
        """Test that Saturday is identified as weekend"""
        # 2025-11-29 is Saturday
        saturday = date(2025, 11, 29)
        assert _get_day_type(saturday) == "weekend"

    def test_weekend_sunday(self):
        """Test that Sunday is identified as weekend"""
        # 2025-11-30 is Sunday
        sunday = date(2025, 11, 30)
        assert _get_day_type(sunday) == "weekend"

    def test_holiday_thanksgiving(self):
        """Test that Thanksgiving is identified as holiday"""
        # 2025-11-27 is Thanksgiving
        thanksgiving = date(2025, 11, 27)
        assert _get_day_type(thanksgiving) == "holiday"

    def test_holiday_christmas(self):
        """Test that Christmas is identified as holiday"""
        # 2025-12-25 is Christmas
        christmas = date(2025, 12, 25)
        assert _get_day_type(christmas) == "holiday"

    def test_trading_day(self):
        """Test that normal weekday is identified as trading"""
        # 2025-11-28 is Friday (day after Thanksgiving, normal trading day)
        friday = date(2025, 11, 28)
        assert _get_day_type(friday) == "trading"


class TestRequireTradingDay:
    """Tests for require_trading_day dependency"""

    def test_valid_trading_day(self):
        """Test that valid trading day passes validation"""
        # 2025-11-28 is Friday (normal trading day)
        request = MockRequest("2025-11-28")
        result = require_trading_day(request)
        assert result == date(2025, 11, 28)

    def test_thanksgiving_raises_error(self):
        """Test that Thanksgiving raises NonTradingDayError"""
        # 2025-11-27 is Thanksgiving
        request = MockRequest("2025-11-27")
        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value
        assert error.status_code == 422
        assert error.error_code == "NON_TRADING_DAY"
        assert "2025-11-27" in error.message
        assert "holiday" in error.message
        assert error.details["requested_date"] == "2025-11-27"
        assert error.details["day_type"] == "holiday"
        assert error.details["next_trading_day"] == "2025-11-28"

    def test_weekend_saturday_raises_error(self):
        """Test that Saturday raises NonTradingDayError"""
        # 2025-11-29 is Saturday
        request = MockRequest("2025-11-29")
        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value
        assert error.details["day_type"] == "weekend"
        assert error.details["next_trading_day"] == "2025-12-01"  # Monday

    def test_weekend_sunday_raises_error(self):
        """Test that Sunday raises NonTradingDayError"""
        # 2025-11-30 is Sunday
        request = MockRequest("2025-11-30")
        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value
        assert error.details["day_type"] == "weekend"
        assert error.details["next_trading_day"] == "2025-12-01"  # Monday

    def test_invalid_date_format_raises_error(self):
        """Test that invalid date format raises NonTradingDayError"""
        request = MockRequest("invalid-date")
        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value
        assert error.details["day_type"] == "invalid_format"

    def test_past_trading_day_allowed(self):
        """Test that past trading days are allowed"""
        # 2025-01-02 is Thursday (past trading day)
        request = MockRequest("2025-01-02")
        result = require_trading_day(request)
        assert result == date(2025, 1, 2)

    def test_no_parameter_uses_current_kst_day(self):
        """Test that no parameter defaults to current KST trading day"""
        request = MockRequest("")
        result = require_trading_day(request)
        # Result should be a valid date (actual validation depends on current date)
        assert isinstance(result, date)


class TestUSMarketHours:
    """Tests for USMarketHours utility functions with caching"""

    def test_is_us_trading_day_cache(self):
        """Test that is_us_trading_day caching works"""
        test_date = date(2025, 11, 28)

        # First call
        result1 = USMarketHours.is_us_trading_day(test_date)
        # Second call (should use cache)
        result2 = USMarketHours.is_us_trading_day(test_date)

        assert result1 == result2 == True

    def test_get_next_trading_day_after_thanksgiving(self):
        """Test getting next trading day after Thanksgiving"""
        thanksgiving = date(2025, 11, 27)  # Thursday
        next_day = USMarketHours.get_next_trading_day(thanksgiving)
        assert next_day == date(2025, 11, 28)  # Friday

    def test_get_next_trading_day_after_weekend(self):
        """Test getting next trading day after weekend"""
        friday = date(2025, 11, 28)
        next_day = USMarketHours.get_next_trading_day(friday)
        assert next_day == date(2025, 12, 1)  # Monday (skips Sat/Sun)

    def test_get_next_trading_day_cache(self):
        """Test that get_next_trading_day caching works"""
        test_date = date(2025, 11, 27)

        # First call
        result1 = USMarketHours.get_next_trading_day(test_date)
        # Second call (should use cache)
        result2 = USMarketHours.get_next_trading_day(test_date)

        assert result1 == result2 == date(2025, 11, 28)


class TestHolidayEdgeCases:
    """Tests for various US holidays in 2025"""

    @pytest.mark.parametrize(
        "holiday_date,holiday_name",
        [
            (date(2025, 1, 1), "New Year's Day"),
            (date(2025, 1, 20), "MLK Jr. Day"),
            (date(2025, 2, 17), "Presidents' Day"),
            (date(2025, 4, 18), "Good Friday"),
            (date(2025, 5, 26), "Memorial Day"),
            (date(2025, 6, 19), "Juneteenth"),
            (date(2025, 7, 4), "Independence Day"),
            (date(2025, 9, 1), "Labor Day"),
            (date(2025, 11, 27), "Thanksgiving"),
            (date(2025, 12, 25), "Christmas"),
        ],
    )
    def test_all_holidays_raise_error(self, holiday_date, holiday_name):
        """Test that all US holidays raise NonTradingDayError"""
        request = MockRequest(str(holiday_date))
        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value
        assert error.details["day_type"] == "holiday"
        assert error.details["requested_date"] == str(holiday_date)


class TestErrorResponseStructure:
    """Tests for error response structure compliance"""

    def test_error_response_has_required_fields(self):
        """Test that NonTradingDayError response has all required fields"""
        request = MockRequest("2025-11-27")  # Thanksgiving

        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value

        # Check status code
        assert error.status_code == 422

        # Check error structure (as defined in BaseAPIException)
        assert hasattr(error, "detail")
        detail = error.detail

        assert detail["success"] is False
        assert "error" in detail

        error_obj = detail["error"]
        assert error_obj["code"] == "NON_TRADING_DAY"
        assert "message" in error_obj
        assert "details" in error_obj

        # Check details structure
        details = error_obj["details"]
        assert "requested_date" in details
        assert "day_type" in details
        assert "next_trading_day" in details

    def test_error_message_is_human_readable(self):
        """Test that error message is human-readable"""
        request = MockRequest("2025-11-27")

        with pytest.raises(NonTradingDayError) as exc_info:
            require_trading_day(request)

        error = exc_info.value
        message = error.message

        # Message should contain date and reason
        assert "2025-11-27" in message
        assert "holiday" in message
        assert "trading day" in message.lower()

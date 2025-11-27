# Trading Day Validation Middleware Implementation Plan

## Executive Summary

This plan addresses the 404 error issue on `/prices/trading-day-summary` endpoint during non-trading days (e.g., Thanksgiving 2025-11-27). The solution implements a **dependency injection-based validator** rather than global middleware, providing granular control over which endpoints require trading day validation.

## Problem Analysis

### Current Behavior
- `/prices/trading-day-summary` returns 404 (NotFoundError) on holidays
- Error occurs because `price_service.get_trading_day_price_summary()` cannot find universe data
- No data exists for non-trading days, causing service layer to raise NotFoundError

### Root Cause
```python
# myapi/routers/price_router.py:88
summaries = price_service.get_trading_day_price_summary(
    trading_day=day, symbols=symbol_list
)
# If no universe exists for the date, NotFoundError is raised
```

## Recommended Approach: Dependency Injection Pattern

### Why Dependency Injection > Middleware

**Advantages:**
1. **Granular Control**: Apply to specific endpoints, not all requests
2. **Reusable**: Inject into any router that needs trading day validation
3. **Composable**: Combine with existing dependencies (auth, services)
4. **FastAPI Native**: Follows framework best practices
5. **Testable**: Easy to mock and unit test
6. **Performance**: No overhead on endpoints that don't need it

**Disadvantages of Middleware:**
- Executes on EVERY request (inefficient)
- Requires URL pattern matching (fragile)
- Harder to configure per-endpoint exceptions
- Adds latency to unrelated endpoints

## Implementation Design

### 1. Scope Analysis: Which Endpoints Need Validation?

#### Endpoints That MUST Block Non-Trading Days
```python
# Price endpoints querying trading day data
GET  /prices/trading-day-summary          # Main issue - queries universe data
GET  /prices/universe/{trading_day}       # Requires universe existence
POST /prices/collect-eod/{trading_day}    # Collects EOD data (admin)
GET  /prices/admin/validate-settlement/{trading_day}  # Requires EOD data

# Universe endpoints
GET  /universe/today                      # Queries today's universe
GET  /universe/today/with-prices          # Requires universe + prices
POST /universe/refresh-prices             # Refreshes trading day prices

# Session endpoints (prediction-related)
POST /session/flip-to-predict             # Already has trading day check ✅
POST /session/cutoff                      # Session management

# Prediction endpoints
POST /predictions/{symbol}                # Submit prediction (needs active universe)

# Settlement endpoints
POST /settlement/admin/settle/{trading_day}  # Requires trading day data
```

#### Endpoints That Should ALLOW Non-Trading Days
```python
# Informational endpoints
GET  /session/today                       # Returns market_status (always works)
GET  /session/prediction-status           # Info about prediction window
GET  /session/can-predict                 # Returns boolean (no error)

# Historical/reference data
GET  /prices/current/{symbol}             # Real-time price (yfinance)
GET  /prices/eod/{symbol}/{trading_day}   # Historical lookup (might exist)

# Admin/batch operations
POST /batch/universe/setup-next-day       # Admin tools (bypass validation)
GET  /admin/*                             # Admin endpoints (bypass validation)
```

### 2. HTTP Status Code Decision

**Recommended: 422 Unprocessable Entity**

**Rationale:**
- Request syntax is valid (not 400 Bad Request)
- Date format is correct but semantically invalid for operation
- Server understands request but cannot process it due to business rule violation
- Not a server error (not 503 Service Unavailable)

**Alternative Considered:**
- **400 Bad Request**: Too generic, implies client syntax error
- **503 Service Unavailable**: Implies temporary service outage (misleading)
- **409 Conflict**: Implies resource state conflict (not quite right)

**Response Format:**
```json
{
  "success": false,
  "error": {
    "code": "NON_TRADING_DAY",
    "message": "2025-11-27 is not a US trading day (Thanksgiving)",
    "details": {
      "requested_date": "2025-11-27",
      "day_type": "holiday",
      "next_trading_day": "2025-11-29",
      "is_trading_day": false
    }
  }
}
```

### 3. Architecture Components

#### 3.1 Custom Exception
**File:** `myapi/core/exceptions.py`

```python
class NonTradingDayError(BaseAPIException):
    """Raised when operation requires a trading day but date is weekend/holiday"""
    def __init__(
        self, 
        requested_date: date,
        next_trading_day: date,
        day_type: str = "non-trading day",
        details: Optional[Dict] = None
    ):
        message = f"{requested_date.strftime('%Y-%m-%d')} is not a US trading day ({day_type})"
        
        error_details = {
            "requested_date": requested_date.isoformat(),
            "day_type": day_type,
            "next_trading_day": next_trading_day.isoformat(),
            "is_trading_day": False,
            **(details or {})
        }
        
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code="NON_TRADING_DAY",
            message=message,
            details=error_details
        )
```

#### 3.2 Dependency Validators
**File:** `myapi/deps.py`

```python
def validate_trading_day(
    trading_day: Optional[str] = None,
    allow_past: bool = True,
    allow_future: bool = False,
) -> date:
    """
    Validates that a date is a US trading day.
    
    Args:
        trading_day: Date string (YYYY-MM-DD) or None for today
        allow_past: Allow historical trading days (default: True)
        allow_future: Allow future trading days (default: False)
    
    Returns:
        date: Validated trading day
        
    Raises:
        NonTradingDayError: If date is weekend/holiday
        ValidationError: If date format is invalid
    """
    from myapi.utils.market_hours import USMarketHours
    from myapi.core.exceptions import NonTradingDayError, ValidationError
    
    # Parse date
    try:
        target_date = (
            date.fromisoformat(trading_day) 
            if trading_day 
            else USMarketHours.get_kst_trading_day()
        )
    except ValueError as e:
        raise ValidationError(
            message=f"Invalid date format: {trading_day}",
            details={"expected_format": "YYYY-MM-DD"}
        )
    
    # Check if trading day
    if not USMarketHours.is_us_trading_day(target_date):
        day_type = "weekend" if target_date.weekday() >= 5 else "holiday"
        next_trading_day = USMarketHours.get_next_trading_day(target_date)
        
        raise NonTradingDayError(
            requested_date=target_date,
            next_trading_day=next_trading_day,
            day_type=day_type
        )
    
    # Check past/future constraints
    today = USMarketHours.get_kst_trading_day()
    
    if not allow_past and target_date < today:
        raise ValidationError(
            message=f"Historical dates not allowed: {target_date}",
            details={"requested_date": target_date.isoformat()}
        )
    
    if not allow_future and target_date > today:
        raise ValidationError(
            message=f"Future dates not allowed: {target_date}",
            details={"requested_date": target_date.isoformat()}
        )
    
    return target_date


def require_trading_day(
    trading_day: Optional[str] = None
) -> date:
    """
    Strict trading day validation (no past/future restrictions).
    Use for endpoints that work with any trading day.
    """
    return validate_trading_day(trading_day, allow_past=True, allow_future=True)


def require_current_trading_day(
    trading_day: Optional[str] = None
) -> date:
    """
    Strict validation: must be today's trading day only.
    Use for prediction submissions and real-time operations.
    """
    return validate_trading_day(trading_day, allow_past=False, allow_future=False)
```

#### 3.3 Router Integration Pattern

**Example 1: Trading Day Summary (Main Issue)**
```python
# myapi/routers/price_router.py

@router.get("/trading-day-summary", response_model=BaseResponse)
@inject
async def get_trading_day_price_summary(
    trading_day: str = "",
    symbols: str = "",
    validated_date: date = Depends(require_trading_day),  # NEW
    _current_user: UserSchema = Depends(get_current_active_user),
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """
    거래일 가격 요약 조회 (종가 + 현재가)
    
    Note: validated_date is automatically checked for trading day validity.
          NonTradingDayError is raised automatically for weekends/holidays.
    """
    try:
        # Use validated_date instead of parsing trading_day again
        symbol_list = None
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

        summaries = price_service.get_trading_day_price_summary(
            trading_day=validated_date,  # Already validated
            symbols=symbol_list
        )

        return BaseResponse(
            success=True,
            data={
                "trading_day": summaries[0].trading_day if summaries else None,
                "count": len(summaries),
                "summaries": [s.model_dump() for s in summaries],
            },
        )
    except NotFoundError as e:
        # This should rarely happen now since date is pre-validated
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trading day price summary: {str(e)}",
        )
```

**Example 2: Prediction Submission**
```python
# myapi/routers/prediction_router.py

@router.post("/{symbol}", response_model=BaseResponse)
@inject
def submit_prediction(
    payload: PredictionUpdate,
    symbol: str = Path(..., pattern=r"^[A-Z]{1,5}$"),
    validated_date: date = Depends(require_current_trading_day),  # NEW - must be today
    current_user: UserSchema = Depends(get_current_active_user),
    service: PredictionService = Depends(get_prediction_service),
):
    """Submit prediction for current trading day only"""
    try:
        create_payload = PredictionCreate(symbol=symbol.upper(), choice=payload.choice)
        created = service.submit_prediction(
            current_user.id, validated_date, create_payload  # Use validated date
        )
        return BaseResponse(success=True, data={"prediction": created.model_dump()})
    except (ValidationError, BusinessLogicError, ConflictError, RateLimitError) as e:
        # NonTradingDayError will be caught by global exception handler
        # before reaching this point
        ...
```

**Example 3: Admin Endpoint (Bypass Validation)**
```python
# myapi/routers/price_router.py

@router.post("/admin/compare-prediction", response_model=BaseResponse)
@inject
async def compare_prediction_with_outcome(
    symbol: str,
    trading_day: str,
    predicted_direction: str,
    _current_user: UserSchema = Depends(require_admin),
    price_service: PriceService = Depends(get_price_service),
) -> Any:
    """
    Admin endpoint - NO trading day validation.
    Admins can query any date for debugging/analysis.
    """
    try:
        day = date.fromisoformat(trading_day)  # Parse directly, no validation
        # ... rest of logic
```

### 4. Performance Optimization: Caching

**Cache Implementation:**
```python
# myapi/utils/market_hours.py

from functools import lru_cache
from datetime import date, timedelta

class USMarketHours:
    # ... existing code ...
    
    @classmethod
    @lru_cache(maxsize=128)
    def is_us_trading_day_cached(cls, check_date: date) -> bool:
        """Cached version of is_us_trading_day for performance"""
        return cls.is_us_trading_day(check_date)
    
    @classmethod
    @lru_cache(maxsize=128)
    def get_next_trading_day_cached(cls, from_date: date) -> date:
        """Cached version of get_next_trading_day"""
        return cls.get_next_trading_day(from_date)
```

**Usage in deps.py:**
```python
# Use cached versions in validators
if not USMarketHours.is_us_trading_day_cached(target_date):
    next_trading_day = USMarketHours.get_next_trading_day_cached(target_date)
    # ... raise error
```

**Cache Benefits:**
- Same-day requests hit cache (O(1) lookup)
- Reduces repeated holiday set lookups
- LRU eviction prevents unbounded memory growth
- 128 entries ~ 4 months of cached dates

### 5. Edge Cases & Solutions

#### Edge Case 1: Historical Non-Trading Day Queries
**Scenario:** Admin wants to check why 2025-11-27 data is missing

**Solution:** Admin endpoints bypass validation
```python
# Admin can explicitly request any date
GET /prices/admin/validate-settlement/2025-11-27  # No validation
```

#### Edge Case 2: Date Range Queries Spanning Non-Trading Days
**Scenario:** User queries week including Thanksgiving

**Solution:** Filter valid trading days in service layer
```python
def get_price_range(start: date, end: date) -> List[PriceSummary]:
    """Get prices for date range, skipping non-trading days"""
    trading_days = [
        d for d in date_range(start, end)
        if USMarketHours.is_us_trading_day(d)
    ]
    return [get_price_for_day(d) for d in trading_days]
```

#### Edge Case 3: Optional Trading Day Parameter
**Scenario:** `/prices/trading-day-summary?trading_day=` (empty string)

**Solution:** Dependency handles None/empty gracefully
```python
def require_trading_day(trading_day: Optional[str] = None) -> date:
    target_date = (
        date.fromisoformat(trading_day) 
        if trading_day  # Handles "", None
        else USMarketHours.get_kst_trading_day()
    )
```

#### Edge Case 4: Timezone Edge Cases (KST vs ET)
**Scenario:** KST 2025-11-28 06:00 is still ET 2025-11-27 16:00 (Thanksgiving)

**Solution:** Use existing `get_kst_trading_day()` logic
```python
# Already handles timezone correctly
target_date = USMarketHours.get_kst_trading_day()  # Returns correct ET trading day
```

#### Edge Case 5: Future Trading Days
**Scenario:** User queries 2025-12-25 (Christmas, but in future)

**Solution:** Use `allow_future` parameter
```python
# For universe setup (allow future)
validated_date = Depends(lambda td: validate_trading_day(td, allow_future=True))

# For predictions (disallow future)
validated_date = Depends(require_current_trading_day)  # Only today
```

### 6. Testing Strategy

#### Unit Tests
**File:** `tests/test_trading_day_validation.py`

```python
import pytest
from datetime import date
from myapi.deps import validate_trading_day, require_current_trading_day
from myapi.core.exceptions import NonTradingDayError, ValidationError

class TestTradingDayValidation:
    def test_valid_trading_day(self):
        """2025-11-26 (Wednesday) is a trading day"""
        result = validate_trading_day("2025-11-26")
        assert result == date(2025, 11, 26)
    
    def test_thanksgiving_holiday(self):
        """2025-11-27 (Thanksgiving) should raise NonTradingDayError"""
        with pytest.raises(NonTradingDayError) as exc:
            validate_trading_day("2025-11-27")
        
        assert exc.value.details["day_type"] == "holiday"
        assert exc.value.details["next_trading_day"] == "2025-11-29"
    
    def test_weekend(self):
        """2025-11-29 (Saturday) should raise NonTradingDayError"""
        with pytest.raises(NonTradingDayError) as exc:
            validate_trading_day("2025-11-29")
        
        assert exc.value.details["day_type"] == "weekend"
    
    def test_invalid_date_format(self):
        """Invalid format should raise ValidationError"""
        with pytest.raises(ValidationError):
            validate_trading_day("invalid-date")
    
    def test_none_defaults_to_current(self):
        """None should default to current KST trading day"""
        result = validate_trading_day(None)
        assert isinstance(result, date)
    
    def test_future_not_allowed(self):
        """Future dates rejected when allow_future=False"""
        with pytest.raises(ValidationError):
            validate_trading_day("2026-01-02", allow_future=False)
```

#### Integration Tests
```python
class TestPriceRouterValidation:
    def test_trading_day_summary_on_holiday(self, client, auth_headers):
        """GET /prices/trading-day-summary on holiday returns 422"""
        response = client.get(
            "/api/v1/prices/trading-day-summary?trading_day=2025-11-27",
            headers=auth_headers
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "NON_TRADING_DAY"
        assert "2025-11-27" in data["error"]["message"]
        assert data["error"]["details"]["next_trading_day"] == "2025-11-29"
    
    def test_trading_day_summary_on_valid_day(self, client, auth_headers):
        """GET /prices/trading-day-summary on valid day returns 200"""
        response = client.get(
            "/api/v1/prices/trading-day-summary?trading_day=2025-11-26",
            headers=auth_headers
        )
        assert response.status_code in [200, 404]  # 404 if no data, but not 422
```

### 7. Migration Path

#### Phase 1: Add Exception & Validators (Non-Breaking)
1. Add `NonTradingDayError` to `exceptions.py`
2. Add `validate_trading_day()` functions to `deps.py`
3. Add caching to `market_hours.py`
4. Write unit tests

#### Phase 2: Update Critical Endpoints
1. `/prices/trading-day-summary` (main issue)
2. `/universe/today`
3. `/universe/today/with-prices`
4. `/predictions/{symbol}`

#### Phase 3: Update Remaining Endpoints
1. `/prices/universe/{trading_day}`
2. `/prices/collect-eod/{trading_day}`
3. `/universe/refresh-prices`
4. `/settlement/admin/settle/{trading_day}`

#### Phase 4: Cleanup
1. Remove redundant validation in service layer
2. Update API documentation
3. Add client-side handling examples

### 8. Alternative Approaches Considered

#### Alternative 1: Global Middleware
**Rejected Because:**
- Executes on ALL requests (performance overhead)
- Requires URL pattern matching (fragile)
- Cannot distinguish admin vs user endpoints
- Harder to configure exceptions

#### Alternative 2: Decorator Pattern
```python
@require_trading_day(param="trading_day")
def get_trading_day_summary(trading_day: str, ...):
    ...
```

**Rejected Because:**
- Less idiomatic in FastAPI (dependencies preferred)
- Harder to compose with other decorators
- No automatic parameter injection

#### Alternative 3: Service Layer Validation
```python
# In price_service.py
def get_trading_day_price_summary(self, trading_day: date, ...):
    if not USMarketHours.is_us_trading_day(trading_day):
        raise NonTradingDayError(...)
```

**Rejected Because:**
- Duplicated across multiple services
- Validation happens late (after auth, DB connection)
- Inconsistent error handling
- Cannot customize per-endpoint (allow_past, allow_future)

### 9. Backwards Compatibility

#### Breaking Changes: None
- New validation is additive (doesn't change existing success paths)
- Only changes error responses (404 → 422 for non-trading days)
- Clients already handle errors generically

#### Client Migration
```javascript
// Before: Check for 404
if (response.status === 404) {
  showError("Data not found");
}

// After: Check for 422 (non-trading day)
if (response.status === 422 && response.error.code === "NON_TRADING_DAY") {
  showWarning(`Market closed on ${response.error.details.requested_date}`);
  suggestNextTradingDay(response.error.details.next_trading_day);
} else if (response.status === 404) {
  showError("Data not found");
}
```

## Implementation Checklist

- [ ] Add `NonTradingDayError` to `myapi/core/exceptions.py`
- [ ] Add validation functions to `myapi/deps.py`
- [ ] Add caching to `myapi/utils/market_hours.py`
- [ ] Update `myapi/routers/price_router.py` (`/trading-day-summary`)
- [ ] Update `myapi/routers/universe_router.py` (`/today`, `/today/with-prices`)
- [ ] Update `myapi/routers/prediction_router.py` (`POST /{symbol}`)
- [ ] Write unit tests for validators
- [ ] Write integration tests for endpoints
- [ ] Update API documentation
- [ ] Test on local development
- [ ] Deploy to staging
- [ ] Monitor production errors

## Success Metrics

- Zero 404 errors on `/prices/trading-day-summary` for non-trading days
- Consistent 422 responses with actionable error messages
- <10ms overhead from validation (with caching)
- 100% test coverage for validation logic
- Clear error messages guide users to next trading day

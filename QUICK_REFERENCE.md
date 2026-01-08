# Quick Reference: Prediction Refactoring

## New API Endpoints

### RANGE Predictions (Price Range)
```bash
# Create RANGE prediction
POST /api/v1/range-predictions
{
  "symbol": "BTCUSDT",
  "price_low": 95000.0,
  "price_high": 97000.0
}

# Update RANGE prediction (NEW!)
PATCH /api/v1/range-predictions/{id}
{
  "price_low": 95500.0,
  "price_high": 96500.0
}

# List user's RANGE predictions
GET /api/v1/range-predictions?symbol=BTCUSDT&limit=50&offset=0

# Get prediction history
GET /api/v1/range-predictions/history?limit=50&offset=0

# Settle predictions (admin only)
POST /api/v1/range-predictions/settle
```

### DIRECTION Predictions (UP/DOWN)
```bash
# Unchanged - existing endpoints still work
POST /api/v1/predictions
PATCH /api/v1/predictions/{id}
GET /api/v1/predictions
```

## Dependency Injection Usage

```python
# In routers or other services
from myapi.deps import (
    get_direction_prediction_service,
    get_range_prediction_service,
)

# DIRECTION service (UP/DOWN)
direction_service = Depends(get_direction_prediction_service)

# RANGE service (price ranges)
range_service = Depends(get_range_prediction_service)

# Legacy (still works - backward compatibility)
prediction_service = Depends(get_prediction_service)  # → Direction
crypto_service = Depends(get_crypto_prediction_service)  # → Range
```

## Configuration

Add to `.env` or `config.py`:

```python
# Allowed symbols for RANGE predictions
ALLOWED_RANGE_SYMBOLS_CRYPTO=["BTCUSDT", "ETHUSDT"]  # Crypto
ALLOWED_RANGE_SYMBOLS_STOCK=[]  # Stocks (future)

# Time window for RANGE predictions
RANGE_PREDICTION_TIME_WINDOW_HOURS=1
```

## Service Layer Usage

### DIRECTION Prediction
```python
from myapi.services.direction_prediction_service import DirectionPredictionService

service = DirectionPredictionService(db, settings)

# Create
prediction = service.submit_prediction(user_id, trading_day, payload)

# Update choice
updated = service.update_prediction(user_id, prediction_id, update_payload)

# Query
predictions = service.get_user_predictions_for_day(user_id, trading_day)
trends = service.get_prediction_trends(trading_day, limit=5)
```

### RANGE Prediction
```python
from myapi.services.range_prediction_service import RangePredictionService

service = RangePredictionService(db, settings, binance_service, allowed_symbols)

# Create
prediction = await service.create_prediction(user_id, payload)

# Update bounds (NEW!)
updated = await service.update_range_prediction(user_id, prediction_id, update_payload)

# Query
predictions = await service.list_user_predictions(user_id, symbol, limit=50, offset=0)

# Settle
result = await service.settle_due_predictions(now_ms=current_time_ms)
```

## Repository Layer Usage

### DIRECTION Repository
```python
from myapi.repositories.direction_prediction_repository import DirectionPredictionRepository

repo = DirectionPredictionRepository(db)

# Create
prediction = repo.create_prediction(user_id, trading_day, symbol, choice, submitted_at)

# Update choice
updated = repo.update_prediction_choice(prediction_id, new_choice)

# Check existence
exists = repo.prediction_exists(user_id, trading_day, symbol)
```

### RANGE Repository
```python
from myapi.repositories.range_prediction_repository import RangePredictionRepository

repo = RangePredictionRepository(db)

# Create
prediction = repo.create_prediction(
    user_id=user_id,
    trading_day=trading_day,
    symbol=symbol,
    price_low=Decimal("95000"),
    price_high=Decimal("97000"),
    target_open_time_ms=open_ms,
    target_close_time_ms=close_ms,
    submitted_at=datetime.now(timezone.utc),
)

# Update bounds (NEW!)
updated = repo.update_range_bounds(
    prediction_id=prediction_id,
    price_low=Decimal("95500"),
    price_high=Decimal("96500"),
)

# Check existence
exists = repo.prediction_exists(user_id, target_open_time_ms)
```

## Schema Usage

### DIRECTION Schemas
```python
from myapi.schemas.prediction import (
    PredictionCreate,
    PredictionUpdate,
    PredictionResponse,
    # Aliases
    DirectionPredictionCreate,
    DirectionPredictionUpdate,
)

# Create payload
create_payload = PredictionCreate(
    symbol="AAPL",
    choice=PredictionChoice.UP
)

# Update payload
update_payload = PredictionUpdate(
    choice=PredictionChoice.DOWN
)
```

### RANGE Schemas
```python
from myapi.schemas.range_prediction import (
    RangePredictionCreate,
    RangePredictionUpdate,  # NEW!
    RangePredictionResponse,
    # Backward compatibility
    CryptoPredictionCreate,
    CryptoPredictionSchema,
)

# Create payload
create_payload = RangePredictionCreate(
    symbol="BTCUSDT",
    price_low=Decimal("95000"),
    price_high=Decimal("97000")
)

# Update payload (NEW!)
update_payload = RangePredictionUpdate(
    price_low=Decimal("95500"),
    price_high=Decimal("96500")
)
```

## Migration Guide

### Before (Old Code)
```python
# Old service usage
from myapi.services.crypto_prediction_service import CryptoPredictionService
from myapi.deps import get_crypto_prediction_service

service = Depends(get_crypto_prediction_service)

# No update endpoint existed
# POST /crypto-predictions (create only)
```

### After (New Code)
```python
# New service usage
from myapi.services.range_prediction_service import RangePredictionService
from myapi.deps import get_range_prediction_service

service = Depends(get_range_prediction_service)

# Now has update endpoint!
# POST /range-predictions (create)
# PATCH /range-predictions/{id} (update) ← NEW!
```

### Backward Compatibility
```python
# Old code still works (no changes needed)
from myapi.deps import get_crypto_prediction_service
service = Depends(get_crypto_prediction_service)  # Returns RangePredictionService

# Old endpoint still works
POST /api/v1/crypto-predictions  # Internally uses RangePredictionService
```

## Testing

```bash
# Test DIRECTION prediction
curl -X POST http://localhost:8000/api/v1/predictions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"symbol":"AAPL","choice":"UP"}'

# Test RANGE prediction (new endpoint)
curl -X POST http://localhost:8000/api/v1/range-predictions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"symbol":"BTCUSDT","price_low":95000,"price_high":97000}'

# Test RANGE update (NEW!)
curl -X PATCH http://localhost:8000/api/v1/range-predictions/123 \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"price_low":95500,"price_high":96500}'

# Test backward compatibility
curl -X POST http://localhost:8000/api/v1/crypto-predictions \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"symbol":"BTCUSDT","price_low":95000,"price_high":97000}'
```

## Key Benefits

✅ **Unified Architecture**: Common base for DIRECTION/RANGE
✅ **Asset Agnostic**: Easy to add stocks, forex, etc.
✅ **Feature Parity**: RANGE now has update like DIRECTION
✅ **No Breaking Changes**: All existing code continues to work
✅ **Extensible**: Add new prediction types easily
✅ **Maintainable**: DRY principle, shared logic in base classes


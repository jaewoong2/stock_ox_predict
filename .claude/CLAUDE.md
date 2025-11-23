# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Running the Application

```bash
# Local development with uvicorn
uvicorn myapi.main:app --host 0.0.0.0 --port 8000 --reload

# Docker development
docker-compose up --build

# AWS Lambda deployment
./deploy.sh
```

### Testing

```bash
# Run tests (pytest should be used based on test structure)
python -m pytest tests/

# Run specific test
python -m pytest tests/test_web_search_repository.py
```

### Database Operations

```bash
# The application uses PostgreSQL with async SQLAlchemy
# Connection configured via environment variables in myapi/.env
# Schema: crypto (as defined in models)
```

### Key Configuration

- Environment variables loaded from `myapi/.env`
- Database connection pooling with retry logic
- CORS configured for development and production origins
- Logging configured for AWS Lambda compatibility

## Backend Performance

- MUST: Use async/await for I/O operations
- MUST: Implement database query optimization
- SHOULD: Use caching for expensive operations
- SHOULD: Implement pagination for large datasets
- SHOULD: Monitor API response times

## Python/FastAPI Rules - General Principles

- MUST: Follow PEP 8 style guide
- MUST: Use type hints for all function parameters and return values
- MUST: Use async/await for I/O operations
- SHOULD: Use descriptive variable and function names
- SHOULD: Keep functions small and focused

## FastAPI Specific

- MUST: Use Pydantic models for request/response validation
- MUST: Use dependency injection for database sessions and auth
- MUST: Define proper HTTP status codes for responses
- MUST: Use proper exception handling with HTTPException
- SHOULD: Group related endpoints in separate router files
- SHOULD: Use response_model for endpoint documentation

## Database & Models

- MUST: Use SQLAlchemy async for database operations
- MUST: Define separate Pydantic schemas for create/update/read operations
- MUST: Use proper database migrations with Alembic
- SHOULD: Use database transactions for data consistency
- SHOULD: Implement proper database indexing

## Repository Layer Pattern

**CRITICAL**: Repositories MUST return Pydantic schemas, NEVER raw SQLAlchemy models.

### Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│                     API Layer (Routers)                     │
│  - Receives Pydantic schemas from services                 │
│  - Returns BaseResponse with schema.model_dump()           │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                   Service Layer                             │
│  - Receives Pydantic schemas from repositories             │
│  - Implements business logic                               │
│  - Returns Pydantic schemas to routers                     │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                Repository Layer (THIS IS KEY)               │
│  - Queries SQLAlchemy models from database                 │
│  - MUST convert models to Pydantic schemas                 │
│  - NEVER return raw SQLAlchemy models                      │
│  - Returns type-safe Pydantic schemas                      │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│                   Database Layer                            │
│  - SQLAlchemy models (internal only)                       │
│  - Never exposed outside repository                        │
└─────────────────────────────────────────────────────────────┘
```

### Repository Implementation Rules

#### MUST: Use BaseRepository Pattern

```python
from myapi.repositories.base import BaseRepository
from myapi.models.your_model import YourModel
from myapi.schemas.your_schema import YourSchema

class YourRepository(BaseRepository[YourModel, YourSchema]):
    def __init__(self, db: Session):
        super().__init__(
            model_class=YourModel,
            schema_class=YourSchema,
            db=db
        )

    # All inherited methods (get_by_id, find_all, create, update, delete)
    # automatically return YourSchema, NOT YourModel
```

#### MUST: Return Schemas from Custom Methods

```python
def get_by_custom_field(self, field_value: str) -> Optional[YourSchema]:
    """Custom query method - MUST return schema"""
    model_instance = self.db.query(self.model_class)\
        .filter(self.model_class.custom_field == field_value)\
        .first()

    # Use base class conversion
    return self._to_schema(model_instance)
```

#### MUST: Use Schema Conversion Methods

**Option 1: Base Class `_to_schema()` (Simple Cases)**

```python
# Inherited from BaseRepository - handles basic conversion
return self._to_schema(model_instance)
```

**Option 2: Custom Conversion (Complex Cases)**

```python
def _to_custom_schema(self, model: YourModel) -> YourSchema:
    """Use when you need field transformations or calculated fields"""
    return YourSchema(
        id=model.id,
        name=model.name,
        created_at=model.created_at.isoformat(),  # Date transformation
        calculated_field=self._calculate_something(model),  # Business logic
    )

def get_with_calculations(self, id: int) -> Optional[YourSchema]:
    model = self.db.query(self.model_class).filter_by(id=id).first()
    return self._to_custom_schema(model)
```

**Option 3: Snapshot Pattern (Type Safety)**

```python
# For methods needing type-safe intermediate conversion
from myapi.schemas.your_schema import YourSnapshot

def _to_custom_schema(self, model: YourModel) -> YourSchema:
    # First convert to snapshot for type safety
    snapshot = YourSnapshot.from_db_model(model)

    # Then build final schema with business logic
    return YourSchema(
        id=snapshot.id,
        calculated_total=snapshot.field_a + snapshot.field_b,
    )
```

### Schema Design Patterns

#### Pattern 1: Direct Model Mapping

```python
# myapi/schemas/simple.py
class SimpleSchema(BaseModel):
    """1:1 mapping with DB model"""
    id: int
    name: str
    created_at: datetime

    class Config:
        from_attributes = True  # Pydantic v2: enables model_validate()
```

#### Pattern 2: Snapshot + Response Schema

```python
# myapi/schemas/complex.py
from typing import Any
from datetime import datetime, timezone

class DataSnapshot(BaseModel):
    """Type-safe DB → Schema conversion layer"""
    symbol: str
    price: Decimal
    timestamp: datetime

    @classmethod
    def from_db_model(cls, db_model: Any) -> "DataSnapshot":
        """Explicit type conversion from SQLAlchemy model"""
        return cls(
            symbol=str(db_model.symbol),
            price=Decimal(str(db_model.price)),
            timestamp=db_model.timestamp if db_model.timestamp else datetime.now(timezone.utc),
        )

class DataResponse(BaseModel):
    """API response with calculated/transformed fields"""
    symbol: str
    price: Decimal
    price_change_percent: Decimal  # Calculated field
    formatted_time: str  # Transformed field
```

### Common Patterns by Use Case

| Use Case              | Pattern                 | Example                                            |
| --------------------- | ----------------------- | -------------------------------------------------- |
| Simple CRUD           | BaseRepository          | UserRepository, CooldownRepository                 |
| Field transformations | Custom `_to_*_schema()` | PriceRepository (date.isoformat())                 |
| Calculated fields     | Snapshot + Schema       | RewardsRepository (available_stock calculation)    |
| Type safety critical  | Snapshot pattern        | TradingDayPriceSummary (prevents Column[T] errors) |
| Enum handling         | Custom conversion       | SessionRepository (SessionPhase enum)              |

### Anti-Patterns (NEVER DO THIS)

❌ **Returning SQLAlchemy models directly**

```python
def get_user(self, id: int) -> UserModel:  # ❌ WRONG
    return self.db.query(UserModel).filter_by(id=id).first()
```

✅ **Always return schemas**

```python
def get_user(self, id: int) -> Optional[UserSchema]:  # ✅ CORRECT
    model = self.db.query(UserModel).filter_by(id=id).first()
    return self._to_schema(model)
```

❌ **Using models in service layer**

```python
# service.py
user_model = self.user_repo.get_user(id)  # ❌ If this returns a model
user_model.email = "new@email.com"  # ❌ Direct model manipulation
```

✅ **Using schemas in service layer**

```python
# service.py
user_schema = self.user_repo.get_user(id)  # ✅ Returns schema
updated = self.user_repo.update(id, {"email": "new@email.com"})  # ✅ Returns schema
```

### Exception: Internal-Only Methods

Only use raw models for internal repository methods (prefix with `_` or clearly document):

```python
def get_universe_models_for_date(self, date: date) -> List[ActiveUniverseModel]:
    """
    Internal use only - returns models for complex joins/calculations.
    Public API methods should use get_universe_for_date() which returns schemas.
    """
    return self.db.query(ActiveUniverseModel).filter_by(trading_day=date).all()

def get_universe_for_date(self, date: date) -> List[UniverseItem]:
    """Public API - returns schemas"""
    models = self.get_universe_models_for_date(date)
    return [self._to_schema(m) for m in models]
```

### Benefits of This Pattern

1. **Type Safety**: Pydantic validates all data at repository boundary
2. **API Contract**: Schemas define clear contracts, models are implementation details
3. **Prevents Leakage**: SQLAlchemy sessions and lazy-loading issues contained in repository
4. **Easier Testing**: Mock with Pydantic schemas instead of SQLAlchemy models
5. **Migration Safety**: Model changes don't break API if schema stays stable
6. **Security**: Prevents accidental exposure of sensitive model fields

\*\*

- 내가 지시하는 것 보다 더 좋은 방향 (베스트 프랙티스)이 있으면 더 좋게 구현 할 것
- 덕지덕지 코드 말고, 재사용 가능 하며 베스트 프랙티스가 있는 방향으로 구현 할 것
- 리팩토링이 쉬운 코드로 구현 할 것
- 이미 구현 되어 있는 코드 및 기능이 있는지 찾아 볼 것
  \*\*

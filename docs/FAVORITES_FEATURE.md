# User Favorites/Watchlist Feature

## Overview

A complete implementation of user favorites/watchlist functionality allowing users to save and manage their favorite stock tickers.

**Implementation Date**: 2025-11-21

## Architecture

### Database Layer

**Table**: `crypto.user_favorites`
- **Type**: Junction table (many-to-many relationship)
- **Primary Key**: Composite `(user_id, symbol)`
- **Foreign Keys**:
  - `user_id` → `crypto.users.id` (CASCADE DELETE)
  - `symbol` → `crypto.tickers_reference.symbol` (CASCADE DELETE)
- **Timestamps**: `created_at`, `updated_at` (auto-managed)
- **Indexes**: `user_id`, `symbol`, `created_at DESC`

**Model**: [`myapi/models/user_favorites.py`](../myapi/models/user_favorites.py)

### Schema Layer (Pydantic)

**File**: [`myapi/schemas/favorites.py`](../myapi/schemas/favorites.py)

**Schemas**:
- `FavoriteSchema` - Basic favorite record
- `FavoriteTickerInfo` - Favorite with full ticker details
- `UserFavoritesResponse` - List response with metadata
- `FavoriteCheckResponse` - Check if symbol is favorited
- `AddFavoriteRequest` - Request body (optional, can use path param)

### Repository Layer

**File**: [`myapi/repositories/favorites_repository.py`](../myapi/repositories/favorites_repository.py)

**Pattern**: Extends `BaseRepository[UserFavorite, FavoriteSchema]`

**Key Methods** (all return Pydantic schemas):
- `get_user_favorites(user_id, limit, offset)` → `List[FavoriteTickerInfo]`
- `add_favorite(user_id, symbol)` → `Optional[FavoriteSchema]`
- `remove_favorite(user_id, symbol)` → `bool`
- `is_favorited(user_id, symbol)` → `bool`
- `get_favorites_count(user_id)` → `int`
- `get_all_favorited_symbols(user_id)` → `List[str]`

**CRITICAL**: Repository returns **Pydantic schemas only**, never SQLAlchemy models (per CLAUDE.md repository pattern).

### Service Layer

**File**: [`myapi/services/favorites_service.py`](../myapi/services/favorites_service.py)

**Business Logic**:
- Validates ticker symbols exist in `tickers_reference`
- Prevents duplicate favorites (throws `ConflictError`)
- Normalizes symbols to uppercase
- Enforces pagination limits (max 500)

**Methods**:
- `get_user_favorites(user_id, limit, offset)` → `UserFavoritesResponse`
- `add_favorite(user_id, symbol)` → `FavoriteTickerInfo`
- `remove_favorite(user_id, symbol)` → `bool`
- `check_favorite(user_id, symbol)` → `FavoriteCheckResponse`
- `get_favorited_symbols(user_id)` → `List[str]`

### Router Layer

**File**: [`myapi/routers/favorites_router.py`](../myapi/routers/favorites_router.py)

**Base Path**: `/api/v1/favorites`
**Tag**: `favorites`
**Auth**: All endpoints require authenticated user (`get_current_active_user`)

## API Endpoints

### 1. Get User's Favorites

```http
GET /api/v1/favorites
```

**Query Parameters**:
- `limit` (optional, default: 100, max: 500) - Number of results
- `offset` (optional, default: 0) - Number to skip for pagination

**Response**:
```json
{
  "success": true,
  "data": {
    "user_id": 123,
    "favorites": [
      {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "market_category": "Q",
        "is_etf": false,
        "added_at": "2025-11-21T10:30:00Z"
      }
    ],
    "total_count": 15
  },
  "meta": {
    "limit": 100,
    "offset": 0,
    "total_count": 15,
    "has_next": false
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/favorites?limit=50&offset=0" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

### 2. Add Ticker to Favorites

```http
POST /api/v1/favorites/{symbol}
```

**Path Parameters**:
- `symbol` (required) - Ticker symbol (e.g., AAPL, GOOGL)

**Response**:
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "name": "Apple Inc.",
    "market_category": "Q",
    "is_etf": false,
    "added_at": "2025-11-21T10:30:00Z"
  },
  "meta": {
    "message": "Successfully added AAPL to favorites"
  }
}
```

**Error Responses**:
- `404 NOT_FOUND` - Ticker symbol doesn't exist
- `409 CONFLICT` - Ticker already in favorites
- `422 VALIDATION_ERROR` - Failed to add favorite

**cURL Example**:
```bash
curl -X POST "http://localhost:8000/api/v1/favorites/AAPL" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

### 3. Remove Ticker from Favorites

```http
DELETE /api/v1/favorites/{symbol}
```

**Path Parameters**:
- `symbol` (required) - Ticker symbol to remove

**Response**:
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL"
  },
  "meta": {
    "message": "Successfully removed AAPL from favorites"
  }
}
```

**Error Responses**:
- `404 NOT_FOUND` - Ticker not in favorites
- `422 VALIDATION_ERROR` - Failed to remove favorite

**cURL Example**:
```bash
curl -X DELETE "http://localhost:8000/api/v1/favorites/AAPL" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

### 4. Check if Ticker is Favorited

```http
GET /api/v1/favorites/check/{symbol}
```

**Path Parameters**:
- `symbol` (required) - Ticker symbol to check

**Response**:
```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "is_favorited": true
  }
}
```

**cURL Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/favorites/check/AAPL" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

---

### 5. Get Favorite Symbols List

```http
GET /api/v1/favorites/symbols/list
```

**Response**:
```json
{
  "success": true,
  "data": {
    "symbols": ["AAPL", "GOOGL", "MSFT", "TSLA"],
    "count": 4
  }
}
```

**Use Case**: Quick list for dropdowns, filters, or simple checks without full ticker metadata.

**cURL Example**:
```bash
curl -X GET "http://localhost:8000/api/v1/favorites/symbols/list" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Database Migration

### Apply Migration

```bash
# Using psql with database URL from .env
psql "<DATABASE_URL>" -f migrations/001_create_user_favorites_table.sql
```

### Rollback Migration

```bash
psql "<DATABASE_URL>" -f migrations/001_create_user_favorites_table_rollback.sql
```

**Migration Files**:
- [`migrations/001_create_user_favorites_table.sql`](../migrations/001_create_user_favorites_table.sql) - Create table
- [`migrations/001_create_user_favorites_table_rollback.sql`](../migrations/001_create_user_favorites_table_rollback.sql) - Drop table

## Testing

### Manual Testing with cURL

1. **Get JWT token** (login first):
```bash
TOKEN=$(curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"password"}' \
  | jq -r '.data.access_token')
```

2. **Add favorite**:
```bash
curl -X POST "http://localhost:8000/api/v1/favorites/AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

3. **Get favorites**:
```bash
curl -X GET "http://localhost:8000/api/v1/favorites" \
  -H "Authorization: Bearer $TOKEN"
```

4. **Check if favorited**:
```bash
curl -X GET "http://localhost:8000/api/v1/favorites/check/AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

5. **Remove favorite**:
```bash
curl -X DELETE "http://localhost:8000/api/v1/favorites/AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

### Unit Tests (TODO)

Create test file: `tests/test_favorites.py`

**Test Cases**:
- `test_add_favorite_success`
- `test_add_favorite_duplicate_conflict`
- `test_add_favorite_invalid_symbol`
- `test_remove_favorite_success`
- `test_remove_favorite_not_found`
- `test_get_favorites_pagination`
- `test_check_favorite_true`
- `test_check_favorite_false`

## Key Design Decisions

### 1. User (one) to Ticker (many) - Junction Table

**Decision**: Use junction table with composite primary key `(user_id, symbol)`

**Benefits**:
- Prevents duplicate favorites per user
- Efficient many-to-many queries
- Cascade deletion (user deleted → favorites deleted)
- Easy to add metadata (e.g., `added_at`, custom tags)

**Alternative Rejected**: Array field in users table (less normalized, harder to query/index)

### 2. Repository Pattern Compliance

**Critical Rule**: Repositories MUST return Pydantic schemas, NEVER SQLAlchemy models

**Implementation**:
- All repository methods use `_to_schema()` or custom conversion
- Service layer only handles Pydantic schemas
- Router calls `.model_dump()` for JSON serialization

**Reference**: See [CLAUDE.md Repository Layer Pattern](../CLAUDE.md#repository-layer-pattern)

### 3. Symbol Normalization

**Decision**: Normalize all symbols to uppercase in service layer

**Reason**: Database symbols are uppercase, prevents case-sensitivity issues

### 4. Ticker Validation

**Decision**: Validate symbol exists in `tickers_reference` before adding

**Benefits**:
- Prevents orphaned references
- Clear error messages for invalid symbols
- Foreign key constraint enforces referential integrity

### 5. Pagination Limits

**Decision**: Max 500 results per request, default 100

**Reason**: Balance between flexibility and performance

## Files Created

```
myapi/
├── models/
│   └── user_favorites.py          # SQLAlchemy model
├── schemas/
│   └── favorites.py               # Pydantic schemas
├── repositories/
│   └── favorites_repository.py    # Data access layer
├── services/
│   └── favorites_service.py       # Business logic layer
├── routers/
│   └── favorites_router.py        # API endpoints
├── deps.py                        # Added get_favorites_service()
└── main.py                        # Registered router

migrations/
├── 001_create_user_favorites_table.sql
├── 001_create_user_favorites_table_rollback.sql
└── README.md

docs/
└── FAVORITES_FEATURE.md           # This file
```

## Integration Points

### Frontend Integration

**Example React Hook**:
```typescript
// useFavorites.ts
export const useFavorites = () => {
  const addFavorite = async (symbol: string) => {
    const response = await fetch(`/api/v1/favorites/${symbol}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.json();
  };

  const removeFavorite = async (symbol: string) => {
    const response = await fetch(`/api/v1/favorites/${symbol}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` }
    });
    return response.json();
  };

  const getFavorites = async (limit = 100, offset = 0) => {
    const response = await fetch(
      `/api/v1/favorites?limit=${limit}&offset=${offset}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return response.json();
  };

  const isFavorited = async (symbol: string) => {
    const response = await fetch(`/api/v1/favorites/check/${symbol}`, {
      headers: { Authorization: `Bearer ${token}` }
    });
    const data = await response.json();
    return data.data.is_favorited;
  };

  return { addFavorite, removeFavorite, getFavorites, isFavorited };
};
```

## Performance Considerations

### Indexes

All critical queries are indexed:
- `idx_user_favorites_user_id` - For user's favorites list
- `idx_user_favorites_symbol` - For symbol lookups
- `idx_user_favorites_created_at` - For chronological sorting

### Query Optimization

- Join with `tickers_reference` only when full details needed
- Use `get_all_favorited_symbols()` for lightweight symbol lists
- Pagination prevents large result sets

### Caching Opportunities (Future)

Consider caching:
- User's favorite symbols list (Redis, 5-minute TTL)
- Ticker reference data (rarely changes)
- Is-favorited checks for UI responsiveness

## Security

- **Authentication**: All endpoints require JWT token
- **Authorization**: Users can only manage their own favorites
- **Input Validation**: Symbols normalized and validated against reference table
- **SQL Injection**: Protected by SQLAlchemy ORM and parameterized queries
- **Cascade Deletion**: User deletion automatically cleans up favorites

## Future Enhancements

1. **Custom Tags/Categories**
   - Add `tag` column for custom watchlists (e.g., "tech stocks", "high-risk")

2. **Favorite Order**
   - Add `display_order` column for user-defined sorting

3. **Notifications**
   - Trigger price alerts for favorited stocks

4. **Analytics**
   - Track most favorited stocks across all users
   - User engagement metrics

5. **Bulk Operations**
   - `POST /favorites/bulk` - Add multiple symbols at once
   - `DELETE /favorites/bulk` - Remove multiple symbols

6. **Export**
   - `GET /favorites/export` - Export as CSV/JSON

## Support

For questions or issues:
- Check API documentation: `http://localhost:8000/docs`
- Review [CLAUDE.md](../CLAUDE.md) for architecture patterns
- See [Repository Pattern](../CLAUDE.md#repository-layer-pattern) for data layer rules

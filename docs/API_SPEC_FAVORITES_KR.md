# 즐겨찾기(Favorites) API 명세서

## 📋 개요

사용자가 관심있는 종목을 즐겨찾기에 추가/삭제하고 관리할 수 있는 기능입니다.

**배포일**: 2025-11-21
**Base URL**: `https://ox-api.biizbiiz.com` (프로덕션) / `http://localhost:8000` (로컬)
**API Version**: `/api/v1`

---

## 🔐 인증

모든 엔드포인트는 **JWT 토큰 인증이 필수**입니다.

```javascript
// Headers에 포함
{
  "Authorization": "Bearer {access_token}"
}
```

---

## 📡 API 엔드포인트

### 1. 즐겨찾기 목록 조회

사용자의 즐겨찾기 종목 목록을 페이지네이션과 함께 조회합니다.

#### Request

```http
GET /api/v1/favorites?limit={limit}&offset={offset}
```

**Query Parameters**

| 파라미터 | 타입 | 필수 | 기본값 | 설명 |
|---------|------|------|--------|------|
| `limit` | number | 선택 | 100 | 한 번에 가져올 개수 (최대 500) |
| `offset` | number | 선택 | 0 | 건너뛸 개수 (페이지네이션) |

**Headers**
```
Authorization: Bearer {access_token}
```

#### Response

**성공 (200 OK)**

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
      },
      {
        "symbol": "GOOGL",
        "name": "Alphabet Inc.",
        "market_category": "Q",
        "is_etf": false,
        "added_at": "2025-11-20T15:20:00Z"
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

**실패**

```json
{
  "success": false,
  "error": {
    "code": "FAVORITES_001",
    "message": "에러 메시지"
  }
}
```

#### TypeScript 타입

```typescript
interface FavoriteItem {
  symbol: string;           // 티커 심볼 (예: "AAPL")
  name: string;             // 회사명 (예: "Apple Inc.")
  market_category: string | null;  // 마켓 카테고리
  is_etf: boolean;          // ETF 여부
  added_at: string;         // ISO 8601 날짜 문자열
}

interface GetFavoritesResponse {
  success: boolean;
  data: {
    user_id: number;
    favorites: FavoriteItem[];
    total_count: number;
  };
  meta: {
    limit: number;
    offset: number;
    total_count: number;
    has_next: boolean;     // 다음 페이지 존재 여부
  };
}
```

#### 프론트엔드 구현 예시

```typescript
// React Query 사용 예시
const useFavorites = (limit = 100, offset = 0) => {
  return useQuery({
    queryKey: ['favorites', limit, offset],
    queryFn: async () => {
      const response = await fetch(
        `/api/v1/favorites?limit=${limit}&offset=${offset}`,
        {
          headers: {
            'Authorization': `Bearer ${getAccessToken()}`
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to fetch favorites');
      }

      return response.json();
    }
  });
};

// 사용
function FavoritesList() {
  const { data, isLoading, error } = useFavorites(50, 0);

  if (isLoading) return <Loading />;
  if (error) return <Error message={error.message} />;

  return (
    <div>
      {data.data.favorites.map(fav => (
        <FavoriteCard key={fav.symbol} {...fav} />
      ))}
      {data.meta.has_next && <LoadMoreButton />}
    </div>
  );
}
```

---

### 2. 즐겨찾기 추가

특정 종목을 즐겨찾기에 추가합니다.

#### Request

```http
POST /api/v1/favorites/{symbol}
```

**Path Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 티커 심볼 (예: AAPL, GOOGL) |

**Headers**
```
Authorization: Bearer {access_token}
```

#### Response

**성공 (200 OK)**

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

**실패 - 종목이 존재하지 않음 (404)**

```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Ticker symbol 'XYZ' not found in our database"
  }
}
```

**실패 - 이미 즐겨찾기에 있음 (409)**

```json
{
  "success": false,
  "error": {
    "code": "CONFLICT",
    "message": "Ticker 'AAPL' is already in your favorites"
  }
}
```

#### TypeScript 타입

```typescript
interface AddFavoriteResponse {
  success: boolean;
  data?: FavoriteItem;
  meta?: {
    message: string;
  };
  error?: {
    code: string;
    message: string;
  };
}
```

#### 프론트엔드 구현 예시

```typescript
// React Query Mutation 사용
const useAddFavorite = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (symbol: string) => {
      const response = await fetch(`/api/v1/favorites/${symbol}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`
        }
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error.message);
      }

      return data;
    },
    onSuccess: () => {
      // 즐겨찾기 목록 다시 불러오기
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
      toast.success('즐겨찾기에 추가되었습니다');
    },
    onError: (error: Error) => {
      toast.error(error.message);
    }
  });
};

// 사용
function AddFavoriteButton({ symbol }: { symbol: string }) {
  const { mutate, isPending } = useAddFavorite();

  return (
    <button
      onClick={() => mutate(symbol)}
      disabled={isPending}
    >
      {isPending ? '추가 중...' : '즐겨찾기 추가'}
    </button>
  );
}
```

---

### 3. 즐겨찾기 삭제

특정 종목을 즐겨찾기에서 제거합니다.

#### Request

```http
DELETE /api/v1/favorites/{symbol}
```

**Path Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 티커 심볼 (예: AAPL) |

**Headers**
```
Authorization: Bearer {access_token}
```

#### Response

**성공 (200 OK)**

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

**실패 - 즐겨찾기에 없음 (404)**

```json
{
  "success": false,
  "error": {
    "code": "NOT_FOUND",
    "message": "Ticker 'AAPL' is not in your favorites"
  }
}
```

#### TypeScript 타입

```typescript
interface RemoveFavoriteResponse {
  success: boolean;
  data?: {
    symbol: string;
  };
  meta?: {
    message: string;
  };
  error?: {
    code: string;
    message: string;
  };
}
```

#### 프론트엔드 구현 예시

```typescript
const useRemoveFavorite = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (symbol: string) => {
      const response = await fetch(`/api/v1/favorites/${symbol}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`
        }
      });

      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error.message);
      }

      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
      toast.success('즐겨찾기에서 제거되었습니다');
    }
  });
};

// 사용
function RemoveFavoriteButton({ symbol }: { symbol: string }) {
  const { mutate, isPending } = useRemoveFavorite();

  return (
    <button
      onClick={() => mutate(symbol)}
      disabled={isPending}
      className="text-red-500"
    >
      {isPending ? '삭제 중...' : '즐겨찾기 삭제'}
    </button>
  );
}
```

---

### 4. 즐겨찾기 여부 확인

특정 종목이 즐겨찾기에 있는지 확인합니다.

#### Request

```http
GET /api/v1/favorites/check/{symbol}
```

**Path Parameters**

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `symbol` | string | 필수 | 티커 심볼 (예: AAPL) |

**Headers**
```
Authorization: Bearer {access_token}
```

#### Response

**성공 (200 OK)**

```json
{
  "success": true,
  "data": {
    "symbol": "AAPL",
    "is_favorited": true
  }
}
```

#### TypeScript 타입

```typescript
interface CheckFavoriteResponse {
  success: boolean;
  data: {
    symbol: string;
    is_favorited: boolean;
  };
}
```

#### 프론트엔드 구현 예시

```typescript
const useIsFavorited = (symbol: string) => {
  return useQuery({
    queryKey: ['favorite-check', symbol],
    queryFn: async () => {
      const response = await fetch(`/api/v1/favorites/check/${symbol}`, {
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`
        }
      });
      const data = await response.json();
      return data.data.is_favorited;
    },
    enabled: !!symbol  // symbol이 있을 때만 실행
  });
};

// 사용: 토글 버튼
function FavoriteToggleButton({ symbol }: { symbol: string }) {
  const { data: isFavorited } = useIsFavorited(symbol);
  const addFavorite = useAddFavorite();
  const removeFavorite = useRemoveFavorite();

  const handleToggle = () => {
    if (isFavorited) {
      removeFavorite.mutate(symbol);
    } else {
      addFavorite.mutate(symbol);
    }
  };

  return (
    <button onClick={handleToggle}>
      {isFavorited ? '★' : '☆'} {/* 채워진 별 / 빈 별 */}
    </button>
  );
}
```

---

### 5. 즐겨찾기 심볼 목록 (간단 버전)

티커 심볼만 간단하게 배열로 받습니다. (상세 정보 없이 빠른 조회)

#### Request

```http
GET /api/v1/favorites/symbols/list
```

**Headers**
```
Authorization: Bearer {access_token}
```

#### Response

**성공 (200 OK)**

```json
{
  "success": true,
  "data": {
    "symbols": ["AAPL", "GOOGL", "MSFT", "TSLA"],
    "count": 4
  }
}
```

#### TypeScript 타입

```typescript
interface GetFavoriteSymbolsResponse {
  success: boolean;
  data: {
    symbols: string[];
    count: number;
  };
}
```

#### 프론트엔드 구현 예시

```typescript
// 사용 예: 드롭다운, 필터, 빠른 체크
const useFavoriteSymbols = () => {
  return useQuery({
    queryKey: ['favorite-symbols'],
    queryFn: async () => {
      const response = await fetch('/api/v1/favorites/symbols/list', {
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`
        }
      });
      const data = await response.json();
      return data.data.symbols; // string[]
    }
  });
};

// 사용: Set으로 변환하여 빠른 체크
function StockCard({ symbol }: { symbol: string }) {
  const { data: favoriteSymbols = [] } = useFavoriteSymbols();
  const favoriteSet = new Set(favoriteSymbols);
  const isFavorited = favoriteSet.has(symbol);

  return (
    <div>
      {symbol} {isFavorited && '★'}
    </div>
  );
}
```

---

## 🎨 UI/UX 권장사항

### 1. 즐겨찾기 버튼 위치

```typescript
// 종목 상세 페이지
<StockDetailPage>
  <StockHeader>
    <h1>{symbol} - {name}</h1>
    <FavoriteToggleButton symbol={symbol} />  {/* 여기! */}
  </StockHeader>
</StockDetailPage>

// 종목 목록 페이지
<StockCard>
  <div className="flex justify-between">
    <span>{symbol}</span>
    <FavoriteToggleButton symbol={symbol} />  {/* 여기! */}
  </div>
</StockCard>
```

### 2. 로딩 상태 처리

```typescript
function FavoriteButton({ symbol }: { symbol: string }) {
  const { data: isFavorited, isLoading } = useIsFavorited(symbol);
  const addFavorite = useAddFavorite();
  const removeFavorite = useRemoveFavorite();

  if (isLoading) {
    return <Spinner size="small" />;
  }

  const isPending = addFavorite.isPending || removeFavorite.isPending;

  return (
    <button
      disabled={isPending}
      className={isPending ? 'opacity-50 cursor-not-allowed' : ''}
    >
      {isPending ? <Spinner /> : isFavorited ? '★' : '☆'}
    </button>
  );
}
```

### 3. 에러 처리

```typescript
const useAddFavorite = () => {
  return useMutation({
    mutationFn: addFavoriteAPI,
    onError: (error: any) => {
      // 에러 코드별 메시지
      if (error.message.includes('not found')) {
        toast.error('존재하지 않는 종목입니다');
      } else if (error.message.includes('already in your favorites')) {
        toast.info('이미 즐겨찾기에 추가된 종목입니다');
      } else {
        toast.error('즐겨찾기 추가에 실패했습니다');
      }
    }
  });
};
```

### 4. 낙관적 업데이트 (Optimistic Update)

```typescript
const useToggleFavorite = (symbol: string) => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (action: 'add' | 'remove') => {
      if (action === 'add') {
        return addFavoriteAPI(symbol);
      } else {
        return removeFavoriteAPI(symbol);
      }
    },
    // 서버 응답 전에 UI 먼저 업데이트
    onMutate: async (action) => {
      await queryClient.cancelQueries({ queryKey: ['favorite-check', symbol] });

      const previousValue = queryClient.getQueryData(['favorite-check', symbol]);

      // 낙관적으로 UI 업데이트
      queryClient.setQueryData(['favorite-check', symbol], action === 'add');

      return { previousValue };
    },
    // 에러 시 롤백
    onError: (err, action, context) => {
      queryClient.setQueryData(
        ['favorite-check', symbol],
        context?.previousValue
      );
      toast.error('작업에 실패했습니다');
    },
    // 성공 시 서버 데이터로 갱신
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['favorite-check', symbol] });
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
    }
  });
};
```

---

## 📦 완성된 Custom Hook 예제

```typescript
// hooks/useFavorites.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'react-toastify';

const API_BASE = '/api/v1';

const getAccessToken = () => {
  // 실제 토큰 가져오기 로직
  return localStorage.getItem('access_token') || '';
};

// API 호출 함수들
const favoritesAPI = {
  getList: async (limit = 100, offset = 0) => {
    const response = await fetch(
      `${API_BASE}/favorites?limit=${limit}&offset=${offset}`,
      {
        headers: { Authorization: `Bearer ${getAccessToken()}` }
      }
    );
    return response.json();
  },

  add: async (symbol: string) => {
    const response = await fetch(`${API_BASE}/favorites/${symbol}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error.message);
    return data;
  },

  remove: async (symbol: string) => {
    const response = await fetch(`${API_BASE}/favorites/${symbol}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    const data = await response.json();
    if (!data.success) throw new Error(data.error.message);
    return data;
  },

  check: async (symbol: string) => {
    const response = await fetch(`${API_BASE}/favorites/check/${symbol}`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    const data = await response.json();
    return data.data.is_favorited;
  },

  getSymbols: async () => {
    const response = await fetch(`${API_BASE}/favorites/symbols/list`, {
      headers: { Authorization: `Bearer ${getAccessToken()}` }
    });
    const data = await response.json();
    return data.data.symbols;
  }
};

// Custom Hooks
export const useFavorites = (limit = 100, offset = 0) => {
  return useQuery({
    queryKey: ['favorites', limit, offset],
    queryFn: () => favoritesAPI.getList(limit, offset)
  });
};

export const useAddFavorite = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: favoritesAPI.add,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
      toast.success('즐겨찾기에 추가되었습니다');
    },
    onError: (error: Error) => {
      toast.error(error.message);
    }
  });
};

export const useRemoveFavorite = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: favoritesAPI.remove,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['favorites'] });
      toast.success('즐겨찾기에서 제거되었습니다');
    },
    onError: (error: Error) => {
      toast.error(error.message);
    }
  });
};

export const useIsFavorited = (symbol: string) => {
  return useQuery({
    queryKey: ['favorite-check', symbol],
    queryFn: () => favoritesAPI.check(symbol),
    enabled: !!symbol
  });
};

export const useFavoriteSymbols = () => {
  return useQuery({
    queryKey: ['favorite-symbols'],
    queryFn: favoritesAPI.getSymbols
  });
};

// 토글 Hook (가장 많이 쓰일 것)
export const useToggleFavorite = (symbol: string) => {
  const { data: isFavorited } = useIsFavorited(symbol);
  const addFavorite = useAddFavorite();
  const removeFavorite = useRemoveFavorite();

  const toggle = () => {
    if (isFavorited) {
      removeFavorite.mutate(symbol);
    } else {
      addFavorite.mutate(symbol);
    }
  };

  return {
    isFavorited,
    toggle,
    isLoading: addFavorite.isPending || removeFavorite.isPending
  };
};
```

---

## 🧪 테스트 방법

### Postman / Thunder Client

1. **환경 변수 설정**
   ```
   BASE_URL: http://localhost:8000
   ACCESS_TOKEN: {로그인 후 받은 JWT 토큰}
   ```

2. **테스트 시퀀스**
   ```
   1. POST /api/v1/favorites/AAPL        # 추가
   2. GET /api/v1/favorites               # 목록 확인
   3. GET /api/v1/favorites/check/AAPL   # 여부 확인 (true)
   4. DELETE /api/v1/favorites/AAPL      # 삭제
   5. GET /api/v1/favorites/check/AAPL   # 여부 확인 (false)
   ```

### cURL 테스트

```bash
# 1. 로그인해서 토큰 받기
TOKEN=$(curl -X POST "http://localhost:8000/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"password"}' \
  | jq -r '.data.access_token')

# 2. 즐겨찾기 추가
curl -X POST "http://localhost:8000/api/v1/favorites/AAPL" \
  -H "Authorization: Bearer $TOKEN"

# 3. 목록 조회
curl -X GET "http://localhost:8000/api/v1/favorites" \
  -H "Authorization: Bearer $TOKEN"

# 4. 여부 확인
curl -X GET "http://localhost:8000/api/v1/favorites/check/AAPL" \
  -H "Authorization: Bearer $TOKEN"

# 5. 삭제
curl -X DELETE "http://localhost:8000/api/v1/favorites/AAPL" \
  -H "Authorization: Bearer $TOKEN"
```

---

## 🚨 에러 코드 정리

| 에러 코드 | HTTP 상태 | 설명 | 사용자 메시지 예시 |
|----------|----------|------|------------------|
| `NOT_FOUND` | 404 | 종목이 존재하지 않음 | "존재하지 않는 종목입니다" |
| `NOT_FOUND` | 404 | 즐겨찾기에 없음 (삭제 시) | "즐겨찾기에 없는 종목입니다" |
| `CONFLICT` | 409 | 이미 즐겨찾기에 있음 | "이미 즐겨찾기에 추가된 종목입니다" |
| `VALIDATION_ERROR` | 422 | 작업 실패 | "작업에 실패했습니다. 다시 시도해주세요" |
| `FAVORITES_001` | 500 | 목록 조회 실패 | "즐겨찾기 목록을 불러올 수 없습니다" |
| `FAVORITES_002` | 500 | 추가 실패 | "즐겨찾기 추가에 실패했습니다" |
| `FAVORITES_003` | 500 | 삭제 실패 | "즐겨찾기 삭제에 실패했습니다" |

---

## 📝 체크리스트

프론트엔드 개발 시 확인사항:

- [ ] JWT 토큰을 모든 요청 헤더에 포함
- [ ] 로딩 상태 표시 (버튼 disabled, 스피너 등)
- [ ] 에러 처리 및 사용자 피드백 (toast, alert 등)
- [ ] 즐겨찾기 추가/삭제 후 목록 새로고침
- [ ] 페이지네이션 구현 (무한 스크롤 or 페이지 버튼)
- [ ] 낙관적 업데이트로 UX 개선
- [ ] 로그아웃 시 캐시 초기화
- [ ] 접근성: 키보드 네비게이션, 스크린 리더 지원

---

## 🔗 관련 문서

- [백엔드 상세 문서](./FAVORITES_FEATURE.md)
- [API Swagger 문서](http://localhost:8000/docs) (로컬 개발 시)

---

## 💬 문의

- 백엔드 API 이슈: GitHub Issues
- 통합 테스트 필요 시: 백엔드 팀에 요청
- Swagger 문서에서 직접 테스트 가능: `/docs` 엔드포인트

---

**작성일**: 2025-11-21
**작성자**: Backend Team
**최종 수정**: 2025-11-21

# Frontend API Reference

React TypeScript + React Query 프론트엔드 개발을 위한 O/X 예측 서비스 API 문서입니다.

## 📋 목차

- [기본 설정](#기본-설정)
- [공통 타입 정의](#공통-타입-정의)
- [아키텍처 패턴](#아키텍처-패턴)
- [인증 시스템](#인증-시스템)
- [사용자 관리](#사용자-관리)
- [예측 시스템](#예측-시스템)
- [세션 관리](#세션-관리)
- [종목 유니버스](#종목-유니버스)
- [포인트 시스템](#포인트-시스템)
- [광고 및 슬롯](#광고-및-슬롯)
- [리워드 시스템](#리워드-시스템)
- [React Query 통합](#react-query-통합)
- [에러 처리](#에러-처리)

## 🔧 기본 설정

### Base URL

```typescript
const API_BASE_URL = "https://your-domain.com/api/v1";
```

### 인증 헤더

```typescript
const headers = {
  Authorization: `Bearer ${token}`,
  "Content-Type": "application/json",
};
```

## 🏗️ 공통 타입 정의

### Base Response

```typescript
interface BaseResponse<T = any> {
  success: boolean;
  data?: T;
  error?: ApiError;
  meta?: {
    limit?: number;
    offset?: number;
    total_count?: number;
    has_next?: boolean;
    [key: string]: any;
  };
}

interface ApiError {
  code: ErrorCode;
  message: string;
  details?: Record<string, any>;
}

enum ErrorCode {
  // Auth related
  UNAUTHORIZED = "AUTH_001",
  FORBIDDEN = "AUTH_002",
  TOKEN_EXPIRED = "AUTH_003",
  INVALID_CREDENTIALS = "AUTH_004",

  // OAuth related
  OAUTH_INVALID_CODE = "OAUTH_001",
  OAUTH_STATE_MISMATCH = "OAUTH_002",
  OAUTH_PROVIDER_ERROR = "OAUTH_003",

  // User related
  USER_ALREADY_EXISTS = "USER_001",
  USER_NOT_FOUND = "USER_002",
}
```

### 페이지네이션

```typescript
interface PaginationParams {
  limit?: number; // 엔드포인트별 범위 다름
  offset?: number; // 0 이상, 기본값: 0
}

// BaseResponse 래핑하는 페이지네이션 (대부분)
interface PaginatedResponse<T> extends BaseResponse<T> {
  meta?: {
    limit: number;
    offset: number;
    total_count?: number;
    has_next?: boolean;
  };
}

// 직접 응답하는 페이지네이션 (일부)
interface DirectPaginatedResponse<T> {
  data: T[];
  total_count: number;
  has_next: boolean;
  limit: number;
  offset: number;
}

// 엔드포인트별 페이지네이션 제한
const PAGINATION_LIMITS = {
  PREDICTIONS_HISTORY: { min: 1, max: 100, default: 50 },
  POINTS_LEDGER: { min: 1, max: 100, default: 50 },
  REWARDS_HISTORY: { min: 1, max: 100, default: 50 },
  USER_LIST: { min: 1, max: 100, default: 20 },
  USER_SEARCH: { min: 1, max: 50, default: 20 },
} as const;
```

## 🏛️ 아키텍처 패턴

React Query + Service/Custom Hook 패턴을 사용한 클린 아키텍처입니다.

### 폴더 구조

```typescript
src/
├── api/
│   ├── client.ts              // Axios/Fetch 클라이언트
│   ├── services/              // API 서비스 레이어
│   │   ├── authService.ts
│   │   ├── userService.ts
│   │   ├── predictionService.ts
│   │   └── ...
│   └── types/                 // API 타입 정의
│       ├── auth.ts
│       ├── user.ts
│       └── ...
├── hooks/                     // React Query 커스텀 훅
│   ├── auth/
│   │   ├── useAuth.ts
│   │   └── useTokenRefresh.ts
│   ├── user/
│   │   ├── useUser.ts
│   │   └── useUserProfile.ts
│   └── ...
└── utils/
    ├── queryClient.ts         // React Query 설정
    └── storage.ts             // 로컬 스토리지 관리
```

### 레이어 분리 원칙

1. **Service Layer**: 순수한 API 호출 로직
2. **Hook Layer**: React Query와 UI 상태 관리
3. **Component Layer**: UI 렌더링과 사용자 상호작용

## 🔐 인증 시스템

### OAuth 로그인 시작

```typescript
// GET /auth/oauth/{provider}/authorize?client_redirect={url}
interface OAuthAuthorizeParams {
  provider: "google" | "kakao";
  client_redirect: string; // 로그인 후 리다이렉트될 URL
}

// 브라우저가 자동으로 OAuth 제공자 페이지로 리다이렉트됨
```

### OAuth 콜백 응답 (URL 파라미터)

```typescript
// 로그인 성공 후 client_redirect URL에 쿼리 파라미터로 전달
interface OAuthCallbackParams {
  token: string; // JWT 토큰
  user_id: string; // 사용자 ID
  nickname: string; // 사용자 닉네임
  provider: string; // OAuth 제공자
  is_new_user: string; // 'true' | 'false' 신규 사용자 여부
}

// 예시: https://yourapp.com/callback?token=eyJ...&user_id=123&nickname=홍길동&provider=google&is_new_user=true
```

### 토큰 갱신

```typescript
// POST /auth/token/refresh
interface TokenRefreshRequest {
  current_token: string;
}

interface TokenRefreshResponse {
  access_token: string;
  token_type: "bearer";
}

const refreshToken = async (
  currentToken: string
): Promise<TokenRefreshResponse> => {
  const response = await fetch(`${API_BASE_URL}/auth/token/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(currentToken),
  });

  const result: BaseResponse<TokenRefreshResponse> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 로그아웃

```typescript
// POST /auth/logout
const logout = async (token: string): Promise<void> => {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(token),
  });
};
```

## 👤 사용자 관리

### 사용자 타입 정의

```typescript
enum AuthProvider {
  LOCAL = "local",
  GOOGLE = "google",
  KAKAO = "kakao",
}

enum UserRole {
  USER = "user",
  PREMIUM = "premium",
  ADMIN = "admin",
}

interface User {
  id: number;
  email: string;
  nickname: string;
  auth_provider: AuthProvider;
  created_at: string; // ISO 8601
  last_login_at: string | null; // ISO 8601
  is_active: boolean;
  role: UserRole;
}

interface UserProfile {
  user_id: number;
  email: string;
  nickname: string;
  auth_provider: AuthProvider;
  created_at: string; // ISO 8601
  is_oauth_user: boolean;
}

interface UserUpdate {
  nickname?: string;
  email?: string;
}
```

### 내 프로필 조회

```typescript
// GET /users/me
const getMyProfile = async (token: string): Promise<User> => {
  const response = await fetch(`${API_BASE_URL}/users/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  const result: BaseResponse<User> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 프로필 업데이트

```typescript
// PUT /users/me
const updateMyProfile = async (
  token: string,
  updates: UserUpdate
): Promise<User> => {
  const response = await fetch(`${API_BASE_URL}/users/me`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(updates),
  });

  const result: BaseResponse<User> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 사용자 목록 조회 (페이지네이션)

```typescript
// GET /users/?limit={limit}&offset={offset}
interface UserListParams extends PaginationParams {
  limit?: number; // 1-100, 기본값: 20
  offset?: number; // 0 이상, 기본값: 0
}

interface UserListResult {
  users: Array<{
    id: number;
    nickname: string;
    auth_provider: AuthProvider;
    created_at: string; // ISO 8601
  }>;
  count: number;
}

const getUserList = async (
  token: string,
  params?: UserListParams
): Promise<PaginatedResponse<UserListResult>> => {
  const queryString = new URLSearchParams({
    limit: (params?.limit || PAGINATION_LIMITS.USER_LIST.default).toString(),
    offset: (params?.offset || 0).toString(),
  });

  const response = await fetch(`${API_BASE_URL}/users/?${queryString}`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  return await response.json();
};
```

### 사용자 검색 (제한된 페이지네이션)

```typescript
// GET /users/search/nickname?q={nickname}&limit={limit}
interface UserSearchParams {
  q: string; // 2-50자
  limit?: number; // 1-50, 기본값: 20 (offset 없음)
}

interface UserSearchResult {
  users: Array<{
    id: number;
    nickname: string;
    auth_provider: AuthProvider;
  }>;
  count: number;
}

const searchUsers = async (
  token: string,
  params: UserSearchParams
): Promise<UserSearchResult> => {
  const queryString = new URLSearchParams({
    q: params.q,
    limit: (params.limit || PAGINATION_LIMITS.USER_SEARCH.default).toString(),
  });

  const response = await fetch(
    `${API_BASE_URL}/users/search/nickname?${queryString}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  const result: BaseResponse<UserSearchResult> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 사용자 Service Layer

```typescript
// api/services/userService.ts
export class UserService {
  // 내 프로필 조회
  static async getMyProfile(token: string): Promise<User> {
    return await apiClient.request<User>("/users/me", {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  // 프로필 업데이트
  static async updateMyProfile(
    token: string,
    updates: UserUpdate
  ): Promise<User> {
    return await apiClient.request<User>("/users/me", {
      method: "PUT",
      headers: { Authorization: `Bearer ${token}` },
      body: JSON.stringify(updates),
    });
  }

  // 사용자 목록 조회 (페이지네이션)
  static async getUserList(
    token: string,
    params?: UserListParams
  ): Promise<UserListResult> {
    const queryString = new URLSearchParams({
      limit: (params?.limit || PAGINATION_LIMITS.USER_LIST.default).toString(),
      offset: (params?.offset || 0).toString(),
    });

    return await apiClient.request<UserListResult>(`/users/?${queryString}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  }

  // 사용자 검색
  static async searchUsers(
    token: string,
    params: UserSearchParams
  ): Promise<UserSearchResult> {
    const queryString = new URLSearchParams({
      q: params.q,
      limit: (params.limit || PAGINATION_LIMITS.USER_SEARCH.default).toString(),
    });

    return await apiClient.request<UserSearchResult>(
      `/users/search/nickname?${queryString}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
  }
}
```

### 사용자 Custom Hooks

```typescript
// hooks/user/useUser.ts
export const useMyProfile = () => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["user", "profile"],
    queryFn: () => UserService.getMyProfile(token!),
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5분
  });
};

export const useUpdateProfile = () => {
  const queryClient = useQueryClient();
  const { token } = useAuth();

  return useMutation({
    mutationFn: (updates: UserUpdate) =>
      UserService.updateMyProfile(token!, updates),
    onSuccess: () => {
      queryClient.invalidateQueries(["user", "profile"]);
    },
  });
};

export const useUserList = (params?: UserListParams) => {
  const { token } = useAuth();

  return useInfiniteQuery({
    queryKey: ["users", "list", params],
    queryFn: ({ pageParam = 0 }) =>
      UserService.getUserList(token!, {
        ...params,
        offset: pageParam,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const limit = params?.limit || PAGINATION_LIMITS.USER_LIST.default;
      return lastPage.count === limit ? allPages.length * limit : undefined;
    },
    enabled: !!token,
    staleTime: 2 * 60 * 1000, // 2분
  });
};

export const useUserSearch = (query: string, limit?: number) => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["users", "search", query, limit],
    queryFn: () => UserService.searchUsers(token!, { q: query, limit }),
    enabled: !!token && query.length >= 2,
    staleTime: 30 * 1000, // 30초
    debounceMs: 300, // 300ms 디바운스
  });
};
```

## 🎯 예측 시스템

### 예측 타입 정의

```typescript
enum PredictionChoice {
  UP = "UP", // 상승 예측
  DOWN = "DOWN", // 하락 예측
}

enum PredictionStatus {
  PENDING = "PENDING", // 대기 중
  LOCKED = "LOCKED", // 정산용 잠금
  CORRECT = "CORRECT", // 정답
  INCORRECT = "INCORRECT", // 오답
  VOID = "VOID", // 무효 (환불)
}

interface Prediction {
  id: number;
  user_id: number;
  symbol: string;
  choice: PredictionChoice;
  status: PredictionStatus;
  trading_day: string; // YYYY-MM-DD
  created_at: string; // ISO 8601
  points_awarded?: number;
}

interface PredictionCreate {
  symbol: string; // 대문자 1-5자 (예: AAPL)
  choice: PredictionChoice;
}

interface PredictionUpdate {
  choice: PredictionChoice;
}
```

### 예측 제출

```typescript
// POST /predictions/{symbol}
const submitPrediction = async (
  token: string,
  symbol: string,
  choice: PredictionChoice
): Promise<Prediction> => {
  const response = await fetch(
    `${API_BASE_URL}/predictions/${symbol.toUpperCase()}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ choice }),
    }
  );

  const result: BaseResponse<{ prediction: Prediction }> =
    await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.prediction;
};
```

### 예측 수정

```typescript
// PUT /predictions/{prediction_id}
const updatePrediction = async (
  token: string,
  predictionId: number,
  choice: PredictionChoice
): Promise<Prediction> => {
  const response = await fetch(`${API_BASE_URL}/predictions/${predictionId}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ choice }),
  });

  const result: BaseResponse<{ prediction: Prediction }> =
    await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.prediction;
};
```

### 예측 취소

```typescript
// DELETE /predictions/{prediction_id}
const cancelPrediction = async (
  token: string,
  predictionId: number
): Promise<Prediction> => {
  const response = await fetch(`${API_BASE_URL}/predictions/${predictionId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });

  const result: BaseResponse<{ prediction: Prediction }> =
    await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.prediction;
};
```

### 특정 날짜 예측 조회

```typescript
// GET /predictions/day/{trading_day}
const getUserPredictionsForDay = async (
  token: string,
  tradingDay: string // YYYY-MM-DD
): Promise<Prediction[]> => {
  const response = await fetch(
    `${API_BASE_URL}/predictions/day/${tradingDay}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  const result: BaseResponse<{ result: Prediction[] }> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.result;
};
```

### 남은 예측 슬롯 조회

```typescript
// GET /predictions/remaining/{trading_day}
const getRemainingPredictions = async (
  token: string,
  tradingDay: string
): Promise<number> => {
  const response = await fetch(
    `${API_BASE_URL}/predictions/remaining/${tradingDay}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  const result: BaseResponse<{ remaining_predictions: number }> =
    await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.remaining_predictions;
};
```

### 예측 이력 조회 (페이지네이션)

```typescript
// GET /predictions/history?limit={limit}&offset={offset}
interface PredictionHistoryParams extends PaginationParams {
  limit?: number; // 1-100, 기본값: 50
  offset?: number; // 0 이상, 기본값: 0
}

const getPredictionHistory = async (
  token: string,
  params?: PredictionHistoryParams
): Promise<Prediction[]> => {
  const queryString = new URLSearchParams({
    ...(params?.limit && { limit: params.limit.toString() }),
    ...(params?.offset && { offset: params.offset.toString() }),
  });

  const response = await fetch(
    `${API_BASE_URL}/predictions/history?${queryString}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  const result: BaseResponse<{ history: Prediction[] }> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.history;
};
```

### 예측 Service Layer

```typescript
// api/services/predictionService.ts
export class PredictionService {
  // 예측 제출
  static async submitPrediction(
    token: string,
    symbol: string,
    choice: PredictionChoice
  ): Promise<Prediction> {
    return await apiClient
      .request<{ prediction: Prediction }>(
        `/predictions/${symbol.toUpperCase()}`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: JSON.stringify({ choice }),
        }
      )
      .then((res) => res.prediction);
  }

  // 예측 이력 조회 (페이지네이션)
  static async getPredictionHistory(
    token: string,
    params?: PredictionHistoryParams
  ): Promise<Prediction[]> {
    const queryString = new URLSearchParams({
      limit: (
        params?.limit || PAGINATION_LIMITS.PREDICTIONS_HISTORY.default
      ).toString(),
      offset: (params?.offset || 0).toString(),
    });

    return await apiClient
      .request<{ history: Prediction[] }>(
        `/predictions/history?${queryString}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      .then((res) => res.history);
  }

  // 특정 날짜 예측 조회
  static async getUserPredictionsForDay(
    token: string,
    tradingDay: string
  ): Promise<Prediction[]> {
    return await apiClient
      .request<{ result: Prediction[] }>(`/predictions/day/${tradingDay}`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => res.result);
  }

  // 남은 예측 슬롯 조회
  static async getRemainingPredictions(
    token: string,
    tradingDay: string
  ): Promise<number> {
    return await apiClient
      .request<{ remaining_predictions: number }>(
        `/predictions/remaining/${tradingDay}`,
        { headers: { Authorization: `Bearer ${token}` } }
      )
      .then((res) => res.remaining_predictions);
  }
}
```

### 예측 Custom Hooks

```typescript
// hooks/predictions/usePredictions.ts
export const useSubmitPrediction = () => {
  const queryClient = useQueryClient();
  const { token } = useAuth();

  return useMutation({
    mutationFn: ({
      symbol,
      choice,
    }: {
      symbol: string;
      choice: PredictionChoice;
    }) => PredictionService.submitPrediction(token!, symbol, choice),
    onSuccess: () => {
      // 관련 데이터 무효화
      queryClient.invalidateQueries(["predictions"]);
      queryClient.invalidateQueries(["points", "balance"]);
      queryClient.invalidateQueries(["ads", "available-slots"]);
    },
  });
};

export const usePredictionHistory = (params?: PredictionHistoryParams) => {
  const { token } = useAuth();

  return useInfiniteQuery({
    queryKey: ["predictions", "history", params],
    queryFn: ({ pageParam = 0 }) =>
      PredictionService.getPredictionHistory(token!, {
        ...params,
        offset: pageParam,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const limit =
        params?.limit || PAGINATION_LIMITS.PREDICTIONS_HISTORY.default;
      return lastPage.length === limit ? allPages.length * limit : undefined;
    },
    enabled: !!token,
    staleTime: 2 * 60 * 1000, // 2분
  });
};

export const usePredictionsForDay = (tradingDay: string) => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["predictions", "day", tradingDay],
    queryFn: () =>
      PredictionService.getUserPredictionsForDay(token!, tradingDay),
    enabled: !!token && !!tradingDay,
    staleTime: 30 * 1000, // 30초
  });
};

export const useRemainingPredictions = (tradingDay: string) => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["predictions", "remaining", tradingDay],
    queryFn: () =>
      PredictionService.getRemainingPredictions(token!, tradingDay),
    enabled: !!token && !!tradingDay,
    refetchInterval: 30 * 1000, // 30초마다 갱신
  });
};
```

## 📅 세션 관리

### 세션 타입 정의

```typescript
enum SessionStatus {
  OPEN = "OPEN", // 예측 가능
  CLOSED = "CLOSED", // 예측 마감
}

interface Session {
  id: number;
  trading_day: string; // YYYY-MM-DD
  status: SessionStatus;
  created_at: string; // ISO 8601
  closed_at?: string; // ISO 8601
}

interface MarketStatus {
  current_date: string; // YYYY-MM-DD
  current_time_kst: string; // HH:MM:SS
  is_trading_day: boolean;
  message: string;
  next_trading_day?: string; // YYYY-MM-DD (휴일인 경우)
}

interface SessionTodayResponse {
  session: Session | null;
  market_status: MarketStatus;
}
```

### 오늘 세션 조회

```typescript
// GET /session/today
const getTodaySession = async (): Promise<SessionTodayResponse> => {
  const response = await fetch(`${API_BASE_URL}/session/today`);

  const result: BaseResponse<SessionTodayResponse> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 예측 가능 여부 확인

```typescript
// GET /session/can-predict?trading_day={date}
interface PredictionAvailability {
  can_predict: boolean;
  trading_day: string; // YYYY-MM-DD
  current_time: string; // YYYY-MM-DD HH:MM:SS
}

const canPredictNow = async (
  tradingDay?: string
): Promise<PredictionAvailability> => {
  const url = tradingDay
    ? `${API_BASE_URL}/session/can-predict?trading_day=${tradingDay}`
    : `${API_BASE_URL}/session/can-predict`;

  const response = await fetch(url);

  const result: BaseResponse<PredictionAvailability> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

## 🌌 종목 유니버스

### 유니버스 타입 정의

```typescript
interface UniverseItem {
  symbol: string; // 대문자 1-5자 (예: AAPL)
  seq: number; // 1-20 순서
}

interface UniverseItemWithPrice extends UniverseItem {
  company_name: string;
  current_price: number;
  previous_close: number;
  change_percent: number;
  change_direction: "UP" | "DOWN" | "FLAT";
  formatted_change: string; // '+2.01%' 형식
}

interface UniverseResponse {
  trading_day: string; // YYYY-MM-DD
  symbols: UniverseItem[];
  total_count: number;
}

interface UniverseWithPricesResponse {
  trading_day: string; // YYYY-MM-DD
  symbols: UniverseItemWithPrice[];
  total_count: number;
  last_updated: string; // ISO 8601
}
```

### 오늘의 종목 조회

```typescript
// GET /universe/today
const getTodayUniverse = async (): Promise<UniverseResponse> => {
  const response = await fetch(`${API_BASE_URL}/universe/today`);

  const result: BaseResponse<{ universe: UniverseResponse | null }> =
    await response.json();
  if (!result.success) throw new Error(result.error?.message);
  if (!result.data?.universe) throw new Error("No universe available today");
  return result.data.universe;
};
```

### 가격 정보 포함 종목 조회

```typescript
// GET /universe/today/with-prices
const getTodayUniverseWithPrices =
  async (): Promise<UniverseWithPricesResponse> => {
    const response = await fetch(`${API_BASE_URL}/universe/today/with-prices`);

    const result: BaseResponse<{
      universe: UniverseWithPricesResponse | null;
    }> = await response.json();
    if (!result.success) throw new Error(result.error?.message);
    if (!result.data?.universe) throw new Error("No universe available today");
    return result.data.universe;
  };
```

## 💰 포인트 시스템

### 포인트 타입 정의

```typescript
// BaseResponse를 사용하는 엔드포인트 (/users/me/points/*)
interface PointsBalance {
  balance: number;
  user_id: number;
}

interface PointsLedgerEntry {
  id: number;
  transaction_type: string;
  delta_points: number; // 양수: 획득, 음수: 사용
  balance_after: number;
  reason: string;
  ref_id?: string;
  created_at: string; // ISO 8601
}

interface PointsLedger {
  balance: number;
  entries: PointsLedgerEntry[];
  total_count: number;
  has_next: boolean;
}

// 직접 응답하는 엔드포인트 (/points/*)
interface PointsBalanceResponse {
  balance: number;
}

interface PointsLedgerResponse {
  balance: number;
  entries: PointsLedgerEntry[];
  total_count: number;
  has_next: boolean;
}

interface UserProfileWithPoints {
  user_profile: UserProfile;
  points_balance: number;
  last_updated: string; // ISO 8601
}

interface UserFinancialSummary {
  user_id: number;
  current_balance: number;
  points_earned_today: number;
  can_make_predictions: boolean;
  summary_date: string; // YYYY-MM-DD
}

interface AffordabilityCheck {
  amount: number;
  can_afford: boolean;
  current_balance: number;
  shortfall: number; // 부족한 포인트 (can_afford가 false일 때)
}
```

### 포인트 Service Layer

```typescript
// api/services/pointService.ts
export class PointService {
  // 내 포인트 잔액 조회 (BaseResponse 래핑)
  static async getMyPointsBalance(token: string): Promise<PointsBalance> {
    const response = await apiClient.request<PointsBalance>(
      "/users/me/points/balance",
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    return response;
  }

  // 포인트 잔액 조회 (직접 응답)
  static async getPointsBalance(token: string): Promise<PointsBalanceResponse> {
    const response = await fetch(`${API_BASE_URL}/points/balance`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    return await response.json();
  }

  // 포인트 거래 내역 조회 (BaseResponse 래핑)
  static async getMyPointsLedger(
    token: string,
    pagination?: PaginationParams
  ): Promise<PointsLedger> {
    const queryString = new URLSearchParams({
      ...(pagination?.limit && { limit: pagination.limit.toString() }),
      ...(pagination?.offset && { offset: pagination.offset.toString() }),
    });

    return await apiClient.request<PointsLedger>(
      `/users/me/points/ledger?${queryString}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
  }

  // 포인트 거래 내역 조회 (직접 응답)
  static async getPointsLedger(
    token: string,
    pagination?: PaginationParams
  ): Promise<PointsLedgerResponse> {
    const queryString = new URLSearchParams({
      ...(pagination?.limit && { limit: pagination.limit.toString() }),
      ...(pagination?.offset && { offset: pagination.offset.toString() }),
    });

    const response = await fetch(
      `${API_BASE_URL}/points/ledger?${queryString}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    return await response.json();
  }

  // 프로필 + 포인트 정보
  static async getMyProfileWithPoints(
    token: string
  ): Promise<UserProfileWithPoints> {
    return await apiClient.request<UserProfileWithPoints>(
      "/users/me/profile-with-points",
      { headers: { Authorization: `Bearer ${token}` } }
    );
  }

  // 재정 요약 정보
  static async getMyFinancialSummary(
    token: string
  ): Promise<UserFinancialSummary> {
    return await apiClient.request<UserFinancialSummary>(
      "/users/me/financial-summary",
      { headers: { Authorization: `Bearer ${token}` } }
    );
  }

  // 지불 가능 여부 확인
  static async checkAffordability(
    token: string,
    amount: number
  ): Promise<AffordabilityCheck> {
    return await apiClient.request<AffordabilityCheck>(
      `/users/me/can-afford/${amount}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
  }
}
```

### 포인트 Custom Hooks

```typescript
// hooks/points/usePoints.ts
export const usePointsBalance = () => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["points", "balance"],
    queryFn: () => PointService.getMyPointsBalance(token!),
    enabled: !!token,
    staleTime: 30 * 1000, // 30초
  });
};

export const usePointsLedger = (pagination?: PaginationParams) => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["points", "ledger", pagination],
    queryFn: () => PointService.getMyPointsLedger(token!, pagination),
    enabled: !!token,
    keepPreviousData: true,
  });
};

export const useProfileWithPoints = () => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["user", "profile-with-points"],
    queryFn: () => PointService.getMyProfileWithPoints(token!),
    enabled: !!token,
    staleTime: 60 * 1000, // 1분
  });
};
```

## 🎬 광고 및 슬롯 시스템

### 광고 타입 정의

```typescript
enum UnlockMethod {
  AD = "AD",
  COOLDOWN = "COOLDOWN",
}

// 사용 가능한 슬롯 정보 응답 (직접 응답)
interface AvailableSlotsResponse {
  current_max_predictions: number;
  predictions_made: number;
  available_predictions: number;
  can_unlock_by_ad: boolean;
  can_unlock_by_cooldown: boolean;
  today_ad_unlocks: number;
  today_cooldown_unlocks: number;
}

// 광고 시청 완료 응답 (직접 응답)
interface AdWatchCompleteResponse {
  success: boolean;
  message: string;
  slots_unlocked: number;
  current_max_predictions: number;
}

// 슬롯 해제 응답 (직접 응답)
interface SlotIncreaseResponse {
  success: boolean;
  message: string;
  current_max_predictions: number;
  unlocked_slots: number;
  method_used: string;
}

// 광고 해제 히스토리
interface AdUnlockHistory {
  trading_day: string; // date format
  total_unlocks: number;
  ad_unlocks: number;
  cooldown_unlocks: number;
  records: AdUnlockResponse[];
}

interface AdUnlockResponse {
  id: number;
  user_id: number;
  trading_day: string; // date format
  method: string;
  unlocked_slots: number;
}

// 요청 스키마
interface AdWatchCompleteRequest {
  ad_id?: string;
  duration?: number;
}

interface SlotIncreaseRequest {
  method: UnlockMethod;
}
```

### 광고 Service Layer

```typescript
// api/services/adService.ts
export class AdService {
  // 사용 가능한 슬롯 정보 조회 (직접 응답)
  static async getAvailableSlots(
    token: string
  ): Promise<AvailableSlotsResponse> {
    const response = await fetch(`${API_BASE_URL}/ads/available-slots`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  // 광고 시청 완료 처리 (직접 응답)
  static async completeAdWatch(
    token: string,
    request?: AdWatchCompleteRequest
  ): Promise<AdWatchCompleteResponse> {
    const response = await fetch(`${API_BASE_URL}/ads/watch-complete`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: request ? JSON.stringify(request) : undefined,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  // 쿨다운 슬롯 해제 (직접 응답)
  static async unlockSlot(
    token: string,
    request?: SlotIncreaseRequest
  ): Promise<SlotIncreaseResponse> {
    const response = await fetch(`${API_BASE_URL}/ads/unlock-slot`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: request
        ? JSON.stringify(request)
        : JSON.stringify({ method: "COOLDOWN" }),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  // 광고 해제 히스토리 조회 (직접 응답)
  static async getAdUnlockHistory(token: string): Promise<AdUnlockHistory[]> {
    const response = await fetch(`${API_BASE_URL}/ads/history`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }
}
```

### 광고 Custom Hooks

```typescript
// hooks/ads/useAds.ts
export const useAvailableSlots = () => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["ads", "available-slots"],
    queryFn: () => AdService.getAvailableSlots(token!),
    enabled: !!token,
    refetchInterval: 60 * 1000, // 1분마다 갱신
  });
};

export const useCompleteAdWatch = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      token,
      request,
    }: {
      token: string;
      request?: AdWatchCompleteRequest;
    }) => AdService.completeAdWatch(token, request),
    onSuccess: () => {
      // 관련 데이터 무효화
      queryClient.invalidateQueries(["ads", "available-slots"]);
      queryClient.invalidateQueries(["predictions", "remaining"]);
      queryClient.invalidateQueries(["ads", "history"]);
    },
  });
};

export const useUnlockSlot = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      token,
      request,
    }: {
      token: string;
      request?: SlotIncreaseRequest;
    }) => AdService.unlockSlot(token, request),
    onSuccess: () => {
      queryClient.invalidateQueries(["ads", "available-slots"]);
      queryClient.invalidateQueries(["predictions", "remaining"]);
      queryClient.invalidateQueries(["ads", "history"]);
    },
  });
};

export const useAdUnlockHistory = () => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["ads", "history"],
    queryFn: () => AdService.getAdUnlockHistory(token!),
    enabled: !!token,
    staleTime: 5 * 60 * 1000, // 5분
  });
};
```

## 🎁 리워드 시스템

### 리워드 타입 정의

```typescript
// 리워드 아이템 (실제 스키마)
interface RewardItem {
  sku: string; // 상품 고유 코드
  title: string; // 상품명
  cost_points: number; // 필요 포인트
  stock: number; // 재고 수량
  vendor: string; // 벤더명
  is_available: boolean; // 구매 가능 여부
  description?: string; // 상품 설명
  image_url?: string; // 상품 이미지 URL
}

// 카탈로그 응답 (직접 응답)
interface RewardCatalogResponse {
  rewards: RewardItem[];
  total_count: number;
}

// 교환 요청
interface RewardRedemptionRequest {
  sku: string; // SKU로 교환 요청
  delivery_info?: Record<string, any>; // 배송/발급 정보
}

// 교환 응답 (직접 응답)
interface RewardRedemptionResponse {
  success: boolean;
  redemption_id: string;
  status: string;
  message: string;
  cost_points: number;
  issued_at?: string; // ISO 8601
}

// 교환 내역
interface RewardRedemptionHistory {
  redemption_id: string;
  sku: string;
  title: string;
  cost_points: number;
  status: string;
  requested_at: string; // ISO 8601
  issued_at?: string; // ISO 8601
  vendor?: string;
}

// 교환 내역 응답 (직접 응답)
interface RewardRedemptionHistoryResponse {
  history: RewardRedemptionHistory[];
  total_count: number;
  has_next: boolean;
}
```

### 리워드 Service Layer

```typescript
// api/services/rewardService.ts
export class RewardService {
  // 리워드 카탈로그 조회 (직접 응답)
  static async getRewardCatalog(
    availableOnly: boolean = true
  ): Promise<RewardCatalogResponse> {
    const queryString = new URLSearchParams({
      available_only: availableOnly.toString(),
    });

    const response = await fetch(
      `${API_BASE_URL}/rewards/catalog?${queryString}`
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  // SKU로 특정 리워드 조회 (직접 응답)
  static async getRewardBySku(sku: string): Promise<RewardItem | null> {
    const response = await fetch(`${API_BASE_URL}/rewards/catalog/${sku}`);

    if (response.status === 404) {
      return null;
    }

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  // 리워드 교환 요청 (직접 응답)
  static async redeemReward(
    token: string,
    request: RewardRedemptionRequest
  ): Promise<RewardRedemptionResponse> {
    const response = await fetch(`${API_BASE_URL}/rewards/redeem`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }

  // 내 교환 내역 조회 (직접 응답)
  static async getMyRedemptions(
    token: string,
    pagination?: PaginationParams
  ): Promise<RewardRedemptionHistoryResponse> {
    const queryString = new URLSearchParams({
      ...(pagination?.limit && { limit: pagination.limit.toString() }),
      ...(pagination?.offset && { offset: pagination.offset.toString() }),
    });

    const response = await fetch(
      `${API_BASE_URL}/rewards/my-redemptions?${queryString}`,
      { headers: { Authorization: `Bearer ${token}` } }
    );

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }
}
```

### 리워드 Custom Hooks

```typescript
// hooks/rewards/useRewards.ts
export const useRewardCatalog = (availableOnly: boolean = true) => {
  return useQuery({
    queryKey: ["rewards", "catalog", availableOnly],
    queryFn: () => RewardService.getRewardCatalog(availableOnly),
    staleTime: 10 * 60 * 1000, // 10분
    cacheTime: 30 * 60 * 1000, // 30분
  });
};

export const useRewardBySku = (sku: string) => {
  return useQuery({
    queryKey: ["rewards", "item", sku],
    queryFn: () => RewardService.getRewardBySku(sku),
    enabled: !!sku,
    staleTime: 5 * 60 * 1000, // 5분
  });
};

export const useRedeemReward = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      token,
      request,
    }: {
      token: string;
      request: RewardRedemptionRequest;
    }) => RewardService.redeemReward(token, request),
    onSuccess: () => {
      // 관련 데이터 무효화
      queryClient.invalidateQueries(["rewards", "catalog"]);
      queryClient.invalidateQueries(["rewards", "my-redemptions"]);
      queryClient.invalidateQueries(["points", "balance"]);
    },
  });
};

export const useMyRedemptions = (pagination?: PaginationParams) => {
  const { token } = useAuth();

  return useQuery({
    queryKey: ["rewards", "my-redemptions", pagination],
    queryFn: () => RewardService.getMyRedemptions(token!, pagination),
    enabled: !!token,
    keepPreviousData: true,
    staleTime: 2 * 60 * 1000, // 2분
  });
};

// 리워드 교환 플로우 훅
export const useRewardExchange = () => {
  const redeemMutation = useRedeemReward();
  const { data: balance } = usePointsBalance();

  const canAfford = useCallback(
    (costPoints: number) => {
      return balance ? balance.balance >= costPoints : false;
    },
    [balance]
  );

  const exchangeReward = useCallback(
    async (token: string, sku: string, deliveryInfo?: Record<string, any>) => {
      return redeemMutation.mutateAsync({
        token,
        request: { sku, delivery_info: deliveryInfo },
      });
    },
    [redeemMutation]
  );

  return {
    exchangeReward,
    canAfford,
    isLoading: redeemMutation.isLoading,
    error: redeemMutation.error,
  };
};
```

## ⚡ React Query 통합

### Query Client 설정

```typescript
// utils/queryClient.ts
import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 3,
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex, 30000),
      staleTime: 5 * 60 * 1000, // 5분
      cacheTime: 10 * 60 * 1000, // 10분
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
});

// App.tsx
import { QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <Routes>{/* 라우트 정의 */}</Routes>
      </Router>
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

### 통합 API 클라이언트

```typescript
// api/client.ts
export class ApiClient {
  private baseURL: string;

  constructor(baseURL: string) {
    this.baseURL = baseURL;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = localStorage.getItem("token");
    const url = `${this.baseURL}${endpoint}`;

    const config: RequestInit = {
      headers: {
        "Content-Type": "application/json",
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
      ...options,
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        throw new Error("UNAUTHORIZED");
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result: BaseResponse<T> = await response.json();

    if (!result.success) {
      throw new Error(result.error?.message || "API Error");
    }

    return result.data!;
  }

  // BaseResponse를 사용하지 않는 엔드포인트용
  async requestDirect<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = localStorage.getItem("token");
    const url = `${this.baseURL}${endpoint}`;

    const config: RequestInit = {
      headers: {
        "Content-Type": "application/json",
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
      ...options,
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      if (response.status === 401) {
        localStorage.removeItem("token");
        window.location.href = "/login";
        throw new Error("UNAUTHORIZED");
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return await response.json();
  }
}

export const apiClient = new ApiClient(
  process.env.REACT_APP_API_URL || "https://api.example.com/api/v1"
);
```

### 통합 인증 Hook

```typescript
// hooks/auth/useAuth.ts
interface AuthState {
  token: string | null;
  isAuthenticated: boolean;
  user: User | null;
}

export const useAuth = () => {
  const [authState, setAuthState] = useState<AuthState>({
    token: localStorage.getItem("token"),
    isAuthenticated: !!localStorage.getItem("token"),
    user: null,
  });

  const login = useCallback((token: string) => {
    localStorage.setItem("token", token);
    setAuthState({
      token,
      isAuthenticated: true,
      user: null,
    });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("token");
    setAuthState({
      token: null,
      isAuthenticated: false,
      user: null,
    });
    queryClient.clear(); // 모든 캐시 클리어
  }, []);

  const { data: user } = useQuery({
    queryKey: ["user", "profile"],
    queryFn: () => UserService.getMyProfile(authState.token!),
    enabled: authState.isAuthenticated,
    onSuccess: (userData) => {
      setAuthState((prev) => ({ ...prev, user: userData }));
    },
  });

  return {
    ...authState,
    user: user || authState.user,
    login,
    logout,
  };
};
```

### 종합적인 대시보드 Hook 예시

```typescript
// hooks/dashboard/useDashboard.ts
export const useDashboard = () => {
  const { token, isAuthenticated } = useAuth();

  // 병렬 데이터 로딩
  const sessionQuery = useQuery({
    queryKey: ["session", "today"],
    queryFn: SessionService.getTodaySession,
    refetchInterval: 60 * 1000, // 1분마다 갱신
  });

  const universeQuery = useQuery({
    queryKey: ["universe", "today-with-prices"],
    queryFn: UniverseService.getTodayUniverseWithPrices,
    enabled: sessionQuery.data?.session?.status === "OPEN",
    refetchInterval: 30 * 1000, // 30초마다 가격 갱신
  });

  const balanceQuery = useQuery({
    queryKey: ["points", "balance"],
    queryFn: () => PointService.getMyPointsBalance(token!),
    enabled: isAuthenticated,
  });

  const slotsQuery = useQuery({
    queryKey: ["ads", "available-slots"],
    queryFn: () => AdService.getAvailableSlots(token!),
    enabled: isAuthenticated,
    refetchInterval: 60 * 1000,
  });

  const remainingQuery = useQuery({
    queryKey: [
      "predictions",
      "remaining",
      sessionQuery.data?.session?.trading_day,
    ],
    queryFn: () =>
      PredictionService.getRemainingPredictions(
        token!,
        sessionQuery.data?.session?.trading_day ||
          new Date().toISOString().split("T")[0]
      ),
    enabled: isAuthenticated && !!sessionQuery.data?.session?.trading_day,
    refetchInterval: 30 * 1000,
  });

  const isLoading =
    sessionQuery.isLoading ||
    universeQuery.isLoading ||
    balanceQuery.isLoading ||
    slotsQuery.isLoading;

  const canPredict =
    sessionQuery.data?.session?.status === "OPEN" &&
    (remainingQuery.data || 0) > 0;

  const needsMoreSlots =
    sessionQuery.data?.session?.status === "OPEN" &&
    (remainingQuery.data || 0) === 0 &&
    (slotsQuery.data?.can_unlock_by_ad ||
      slotsQuery.data?.can_unlock_by_cooldown);

  return {
    // 데이터
    session: sessionQuery.data,
    universe: universeQuery.data,
    balance: balanceQuery.data,
    slots: slotsQuery.data,
    remainingPredictions: remainingQuery.data,

    // 상태
    isLoading,
    canPredict,
    needsMoreSlots,

    // 에러
    error: sessionQuery.error || universeQuery.error || balanceQuery.error,

    // 리프레시
    refetch: () => {
      sessionQuery.refetch();
      universeQuery.refetch();
      balanceQuery.refetch();
      slotsQuery.refetch();
      remainingQuery.refetch();
    },
  };
};
```

## 🚨 에러 처리

### React Hook을 활용한 에러 처리

```typescript
import { useState, useCallback } from "react";

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useApi<T>() {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    loading: false,
    error: null,
  });

  const execute = useCallback(async (apiCall: () => Promise<T>) => {
    setState((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const result = await apiCall();
      setState({ data: result, loading: false, error: null });
      return result;
    } catch (error) {
      const errorMessage =
        error instanceof Error ? error.message : "Unknown error";
      setState((prev) => ({ ...prev, loading: false, error: errorMessage }));
      throw error;
    }
  }, []);

  return { ...state, execute };
}

// 사용 예시
const MyComponent = () => {
  const { data, loading, error, execute } =
    useApi<UniverseWithPricesResponse>();

  useEffect(() => {
    execute(() => getTodayUniverseWithPrices());
  }, [execute]);

  if (loading) return <div>로딩 중...</div>;
  if (error) return <div>에러: {error}</div>;
  if (!data) return <div>데이터가 없습니다.</div>;

  return (
    <div>
      {data.symbols.map((symbol) => (
        <div key={symbol.symbol}>
          {symbol.symbol}: {symbol.formatted_change}
        </div>
      ))}
    </div>
  );
};
```

### 전역 에러 처리

```typescript
// api/client.ts
class ApiClient {
  private baseURL: string;
  private getToken: () => string | null;

  constructor(baseURL: string, getToken: () => string | null) {
    this.baseURL = baseURL;
    this.getToken = getToken;
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const token = this.getToken();
    const url = `${this.baseURL}${endpoint}`;

    const config: RequestInit = {
      headers: {
        "Content-Type": "application/json",
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
      ...options,
    };

    const response = await fetch(url, config);

    if (!response.ok) {
      if (response.status === 401) {
        // 토큰 만료 처리
        throw new Error("UNAUTHORIZED");
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result: BaseResponse<T> = await response.json();

    if (!result.success) {
      throw new Error(result.error?.message || "API Error");
    }

    return result.data!;
  }
}

// 사용
const apiClient = new ApiClient(API_BASE_URL, () =>
  localStorage.getItem("token")
);
```

## 📝 사용 예시

### React Query + TypeScript 완전한 대시보드 예시

```typescript
// pages/Dashboard.tsx
import React from "react";
import { useDashboard } from "../hooks/dashboard/useDashboard";
import { useSubmitPrediction } from "../hooks/predictions/usePredictions";
import { useCompleteAdWatch, useUnlockSlot } from "../hooks/ads/useAds";
import { PredictionChoice } from "../api/types/prediction";
import { LoadingSpinner } from "../components/LoadingSpinner";
import { ErrorMessage } from "../components/ErrorMessage";

const Dashboard: React.FC = () => {
  const {
    session,
    universe,
    balance,
    slots,
    remainingPredictions,
    isLoading,
    canPredict,
    needsMoreSlots,
    error,
    refetch,
  } = useDashboard();

  // Mutations
  const submitPrediction = useSubmitPrediction();
  const completeAdWatch = useCompleteAdWatch();
  const unlockSlot = useUnlockSlot();

  const handlePrediction = async (symbol: string, choice: PredictionChoice) => {
    try {
      await submitPrediction.mutateAsync({ symbol, choice });
    } catch (error) {
      console.error("Prediction failed:", error);
    }
  };

  const handleWatchAd = async () => {
    try {
      await completeAdWatch.mutateAsync({
        token: localStorage.getItem("token")!,
      });
    } catch (error) {
      console.error("Ad watch failed:", error);
    }
  };

  const handleUnlockSlot = async () => {
    try {
      await unlockSlot.mutateAsync({
        token: localStorage.getItem("token")!,
        request: { method: "COOLDOWN" },
      });
    } catch (error) {
      console.error("Slot unlock failed:", error);
    }
  };

  if (isLoading) return <LoadingSpinner />;
  if (error) return <ErrorMessage error={error} onRetry={refetch} />;

  return (
    <div className="dashboard">
      {/* 헤더 */}
      <header className="dashboard-header">
        <h1>O/X 예측 대시보드</h1>
        <div className="user-info">
          <span className="points">포인트: {balance?.balance || 0}P</span>
          <span className="remaining-slots">
            남은 예측: {remainingPredictions || 0}개
          </span>
        </div>
      </header>

      {/* 세션 상태 */}
      <section className="session-status">
        <h2>오늘의 세션</h2>
        {session?.session ? (
          <div className="session-info">
            <span className={`status ${session.session.status.toLowerCase()}`}>
              {session.session.status === "OPEN"
                ? "예측 가능 🟢"
                : "예측 마감 🔴"}
            </span>
            <span>거래일: {session.session.trading_day}</span>
            {session.market_status && (
              <span className="market-status">
                {session.market_status.message}
              </span>
            )}
          </div>
        ) : (
          <div className="no-session">오늘은 휴장일입니다</div>
        )}
      </section>

      {/* 슬롯 관리 */}
      {needsMoreSlots && (
        <section className="slot-unlock">
          <h3>예측 슬롯 추가</h3>
          <div className="unlock-options">
            {slots?.can_unlock_by_ad && (
              <button
                onClick={handleWatchAd}
                disabled={completeAdWatch.isLoading}
                className="watch-ad-btn"
              >
                {completeAdWatch.isLoading
                  ? "처리 중..."
                  : "광고 보고 슬롯 획득 🎬"}
              </button>
            )}
            {slots?.can_unlock_by_cooldown && (
              <button
                onClick={handleUnlockSlot}
                disabled={unlockSlot.isLoading}
                className="cooldown-unlock-btn"
              >
                {unlockSlot.isLoading
                  ? "처리 중..."
                  : "쿨다운으로 슬롯 해제 ⏰"}
              </button>
            )}
          </div>
          <div className="slot-info">
            <small>
              오늘 광고: {slots?.today_ad_unlocks || 0}회 | 쿨다운:{" "}
              {slots?.today_cooldown_unlocks || 0}회
            </small>
          </div>
        </section>
      )}

      {/* 종목 리스트 */}
      <section className="universe">
        <h2>오늘의 종목 ({universe?.total_count || 0}개)</h2>
        {universe?.symbols.length ? (
          <div className="stock-grid">
            {universe.symbols.map((stock) => (
              <div key={stock.symbol} className="stock-card">
                <div className="stock-header">
                  <h3>{stock.symbol}</h3>
                  <span className="company-name">{stock.company_name}</span>
                </div>

                <div className="stock-price">
                  <span className="current-price">${stock.current_price}</span>
                  <span
                    className={`change ${stock.change_direction.toLowerCase()}`}
                  >
                    {stock.formatted_change}
                  </span>
                </div>

                <div className="prediction-actions">
                  <button
                    onClick={() =>
                      handlePrediction(stock.symbol, PredictionChoice.UP)
                    }
                    disabled={!canPredict || submitPrediction.isLoading}
                    className="predict-up"
                  >
                    상승 ⬆️
                  </button>
                  <button
                    onClick={() =>
                      handlePrediction(stock.symbol, PredictionChoice.DOWN)
                    }
                    disabled={!canPredict || submitPrediction.isLoading}
                    className="predict-down"
                  >
                    하락 ⬇️
                  </button>
                </div>

                {submitPrediction.isLoading && (
                  <div className="prediction-loading">
                    <small>예측 제출 중...</small>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="no-stocks">오늘 거래 가능한 종목이 없습니다</div>
        )}
      </section>

      {/* 최근 예측 결과 */}
      <section className="recent-predictions">
        <h2>최근 예측 현황</h2>
        <RecentPredictions />
      </section>
    </div>
  );
};

// 최근 예측 컴포넌트 예시
const RecentPredictions: React.FC = () => {
  const { data: predictions, isLoading } = useQuery({
    queryKey: ["predictions", "history"],
    queryFn: () =>
      PredictionService.getUserPredictionHistory(
        localStorage.getItem("token")!,
        { limit: 5, offset: 0 }
      ),
    staleTime: 2 * 60 * 1000,
  });

  if (isLoading) return <div>예측 내역 로딩 중...</div>;
  if (!predictions?.length) return <div>예측 내역이 없습니다</div>;

  return (
    <div className="predictions-list">
      {predictions.slice(0, 5).map((prediction) => (
        <div key={prediction.id} className="prediction-item">
          <span className="symbol">{prediction.symbol}</span>
          <span className={`choice ${prediction.choice.toLowerCase()}`}>
            {prediction.choice === "UP" ? "⬆️" : "⬇️"}
          </span>
          <span className={`status ${prediction.status.toLowerCase()}`}>
            {prediction.status}
          </span>
          <span className="points">
            {prediction.points_awarded ? `+${prediction.points_awarded}P` : "-"}
          </span>
        </div>
      ))}
    </div>
  );
};

export default Dashboard;
```

### 추가 실용 예시: 리워드 페이지

```typescript
// pages/Rewards.tsx
import React, { useState } from "react";
import {
  useRewardCatalog,
  useRewardExchange,
  useMyRedemptions,
} from "../hooks/rewards/useRewards";
import { usePointsBalance } from "../hooks/points/usePoints";

const Rewards: React.FC = () => {
  const [selectedSku, setSelectedSku] = useState<string>("");

  const { data: catalog, isLoading: catalogLoading } = useRewardCatalog();
  const { data: balance } = usePointsBalance();
  const { data: redemptions } = useMyRedemptions({ limit: 10, offset: 0 });
  const {
    exchangeReward,
    canAfford,
    isLoading: exchangeLoading,
  } = useRewardExchange();

  const handleExchange = async (sku: string) => {
    try {
      await exchangeReward(localStorage.getItem("token")!, sku);
      setSelectedSku("");
    } catch (error) {
      console.error("Exchange failed:", error);
    }
  };

  if (catalogLoading) return <div>카탈로그 로딩 중...</div>;

  return (
    <div className="rewards-page">
      <header>
        <h1>리워드 교환</h1>
        <div>보유 포인트: {balance?.balance || 0}P</div>
      </header>

      <section className="reward-catalog">
        <h2>상품 카탈로그</h2>
        <div className="rewards-grid">
          {catalog?.rewards.map((reward) => (
            <div key={reward.sku} className="reward-card">
              {reward.image_url && (
                <img src={reward.image_url} alt={reward.title} />
              )}
              <h3>{reward.title}</h3>
              <p className="cost">{reward.cost_points}P</p>
              <p className="stock">재고: {reward.stock}개</p>
              <button
                onClick={() => handleExchange(reward.sku)}
                disabled={
                  !canAfford(reward.cost_points) ||
                  !reward.is_available ||
                  exchangeLoading
                }
                className={
                  canAfford(reward.cost_points) ? "can-afford" : "cannot-afford"
                }
              >
                {exchangeLoading && selectedSku === reward.sku
                  ? "교환 중..."
                  : canAfford(reward.cost_points)
                  ? "교환하기"
                  : "포인트 부족"}
              </button>
            </div>
          ))}
        </div>
      </section>

      <section className="redemption-history">
        <h2>교환 내역</h2>
        <div className="history-list">
          {redemptions?.history.map((redemption) => (
            <div key={redemption.redemption_id} className="history-item">
              <span>{redemption.title}</span>
              <span>{redemption.cost_points}P</span>
              <span className={`status ${redemption.status.toLowerCase()}`}>
                {redemption.status}
              </span>
              <span>{redemption.requested_at}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default Rewards;
```

이 업데이트된 문서는 **실제 백엔드 스키마**를 기반으로 하고, **React Query + Service/Hook 패턴**을 완전히 적용한 현대적인 프론트엔드 개발 가이드입니다. 실제 개발 시 바로 사용할 수 있도록 구성되어 있어요!

## 📋 페이지네이션 완벽 가이드

### 페이지네이션이 필요한 실제 엔드포인트들:

1. **예측 이력**: GET /predictions/history (limit: 1-100, offset, 기본값: 50)
2. **포인트 원장**: GET /users/me/points/ledger (limit: 1-100, offset, 기본값: 50)
3. **포인트 원장 직접**: GET /points/ledger (limit: 1-100, offset, 기본값: 50)
4. **리워드 교환 내역**: GET /rewards/my-redemptions (limit: 1-100, offset, 기본값: 50)
5. **사용자 목록**: GET /users/ (limit: 1-100, offset, 기본값: 20)
6. **사용자 검색**: GET /users/search/nickname (limit: 1-50, offset 없음, 기본값: 20)

### 무한 스크롤 구현 예시

```typescript
// hooks/pagination/usePaginatedData.ts
import { useInfiniteQuery } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";

interface PaginatedData<T> {
  data: T[];
  hasNextPage: boolean;
  isLoading: boolean;
  isFetchingNextPage: boolean;
  fetchNextPage: () => void;
  error: Error | null;
  refetch: () => void;
}

// 1. 예측 이력 무한 스크롤
export const usePredictionHistoryInfinite = (): PaginatedData<Prediction> => {
  const { token } = useAuth();

  const query = useInfiniteQuery({
    queryKey: ["predictions", "history", "infinite"],
    queryFn: ({ pageParam = 0 }) =>
      PredictionService.getPredictionHistory(token!, {
        limit: PAGINATION_LIMITS.PREDICTIONS_HISTORY.default,
        offset: pageParam,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const limit = PAGINATION_LIMITS.PREDICTIONS_HISTORY.default;
      return lastPage.length === limit ? allPages.length * limit : undefined;
    },
    enabled: !!token,
    staleTime: 2 * 60 * 1000,
  });

  const flatData = useMemo(
    () => query.data?.pages.flatMap((page) => page) ?? [],
    [query.data]
  );

  return {
    data: flatData,
    hasNextPage: !!query.hasNextPage,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: query.fetchNextPage,
    error: query.error,
    refetch: query.refetch,
  };
};

// 2. 포인트 원장 무한 스크롤
export const usePointsLedgerInfinite = (): PaginatedData<PointsLedgerEntry> => {
  const { token } = useAuth();

  const query = useInfiniteQuery({
    queryKey: ["points", "ledger", "infinite"],
    queryFn: ({ pageParam = 0 }) =>
      PointService.getMyPointsLedger(token!, {
        limit: PAGINATION_LIMITS.POINTS_LEDGER.default,
        offset: pageParam,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const limit = PAGINATION_LIMITS.POINTS_LEDGER.default;
      return lastPage.has_next ? allPages.length * limit : undefined;
    },
    enabled: !!token,
    staleTime: 30 * 1000,
  });

  const flatData = useMemo(
    () => query.data?.pages.flatMap((page) => page.entries) ?? [],
    [query.data]
  );

  return {
    data: flatData,
    hasNextPage: !!query.hasNextPage,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: query.fetchNextPage,
    error: query.error,
    refetch: query.refetch,
  };
};

// 3. 리워드 교환 내역 무한 스크롤
export const useRedemptionsInfinite = (): PaginatedData<RewardRedemptionHistory> => {
  const { token } = useAuth();

  const query = useInfiniteQuery({
    queryKey: ["rewards", "my-redemptions", "infinite"],
    queryFn: ({ pageParam = 0 }) =>
      RewardService.getMyRedemptions(token!, {
        limit: PAGINATION_LIMITS.REWARDS_HISTORY.default,
        offset: pageParam,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const limit = PAGINATION_LIMITS.REWARDS_HISTORY.default;
      return lastPage.has_next ? allPages.length * limit : undefined;
    },
    enabled: !!token,
    staleTime: 2 * 60 * 1000,
  });

  const flatData = useMemo(
    () => query.data?.pages.flatMap((page) => page.history) ?? [],
    [query.data]
  );

  return {
    data: flatData,
    hasNextPage: !!query.hasNextPage,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: query.fetchNextPage,
    error: query.error,
    refetch: query.refetch,
  };
};

// 4. 사용자 목록 무한 스크롤
export const useUserListInfinite = (): PaginatedData<{
  id: number;
  nickname: string;
  auth_provider: AuthProvider;
  created_at: string;
}> => {
  const { token } = useAuth();

  const query = useInfiniteQuery({
    queryKey: ["users", "list", "infinite"],
    queryFn: ({ pageParam = 0 }) =>
      UserService.getUserList(token!, {
        limit: PAGINATION_LIMITS.USER_LIST.default,
        offset: pageParam,
      }),
    getNextPageParam: (lastPage, allPages) => {
      const limit = PAGINATION_LIMITS.USER_LIST.default;
      return lastPage.data?.users.length === limit
        ? allPages.length * limit
        : undefined;
    },
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
  });

  const flatData = useMemo(
    () => query.data?.pages.flatMap((page) => page.data?.users ?? []) ?? [],
    [query.data]
  );

  return {
    data: flatData,
    hasNextPage: !!query.hasNextPage,
    isLoading: query.isLoading,
    isFetchingNextPage: query.isFetchingNextPage,
    fetchNextPage: query.fetchNextPage,
    error: query.error,
    refetch: query.refetch,
  };
};
```

### 디바운스 검색 구현

```typescript
// hooks/search/useDebounceSearch.ts
import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDebounce } from "use-debounce";

// 5. 사용자 검색 (디바운스 적용)
export const useUserSearch = (initialQuery: string = "") => {
  const { token } = useAuth();
  const [searchQuery, setSearchQuery] = useState(initialQuery);
  const [debouncedQuery] = useDebounce(searchQuery, 300); // 300ms 디바운스

  const query = useQuery({
    queryKey: ["users", "search", debouncedQuery],
    queryFn: () =>
      UserService.searchUsers(token!, {
        q: debouncedQuery,
        limit: PAGINATION_LIMITS.USER_SEARCH.default,
      }),
    enabled: !!token && debouncedQuery.length >= 2,
    staleTime: 30 * 1000,
    keepPreviousData: true, // 검색 중 이전 결과 유지
  });

  return {
    searchQuery,
    setSearchQuery,
    debouncedQuery,
    isSearching: query.isLoading,
    users: query.data?.users ?? [],
    totalCount: query.data?.count ?? 0,
    error: query.error,
  };
};

// 더 고도화된 검색 훅 (히스토리 + 캐싱)
export const useAdvancedUserSearch = () => {
  const { token } = useAuth();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchHistory, setSearchHistory] = useState<string[]>([]);
  const [debouncedQuery] = useDebounce(searchQuery, 300);

  // 검색 히스토리 관리
  const addToHistory = useCallback((query: string) => {
    if (query.length >= 2 && !searchHistory.includes(query)) {
      setSearchHistory(prev => [query, ...prev.slice(0, 4)]); // 최근 5개 유지
    }
  }, [searchHistory]);

  const searchQuery_ = useQuery({
    queryKey: ["users", "search", debouncedQuery],
    queryFn: async () => {
      const result = await UserService.searchUsers(token!, {
        q: debouncedQuery,
        limit: PAGINATION_LIMITS.USER_SEARCH.default,
      });
      addToHistory(debouncedQuery);
      return result;
    },
    enabled: !!token && debouncedQuery.length >= 2,
    staleTime: 30 * 1000,
    keepPreviousData: true,
  });

  const clearHistory = useCallback(() => {
    setSearchHistory([]);
  }, []);

  return {
    searchQuery,
    setSearchQuery,
    debouncedQuery,
    searchHistory,
    clearHistory,
    isSearching: searchQuery_.isLoading,
    users: searchQuery_.data?.users ?? [],
    totalCount: searchQuery_.data?.count ?? 0,
    error: searchQuery_.error,
  };
};
```

### 실제 컴포넌트 구현 예시

```typescript
// components/PredictionHistory.tsx
import React, { useRef, useCallback } from "react";
import { usePredictionHistoryInfinite } from "../hooks/pagination/usePaginatedData";
import { PredictionChoice, PredictionStatus } from "../api/types/prediction";

const PredictionHistory: React.FC = () => {
  const {
    data: predictions,
    hasNextPage,
    isLoading,
    isFetchingNextPage,
    fetchNextPage,
    error,
  } = usePredictionHistoryInfinite();

  const observer = useRef<IntersectionObserver>();
  
  // 무한 스크롤 트리거
  const lastElementRef = useCallback(
    (node: HTMLDivElement) => {
      if (isLoading) return;
      if (observer.current) observer.current.disconnect();
      
      observer.current = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && hasNextPage) {
          fetchNextPage();
        }
      });
      
      if (node) observer.current.observe(node);
    },
    [isLoading, hasNextPage, fetchNextPage]
  );

  if (isLoading && !predictions.length) {
    return <div className="loading">예측 이력을 불러오는 중...</div>;
  }

  if (error) {
    return <div className="error">오류가 발생했습니다: {error.message}</div>;
  }

  if (!predictions.length) {
    return <div className="no-data">예측 이력이 없습니다.</div>;
  }

  return (
    <div className="prediction-history">
      <h2>예측 이력</h2>
      
      <div className="predictions-list">
        {predictions.map((prediction, index) => {
          const isLast = index === predictions.length - 1;
          
          return (
            <div
              key={prediction.id}
              ref={isLast ? lastElementRef : null}
              className="prediction-item"
            >
              <div className="prediction-header">
                <span className="symbol">{prediction.symbol}</span>
                <span className="trading-day">{prediction.trading_day}</span>
              </div>
              
              <div className="prediction-details">
                <span className={`choice ${prediction.choice.toLowerCase()}`}>
                  {prediction.choice === PredictionChoice.UP ? "⬆️ 상승" : "⬇️ 하락"}
                </span>
                <span className={`status ${prediction.status.toLowerCase()}`}>
                  {getStatusText(prediction.status)}
                </span>
                {prediction.points_awarded && (
                  <span className="points">+{prediction.points_awarded}P</span>
                )}
              </div>
              
              <div className="prediction-time">
                {new Date(prediction.created_at).toLocaleString()}
              </div>
            </div>
          );
        })}
      </div>

      {isFetchingNextPage && (
        <div className="loading-more">더 많은 데이터를 불러오는 중...</div>
      )}
      
      {!hasNextPage && predictions.length > 0 && (
        <div className="end-message">모든 예측 이력을 불러왔습니다.</div>
      )}
    </div>
  );
};

const getStatusText = (status: PredictionStatus): string => {
  switch (status) {
    case PredictionStatus.PENDING:
      return "대기 중";
    case PredictionStatus.LOCKED:
      return "정산 대기";
    case PredictionStatus.CORRECT:
      return "정답 ✅";
    case PredictionStatus.INCORRECT:
      return "오답 ❌";
    case PredictionStatus.VOID:
      return "무효 처리";
    default:
      return status;
  }
};

export default PredictionHistory;
```

```typescript
// components/UserSearchWithHistory.tsx
import React, { useState } from "react";
import { useAdvancedUserSearch } from "../hooks/search/useDebounceSearch";
import { AuthProvider } from "../api/types/user";

const UserSearchWithHistory: React.FC = () => {
  const {
    searchQuery,
    setSearchQuery,
    debouncedQuery,
    searchHistory,
    clearHistory,
    isSearching,
    users,
    totalCount,
    error,
  } = useAdvancedUserSearch();

  const [showHistory, setShowHistory] = useState(false);

  const handleHistoryClick = (historyQuery: string) => {
    setSearchQuery(historyQuery);
    setShowHistory(false);
  };

  return (
    <div className="user-search">
      <div className="search-container">
        <div className="search-input-wrapper">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => setShowHistory(true)}
            onBlur={() => setTimeout(() => setShowHistory(false), 200)}
            placeholder="사용자 닉네임 검색... (최소 2글자)"
            className="search-input"
          />
          
          {isSearching && <div className="search-loading">🔍</div>}
        </div>

        {/* 검색 히스토리 */}
        {showHistory && searchHistory.length > 0 && (
          <div className="search-history">
            <div className="history-header">
              <span>최근 검색</span>
              <button onClick={clearHistory} className="clear-history">
                전체 삭제
              </button>
            </div>
            <div className="history-list">
              {searchHistory.map((historyQuery, index) => (
                <button
                  key={index}
                  onClick={() => handleHistoryClick(historyQuery)}
                  className="history-item"
                >
                  {historyQuery}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 검색 결과 */}
      {error && (
        <div className="search-error">
          검색 중 오류가 발생했습니다: {error.message}
        </div>
      )}

      {debouncedQuery.length >= 2 && !isSearching && (
        <div className="search-results">
          <div className="results-header">
            <span>검색 결과: {totalCount}명</span>
            {totalCount >= PAGINATION_LIMITS.USER_SEARCH.default && (
              <small>최대 {PAGINATION_LIMITS.USER_SEARCH.default}명까지 표시</small>
            )}
          </div>

          {users.length > 0 ? (
            <div className="users-list">
              {users.map((user) => (
                <div key={user.id} className="user-item">
                  <div className="user-info">
                    <span className="nickname">{user.nickname}</span>
                    <span className="provider">
                      {getProviderText(user.auth_provider)}
                    </span>
                  </div>
                  <div className="user-actions">
                    <button className="follow-btn">팔로우</button>
                    <button className="profile-btn">프로필 보기</button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="no-results">
              '{debouncedQuery}'에 대한 검색 결과가 없습니다.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const getProviderText = (provider: AuthProvider): string => {
  switch (provider) {
    case AuthProvider.GOOGLE:
      return "Google";
    case AuthProvider.KAKAO:
      return "Kakao";
    case AuthProvider.LOCAL:
      return "일반";
    default:
      return provider;
  }
};

export default UserSearchWithHistory;
```

```typescript
// components/PointsLedger.tsx
import React from "react";
import { usePointsLedgerInfinite } from "../hooks/pagination/usePaginatedData";
import { PointsLedgerEntry } from "../api/types/points";

const PointsLedger: React.FC = () => {
  const {
    data: entries,
    hasNextPage,
    isLoading,
    isFetchingNextPage,
    fetchNextPage,
  } = usePointsLedgerInfinite();

  const handleLoadMore = () => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  };

  if (isLoading && !entries.length) {
    return <div className="loading">포인트 내역을 불러오는 중...</div>;
  }

  if (!entries.length) {
    return <div className="no-data">포인트 거래 내역이 없습니다.</div>;
  }

  return (
    <div className="points-ledger">
      <h2>포인트 거래 내역</h2>
      
      <div className="ledger-table">
        <div className="table-header">
          <span>날짜</span>
          <span>유형</span>
          <span>변경량</span>
          <span>잔액</span>
          <span>사유</span>
        </div>
        
        <div className="table-body">
          {entries.map((entry) => (
            <div key={entry.id} className="ledger-row">
              <span className="date">
                {new Date(entry.created_at).toLocaleDateString()}
              </span>
              <span className="transaction-type">
                {getTransactionTypeText(entry.transaction_type)}
              </span>
              <span className={`delta ${entry.delta_points > 0 ? 'positive' : 'negative'}`}>
                {entry.delta_points > 0 ? '+' : ''}{entry.delta_points}P
              </span>
              <span className="balance">{entry.balance_after}P</span>
              <span className="reason">{entry.reason}</span>
            </div>
          ))}
        </div>
      </div>

      {hasNextPage && (
        <div className="load-more-section">
          <button
            onClick={handleLoadMore}
            disabled={isFetchingNextPage}
            className="load-more-btn"
          >
            {isFetchingNextPage ? "로딩 중..." : "더 보기"}
          </button>
        </div>
      )}
      
      {!hasNextPage && entries.length > 0 && (
        <div className="end-message">모든 거래 내역을 확인했습니다.</div>
      )}
    </div>
  );
};

const getTransactionTypeText = (type: string): string => {
  const types: Record<string, string> = {
    'PREDICTION_CORRECT': '예측 성공',
    'PREDICTION_VOID': '예측 환불',
    'REWARD_REDEMPTION': '리워드 교환',
    'ADMIN_ADJUSTMENT': '관리자 조정',
    'SIGNUP_BONUS': '가입 보너스',
  };
  
  return types[type] || type;
};

export default PointsLedger;
```

### 통합 페이지네이션 유틸리티

```typescript
// utils/pagination.ts
export interface PaginationConfig {
  initialPageSize?: number;
  maxPageSize?: number;
  enableInfiniteScroll?: boolean;
  debounceMs?: number;
}

export class PaginationManager<T> {
  private config: Required<PaginationConfig>;

  constructor(config: PaginationConfig = {}) {
    this.config = {
      initialPageSize: config.initialPageSize || 20,
      maxPageSize: config.maxPageSize || 100,
      enableInfiniteScroll: config.enableInfiniteScroll ?? true,
      debounceMs: config.debounceMs || 300,
    };
  }

  // 페이지네이션 파라미터 검증
  validateParams(params: PaginationParams): PaginationParams {
    return {
      limit: Math.min(
        Math.max(params.limit || this.config.initialPageSize, 1),
        this.config.maxPageSize
      ),
      offset: Math.max(params.offset || 0, 0),
    };
  }

  // 다음 페이지 계산
  getNextPageParam<U>(
    lastPage: U[],
    allPages: U[][],
    pageSize: number = this.config.initialPageSize
  ): number | undefined {
    return lastPage.length === pageSize ? allPages.length * pageSize : undefined;
  }

  // 무한 스크롤 옵션 생성
  createInfiniteOptions<U>(
    queryFn: (params: { pageParam?: number }) => Promise<U[]>,
    queryKey: (string | number | boolean)[],
    enabled: boolean = true
  ) {
    return {
      queryKey,
      queryFn,
      getNextPageParam: (lastPage: U[], allPages: U[][]) =>
        this.getNextPageParam(lastPage, allPages),
      enabled,
      staleTime: 2 * 60 * 1000,
    };
  }
}

// 전역 인스턴스
export const paginationManager = new PaginationManager({
  initialPageSize: 20,
  maxPageSize: 100,
  enableInfiniteScroll: true,
  debounceMs: 300,
});
```

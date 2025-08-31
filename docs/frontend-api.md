# Frontend API Reference

React TypeScript 프론트엔드 개발을 위한 O/X 예측 서비스 API 문서입니다.

## 📋 목차

- [기본 설정](#기본-설정)
- [공통 타입 정의](#공통-타입-정의)
- [인증 시스템](#인증-시스템)
- [사용자 관리](#사용자-관리)
- [예측 시스템](#예측-시스템)
- [세션 관리](#세션-관리)
- [종목 유니버스](#종목-유니버스)
- [포인트 시스템](#포인트-시스템)
- [광고 및 슬롯](#광고-및-슬롯)
- [리워드 시스템](#리워드-시스템)
- [에러 처리](#에러-처리)

## 🔧 기본 설정

### Base URL
```typescript
const API_BASE_URL = 'https://your-domain.com/api/v1'
```

### 인증 헤더
```typescript
const headers = {
  'Authorization': `Bearer ${token}`,
  'Content-Type': 'application/json'
}
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
  USER_NOT_FOUND = "USER_002"
}
```

### 페이지네이션
```typescript
interface PaginationParams {
  limit?: number; // 1-100, 기본값: 20-50
  offset?: number; // 0 이상, 기본값: 0
}

interface PaginatedResponse<T> extends BaseResponse<T> {
  meta: {
    limit: number;
    offset: number;
    total_count: number;
    has_next: boolean;
  };
}
```

## 🔐 인증 시스템

### OAuth 로그인 시작
```typescript
// GET /auth/oauth/{provider}/authorize?client_redirect={url}
interface OAuthAuthorizeParams {
  provider: 'google' | 'kakao';
  client_redirect: string; // 로그인 후 리다이렉트될 URL
}

// 브라우저가 자동으로 OAuth 제공자 페이지로 리다이렉트됨
```

### OAuth 콜백 응답 (URL 파라미터)
```typescript
// 로그인 성공 후 client_redirect URL에 쿼리 파라미터로 전달
interface OAuthCallbackParams {
  token: string;        // JWT 토큰
  user_id: string;      // 사용자 ID
  nickname: string;     // 사용자 닉네임
  provider: string;     // OAuth 제공자
  is_new_user: string;  // 'true' | 'false' 신규 사용자 여부
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
  token_type: 'bearer';
}

const refreshToken = async (currentToken: string): Promise<TokenRefreshResponse> => {
  const response = await fetch(`${API_BASE_URL}/auth/token/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(currentToken)
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
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(token)
  });
};
```

## 👤 사용자 관리

### 사용자 타입 정의
```typescript
enum AuthProvider {
  LOCAL = 'local',
  GOOGLE = 'google', 
  KAKAO = 'kakao'
}

enum UserRole {
  USER = 'user',
  PREMIUM = 'premium',
  ADMIN = 'admin'
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
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<User> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 프로필 업데이트
```typescript
// PUT /users/me
const updateMyProfile = async (token: string, updates: UserUpdate): Promise<User> => {
  const response = await fetch(`${API_BASE_URL}/users/me`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(updates)
  });
  
  const result: BaseResponse<User> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 사용자 검색
```typescript
// GET /users/search/nickname?q={nickname}&limit={limit}
interface UserSearchParams {
  q: string; // 2-50자
  limit?: number; // 1-50, 기본값: 20
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
    ...(params.limit && { limit: params.limit.toString() })
  });
  
  const response = await fetch(
    `${API_BASE_URL}/users/search/nickname?${queryString}`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  
  const result: BaseResponse<UserSearchResult> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

## 🎯 예측 시스템

### 예측 타입 정의
```typescript
enum PredictionChoice {
  UP = 'UP',     // 상승 예측
  DOWN = 'DOWN'  // 하락 예측
}

enum PredictionStatus {
  PENDING = 'PENDING',     // 대기 중
  LOCKED = 'LOCKED',       // 정산용 잠금
  CORRECT = 'CORRECT',     // 정답
  INCORRECT = 'INCORRECT', // 오답
  VOID = 'VOID'           // 무효 (환불)
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
  const response = await fetch(`${API_BASE_URL}/predictions/${symbol.toUpperCase()}`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ choice })
  });
  
  const result: BaseResponse<{ prediction: Prediction }> = await response.json();
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
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ choice })
  });
  
  const result: BaseResponse<{ prediction: Prediction }> = await response.json();
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
    method: 'DELETE',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<{ prediction: Prediction }> = await response.json();
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
    { headers: { 'Authorization': `Bearer ${token}` } }
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
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  
  const result: BaseResponse<{ remaining_predictions: number }> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!.remaining_predictions;
};
```

## 📅 세션 관리

### 세션 타입 정의
```typescript
enum SessionStatus {
  OPEN = 'OPEN',     // 예측 가능
  CLOSED = 'CLOSED'  // 예측 마감
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

const canPredictNow = async (tradingDay?: string): Promise<PredictionAvailability> => {
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
  change_direction: 'UP' | 'DOWN' | 'FLAT';
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
  
  const result: BaseResponse<{ universe: UniverseResponse | null }> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  if (!result.data?.universe) throw new Error('No universe available today');
  return result.data.universe;
};
```

### 가격 정보 포함 종목 조회
```typescript
// GET /universe/today/with-prices
const getTodayUniverseWithPrices = async (): Promise<UniverseWithPricesResponse> => {
  const response = await fetch(`${API_BASE_URL}/universe/today/with-prices`);
  
  const result: BaseResponse<{ universe: UniverseWithPricesResponse | null }> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  if (!result.data?.universe) throw new Error('No universe available today');
  return result.data.universe;
};
```

## 💰 포인트 시스템

### 포인트 타입 정의
```typescript
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

### 내 포인트 잔액 조회
```typescript
// GET /users/me/points/balance
const getMyPointsBalance = async (token: string): Promise<PointsBalance> => {
  const response = await fetch(`${API_BASE_URL}/users/me/points/balance`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<PointsBalance> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 포인트 거래 내역 조회
```typescript
// GET /users/me/points/ledger?limit={limit}&offset={offset}
const getMyPointsLedger = async (
  token: string,
  pagination?: PaginationParams
): Promise<PointsLedger> => {
  const queryString = new URLSearchParams({
    ...(pagination?.limit && { limit: pagination.limit.toString() }),
    ...(pagination?.offset && { offset: pagination.offset.toString() })
  });
  
  const response = await fetch(
    `${API_BASE_URL}/users/me/points/ledger?${queryString}`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  
  const result: BaseResponse<PointsLedger> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 포인트 정보 포함 프로필 조회
```typescript
// GET /users/me/profile-with-points
const getMyProfileWithPoints = async (token: string): Promise<UserProfileWithPoints> => {
  const response = await fetch(`${API_BASE_URL}/users/me/profile-with-points`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<UserProfileWithPoints> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 재정 요약 정보 조회
```typescript
// GET /users/me/financial-summary
const getMyFinancialSummary = async (token: string): Promise<UserFinancialSummary> => {
  const response = await fetch(`${API_BASE_URL}/users/me/financial-summary`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<UserFinancialSummary> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 지불 가능 여부 확인
```typescript
// GET /users/me/can-afford/{amount}
const checkAffordability = async (
  token: string, 
  amount: number
): Promise<AffordabilityCheck> => {
  const response = await fetch(`${API_BASE_URL}/users/me/can-afford/${amount}`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<AffordabilityCheck> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

## 🎬 광고 및 슬롯 시스템

### 광고 타입 정의
```typescript
interface AdSlotInfo {
  available_slots: number;
  max_daily_slots: number;
  slots_from_ads: number;
  next_cooldown_unlock?: string; // ISO 8601, 쿨다운 해제 시간
  can_watch_ad: boolean;
  can_unlock_cooldown: boolean;
}

interface AdWatchResult {
  success: boolean;
  slots_added: number;
  total_available_slots: number;
  message: string;
}

interface AdUnlockHistory {
  unlock_date: string; // YYYY-MM-DD
  ads_watched: number;
  cooldowns_used: number;
  total_unlocks: number;
}
```

### 사용 가능한 슬롯 정보 조회
```typescript
// GET /ads/available-slots
const getAvailableSlots = async (token: string): Promise<AdSlotInfo> => {
  const response = await fetch(`${API_BASE_URL}/ads/available-slots`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<AdSlotInfo> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 광고 시청 완료 처리
```typescript
// POST /ads/watch-complete
const completeAdWatch = async (token: string): Promise<AdWatchResult> => {
  const response = await fetch(`${API_BASE_URL}/ads/watch-complete`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<AdWatchResult> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 쿨다운 슬롯 해제
```typescript
// POST /ads/unlock-slot
const unlockCooldownSlot = async (token: string): Promise<AdWatchResult> => {
  const response = await fetch(`${API_BASE_URL}/ads/unlock-slot`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  
  const result: BaseResponse<AdWatchResult> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

## 🎁 리워드 시스템

### 리워드 타입 정의
```typescript
interface RewardItem {
  id: number;
  name: string;
  description: string;
  points_required: number;
  category: string;
  image_url?: string;
  is_available: boolean;
  stock_count?: number;
}

interface RewardCatalog {
  rewards: RewardItem[];
  categories: string[];
  total_count: number;
}

interface RewardRedemption {
  id: number;
  user_id: number;
  reward_id: number;
  reward_name: string;
  points_spent: number;
  status: 'PENDING' | 'COMPLETED' | 'FAILED';
  created_at: string; // ISO 8601
  completed_at?: string; // ISO 8601
}

interface RedemptionRequest {
  reward_id: number;
  quantity?: number; // 기본값: 1
}
```

### 리워드 카탈로그 조회
```typescript
// GET /rewards/catalog
const getRewardCatalog = async (): Promise<RewardCatalog> => {
  const response = await fetch(`${API_BASE_URL}/rewards/catalog`);
  
  const result: BaseResponse<RewardCatalog> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 리워드 교환 요청
```typescript
// POST /rewards/redeem
const redeemReward = async (
  token: string,
  redemption: RedemptionRequest
): Promise<RewardRedemption> => {
  const response = await fetch(`${API_BASE_URL}/rewards/redeem`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(redemption)
  });
  
  const result: BaseResponse<RewardRedemption> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result.data!;
};
```

### 내 교환 내역 조회
```typescript
// GET /rewards/my-redemptions?limit={limit}&offset={offset}
const getMyRedemptions = async (
  token: string,
  pagination?: PaginationParams
): Promise<PaginatedResponse<RewardRedemption[]>> => {
  const queryString = new URLSearchParams({
    ...(pagination?.limit && { limit: pagination.limit.toString() }),
    ...(pagination?.offset && { offset: pagination.offset.toString() })
  });
  
  const response = await fetch(
    `${API_BASE_URL}/rewards/my-redemptions?${queryString}`,
    { headers: { 'Authorization': `Bearer ${token}` } }
  );
  
  const result: PaginatedResponse<RewardRedemption[]> = await response.json();
  if (!result.success) throw new Error(result.error?.message);
  return result;
};
```

## 🚨 에러 처리

### React Hook을 활용한 에러 처리
```typescript
import { useState, useCallback } from 'react';

interface ApiState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

function useApi<T>() {
  const [state, setState] = useState<ApiState<T>>({
    data: null,
    loading: false,
    error: null
  });

  const execute = useCallback(async (apiCall: () => Promise<T>) => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    
    try {
      const result = await apiCall();
      setState({ data: result, loading: false, error: null });
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      setState(prev => ({ ...prev, loading: false, error: errorMessage }));
      throw error;
    }
  }, []);

  return { ...state, execute };
}

// 사용 예시
const MyComponent = () => {
  const { data, loading, error, execute } = useApi<UniverseWithPricesResponse>();
  
  useEffect(() => {
    execute(() => getTodayUniverseWithPrices());
  }, [execute]);

  if (loading) return <div>로딩 중...</div>;
  if (error) return <div>에러: {error}</div>;
  if (!data) return <div>데이터가 없습니다.</div>;

  return (
    <div>
      {data.symbols.map(symbol => (
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

  async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();
    const url = `${this.baseURL}${endpoint}`;
    
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        ...(token && { 'Authorization': `Bearer ${token}` }),
        ...options.headers
      },
      ...options
    };

    const response = await fetch(url, config);
    
    if (!response.ok) {
      if (response.status === 401) {
        // 토큰 만료 처리
        throw new Error('UNAUTHORIZED');
      }
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const result: BaseResponse<T> = await response.json();
    
    if (!result.success) {
      throw new Error(result.error?.message || 'API Error');
    }

    return result.data!;
  }
}

// 사용
const apiClient = new ApiClient(API_BASE_URL, () => localStorage.getItem('token'));
```

## 📝 사용 예시

### React Router와 함께 사용하는 완전한 예시
```typescript
// pages/Dashboard.tsx
import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';

const Dashboard: React.FC = () => {
  const [session, setSession] = useState<SessionTodayResponse | null>(null);
  const [universe, setUniverse] = useState<UniverseWithPricesResponse | null>(null);
  const [balance, setBalance] = useState<PointsBalance | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const loadDashboardData = async () => {
      try {
        const token = localStorage.getItem('token');
        if (!token) {
          navigate('/login');
          return;
        }

        // 병렬로 데이터 로드
        const [sessionData, universeData, balanceData] = await Promise.all([
          getTodaySession(),
          getTodayUniverseWithPrices(),
          getMyPointsBalance(token)
        ]);

        setSession(sessionData);
        setUniverse(universeData);
        setBalance(balanceData);
      } catch (error) {
        console.error('Dashboard load error:', error);
        if (error.message === 'UNAUTHORIZED') {
          localStorage.removeItem('token');
          navigate('/login');
        }
      } finally {
        setLoading(false);
      }
    };

    loadDashboardData();
  }, [navigate]);

  const handlePrediction = async (symbol: string, choice: PredictionChoice) => {
    try {
      const token = localStorage.getItem('token')!;
      await submitPrediction(token, symbol, choice);
      
      // 성공 후 데이터 재로드
      const updatedBalance = await getMyPointsBalance(token);
      setBalance(updatedBalance);
      
      alert('예측이 성공적으로 제출되었습니다!');
    } catch (error) {
      alert(`예측 제출 실패: ${error.message}`);
    }
  };

  if (loading) return <div>로딩 중...</div>;

  return (
    <div className="dashboard">
      <header>
        <h1>O/X 예측 대시보드</h1>
        <div>포인트: {balance?.balance || 0}P</div>
      </header>

      <section className="session-status">
        <h2>오늘의 세션</h2>
        {session?.session ? (
          <div>
            상태: {session.session.status === 'OPEN' ? '예측 가능 🟢' : '예측 마감 🔴'}
            <br />
            거래일: {session.session.trading_day}
          </div>
        ) : (
          <div>오늘은 휴장일입니다</div>
        )}
      </section>

      <section className="universe">
        <h2>오늘의 종목 ({universe?.total_count || 0}개)</h2>
        <div className="stock-list">
          {universe?.symbols.map(stock => (
            <div key={stock.symbol} className="stock-item">
              <div className="stock-info">
                <strong>{stock.symbol}</strong>
                <span>{stock.company_name}</span>
                <span className={`change ${stock.change_direction.toLowerCase()}`}>
                  {stock.formatted_change}
                </span>
              </div>
              <div className="prediction-buttons">
                <button 
                  onClick={() => handlePrediction(stock.symbol, PredictionChoice.UP)}
                  disabled={session?.session?.status !== 'OPEN'}
                >
                  상승 ⬆️
                </button>
                <button 
                  onClick={() => handlePrediction(stock.symbol, PredictionChoice.DOWN)}
                  disabled={session?.session?.status !== 'OPEN'}
                >
                  하락 ⬇️
                </button>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
};

export default Dashboard;
```

이 문서는 React TypeScript 프론트엔드 개발에 필요한 모든 API 정보를 포함하고 있습니다. 실제 구현 시 프로젝트의 상황에 맞게 조정해서 사용하시면 됩니다!
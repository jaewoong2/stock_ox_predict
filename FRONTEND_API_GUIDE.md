# 프론트엔드 개발자를 위한 API 변경사항 가이드

## 📋 목차
1. [변경 사항 요약](#변경-사항-요약)
2. [즉시 사용 가능한 신규 기능](#즉시-사용-가능한-신규-기능)
3. [기존 API 동작 (변경 없음)](#기존-api-동작-변경-없음)
4. [권장 마이그레이션](#권장-마이그레이션)
5. [API 엔드포인트 상세](#api-엔드포인트-상세)

---

## 변경 사항 요약

### 🎉 신규 기능
- ✨ **RANGE 예측 수정 기능 추가** - 이제 가격 범위를 수정할 수 있습니다!
- 🔄 새로운 엔드포인트: `/api/v1/range-predictions`
- 🆕 RANGE 예측 업데이트 API 추가

### ✅ 하위 호환성
- ✅ **기존 API 100% 호환** - 모든 기존 코드가 그대로 작동합니다
- ✅ `/crypto-predictions` 엔드포인트 유지
- ✅ 스키마 변경 없음 (aliases 제공)

### 📝 권장 사항
- 💡 신규 개발 시 `/range-predictions` 사용 권장
- 💡 기존 코드는 변경 불필요 (optional migration)

---

## 즉시 사용 가능한 신규 기능

### 1️⃣ RANGE 예측 수정 기능 (NEW! 🆕)

이제 사용자가 PENDING 상태의 RANGE 예측 범위를 수정할 수 있습니다!

#### API 엔드포인트
```http
PATCH /api/v1/range-predictions/{prediction_id}
Content-Type: application/json
Authorization: Bearer {token}

{
  "price_low": 95500.0,
  "price_high": 96500.0
}
```

#### 응답 예시
```json
{
  "success": true,
  "data": {
    "prediction": {
      "id": 123,
      "user_id": 456,
      "trading_day": "2025-01-08",
      "symbol": "BTCUSDT",
      "prediction_type": "RANGE",
      "price_low": 95500.0,
      "price_high": 96500.0,
      "target_open_time_ms": 1704672000000,
      "target_close_time_ms": 1704675600000,
      "status": "PENDING",
      "points_earned": 0,
      "submitted_at": "2025-01-08T10:00:00Z",
      "updated_at": "2025-01-08T10:15:00Z"
    }
  }
}
```

#### 수정 가능 조건
- ✅ `status`가 `PENDING`인 경우만
- ✅ `locked_at`이 `null`인 경우만 (정산 잠금 전)
- ✅ 본인이 생성한 예측만
- ✅ `price_low` < `price_high` 조건 만족

#### 에러 응답
```json
// 본인 소유가 아닌 경우
{
  "success": false,
  "error": {
    "code": "FORBIDDEN_PREDICTION",
    "message": "Cannot modify another user's prediction"
  }
}

// PENDING 상태가 아닌 경우
{
  "success": false,
  "error": {
    "code": "PREDICTION_LOCKED",
    "message": "Only pending predictions can be updated"
  }
}
```

---

## 기존 API 동작 (변경 없음)

### ✅ 기존 엔드포인트 모두 정상 작동

#### 크립토 예측 생성 (변경 없음)
```http
POST /api/v1/crypto-predictions
Content-Type: application/json
Authorization: Bearer {token}

{
  "symbol": "BTCUSDT",
  "price_low": 95000.0,
  "price_high": 97000.0
}
```

#### 크립토 예측 목록 조회 (변경 없음)
```http
GET /api/v1/crypto-predictions?symbol=BTCUSDT&limit=50&offset=0
Authorization: Bearer {token}
```

#### 크립토 예측 히스토리 (변경 없음)
```http
GET /api/v1/crypto-predictions/history?limit=50&offset=0
Authorization: Bearer {token}
```

#### 방향 예측 (UP/DOWN) - 변경 없음
```http
POST /api/v1/predictions
PATCH /api/v1/predictions/{id}
GET /api/v1/predictions
```

**모든 기존 코드가 그대로 작동합니다!** 🎉

---

## 권장 마이그레이션

### 신규 개발 시 권장사항

기존 `/crypto-predictions`를 사용 중이라면, 신규 개발 시 `/range-predictions`로 마이그레이션을 권장합니다.

#### Before (기존 코드 - 여전히 작동함)
```typescript
// 예측 생성
const response = await fetch('/api/v1/crypto-predictions', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    symbol: 'BTCUSDT',
    price_low: 95000,
    price_high: 97000
  })
});

// ❌ 수정 기능 없음
```

#### After (권장 - 신규 기능 포함)
```typescript
// 예측 생성
const response = await fetch('/api/v1/range-predictions', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    symbol: 'BTCUSDT',
    price_low: 95000,
    price_high: 97000
  })
});

// ✅ 수정 기능 사용 가능!
const updateResponse = await fetch(`/api/v1/range-predictions/${predictionId}`, {
  method: 'PATCH',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    price_low: 95500,
    price_high: 96500
  })
});
```

### 마이그레이션 타임라인

- **즉시 사용 가능**: 신규 `/range-predictions` API
- **기존 코드**: 변경 불필요, 그대로 사용 가능
- **권장 시기**: 다음 기능 개발 시점부터 새 API 사용

---

## API 엔드포인트 상세

### RANGE 예측 API (신규 & 권장)

#### 1. 예측 생성
```http
POST /api/v1/range-predictions
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
  "symbol": "BTCUSDT",
  "price_low": 95000.0,
  "price_high": 97000.0
}

Response (200):
{
  "success": true,
  "data": {
    "prediction": {
      "id": 123,
      "user_id": 456,
      "trading_day": "2025-01-08",
      "symbol": "BTCUSDT",
      "prediction_type": "RANGE",
      "price_low": 95000.0,
      "price_high": 97000.0,
      "target_open_time_ms": 1704672000000,
      "target_close_time_ms": 1704675600000,
      "status": "PENDING",
      "settlement_price": null,
      "points_earned": 0,
      "submitted_at": "2025-01-08T10:00:00Z",
      "updated_at": null
    }
  }
}
```

#### 2. 예측 수정 (NEW! 🆕)
```http
PATCH /api/v1/range-predictions/{prediction_id}
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
  "price_low": 95500.0,    // Optional
  "price_high": 96500.0    // Optional
}

Response (200):
{
  "success": true,
  "data": {
    "prediction": {
      "id": 123,
      "price_low": 95500.0,
      "price_high": 96500.0,
      "updated_at": "2025-01-08T10:15:00Z",
      // ... other fields
    }
  }
}

Error (403):
{
  "success": false,
  "error": {
    "code": "PREDICTION_LOCKED",
    "message": "Only pending predictions can be updated"
  }
}
```

#### 3. 예측 목록 조회
```http
GET /api/v1/range-predictions?symbol=BTCUSDT&limit=50&offset=0
Authorization: Bearer {token}

Response:
{
  "success": true,
  "data": {
    "predictions": [...]
  },
  "meta": {
    "total_count": 100,
    "limit": 50,
    "offset": 0,
    "has_next": true
  }
}
```

#### 4. 예측 히스토리
```http
GET /api/v1/range-predictions/history?limit=50&offset=0
Authorization: Bearer {token}

Response:
{
  "success": true,
  "data": {
    "history": [...]
  },
  "meta": {
    "total_count": 100,
    "limit": 50,
    "offset": 0,
    "has_next": true
  }
}
```

### DIRECTION 예측 API (기존, 변경 없음)

#### 1. 예측 생성
```http
POST /api/v1/predictions
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
  "symbol": "AAPL",
  "choice": "UP"  // "UP" or "DOWN"
}
```

#### 2. 예측 수정
```http
PATCH /api/v1/predictions/{prediction_id}
Authorization: Bearer {token}
Content-Type: application/json

Request Body:
{
  "choice": "DOWN"  // "UP" or "DOWN"
}
```

---

## TypeScript 타입 정의

### RANGE 예측 타입
```typescript
// Request Types
interface RangePredictionCreate {
  symbol: string;
  price_low: number;
  price_high: number;
}

interface RangePredictionUpdate {  // NEW!
  price_low?: number;
  price_high?: number;
}

// Response Type
interface RangePrediction {
  id: number;
  user_id: number;
  trading_day: string;  // ISO date
  symbol: string;
  prediction_type: 'RANGE';
  price_low: number;
  price_high: number;
  target_open_time_ms: number;
  target_close_time_ms: number;
  status: 'PENDING' | 'CORRECT' | 'INCORRECT' | 'CANCELLED' | 'VOID';
  settlement_price: number | null;
  points_earned: number;
  submitted_at: string;  // ISO datetime
  updated_at: string | null;  // ISO datetime
}

// List Response
interface RangePredictionListResponse {
  predictions: RangePrediction[];
  total_count: number;
  limit: number;
  offset: number;
  has_next: boolean;
}
```

### DIRECTION 예측 타입 (변경 없음)
```typescript
interface DirectionPredictionCreate {
  symbol: string;
  choice: 'UP' | 'DOWN';
}

interface DirectionPredictionUpdate {
  choice: 'UP' | 'DOWN';
}

interface DirectionPrediction {
  id: number;
  user_id: number;
  trading_day: string;
  symbol: string;
  prediction_type: 'DIRECTION';
  choice: 'UP' | 'DOWN';
  status: 'PENDING' | 'CORRECT' | 'INCORRECT' | 'CANCELLED' | 'VOID';
  submitted_at: string;
  updated_at: string | null;
  points_earned: number | null;
  settlement_price: number | null;
  // Price snapshot
  prediction_price: number | null;
  prediction_price_at: string | null;
  prediction_price_source: string | null;
  // Ticker info
  ticker_name: string | null;
  ticker_market_category: string | null;
  ticker_is_etf: boolean | null;
  ticker_exchange: string | null;
}
```

---

## React 컴포넌트 예시

### RANGE 예측 수정 기능 구현 예시

```typescript
import React, { useState } from 'react';

interface EditRangePredictionProps {
  prediction: RangePrediction;
  onUpdate: (updated: RangePrediction) => void;
}

export const EditRangePrediction: React.FC<EditRangePredictionProps> = ({ 
  prediction, 
  onUpdate 
}) => {
  const [priceLow, setPriceLow] = useState(prediction.price_low);
  const [priceHigh, setPriceHigh] = useState(prediction.price_high);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 수정 가능 여부 체크
  const canEdit = prediction.status === 'PENDING' && !prediction.updated_at;

  const handleUpdate = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `/api/v1/range-predictions/${prediction.id}`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${getAuthToken()}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            price_low: priceLow,
            price_high: priceHigh
          })
        }
      );

      const data = await response.json();

      if (data.success) {
        onUpdate(data.data.prediction);
        alert('예측이 수정되었습니다!');
      } else {
        setError(data.error.message);
      }
    } catch (err) {
      setError('수정 중 오류가 발생했습니다.');
    } finally {
      setLoading(false);
    }
  };

  if (!canEdit) {
    return <div>이 예측은 수정할 수 없습니다.</div>;
  }

  return (
    <div className="edit-range-prediction">
      <h3>예측 범위 수정</h3>
      
      <div className="form-group">
        <label>최저가</label>
        <input
          type="number"
          value={priceLow}
          onChange={(e) => setPriceLow(parseFloat(e.target.value))}
          disabled={loading}
        />
      </div>

      <div className="form-group">
        <label>최고가</label>
        <input
          type="number"
          value={priceHigh}
          onChange={(e) => setPriceHigh(parseFloat(e.target.value))}
          disabled={loading}
        />
      </div>

      {error && <div className="error">{error}</div>}

      <button 
        onClick={handleUpdate} 
        disabled={loading || priceLow >= priceHigh}
      >
        {loading ? '수정 중...' : '수정하기'}
      </button>
    </div>
  );
};
```

---

## 에러 코드 참조

### 새로운 에러 코드
```typescript
enum ErrorCode {
  // 기존 에러 코드들...
  
  // RANGE 예측 관련
  FORBIDDEN_PREDICTION = 'FORBIDDEN_PREDICTION',     // 타인의 예측 수정 시도
  PREDICTION_LOCKED = 'PREDICTION_LOCKED',           // 잠긴 예측 수정 시도
  INVALID_RANGE = 'INVALID_RANGE',                   // price_low >= price_high
  DUPLICATE_PREDICTION = 'DUPLICATE_PREDICTION',     // 중복 예측
  SYMBOL_NOT_ALLOWED = 'SYMBOL_NOT_ALLOWED',         // 허용되지 않은 심볼
  NO_SLOTS = 'NO_SLOTS',                             // 슬롯 부족
  COOLDOWN_ACTIVE = 'COOLDOWN_ACTIVE',               // 쿨다운 진행 중
}
```

---

## FAQ

### Q1: 기존 코드를 수정해야 하나요?
**A:** 아니요! 기존 코드는 그대로 작동합니다. 신규 기능이 필요한 경우에만 새 API를 사용하세요.

### Q2: `/crypto-predictions`와 `/range-predictions`의 차이는?
**A:** 기능은 동일하지만, `/range-predictions`는 수정 기능(PATCH)을 추가로 제공합니다.

### Q3: 언제 마이그레이션해야 하나요?
**A:** 다음 기능 개발 시점부터 권장합니다. 급하지 않습니다!

### Q4: 수정 기능의 제한사항은?
**A:** 
- PENDING 상태만 수정 가능
- 정산 전(locked_at = null)만 가능
- 본인이 생성한 예측만 가능
- price_low < price_high 조건 필수

### Q5: 에러 처리는 어떻게 하나요?
**A:** 기존과 동일합니다. `success: false`일 때 `error.code`와 `error.message`를 확인하세요.

---

## 요청사항 체크리스트

### 즉시 개발 가능 ✅
- [x] 신규 RANGE 예측 수정 UI 개발
- [x] 수정 가능 여부 표시 (PENDING 상태 체크)
- [x] 수정 폼 (price_low, price_high)
- [x] 에러 처리 (403, 404, 400)

### 선택적 마이그레이션 (권장) 💡
- [ ] 기존 `/crypto-predictions` → `/range-predictions` 경로 변경
- [ ] TypeScript 타입 정의 업데이트
- [ ] API 호출 코드 리팩토링

### 변경 불필요 ✅
- [x] 기존 DIRECTION 예측 (UP/DOWN) 코드
- [x] 기존 크립토 예측 목록/히스토리 조회
- [x] 기존 인증/권한 처리

---

## 지원 및 문의

- 📚 **상세 문서**: `REFACTORING_SUMMARY.md`, `QUICK_REFERENCE.md`
- 🐛 **버그 리포트**: Backend team에 문의
- 💬 **질문**: Slack #backend-support 채널

---

**Last Updated**: 2025-01-08
**API Version**: v1
**Backward Compatible**: ✅ Yes (100%)


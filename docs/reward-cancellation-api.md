# 리워드 취소 API 명세서

## 개요
사용자가 구매한 리워드를 취소하고 포인트를 환불받을 수 있는 기능입니다.

## API 엔드포인트

### POST `/rewards/cancel/{redemption_id}`

사용자가 구매한 리워드를 취소하고 사용한 포인트를 환불받습니다.

---

## 요청 (Request)

### HTTP Method
```
POST
```

### URL
```
/rewards/cancel/{redemption_id}
```

### Path Parameters

| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `redemption_id` | integer | ✅ | 취소할 교환 ID |

### Headers

| 헤더 | 값 | 필수 | 설명 |
|------|-----|------|------|
| `Authorization` | `Bearer {access_token}` | ✅ | 사용자 인증 토큰 |

### Request Body
없음 (Body 불필요)

---

## 응답 (Response)

### 성공 응답 (200 OK)

```json
{
  "success": true,
  "message": "리워드가 취소되었습니다",
  "redemption_id": 123
}
```

#### Response Fields

| 필드 | 타입 | 설명 |
|------|------|------|
| `success` | boolean | 취소 성공 여부 (항상 true) |
| `message` | string | 응답 메시지 |
| `redemption_id` | integer | 취소된 교환 ID |

---

## 에러 응답 (Error Responses)

### 1. 리워드를 찾을 수 없음 (404 Not Found)
사용자가 소유하지 않은 리워드이거나 존재하지 않는 교환 ID인 경우

```json
{
  "detail": "리워드를 찾을 수 없습니다"
}
```

### 2. 취소 불가능한 상태 (400 Bad Request)
이미 사용되었거나 취소할 수 없는 상태의 리워드인 경우

```json
{
  "detail": "사용할 수 없는 상태입니다: USED"
}
```

**가능한 상태값:**
- `AVAILABLE`: 사용 가능 (✅ 취소 가능)
- `USED`: 사용 완료 (❌ 취소 불가)
- `CANCELLED`: 이미 취소됨 (❌ 취소 불가)
- `PENDING`: 처리 대기 중 (❌ 취소 불가)
- `FAILED`: 발급 실패 (❌ 취소 불가)

### 3. 인증 오류 (401 Unauthorized)
유효하지 않거나 만료된 토큰인 경우

```json
{
  "detail": "Could not validate credentials"
}
```

### 4. 서버 오류 (500 Internal Server Error)
서버에서 처리 중 오류가 발생한 경우

```json
{
  "detail": "Failed to cancel reward"
}
```

---

## 비즈니스 로직

### 취소 가능 조건
1. ✅ 사용자가 해당 리워드를 소유해야 함
2. ✅ 리워드 상태가 `AVAILABLE`이어야 함
3. ✅ 유효한 인증 토큰이 필요함

### 취소 시 처리 내용
1. 리워드 상태를 `CANCELLED`로 변경
2. 사용했던 포인트를 사용자에게 환불
3. 환불 내역이 포인트 거래 이력에 기록됨
4. **재고 예약 해제** (구매 시 예약된 재고를 다시 사용 가능하도록 반환)

### 환불 포인트
- 리워드 구매 시 사용한 포인트 전액이 환불됩니다.
- 환불 이유(reason): `"Refund for canceled redemption: {redemption_id}"`
- 참조 ID(ref_id): `"cancel_refund_{redemption_id}"`

---

## 사용 예시

### JavaScript (Fetch API)

```javascript
async function cancelReward(redemptionId, accessToken) {
  try {
    const response = await fetch(
      `https://api.example.com/rewards/cancel/${redemptionId}`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json'
        }
      }
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail);
    }

    const data = await response.json();
    console.log('취소 성공:', data);
    return data;
  } catch (error) {
    console.error('취소 실패:', error.message);
    throw error;
  }
}

// 사용
cancelReward(123, 'your-access-token-here')
  .then(result => {
    alert(result.message); // "리워드가 취소되었습니다"
  })
  .catch(error => {
    alert(`오류: ${error.message}`);
  });
```

### TypeScript (with Axios)

```typescript
import axios, { AxiosError } from 'axios';

interface RewardCancellationResponse {
  success: boolean;
  message: string;
  redemption_id: number;
}

interface ErrorResponse {
  detail: string;
}

async function cancelReward(
  redemptionId: number, 
  accessToken: string
): Promise<RewardCancellationResponse> {
  try {
    const response = await axios.post<RewardCancellationResponse>(
      `/rewards/cancel/${redemptionId}`,
      {},
      {
        headers: {
          'Authorization': `Bearer ${accessToken}`
        }
      }
    );

    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const axiosError = error as AxiosError<ErrorResponse>;
      const errorMessage = axiosError.response?.data?.detail || '알 수 없는 오류가 발생했습니다';
      throw new Error(errorMessage);
    }
    throw error;
  }
}

// 사용 예시
(async () => {
  try {
    const result = await cancelReward(123, 'your-access-token');
    console.log(result.message); // "리워드가 취소되었습니다"
  } catch (error) {
    if (error instanceof Error) {
      console.error('취소 실패:', error.message);
    }
  }
})();
```

### React 컴포넌트 예시

```tsx
import React, { useState } from 'react';
import axios from 'axios';

interface RewardCancellationResponse {
  success: boolean;
  message: string;
  redemption_id: number;
}

interface RewardItemProps {
  redemptionId: number;
  title: string;
  costPoints: number;
  status: string;
  accessToken: string;
  onCancelSuccess: () => void;
}

const RewardItem: React.FC<RewardItemProps> = ({
  redemptionId,
  title,
  costPoints,
  status,
  accessToken,
  onCancelSuccess
}) => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCancel = async () => {
    // 확인 다이얼로그
    const confirmed = window.confirm(
      `"${title}"을(를) 취소하시겠습니까?\n${costPoints} 포인트가 환불됩니다.`
    );
    
    if (!confirmed) return;

    setLoading(true);
    setError(null);

    try {
      const response = await axios.post<RewardCancellationResponse>(
        `/rewards/cancel/${redemptionId}`,
        {},
        {
          headers: {
            'Authorization': `Bearer ${accessToken}`
          }
        }
      );

      alert(response.data.message);
      onCancelSuccess(); // 상위 컴포넌트에 성공 알림 (목록 새로고침 등)
    } catch (err) {
      if (axios.isAxiosError(err)) {
        const errorMsg = err.response?.data?.detail || '취소 중 오류가 발생했습니다';
        setError(errorMsg);
        alert(errorMsg);
      }
    } finally {
      setLoading(false);
    }
  };

  // AVAILABLE 상태일 때만 취소 버튼 표시
  const canCancel = status === 'AVAILABLE';

  return (
    <div className="reward-item">
      <h3>{title}</h3>
      <p>포인트: {costPoints}</p>
      <p>상태: {status}</p>
      
      {canCancel && (
        <button 
          onClick={handleCancel} 
          disabled={loading}
          className="btn-cancel"
        >
          {loading ? '처리 중...' : '취소하기'}
        </button>
      )}
      
      {error && <p className="error">{error}</p>}
    </div>
  );
};

export default RewardItem;
```

---

## UI/UX 가이드라인

### 취소 버튼 표시 조건
- 리워드 상태가 `AVAILABLE`일 때만 "취소하기" 버튼을 표시
- 다른 상태(`USED`, `CANCELLED`, `PENDING`, `FAILED`)에서는 버튼을 숨기거나 비활성화

### 확인 다이얼로그
취소 버튼 클릭 시 사용자에게 확인 메시지 표시 권장:
```
"{리워드명}"을(를) 취소하시겠습니까?
{cost_points} 포인트가 환불됩니다.
```

### 성공 시 처리
1. 성공 메시지 표시: "리워드가 취소되었습니다"
2. 리워드 목록 새로고침
3. 사용자 포인트 잔액 업데이트

### 에러 처리
- 404: "리워드를 찾을 수 없습니다"
- 400: "이미 사용되었거나 취소할 수 없는 리워드입니다"
- 401: "로그인이 필요합니다"
- 500: "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요"

### 로딩 상태
- 취소 요청 중 버튼 비활성화
- 로딩 인디케이터 표시 ("처리 중..." 또는 스피너)
- 중복 클릭 방지

---

## 테스트 시나리오

### 정상 케이스
1. ✅ AVAILABLE 상태의 리워드 취소
   - 기대 결과: 성공 응답, 포인트 환불

### 에러 케이스
1. ❌ 다른 사용자의 리워드 취소 시도
   - 기대 결과: 404 Not Found
2. ❌ 이미 사용된 리워드 취소 시도
   - 기대 결과: 400 Bad Request, "사용할 수 없는 상태입니다: USED"
3. ❌ 존재하지 않는 redemption_id
   - 기대 결과: 404 Not Found
4. ❌ 만료된 토큰으로 요청
   - 기대 결과: 401 Unauthorized

---

## 관련 API

### 리워드 목록 조회
- **GET** `/rewards/my-summary` - 사용자의 전체 리워드 요약 (사용 가능, 사용 완료, 대기 중)
- **GET** `/rewards/my-redemptions` - 교환 내역 조회

### 리워드 사용
- **POST** `/rewards/activate/{redemption_id}` - 리워드 사용하기

### 리워드 구매
- **POST** `/rewards/redeem` - 포인트로 리워드 구매

---

## 데이터베이스 변경사항

### rewards_redemptions 테이블
```sql
-- 상태가 CANCELLED로 업데이트됨
UPDATE rewards_redemptions 
SET status = 'CANCELLED', 
    updated_at = NOW()
WHERE id = {redemption_id};
```

### rewards_inventory 테이블
```sql
-- 예약된 재고가 해제됨 (다시 사용 가능한 재고로 복원)
UPDATE rewards_inventory
SET reserved = reserved - 1
WHERE sku = {sku};
```

### points_transactions 테이블
```sql
-- 포인트 환불 트랜잭션 생성
INSERT INTO points_transactions (
  user_id, 
  points, 
  reason, 
  ref_id
) VALUES (
  {user_id}, 
  {cost_points}, 
  'Refund for canceled redemption: {redemption_id}',
  'cancel_refund_{redemption_id}'
);
```

---

## 주의사항

1. **중복 취소 방지**: 이미 `CANCELLED` 상태인 리워드는 다시 취소할 수 없습니다.
2. **권한 확인**: 본인이 구매한 리워드만 취소할 수 있습니다.
3. **포인트 환불**: 취소 시 사용한 포인트는 자동으로 환불되며, 별도의 승인 과정은 없습니다.
4. **상태 전환**: AVAILABLE → CANCELLED 전환만 가능합니다.
5. **재고 복원**: 취소 시 구매 시 예약했던 재고(`reserved`)가 자동으로 해제되어 다른 사용자가 구매할 수 있게 됩니다.

---

## 변경 이력

| 날짜 | 버전 | 변경 내용 |
|------|------|-----------|
| 2025-12-19 | 1.0.0 | 초기 문서 작성 |

---

## 문의

API 관련 문의사항이 있으시면 백엔드 개발팀에 문의해주세요.


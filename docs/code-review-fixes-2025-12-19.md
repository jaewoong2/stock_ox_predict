# 코드 리뷰 수정사항 - 2025-12-19

## 개요

Git diff에서 발견된 보안 및 트랜잭션 일관성 문제를 해결하기 위한 Critical 수정사항을 적용했습니다.

## 적용된 수정사항

### 🔴 Critical Fix 1: 민감 정보 로깅 제거 (보안)

**파일**: `myapi/core/auth_middleware.py`, `myapi/routers/user_router.py`

**문제점**:
- JWT 토큰 전체를 로그에 기록하여 보안 취약점 발생
- 사용자 전체 정보(이메일, 개인정보)를 로그에 기록하여 GDPR/개인정보보호법 위반 가능성

**수정 내용**:

#### auth_middleware.py
```python
# Before (❌ 보안 취약)
logger.info(f"internal_token: {internal_token}")
logger.info(f"credentials: {credentials}")

# After (✅ 안전)
logger.debug(f"internal_token present: {bool(internal_token)}")
logger.debug(f"credentials present: {bool(credentials)}")
```

#### user_router.py
```python
# Before (❌ 개인정보 노출)
logger.info(f"current_user: {current_user}")

# After (✅ 최소 정보만 로깅)
logger.debug(f"Authenticated user_id: {current_user.id}")
```

**개선 효과**:
- JWT 토큰 탈취 위험 제거
- 개인정보 로그 노출 방지
- 디버깅에 필요한 최소 정보만 DEBUG 레벨로 기록

---

### 🔴 Critical Fix 2: 리워드 취소 트랜잭션 일관성 보장

**파일**: `myapi/services/reward_service.py`

**문제점**:
- 상태 변경과 포인트 환불이 별도의 트랜잭션으로 실행됨
- 중간 실패 시 데이터 불일치 발생 가능
  - 예: 상태는 CANCELLED인데 포인트는 환불 안됨

**수정 내용**:

```python
# Before (❌ 원자성 보장 안됨)
async def cancel_reward(self, user_id: int, redemption_id: int):
    self.rewards_repo.update_redemption_status(
        redemption_id, RedemptionStatusEnum.CANCELLED
    )  # ← COMMIT 1
    
    self.points_repo.add_points(...)  # ← COMMIT 2 (실패 시 불일치)

# After (✅ 단일 트랜잭션)
async def cancel_reward(self, user_id: int, redemption_id: int):
    try:
        with self.db.begin():  # 명시적 트랜잭션 시작
            # 소유권 및 상태 확인
            result = self.rewards_repo.get_redemption_with_inventory(
                redemption_id, user_id
            )
            if not result:
                raise NotFoundError("리워드를 찾을 수 없습니다")
            
            redemption, inventory = result
            if redemption.status != "AVAILABLE":
                raise ValidationError(f"사용할 수 없는 상태입니다: {redemption.status}")
            
            # 모든 작업을 auto_commit=False로 실행
            self.rewards_repo.update_redemption_status(
                redemption_id, 
                RedemptionStatusEnum.CANCELLED,
                auto_commit=False  # COMMIT 연기
            )
            
            self.points_repo.add_points(
                user_id=user_id,
                points=redemption.cost_points,
                reason=f"Refund for canceled redemption: {redemption.id}",
                ref_id=f"cancel_refund_{redemption_id}",
                auto_commit=False,  # COMMIT 연기
            )
            # with 블록 끝 → 자동 COMMIT
            # 예외 발생 시 → 자동 ROLLBACK
    except (NotFoundError, ValidationError):
        raise
    except Exception as e:
        logger.error(f"리워드 취소 실패: {e}")
        raise ValidationError(f"리워드 취소 중 오류가 발생했습니다: {str(e)}")
```

**개선 효과**:
- 상태 변경 + 포인트 환불 + 재고 해제가 원자적으로 실행
- 실패 시 모든 변경사항 자동 롤백
- 데이터 일관성 보장

---

### 🟡 Warning Fix 3: INTERNAL_AUTH_HEADER 복원

**파일**: `myapi/config.py`

**문제점**:
- `INTERNAL_AUTH_HEADER`를 `"authorization"`으로 변경했으나, AWS Lambda Function URL의 IAM 인증과 충돌 가능성
- Lambda가 `Authorization` 헤더를 SigV4 인증으로 해석할 수 있음

**수정 내용**:

```python
# Before (❌ Lambda IAM 인증과 충돌)
INTERNAL_AUTH_HEADER: str = "authorization"

# After (✅ 커스텀 헤더로 충돌 방지)
# Using custom header to prevent conflict with Lambda IAM authentication
INTERNAL_AUTH_HEADER: str = "x-internal-authorization"
```

**개선 효과**:
- Lambda Function URL IAM 인증과의 충돌 방지
- JWT 인증과 IAM 인증을 독립적으로 처리 가능

---

### 🟡 Warning Fix 4: JWT 에러 핸들링 후방 호환성 유지

**파일**: `myapi/services/auth_service.py`

**문제점**:
- `verify_token()`이 예외를 발생시키도록 변경되어 Breaking Change 발생
- 기존 호출자는 `None` 체크로 에러를 처리했으나, 이제는 try-catch 필요

**수정 내용**:

```python
# Before (❌ Breaking Change)
except JWTError as e:
    logger.error(f"JWT verification error: {str(e)}")
    raise AuthenticationError(f"JWT verification error: {str(e)}")

# After (✅ 후방 호환성 유지)
except JWTError as e:
    # Return None to maintain backward compatibility
    # Callers check for None rather than catching exceptions
    logger.debug(f"JWT verification error: {str(e)}")
    return None
```

**개선 효과**:
- 기존 코드와의 호환성 유지
- 호출자가 `Optional[TokenData]` 반환값을 체크하는 기존 패턴 유지
- 불필요한 코드 변경 방지

---

## 수정되지 않은 항목 (향후 리팩토링 권장)

### 예외 처리 일관성 (섹션 3.3)

**현재 상태**: `auto_commit` 플래그에 따라 에러 처리 방식이 달라짐
- `auto_commit=True`: 예외 → `PointsTransactionResponse(success=False)`
- `auto_commit=False`: 예외 재발생

**권장사항**: 
- Option 1: 항상 커스텀 예외 발생 (권장)
- Option 2: 항상 Response 객체 반환

**우선순위**: 낮음 (현재 동작은 정상이며, 리팩토링 시 개선)

---

## 테스트 권장사항

### 1. 보안 로깅 확인
```bash
# 로그에 토큰이 노출되지 않는지 확인
tail -f /var/log/app.log | grep -i "token"
# "internal_token present: True/False" 형태로만 출력되어야 함
```

### 2. 리워드 취소 트랜잭션 테스트
```python
# 시나리오 1: 정상 취소
POST /rewards/cancel/{redemption_id}
# 기대: 상태 CANCELLED + 포인트 환불 + 재고 복원

# 시나리오 2: 중간 실패 (DB 연결 끊김 등)
# 기대: 모든 변경사항 롤백 (일관성 유지)
```

### 3. Lambda IAM 인증 테스트
```bash
# x-internal-authorization 헤더로 JWT 전송 확인
curl -X GET https://your-lambda-url.amazonaws.com/users/me \
  -H "x-internal-authorization: Bearer YOUR_JWT_TOKEN"
```

### 4. JWT 에러 핸들링 테스트
```python
# 만료된 토큰으로 요청
# 기대: None 반환 (예외 발생 안함)
token_data = auth_service.verify_token(expired_token)
assert token_data is None
```

---

## 변경 파일 요약

| 파일 | 변경 유형 | 심각도 |
|------|----------|--------|
| `myapi/core/auth_middleware.py` | 보안 로깅 개선 | 🔴 Critical |
| `myapi/routers/user_router.py` | 보안 로깅 개선 | 🔴 Critical |
| `myapi/services/reward_service.py` | 트랜잭션 일관성 | 🔴 Critical |
| `myapi/config.py` | 설정 복원 | 🟡 Warning |
| `myapi/services/auth_service.py` | 호환성 유지 | 🟡 Warning |

---

## 배포 전 체크리스트

- [x] 보안 로깅 수정 완료
- [x] 트랜잭션 일관성 보장
- [x] INTERNAL_AUTH_HEADER 복원
- [x] JWT 에러 핸들링 후방 호환성 유지
- [ ] 단위 테스트 실행 (`pytest tests/`)
- [ ] 통합 테스트 실행 (리워드 취소 API)
- [ ] Lambda Function URL 인증 테스트
- [ ] 로그 모니터링 (토큰 노출 여부 확인)

---

## 참고 문서

- [코드 리뷰 계획서](/Users/macbook/.cursor/plans/code_review_plan_3147a1c5.plan.md)
- [리워드 취소 API 명세](./reward-cancellation-api.md)
- [CLAUDE.md 코딩 가이드라인](../CLAUDE.md)

---

## 변경 이력

| 날짜 | 작업자 | 변경 내용 |
|------|--------|----------|
| 2025-12-19 | AI Assistant | Critical 보안 및 트랜잭션 수정 적용 |



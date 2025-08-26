# OX Universe 코드 리뷰: Routers / Services / Repositories 점검 보고서

- 기준일: 2025-08-26
- 범위: `myapi/routers/`, `myapi/services/`, `myapi/repositories/` 전수 점검 후 `docs/todo.md`와의 불일치 및 논리 이슈 식별

## 개요
- 전반적으로 문서의 아키텍처와 구현이 잘 맞춰져 있으며, 예측/정산/포인트/리워드/배치의 핵심 흐름이 동작 가능 상태로 보입니다.
- 다만, 관리자 권한 검사, 일부 트랜잭션 처리 순서, 수동 정산 시 포인트 지급 누락, 타입/응답 일관성 등 운영 시 장애로 이어질 수 있는 이슈가 있어 선제적 보완을 권장합니다.

## 핵심 결론
- Admin 권한 검증이 사실상 미구현 상태이거나 잘못 사용됨 → 관리자 API가 일반 사용자에게 노출될 위험.
- 수동 정산 경로에서 포인트 지급이 누락 → 자동 정산과 결과 불일치(원장 불일치).
- 일부 리포지토리에서 `flush()`/`commit()` 순서가 뒤바뀜 → 일관성/가독성 저하.
- 예측 응답 변환에서 `points_earned` 처리 비안전 → `None` 케이스 오류 가능.
- 일부 라우터에서 인증 객체 타입을 dict로 가정 → 런타임 오류 가능.

---

## 상세 진단

### 1) Routers

- 관리자 권한 체크 누락/오용
  - 파일: `myapi/routers/price_router.py`
    - 경로: `/prices/admin/*` (validate-settlement, compare-prediction)
    - 현재: `get_current_active_user`만 검사 → 관리자 전용 보장이 안 됨
  - 파일: `myapi/routers/settlement_router.py`
    - 경로: `/admin/settlement/*`
    - 현재: 동일하게 활성 사용자만 검사 → 관리자 전용 보장 안 됨
  - 파일: `myapi/routers/point_router.py`, `myapi/routers/reward_router.py`
    - 관리자 엔드포인트에서 `current_user.get("is_admin")`으로 검사 시도
    - 문제 1: `verify_bearer_token`은 Pydantic `User` 모델을 반환하므로 `.get()` 사용 시 런타임 오류
    - 문제 2: 현 모델/스키마에 `is_admin` 필드가 없음 → 권한 판단 불가

- 인증 객체 타입/접근 방식 불일치
  - 파일: `myapi/routers/point_router.py`, `myapi/routers/reward_router.py`
  - 현상: `current_user`를 dict로 가정(`.get(...)`) → 실제는 `User` 모델 → 속성 접근 필요(`current_user.id`, `current_user.is_admin`)

- 응답 모델 일관성
  - 대부분 `BaseResponse` 사용. 다만 포인트 라우터는 도메인 응답 스키마를 직접 반환하는 엔드포인트가 일부 존재(정책에 따라 통일 검토)

- 사소한 사항
  - 티커 정규식: `^[A-Z]{1,5}$`로 고정. 현재 유니버스 목록 내에서는 문제 없음. 확장 정책(BRK.B 등) 필요 시 가이드 필요.

### 2) Services

- 수동 정산 시 포인트 지급 누락
  - 파일: `myapi/services/settlement_service.py`
  - 메서드: `manual_settle_symbol()`
  - 현상: 내부에서 `PredictionRepository.bulk_update_predictions_status(...)`만 호출하여 상태/points_earned만 일괄 갱신. 자동 정산 경로처럼 `PointService.award_prediction_points(...)` 호출이 없어 원장에 보상이 기록되지 않음.
  - 영향: 자동/수동 정산 결과 불일치(특히 포인트 원장 기준), 운영 중 관리자 수동 처리 시 회계적 불일치 위험.

- 예측 수수료 차감 흐름의 비자연스러움(개선 제안)
  - 파일: `myapi/services/prediction_service.py`
  - 메서드: `submit_prediction()`
  - 현상: 예측 생성 전 `prediction_id=0`으로 선차감 후, 생성 성공 시 `fee=0` 거래로 “기록 업데이트” 시도. 0 delta 거래가 생길 수 있고 최초 차감 건과 생성된 예측 간 연동이 약함.
  - 제안: (1) 사전 잔액검사 후 생성 성공 시에만 실제 차감, (2) 혹은 DB 트랜잭션으로 묶어 생성 실패 시 롤백, (3) 선차감이 필수면 첫 거래 ref_id를 임시 키로 두고 생성 후 연결/갱신 가능하도록 설계(현 구조엔 미존재)로 개선.

- PriceService 캐시 전략(제안 사항)
  - 파일: `myapi/services/price_service.py`
  - 현상: `cache_ttl = 60초` 고정 TTL.
  - 문서: 장 상태별 차등 TTL 제안. 불일치는 아니지만 향후 적용 가치 있음(OPEN 30초, PRE/AFTER 5분, CLOSED 30분 등).

### 3) Repositories

- 트랜잭션 순서 일관성
  - 파일: `myapi/repositories/active_universe_repository.py`
    - 메서드: `set_universe_for_date()`에서 `commit()` → `flush()` 순서 사용
    - 보통 `flush()` → `commit()`이 자연스러움. 동일 파일 내 타 메서드들과도 일관성 유지 필요.
  - 파일: `myapi/repositories/session_repository.py`
    - `create_session()` 등에서도 `commit()` → `flush()` 순서. 동작엔 큰 문제 없으나 일관성/관례 측면에서 정리 권장.

- 예측 응답 변환 안전성
  - 파일: `myapi/repositories/prediction_repository.py`
  - 메서드: `_to_prediction_response()`에서 `points_earned` 변환이 `model_instance.points_earned.__str__()` 전제. `None`일 경우 예외 가능. `points = model_instance.points_earned or 0` 형태로 안전화 권장.

- 불필요 import
  - 파일: `myapi/repositories/session_repository.py`
  - `from pyexpat import model` 사용되지 않음 → 제거 권장.

---

## 문서(todo) 대비 일치/불일치 요약

- 일치
  - 예측 CRUD/조회/슬롯/통계, 가격 API, 자동 정산(검증/포인트 지급/VOID 처리), 유니버스/세션/배치 라우터 및 서비스, 포인트/리워드(멱등성/잔액/인벤토리/예약/교환/환불) 등 핵심 플로우는 문서와 부합.

- 불일치/이상
  - Admin 전용 엔드포인트 실제 권한 체크 부재 또는 오용
  - 수동 정산 시 포인트 지급 누락(자동 정산과 불일치)
  - 일부 `flush()/commit()` 순서 역전
  - 예측 응답 변환의 `points_earned` 처리 안전성 부족
  - 인증 객체 타입/필드 접근 불일치(런타임 오류 가능)

---

## 권장 수정 사항(우선순위 순)

1) 관리자 권한 모델/체크 도입
- 내용:
  - `models.user.User` 및 `schemas.user.User`에 `is_admin: bool = False` 추가, 마이그레이션 반영.
  - 토큰 생성 시 `is_admin` 클레임 포함(선택), 혹은 DB 조회로 검사.
  - `core/auth_middleware.py`에 `require_admin` 의존성 추가.
  - 아래 라우터의 관리자 엔드포인트에 적용:
    - `myapi/routers/price_router.py`의 `/prices/admin/*`
    - `myapi/routers/settlement_router.py`의 `/admin/settlement/*`
    - `myapi/routers/point_router.py`와 `myapi/routers/reward_router.py`의 admin 경로 전부

2) 인증 객체 접근 방식 수정
- 내용:
  - `point_router.py`, `reward_router.py`에서 `current_user.get(...)` 제거.
  - `current_user: User` 모델 속성 사용(`current_user.id`, `current_user.is_admin`).

3) 수동 정산 시 포인트 지급 일치화
- 내용:
  - `SettlementService.manual_settle_symbol()`에서 자동 정산과 동일하게 정답 예측에 대해 `PointService.award_prediction_points(...)` 호출.
  - 또는 자동 정산 루프 로직을 공용 메서드로 추출해 manual에서도 재사용.

4) 트랜잭션 순서/일관성 개선
- 내용:
  - `active_universe_repository.py`, `session_repository.py` 내 `flush()` → `commit()` 순서로 정리.

5) 예측 응답 변환 안전화
- 내용:
  - `prediction_repository.py::_to_prediction_response()`에서 `points_earned`를 `model_instance.points_earned or 0` 형태로 방어적 처리.

6) (선택) PriceService 캐시 TTL 고도화
- 내용:
  - 장 상태별 TTL 차등 적용(OPEN 30초, PRE/AFTER 5분, CLOSED 30분 등).

7) (선택) 예측 수수료 차감 플로우 개선
- 내용:
  - 선차감 → 생성 실패 시 환불 대신, 생성 성공 시 차감 혹은 트랜잭션 묶음으로 단순화.

---

## 제안 패치 포인트(파일 경로별)

- `myapi/routers/price_router.py`: admin 엔드포인트에 `require_admin` 적용
- `myapi/routers/settlement_router.py`: admin 엔드포인트에 `require_admin` 적용
- `myapi/routers/point_router.py`: `current_user` 접근을 속성 접근으로 수정, admin 권한 검사 교정
- `myapi/routers/reward_router.py`: 동일
- `myapi/services/settlement_service.py`: `manual_settle_symbol()`에서 포인트 지급 호출 추가
- `myapi/repositories/active_universe_repository.py`: `set_universe_for_date()`에서 flush→commit 순서로 변경
- `myapi/repositories/session_repository.py`: 불필요 import 제거, flush→commit 순서 정리
- `myapi/repositories/prediction_repository.py`: `_to_prediction_response()`의 `points_earned` 안전 처리
- (선택) `myapi/services/price_service.py`: 장 상태별 TTL 적용
- (선택) `myapi/services/prediction_service.py`: 수수료 차감 흐름 개선

---

## 후속 작업 체크리스트

- [ ] User/스키마에 `is_admin` 추가 및 마이그레이션 적용
- [ ] JWT 클레임 또는 DB연동 방식으로 `require_admin` 의존성 구현
- [ ] admin 라우트 전부에 `require_admin` 적용(가격/정산/포인트/리워드)
- [ ] `point_router.py`/`reward_router.py`의 `current_user` 접근 방식 수정
- [ ] 수동 정산 시 포인트 지급 로직 추가(자동 정산과 일치화)
- [ ] `flush()`/`commit()` 순서 정리(유니버스/세션 리포)
- [ ] 예측 응답 `points_earned` 변환 방어 코드 적용
- [ ] (선택) PriceService 캐시 TTL 차등화
- [ ] (선택) 예측 수수료 차감 플로우 단순화/트랜잭션화

---

## 비고
- 현재 코드베이스는 문서의 주요 요구사항(예측 시간 제한, 유니버스 기반, 마감 후 자동 정산, 포인트 경제)을 전반적으로 충족합니다. 본 문서의 수정 권고안은 운영 안전성과 데이터 회계 일관성을 높이기 위한 것입니다.
- 원하시면 위 항목들을 순서대로 패치해 드리겠습니다(권한/타입 문제, 수동 정산 포인트 지급부터 우선 권장).


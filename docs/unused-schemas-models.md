# Unused Schemas & Models Inventory

- 기준일: 2025-10-01 (verified scan)
- 스캔 범위: `myapi/**` (전체 프로젝트)
- 판별 방식: 스키마/모델 정의와 실제 코드 참조를 검증. 스키마 간 의존 관계, utils 모듈, `__init__.py` export 포함.

## ❌ 실제 사용 중 (삭제 불가)

| File | Line | Class | 사용처 |
| --- | --- | --- | --- |
| `myapi/schemas/market.py` | 4 | `MarketStatusResponse` | `myapi/utils/market_hours.py:108, 124` |
| `myapi/models/settlement.py` | 7 | `OutcomeEnum` | `myapi/models/settlement.py:28` (Column 정의) |
| `myapi/models/settlement.py` | 12 | `SettlementStatusEnum` | `myapi/models/settlement.py:32` (Column 정의 및 기본값) |
| `myapi/schemas/settlement.py` | 8 | `OutcomeType` | `SettlementCreate`, `SettlementResponse`, `SettlementStats`에서 사용 |
| `myapi/schemas/settlement.py` | 14 | `SettlementStatus` | `SettlementResponse`에서 사용 |
| `myapi/schemas/settlement.py` | 20 | `EODDataCreate` | `BatchSettlementRequest`에서 사용 |
| `myapi/schemas/settlement.py` | 49 | `SettlementCreate` | 내부적으로 `OutcomeType` 사용 |
| `myapi/schemas/settlement.py` | 63 | `SettlementResponse` | `myapi/schemas/__init__.py:6` export |
| `myapi/schemas/settlement.py` | 134 | `SettlementStatusResponse` | `myapi/services/settlement_service.py:584, 592, 638` |
| `myapi/schemas/settlement.py` | 164 | `SettlementStats` | 내부적으로 `OutcomeType` 사용 |
| `myapi/schemas/settlement.py` | 177 | `BatchSettlementRequest` | 내부적으로 `EODDataCreate` 사용 |
| `myapi/schemas/settlement.py` | 189 | `BatchSettlementResponse` | 정의되어 있음 (잠재적 사용) |
| `myapi/schemas/pagination.py` | 21 | `PaginatedResponse` | `myapi/schemas/user.py:7` import |
| `myapi/schemas/user.py` | 91 | `UserListItem` | `UserListResult`에서 사용 |
| `myapi/schemas/user.py` | 102 | `UserListResult` | 내부적으로 `UserListItem` 사용 |
| `myapi/schemas/user.py` | 108 | `UserSearchItem` | `UserSearchResult`에서 사용 |
| `myapi/schemas/user.py` | 118 | `UserSearchResult` | 내부적으로 `UserSearchItem` 사용 |

## ✅ 안전하게 삭제 가능 (실제 미사용)

| File | Line | Class | 검증 결과 |
| --- | --- | --- | --- |
| `myapi/schemas/cooldown.py` | 6 | `CooldownTimerCreateSchema` | 정의만 있고 코드 참조 없음 |
| `myapi/schemas/error_log.py` | 27 | `ErrorLogCreate` | 정의만 있고 코드 참조 없음 |
| `myapi/schemas/pagination.py` | 7 | `PaginationParams` | 정의만 있고 코드 참조 없음 |
| `myapi/schemas/pagination.py` | 28 | `DirectPaginatedResponse` | 정의만 있고 코드 참조 없음 |
| `myapi/schemas/session.py` | 32 | `SessionTransition` | 정의만 있고 코드 참조 없음 |

## Follow-up

- ✅ 안전하게 삭제 가능한 항목: **5개**
- ❌ 실제 사용 중인 항목: **17개** (스키마 간 의존 관계, utils, export 포함)
- 삭제 전 테스트 실행 및 마이그레이션 영향 확인 필수
- 새로 추가한 스키마/모델은 동일 방식으로 주기적으로 스캔하여 문서화
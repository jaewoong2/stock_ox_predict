# O/X Prediction Service API

미국 주식 시장을 배경으로 하루 한 번 제공되는 종목 리스트에 대해 상승(`O`) 또는 하락(`X`)을 예측하고, 결과에 따라 포인트와 리워드를 제공하는 게이미피케이션 서비스의 백엔드 API입니다. FastAPI와 SQLAlchemy를 기반으로 세션·예측·정산·포인트·리워드까지 전 과정을 자동화하고, AWS 인프라와 연계된 배치 파이프라인으로 안정적으로 운영됩니다.

## 목차
- [서비스 개요](#서비스-개요)
- [핵심 기능](#핵심-기능)
- [사용자 여정](#사용자-여정)
- [시스템 아키텍처](#시스템-아키텍처)
- [도메인 & API 모듈](#도메인--api-모듈)
- [기술 스택](#기술-스택)
- [프로젝트 구조](#프로젝트-구조)
- [로컬 개발 가이드](#로컬-개발-가이드)
- [테스트](#테스트)
- [배포 & 운영](#배포--운영)
- [참고 문서](#참고-문서)

## 서비스 개요
- **미션**: "누구나 쉽게 참여할 수 있는 일일 주식 O/X 퀴즈"를 통해 투자 학습과 재미를 동시에 제공.
- **비즈니스 가치**: 간단한 참여 → 공정한 정산 → 포인트/리워드 보상 → 광고 및 리텐션 고도화.
- **대상 시장**: 미국 증시(나스닥, NYSE 등)를 중심으로 한 글로벌 투자 관심 사용자.
- **운영 철학**: 거래일 기준의 세션 제어, 예측 시점 가격 스냅샷, 장마감(EOD) 비교를 통한 투명한 정산.

## 핵심 기능
- **거래일/세션 관리**: `myapi/routers/session_router.py`에서 예측 가능 시간과 상태를 제어, 거래일 기반으로 API 동작을 통일합니다.
- **예측 슬롯 & 게이미피케이션**: 사용자별 일일 슬롯 관리, 광고/쿨다운을 통한 슬롯 충전(`myapi/services/cooldown_service.py`, `myapi/services/ad_unlock_service.py`).
- **예측 제출/수정/취소**: 중복방지, 취소 시간 제한, 포인트 선차감 등 비즈니스 규칙을 `myapi/services/prediction_service.py`에 집약.
- **가격 스냅샷 & 정산**: yfinance/Alpha Vantage를 활용한 가격 수집과 검증(`myapi/services/price_service.py`), 예측 시점 스냅샷 대비 장마감 결과 정산(`myapi/services/settlement_service.py`).
- **포인트 원장 & 정합성**: 멱등성 있는 포인트 트랜잭션(`myapi/services/point_service.py`)과 정합성 점검 API로 경제 시스템 안정화.
- **리워드 상점**: 카탈로그/재고/교환 내역/관리자 재고 조정을 제공하는 리워드 도메인(`myapi/services/reward_service.py`).
- **OAuth 인증 & 가입 보너스**: Google/Kakao/Apple OAuth 지원과 신규 가입 보너스 지급(`myapi/services/auth_service.py`).
- **배치 & 자동화**: AWS SQS/Lambda/EventBridge와 연동된 배치 큐(`myapi/routers/batch_router.py`)로 가격 갱신, 정산, 포인트 지급을 자동화.

## 사용자 여정
1. **온보딩 & 인증**
   - OAuth 인증 URL 발급 → 콜백 처리 후 JWT 발급 (`myapi/routers/auth_router.py`).
   - 신규 사용자는 1,000 포인트 웰컴 보너스를 즉시 지급.
2. **일일 예측 사이클**
   - `/session/today`로 당일 거래일·시장 상태 확인.
   - `/universe/today`에서 오늘의 종목을 조회하고, `/predictions/{symbol}`으로 예측 제출.
   - 슬롯이 부족하면 `/ads/unlock-slot`(광고) 또는 `/cooldown/claim`으로 충전.
3. **정산 & 리워드**
   - 장 마감 후 배치가 가격을 수집하고 `/admin/settlement/settle-day/{date}`로 정산.
   - `/points/balance`, `/points/ledger`로 획득 포인트 확인 후 `/rewards/redeem`으로 리워드 교환.

## 시스템 아키텍처
```
┌─────────────┐    ┌──────────────┐    ┌──────────────────┐
│ Web / App   │←→│ API Gateway   │←→│ FastAPI (myapi)   │
│ Frontend    │    │ (REST)      │    │  Routers/Services│
└─────────────┘    └──────────────┘    └─────┬────────────┘
                                             │
                       ┌─────────────────────┴──────────────────┐
                       │ Postgres (crypto schema)               │
                       │ SQLAlchemy ORM / Alembic-ready models │
                       └────────────────┬───────────────────────┘
                                        │
     ┌────────────────────────┬─────────┴─────────┬────────────────────┐
     │ External Market Data   │ Batch Automation  │ AWS Integrations    │
     │ (yfinance, AlphaVantage)│ (EventBridge→SQS) │ (Lambda, SQS, SES) │
     └────────────────────────┴───────────────────┴────────────────────┘
```
- Dependency Injector(`myapi/containers.py`)로 서비스/리포지토리를 주입하고, `myapi/core` 모듈에서 로깅·예외·보안 미들웨어를 관리합니다.
- 가격/예측/포인트 등 모든 도메인은 트랜잭션 안전성과 재시도 전략을 내장해 운영 중단 시에도 일관성을 유지합니다.
- 배치 경로는 `BatchRouter → AwsService → SQS/Lambda` 흐름으로 구성되어 관리형 스케줄러(EventBridge)와 결합됩니다.

## 도메인 & API 모듈
| 도메인 | 주요 기능 | 대표 엔드포인트 | 구현 파일 |
| --- | --- | --- | --- |
| 인증(Auth) | OAuth, JWT, 토큰 갱신 | `GET /auth/oauth/{provider}/authorize`<br>`POST /auth/token/refresh` | `myapi/routers/auth_router.py` |
| 사용자(User) | 프로필, 관리자 검색, 메모 | `GET /users/me` | `myapi/routers/user_router.py` |
| 세션(Session) | 거래일/시장 상태, 예측 가능 여부 | `GET /session/today`<br>`GET /session/can-predict` | `myapi/routers/session_router.py` |
| 유니버스(Universe) | 일일 종목, 가격 스냅샷 | `GET /universe/today`<br>`POST /universe/refresh-prices` | `myapi/routers/universe_router.py` |
| 예측(Prediction) | 제출/수정/취소, 통계, 트렌드 | `POST /predictions/{symbol}`<br>`GET /predictions/summary/{day}` | `myapi/routers/prediction_router.py` |
| 가격(Price) | 실시간/분봉/EOD 조회, 검증 | `GET /prices/{symbol}` | `myapi/routers/price_router.py` |
| 정산(Settlement) | 장마감 비교, VOID 처리, 리포트 | `POST /admin/settlement/settle-day/{day}` | `myapi/routers/settlement_router.py` |
| 포인트(Points) | 잔액, 거래 원장, 관리자 조정 | `GET /points/balance`<br>`POST /points/admin/add` | `myapi/routers/point_router.py` |
| 리워드(Rewards) | 카탈로그, 재고, 교환 내역 | `GET /rewards/catalog`<br>`POST /rewards/redeem` | `myapi/routers/reward_router.py` |
| 광고/쿨다운 | 슬롯 충전, 타이머, 쿨다운 정책 | `POST /ads/unlock-slot`<br>`POST /cooldown/claim` | `myapi/routers/ad_unlock_router.py`<br>`myapi/routers/cooldown_router.py` |
| 관리자(Admin) | 모니터링, 강제 정산, 포인트 집계 | `GET /admin/system/overview` 등 | `myapi/routers/admin_router.py` |
| 배치(Batch) | SQS/Lambda 큐잉, 스케줄 모니터 | `POST /batch/universe-refresh-prices` | `myapi/routers/batch_router.py` |

## 기술 스택
- **애플리케이션**: FastAPI, Pydantic v2, Dependency Injector, Uvicorn, Mangum(AWS Lambda 호환).
- **데이터**: PostgreSQL(`crypto` 스키마), SQLAlchemy 2.x ORM, yfinance/AlphaVantage 연동, 캐시 디렉터리 자동 구성.
- **인증/보안**: OAuth(Google, Kakao, Apple), JWT, Magic Link(설정 기반), Rate Limiting, Logging Middleware.
- **인프라**: Docker, docker-compose, Terraform(AWS ECS Fargate, ALB, ECR, Route53, ACM), AWS SQS/Lambda/SES.
- **테스트 & 품질**: Pytest, pytest-asyncio, HTTPX, Python JSON Logger, 구조화 로깅.

## 프로젝트 구조
```
.
├── myapi
│   ├── main.py                # FastAPI 엔트리포인트
│   ├── config.py              # 환경설정 & Settings
│   ├── containers.py          # Dependency Injector 컨테이너
│   ├── core/                  # 로깅, 예외, 인증 미들웨어
│   ├── routers/               # API 엔드포인트(도메인별)
│   ├── services/              # 비즈니스 로직
│   ├── repositories/          # DB 접근 계층
│   ├── models/                # SQLAlchemy 모델
│   ├── schemas/               # Pydantic 스키마
│   └── utils/                 # 공통 유틸 (시장시간, yfinance 캐시 등)
├── tests/                     # 도메인별 API/서비스 테스트
├── docs/                      # 추가 사양 및 아키텍처 문서
├── terraform/                 # AWS 배포용 Terraform 코드
├── Dockerfile*, docker-compose*.yaml
├── requirements.txt
└── deploy-fastapi.sh, deploy.sh
```

## 로컬 개발 가이드
1. **필수 도구 설치**
   - Python 3.11, PostgreSQL 14+, Git, Docker(선택).
2. **환경 변수 설정**
   - `myapi/config.py`는 `myapi/.env`를 기본 로드합니다. 아래 형태로 파일을 준비하세요:
     ```env
     # myapi/.env (예시)
     POSTGRES_HOST=localhost
     POSTGRES_PORT=5432
     POSTGRES_USERNAME=postgres
     POSTGRES_PASSWORD=local-password
     POSTGRES_DATABASE=ox_predict
     POSTGRES_SCHEMA=crypto

     SECRET_KEY=change-me
     JWT_ALGORITHM=HS256
     GOOGLE_CLIENT_ID=...
     GOOGLE_CLIENT_SECRET=...
     KAKAO_CLIENT_ID=...
     KAKAO_CLIENT_SECRET=...
     APPLE_CLIENT_ID=...
     APPLE_TEAM_ID=...
     APPLE_KEY_ID=...
     APPLE_PRIVATE_KEY=""

     AWS_REGION=ap-northeast-2
     SQS_MAIN_QUEUE_URL=https://sqs.../ox.fifo
     ```
   - 민감한 값은 버전 관리에 포함하지 마세요. 배포 환경에서는 AWS Parameter Store/Secrets Manager 사용을 권장합니다.
3. **의존성 설치 & 실행**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt

   # 데이터베이스 준비 (스키마 생성)
   psql -h localhost -U postgres -c 'CREATE SCHEMA IF NOT EXISTS crypto;'

   # 개발 서버 실행
   uvicorn myapi.main:app --reload
   ```
4. **API 문서 확인**: `http://localhost:8000/docs` (Swagger UI), `http://localhost:8000/redoc`.
5. **Docker로 실행 (선택)**
   ```bash
   docker build -t ox-predict-api -f Dockerfile.fastapi .
   docker run --rm -p 8000:8000 --env-file myapi/.env ox-predict-api
   ```

## 테스트
- 단위 및 통합 테스트는 `tests/` 디렉터리에 정리되어 있으며 Pytest로 실행합니다.
  ```bash
  pytest
  ```
- HTTP 계층 테스트는 HTTPX 클라이언트를, 서비스 계층 테스트는 인메모리/모킹 전략을 사용합니다.
- CI 파이프라인 구성 시 `pytest -q`와 함께 커버리지 도구를 추가하는 것을 권장합니다.

## 배포 & 운영
- **컨테이너 빌드**: `Dockerfile.fastapi`로 FastAPI 서비스를, `Dockerfile.lambda`로 Lambda 함수 이미지를 구성합니다.
- **Terraform** (`terraform/`)
  1. `terraform init`
  2. `cp terraform.tfvars.example terraform.tfvars` 후 환경 값 입력
  3. `terraform apply`로 ECS Fargate, ALB, ECR, Route53, ACM 등을 프로비저닝
- **애플리케이션 배포**
  - `deploy-fastapi.sh` 스크립트로 ECR 푸시 및 ECS 서비스 업데이트 자동화.
  - Lambda 기반 배치는 `deploy.sh`를 통해 패키징/배포.
- **배치 운영**
  - EventBridge Scheduler → Lambda → `batch_router` → SQS → FastAPI 내부 핸들러 순으로 동작합니다.
  - 가격 스냅샷, 장마감 정산, 포인트 지급 등 주요 작업은 FIFO 큐로 순서 보장.
- **모니터링 & 로깅**
  - `myapi/logging_config.py`에서 Python JSON Logger 세팅.
  - `/health` 엔드포인트로 ALB/ECS/Lambda 헬스 체크.
  - 포인트/정산/가격 오류는 `ErrorLogService`를 통해 DB에 축적되어 관리자 API로 노출.
- **보안 & 안정성**
  - JWT 만료, Rate Limiting, 세션 상태 검사로 남용 방지.
  - 예측 시점 가격 스냅샷 미존재 시 자동 `VOID` 처리로 데이터 무결성 확보.

## 참고 문서
- 서비스 플로우 & 정책: `docs/service_flow.md`
- 프론트엔드 연동 가이드: `docs/frontend-api.md`
- 크립토 RANGE 예측 변경 노트: `docs/frontend-api.md`
- OAuth 셋업 가이드: `docs/oauth-setup-guide.md`
- 티커 정책 및 관리: `docs/tickers.md`
- 라우터/서비스 리뷰 노트: `docs/review-routers-services-repositories.md`

프로젝트나 문서에 대한 질문은 언제든지 환영합니다. 🚀

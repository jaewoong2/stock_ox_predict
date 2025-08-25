# OX Universe - 구현 TODO

## 완료된 작업 ✅

### Phase 1: 기본 인프라 및 데이터베이스
- [x] 프로젝트 구조 분석 완료
- [x] 요구사항 문서 분석 완료
- [x] 아키텍처 설계 분석 완료
- [x] **프로젝트 폴더 구조 정리 및 기본 설정**
  - [x] requirements.txt 업데이트 (JWT, OAuth, 배치 등 필수 패키지 추가)
  - [x] .env.example 파일 생성 (완전한 환경변수 설정)
- [x] **SQLAlchemy 모델 정의 (crypto 스키마 기반)**
  - [x] 사용자 모델 (OAuth 지원)
  - [x] 세션 및 종목 모델
  - [x] 예측 및 정산 모델
  - [x] 포인트 및 리워드 모델
- [x] **Pydantic 스키마 정의 (모든 Request/Response)**
  - [x] 인증 관련 스키마
  - [x] 사용자, 세션, 예측 스키마
  - [x] 정산, 포인트, 리워드 스키마
- [x] **Repository 패턴 구현 (Pydantic 응답)**
  - [x] BaseRepository 클래스 (Pydantic 응답 보장)
  - [x] UserRepository (OAuth 지원)
  - [x] SessionRepository & ActiveUniverseRepository
  - [x] PredictionRepository & UserDailyStatsRepository
  - [x] PointsRepository (멱등성 보장)
  - [x] RewardsRepository (인벤토리 & 교환)
  - [x] **Pylance 타입 에러 수정 완료**
    - [x] SQLAlchemy Column 타입 에러 해결
    - [x] BaseRepository 제네릭 타입 제약 수정
    - [x] 안전한 모델 속성 접근 패턴 적용
    - [x] Optional 타입 처리 및 null-safety 보장

## 진행 중인 작업 🚧

- 포인트 시스템 및 리워드 시스템 구현 (진행 예정)

## 대기 중인 작업 📋

### Phase 2: 서비스 계층 구현
- [x] **인증 시스템 구현 (JWT + OAuth)** ✅
  - [x] JWT 토큰 관리 서비스 (HS256)
  - [x] OAuth 인증 서비스 (Google & Kakao)
  - [x] 인증 미들웨어
  - [x] 사용자 인증 서비스
- [x] **세션 관리 시스템 구현** ✅
  - [x] 세션 서비스 구현
  - [x] 활성 유니버스 서비스 구현
- [x] **예측 시스템 구현** ✅
  - [x] 예측 서비스 구현
  - [x] 예측 제출/수정/취소 검증 로직
  - [x] 일일 통계 관리 서비스 연동
  - [x] 정산 보조 로직 (lock/bulk update/stats)
  - [x] **예측 라우터 완전 구현** (prediction_router.py 완료)
    - [x] 기본 CRUD 작업 (제출/수정/취소)
    - [x] 사용자 예측 히스토리 조회
    - [x] 종목별 예측 조회
    - [x] 일일 통계 및 요약 조회
    - [x] 남은 예측 슬롯 조회 및 증가
    - [x] 관리자용 정산 처리 엔드포인트 (잠금/일괄처리/대기목록)
    - [x] **가격 조회 시스템 구현** (PriceService 완료)
      - [x] 실시간 종목 가격 조회 (Yahoo Finance API 연동)
      - [x] 오늘의 유니버스 전체 가격 일괄 조회
      - [x] EOD(장 마감) 가격 조회 및 검증
      - [x] 예측 결과와 실제 가격 비교 기능
    - [x] **정산 검증 시스템 구현** (SettlementService 완료)
      - [x] 자동 정산 및 가격 검증
      - [x] 예측 성공/실패 판정 로직
      - [x] 수동 정산 기능 (관리자용)
      - [x] 정산 요약 및 통계 제공
      - [x] 비정상 가격 데이터 처리 (VOID 처리)
- [x] **배치 시스템 구현** ✅
  - [x] 배치 서비스 구현 (Universe & Session 관리)
  - [x] SQS 기반 워크플로우 스케줄링
  - [x] 일일 배치 작업 자동화 (유니버스 생성 → 예측 시작 → 예측 마감)
- [ ] **포인트 시스템 구현**
  - [ ] 포인트 서비스 구현 (멱등성 보장)
  - [ ] 포인트 거래 및 무결성 관리
- [ ] **리워드 시스템 구현**
  - [ ] 리워드 서비스 구현
  - [ ] 인벤토리 관리 서비스
  - [ ] 교환 처리 서비스

### Phase 3: API 계층 구현
- [x] **라우터 구현 (Auth & User)** ✅
  - [x] 사용자 인증 라우터
  - [x] 사용자 관리 라우터 (프로필, 검색, 통계)
  - [x] 로컬 회원가입 제거 (OAuth 전용 가입)
  - [x] 로컬 로그인 제거 (OAuth 전용 로그인)
  - [x] 세션 관리 라우터 ✅
  - [x] 예측 제출 라우터 (인증 사용자 전용) ✅
  - [x] 유니버스 관리 라우터 ✅
  - [x] 배치 관리 라우터 ✅ (Universe/Session 배치, SQS 워크플로우 스케줄링)
  - [ ] 포인트 관리 라우터
  - [ ] 리워드 교환 라우터
- [x] **배치 처리 시스템** ✅
  - [x] 배치 워커 구현 (SQS 기반)
  - [x] 일일 워크플로우 자동화
  - [ ] EOD 데이터 수집 서비스
  - [ ] 정산 서비스 구현

### Phase 4: 통합 및 테스트
- [x] **의존성 주입 설정 완료** ✅
  - [x] 서비스 컨테이너 설정 (containers.py)
  - [x] Repository 의존성 등록
  - [x] 전체 서비스 의존성 통합 (Universe, Session, Batch, Prediction)
- [x] **FastAPI 앱 통합** ✅
  - [x] 라우터 등록 (main.py) — auth, users, predictions, session, universe, batch 포함
  - [ ] 미들웨어 설정
  - [x] CORS 및 보안 설정
- [x] **테스트 코드 작성** ✅
  - [ ] Repository 테스트
  - [x] 서비스 테스트 (Universe, Session, Batch)
  - [x] API 엔드포인트 테스트 (Auth, User, Universe, Session, Batch)
  - [x] 로컬 회원가입 테스트 제거 (OAuth Only 정책 반영)
  - [x] 로컬 로그인 테스트 제거 (OAuth Only 정책 반영)

## 다음에 해야 할 구체적 작업

1. **데이터베이스 스키마 생성**
   - Alembic 마이그레이션 스크립트 생성
   - crypto 스키마 및 모든 테이블 생성
   - 인덱스 및 제약조건 설정

2. **인증 시스템 구현**
   - JWT 설정 (RS256 알고리즘)
   - Google OAuth 연동
   - 인증 미들웨어 구현

3. **서비스 계층 구현**
   - 각 도메인별 서비스 클래스 구현
   - 비즈니스 로직 구현
   - 트랜잭션 관리

## 주요 고려사항

- ✅ 모든 Request/Response는 Pydantic BaseModel 사용
- ✅ Repository 응답은 ORM이 아닌 Pydantic 스키마 사용
- ✅ Pylance 에러 방지를 위한 타입 힌팅 (SQLAlchemy Column 타입 에러 해결)
- 비즈니스 로직은 @docs/ 문서 기반으로 구현
- 멱등성 보장 (포인트 시스템)
- 트랜잭션 무결성 보장
 - 가입/로그인은 OAuth 전용 (로컬 이메일/비밀번호 비활성화)
 - OAuth 로그인 시 닉네임 변경 감지 및 중복 회피 동기화

## 구현 완료 현황

### ✅ **Phase 1: 기본 인프라 및 데이터베이스** - 완료
- **SQLAlchemy 모델**: 모든 도메인 모델 완료 (User, Session, Prediction, Points, Rewards)
- **Pydantic 스키마**: 완전한 Request/Response 스키마 정의
- **Repository 패턴**: 완전 구현된 데이터 액세스 계층 + 타입 안전성
  - BaseRepository (제네릭 CRUD + Pydantic 보장)
  - UserRepository (OAuth 지원)
  - SessionRepository & ActiveUniverseRepository 
  - PredictionRepository & UserDailyStatsRepository
  - PointsRepository (멱등성 보장)
  - RewardsRepository (인벤토리 & 교환 관리)
  - **모든 Pylance 타입 에러 해결** (SQLAlchemy Column 타입 호환성, 제네릭 타입 제약, Optional 처리)

### 🚧 **현재 진행 중**: Phase 1.5 - 데이터베이스 스키마 생성
- Alembic 마이그레이션 스크립트
- PostgreSQL crypto 스키마 생성
- 테이블 및 제약조건 설정

### ✅ **완료된 작업**: Phase 2-4 - 서비스/API/테스트 구현 완료
- **UniverseService**: 오늘의 종목 관리 완료 (오늘 종목 조회, 특정 날짜 종목 조회, 종목 업서트)
- **SessionService**: 세션 상태 관리 완료 (현재 세션, 예측 시작/종료, 정산 상태 전환)  
- **PredictionService**: 예측 시스템 완료 (예측 제출/수정/취소, 통계 조회, 정산 관련)
- **BatchService**: 배치 시스템 완료 (SQS 워크플로우, 일일 자동화, Universe/Session 관리)
- **API 라우터**: Universe, Session, Batch 라우터 구현 및 통합
- **테스트 코드**: 모든 라우터 및 서비스에 대한 포괄적인 단위 테스트 완료

### 📋 **다음 단계**: 포인트 및 리워드 시스템 구현
핵심 예측 시스템과 배치 자동화가 완료되었으므로, 사용자 보상 시스템 구현이 다음 우선순위입니다.

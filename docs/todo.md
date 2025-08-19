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

## 진행 중인 작업 🚧

- [ ] PostgreSQL 스키마 및 테이블 생성 (crypto 스키마)

## 대기 중인 작업 📋

### Phase 2: 인증 및 세션 관리
- [ ] **인증 시스템 구현 (JWT + OAuth)**
  - [ ] JWT 토큰 관리 (RS256)
  - [ ] OAuth 인증 구현 (Google)
  - [ ] 인증 미들웨어
- [ ] **세션 관리 시스템 구현**
  - [ ] 세션 서비스 구현
  - [ ] 세션 라우터 구현

### Phase 3: 핵심 비즈니스 로직
- [ ] **예측 시스템 구현**
  - [ ] 예측 서비스 구현
  - [ ] 예측 제출 검증 로직
  - [ ] 예측 라우터 구현
- [ ] **정산 및 EOD 데이터 처리 시스템**
  - [ ] EOD 데이터 수집 서비스
  - [ ] 정산 서비스 구현
  - [ ] 배치 워커 구현
- [ ] **포인트 시스템 구현**
  - [ ] 포인트 서비스 구현
  - [ ] 포인트 지급 워커
  - [ ] 포인트 라우터 구현
- [ ] **리워드 시스템 구현**
  - [ ] 리워드 서비스 구현
  - [ ] 리워드 교환 워커
  - [ ] 리워드 라우터 구현

### Phase 4: 통합 및 테스트
- [ ] **비즈니스 로직 통합 및 테스트**
  - [ ] FastAPI 앱 통합
  - [ ] 라우터 등록
  - [ ] 미들웨어 설정
  - [ ] 테스트 코드 작성

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
- ✅ Pylance 에러 방지를 위한 타입 힌팅
- 비즈니스 로직은 @docs/ 문서 기반으로 구현
- 멱등성 보장 (포인트 시스템)
- 트랜잭션 무결성 보장

## 구현 완료 현황

현재까지 **데이터 액세스 계층(Repository Pattern)**이 완전히 구현되어 Pydantic 응답이 보장됩니다.
- 총 6개 도메인의 Repository 구현 완료
- 모든 CRUD 작업에서 Pydantic 스키마 반환
- 비즈니스 로직에 필요한 메서드 구현 완료

다음 단계는 **데이터베이스 스키마 생성** 후 **서비스 계층 구현**입니다.
## 전체 서비스 아키텍처 및 플로우

### 1. 서비스 개요 및 핵심 가치

**미국 주식 O/X 예측 서비스**는 사용자가 매일 선정된 미국 주식 종목에 대해 상승/하락을 예측하고, 정답에 따라 포인트를 획득하여 리워드를 교환할 수 있는 게이미피케이션 서비스입니다.

**핵심 가치제안:**
- **간단한 참여**: 매일 100개 종목에 대한 단순한 O/X 선택
- **공정한 정산**: EOD(장 마감) 가격 기준 자동 정산
- **보상 시스템**: 예측 성공 시 포인트 지급, 리워드 교환 가능
- **성장 요소**: 광고 시청을 통한 추가 예측 기회 제공

### 2. 전체 시스템 아키텍처

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Client Apps   │    │   API Gateway   │    │   FastAPI App   │
│  (Web/Mobile)   │◄──►│                 │◄──►│  (Main Service) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                                        │
                       ┌─────────────────┐              │
                       │   OAuth APIs    │◄─────────────┤
                       │ (Google/Kakao)  │              │
                       └─────────────────┘              │
                                                        │
┌─────────────────┐    ┌─────────────────┐              │
│  Batch          │◄──►│   Message Queue │◄─────────────┤
│ (EOD/Settlement)│    │   (AWS SQS)     │              │
└─────────────────┘    └─────────────────┘              │
                                                        │
┌─────────────────┐    ┌─────────────────┐              │
│  External APIs  │◄──►│   PostgreSQL    │◄─────────────┘
│   (Yahoo)       │    │ (crypto schema) │
└─────────────────┘    └─────────────────┘
```

### 3. 데이터 모델 및 핵심 엔티티

**핵심 도메인 객체:**
- **User**: OAuth 기반 사용자 (Google/Kakao 로그인)
- **Session**: 일일 예측 세션 (OPEN/CLOSED 상태)
- **Universe**: 일일 선정 종목 (~100개)
- **Prediction**: 사용자 예측 (상승/하락)
- **Settlement**: 정산 결과 (정답/오답/VOID)
- **Points**: 포인트 원장 (멱등성 보장)
- **Reward**: 리워드 카탈로그 및 교환

**데이터 관계:**
```
User ──┬─► Prediction ──► Settlement ──► Points ──► Reward Redemption
       └─► AdUnlock (광고 시청) ──► Additional Prediction Slots
```

### 4. 상세 사용자 플로우

#### 4.1 사용자 온보딩 및 인증
```mermaid
graph TD
    A[사용자 접속] --> B[OAuth 로그인 선택]
    B --> C[Google/Kakao 인증]
    C --> D[JWT 토큰 발급]
    D --> E[사용자 세션 생성]
    E --> F[신규 가입자 1000포인트 지급]
```

#### 4.2 일일 예측 참여 플로우
```mermaid
graph TD
    A[메인 페이지 접속] --> B[현재 세션 상태 확인]
    B --> C{세션 상태 확인}
    C -->|OPEN| D[오늘의 종목 100개 조회]
    C -->|CLOSED| E[예측 마감 안내]
    
    D --> G[사용자 예측 슬롯 확인]
    G --> H{슬롯 여부}
    H -->|있음| I[종목 선택 및 예측 제출]
    H -->|없음| J[광고 시청 또는 쿨다운 대기]
    
    I --> L[예측 저장 및 확인]
    
    J --> M[광고 시청 완료]
    M --> N[추가 슬롯 1개 획득]
    N --> I
```

```
  실제 API 엔드포인트:

  | 플로우 단계      | API 엔드포인트                           | 파일 위치                   |
  |-------------|-------------------------------------|-------------------------|
  | 세션 상태 확인    | GET /session/today                  | session_router.py:21    |
  | 예측 가능 여부 체크 | GET /session/can-predict            | session_router.py:170   |
  | 오늘의 종목 조회   | GET /universe/today                 | universe_router.py:20   |
  | 예측 제출       | POST /predictions/{symbol}          | prediction_router.py:29 |
  | 예측 수정       | PUT /predictions/{prediction_id}    | prediction_router.py:66 |
  | 예측 취소       | DELETE /predictions/{prediction_id} | prediction_router.py:96 |
  | 슬롯 정보 조회    | GET /ads/available-slots            | ad_unlock_router.py:183 |
  | 광고 시청 완료    | POST /ads/watch-complete            | ad_unlock_router.py:54  |
  | 쿨다운 슬롯 해제   | POST /ads/unlock-slot               | ad_unlock_router.py:121 |
```

#### 4.3 정산 및 보상 플로우
```mermaid
graph TD
    A[23:59 KST 예측 마감] --> B[06:00 KST EOD 데이터 수집, EOD DB 저장] 
    B --> C[정산 로직 실행]
    C --> D{예측 결과}
    D -->|정답| E[50포인트 지급]
    D -->|오답| F[포인트 없음]
    
    E --> H[포인트 원장 업데이트]
    F --> H
    G --> H
    H --> I[사용자 알림 발송]
```

#### 4.4 리워드 교환 플로우
```mermaid
graph TD
    A[리워드 카탈로그 조회] --> B[원하는 상품 선택]
    B --> C{포인트 잔액 확인}
    C -->|부족| D[광고 시청 유도]
    C -->|충분| E[포인트 차감 및 교환 요청]
    E --> F[외부 벤더 발급 요청]
    F --> G{발급 성공}
    G -->|성공| H[교환 완료 알림]
    G -->|실패| I[포인트 환불]
```

### 5. 시스템 배치 및 자동화 플로우

#### 5.1 일일 배치 스케줄 (KST 기준)
```
06:00 - 일일 종목 선정 배치 실행
     └─► 인기 미국 주식 100개 선정
     └─► active_universe 테이블 업데이트

06:00 - 정산 및 새 세션 시작 배치
     ├─► EOD 가격 데이터 수집 (Yahoo Finance)
     ├─► EOD 가격 데이터 DB저장
     ├─► 전일 예측 정산 실행 (정답/오답/VOID 판정)
     ├─► 포인트 지급 처리 (승리시 100pt, 실패시 0pt, 무효시 환불)
     └─► 새 예측 세션 OPEN 상태로 전환

23:59 - 예측 마감 배치
     └─► 현재 예측 세션 CLOSED 상태로 전환
```

#### 5.2 SQS 기반 비동기 처리
```
사용자 예측 제출 → SQS Queue
EOD 데이터 수집 → SQS Queue 
정산 완료 → SQS Queue
리워드 교환 → SQS Queue
```

### 6. 고급 기능 및 게이미피케이션

#### 6.1 광고 시스템 및 슬롯 관리
```
기본 예측 슬롯: 3개/일
광고 시청시: +1슬롯 (최대 10개/일)
쿨다운 시스템: 5분 대기 후 +1슬롯 추가
```

#### 6.2 포인트 경제 시스템
```
신규 가입: +1000 포인트
정답 보상: +50 포인트/건
리워드 교환: -포인트 (상품별 차등)
```

### 7. 기술적 특징 및 안정성

#### 7.1 데이터 정합성 보장
- **멱등성 보장**: 포인트 지급/차감에 ref_id 기반 중복 방지
- **트랜잭션 관리**: ACID 속성 보장으로 데이터 일관성 유지
- **감사 로그**: 모든 포인트 변동 내역 추적
- **정합성 검증**: 일일 포인트 총합 검증 배치

#### 7.2 성능 및 확장성
- **Connection Pooling**: PostgreSQL 연결 최적화
- **레이트 리밋**: 분당/시간당 API 호출 제한
- **인덱스 최적화**: 핵심 쿼리 성능 향상
- **SQS 큐**: 비동기 처리로 응답성 개선

#### 7.3 모니터링 및 운영
- **비즈니스 메트릭**: DAU, 예측 참여율, 승률, 포인트 순환율
- **시스템 메트릭**: API 응답시간, DB 성능, 큐 처리량
- **알림 시스템**: 배치 실패, 데이터 이상, 보안 위협 감지
- **관리자 도구**: 종목 관리, 포인트 조정, 리워드 관리

### 8. 보안 및 컴플라이언스

#### 8.1 인증 및 권한 관리
- **OAuth 2.0**: Google/Kakao 안전한 로그인
- **JWT 토큰**: RS256 알고리즘 기반 무상태 인증
- **관리자 권한**: MFA 적용, 권한별 API 접근 제어

#### 8.2 데이터 보호
- **개인정보 최소화**: 필수 정보만 수집
- **암호화**: 민감 데이터 AES-256 암호화
- **감사 추적**: 모든 관리자 작업 로깅

### 9. 사용자 측면 상세 플로우

1. **사용자 접속 및 인증**
   - 웹/모바일 앱 접속
   - OAuth (Google/Kakao) 로그인
   - JWT 토큰 기반 세션 관리

2. **예측 참여 과정**
   - 현재 세션 상태 확인 (OPEN/CLOSED)
   - 오늘의 종목 100개 조회
   - 사용자 예측 슬롯 확인 (기본 3개, 광고시청으로 최대 7개)
   - 예측 제출 (상승/하락 선택)

3. **추가 기회 획득**
   - 슬롯 소진시 광고 시청 유도
   - 광고 시청 완료 후 추가 슬롯 1개 획득
   - 쿨다운 시스템 (5분 대기) 활용

4. **포인트 및 리워드 활용**
   - 포인트 잔액 및 내역 조회
   - 리워드 카탈로그 탐색
   - 포인트로 상품 교환

### 10. 시스템 측면 상세 플로우

1. **일일 사이클 관리**
   - [05:30 KST] 일일 종목 선정 및 데이터 준비
   - [06:00 KST] 전일 정산 + 새 세션 OPEN 상태 전환
   - [06:00-22:00] 사용자 예측 제출 활성화 기간
   - [23:59 KST] 예측 마감, CLOSED 상태 전환
   - [23:59-06:00] 정산 대기 및 처리

2. **데이터 처리 파이프라인**
   - EOD 가격 데이터 외부 API 수집 (Yahoo Finance)
   - 가격 변동률 계산 후 사용자 예측과 비교하여 정답/오답/VOID 판정
   - 사용자별 예측 결과 매칭
   - 포인트 지급/환불 처리 (멱등성 보장)

3. **백그라운드 작업 처리**
   - SQS 큐 기반 비동기 작업 처리
   - 배치 작업 모니터링 및 실패 처리
   - 데이터 정합성 검증 (일일 실행)
   - 시스템 헬스 체크 및 알림

이와 같이 전체적으로 **사용자 중심의 게이미피케이션**과 **시스템의 안정성 및 확장성**을 모두 고려한 종합적인 O/X 예측 서비스 아키텍처를 구축하여, 단순하면서도 중독성 있는 사용자 경험과 신뢰할 수 있는 포인트 경제 시스템을 제공합니다.

---

## 📋 **아키텍처 분석 결과** (2025-08-27)

### ✅ **완벽하게 구현된 아키텍처**

**1. 3계층 아키텍처 완전 구현**
- **Services**: 11개 서비스 (auth, user, session, universe, prediction, price, settlement, point, reward, ad_unlock, aws)
- **Repositories**: 9개 리포지토리 (user, session, active_universe, prediction, points, rewards, ad_unlock, oauth_state, base)
- **Routers**: 12개 라우터 (auth, user, session, universe, prediction, price, settlement, batch, point, reward, ad_unlock)

**2. 핵심 도메인 100% 커버**
- User (OAuth 전용), Session, Universe, Prediction, Settlement, Points, Rewards, AdUnlock
- 의존성 주입을 통한 완벽한 계층 분리
- 관리자 권한 시스템 구현 완료

### 🔥 **완벽한 API 엔드포인트 매핑**

#### **4.1 사용자 온보딩 및 인증**
```
OAuth 로그인 → JWT 토큰 발급 → 신규 가입자 1000포인트 보너스
```
**API 엔드포인트:**
- `GET /auth/oauth/{provider}/authorize` - OAuth 인증 시작
- `GET /auth/oauth/{provider}/callback` - OAuth 콜백 처리  
- `POST /auth/token/refresh` - JWT 토큰 갱신
- `POST /auth/logout` - 로그아웃

#### **4.2 일일 예측 참여**
```
세션 상태 확인 → 유니버스 조회 → 예측 슬롯 확인 → 예측 제출
```
**API 엔드포인트:**
- `GET /session/today` - 현재 세션 상태 확인
- `GET /session/can-predict` - 예측 가능 여부 체크
- `GET /universe/today` - 오늘의 종목 100개 조회
- `POST /predictions/{symbol}` - 예측 제출 (상승/하락)
- `PUT /predictions/{symbol}` - 예측 수정
- `DELETE /predictions/{symbol}` - 예측 취소

#### **4.3 광고 시청 및 슬롯 증가**
```
슬롯 소진 → 광고 시청 → 추가 슬롯 1개 획득
```
**API 엔드포인트:**
- `GET /ads/available-slots` - 사용 가능한 슬롯 정보
- `POST /ads/watch-complete` - 광고 시청 완료 처리
- `POST /ads/unlock-slot` - 쿨다운을 통한 슬롯 해제
- `GET /ads/history` - 광고 해제 히스토리

#### **4.4 정산 및 보상 시스템**
```
23:59 예측 마감 → 06:00 EOD 수집 → 정산 실행 → 50포인트 지급
```
**API 엔드포인트:**
- `POST /admin/settlement/settle-day/{trading_day}` - 자동 정산 실행
- `GET /admin/settlement/summary/{trading_day}` - 정산 요약
- `POST /admin/settlement/manual-settle` - 수동 정산
- `GET /prices/eod/{symbol}/{trading_day}` - EOD 가격 조회
- `GET /prices/current/{symbol}` - 실시간 가격 조회

#### **4.5 포인트 및 리워드 경제**
```
포인트 조회 → 리워드 카탈로그 → 교환 요청 → 외부 벤더 발급
```
**API 엔드포인트:**
- `GET /users/me/points/balance` - 포인트 잔액 조회
- `GET /users/me/points/ledger` - 포인트 거래 내역
- `GET /rewards/catalog` - 리워드 카탈로그 조회
- `POST /rewards/redeem` - 포인트 교환 요청
- `GET /rewards/history` - 교환 내역 조회

#### **4.6 배치 및 자동화 시스템**
```
05:30 유니버스 생성 → 06:00 정산 → 23:59 세션 마감
```
**API 엔드포인트:**
- `POST /batch/universe/create` - 유니버스 생성 배치
- `POST /batch/session/start` - 세션 시작 배치  
- `POST /batch/session/end` - 세션 종료 배치
- `POST /batch/schedule/settlement` - 정산 스케줄링

----
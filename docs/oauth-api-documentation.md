# OAuth 로그인 API 문서

OX Universe 백엔드는 4가지 로그인 방식을 지원합니다:
- Google OAuth
- Kakao OAuth  
- Apple OAuth
- Magic Link (이메일 인증)

## 📋 목차
- [공통 응답 형식](#공통-응답-형식)
- [Google OAuth](#1-google-oauth)
- [Kakao OAuth](#2-kakao-oauth)
- [Apple OAuth](#3-apple-oauth)
- [Magic Link](#4-magic-link-이메일-인증)
- [토큰 관리](#5-토큰-관리)

---

## 공통 응답 형식

### 성공 응답
```json
{
  "success": true,
  "data": {
    "user_id": 123,
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "nickname": "사용자닉네임",
    "is_new_user": false
  },
  "error": null
}
```

### 에러 응답
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "OAUTH_PROVIDER_ERROR",
    "message": "Failed to exchange authorization code"
  }
}
```

### 에러 코드
| 코드 | 설명 |
|------|------|
| `OAUTH_PROVIDER_ERROR` | OAuth 제공자 통신 실패 |
| `USER_ALREADY_EXISTS` | 다른 제공자로 이미 가입된 이메일 |
| `UNAUTHORIZED` | 인증 실패 (토큰 만료, 잘못된 토큰 등) |
| `INTERNAL_ERROR` | 서버 내부 오류 |

---

## 1. Google OAuth

### 1.1 인증 시작 (리다이렉트)

**Endpoint**: `GET /api/v1/auth/oauth/google/authorize`

**Query Parameters**:
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `client_redirect` | string | ✅ | 로그인 완료 후 돌아갈 프론트엔드 URL |

**Request Example**:
```
GET /api/v1/auth/oauth/google/authorize?client_redirect=https://yourapp.com/auth/callback
```

**Response**: 
- `307 Temporary Redirect` → Google 로그인 페이지로 리다이렉트

### 1.2 콜백 처리 (자동)

사용자가 Google 로그인 완료 → 백엔드가 자동 처리 → 프론트엔드로 리다이렉트

**프론트엔드가 받는 URL**:
```
https://yourapp.com/auth/callback?token=eyJ...&user_id=123&nickname=홍길동&provider=google&is_new_user=false
```

**Query Parameters**:
| 파라미터 | 타입 | 설명 |
|---------|------|------|
| `token` | string | JWT 액세스 토큰 (이후 API 요청 시 사용) |
| `user_id` | integer | 사용자 ID |
| `nickname` | string | 사용자 닉네임 |
| `provider` | string | `google` |
| `is_new_user` | boolean | 신규 가입 여부 |

**에러 시 URL**:
```
https://yourapp.com/auth/callback?error=oauth_error&error_description=Failed+to+exchange+code&provider=google
```

---

## 2. Kakao OAuth

### 2.1 인증 시작

**Endpoint**: `GET /api/v1/auth/oauth/kakao/authorize`

**Query Parameters**:
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `client_redirect` | string | ✅ | 로그인 완료 후 돌아갈 프론트엔드 URL |

**Request Example**:
```
GET /api/v1/auth/oauth/kakao/authorize?client_redirect=https://yourapp.com/auth/callback
```

### 2.2 콜백 처리

Google과 동일한 방식으로 처리됩니다.

**성공 시 프론트엔드 리다이렉트**:
```
https://yourapp.com/auth/callback?token=eyJ...&user_id=123&nickname=김철수&provider=kakao&is_new_user=true
```

---

## 3. Apple OAuth

### 3.1 인증 시작

**Endpoint**: `GET /api/v1/auth/oauth/apple/authorize`

**Query Parameters**:
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `client_redirect` | string | ✅ | 로그인 완료 후 돌아갈 프론트엔드 URL |

**Request Example**:
```
GET /api/v1/auth/oauth/apple/authorize?client_redirect=https://yourapp.com/auth/callback
```

### 3.2 콜백 처리

Google/Kakao와 동일한 방식으로 처리됩니다.

**성공 시 프론트엔드 리다이렉트**:
```
https://yourapp.com/auth/callback?token=eyJ...&user_id=123&nickname=이영희&provider=apple&is_new_user=false
```

**⚠️ 주의사항**:
- Apple은 사용자 이름을 **최초 1회만** 제공합니다
- 프로필 이미지는 제공하지 않습니다

---

## 4. Magic Link (이메일 인증)

### 4.1 매직링크 발송

**Endpoint**: `POST /api/v1/auth/magic-link/send`

**Request Body**:
```json
{
  "email": "user@example.com"
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "message": "Magic link sent to your email"
  },
  "error": null
}
```

**이메일 내용**:
- 제목: "OX Universe 로그인 링크"
- 내용: 로그인 버튼 포함 (클릭 시 `MAGIC_LINK_BASE_URL?token=...`로 이동)
- 유효 시간: 15분

### 4.2 매직링크 검증

**Endpoint**: `GET /api/v1/auth/magic-link/verify`

**Query Parameters**:
| 파라미터 | 타입 | 필수 | 설명 |
|---------|------|------|------|
| `token` | string | ✅ | 이메일로 받은 토큰 |

**Request Example**:
```
GET /api/v1/auth/magic-link/verify?token=abc123def456...
```

**Response**:
```json
{
  "success": true,
  "data": {
    "user_id": 123,
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "nickname": "user123",
    "is_new_user": true
  },
  "error": null
}
```

**에러 케이스**:
- 만료된 토큰: `Invalid or expired magic link`
- 이미 사용된 토큰: `Invalid or expired magic link`
- 존재하지 않는 토큰: `Invalid or expired magic link`

---

## 5. 토큰 관리

### 5.1 토큰 갱신

**Endpoint**: `POST /api/v1/auth/token/refresh`

**Request Body**:
```json
{
  "current_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  },
  "error": null
}
```

### 5.2 로그아웃

**Endpoint**: `POST /api/v1/auth/logout`

**Request Body**:
```json
{
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

**Response**:
```json
{
  "success": true,
  "data": {
    "message": "Logout successful"
  },
  "error": null
}
```

---

## 6. 프론트엔드 구현 가이드

### 6.1 OAuth 로그인 플로우 (Google/Kakao/Apple)

```javascript
// 1. 로그인 버튼 클릭
function loginWithProvider(provider) {
  const clientRedirect = encodeURIComponent('https://yourapp.com/auth/callback');
  window.location.href = `https://api.yourapp.com/api/v1/auth/oauth/${provider}/authorize?client_redirect=${clientRedirect}`;
}

// 2. 콜백 페이지에서 토큰 받기 (/auth/callback)
function handleAuthCallback() {
  const params = new URLSearchParams(window.location.search);
  
  // 에러 체크
  if (params.get('error')) {
    console.error('Login failed:', params.get('error_description'));
    return;
  }
  
  // 성공 - 토큰 저장
  const token = params.get('token');
  const userId = params.get('user_id');
  const nickname = params.get('nickname');
  const isNewUser = params.get('is_new_user') === 'true';
  
  localStorage.setItem('access_token', token);
  localStorage.setItem('user_id', userId);
  
  // 신규 가입자면 온보딩, 기존 유저면 메인 페이지
  if (isNewUser) {
    window.location.href = '/onboarding';
  } else {
    window.location.href = '/dashboard';
  }
}
```

### 6.2 Magic Link 플로우

```javascript
// 1. 이메일 입력 → 매직링크 발송
async function sendMagicLink(email) {
  const response = await fetch('https://api.yourapp.com/api/v1/auth/magic-link/send', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email })
  });
  
  const result = await response.json();
  if (result.success) {
    alert('이메일을 확인해주세요!');
  }
}

// 2. 이메일 링크 클릭 → 검증 페이지 (/verify?token=...)
async function verifyMagicLink() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get('token');
  
  const response = await fetch(
    `https://api.yourapp.com/api/v1/auth/magic-link/verify?token=${token}`
  );
  
  const result = await response.json();
  if (result.success) {
    localStorage.setItem('access_token', result.data.token);
    localStorage.setItem('user_id', result.data.user_id);
    window.location.href = '/dashboard';
  } else {
    alert('로그인 링크가 만료되었습니다.');
  }
}
```

### 6.3 인증된 API 요청

```javascript
// JWT 토큰을 헤더에 포함
async function fetchUserData() {
  const token = localStorage.getItem('access_token');
  
  const response = await fetch('https://api.yourapp.com/api/v1/user/me', {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });
  
  return response.json();
}
```

### 6.4 토큰 갱신

```javascript
async function refreshToken() {
  const currentToken = localStorage.getItem('access_token');
  
  const response = await fetch('https://api.yourapp.com/api/v1/auth/token/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_token: currentToken })
  });
  
  const result = await response.json();
  if (result.success) {
    localStorage.setItem('access_token', result.data.access_token);
  }
}
```

---

## 7. 환경별 URL

### Production
```
Base URL: https://api.oxuniverse.com/api/v1
```

### Development
```
Base URL: http://localhost:8000/api/v1
```

---

## 8. 테스트 계정

### Google
- 테스트 계정: (프로덕션 배포 전 Google OAuth 승인 필요)

### Kakao
- 테스트 계정: (Kakao Developers에서 테스트 유저 등록)

### Apple
- 테스트 계정: (Apple Developer에서 Sandbox 테스트)

### Magic Link
- 아무 이메일이나 사용 가능 (AWS SES 설정 필요)

---

## 9. FAQ

### Q1. 토큰 만료 시간은?
- **1440분 (24시간)**

### Q2. 같은 이메일로 다른 제공자 로그인 가능?
- **불가능**. 이미 Google로 가입한 이메일은 Kakao/Apple로 로그인 불가
- 에러: `USER_ALREADY_EXISTS`

### Q3. Magic Link는 몇 번 사용 가능?
- **1회만 사용 가능**. 사용 후 자동 삭제됨

### Q4. 신규 가입 시 보너스 포인트는?
- **1000 포인트** 자동 지급 (`SIGNUP_BONUS_POINTS`)

### Q5. 닉네임 중복 처리는?
- 자동으로 `_{숫자}` 추가 (예: `홍길동_1`, `홍길동_2`)

---

## 10. 보안 고려사항

### ✅ HTTPS 필수
- 프로덕션 환경에서는 반드시 HTTPS 사용

### ✅ CSRF 보호
- OAuth state 파라미터로 CSRF 방지

### ✅ 토큰 저장
- `localStorage` 또는 `sessionStorage` 사용
- ⚠️ `document.cookie`에 저장 시 `httpOnly` 플래그 설정 불가하므로 XSS 위험

### ✅ 토큰 전송
- API 요청 시 `Authorization: Bearer {token}` 헤더 사용
- URL 파라미터로 토큰 전송 금지

---

## 11. 문의

백엔드 API 관련 문의:
- Slack: #backend-api
- Email: backend-team@oxuniverse.com

# OAuth 로그인 설정 가이드 (백엔드)

## 📋 필수 패키지 설치

Apple OAuth를 위해 추가 패키지 설치 필요:

```bash
pip install PyJWT cryptography
```

또는 `requirements.txt`에 추가:
```txt
PyJWT==2.8.0
cryptography==41.0.7
```

---

## 🔧 환경 변수 설정

### `.env` 파일 설정

```bash
# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret

# Kakao OAuth
KAKAO_CLIENT_ID=your_kakao_rest_api_key
KAKAO_CLIENT_SECRET=your_kakao_client_secret

# Apple OAuth
APPLE_CLIENT_ID=com.yourcompany.yourapp
APPLE_TEAM_ID=YOUR_TEAM_ID
APPLE_KEY_ID=YOUR_KEY_ID
APPLE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\nMIGTA...your_private_key...\n-----END PRIVATE KEY-----

# OAuth 공통
OAUTH_STATE_EXPIRE_MINUTES=10

# Magic Link
MAGIC_LINK_EXPIRE_MINUTES=15
MAGIC_LINK_BASE_URL=https://yourapp.com/auth/verify
SES_FROM_EMAIL=noreply@yourdomain.com

# AWS SES (Magic Link용)
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
```

---

## 1. Google OAuth 설정

### 1.1 Google Cloud Console 설정

1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 프로젝트 생성 또는 선택
3. **API 및 서비스** → **사용자 인증 정보**
4. **+ 사용자 인증 정보 만들기** → **OAuth 클라이언트 ID**
5. 애플리케이션 유형: **웹 애플리케이션**
6. 승인된 리디렉션 URI 추가:
   ```
   https://api.yourdomain.com/api/v1/auth/oauth/google/callback
   http://localhost:8000/api/v1/auth/oauth/google/callback (개발용)
   ```

### 1.2 환경 변수 설정

```bash
GOOGLE_CLIENT_ID=123456789-abcdefg.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-abc123def456
```

---

## 2. Kakao OAuth 설정

### 2.1 Kakao Developers 설정

1. [Kakao Developers](https://developers.kakao.com/) 접속
2. 애플리케이션 추가
3. **앱 설정** → **플랫폼** → **Web 플랫폼 등록**
   - 사이트 도메인: `https://yourdomain.com`
4. **제품 설정** → **카카오 로그인** 활성화
5. **Redirect URI 등록**:
   ```
   https://api.yourdomain.com/api/v1/auth/oauth/kakao/callback
   http://localhost:8000/api/v1/auth/oauth/kakao/callback (개발용)
   ```
6. **동의 항목** 설정:
   - 이메일 (필수)
   - 닉네임 (선택)
   - 프로필 이미지 (선택)
7. **앱 키** 복사:
   - REST API 키 → `KAKAO_CLIENT_ID`
   - 보안 → Client Secret 발급 → `KAKAO_CLIENT_SECRET`

### 2.2 환경 변수 설정

```bash
KAKAO_CLIENT_ID=your_rest_api_key
KAKAO_CLIENT_SECRET=your_client_secret
```

---

## 3. Apple OAuth 설정

### 3.1 Apple Developer 설정

#### Step 1: App ID 생성
1. [Apple Developer](https://developer.apple.com/account/) 접속
2. **Certificates, Identifiers & Profiles**
3. **Identifiers** → **+** 버튼
4. **App IDs** 선택 → Continue
5. **App** 선택 → Continue
6. Bundle ID 입력 (예: `com.yourcompany.yourapp`)
7. **Sign in with Apple** 체크 → Continue → Register

#### Step 2: Service ID 생성
1. **Identifiers** → **+** 버튼
2. **Services IDs** 선택 → Continue
3. Identifier 입력 (예: `com.yourcompany.yourapp.service`)
4. **Sign in with Apple** 체크 → Configure
5. **Primary App ID** 선택
6. **Domains and Subdomains** 추가:
   ```
   api.yourdomain.com
   localhost (개발용)
   ```
7. **Return URLs** 추가:
   ```
   https://api.yourdomain.com/api/v1/auth/oauth/apple/callback
   http://localhost:8000/api/v1/auth/oauth/apple/callback (개발용)
   ```

#### Step 3: Private Key 생성
1. **Keys** → **+** 버튼
2. Key Name 입력 (예: `AppleSignInKey`)
3. **Sign in with Apple** 체크 → Configure
4. **Primary App ID** 선택 → Save
5. Continue → Register
6. **Download** 클릭 → `.p8` 파일 다운로드
7. **Key ID** 복사 (나중에 필요)

#### Step 4: Team ID 확인
1. 우측 상단 계정 메뉴 → **Membership**
2. **Team ID** 복사

### 3.2 Private Key 변환

`.p8` 파일을 환경 변수용 문자열로 변환:

```bash
# macOS/Linux
cat AuthKey_ABCD123456.p8 | sed 's/$/\\n/g' | tr -d '\n'

# 결과 예시:
-----BEGIN PRIVATE KEY-----\nMIGTAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBHkwdwIBAQQg...\n-----END PRIVATE KEY-----\n
```

### 3.3 환경 변수 설정

```bash
APPLE_CLIENT_ID=com.yourcompany.yourapp.service
APPLE_TEAM_ID=ABCD123456
APPLE_KEY_ID=ABCD123456
APPLE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\nMIGTA...\n-----END PRIVATE KEY-----
```

⚠️ **주의**: Private Key는 절대 Git에 커밋하지 마세요!

---

## 4. Magic Link (AWS SES) 설정

### 4.1 AWS SES 설정

#### Step 1: 이메일 주소 인증
1. [AWS SES Console](https://console.aws.amazon.com/ses/) 접속
2. **Verified identities** → **Create identity**
3. **Email address** 선택
4. 발신 이메일 입력 (예: `noreply@yourdomain.com`)
5. 이메일 확인 링크 클릭

#### Step 2: 도메인 인증 (선택사항, 프로덕션 권장)
1. **Verified identities** → **Create identity**
2. **Domain** 선택
3. 도메인 입력 (예: `yourdomain.com`)
4. DNS 레코드 추가 (CNAME, MX, TXT)

#### Step 3: Sandbox 벗어나기 (프로덕션 필수)
- Sandbox 모드: 인증된 이메일로만 발송 가능
- Production 모드: 모든 이메일로 발송 가능
- **Request production access** 클릭 → 신청

#### Step 4: IAM 사용자 생성
1. [IAM Console](https://console.aws.amazon.com/iam/) 접속
2. **Users** → **Add users**
3. User name 입력 → **Access key** 선택
4. **Permissions** → **Attach policies directly**
5. **AmazonSESFullAccess** 선택
6. **Access key ID** / **Secret access key** 복사

### 4.2 환경 변수 설정

```bash
# AWS 자격 증명
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

# Magic Link 설정
MAGIC_LINK_EXPIRE_MINUTES=15
MAGIC_LINK_BASE_URL=https://yourapp.com/auth/verify
SES_FROM_EMAIL=noreply@yourdomain.com
```

### 4.3 이메일 템플릿 테스트

```bash
# Python으로 테스트 발송
python -c "
import boto3
ses = boto3.client('ses', region_name='ap-northeast-2')
ses.send_email(
    Source='noreply@yourdomain.com',
    Destination={'ToAddresses': ['test@example.com']},
    Message={
        'Subject': {'Data': 'Test Email'},
        'Body': {'Html': {'Data': '<h1>Hello!</h1>'}}
    }
)
print('Email sent!')
"
```

---

## 5. 데이터베이스 테이블 확인

기존 테이블 활용 (추가 마이그레이션 불필요):

### `crypto.oauth_states` 테이블
```sql
-- OAuth state 및 Magic Link 토큰 저장
CREATE TABLE crypto.oauth_states (
    state VARCHAR PRIMARY KEY,
    redirect_uri VARCHAR NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);
```

이 테이블이 이미 존재하면 추가 작업 불필요합니다.

---

## 6. 배포 전 체크리스트

### ✅ Google OAuth
- [ ] Google Cloud Console에서 Redirect URI 등록
- [ ] `.env`에 `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` 설정
- [ ] HTTPS 활성화 (프로덕션)

### ✅ Kakao OAuth
- [ ] Kakao Developers에서 Redirect URI 등록
- [ ] `.env`에 `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET` 설정
- [ ] 동의 항목 설정 (이메일 필수)
- [ ] HTTPS 활성화 (프로덕션)

### ✅ Apple OAuth
- [ ] Apple Developer에서 Service ID, Key 생성
- [ ] `.env`에 `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` 설정
- [ ] Private Key 안전하게 보관
- [ ] HTTPS 활성화 (필수)

### ✅ Magic Link
- [ ] AWS SES에서 이메일/도메인 인증
- [ ] Production access 승인 (프로덕션)
- [ ] `.env`에 AWS 자격 증명 설정
- [ ] 이메일 템플릿 테스트

### ✅ 공통
- [ ] `oauth_states` 테이블 존재 확인
- [ ] 환경 변수 `.env` 파일에 모두 설정
- [ ] `.env` 파일 `.gitignore`에 추가
- [ ] HTTPS 인증서 설정 (Let's Encrypt 권장)
- [ ] CORS 설정 확인

---

## 7. 개발 환경 테스트

### 7.1 로컬 서버 실행

```bash
# 패키지 설치
pip install -r requirements.txt

# 환경 변수 로드
source .env  # Linux/macOS
# 또는
set -a; source .env; set +a

# 서버 실행
uvicorn myapi.main:app --host 0.0.0.0 --port 8000 --reload
```

### 7.2 OAuth 플로우 테스트

```bash
# 브라우저에서 접속
http://localhost:8000/api/v1/auth/oauth/google/authorize?client_redirect=http://localhost:3000/callback
```

### 7.3 Magic Link 테스트

```bash
# curl로 테스트
curl -X POST http://localhost:8000/api/v1/auth/magic-link/send \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com"}'
```

---

## 8. 프로덕션 배포 가이드

### 8.1 환경 변수 설정

**Docker Compose 사용 시**:
```yaml
# docker-compose.yml
services:
  api:
    environment:
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET}
      - KAKAO_CLIENT_ID=${KAKAO_CLIENT_ID}
      - KAKAO_CLIENT_SECRET=${KAKAO_CLIENT_SECRET}
      - APPLE_CLIENT_ID=${APPLE_CLIENT_ID}
      - APPLE_TEAM_ID=${APPLE_TEAM_ID}
      - APPLE_KEY_ID=${APPLE_KEY_ID}
      - APPLE_PRIVATE_KEY=${APPLE_PRIVATE_KEY}
      - MAGIC_LINK_BASE_URL=${MAGIC_LINK_BASE_URL}
      - SES_FROM_EMAIL=${SES_FROM_EMAIL}
```

**AWS Lambda 사용 시**:
- Lambda 환경 변수 또는 AWS Secrets Manager 사용

### 8.2 HTTPS 설정

**Nginx 리버스 프록시**:
```nginx
server {
    listen 443 ssl;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 9. 트러블슈팅

### 문제: Google OAuth 리다이렉트 에러
```
Error: redirect_uri_mismatch
```
**해결**: Google Cloud Console의 Redirect URI와 백엔드 URL이 정확히 일치하는지 확인

### 문제: Kakao OAuth 이메일 없음
```
Error: Email not provided by OAuth provider
```
**해결**: Kakao Developers에서 이메일 동의 항목을 "필수"로 설정

### 문제: Apple OAuth 인증 실패
```
Error: Failed to exchange authorization code
```
**해결**:
- `APPLE_PRIVATE_KEY` 형식 확인 (`\n` 이스케이프 포함)
- Team ID, Key ID 정확성 확인
- Private Key가 만료되지 않았는지 확인

### 문제: Magic Link 이메일 미발송
```
Error: MessageRejected
```
**해결**:
- AWS SES Sandbox 모드인 경우 수신자 이메일 인증 필요
- Production access 신청 완료 확인
- IAM 권한 확인 (`ses:SendEmail`)

### 문제: CORS 에러
```
Access to fetch at '...' from origin '...' has been blocked by CORS policy
```
**해결**: `myapi/main.py`에서 CORS 설정 확인
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://yourapp.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 10. 보안 모범 사례

### ✅ 환경 변수 관리
- `.env` 파일 절대 Git에 커밋 금지
- 프로덕션은 AWS Secrets Manager / HashiCorp Vault 사용
- Private Key는 KMS로 암호화

### ✅ HTTPS 강제
- HTTP → HTTPS 리다이렉트 설정
- HSTS 헤더 추가

### ✅ Rate Limiting
- Magic Link 발송: IP당 5회/시간 제한
- OAuth 콜백: 동일 state 1회만 허용

### ✅ 로그 모니터링
- OAuth 실패 로그 수집
- 비정상적인 로그인 시도 감지

---

## 11. 참고 문서

- [Google OAuth 2.0](https://developers.google.com/identity/protocols/oauth2)
- [Kakao Login](https://developers.kakao.com/docs/latest/ko/kakaologin/rest-api)
- [Apple Sign In](https://developer.apple.com/sign-in-with-apple/)
- [AWS SES](https://docs.aws.amazon.com/ses/)
- [FastAPI Security](https://fastapi.tiangolo.com/tutorial/security/)

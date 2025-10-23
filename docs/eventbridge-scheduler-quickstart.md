# EventBridge Scheduler Quick Start 🚀

다른 프로젝트에서 5단계로 빠르게 EventBridge Scheduler를 구현하는 가이드입니다.

---

## ⚡ 5단계 구현

### Step 1: AWS Lambda 함수 배포 (API_CALL_LAMBDA)

#### lambda_function.py
```python
import json
import urllib3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)
http = urllib3.PoolManager()

def lambda_handler(event, context):
    try:
        logger.info(f"Event: {json.dumps(event)}")
        
        target_url = event["target_url"]
        method = event.get("method", "POST")
        headers = event.get("headers", {})
        body = event.get("body", {})
        
        headers.setdefault("Content-Type", "application/json")
        
        response = http.request(
            method=method,
            url=target_url,
            headers=headers,
            body=json.dumps(body) if body else None,
            timeout=30.0
        )
        
        logger.info(f"API response: {response.status}")
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "api_status": response.status
            })
        }
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
```

#### 배포 명령어
```bash
# 1. Lambda 함수 패키징
zip lambda_function.zip lambda_function.py

# 2. Lambda 생성
aws lambda create-function \
    --function-name API_CALL_LAMBDA \
    --runtime python3.11 \
    --role arn:aws:iam::YOUR_ACCOUNT_ID:role/LambdaExecutionRole \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://lambda_function.zip \
    --timeout 30

# 3. Lambda ARN 확인
aws lambda get-function --function-name API_CALL_LAMBDA
```

---

### Step 2: IAM Role 생성

#### EventBridge Scheduler Role

```bash
# 1. Trust Policy 파일 생성
cat > scheduler-trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Service": "scheduler.amazonaws.com"},
    "Action": "sts:AssumeRole"
  }]
}
EOF

# 2. Role 생성
aws iam create-role \
    --role-name EventBridgeSchedulerRole \
    --assume-role-policy-document file://scheduler-trust-policy.json

# 3. Lambda 호출 권한 부여
cat > scheduler-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["lambda:InvokeFunction"],
    "Resource": "arn:aws:lambda:ap-northeast-2:YOUR_ACCOUNT_ID:function:API_CALL_LAMBDA"
  }]
}
EOF

aws iam put-role-policy \
    --role-name EventBridgeSchedulerRole \
    --policy-name LambdaInvokePolicy \
    --policy-document file://scheduler-policy.json

# 4. Role ARN 확인 (나중에 사용)
aws iam get-role --role-name EventBridgeSchedulerRole --query 'Role.Arn'
```

---

### Step 3: 환경 변수 설정

#### .env
```bash
# AWS 설정
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# EventBridge Scheduler
SCHEDULER_TARGET_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/EventBridgeSchedulerRole
SCHEDULER_GROUP_NAME=default

# API 설정
API_BASE_URL=https://your-api.com
INTERNAL_AUTH_TOKEN=your_secret_token_here
```

#### config.py
```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    AWS_REGION: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    SCHEDULER_TARGET_ROLE_ARN: str
    SCHEDULER_GROUP_NAME: str = "default"
    
    API_BASE_URL: str
    INTERNAL_AUTH_TOKEN: str
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

### Step 4: AWS Service 메서드 추가

#### services/aws_service.py
```python
import boto3
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Literal
from fastapi import HTTPException
from your_app.config import settings

logger = logging.getLogger(__name__)

class AwsService:
    def __init__(self, config=settings):
        self.config = config
        self.region = config.AWS_REGION
        
    def _client(self, service: str):
        """AWS 클라이언트 생성"""
        return boto3.client(
            service,
            region_name=self.region,
            aws_access_key_id=self.config.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=self.config.AWS_SECRET_ACCESS_KEY,
        )
    
    def _get_lambda_arn(self, function_name: str) -> str:
        """Lambda 함수 ARN 조회"""
        client = self._client("lambda")
        try:
            resp = client.get_function(FunctionName=function_name)
            return resp["Configuration"]["FunctionArn"]
        except Exception as e:
            raise HTTPException(500, f"Lambda ARN 조회 실패: {str(e)}")
    
    def generate_api_call_payload(
        self,
        target_url: str,
        method: str = "POST",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """API_CALL_LAMBDA용 페이로드 생성"""
        return {
            "target_url": target_url,
            "method": method.upper(),
            "headers": headers or {},
            "body": body or {},
        }
    
    def schedule_one_time_task(
        self,
        delay_minutes: int,
        callback_url: str,
        payload: Dict[str, Any],
        task_name: str = "task",
    ) -> str:
        """
        일회성 스케줄 생성
        
        Returns:
            Schedule ARN
        """
        scheduler = self._client("scheduler")
        
        # 실행 시간 계산 (UTC)
        scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        rounded = scheduled_time.replace(second=0, microsecond=0)
        if scheduled_time.second > 0:
            rounded += timedelta(minutes=1)
        
        at_expr = f"at({rounded.strftime('%Y-%m-%dT%H:%M:%S')})"
        
        # Lambda ARN 조회
        lambda_arn = self._get_lambda_arn("API_CALL_LAMBDA")
        
        # 스케줄 이름 생성
        schedule_name = f"{task_name}-{uuid.uuid4().hex[:8]}"
        
        # API 호출 페이로드 생성
        api_payload = self.generate_api_call_payload(
            target_url=callback_url,
            method="POST",
            headers={"Authorization": f"Bearer {self.config.INTERNAL_AUTH_TOKEN}"},
            body=payload,
        )
        
        try:
            resp = scheduler.create_schedule(
                Name=schedule_name,
                GroupName=self.config.SCHEDULER_GROUP_NAME,
                ScheduleExpression=at_expr,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn,
                    "RoleArn": self.config.SCHEDULER_TARGET_ROLE_ARN,
                    "Input": json.dumps(api_payload),
                    "RetryPolicy": {
                        "MaximumRetryAttempts": 2,
                        "MaximumEventAgeInSeconds": 3600,
                    },
                },
                State="ENABLED",
            )
            
            schedule_arn = resp.get("ScheduleArn", "")
            logger.info(f"Created schedule: {schedule_name}, ARN: {schedule_arn}")
            return schedule_arn
            
        except Exception as e:
            logger.error(f"Failed to create schedule: {str(e)}")
            raise HTTPException(500, f"스케줄 생성 실패: {str(e)}")
    
    def cancel_schedule(self, schedule_arn: str) -> bool:
        """스케줄 취소"""
        try:
            if ":schedule/" not in schedule_arn:
                return False
            
            parts = schedule_arn.split(":schedule/")[-1].split("/")
            if len(parts) != 2:
                return False
            
            group, name = parts[0], parts[1]
            
            scheduler = self._client("scheduler")
            scheduler.delete_schedule(Name=name, GroupName=group)
            
            logger.info(f"Deleted schedule: {group}/{name}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cancel schedule: {str(e)}")
            return False
```

---

### Step 5: 라우터 및 서비스 구현

#### routers/task_router.py
```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])

# 의존성 주입 (프로젝트에 맞게 수정)
from your_app.services.aws_service import AwsService
from your_app.config import settings

def get_aws_service():
    return AwsService(settings)


class TaskScheduleRequest(BaseModel):
    """스케줄 요청"""
    delay_minutes: int
    data: Dict[str, Any]


class TaskCallbackRequest(BaseModel):
    """콜백 요청"""
    task_id: int
    user_id: int
    data: Dict[str, Any]


@router.post("/schedule")
async def schedule_task(
    request: TaskScheduleRequest,
    aws_service: AwsService = Depends(get_aws_service),
):
    """
    작업 스케줄링
    
    예시:
    {
      "delay_minutes": 30,
      "data": {
        "task_id": 123,
        "user_id": 456,
        "action": "send_notification"
      }
    }
    """
    try:
        # 콜백 URL 생성
        callback_url = f"{settings.API_BASE_URL}/api/v1/tasks/callback"
        
        # 스케줄 생성
        schedule_arn = aws_service.schedule_one_time_task(
            delay_minutes=request.delay_minutes,
            callback_url=callback_url,
            payload=request.data,
            task_name="task",
        )
        
        return {
            "success": True,
            "message": "Task scheduled successfully",
            "schedule_arn": schedule_arn,
            "scheduled_in_minutes": request.delay_minutes,
        }
        
    except Exception as e:
        logger.error(f"Failed to schedule task: {str(e)}")
        raise HTTPException(500, f"스케줄링 실패: {str(e)}")


@router.post("/callback")
async def handle_task_callback(request: TaskCallbackRequest):
    """
    Lambda에서 호출되는 콜백 엔드포인트
    
    이 엔드포인트는 EventBridge Scheduler → Lambda → 여기로 호출됩니다.
    """
    try:
        logger.info(f"Task callback received: {request.model_dump()}")
        
        # 여기에 실제 비즈니스 로직 구현
        # 예: DB 업데이트, 알림 발송, 외부 API 호출 등
        
        return {
            "success": True,
            "message": "Task processed successfully",
            "task_id": request.task_id,
        }
        
    except Exception as e:
        logger.error(f"Failed to process task: {str(e)}")
        raise HTTPException(500, f"작업 처리 실패: {str(e)}")
```

---

## 🧪 테스트

### 1. API 테스트 (cURL)

```bash
# 스케줄 생성 (30분 후 실행)
curl -X POST "https://your-api.com/api/v1/tasks/schedule" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "delay_minutes": 1,
    "data": {
      "task_id": 123,
      "user_id": 456,
      "action": "test_notification"
    }
  }'

# 응답:
# {
#   "success": true,
#   "schedule_arn": "arn:aws:scheduler:...:schedule/default/task-abc12345",
#   "scheduled_in_minutes": 1
# }
```

### 2. Lambda 로그 확인

```bash
# CloudWatch Logs 확인
aws logs tail /aws/lambda/API_CALL_LAMBDA --follow
```

### 3. 콜백 엔드포인트 직접 테스트

```bash
# 콜백 엔드포인트 직접 호출
curl -X POST "https://your-api.com/api/v1/tasks/callback" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_INTERNAL_TOKEN" \
  -d '{
    "task_id": 123,
    "user_id": 456,
    "data": {"action": "test"}
  }'
```

---

## 🎯 실제 사용 예시

### 예시 1: 결제 만료 알림

```python
# 30분 후 결제 만료 알림
await aws_service.schedule_one_time_task(
    delay_minutes=30,
    callback_url=f"{settings.API_BASE_URL}/api/v1/payments/expiration-reminder",
    payload={
        "payment_id": 12345,
        "user_id": 789,
        "amount": 9900
    },
    task_name="payment-reminder"
)
```

### 예시 2: 이메일 발송 지연

```python
# 1시간 후 환영 이메일 발송
await aws_service.schedule_one_time_task(
    delay_minutes=60,
    callback_url=f"{settings.API_BASE_URL}/api/v1/emails/send-welcome",
    payload={
        "user_id": 456,
        "email": "user@example.com",
        "template": "welcome"
    },
    task_name="email-welcome"
)
```

### 예시 3: 임시 데이터 정리

```python
# 24시간 후 임시 파일 삭제
await aws_service.schedule_one_time_task(
    delay_minutes=1440,  # 24시간
    callback_url=f"{settings.API_BASE_URL}/api/v1/cleanup/temp-files",
    payload={
        "file_id": "temp-abc123",
        "bucket": "temp-storage"
    },
    task_name="cleanup-temp"
)
```

---

## 🔍 트러블슈팅

### 문제 1: Lambda 호출 실패
```
Error: Lambda invoke failed: AccessDeniedException
```

**해결책:**
- EventBridge Scheduler Role에 Lambda 호출 권한이 있는지 확인
- `SCHEDULER_TARGET_ROLE_ARN` 환경 변수가 올바른지 확인

### 문제 2: 콜백 엔드포인트 401 Unauthorized
```
API response: 401
```

**해결책:**
- `INTERNAL_AUTH_TOKEN` 설정 확인
- FastAPI 미들웨어에서 내부 토큰 인증 추가

```python
# middleware.py
@app.middleware("http")
async def internal_auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/v1/tasks/callback"):
        auth_header = request.headers.get("Authorization", "")
        expected = f"Bearer {settings.INTERNAL_AUTH_TOKEN}"
        if auth_header != expected:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
    return await call_next(request)
```

### 문제 3: Lambda Timeout
```
Task timed out after 30.00 seconds
```

**해결책:**
- Lambda timeout 설정 증가
- FastAPI 엔드포인트 응답 시간 최적화

```bash
aws lambda update-function-configuration \
    --function-name API_CALL_LAMBDA \
    --timeout 60
```

---

## 📚 다음 단계

완성했다면 다음을 고려하세요:

1. **DB 저장**: 스케줄된 작업을 DB에 저장하여 추적
2. **모니터링**: CloudWatch Alarms 설정
3. **재시도 로직**: 실패 시 재시도 메커니즘 추가
4. **반복 스케줄**: Cron 표현식으로 반복 작업 구현
5. **스케줄 조회**: 활성 스케줄 목록 조회 API 추가

자세한 내용은 `eventbridge-scheduler-template.md`를 참고하세요!

---

## ✅ 완료 체크리스트

- [ ] Lambda 함수(API_CALL_LAMBDA) 배포
- [ ] IAM Role (EventBridgeSchedulerRole) 생성
- [ ] 환경 변수 설정 (.env)
- [ ] AwsService 메서드 구현
- [ ] 라우터 구현 (/schedule, /callback)
- [ ] 테스트 실행
- [ ] CloudWatch Logs 확인

🎉 모두 체크했다면 완료입니다!



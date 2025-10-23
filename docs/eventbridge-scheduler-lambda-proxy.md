# EventBridge Scheduler + Lambda Proxy 통합 가이드 🚀

EventBridge Scheduler로 Lambda를 호출하고, Lambda가 **API Gateway Proxy 형식**으로 FastAPI(Mangum)를 직접 실행하는 패턴입니다.

> **차이점**: HTTP 요청을 보내는 대신, Lambda가 FastAPI 애플리케이션을 직접 실행합니다.

---

## 🏗️ 아키텍처 비교

### (Lambda Proxy)
```
EventBridge Scheduler
    ↓
Lambda (FastAPI + Mangum)
    ↓ 직접 실행
FastAPI Handler
```

**장점:**
- 네트워크 호출 없음 (더 빠름)
- 인증 불필요 (Lambda 내부 실행)
- 비용 절감 (Lambda 실행만)
- 더 간단한 구조

---

## 📋 전체 플로우

```
1. FastAPI Service
   └─> schedule_task() 호출

2. AWS Service
   └─> generate_lambda_proxy_payload() - API Gateway 형식 생성
   └─> schedule_one_time_lambda_with_scheduler() - EventBridge Scheduler 생성

3. EventBridge Scheduler (지정 시간 대기)

4. Lambda 함수 실행
   └─> Mangum Handler
       └─> FastAPI Application
           └─> 라우터 엔드포인트 실행
```

---

## 🚀 구현 가이드 (DB 테이블 없이)

### Step 1: Lambda 함수 생성 (FastAPI + Mangum)

#### requirements.txt
```txt
fastapi==0.104.1
mangum==0.17.0
pydantic==2.5.0
```

#### lambda_handler.py
```python
"""
EventBridge Scheduler에서 호출되는 Lambda 함수
API Gateway Proxy 형식으로 FastAPI를 실행
"""
from fastapi import FastAPI, HTTPException
from mangum import Mangum
from pydantic import BaseModel
from typing import Dict, Any
import logging

# 로깅 설정
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# FastAPI 앱 생성
app = FastAPI(title="Scheduled Tasks Lambda")

# ========================================
# Pydantic 스키마
# ========================================

class TaskCallbackRequest(BaseModel):
    """콜백 요청 스키마"""
    task_id: str
    user_id: int
    action: str
    data: Dict[str, Any] = {}


class TaskCallbackResponse(BaseModel):
    """콜백 응답 스키마"""
    success: bool
    message: str
    task_id: str


# ========================================
# FastAPI 라우터
# ========================================

@app.get("/health")
def health_check():
    """헬스체크"""
    return {"status": "ok", "service": "scheduled-tasks-lambda"}


@app.post("/api/v1/tasks/callback", response_model=TaskCallbackResponse)
async def handle_task_callback(request: TaskCallbackRequest):
    """
    EventBridge Scheduler → Lambda → 이 엔드포인트
    
    스케줄된 작업이 실행될 때 호출됩니다.
    """
    try:
        logger.info(f"Task callback: {request.model_dump()}")
        
        # ========================================
        # 여기에 비즈니스 로직 작성
        # ========================================
        
        if request.action == "send_notification":
            # 알림 발송 로직
            logger.info(f"Sending notification to user {request.user_id}")
            # send_notification(request.user_id, request.data)
            
        elif request.action == "process_payment":
            # 결제 처리 로직
            logger.info(f"Processing payment for task {request.task_id}")
            # process_payment(request.data)
            
        elif request.action == "cleanup":
            # 정리 작업 로직
            logger.info(f"Cleaning up resources for {request.task_id}")
            # cleanup_resources(request.data)
            
        else:
            logger.warning(f"Unknown action: {request.action}")
        
        # ========================================
        # 응답 반환
        # ========================================
        
        return TaskCallbackResponse(
            success=True,
            message=f"Task {request.task_id} processed successfully",
            task_id=request.task_id
        )
        
    except Exception as e:
        logger.error(f"Task callback failed: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Task processing failed: {str(e)}"
        )


# ========================================
# Mangum Handler (Lambda 진입점)
# ========================================

# API Gateway Proxy 형식을 FastAPI로 변환
handler = Mangum(app, lifespan="off")


def lambda_handler(event, context):
    """Lambda 진입점"""
    logger.info(f"Received event: {event}")
    
    # Mangum이 API Gateway Proxy 형식을 FastAPI로 변환
    return handler(event, context)
```

#### Lambda 배포

```bash
# 1. 의존성 패키징
mkdir package
pip install -r requirements.txt -t package/
cd package
zip -r ../lambda_package.zip .
cd ..

# 2. Lambda 코드 추가
zip -g lambda_package.zip lambda_handler.py

# 3. Lambda 생성
aws lambda create-function \
    --function-name FastAPI_Scheduled_Tasks \
    --runtime python3.11 \
    --role arn:aws:iam::YOUR_ACCOUNT_ID:role/LambdaExecutionRole \
    --handler lambda_handler.lambda_handler \
    --zip-file fileb://lambda_package.zip \
    --timeout 60 \
    --memory-size 512

# 4. Lambda ARN 확인
aws lambda get-function --function-name FastAPI_Scheduled_Tasks \
    --query 'Configuration.FunctionArn'
```

---

### Step 2: FastAPI Service (스케줄러)

메인 FastAPI 애플리케이션에서 스케줄을 생성하는 부분입니다.

#### services/aws_service.py

```python
import boto3
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Literal
from fastapi import HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LambdaProxyMessage(BaseModel):
    """API Gateway Proxy 형식 메시지"""
    body: Optional[str | Dict[str, Any]]
    resource: str
    path: str
    httpMethod: Literal["GET", "POST", "PUT", "DELETE"]
    isBase64Encoded: bool
    pathParameters: Dict[str, Any]
    queryStringParameters: Dict[str, Any]
    headers: Dict[str, Any]
    requestContext: Dict[str, Any]


class AwsService:
    def __init__(self, aws_region: str, access_key: str = None, secret_key: str = None):
        self.region = aws_region
        self.access_key = access_key
        self.secret_key = secret_key
        
    def _client(self, service: str):
        """AWS 클라이언트 생성"""
        if self.access_key and self.secret_key:
            return boto3.client(
                service,
                region_name=self.region,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
            )
        return boto3.client(service, region_name=self.region)
    
    def generate_lambda_proxy_payload(
        self,
        path: str,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        body: Optional[Dict[str, Any]] = None,
        query_params: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        API Gateway Proxy 형식 페이로드 생성
        
        이 형식은 Mangum이 FastAPI로 변환할 수 있는 표준 형식입니다.
        
        Args:
            path: API 경로 (예: "api/v1/tasks/callback")
            method: HTTP 메서드
            body: Request body (JSON)
            query_params: Query string parameters
            headers: HTTP headers
            
        Returns:
            API Gateway Proxy 형식의 dict
        """
        from urllib.parse import urlsplit, parse_qs
        
        # Path에서 query string 분리
        supplied_qsp = query_params or {}
        split = urlsplit(path)
        clean_path = split.path.lstrip("/") if split.path else path.lstrip("/")
        
        # Query string 파싱 및 병합
        parsed_qs = {}
        if split.query:
            parsed_qs = {
                k: v[0] if isinstance(v, list) and v else v 
                for k, v in parse_qs(split.query).items()
            }
        qsp = {**parsed_qs, **supplied_qsp} if parsed_qs or supplied_qsp else {}
        
        # Body 처리
        body_value = None if method == "GET" else body
        
        # Headers 기본값
        default_headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        final_headers = {**default_headers, **(headers or {})}
        
        # API Gateway Proxy 형식 생성
        proxy_message = LambdaProxyMessage(
            body=body_value,
            resource="/{proxy+}",
            path=f"/{clean_path}",
            httpMethod=method,
            isBase64Encoded=False,
            pathParameters={"proxy": clean_path},
            queryStringParameters=qsp,
            headers=final_headers,
            requestContext={
                "path": f"/{clean_path}",
                "resourcePath": "/{proxy+}",
                "httpMethod": method,
                "requestId": f"req-{uuid.uuid4().hex[:8]}",
                "stage": "prod",
            },
        )
        
        return proxy_message.model_dump()
    
    def _get_lambda_arn(self, function_name: str) -> str:
        """Lambda 함수 ARN 조회"""
        client = self._client("lambda")
        try:
            resp = client.get_function(FunctionName=function_name)
            return resp["Configuration"]["FunctionArn"]
        except Exception as e:
            raise HTTPException(500, f"Lambda ARN 조회 실패: {str(e)}")
    
    def schedule_lambda_proxy_task(
        self,
        *,
        lambda_function_name: str,
        callback_path: str,
        callback_body: Dict[str, Any],
        delay_minutes: int,
        scheduler_role_arn: str,
        scheduler_group: str = "default",
        task_name_prefix: str = "task",
    ) -> str:
        """
        EventBridge Scheduler로 Lambda Proxy 작업 스케줄링
        
        Args:
            lambda_function_name: Lambda 함수 이름 (예: "FastAPI_Scheduled_Tasks")
            callback_path: FastAPI 경로 (예: "api/v1/tasks/callback")
            callback_body: Request body
            delay_minutes: 지연 시간 (분)
            scheduler_role_arn: EventBridge Scheduler IAM Role ARN
            scheduler_group: Scheduler 그룹 이름
            task_name_prefix: 작업 이름 접두사
            
        Returns:
            생성된 Schedule ARN
        """
        scheduler = self._client("scheduler")
        
        # 1. 실행 시간 계산 (UTC)
        scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        rounded = scheduled_time.replace(second=0, microsecond=0)
        if scheduled_time.second > 0 or scheduled_time.microsecond > 0:
            rounded += timedelta(minutes=1)
        
        at_expression = f"at({rounded.strftime('%Y-%m-%dT%H:%M:%S')})"
        
        # 2. Lambda ARN 조회
        lambda_arn = self._get_lambda_arn(lambda_function_name)
        
        # 3. API Gateway Proxy 페이로드 생성
        proxy_payload = self.generate_lambda_proxy_payload(
            path=callback_path,
            method="POST",
            body=callback_body,
        )
        
        # 4. 스케줄 이름 생성
        schedule_name = f"{task_name_prefix}-{uuid.uuid4().hex[:8]}"
        
        try:
            resp = scheduler.create_schedule(
                Name=schedule_name,
                GroupName=scheduler_group,
                ScheduleExpression=at_expression,
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={
                    "Arn": lambda_arn,
                    "RoleArn": scheduler_role_arn,
                    "Input": json.dumps(proxy_payload),
                    "RetryPolicy": {
                        "MaximumRetryAttempts": 2,
                        "MaximumEventAgeInSeconds": 3600,
                    },
                },
                State="ENABLED",
                Description=f"Scheduled task: {task_name_prefix}",
            )
            
            schedule_arn = resp.get("ScheduleArn", "")
            logger.info(
                f"Created Lambda Proxy schedule: {schedule_name}, "
                f"ARN: {schedule_arn}, "
                f"Lambda: {lambda_function_name}, "
                f"Path: {callback_path}"
            )
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

### Step 3: FastAPI 라우터 (스케줄 생성)

메인 애플리케이션에서 스케줄을 생성하는 라우터입니다.

#### routers/scheduler_router.py

```python
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scheduler", tags=["scheduler"])

# 의존성 주입 (프로젝트에 맞게 수정)
from your_app.services.aws_service import AwsService
from your_app.config import settings

def get_aws_service():
    return AwsService(
        aws_region=settings.AWS_REGION,
        access_key=settings.AWS_ACCESS_KEY_ID,
        secret_key=settings.AWS_SECRET_ACCESS_KEY,
    )


class ScheduleTaskRequest(BaseModel):
    """스케줄 생성 요청"""
    task_id: str = Field(..., description="작업 ID")
    user_id: int = Field(..., description="사용자 ID")
    action: str = Field(..., description="실행할 액션")
    delay_minutes: int = Field(..., ge=1, le=10080, description="지연 시간 (분)")
    data: Dict[str, Any] = Field(default_factory=dict, description="추가 데이터")


class ScheduleTaskResponse(BaseModel):
    """스케줄 생성 응답"""
    success: bool
    message: str
    schedule_arn: str
    task_id: str
    scheduled_in_minutes: int


@router.post("/schedule", response_model=ScheduleTaskResponse)
async def schedule_task(
    request: ScheduleTaskRequest,
    aws_service: AwsService = Depends(get_aws_service),
):
    """
    작업 스케줄링 (Lambda Proxy 방식)
    
    예시:
    ```json
    {
      "task_id": "task-123",
      "user_id": 456,
      "action": "send_notification",
      "delay_minutes": 30,
      "data": {
        "notification_type": "reminder",
        "message": "Your task is ready"
      }
    }
    ```
    
    이 API를 호출하면:
    1. EventBridge Scheduler가 생성됩니다
    2. 지정된 시간 후 Lambda 함수가 실행됩니다
    3. Lambda 내부의 FastAPI 엔드포인트가 호출됩니다
    """
    try:
        # Lambda Proxy 스케줄 생성
        schedule_arn = aws_service.schedule_lambda_proxy_task(
            lambda_function_name=settings.SCHEDULER_LAMBDA_FUNCTION_NAME,
            callback_path="api/v1/tasks/callback",
            callback_body={
                "task_id": request.task_id,
                "user_id": request.user_id,
                "action": request.action,
                "data": request.data,
            },
            delay_minutes=request.delay_minutes,
            scheduler_role_arn=settings.SCHEDULER_TARGET_ROLE_ARN,
            scheduler_group=settings.SCHEDULER_GROUP_NAME,
            task_name_prefix=f"task-{request.user_id}",
        )
        
        logger.info(
            f"Scheduled task: task_id={request.task_id}, "
            f"user_id={request.user_id}, "
            f"action={request.action}, "
            f"delay={request.delay_minutes}min"
        )
        
        return ScheduleTaskResponse(
            success=True,
            message="Task scheduled successfully",
            schedule_arn=schedule_arn,
            task_id=request.task_id,
            scheduled_in_minutes=request.delay_minutes,
        )
        
    except Exception as e:
        logger.error(f"Failed to schedule task: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"스케줄 생성 실패: {str(e)}"
        )


@router.delete("/schedule/{schedule_arn:path}")
async def cancel_schedule(
    schedule_arn: str,
    aws_service: AwsService = Depends(get_aws_service),
):
    """
    스케줄 취소
    
    예시:
    DELETE /scheduler/schedule/arn:aws:scheduler:ap-northeast-2:123456789012:schedule/default/task-abc12345
    """
    try:
        success = aws_service.cancel_schedule(schedule_arn)
        
        if success:
            return {
                "success": True,
                "message": "Schedule cancelled successfully",
                "schedule_arn": schedule_arn,
            }
        else:
            raise HTTPException(
                status_code=404,
                detail="Schedule not found or already executed"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel schedule: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"스케줄 취소 실패: {str(e)}"
        )
```

---

### Step 4: 환경 변수 설정

#### .env
```bash
# AWS 설정
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key

# Lambda 설정
SCHEDULER_LAMBDA_FUNCTION_NAME=FastAPI_Scheduled_Tasks

# EventBridge Scheduler 설정
SCHEDULER_TARGET_ROLE_ARN=arn:aws:iam::YOUR_ACCOUNT_ID:role/EventBridgeSchedulerRole
SCHEDULER_GROUP_NAME=default
```

#### config.py
```python
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    AWS_REGION: str = "ap-northeast-2"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    
    SCHEDULER_LAMBDA_FUNCTION_NAME: str
    SCHEDULER_TARGET_ROLE_ARN: str
    SCHEDULER_GROUP_NAME: str = "default"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 🧪 테스트

### 1. Lambda 함수 테스트 (로컬)

Lambda Proxy 형식으로 직접 테스트:

```python
# test_lambda.py
import json
from lambda_handler import lambda_handler

# API Gateway Proxy 형식 이벤트
event = {
    "body": json.dumps({
        "task_id": "test-123",
        "user_id": 456,
        "action": "send_notification",
        "data": {"message": "Hello"}
    }),
    "resource": "/{proxy+}",
    "path": "/api/v1/tasks/callback",
    "httpMethod": "POST",
    "isBase64Encoded": False,
    "pathParameters": {"proxy": "api/v1/tasks/callback"},
    "queryStringParameters": {},
    "headers": {
        "Content-Type": "application/json"
    },
    "requestContext": {
        "path": "/api/v1/tasks/callback",
        "httpMethod": "POST"
    }
}

context = {}

# Lambda 실행
response = lambda_handler(event, context)
print(json.dumps(response, indent=2))
```

실행:
```bash
python test_lambda.py
```

### 2. Lambda 함수 테스트 (AWS)

```bash
# 테스트 이벤트 생성
cat > test_event.json << EOF
{
  "body": "{\"task_id\": \"test-123\", \"user_id\": 456, \"action\": \"send_notification\", \"data\": {\"message\": \"Hello\"}}",
  "resource": "/{proxy+}",
  "path": "/api/v1/tasks/callback",
  "httpMethod": "POST",
  "isBase64Encoded": false,
  "pathParameters": {"proxy": "api/v1/tasks/callback"},
  "queryStringParameters": {},
  "headers": {"Content-Type": "application/json"},
  "requestContext": {"path": "/api/v1/tasks/callback", "httpMethod": "POST"}
}
EOF

# Lambda 직접 호출
aws lambda invoke \
    --function-name FastAPI_Scheduled_Tasks \
    --payload file://test_event.json \
    response.json

# 결과 확인
cat response.json
```

### 3. 스케줄 생성 테스트

```bash
# 1분 후 실행되도록 스케줄 생성
curl -X POST "https://your-api.com/api/v1/scheduler/schedule" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "task_id": "task-123",
    "user_id": 456,
    "action": "send_notification",
    "delay_minutes": 1,
    "data": {
      "notification_type": "reminder",
      "message": "Test message"
    }
  }'

# 응답:
# {
#   "success": true,
#   "message": "Task scheduled successfully",
#   "schedule_arn": "arn:aws:scheduler:...:schedule/default/task-456-abc12345",
#   "task_id": "task-123",
#   "scheduled_in_minutes": 1
# }
```

### 4. CloudWatch Logs 확인

```bash
# Lambda 로그 실시간 확인
aws logs tail /aws/lambda/FastAPI_Scheduled_Tasks --follow

# 특정 시간대 로그 확인
aws logs tail /aws/lambda/FastAPI_Scheduled_Tasks \
    --since 10m \
    --format short
```

---

## 📊 실제 사용 예시

### 예시 1: 결제 만료 알림

```python
# 30분 후 결제 만료 알림
schedule_arn = aws_service.schedule_lambda_proxy_task(
    lambda_function_name="FastAPI_Scheduled_Tasks",
    callback_path="api/v1/tasks/callback",
    callback_body={
        "task_id": f"payment-reminder-{payment_id}",
        "user_id": user_id,
        "action": "send_notification",
        "data": {
            "payment_id": payment_id,
            "notification_type": "payment_expiration",
            "expires_at": "2025-10-23T15:30:00Z"
        }
    },
    delay_minutes=30,
    scheduler_role_arn=settings.SCHEDULER_TARGET_ROLE_ARN,
    task_name_prefix="payment-reminder",
)
```

### 예시 2: 환영 이메일 발송

```python
# 1시간 후 환영 이메일
schedule_arn = aws_service.schedule_lambda_proxy_task(
    lambda_function_name="FastAPI_Scheduled_Tasks",
    callback_path="api/v1/tasks/callback",
    callback_body={
        "task_id": f"welcome-email-{user_id}",
        "user_id": user_id,
        "action": "send_notification",
        "data": {
            "email": user_email,
            "template": "welcome",
            "language": "ko"
        }
    },
    delay_minutes=60,
    scheduler_role_arn=settings.SCHEDULER_TARGET_ROLE_ARN,
    task_name_prefix="welcome-email",
)
```

### 예시 3: 리소스 정리

```python
# 24시간 후 임시 리소스 삭제
schedule_arn = aws_service.schedule_lambda_proxy_task(
    lambda_function_name="FastAPI_Scheduled_Tasks",
    callback_path="api/v1/tasks/callback",
    callback_body={
        "task_id": f"cleanup-{resource_id}",
        "user_id": user_id,
        "action": "cleanup",
        "data": {
            "resource_id": resource_id,
            "resource_type": "temp_file",
            "s3_bucket": "temp-storage",
            "s3_key": f"temp/{resource_id}"
        }
    },
    delay_minutes=1440,  # 24시간
    scheduler_role_arn=settings.SCHEDULER_TARGET_ROLE_ARN,
    task_name_prefix="cleanup",
)
```

---

## 🔐 IAM 권한 설정

### EventBridge Scheduler Role

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:ap-northeast-2:YOUR_ACCOUNT_ID:function:FastAPI_Scheduled_Tasks"
    }
  ]
}
```

### Trust Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "scheduler.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### Lambda Execution Role

Lambda 함수가 CloudWatch Logs에 쓸 수 있도록:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    }
  ]
}
```

---

## 🆚 HTTP Call 방식 vs Lambda Proxy 방식 비교

| 특성 | HTTP Call | Lambda Proxy |
|------|-----------|--------------|
| **아키텍처** | Lambda → HTTP → FastAPI | Lambda (FastAPI 내장) |
| **네트워크** | 필요 (외부 호출) | 불필요 (내부 실행) |
| **인증** | 필요 (Bearer Token) | 불필요 |
| **응답 속도** | 느림 (네트워크 지연) | 빠름 (직접 실행) |
| **비용** | 높음 (Lambda + Data Transfer) | 낮음 (Lambda만) |
| **Lambda Cold Start** | 영향 적음 | 영향 있음 (Mangum 로딩) |
| **배포** | 별도 FastAPI 서버 필요 | Lambda 하나로 완결 |
| **디버깅** | CloudWatch + 서버 로그 | CloudWatch만 |
| **확장성** | 서버 스케일링 필요 | Lambda 자동 스케일링 |

### 언제 어떤 방식을 쓸까?

#### HTTP Call 방식 추천:
- ✅ 기존 FastAPI 서버가 이미 있는 경우
- ✅ 복잡한 비즈니스 로직이 많은 경우
- ✅ DB 연결이 필요한 경우
- ✅ 여러 서비스와 통신해야 하는 경우

#### Lambda Proxy 방식 추천:
- ✅ 간단한 작업만 수행하는 경우
- ✅ 독립적인 스케줄 작업인 경우
- ✅ 비용을 최소화하고 싶은 경우
- ✅ 서버리스로 완전히 구성하고 싶은 경우

---

## 🔄 반복 스케줄 (Cron)

일회성이 아닌 반복 작업:

```python
def schedule_recurring_lambda_proxy_task(
    self,
    *,
    lambda_function_name: str,
    callback_path: str,
    callback_body: Dict[str, Any],
    cron_expression: str,  # 예: "cron(0 9 * * ? *)" - 매일 09:00 UTC
    scheduler_role_arn: str,
    scheduler_group: str = "default",
    schedule_name: str,
) -> str:
    """반복 스케줄 생성"""
    scheduler = self._client("scheduler")
    lambda_arn = self._get_lambda_arn(lambda_function_name)
    
    proxy_payload = self.generate_lambda_proxy_payload(
        path=callback_path,
        method="POST",
        body=callback_body,
    )
    
    try:
        resp = scheduler.create_schedule(
            Name=schedule_name,
            GroupName=scheduler_group,
            ScheduleExpression=cron_expression,  # at() 대신 cron()
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": lambda_arn,
                "RoleArn": scheduler_role_arn,
                "Input": json.dumps(proxy_payload),
            },
            State="ENABLED",
            Description=f"Recurring task: {schedule_name}",
        )
        return resp["ScheduleArn"]
    except Exception as e:
        logger.error(f"Failed to create recurring schedule: {str(e)}")
        raise
```

사용 예시:
```python
# 매일 오전 9시 (UTC) 실행
schedule_arn = aws_service.schedule_recurring_lambda_proxy_task(
    lambda_function_name="FastAPI_Scheduled_Tasks",
    callback_path="api/v1/tasks/callback",
    callback_body={
        "task_id": "daily-report",
        "user_id": 0,  # 시스템 작업
        "action": "generate_daily_report",
        "data": {}
    },
    cron_expression="cron(0 9 * * ? *)",  # 매일 09:00 UTC
    scheduler_role_arn=settings.SCHEDULER_TARGET_ROLE_ARN,
    schedule_name="daily-report",
)
```

---

## 💡 팁 & 베스트 프랙티스

### 1. Lambda Cold Start 최소화

```python
# Lambda 함수 외부에서 초기화 (재사용)
app = FastAPI()
handler = Mangum(app, lifespan="off")

# DB 연결도 외부에서 초기화
db_client = None

def get_db():
    global db_client
    if db_client is None:
        db_client = create_db_connection()
    return db_client
```

### 2. 에러 처리

```python
@app.post("/api/v1/tasks/callback")
async def handle_task_callback(request: TaskCallbackRequest):
    try:
        # 비즈니스 로직
        result = process_task(request)
        
        return {"success": True, "result": result}
        
    except Exception as e:
        # 에러를 CloudWatch Logs에 기록
        logger.error(f"Task failed: {str(e)}", exc_info=True)
        
        # EventBridge Scheduler에 재시도 신호 보내기
        raise HTTPException(500, detail=str(e))
```

### 3. 멱등성 보장

같은 작업이 여러 번 실행되어도 안전하도록:

```python
@app.post("/api/v1/tasks/callback")
async def handle_task_callback(request: TaskCallbackRequest):
    # 1. 중복 실행 체크 (Redis, DynamoDB 등)
    if is_task_already_processed(request.task_id):
        logger.info(f"Task {request.task_id} already processed")
        return {"success": True, "message": "Already processed"}
    
    # 2. 작업 실행
    result = process_task(request)
    
    # 3. 실행 기록 저장
    mark_task_as_processed(request.task_id)
    
    return {"success": True, "result": result}
```

### 4. 구조화된 로깅

```python
import json

logger.info(json.dumps({
    "event": "task_started",
    "task_id": request.task_id,
    "user_id": request.user_id,
    "action": request.action,
    "timestamp": datetime.utcnow().isoformat()
}))
```

---

## 🔍 트러블슈팅

### 문제 1: Mangum이 경로를 찾지 못함

```
{"detail":"Not Found"}
```

**원인**: path가 올바르지 않거나 FastAPI 라우터 prefix와 맞지 않음

**해결책**:
```python
# Lambda에서
@app.post("/api/v1/tasks/callback")  # 전체 경로 명시

# 또는
router = APIRouter(prefix="/api/v1/tasks")
@router.post("/callback")

# 스케줄 생성 시
callback_path="api/v1/tasks/callback"  # 앞에 / 없이
```

### 문제 2: Body가 None

```
{"detail":[{"type":"missing","loc":["body"],"msg":"Field required"}]}
```

**원인**: body가 문자열이 아닌 dict로 전달됨

**해결책**:
```python
# generate_lambda_proxy_payload에서 body를 dict로 전달 (OK)
body={"task_id": "123"}  # ✅ 맞음

# Pydantic이 자동으로 파싱함
```

### 문제 3: Lambda Timeout

```
Task timed out after 60.00 seconds
```

**해결책**:
```bash
# Timeout 증가
aws lambda update-function-configuration \
    --function-name FastAPI_Scheduled_Tasks \
    --timeout 300

# 또는 비동기 처리
@app.post("/api/v1/tasks/callback")
async def handle_task_callback(request: TaskCallbackRequest):
    # 백그라운드 작업으로 실행
    background_tasks.add_task(process_task, request)
    return {"success": True, "message": "Processing in background"}
```

---

## ✅ 체크리스트

### 설정
- [ ] Lambda 함수 생성 (FastAPI + Mangum)
- [ ] EventBridge Scheduler IAM Role 생성
- [ ] Lambda Execution Role 설정
- [ ] 환경 변수 설정

### 코드
- [ ] `generate_lambda_proxy_payload()` 구현
- [ ] `schedule_lambda_proxy_task()` 구현
- [ ] Lambda 함수에 FastAPI 엔드포인트 구현
- [ ] 스케줄 생성 라우터 구현

### 테스트
- [ ] Lambda 함수 로컬 테스트
- [ ] Lambda 함수 AWS 테스트
- [ ] 스케줄 생성 테스트
- [ ] CloudWatch Logs 확인
- [ ] 실제 스케줄 실행 확인 (1분 후 실행)

---

## 📚 참고 자료

- [Mangum 문서](https://mangum.io/)
- [AWS EventBridge Scheduler](https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html)
- [API Gateway Proxy Integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html)

---

이 방식은 **DB 테이블 없이**, **API Gateway Proxy 형식**으로 간단하게 스케줄 작업을 구현할 수 있습니다! 🎉


# EventBridge Scheduler + Lambda HTTP Proxy 템플릿

다른 프로젝트에서 EventBridge Scheduler를 통해 Lambda로 API를 호출하는 패턴을 구현하기 위한 가이드입니다.

## 📌 개요

현재 ox_universe 프로젝트의 쿨다운 서비스에서 사용하는 패턴:
- EventBridge Scheduler로 일회성/반복성 스케줄 생성
- Lambda 함수(API_CALL_LAMBDA)가 HTTP Proxy 역할
- API Gateway 형식의 JSON 페이로드로 FastAPI 엔드포인트 호출

## 🏗️ 아키텍처

```
[FastAPI Service]
    ↓ (스케줄 요청)
[EventBridge Scheduler]
    ↓ (지정 시간 도달)
[Lambda: API_CALL_LAMBDA]
    ↓ (HTTP Request)
[FastAPI Callback Endpoint]
```

---

## 📝 구현 단계

### 1️⃣ AWS Service 클래스 (aws_service.py)

EventBridge Scheduler와 Lambda 호출을 담당하는 서비스 클래스입니다.

**필요한 메서드:**

#### a) Lambda ARN 조회
```python
def _get_lambda_function_arn(self, function_name: str) -> str:
    """Lambda 함수 이름으로 ARN 조회"""
    lambda_client = self._client("lambda")
    try:
        resp = lambda_client.get_function(FunctionName=function_name)
        return resp["Configuration"]["FunctionArn"]
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve Lambda ARN for {function_name}: {str(e)}",
        )
```

#### b) API_CALL_LAMBDA 페이로드 생성
```python
def generate_api_call_lambda_payload(
    self,
    *,
    target_url: str,
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    API_CALL_LAMBDA 함수용 페이로드 생성
    
    EventBridge Scheduler → API_CALL_LAMBDA → FastAPI 호출용
    
    Args:
        target_url: 호출할 API URL (예: https://api.example.com/callback)
        method: HTTP 메서드
        headers: HTTP 헤더 (Authorization 포함)
        body: POST body (JSON 변환됨)
        params: Query string parameters
        
    Returns:
        API_CALL_LAMBDA에 전달할 페이로드
    """
    payload = {
        "target_url": target_url,
        "method": method.upper(),
        "headers": headers or {},
        "params": params or {},
    }
    
    if body and method != "GET":
        payload["body"] = body
        
    return payload
```

#### c) EventBridge Scheduler 생성
```python
def schedule_one_time_lambda_with_scheduler(
    self,
    *,
    delay_minutes: int,
    function_name: str,
    input_payload: dict,
    schedule_name_prefix: str = "scheduled-task",
    scheduler_role_arn: Optional[str] = None,
    scheduler_group_name: str = "default",
) -> str:
    """
    EventBridge Scheduler로 일회성 스케줄을 생성하여 Lambda를 호출합니다.
    
    Args:
        delay_minutes: 현재 시간으로부터 몇 분 후에 실행할지
        function_name: 호출할 Lambda 함수 이름 (예: "API_CALL_LAMBDA")
        input_payload: Lambda에 전달할 페이로드 (generate_api_call_lambda_payload 결과)
        schedule_name_prefix: 스케줄 이름 접두사
        scheduler_role_arn: EventBridge Scheduler가 사용할 IAM Role ARN
        scheduler_group_name: EventBridge Scheduler 그룹 이름
    
    Returns:
        생성된 스케줄 ARN (예: arn:aws:scheduler:...:schedule/default/task-abc123)
    """
    import uuid
    from datetime import datetime, timezone, timedelta
    import json as _json

    if not scheduler_role_arn:
        raise HTTPException(
            status_code=500,
            detail="Scheduler role ARN not configured. Set SCHEDULER_TARGET_ROLE_ARN.",
        )

    scheduler = self._client("scheduler")

    # UTC 시간 계산 및 at() 표현식 사용 (일회성)
    scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
    # 다음 분으로 반올림 (초/마이크로초 제거)
    rounded = scheduled_time.replace(second=0, microsecond=0)
    if scheduled_time.second > 0 or scheduled_time.microsecond > 0:
        rounded = rounded + timedelta(minutes=1)
    at_expression = f"at({rounded.strftime('%Y-%m-%dT%H:%M:%S')})"

    target_lambda_arn = self._get_lambda_function_arn(function_name)
    schedule_name = f"{schedule_name_prefix}-{uuid.uuid4().hex[:8]}"

    try:
        resp = scheduler.create_schedule(
            Name=schedule_name,
            GroupName=scheduler_group_name,
            ScheduleExpression=at_expression,
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": target_lambda_arn,
                "RoleArn": scheduler_role_arn,
                "Input": _json.dumps(input_payload),
                "RetryPolicy": {
                    "MaximumRetryAttempts": 2,
                    "MaximumEventAgeInSeconds": 3600,
                },
            },
            State="ENABLED",
            Description=f"One-time schedule to invoke {function_name}",
        )
        schedule_arn = resp.get("ScheduleArn") or (
            f"arn:aws:scheduler:{self.region_name}:schedule/{scheduler_group_name}/{schedule_name}"
        )
        logger.info(
            f"Created Scheduler one-time schedule: {schedule_name}, ARN: {schedule_arn}"
        )
        return schedule_arn
    except Exception as e:
        logger.error(f"Failed to create Scheduler schedule: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"EventBridge Scheduler 스케줄 생성 실패: {str(e)}",
        )
```

#### d) EventBridge Scheduler 취소
```python
def cancel_scheduled_event(self, rule_arn: str) -> bool:
    """
    예약된 EventBridge Scheduler를 취소합니다.
    
    Args:
        rule_arn: 취소할 스케줄 ARN
    
    Returns:
        bool: 취소 성공 여부
    """
    try:
        if rule_arn.startswith("arn:aws:scheduler:"):
            return self._cancel_scheduler_schedule(rule_arn)
        return False
    except Exception as e:
        logger.error(f"Failed to cancel scheduled event {rule_arn}: {str(e)}")
        return False

def _cancel_scheduler_schedule(self, schedule_arn: str) -> bool:
    """EventBridge Scheduler 스케줄 삭제"""
    try:
        # ARN format: arn:aws:scheduler:region:account:schedule/{group}/{name}
        if ":schedule/" not in schedule_arn:
            raise ValueError("Invalid Scheduler ARN")
        parts = schedule_arn.split(":schedule/")[-1].split("/")
        if len(parts) != 2:
            raise ValueError("Invalid Scheduler ARN components")
        group, name = parts[0], parts[1]
        scheduler = self._client("scheduler")
        scheduler.delete_schedule(Name=name, GroupName=group)
        logger.info(f"Deleted Scheduler schedule: {group}/{name}")
        return True
    except Exception as e:
        logger.warning(
            f"Failed to delete Scheduler schedule {schedule_arn}: {str(e)}"
        )
        return False
```

---

### 2️⃣ 서비스 클래스 (your_service.py)

비즈니스 로직과 스케줄 생성을 담당하는 서비스 클래스입니다.

```python
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from your_app.services.aws_service import AwsService
from your_app.repositories.your_repository import YourRepository
from your_app.config import Settings
import logging

logger = logging.getLogger(__name__)

class YourService:
    """스케줄 작업 관리 서비스"""

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.your_repo = YourRepository(db)
        self.aws_service = AwsService(settings)
        self.settings = settings

    async def schedule_task(
        self,
        user_id: int,
        task_data: dict,
        delay_minutes: int = 30
    ) -> bool:
        """
        작업 스케줄링
        
        Args:
            user_id: 사용자 ID
            task_data: 작업 데이터
            delay_minutes: 지연 시간 (분)
        
        Returns:
            bool: 스케줄링 성공 여부
        """
        try:
            # 1. DB에 작업 레코드 생성 (선택사항)
            task_record = self.your_repo.create_task(
                user_id=user_id,
                scheduled_at=datetime.utcnow() + timedelta(minutes=delay_minutes),
                status="SCHEDULED",
                data=task_data
            )
            
            if not task_record:
                raise Exception("Failed to create task record")
            
            # 2. 콜백 페이로드 준비
            callback_payload = {
                "task_id": task_record.id,
                "user_id": user_id,
                **task_data
            }
            
            # 3. API_CALL_LAMBDA 페이로드 생성
            api_call_payload = self.aws_service.generate_api_call_lambda_payload(
                target_url=f"{self.settings.api_base_url}/api/v1/tasks/callback",
                method="POST",
                headers={"Authorization": f"Bearer {self.settings.AUTH_TOKEN}"},
                body=callback_payload,
            )
            
            # 4. EventBridge Scheduler 생성
            schedule_arn = self.aws_service.schedule_one_time_lambda_with_scheduler(
                delay_minutes=delay_minutes,
                function_name="API_CALL_LAMBDA",  # Lambda 함수 이름
                input_payload=api_call_payload,
                schedule_name_prefix=f"task-{user_id}",
                scheduler_role_arn=self.settings.SCHEDULER_TARGET_ROLE_ARN,
                scheduler_group_name=self.settings.SCHEDULER_GROUP_NAME,
            )
            
            # 5. DB에 스케줄 ARN 저장
            self.your_repo.update_task_schedule_arn(task_record.id, schedule_arn)
            
            logger.info(
                f"Scheduled task for user {user_id}, task_id: {task_record.id}, "
                f"schedule_arn: {schedule_arn}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to schedule task for user {user_id}: {str(e)}")
            raise

    async def handle_task_callback(self, task_id: int) -> bool:
        """
        작업 완료 콜백 처리 (EventBridge Scheduler → Lambda → 이 메서드)
        
        Args:
            task_id: 완료할 작업 ID
        
        Returns:
            bool: 처리 성공 여부
        """
        try:
            # 1. 작업 조회
            task = self.your_repo.get_by_id(task_id)
            if not task or task.status != "SCHEDULED":
                logger.warning(f"Task {task_id} not found or not scheduled")
                return False
            
            # 2. 비즈니스 로직 수행
            # ... 여기에 실제 작업 로직 구현 ...
            
            # 3. 작업 완료 처리
            self.your_repo.complete_task(task_id)
            
            # 4. EventBridge Scheduler 정리 (선택사항)
            if task.schedule_arn:
                try:
                    self.aws_service.cancel_scheduled_event(task.schedule_arn)
                except Exception:
                    logger.warning(f"Failed to cleanup schedule for task {task_id}")
            
            logger.info(f"Task callback completed: task_id={task_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to handle task callback for task {task_id}: {str(e)}")
            return False
```

---

### 3️⃣ FastAPI 라우터 (your_router.py)

스케줄링 요청과 콜백을 처리하는 라우터입니다.

```python
from fastapi import APIRouter, Depends, HTTPException
from your_app.schemas.task import TaskCreateRequest, TaskCallbackMessage, TaskResponse
from your_app.services.your_service import YourService
from your_app.deps import get_your_service
from your_app.core.auth_middleware import get_current_active_user
from your_app.schemas.user import User as UserSchema
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.post("/schedule", response_model=TaskResponse)
async def schedule_task(
    request: TaskCreateRequest,
    current_user: UserSchema = Depends(get_current_active_user),
    your_service: YourService = Depends(get_your_service),
) -> TaskResponse:
    """
    작업 스케줄링
    
    인증 필요: Bearer 토큰
    """
    try:
        success = await your_service.schedule_task(
            user_id=current_user.id,
            task_data=request.data,
            delay_minutes=request.delay_minutes
        )
        
        if success:
            return TaskResponse(
                success=True,
                message="Task scheduled successfully"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to schedule task"
            )
    
    except Exception as e:
        logger.error(f"Failed to schedule task: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"작업 스케줄링 중 오류가 발생했습니다: {str(e)}"
        )


@router.post("/callback")
async def handle_task_callback(
    message: TaskCallbackMessage,
    your_service: YourService = Depends(get_your_service),
) -> dict:
    """
    EventBridge Scheduler Lambda 콜백: 작업 완료 처리
    
    이 엔드포인트는 AWS Lambda를 통해 내부 인증 헤더와 함께 호출됩니다.
    직접 사용자 호출용이 아닙니다.
    
    Args:
        message: 작업 콜백 메시지
    
    Returns:
        dict: 처리 결과
    """
    try:
        logger.info(
            f"Processing task callback: task_id={message.task_id}, "
            f"user_id={message.user_id}"
        )
        
        success = await your_service.handle_task_callback(message.task_id)
        
        if success:
            return {
                "success": True,
                "message": f"Task completed for task {message.task_id}",
                "task_id": message.task_id,
                "user_id": message.user_id,
            }
        else:
            return {
                "success": False,
                "message": f"Task failed for task {message.task_id}",
                "task_id": message.task_id,
                "user_id": message.user_id,
            }
    
    except Exception as e:
        logger.error(f"Failed to handle task callback: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"작업 처리 중 오류가 발생했습니다: {str(e)}"
        )
```

---

### 4️⃣ Pydantic 스키마 (schemas/task.py)

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class TaskCreateRequest(BaseModel):
    """작업 스케줄링 요청"""
    data: Dict[str, Any] = Field(..., description="작업 데이터")
    delay_minutes: int = Field(30, ge=1, le=10080, description="지연 시간 (분)")

class TaskCallbackMessage(BaseModel):
    """Lambda 콜백 메시지"""
    task_id: int = Field(..., description="작업 ID")
    user_id: int = Field(..., description="사용자 ID")
    # ... 추가 필드 ...

class TaskResponse(BaseModel):
    """작업 응답"""
    success: bool
    message: str
    task_id: Optional[int] = None
```

---

### 5️⃣ 환경 변수 설정 (config.py / .env)

```python
# config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # AWS 설정
    AWS_REGION: str = "ap-northeast-2"
    AWS_SQS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SQS_SECRET_ACCESS_KEY: Optional[str] = None
    
    # EventBridge Scheduler 설정
    SCHEDULER_TARGET_ROLE_ARN: str  # Lambda 호출 권한이 있는 IAM Role ARN
    SCHEDULER_GROUP_NAME: str = "default"
    
    # API 설정
    api_base_url: str  # 예: https://api.example.com
    AUTH_TOKEN: str  # 내부 인증 토큰
    
    class Config:
        env_file = ".env"
```

```bash
# .env
AWS_REGION=ap-northeast-2
AWS_SQS_ACCESS_KEY_ID=your_access_key
AWS_SQS_SECRET_ACCESS_KEY=your_secret_key

SCHEDULER_TARGET_ROLE_ARN=arn:aws:iam::123456789012:role/EventBridgeSchedulerRole
SCHEDULER_GROUP_NAME=default

api_base_url=https://api.example.com
AUTH_TOKEN=your_internal_auth_token
```

---

## 🔧 Lambda 함수 (API_CALL_LAMBDA)

EventBridge Scheduler가 호출하는 Lambda 함수입니다.

### Lambda 코드 (Python)

```python
import json
import urllib3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

http = urllib3.PoolManager()

def lambda_handler(event, context):
    """
    EventBridge Scheduler → Lambda → FastAPI
    
    event 구조:
    {
        "target_url": "https://api.example.com/api/v1/tasks/callback",
        "method": "POST",
        "headers": {"Authorization": "Bearer token"},
        "body": {"task_id": 123, "user_id": 456},
        "params": {}
    }
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")
        
        target_url = event.get("target_url")
        method = event.get("method", "POST").upper()
        headers = event.get("headers", {})
        body = event.get("body", {})
        params = event.get("params", {})
        
        if not target_url:
            raise ValueError("target_url is required")
        
        # Content-Type 헤더 추가
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"
        
        # Body를 JSON 문자열로 변환
        body_json = json.dumps(body) if body else None
        
        # HTTP 요청
        response = http.request(
            method=method,
            url=target_url,
            headers=headers,
            body=body_json,
            timeout=30.0
        )
        
        logger.info(
            f"API call completed: status={response.status}, "
            f"url={target_url}, method={method}"
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "api_status": response.status,
                "api_response": response.data.decode("utf-8")
            })
        }
        
    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "success": False,
                "error": str(e)
            })
        }
```

### Lambda 배포

```bash
# requirements.txt
urllib3

# 배포
zip -r lambda_function.zip lambda_function.py
aws lambda create-function \
    --function-name API_CALL_LAMBDA \
    --runtime python3.11 \
    --role arn:aws:iam::123456789012:role/LambdaExecutionRole \
    --handler lambda_function.lambda_handler \
    --zip-file fileb://lambda_function.zip \
    --timeout 30 \
    --memory-size 128
```

---

## 🔐 IAM 권한 설정

### EventBridge Scheduler IAM Role

EventBridge Scheduler가 Lambda를 호출하려면 다음 권한이 필요합니다:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lambda:InvokeFunction"
      ],
      "Resource": "arn:aws:lambda:ap-northeast-2:123456789012:function:API_CALL_LAMBDA"
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

---

## 📊 데이터베이스 스키마 (선택사항)

스케줄된 작업을 추적하려면 DB 테이블이 필요할 수 있습니다:

```python
from sqlalchemy import Column, Integer, String, DateTime, JSON, Enum
from sqlalchemy.ext.declarative import declarative_base
import enum

Base = declarative_base()

class TaskStatus(str, enum.Enum):
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    scheduled_at = Column(DateTime, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.SCHEDULED)
    schedule_arn = Column(String(500), nullable=True)  # EventBridge Scheduler ARN
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
```

---

## ✅ 체크리스트

다른 프로젝트에 적용할 때 확인사항:

### AWS 설정
- [ ] EventBridge Scheduler IAM Role 생성 (Lambda 호출 권한)
- [ ] Lambda 함수(API_CALL_LAMBDA) 배포
- [ ] Lambda 실행 Role에 네트워크 권한 부여 (VPC 내부일 경우)
- [ ] EventBridge Scheduler Group 생성 (선택사항)

### 코드 구현
- [ ] `AwsService` 클래스에 메서드 추가
  - [ ] `generate_api_call_lambda_payload()`
  - [ ] `schedule_one_time_lambda_with_scheduler()`
  - [ ] `cancel_scheduled_event()`
- [ ] 비즈니스 로직 서비스 클래스 구현
- [ ] FastAPI 라우터 구현
  - [ ] 스케줄링 엔드포인트
  - [ ] 콜백 엔드포인트
- [ ] Pydantic 스키마 정의
- [ ] DB 모델 및 Repository (선택사항)

### 환경 변수
- [ ] `SCHEDULER_TARGET_ROLE_ARN` 설정
- [ ] `SCHEDULER_GROUP_NAME` 설정
- [ ] `api_base_url` 설정
- [ ] `AUTH_TOKEN` 설정 (내부 인증용)

### 테스트
- [ ] 스케줄 생성 테스트
- [ ] Lambda 호출 테스트
- [ ] 콜백 엔드포인트 테스트
- [ ] 스케줄 취소 테스트

---

## 🎯 예제 사용 시나리오

### 1. 결제 만료 알림
```python
# 30분 후 결제 만료 알림
await payment_service.schedule_expiration_reminder(
    payment_id=123,
    delay_minutes=30
)
```

### 2. 이메일 발송 지연
```python
# 1시간 후 환영 이메일 발송
await email_service.schedule_welcome_email(
    user_id=456,
    delay_minutes=60
)
```

### 3. 데이터 정리 작업
```python
# 24시간 후 임시 데이터 삭제
await cleanup_service.schedule_cleanup(
    resource_id="temp-123",
    delay_minutes=1440  # 24시간
)
```

---

## 🔄 반복 스케줄 (Recurring Schedule)

일회성이 아닌 반복 스케줄이 필요한 경우:

```python
def schedule_recurring_lambda_with_scheduler(
    self,
    *,
    cron_expression: str,  # 예: "cron(0 9 * * ? *)" - 매일 09:00 UTC
    function_name: str,
    input_payload: dict,
    schedule_name: str,
    scheduler_role_arn: str,
    scheduler_group_name: str = "default",
) -> str:
    """반복 스케줄 생성"""
    scheduler = self._client("scheduler")
    target_lambda_arn = self._get_lambda_function_arn(function_name)
    
    try:
        resp = scheduler.create_schedule(
            Name=schedule_name,
            GroupName=scheduler_group_name,
            ScheduleExpression=cron_expression,  # at() 대신 cron() 사용
            FlexibleTimeWindow={"Mode": "OFF"},
            Target={
                "Arn": target_lambda_arn,
                "RoleArn": scheduler_role_arn,
                "Input": json.dumps(input_payload),
            },
            State="ENABLED",
            Description=f"Recurring schedule for {function_name}",
        )
        return resp["ScheduleArn"]
    except Exception as e:
        logger.error(f"Failed to create recurring schedule: {str(e)}")
        raise
```

---

## 📚 참고 자료

- [AWS EventBridge Scheduler 문서](https://docs.aws.amazon.com/scheduler/latest/UserGuide/what-is-scheduler.html)
- [Lambda 함수 호출 문서](https://docs.aws.amazon.com/lambda/latest/dg/lambda-invocation.html)
- [Cron 표현식 가이드](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-cron-expressions.html)

---

## 💡 팁

1. **at() vs cron()**: 
   - `at()`: 일회성 스케줄 (예: `at(2025-10-23T15:30:00)`)
   - `cron()`: 반복 스케줄 (예: `cron(0 9 * * ? *)`)

2. **타임존**: EventBridge Scheduler는 UTC 기준으로 동작합니다. KST → UTC 변환 필요.

3. **스케줄 정리**: 일회성 스케줄은 실행 후 자동으로 삭제되지 않으므로 수동 정리 필요.

4. **Lambda Cold Start**: 첫 호출 시 지연이 있을 수 있습니다. Provisioned Concurrency 고려.

5. **재시도 정책**: `RetryPolicy`에서 재시도 횟수와 만료 시간을 설정하여 안정성 향상.

6. **모니터링**: CloudWatch Logs로 Lambda 실행 로그 확인 가능.

---

이 템플릿을 다른 프로젝트에 복사하여 필요에 맞게 수정하면 됩니다! 🚀



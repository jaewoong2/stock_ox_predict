import json
import logging
from typing import Any, Literal, Optional, Dict

import boto3
from fastapi import HTTPException

from myapi.config import Settings
from pydantic import BaseModel
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
import requests
import json as _json
import re


class SecretPayload(BaseModel):
    data: Dict[str, Any]


class SQSQueueAttributes(BaseModel):
    ApproximateNumberOfMessages: Optional[str] = None
    ApproximateNumberOfMessagesNotVisible: Optional[str] = None
    ApproximateNumberOfMessagesDelayed: Optional[str] = None
    CreatedTimestamp: Optional[str] = None
    LastModifiedTimestamp: Optional[str] = None
    VisibilityTimeout: Optional[str] = None


class LambdaProxyMessage(BaseModel):
    body: Optional[str | Dict[str, Any]]
    resource: str
    path: str
    httpMethod: Literal["GET", "POST", "PUT", "DELETE"]
    isBase64Encoded: bool
    pathParameters: Dict[str, Any]
    queryStringParameters: Dict[str, Any]
    headers: Dict[str, Any]
    requestContext: Dict[str, Any]


SECRET_NAME = "kakao/tokens"

logger = logging.getLogger(__name__)


class AwsService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.aws_access_key_id = settings.AWS_SQS_ACCESS_KEY_ID
        self.aws_secret_access_key = settings.AWS_SQS_SECRET_ACCESS_KEY
        self.region_name = settings.AWS_SQS_REGION

        self.region_name = settings.AWS_REGION

    def _client(self, service: str):
        if self.aws_access_key_id and self.aws_secret_access_key:
            return boto3.client(
                service,
                region_name=self.region_name,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
            )

        return boto3.client(service, region_name=self.region_name)

    def get_secret(self) -> SecretPayload:
        client = self._client("secretsmanager")
        try:
            response = client.get_secret_value(SecretId=SECRET_NAME)
            secret_string = response.get("SecretString")
            return SecretPayload(
                data=(json.loads(secret_string) if secret_string else {})
            )
        except client.exceptions.ResourceNotFoundException:
            raise HTTPException(status_code=404, detail="Secret not found")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error retrieving secret: {str(e)}"
            )

    def update_secret(self, updated_data: dict) -> SecretPayload:
        client = self._client("secretsmanager")
        try:
            client.put_secret_value(
                SecretId=SECRET_NAME, SecretString=json.dumps(updated_data)
            )
            return SecretPayload(data=updated_data)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error updating secret: {str(e)}"
            )

    def upload_s3(
        self, bucket_name: str, object_key: str, fileobj: Any, content_type: str
    ):
        s3 = self._client("s3")
        return s3.upload_fileobj(
            fileobj, bucket_name, object_key, ExtraArgs={"ContentType": content_type}
        )

    def send_sqs_fifo_message(
        self,
        queue_url: str,
        message_body: str,
        message_group_id: str,
        message_deduplication_id: Optional[str] = None,
        delay_seconds: int = 0,
    ) -> Dict[str, Any]:
        sqs = self._client("sqs")
        params = {
            "QueueUrl": queue_url,
            "MessageBody": message_body,
            "MessageGroupId": message_group_id,
        }
        if message_deduplication_id:
            params["MessageDeduplicationId"] = message_deduplication_id
        if delay_seconds > 0:
            params["DelaySeconds"] = str(delay_seconds)
        try:
            return sqs.send_message(**params)
        except sqs.exceptions.InvalidClientTokenId as e:
            # AWS 자격 증명 문제
            raise HTTPException(
                status_code=500,
                detail=f"AWS credentials error: {str(e)}. Please check IAM role permissions.",
            )
        except sqs.exceptions.QueueDoesNotExist as e:
            # SQS 큐가 존재하지 않음
            raise HTTPException(
                status_code=404, detail=f"SQS queue not found: {queue_url}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error sending FIFO message to SQS: {str(e)}"
            )

    def send_sqs_message(
        self, queue_url: str, message_body: str, delay_seconds: int = 0
    ) -> Dict[str, Any]:
        sqs = self._client("sqs")
        params = {"QueueUrl": queue_url, "MessageBody": message_body}
        if delay_seconds > 0:
            params["DelaySeconds"] = str(delay_seconds)
        try:
            return sqs.send_message(**params)
        except sqs.exceptions.InvalidClientTokenId as e:
            # AWS 자격 증명 문제
            raise HTTPException(
                status_code=500,
                detail=f"AWS credentials error: {str(e)}. Please check IAM role permissions.",
            )
        except sqs.exceptions.QueueDoesNotExist as e:
            # SQS 큐가 존재하지 않음
            raise HTTPException(
                status_code=404, detail=f"SQS queue not found: {queue_url}"
            )
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error sending message to SQS: {str(e)}"
            )

    def generate_queue_message_http(
        self,
        body: str,
        path: str,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        query_string_parameters: Optional[dict] = None,
        auth_token: Optional[str] = "",
    ) -> LambdaProxyMessage:
        # If the caller included a query string in `path`, split it out to avoid 404s in Mangum routing
        from urllib.parse import urlsplit, parse_qs

        supplied_qsp = query_string_parameters or {}
        split = urlsplit(path)
        # Build clean path without query
        clean_path = split.path.lstrip("/") if split.path else path.lstrip("/")

        # Merge parsed query from path and explicitly supplied params
        parsed_qs = (
            {
                k: v[0] if isinstance(v, list) and v else v
                for k, v in parse_qs(split.query).items()
            }
            if split.query
            else {}
        )
        # Explicit parameters override parsed ones
        qsp = {**parsed_qs, **supplied_qsp} if parsed_qs or supplied_qsp else {}

        body_value: Optional[str | Dict[str, Any]] = None if method == "GET" else body
        return LambdaProxyMessage(
            body=body_value,
            resource="/{proxy+}",
            path=f"/{clean_path}",
            httpMethod=method,
            isBase64Encoded=False,
            pathParameters={"proxy": clean_path},
            queryStringParameters=qsp,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, sdch",
                "Accept-Language": "ko",
                "Accept-Charset": "utf-8",
                "Authorization": f"Bearer {auth_token}",
            },
            requestContext={
                "path": f"/{clean_path}",
                "resourcePath": "/{proxy+}",
                "httpMethod": method,
            },
        )

    def get_sqs_queue_attributes(self, queue_url: str) -> SQSQueueAttributes:
        """Fetch selected SQS queue attributes quickly.

        Requests only the attributes used by callers to minimize overhead.
        """
        sqs = self._client("sqs")
        attribute_names = [
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateNumberOfMessagesDelayed",
            "CreatedTimestamp",
            "LastModifiedTimestamp",
            "VisibilityTimeout",
        ]
        try:
            resp = sqs.get_queue_attributes(
                QueueUrl=queue_url, AttributeNames=attribute_names
            )
            attrs = resp.get("Attributes", {})
            return SQSQueueAttributes(**attrs)
        except sqs.exceptions.QueueDoesNotExist:
            raise HTTPException(status_code=404, detail="SQS queue not found")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error fetching SQS queue attributes: {str(e)}"
            )

    def schedule_one_time_event(
        self,
        delay_minutes: int,
        target_queue_url: str,
        message_body: dict,
        message_group_id: str,
        rule_name_prefix: str = "cooldown-slot-refill",
        role_arn: Optional[str] = None,
    ) -> str:
        """
        EventBridge를 사용하여 일회성 이벤트를 스케줄링합니다.

        Args:
            delay_minutes: 지연 시간 (분)
            target_queue_url: 대상 SQS 큐 URL
            message_body: 전송할 메시지 내용
            message_group_id: FIFO 큐 그룹 ID
            rule_name_prefix: EventBridge 규칙 이름 접두사

        Returns:
            str: 생성된 EventBridge 규칙 ARN

        Raises:
            HTTPException: EventBridge 스케줄링 실패
        """
        from datetime import datetime, timezone, timedelta
        import json
        import uuid

        eventbridge = self._client("events")

        # 스케줄 시간 계산 (UTC) 및 1분 단위로 반올림
        scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        # CloudWatch Events(EventBridge) put_rule는 at()를 지원하지 않음. cron() 사용 필요.
        # 초 단위는 불가하므로 다음 분으로 반올림하여 예약한다.
        rounded = scheduled_time.replace(second=0, microsecond=0)
        if scheduled_time.second > 0 or scheduled_time.microsecond > 0:
            rounded = rounded + timedelta(minutes=1)
        # cron(M H D M ? Y) — UTC 기준
        schedule_expression = f"cron({rounded.minute} {rounded.hour} {rounded.day} {rounded.month} ? {rounded.year})"

        # 고유한 규칙 이름 생성
        rule_name = f"{rule_name_prefix}-{uuid.uuid4().hex[:8]}"

        try:
            # EventBridge 규칙 생성 (단발성 시간에만 매칭되도록 연도까지 고정)
            rule_response = eventbridge.put_rule(
                Name=rule_name,
                ScheduleExpression=schedule_expression,
                State="ENABLED",
                Description=f"One-time slot refill timer (delay: {delay_minutes}min)",
            )

            rule_arn = rule_response["RuleArn"]

            # SQS 대상 추가 - Input 사용 (message body 직접 전달)
            target = {
                "Id": "1",
                "Arn": self._get_queue_arn_from_url(target_queue_url),
                "SqsParameters": {"MessageGroupId": message_group_id},
                "Input": json.dumps(message_body),
            }
            if role_arn:
                target["RoleArn"] = role_arn

            eventbridge.put_targets(
                Rule=rule_name,
                Targets=[target],
            )

            logger.info(f"Scheduled one-time event: {rule_name}, ARN: {rule_arn}")
            return rule_arn

        except Exception as e:
            logger.error(f"Failed to schedule one-time event: {str(e)}")
            raise HTTPException(
                status_code=500, detail=f"EventBridge 스케줄링 실패: {str(e)}"
            )

    def cancel_scheduled_event(self, rule_arn: str) -> bool:
        """
        예약된 EventBridge 규칙을 취소합니다.

        Args:
            rule_arn: 취소할 EventBridge 규칙 ARN

        Returns:
            bool: 취소 성공 여부
        """
        # 새 EventBridge Scheduler ARN도 지원 (arn:aws:scheduler:...:schedule/{group}/{name})
        try:
            if rule_arn.startswith("arn:aws:scheduler:"):
                return self._cancel_scheduler_schedule(rule_arn)

            # Legacy CloudWatch Events rule
            eventbridge = self._client("events")
            rule_name = rule_arn.split("/")[-1]
            eventbridge.remove_targets(Rule=rule_name, Ids=["1"])
            eventbridge.delete_rule(Name=rule_name)
            logger.info(f"Successfully cancelled scheduled event: {rule_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel scheduled event {rule_arn}: {str(e)}")
            return False

    def _get_queue_arn_from_url(self, queue_url: str) -> str:
        """
        SQS 큐 URL에서 ARN을 생성합니다.

        Args:
            queue_url: SQS 큐 URL

        Returns:
            str: SQS 큐 ARN
        """
        # URL 형식: https://sqs.{region}.amazonaws.com/{account_id}/{queue_name}
        parts = queue_url.split("/")
        queue_name = parts[-1]
        account_id = parts[-2]
        region = queue_url.split(".")[1]

        return f"arn:aws:sqs:{region}:{account_id}:{queue_name}"

    # -------------------------------
    # EventBridge Scheduler (Lambda)
    # -------------------------------
    def _get_lambda_function_arn(self, function_name: str) -> str:
        lambda_client = self._client("lambda")
        try:
            resp = lambda_client.get_function(FunctionName=function_name)
            return resp["Configuration"]["FunctionArn"]
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to resolve Lambda ARN for {function_name}: {str(e)}",
            )

    def schedule_one_time_lambda_with_scheduler(
        self,
        *,
        delay_minutes: int,
        function_name: str,
        input_payload: dict,
        schedule_name_prefix: str = "cooldown",
        scheduler_role_arn: Optional[str] = None,
        scheduler_group_name: str = "default",
    ) -> str:
        """
        EventBridge Scheduler로 일회성 스케줄을 생성하여 지정된 Lambda를 호출합니다.

        Returns created schedule ARN (arn:aws:scheduler:...:schedule/{group}/{name})
        """
        import uuid
        from datetime import datetime, timezone, timedelta
        import json as _json

        if not scheduler_role_arn:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Scheduler role ARN not configured. Set SCHEDULER_TARGET_ROLE_ARN."
                ),
            )

        scheduler = self._client("scheduler")

        # Compute UTC time and use at() for one-time schedule
        scheduled_time = datetime.now(timezone.utc) + timedelta(minutes=delay_minutes)
        # Round up to the next minute and drop timezone suffix (Scheduler expects UTC without 'Z')
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

    def _cancel_scheduler_schedule(self, schedule_arn: str) -> bool:
        """Delete a schedule by ARN for EventBridge Scheduler."""
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

    # -------------------------------
    # Direct Lambda invocation helpers
    # -------------------------------
    def invoke_lambda(
        self, *, function_name: str, payload: dict, asynchronous: bool = True
    ) -> Dict[str, Any]:
        """Invoke Lambda directly using AWS SDK.

        Sends the API Gateway proxy-like payload used throughout this app.
        When `asynchronous` is True, uses InvocationType='Event' (fire-and-forget).
        """
        client = self._client("lambda")
        try:
            invocation_type = "Event" if asynchronous else "RequestResponse"
            resp = client.invoke(
                FunctionName=function_name,
                InvocationType=invocation_type,
                Payload=_json.dumps(payload).encode("utf-8"),
            )
            return {
                "StatusCode": resp.get("StatusCode"),
                "RequestId": resp.get("ResponseMetadata", {}).get("RequestId"),
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Lambda invoke failed: {str(e)}"
            )

    def invoke_lambda_function_url(
        self,
        *,
        function_url: str,
        path: str,
        method: Literal["GET", "POST", "PUT", "DELETE"],
        body: Optional[str] = None,
        internal_auth_bearer: Optional[str] = None,
        timeout_sec: int = 15,
    ) -> Dict[str, Any]:
        """Invoke Lambda Function URL with IAM SigV4 auth.

        Note: Do NOT place user/service JWT in the standard Authorization header;
        it is reserved for AWS SigV4. Instead, pass it via settings.INTERNAL_AUTH_HEADER.
        """
        full_url = f"{function_url.rstrip('/')}/{path.lstrip('/')}"
        # Derive signing region from Function URL when possible to avoid SigV4 mismatch
        # Example: https://abc123.lambda-url.ap-northeast-2.on.aws/
        m = re.search(r"\.lambda-url\.([a-z0-9\-]+)\.on\.aws", function_url)
        signing_region = m.group(1) if m else self.region_name
        headers: Dict[str, str] = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
        }
        if internal_auth_bearer:
            headers[self.settings.INTERNAL_AUTH_HEADER] = (
                f"Bearer {internal_auth_bearer}"
            )

        data_bytes = body.encode("utf-8") if (body and method != "GET") else None

        # Prepare and sign request
        session = boto3.Session(
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key,
            region_name=signing_region,
        )
        creds = session.get_credentials()
        if not creds:
            raise HTTPException(
                status_code=500, detail="AWS credentials not available for SigV4"
            )
        frozen = creds.get_frozen_credentials()

        aws_request = AWSRequest(
            method=method, url=full_url, data=data_bytes, headers=headers
        )
        SigV4Auth(frozen, "lambda", signing_region).add_auth(aws_request)

        try:
            resp = requests.request(
                method=method,
                url=full_url,
                headers=dict(aws_request.headers.items()),
                data=data_bytes,
                timeout=timeout_sec,
            )
            return {
                "status_code": resp.status_code,
                "ok": resp.ok,
                "text": resp.text,
            }
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Function URL request failed: {str(e)}"
            )

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
            target_url: 호출할 API URL (예: https://ox-universe.bamtoly.com/api/v1/cooldown/handle-slot-refill)
            method: HTTP 메서드
            headers: HTTP 헤더
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

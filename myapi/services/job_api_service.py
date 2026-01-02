import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, cast, Literal

import requests
import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from fastapi import HTTPException

from myapi.config import Settings
from myapi.services.aws_service import AwsService

logger = logging.getLogger(__name__)


class JobApiService:
    """Lightweight client for the Common Job API (Function URL)."""

    def __init__(self, settings: Settings, aws_service: AwsService):
        self.settings = settings
        self.aws_service = aws_service

    def _jobs_create_url(self) -> str:
        if not self.settings.JOB_API_BASE_URL:
            raise HTTPException(
                status_code=500, detail="JOB_API_BASE_URL is not configured"
            )
        return f"{self.settings.JOB_API_BASE_URL.rstrip('/')}/v1/jobs/create"

    def _iso_now(self) -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    def _format_schedule_times(
        self, *, delay_minutes: Optional[int], scheduled_time: Optional[datetime]
    ) -> tuple[str, str]:
        if scheduled_time is None:
            if delay_minutes is None:
                raise HTTPException(
                    status_code=400,
                    detail="Either delay_minutes or scheduled_time is required for scheduled jobs",
                )
            scheduled_time = datetime.now(timezone.utc) + timedelta(
                minutes=delay_minutes
            )
        elif scheduled_time.tzinfo is None:
            scheduled_time = scheduled_time.replace(tzinfo=timezone.utc)
        else:
            scheduled_time = scheduled_time.astimezone(timezone.utc)

        scheduled_at = (
            scheduled_time.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        )
        expression_base = (
            scheduled_time.isoformat(timespec="seconds")
            .replace("+00:00", "")
            .replace("Z", "")
        )
        schedule_expression = f"at({expression_base})"
        return scheduled_at, schedule_expression

    def _build_execution_config(self, dispatch_mode: Optional[str]) -> Dict[str, Any]:
        mode = (dispatch_mode or self.settings.BATCH_DISPATCH_MODE or "SQS").upper()

        if mode == "LAMBDA_INVOKE":
            function_name = (
                self.settings.LAMBDA_FUNCTION_NAME_DIRECT
                or self.settings.LAMBDA_FUNCTION_NAME
            )
            if not function_name:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "LAMBDA_FUNCTION_NAME_DIRECT or LAMBDA_FUNCTION_NAME must be "
                        "configured for lambda-invoke jobs"
                    ),
                )
            return {
                "type": "lambda-invoke",
                "functionName": function_name,
                "invocationType": "Event",
            }

        if mode == "LAMBDA_URL" and self.settings.LAMBDA_FUNCTION_URL:
            return {
                "type": "lambda-url",
                "functionUrl": self.settings.LAMBDA_FUNCTION_URL,
            }
        if mode == "LAMBDA_URL":
            raise HTTPException(
                status_code=500,
                detail="LAMBDA_FUNCTION_URL is not configured for lambda-url jobs",
            )

        base_url = self.settings.api_base_url
        if not base_url:
            raise HTTPException(
                status_code=500,
                detail="API_BASE_URL is not configured for rest-api job execution",
            )
        return {"type": "rest-api", "baseUrl": base_url}

    def _post_job_sigv4(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """POST to Job API Function URL using SigV4 (IAM) auth."""
        url = self._jobs_create_url()
        timeout = self.settings.JOB_API_TIMEOUT_SEC or 10

        session = boto3.Session(
            aws_access_key_id=self.aws_service.aws_access_key_id,
            aws_secret_access_key=self.aws_service.aws_secret_access_key,
            region_name=self.settings.AWS_REGION,
        )
        creds = session.get_credentials()
        if not creds:
            raise HTTPException(
                status_code=500, detail="AWS credentials not available for SigV4"
            )
        frozen = creds.get_frozen_credentials()

        data = json.dumps(payload)
        headers = {"Content-Type": "application/json"}
        aws_request = AWSRequest(method="POST", url=url, data=data, headers=headers)
        SigV4Auth(frozen, "lambda", self.settings.AWS_REGION).add_auth(aws_request)

        try:
            resp = requests.post(
                url,
                data=data,
                headers=dict(aws_request.headers.items()),
                timeout=timeout,
            )
            if resp.status_code >= 400:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Job API error: {resp.text}",
                )
            try:
                return resp.json()
            except ValueError:
                return None
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to enqueue job via Job API (SigV4)")
            raise HTTPException(
                status_code=500, detail=f"Job API request failed: {exc}"
            ) from exc

    def _post_job(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self.settings.JOB_API_APP_ID:
            payload.setdefault("appId", self.settings.JOB_API_APP_ID)

        if self.settings.JOB_API_USE_SIGV4:
            return self._post_job_sigv4(payload)

        headers = {"Content-Type": "application/json"}
        if self.settings.JOB_API_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {self.settings.JOB_API_AUTH_TOKEN}"

        url = self._jobs_create_url()
        timeout = self.settings.JOB_API_TIMEOUT_SEC or 10

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if response.status_code >= 400:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Job API error: {response.text}",
                )
            try:
                return response.json()
            except ValueError:
                # SQS-only mode returns literal `null`
                return None
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("Failed to enqueue job via Job API")
            raise HTTPException(
                status_code=500, detail=f"Job API request failed: {exc}"
            ) from exc

    def create_job(
        self,
        *,
        path: str,
        method: str,
        body: Dict[str, Any],
        group_id: str,
        deduplication_id: Optional[str] = None,
        dispatch_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        lambda_proxy_message = self.aws_service.generate_queue_message_http(
            path=path,
            method=cast(Literal["GET", "POST", "PUT", "DELETE"], method.upper()),
            body=json.dumps(body),
            auth_token=self.settings.AUTH_TOKEN,
        )

        execution_config = self._build_execution_config(dispatch_mode)
        metadata = {
            "messageGroupId": group_id,
            "idempotencyKey": deduplication_id,
            "createdAt": self._iso_now(),
        }

        payload: Dict[str, Any] = {
            "mode": "sqs",
            "message": {
                "lambdaProxyMessage": lambda_proxy_message.model_dump(),
                "execution": execution_config,
                "metadata": metadata,
            },
        }

        return self._post_job(payload)

    def create_scheduled_lambda_invoke(
        self,
        *,
        function_name: str,
        payload: Dict[str, Any],
        target_path: str,
        target_method: Literal["GET", "POST", "PUT", "DELETE"] = "POST",
        delay_minutes: Optional[int] = None,
        scheduled_time: Optional[datetime] = None,
        schedule_group_id: str,
        target_group_id: str,
        idempotency_key: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Create a scheduled job that invokes a Lambda (e.g., API_CALL_LAMBDA) after a delay.

        This follows the Job API schedule schema:
        - execution.type = "schedule"
        - includes scheduledAt, scheduleExpression, and targetJob
        """
        scheduled_at, schedule_expression = self._format_schedule_times(
            delay_minutes=delay_minutes, scheduled_time=scheduled_time
        )

        # Use proxy message so downstream Lambda can read event["body"] as before
        target_lambda_proxy_message = self.aws_service.generate_queue_message_http(
            path=target_path,
            method=cast(
                Literal["GET", "POST", "PUT", "DELETE"], target_method.upper()
            ),
            body=json.dumps(payload),
            auth_token=self.settings.AUTH_TOKEN,
        )

        # Wrapper message used solely for schedule creation (documented as /schedule)
        schedule_lambda_proxy_message = self.aws_service.generate_queue_message_http(
            path="/schedule",
            method="POST",
            body="{}",
            auth_token=self.settings.AUTH_TOKEN,
        )

        target_metadata = {
            "messageGroupId": target_group_id,
            "idempotencyKey": idempotency_key,
            "createdAt": self._iso_now(),
        }
        schedule_metadata = {
            "messageGroupId": schedule_group_id,
            "idempotencyKey": f"{idempotency_key}-schedule",
            "createdAt": self._iso_now(),
        }

        target_job = {
            "lambdaProxyMessage": target_lambda_proxy_message.model_dump(),
            "execution": {
                "type": "lambda-invoke",
                "functionName": function_name,
                "invocationType": "Event",
            },
            "metadata": target_metadata,
        }

        schedule_execution = {
            "type": "schedule",
            "scheduledAt": scheduled_at,
            "scheduleExpression": schedule_expression,
            "targetJob": target_job,
        }

        payload_body: Dict[str, Any] = {
            "mode": "sqs",
            "message": {
                "lambdaProxyMessage": schedule_lambda_proxy_message.model_dump(),
                "execution": schedule_execution,
                "metadata": schedule_metadata,
            },
        }

        return self._post_job(payload_body)

import json
from typing import Any, Literal, Optional, Dict

import boto3
from fastapi import HTTPException

from myapi.config import Settings
from pydantic import BaseModel


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


class AwsService:
    def __init__(self, settings: Settings):
        self.aws_access_key_id = settings.AWS_ACCESS_KEY_ID
        self.aws_secret_access_key = settings.AWS_SECRET_ACCESS_KEY
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
            return SecretPayload(data=(json.loads(secret_string) if secret_string else {}))
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
        qsp = query_string_parameters or {}
        body_value: Optional[str | Dict[str, Any]] = None if method == "GET" else body
        return LambdaProxyMessage(
            body=body_value,
            resource="/{proxy+}",
            path=f"/{path}",
            httpMethod=method,
            isBase64Encoded=False,
            pathParameters={"proxy": path},
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
                "path": f"/{path}",
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
        except getattr(sqs, "exceptions", object()).__dict__.get(
            "QueueDoesNotExist", Exception
        ) as _:
            raise HTTPException(status_code=404, detail="SQS queue not found")
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error fetching SQS queue attributes: {str(e)}"
            )

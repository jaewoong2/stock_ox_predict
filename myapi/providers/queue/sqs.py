
import boto3
import json
from myapi.config import settings

class SQSClient:
    def __init__(self):
        self.sqs = boto3.client(
            'sqs',
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.SQS_ENDPOINT_URL
        )

    def send_message(self, queue_name: str, message_body: dict):
        queue_url = self.sqs.get_queue_url(QueueName=queue_name)['QueueUrl']
        self.sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body)
        )

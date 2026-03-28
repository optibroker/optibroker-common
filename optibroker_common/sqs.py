import json
import logging

import boto3

logger = logging.getLogger(__name__)


class BaseSqsSender:
    def __init__(self, queue_name, aws_access_key, aws_secret_key, region_name="eu-west-2",
                 local_sqs=False, endpoint_url="http://sqs:9324"):
        """
        Base SQS sender with lazy queue loading.

        Args:
            queue_name: Name of the SQS queue.
            aws_access_key: AWS access key ID.
            aws_secret_key: AWS secret access key.
            region_name: AWS region name. Defaults to 'eu-west-2'.
            local_sqs: Whether to use a local SQS endpoint. Defaults to False.
            endpoint_url: Local SQS endpoint URL. Defaults to 'http://sqs:9324'.
        """
        self.queue_name = queue_name

        boto_params = {
            "region_name": region_name,
            "aws_access_key_id": aws_access_key,
            "aws_secret_access_key": aws_secret_key
        }

        if local_sqs:
            boto_params.update({
                "endpoint_url": endpoint_url,
                "region_name": "elasticmq",
                "use_ssl": False
            })

        self.sqs = boto3.resource("sqs", **boto_params)
        self._queue = None

    @property
    def queue(self):
        if self._queue is None:
            self._queue = self.sqs.get_queue_by_name(QueueName=self.queue_name)
        return self._queue

    def send_message(self, message: dict):
        response = self.queue.send_message(
            MessageBody=json.dumps(message)
        )
        logger.info(response.get('MessageId'))
        logger.info(response.get('MD5OfMessageBody'))


class AuditSqsSender(BaseSqsSender):
    def __init__(self, audit_queue_name, aws_access_key, aws_secret_key,
                 region_name="eu-west-2", local_sqs=False, endpoint_url="http://sqs:9324"):
        """
        SQS sender configured for the audit queue.

        Args:
            audit_queue_name: Name of the audit SQS queue.
            aws_access_key: AWS access key ID.
            aws_secret_key: AWS secret access key.
            region_name: AWS region name. Defaults to 'eu-west-2'.
            local_sqs: Whether to use a local SQS endpoint. Defaults to False.
            endpoint_url: Local SQS endpoint URL. Defaults to 'http://sqs:9324'.
        """
        super().__init__(audit_queue_name, aws_access_key, aws_secret_key,
                         region_name, local_sqs, endpoint_url)

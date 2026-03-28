import json
from unittest.mock import patch, MagicMock

from optibroker_common.sqs import BaseSqsSender, AuditSqsSender


class TestBaseSqsSender:
    @patch("optibroker_common.sqs.boto3.resource")
    def test_lazy_queue_loading(self, mock_resource):
        mock_sqs = MagicMock()
        mock_resource.return_value = mock_sqs

        sender = BaseSqsSender("test-queue", "access", "secret")

        # Queue should not be loaded yet
        mock_sqs.get_queue_by_name.assert_not_called()

        # Access queue to trigger lazy load
        _ = sender.queue
        mock_sqs.get_queue_by_name.assert_called_once_with(QueueName="test-queue")

    @patch("optibroker_common.sqs.boto3.resource")
    def test_send_message(self, mock_resource):
        mock_sqs = MagicMock()
        mock_queue = MagicMock()
        mock_queue.send_message.return_value = {"MessageId": "msg1", "MD5OfMessageBody": "abc"}
        mock_sqs.get_queue_by_name.return_value = mock_queue
        mock_resource.return_value = mock_sqs

        sender = BaseSqsSender("test-queue", "access", "secret")
        sender.send_message({"key": "value"})

        mock_queue.send_message.assert_called_once_with(
            MessageBody=json.dumps({"key": "value"})
        )

    @patch("optibroker_common.sqs.boto3.resource")
    def test_local_sqs_config(self, mock_resource):
        mock_sqs = MagicMock()
        mock_resource.return_value = mock_sqs

        BaseSqsSender("test-queue", "access", "secret", local_sqs=True)

        call_kwargs = mock_resource.call_args[1]
        assert call_kwargs["endpoint_url"] == "http://sqs:9324"
        assert call_kwargs["region_name"] == "elasticmq"
        assert call_kwargs["use_ssl"] is False

    @patch("optibroker_common.sqs.boto3.resource")
    def test_custom_endpoint_url(self, mock_resource):
        mock_sqs = MagicMock()
        mock_resource.return_value = mock_sqs

        BaseSqsSender("test-queue", "access", "secret", local_sqs=True, endpoint_url="http://custom:1234")

        call_kwargs = mock_resource.call_args[1]
        assert call_kwargs["endpoint_url"] == "http://custom:1234"

    @patch("optibroker_common.sqs.boto3.resource")
    def test_queue_cached_after_first_access(self, mock_resource):
        mock_sqs = MagicMock()
        mock_queue = MagicMock()
        mock_sqs.get_queue_by_name.return_value = mock_queue
        mock_resource.return_value = mock_sqs

        sender = BaseSqsSender("test-queue", "access", "secret")
        _ = sender.queue
        _ = sender.queue

        mock_sqs.get_queue_by_name.assert_called_once()


class TestAuditSqsSender:
    @patch("optibroker_common.sqs.boto3.resource")
    def test_inherits_base(self, mock_resource):
        mock_sqs = MagicMock()
        mock_resource.return_value = mock_sqs

        sender = AuditSqsSender("audit-queue", "access", "secret")
        assert isinstance(sender, BaseSqsSender)
        assert sender.queue_name == "audit-queue"

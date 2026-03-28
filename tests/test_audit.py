from unittest.mock import MagicMock, patch

import pytest
from flask import Flask

from optibroker_common.audit import AuditLogger


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


class TestAuditLogger:
    def test_log_sends_message(self, app):
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)

        with app.test_request_context(
            "/api/payments",
            method="POST",
            json={"amount": 100},
            headers={"Authorization": "Bearer tok123"}
        ):
            audit.log("pay-1", "payment", "create", "payment_created", "payments-api")

        mock_sender.send_message.assert_called_once()
        message = mock_sender.send_message.call_args[0][0]

        assert message["object_id"] == "pay-1"
        assert message["object_type"] == "payment"
        assert message["action_type"] == "create"
        assert message["event"] == "payment_created"
        assert message["api"] == "payments-api"
        assert message["jwt"] == "tok123"
        assert message["route"] == "/api/payments"
        assert message["method"] == "post"
        assert "event_id" in message
        assert "timestamp" in message

    def test_log_handles_missing_json(self, app):
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)

        with app.test_request_context("/api/test", method="GET"):
            audit.log("obj-1", "test", "read", "test_read", "test-api")

        message = mock_sender.send_message.call_args[0][0]
        assert message["metadata"]["payload"] == {}

    def test_log_catches_exceptions(self, app):
        mock_sender = MagicMock()
        mock_sender.send_message.side_effect = Exception("SQS down")
        audit = AuditLogger(sender=mock_sender)

        with app.test_request_context("/api/test", method="GET"):
            # Should not raise
            audit.log("obj-1", "test", "read", "test_read", "test-api")

    def test_dependency_injection(self):
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)
        assert audit.sender is mock_sender

    @patch("optibroker_common.audit.uuid.uuid4")
    def test_event_id_is_uuid(self, mock_uuid, app):
        mock_uuid.return_value = "fixed-uuid-123"
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)

        with app.test_request_context("/test", method="GET"):
            audit.log("o1", "t1", "a1", "e1", "api1")

        message = mock_sender.send_message.call_args[0][0]
        assert message["event_id"] == "fixed-uuid-123"

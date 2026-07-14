from unittest.mock import MagicMock, patch

import jwt
import pytest
from flask import Flask

from optibroker_common.audit import AuditLogger, audit_actor


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

    def test_log_records_impersonation_actor(self, app):
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)

        token = jwt.encode({"sub": "sarah", "act": {"sub": "steve"}}, "secret", algorithm="HS256")
        with app.test_request_context(
            "/api/clients", method="POST", json={},
            headers={"Authorization": f"Bearer {token}"},
        ):
            audit.log("client-1", "client", "update", "client_updated", "client-api")

        message = mock_sender.send_message.call_args[0][0]
        assert message["is_impersonating"] is True
        assert message["real_actor_id"] == "steve"
        assert message["impersonated_user_id"] == "sarah"

    def test_log_normal_request_actor_is_subject(self, app):
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)

        token = jwt.encode({"sub": "sarah"}, "secret", algorithm="HS256")
        with app.test_request_context(
            "/api/clients", method="POST", json={},
            headers={"Authorization": f"Bearer {token}"},
        ):
            audit.log("client-1", "client", "update", "client_updated", "client-api")

        message = mock_sender.send_message.call_args[0][0]
        assert message["is_impersonating"] is False
        assert message["real_actor_id"] == "sarah"

class TestAuditActor:
    def test_impersonated_attributes_to_real_actor(self):
        user, note = audit_actor({
            "user_id": "sarah", "real_actor_id": "steve", "is_impersonating": True,
        })
        assert user == "steve"
        assert note == "acting as sarah"

    def test_normal_request(self):
        user, note = audit_actor({
            "user_id": "sarah", "real_actor_id": "sarah", "is_impersonating": False,
        })
        assert user == "sarah"
        assert note is None

    def test_pre_adoption_fallback(self):
        # current_user without the actor-aware fields (older token handling).
        user, note = audit_actor({"user_id": "sarah"})
        assert user == "sarah"
        assert note is None

    def test_service_account_fallback(self):
        user, note = audit_actor({"user": "sqs_feeder"})
        assert user == "sqs_feeder"
        assert note is None


class TestEventId:
    @patch("optibroker_common.audit.uuid.uuid4")
    def test_event_id_is_uuid(self, mock_uuid, app):
        mock_uuid.return_value = "fixed-uuid-123"
        mock_sender = MagicMock()
        audit = AuditLogger(sender=mock_sender)

        with app.test_request_context("/test", method="GET"):
            audit.log("o1", "t1", "a1", "e1", "api1")

        message = mock_sender.send_message.call_args[0][0]
        assert message["event_id"] == "fixed-uuid-123"

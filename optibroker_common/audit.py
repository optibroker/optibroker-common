import logging
import uuid
from datetime import datetime

from flask import request

logger = logging.getLogger(__name__)


class AuditLogger:
    def __init__(self, sender):
        """
        Audit logger with dependency injection for the SQS sender.

        Args:
            sender: An object with a send_message(dict) method (e.g. AuditSqsSender).
        """
        self.sender = sender

    def log(self, object_id: str, object_type: str, action_type: str, event: str, api_name: str):
        """
        Log an audit event by sending it to the audit SQS queue.

        Args:
            object_id: ID of the object being acted upon.
            object_type: Type of the object (e.g. 'payment', 'client').
            action_type: Type of action (e.g. 'create', 'update', 'delete').
            event: Description of the event.
            api_name: Name of the API that generated the event.
        """
        try:
            jwt_token = request.headers.get("Authorization", "").replace("Bearer ", "")
            payload = request.get_json(silent=True) or {}

            message = {
                "event_id": str(uuid.uuid4()),
                "jwt": jwt_token,
                "object_id": object_id,
                "object_type": object_type,
                "action_type": action_type,
                "event": event,
                "timestamp": datetime.utcnow().isoformat(),
                "metadata": {
                    "user_ip": request.remote_addr,
                    "payload": payload
                },
                "route": request.path,
                "method": request.method.lower(),
                "api": api_name
            }

            self.sender.send_message(message)

        except Exception as e:
            logger.exception("Audit logging failed: %s", e)

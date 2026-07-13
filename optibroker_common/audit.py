import logging
import uuid
from datetime import datetime

from flask import request

from optibroker_common.authentication import get_impersonation_context

logger = logging.getLogger(__name__)


def audit_actor(current_user):
    """Attribution for DB audit rows written from a ``current_user`` dict.

    Returns ``(user, impersonation_note)``:

    * ``user`` is the real human accountable for the action -- the real actor
      behind any impersonation, falling back to the caller for normal requests
      (and to ``"unknown"`` if neither is present). Attributing to the real
      actor means impersonation can never hide who actually acted.
    * ``impersonation_note`` names the impersonated subject when the request is
      impersonated (e.g. ``"acting as <subject>"``) so the trail reads
      "Sarah did this while acting as Steve"; it is ``None`` otherwise.

    Safe to call before services adopt the actor-aware token claims: without
    ``real_actor_id``/``is_impersonating`` it behaves exactly as attributing to
    the caller with no note.
    """
    real_actor = (current_user.get("real_actor_id")
                  or current_user.get("user_id")
                  or current_user.get("user", "unknown"))
    if current_user.get("is_impersonating"):
        subject = current_user.get("user_id") or current_user.get("user")
        return real_actor, f"acting as {subject}"
    return real_actor, None


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

            # Capture the real actor behind any impersonation so the audit trail
            # can record "Steve did this while acting as Sarah". For ordinary
            # requests is_impersonating is False and real_actor_id is the caller.
            impersonation = get_impersonation_context()

            message = {
                "event_id": str(uuid.uuid4()),
                "jwt": jwt_token,
                "object_id": object_id,
                "object_type": object_type,
                "action_type": action_type,
                "event": event,
                "timestamp": datetime.utcnow().isoformat(),
                "is_impersonating": impersonation["is_impersonating"],
                "real_actor_id": impersonation["real_actor_id"],
                "impersonated_user_id": impersonation["impersonated_user_id"],
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

import logging
import uuid
from datetime import datetime

from flask import g, has_request_context, request

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


def _verified_identity():
    """Who the request was authenticated as, from the current_user the
    get_current_user decorator verified, or None outside one. Never the
    request's credentials (OB-262)."""
    current_user = getattr(g, 'optibroker_current_user', None) if has_request_context() else None
    if not isinstance(current_user, dict):
        return None
    secret_key = current_user.get('auth_method') == 'secret_key'
    return {
        'auth_method': 'secret_key' if secret_key else 'bearer',
        'user_id': current_user.get('user') if secret_key else current_user.get('user_id'),
        'realm': current_user.get('realm'),
        'name': None if secret_key else current_user.get('name'),
        'is_impersonating': bool(current_user.get('is_impersonating')),
        'real_actor_id': None if secret_key else current_user.get('real_actor_id'),
    }


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
            payload = request.get_json(silent=True) or {}

            # Capture the real actor behind any impersonation so the audit trail
            # can record "Steve did this while acting as Sarah". For ordinary
            # requests is_impersonating is False and real_actor_id is the caller.
            verified = _verified_identity()
            if verified is not None:
                impersonation = {
                    "is_impersonating": verified["is_impersonating"],
                    "real_actor_id": verified["real_actor_id"] or verified["user_id"],
                    "impersonated_user_id": verified["user_id"] if verified["is_impersonating"] else None,
                }
            else:
                impersonation = get_impersonation_context()

            # Who acted, from the verified current_user (OB-262). The message
            # used to carry the raw Authorization header ("jwt"): a bearer
            # token, or for a service the secret key itself, sent to the
            # audit store with every event. No credential is sent now.
            identity = verified or {
                "auth_method": None, "user_id": None, "realm": None, "name": None,
            }

            message = {
                "event_id": str(uuid.uuid4()),
                "auth_method": identity["auth_method"],
                "user_id": identity["user_id"],
                "realm": identity["realm"],
                "name": identity["name"],
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

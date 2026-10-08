"""OB-262: an audit message never carries the request's credentials.

It used to copy the raw Authorization header into "jwt" on every event: a
user's bearer token, or for a service call the secret key itself (only a
"Bearer " prefix was stripped). It now says who acted, from the current_user
the get_current_user decorator verified, and nothing from the header."""
import re
from unittest.mock import MagicMock, patch

import jwt
import pytest
from flask import Flask

from optibroker_common.audit import AuditLogger
from optibroker_common.validation import configure, get_current_user

TOKEN = jwt.encode({"sub": "steve", "name": "Steve Adviser", "iss": "http://keycloak/realms/uiqa",
                    "realm_access": {"roles": ["staff"]}, "pad": "x" * 3000}, "k", algorithm="HS256")
SECRET = "svc-secret-key-value-1234567890"
JWT_SHAPED = re.compile(r"[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


def strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from strings(v)
    elif value is not None:
        yield str(value)


def assert_no_credentials(message):
    assert "jwt" not in message
    for text in strings(message):
        assert TOKEN not in text and SECRET not in text
        assert not JWT_SHAPED.search(text), text[:40]


class Rig:
    """Views behind the real get_current_user decorator, called inside a
    request context (has_permission is stubbed to the verified user)."""

    def __init__(self):
        self.app = Flask(__name__)
        configure(algorithm="RS256", keycloak_server_url="http://keycloak", secret_keys=[SECRET])
        self.sender = MagicMock()
        audit = AuditLogger(sender=self.sender)

        @get_current_user([])
        def user_route(**kwargs):
            audit.log("obj-1", "thing", "create", "thing_created", "test-api")

        @get_current_user([], allow_secret_key=True)
        def service_route(**kwargs):
            audit.log("obj-2", "thing", "create", "thing_created", "test-api")

        self.routes = {"/user": user_route, "/service": service_route}

    def post(self, path, authorization, verified):
        with patch("optibroker_common.validation.has_permission", return_value=verified), \
                self.app.test_request_context(path, method="POST", json={"amount": 1},
                                              headers={"Authorization": authorization}):
            self.routes[path]()
        return self.sender.send_message.call_args[0][0]


@pytest.fixture
def app():
    return Rig()


def test_a_user_event_says_who_acted_and_carries_no_token(app):
    user = {"user_id": "steve", "permissions": ["staff"], "realm": "uiqa", "is_impersonating": False,
            "real_actor_id": "steve", "name": "Steve Adviser", "preferred_username": "steve.a"}
    message = app.post("/user", f"Bearer {TOKEN}", user)
    assert_no_credentials(message)
    assert (message["auth_method"], message["user_id"], message["realm"], message["name"]) == \
        ("bearer", "steve", "uiqa", "Steve Adviser")
    assert (message["is_impersonating"], message["real_actor_id"], message["impersonated_user_id"]) == \
        (False, "steve", None)


def test_a_service_event_never_carries_the_secret_key(app):
    service = {"user": "sqs_feeder", "permissions": ["sqs_feeder_access"], "auth_method": "secret_key",
               "realm": "uiqa"}
    message = app.post("/service", f"SecretKey {SECRET}", service)
    assert_no_credentials(message)
    assert (message["auth_method"], message["user_id"], message["name"]) == ("secret_key", "sqs_feeder", None)


def test_an_impersonated_event_names_the_real_actor(app):
    user = {"user_id": "sarah", "permissions": ["viewer"], "realm": "uiqa", "is_impersonating": True,
            "real_actor_id": "steve", "name": "Steve Adviser"}
    message = app.post("/user", f"Bearer {TOKEN}", user)
    assert_no_credentials(message)
    assert (message["is_impersonating"], message["real_actor_id"], message["impersonated_user_id"]) == \
        (True, "steve", "sarah")


def test_outside_an_authenticated_route_it_still_sends_no_token():
    app = Flask(__name__)
    sender = MagicMock()
    with app.test_request_context("/x", method="POST", json={}, headers={"Authorization": f"Bearer {TOKEN}"}):
        AuditLogger(sender=sender).log("obj", "thing", "read", "e", "test-api")
    message = sender.send_message.call_args[0][0]
    assert_no_credentials(message)
    assert message["user_id"] is None and message["auth_method"] is None

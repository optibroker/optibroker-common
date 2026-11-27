"""No audit message carries a credential (OB-509, from OB-262 and OB-194).

The audit logger used to copy the Authorization header into every message as
"jwt": user bearer tokens, and for service calls the whole "SecretKey <key>".
These tests run real requests through the real get_current_user decorator and
scan every value in the message, however deeply nested.
"""
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask

from optibroker_common.audit import AuditLogger
from optibroker_common.validation import configure, get_current_user

SECRET_KEY = "svc-secret-key-that-never-expires"
KEYCLOAK = "http://keycloak"


@pytest.fixture(scope="module")
def rsa_key():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return key, public_pem


@pytest.fixture
def bearer(rsa_key):
    key, public_pem = rsa_key

    def make(**claims):
        payload = {"sub": "sarah-id", "iss": f"{KEYCLOAK}/realms/fsw", "name": "Sarah Jones",
                   "realm_access": {"roles": ["VIEW_CLIENTS"]}, **claims}
        return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "k1"})

    with patch("optibroker_common.authentication.get_public_key", return_value=public_pem):
        yield make


@pytest.fixture
def app():
    configure("RS256", KEYCLOAK, secret_keys=[SECRET_KEY])
    app = Flask(__name__)
    sender = MagicMock()
    audit = AuditLogger(sender=sender)

    @app.route("/guarded", methods=["POST"])
    @get_current_user(allow_secret_key=True)
    def guarded(current_user):
        audit.log("obj-1", "client", "update", "client_updated", "test-api")
        return "ok"

    @app.route("/open", methods=["POST"])
    def open_route():
        audit.log("obj-1", "client", "update", "client_updated", "test-api")
        return "ok"

    app.sender = sender
    return app


def _strings(value):
    if isinstance(value, dict):
        for k, v in value.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _strings(v)
    elif value is not None:
        yield str(value)


def _assert_no_credential(message, *credentials):
    assert "jwt" not in message
    for s in _strings(message):
        assert "SecretKey" not in s
        assert not s.startswith("eyJ"), f"JWT-shaped value in audit message: {s[:20]}..."
        for credential in credentials:
            assert credential not in s


def _sent(app):
    app.sender.send_message.assert_called_once()
    return app.sender.send_message.call_args[0][0]


def test_user_request_names_the_user_and_sends_no_token(app, bearer):
    token = bearer()
    resp = app.test_client().post("/guarded", json={"a": 1}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200

    message = _sent(app)
    _assert_no_credential(message, token)
    assert message["auth_method"] == "bearer"
    assert message["user_id"] == "sarah-id"
    assert message["realm"] == "fsw"
    assert message["name"] == "Sarah Jones"
    assert message["is_impersonating"] is False
    assert message["real_actor_id"] == "sarah-id"


def test_service_request_sends_no_secret_key(app):
    resp = app.test_client().post("/guarded", json={}, headers={
        "Authorization": f"SecretKey {SECRET_KEY}", "X-Keycloak-Realm": "fsw"})
    assert resp.status_code == 200

    message = _sent(app)
    _assert_no_credential(message, SECRET_KEY)
    assert message["auth_method"] == "secret_key"
    assert message["user_id"] == "sqs_feeder"
    assert message["realm"] == "fsw"
    assert message["name"] is None


def test_token_exchange_impersonation_attributes_to_the_real_actor(app, bearer):
    token = bearer(act={"sub": "steve-id"})
    app.test_client().post("/guarded", json={}, headers={"Authorization": f"Bearer {token}"})

    message = _sent(app)
    _assert_no_credential(message, token)
    assert message["is_impersonating"] is True
    assert message["real_actor_id"] == "steve-id"
    assert message["impersonated_user_id"] == "sarah-id"
    assert message["name"] is None  # the token's name is the subject's, not the actor's


def test_unguarded_route_sends_no_token_either(app, bearer):
    token = bearer()
    app.test_client().post("/open", json={}, headers={"Authorization": f"Bearer {token}"})

    message = _sent(app)
    _assert_no_credential(message, token)
    assert message["auth_method"] is None
    assert message["user_id"] is None
    # Impersonation context still falls back to reading the token's subject.
    assert message["real_actor_id"] == "sarah-id"


def test_unguarded_route_sends_no_secret_key_either(app):
    app.test_client().post("/open", json={}, headers={"Authorization": f"SecretKey {SECRET_KEY}"})
    _assert_no_credential(_sent(app), SECRET_KEY)

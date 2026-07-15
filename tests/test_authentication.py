import datetime
from unittest.mock import patch, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask

from optibroker_common.authentication import (
    get_bearer_token,
    get_public_key,
    verify_jwt_or_secret_key,
    get_current_user_permissions,
    has_permission,
    extract_actor,
    get_impersonation_context,
    apply_impersonation_context,
    set_impersonation_public_key,
    IMPERSONATION_HEADER,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


# One keypair for the whole module — RSA keygen is slow.
_IMP_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_IMP_PRIVATE_PEM = _IMP_KEY.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()
_IMP_PUBLIC_PEM = _IMP_KEY.public_key().public_bytes(
    serialization.Encoding.PEM,
    serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()


def _make_assertion(actor_id="steve", subject_id="sarah", realm="testrealm",
                    roles=None, exp_delta=300, key=None):
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "actor_id": actor_id,
        "subject_id": subject_id,
        "realm": realm,
        "roles": roles if roles is not None else ["viewer"],
        "iat": now,
        "exp": now + datetime.timedelta(seconds=exp_delta),
    }
    return jwt.encode(payload, key or _IMP_PRIVATE_PEM, algorithm="RS256")


class TestGetBearerToken:
    def test_extracts_token(self, app):
        with app.test_request_context(headers={"Authorization": "Bearer abc123"}):
            assert get_bearer_token() == "abc123"

    def test_missing_header_aborts(self, app):
        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_bearer_token()
            assert exc_info.value.code == 401

    def test_invalid_prefix_aborts(self, app):
        with app.test_request_context(headers={"Authorization": "Basic abc123"}):
            with pytest.raises(Exception) as exc_info:
                get_bearer_token()
            assert exc_info.value.code == 401


class TestGetPublicKey:
    @patch("optibroker_common.authentication.requests.get")
    @patch("optibroker_common.authentication.jwt.algorithms.RSAAlgorithm.from_jwk")
    def test_returns_public_key(self, mock_from_jwk, mock_get, app):
        mock_openid = MagicMock()
        mock_openid.json.return_value = {"jwks_uri": "http://keycloak/jwks"}

        mock_jwks = MagicMock()
        mock_jwks.json.return_value = {"keys": [{"kid": "key1", "kty": "RSA"}]}

        mock_get.side_effect = [mock_openid, mock_jwks]
        mock_from_jwk.return_value = "public_key_value"

        with app.test_request_context():
            result = get_public_key("http://keycloak/realms/test", "key1", "http://keycloak")
            assert result == "public_key_value"

    @patch("optibroker_common.authentication.requests.get")
    def test_request_error_aborts_503(self, mock_get, app):
        import requests as req
        mock_get.side_effect = req.RequestException("connection refused")

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_public_key("http://keycloak/realms/test", "key1", "http://keycloak")
            assert exc_info.value.code == 503

    @patch("optibroker_common.authentication.requests.get")
    def test_key_not_found_aborts_400(self, mock_get, app):
        mock_openid = MagicMock()
        mock_openid.json.return_value = {"jwks_uri": "http://keycloak/jwks"}

        mock_jwks = MagicMock()
        mock_jwks.json.return_value = {"keys": [{"kid": "other_key"}]}

        mock_get.side_effect = [mock_openid, mock_jwks]

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_public_key("http://keycloak/realms/test", "key1", "http://keycloak")
            assert exc_info.value.code == 400


class TestVerifyJwtOrSecretKey:
    def test_missing_auth_header_aborts(self, app):
        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                verify_jwt_or_secret_key("RS256", "http://keycloak")
            assert exc_info.value.code == 401

    def test_valid_secret_key(self, app):
        with app.test_request_context(
            headers={"Authorization": "SecretKey mysecret", "X-Keycloak-Realm": "testrealm"}
        ):
            result = verify_jwt_or_secret_key("RS256", "http://keycloak", secret_keys=["mysecret"])
            assert result["auth_method"] == "secret_key"
            assert result["realm"] == "testrealm"

    def test_invalid_secret_key_aborts(self, app):
        with app.test_request_context(headers={"Authorization": "SecretKey wrong"}):
            with pytest.raises(Exception) as exc_info:
                verify_jwt_or_secret_key("RS256", "http://keycloak", secret_keys=["mysecret"])
            assert exc_info.value.code == 403

    def test_invalid_auth_prefix_aborts(self, app):
        with app.test_request_context(headers={"Authorization": "Basic abc"}):
            with pytest.raises(Exception) as exc_info:
                verify_jwt_or_secret_key("RS256", "http://keycloak")
            assert exc_info.value.code == 401

    @patch("optibroker_common.authentication.get_public_key")
    @patch("optibroker_common.authentication.jwt.decode")
    @patch("optibroker_common.authentication.jwt.get_unverified_header")
    def test_valid_jwt(self, mock_header, mock_decode, mock_pubkey, app):
        mock_header.return_value = {"kid": "key1"}
        mock_decode.side_effect = [
            {"iss": "http://keycloak/realms/test", "sub": "user1"},  # unverified
            {"iss": "http://keycloak/realms/test", "sub": "user1", "realm_access": {"roles": ["admin"]}},  # verified
        ]
        mock_pubkey.return_value = "public_key"

        with app.test_request_context(headers={"Authorization": "Bearer faketoken"}):
            result = verify_jwt_or_secret_key("RS256", "http://keycloak")
            assert result["sub"] == "user1"


class TestGetCurrentUserPermissions:
    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_jwt_user_returns_permissions(self, mock_verify, app):
        mock_verify.return_value = {
            "sub": "user123",
            "realm_access": {"roles": ["admin", "viewer"]},
            "iss": "http://keycloak/realms/testrealm"
        }

        with app.test_request_context():
            result = get_current_user_permissions("RS256", "http://keycloak")
            assert result["user_id"] == "user123"
            assert result["realm"] == "testrealm"
            assert "admin" in result["permissions"]

    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_secret_key_returns_payload(self, mock_verify, app):
        mock_verify.return_value = {
            "user": "sqs_feeder",
            "permissions": ["sqs_feeder_access"],
            "auth_method": "secret_key",
            "realm": "testrealm"
        }

        with app.test_request_context():
            result = get_current_user_permissions("RS256", "http://keycloak")
            assert result["auth_method"] == "secret_key"

    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_missing_user_id_aborts(self, mock_verify, app):
        mock_verify.return_value = {
            "realm_access": {"roles": []},
            "iss": "http://keycloak/realms/testrealm"
        }

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_current_user_permissions("RS256", "http://keycloak")
            assert exc_info.value.code == 401

    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_invalid_realm_aborts(self, mock_verify, app):
        mock_verify.return_value = {
            "sub": "user123",
            "realm_access": {"roles": []},
            "iss": "http://keycloak/realms/badrealm"
        }

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_current_user_permissions(
                    "RS256", "http://keycloak",
                    get_realms_func=lambda: ["goodrealm"]
                )
            assert exc_info.value.code == 401


class TestExtractActor:
    def test_returns_actor_when_act_claim_present(self):
        actor_id, is_impersonating = extract_actor({"sub": "sarah", "act": {"sub": "steve"}})
        assert actor_id == "steve"
        assert is_impersonating is True

    def test_no_act_claim(self):
        actor_id, is_impersonating = extract_actor({"sub": "sarah"})
        assert actor_id is None
        assert is_impersonating is False

    def test_act_claim_without_sub(self):
        actor_id, is_impersonating = extract_actor({"sub": "sarah", "act": {}})
        assert actor_id is None
        assert is_impersonating is False


class TestGetCurrentUserPermissionsImpersonation:
    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_impersonated_token_exposes_real_actor(self, mock_verify, app):
        mock_verify.return_value = {
            "sub": "sarah",
            "realm_access": {"roles": ["viewer"]},
            "iss": "http://keycloak/realms/testrealm",
            "act": {"sub": "steve"},
        }

        with app.test_request_context():
            result = get_current_user_permissions("RS256", "http://keycloak")
            # The system believes the caller is the impersonated subject...
            assert result["user_id"] == "sarah"
            # ...but the real actor is preserved for audit.
            assert result["is_impersonating"] is True
            assert result["real_actor_id"] == "steve"

    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_normal_token_real_actor_is_subject(self, mock_verify, app):
        mock_verify.return_value = {
            "sub": "sarah",
            "realm_access": {"roles": ["viewer"]},
            "iss": "http://keycloak/realms/testrealm",
        }

        with app.test_request_context():
            result = get_current_user_permissions("RS256", "http://keycloak")
            assert result["is_impersonating"] is False
            assert result["real_actor_id"] == "sarah"


class TestGetImpersonationContext:
    def test_impersonated_token(self, app):
        token = jwt.encode({"sub": "sarah", "act": {"sub": "steve"}}, "secret", algorithm="HS256")
        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            ctx = get_impersonation_context()
            assert ctx["is_impersonating"] is True
            assert ctx["real_actor_id"] == "steve"
            assert ctx["impersonated_user_id"] == "sarah"

    def test_normal_token(self, app):
        token = jwt.encode({"sub": "sarah"}, "secret", algorithm="HS256")
        with app.test_request_context(headers={"Authorization": f"Bearer {token}"}):
            ctx = get_impersonation_context()
            assert ctx["is_impersonating"] is False
            assert ctx["real_actor_id"] == "sarah"
            assert ctx["impersonated_user_id"] == "sarah"

    def test_no_bearer_token(self, app):
        with app.test_request_context():
            ctx = get_impersonation_context()
            assert ctx["is_impersonating"] is False
            assert ctx["real_actor_id"] is None

    def test_malformed_token(self, app):
        with app.test_request_context(headers={"Authorization": "Bearer not-a-jwt"}):
            ctx = get_impersonation_context()
            assert ctx["is_impersonating"] is False
            assert ctx["real_actor_id"] is None


class TestApplyImpersonationContext:
    def setup_method(self):
        set_impersonation_public_key(_IMP_PUBLIC_PEM)

    def teardown_method(self):
        set_impersonation_public_key(None)

    def _actor(self):
        return {
            "user_id": "steve",
            "permissions": ["STAFF"],
            "realm": "testrealm",
            "is_impersonating": False,
            "real_actor_id": "steve",
        }

    def test_no_header_returns_unchanged(self, app):
        with app.test_request_context():
            result = apply_impersonation_context(self._actor())
            assert result["user_id"] == "steve"
            assert result["is_impersonating"] is False

    def test_valid_assertion_resolves_to_subject(self, app):
        assertion = _make_assertion(roles=["CLIENT_VIEW"])
        with app.test_request_context(headers={IMPERSONATION_HEADER: assertion}):
            result = apply_impersonation_context(self._actor())
            # The request now acts as the subject with the subject's roles...
            assert result["user_id"] == "sarah"
            assert result["permissions"] == ["CLIENT_VIEW"]
            # ...and the real actor is preserved for audit.
            assert result["is_impersonating"] is True
            assert result["real_actor_id"] == "steve"
            assert result["impersonator_id"] == "steve"

    def test_actor_mismatch_forbidden(self, app):
        # Assertion minted for a different actor than the authenticated caller.
        assertion = _make_assertion(actor_id="mallory")
        with app.test_request_context(headers={IMPERSONATION_HEADER: assertion}):
            with pytest.raises(Exception) as exc_info:
                apply_impersonation_context(self._actor())
            assert exc_info.value.code == 403

    def test_realm_mismatch_forbidden(self, app):
        assertion = _make_assertion(realm="otherrealm")
        with app.test_request_context(headers={IMPERSONATION_HEADER: assertion}):
            with pytest.raises(Exception) as exc_info:
                apply_impersonation_context(self._actor())
            assert exc_info.value.code == 403

    def test_expired_assertion_unauthorized(self, app):
        assertion = _make_assertion(exp_delta=-10)
        with app.test_request_context(headers={IMPERSONATION_HEADER: assertion}):
            with pytest.raises(Exception) as exc_info:
                apply_impersonation_context(self._actor())
            assert exc_info.value.code == 401

    def test_wrong_key_unauthorized(self, app):
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        other_pem = other.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()
        assertion = _make_assertion(key=other_pem)
        with app.test_request_context(headers={IMPERSONATION_HEADER: assertion}):
            with pytest.raises(Exception) as exc_info:
                apply_impersonation_context(self._actor())
            assert exc_info.value.code == 401

    def test_no_key_configured_fails_closed(self, app):
        set_impersonation_public_key(None)
        assertion = _make_assertion()
        with app.test_request_context(headers={IMPERSONATION_HEADER: assertion}):
            with pytest.raises(Exception) as exc_info:
                apply_impersonation_context(self._actor())
            assert exc_info.value.code == 401


class TestHasPermission:
    @patch("optibroker_common.authentication.get_current_user_permissions")
    def test_user_with_permissions(self, mock_perms, app):
        mock_perms.return_value = {"user_id": "u1", "permissions": ["VIEW", "EDIT"], "realm": "r1"}

        with app.test_request_context():
            result = has_permission(["VIEW"], "RS256", "http://keycloak")
            assert result["user_id"] == "u1"

    @patch("optibroker_common.authentication.get_current_user_permissions")
    def test_missing_permission_aborts(self, mock_perms, app):
        mock_perms.return_value = {"user_id": "u1", "permissions": ["VIEW"], "realm": "r1"}

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                has_permission(["ADMIN"], "RS256", "http://keycloak")
            assert exc_info.value.code == 403

    @patch("optibroker_common.authentication.get_current_user_permissions")
    def test_secret_key_allowed(self, mock_perms, app):
        mock_perms.return_value = {
            "user": "sqs_feeder",
            "permissions": ["sqs_feeder_access"],
            "auth_method": "secret_key",
            "realm": "r1"
        }

        with app.test_request_context():
            result = has_permission([], "RS256", "http://keycloak", allow_secret_key=True)
            assert result["auth_method"] == "secret_key"

    @patch("optibroker_common.authentication.get_current_user_permissions")
    def test_secret_key_not_allowed_aborts(self, mock_perms, app):
        mock_perms.return_value = {
            "user": "sqs_feeder",
            "permissions": ["sqs_feeder_access"],
            "auth_method": "secret_key",
            "realm": "r1"
        }

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                has_permission([], "RS256", "http://keycloak", allow_secret_key=False)
            assert exc_info.value.code == 403

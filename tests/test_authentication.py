from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from optibroker_common.authentication import (
    get_bearer_token,
    get_public_key,
    verify_jwt_or_secret_key,
    get_current_user_permissions,
    has_permission,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture(autouse=True)
def clear_jwks_cache():
    from optibroker_common import authentication as auth_module
    auth_module._jwks_cache.invalidate()
    yield
    auth_module._jwks_cache.invalidate()


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

    @patch("optibroker_common.authentication.requests.get")
    @patch("optibroker_common.authentication.jwt.algorithms.RSAAlgorithm.from_jwk")
    def test_second_call_uses_cached_jwks(self, mock_from_jwk, mock_get, app):
        mock_openid = MagicMock()
        mock_openid.json.return_value = {"jwks_uri": "http://keycloak/jwks"}
        mock_jwks = MagicMock()
        mock_jwks.json.return_value = {"keys": [{"kid": "key1", "kty": "RSA"}]}
        mock_get.side_effect = [mock_openid, mock_jwks]
        mock_from_jwk.return_value = "public_key_value"

        with app.test_request_context():
            get_public_key("http://keycloak/realms/test", "key1", "http://keycloak")
            get_public_key("http://keycloak/realms/test", "key1", "http://keycloak")

        # JWKS fetched once (2 requests); second lookup served from cache.
        assert mock_get.call_count == 2

    @patch("optibroker_common.authentication.requests.get")
    @patch("optibroker_common.authentication.jwt.algorithms.RSAAlgorithm.from_jwk")
    def test_unknown_kid_refreshes_cached_jwks(self, mock_from_jwk, mock_get, app):
        # Warm the cache with key1.
        openid1 = MagicMock()
        openid1.json.return_value = {"jwks_uri": "http://keycloak/jwks"}
        jwks1 = MagicMock()
        jwks1.json.return_value = {"keys": [{"kid": "key1", "kty": "RSA"}]}
        # After rotation, key2 is available on refresh.
        openid2 = MagicMock()
        openid2.json.return_value = {"jwks_uri": "http://keycloak/jwks"}
        jwks2 = MagicMock()
        jwks2.json.return_value = {"keys": [{"kid": "key2", "kty": "RSA"}]}
        mock_get.side_effect = [openid1, jwks1, openid2, jwks2]
        mock_from_jwk.return_value = "rotated_key"

        with app.test_request_context():
            get_public_key("http://keycloak/realms/test", "key1", "http://keycloak")
            # key2 is unknown to the cached JWKS -> triggers a forced refresh.
            result = get_public_key("http://keycloak/realms/test", "key2", "http://keycloak")

        assert result == "rotated_key"
        assert mock_get.call_count == 4


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
                    get_realms_func=lambda force_refresh=False: ["goodrealm"]
                )
            assert exc_info.value.code == 401

    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_new_realm_accepted_after_force_refresh(self, mock_verify, app):
        mock_verify.return_value = {
            "sub": "user123",
            "realm_access": {"roles": []},
            "iss": "http://keycloak/realms/newrealm"
        }

        # Stale cache lacks the realm; a forced refresh returns it.
        def get_realms_func(force_refresh=False):
            return ["newrealm"] if force_refresh else ["oldrealm"]

        with app.test_request_context():
            result = get_current_user_permissions(
                "RS256", "http://keycloak", get_realms_func=get_realms_func
            )
            assert result["realm"] == "newrealm"

    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_legacy_realms_func_without_force_refresh(self, mock_verify, app):
        """A provider that doesn't accept force_refresh still works (backward compat)."""
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

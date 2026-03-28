from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from optibroker_common.keycloak import (
    get_keycloak_admin_token,
    get_keycloak_realms,
    create_keycloak_user,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


KC_PARAMS = {
    "server_url": "http://keycloak:8080",
    "client_id": "admin-cli",
    "admin_username": "admin",
    "admin_password": "password",
}


class TestGetKeycloakAdminToken:
    @patch("optibroker_common.keycloak.requests.post")
    def test_returns_token(self, mock_post, app):
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "tok123"}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        with app.test_request_context():
            token = get_keycloak_admin_token(**KC_PARAMS)
            assert token == "tok123"

    @patch("optibroker_common.keycloak.requests.post")
    def test_http_error_aborts_503(self, mock_post, app):
        import requests as req
        mock_post.side_effect = req.exceptions.HTTPError("auth failed")

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_keycloak_admin_token(**KC_PARAMS)
            assert exc_info.value.code == 503

    @patch("optibroker_common.keycloak.requests.post")
    def test_connection_error_aborts_500(self, mock_post, app):
        import requests as req
        mock_post.side_effect = req.exceptions.ConnectionError("refused")

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                get_keycloak_admin_token(**KC_PARAMS)
            assert exc_info.value.code == 500


class TestGetKeycloakRealms:
    @patch("optibroker_common.keycloak.requests.get")
    @patch("optibroker_common.keycloak.get_keycloak_admin_token")
    def test_returns_realms_excluding_master(self, mock_token, mock_get, app):
        mock_token.return_value = "tok123"
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"realm": "master"},
            {"realm": "tenant1"},
            {"realm": "tenant2"},
        ]
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        with app.test_request_context():
            realms = get_keycloak_realms(**KC_PARAMS)
            assert realms == ["tenant1", "tenant2"]
            assert "master" not in realms


class TestCreateKeycloakUser:
    @patch("optibroker_common.keycloak.requests.post")
    @patch("optibroker_common.keycloak.get_keycloak_admin_token")
    def test_creates_user_returns_id(self, mock_token, mock_post, app):
        mock_token.return_value = "tok123"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers = {"Location": "http://keycloak/admin/realms/test/users/user-uuid-123"}
        mock_post.return_value = mock_response

        with app.test_request_context():
            user_id = create_keycloak_user(
                **KC_PARAMS, realm="test", forename="John", surname="Doe", email="john@example.com"
            )
            assert user_id == "user-uuid-123"

    @patch("optibroker_common.keycloak.requests.post")
    @patch("optibroker_common.keycloak.get_keycloak_admin_token")
    def test_auto_generates_username(self, mock_token, mock_post, app):
        mock_token.return_value = "tok123"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers = {"Location": "http://keycloak/users/uid1"}
        mock_post.return_value = mock_response

        with app.test_request_context():
            create_keycloak_user(**KC_PARAMS, realm="test", forename="Jane", surname="Smith")

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["username"] == "jane.smith"

    @patch("optibroker_common.keycloak.requests.post")
    @patch("optibroker_common.keycloak.get_keycloak_admin_token")
    def test_uses_provided_username(self, mock_token, mock_post, app):
        mock_token.return_value = "tok123"
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.headers = {"Location": "http://keycloak/users/uid1"}
        mock_post.return_value = mock_response

        with app.test_request_context():
            create_keycloak_user(**KC_PARAMS, realm="test", forename="Jane", surname="Smith", username="custom_user")

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["username"] == "custom_user"

    @patch("optibroker_common.keycloak.requests.post")
    @patch("optibroker_common.keycloak.get_keycloak_admin_token")
    def test_http_error_aborts_503(self, mock_token, mock_post, app):
        import requests as req
        mock_token.return_value = "tok123"
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = req.exceptions.HTTPError("conflict")
        mock_response.status_code = 409
        mock_response.text = "User exists"
        mock_post.return_value = mock_response

        with app.test_request_context():
            with pytest.raises(Exception) as exc_info:
                create_keycloak_user(**KC_PARAMS, realm="test", forename="John", surname="Doe")
            assert exc_info.value.code == 503

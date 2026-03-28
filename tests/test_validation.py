from unittest.mock import patch

import pytest
from flask import Flask

from optibroker_common.validation import configure, get_current_user, _auth_config


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


@pytest.fixture(autouse=True)
def reset_config():
    _auth_config.clear()
    yield
    _auth_config.clear()


class TestConfigure:
    def test_sets_config(self):
        configure("RS256", "http://keycloak", secret_keys=["key1"])
        assert _auth_config["algorithm"] == "RS256"
        assert _auth_config["keycloak_server_url"] == "http://keycloak"
        assert _auth_config["secret_keys"] == ["key1"]

    def test_updates_existing_config(self):
        configure("RS256", "http://keycloak1")
        configure("RS512", "http://keycloak2")
        assert _auth_config["algorithm"] == "RS512"
        assert _auth_config["keycloak_server_url"] == "http://keycloak2"


class TestGetCurrentUser:
    def test_raises_without_configure(self, app):
        @get_current_user()
        def my_view(**kwargs):
            return "ok"

        with app.test_request_context(), pytest.raises(RuntimeError, match="configure"):
            my_view()

    @patch("optibroker_common.validation.has_permission")
    def test_injects_current_user(self, mock_has_perm, app):
        configure("RS256", "http://keycloak")
        mock_has_perm.return_value = {"user_id": "u1", "permissions": ["VIEW"], "realm": "r1"}

        @get_current_user(required_permissions=["VIEW"])
        def my_view(**kwargs):
            return kwargs["current_user"]

        with app.test_request_context():
            result = my_view()
            assert result["user_id"] == "u1"

        mock_has_perm.assert_called_once_with(
            ["VIEW"],
            algorithm="RS256",
            keycloak_server_url="http://keycloak",
            secret_keys=None,
            allow_secret_key=False,
            get_realms_func=None,
        )

    @patch("optibroker_common.validation.has_permission")
    def test_allow_secret_key_passed(self, mock_has_perm, app):
        configure("RS256", "http://keycloak", secret_keys=["sk1"])
        mock_has_perm.return_value = {"auth_method": "secret_key"}

        @get_current_user(allow_secret_key=True)
        def my_view(**kwargs):
            return kwargs["current_user"]

        with app.test_request_context():
            result = my_view()
            assert result["auth_method"] == "secret_key"

        mock_has_perm.assert_called_once_with(
            [],
            algorithm="RS256",
            keycloak_server_url="http://keycloak",
            secret_keys=["sk1"],
            allow_secret_key=True,
            get_realms_func=None,
        )

    @patch("optibroker_common.validation.has_permission")
    def test_default_permissions_empty_list(self, mock_has_perm, app):
        configure("RS256", "http://keycloak")
        mock_has_perm.return_value = {"user_id": "u1", "permissions": [], "realm": "r1"}

        @get_current_user()
        def my_view(**kwargs):
            return kwargs["current_user"]

        with app.test_request_context():
            my_view()

        assert mock_has_perm.call_args[0][0] == []

    @patch("optibroker_common.validation.has_permission")
    def test_preserves_function_name(self, mock_has_perm, app):
        configure("RS256", "http://keycloak")
        mock_has_perm.return_value = {}

        @get_current_user()
        def my_special_view(**kwargs):
            pass

        assert my_special_view.__name__ == "my_special_view"

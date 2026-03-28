import json

import pytest
from flask import Flask
from werkzeug.exceptions import NotFound

from optibroker_common.exceptions import (
    ApplicationError,
    application_error,
    unhandled_exception,
    register_exception_handlers,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


class TestApplicationError:
    def test_stores_attributes(self):
        err = ApplicationError("something broke", "ERR001", 400)
        assert err.message == "something broke"
        assert err.code == "ERR001"
        assert err.http_code == 400

    def test_default_http_code(self):
        err = ApplicationError("fail", "ERR002")
        assert err.http_code == 500

    def test_is_exception(self):
        err = ApplicationError("fail", "ERR003")
        assert isinstance(err, Exception)


class TestApplicationErrorHandler:
    def test_returns_json_response(self, app):
        with app.app_context():
            err = ApplicationError("bad input", "VALIDATION_ERR", 422)
            resp = application_error(err)
            data = json.loads(resp.data)

            assert resp.status_code == 422
            assert data["error_message"] == "bad input"
            assert data["error_code"] == "VALIDATION_ERR"


class TestUnhandledException:
    def test_http_exception_returns_json(self, app):
        with app.app_context():
            err = NotFound("page missing")
            resp = unhandled_exception(err)
            data = json.loads(resp.data)

            assert resp.status_code == 404
            assert data["error_code"] == 404

    def test_generic_exception_returns_500(self, app):
        with app.app_context():
            err = ValueError("unexpected")
            resp = unhandled_exception(err)
            data = json.loads(resp.data)

            assert resp.status_code == 500
            assert data["error_message"] == "Unexpected error."
            assert data["error_code"] == "XXX"


class TestRegisterExceptionHandlers:
    def test_registers_handlers(self, app):
        register_exception_handlers(app)

        # Verify by triggering an ApplicationError through the app
        @app.route("/test-app-error")
        def raise_app_error():
            raise ApplicationError("test error", "TEST001", 418)

        client = app.test_client()
        resp = client.get("/test-app-error")
        data = json.loads(resp.data)

        assert resp.status_code == 418
        assert data["error_message"] == "test error"
        assert data["error_code"] == "TEST001"

    def test_handles_generic_exception(self, app):
        register_exception_handlers(app)

        @app.route("/test-generic-error")
        def raise_generic():
            raise RuntimeError("boom")

        client = app.test_client()
        resp = client.get("/test-generic-error")
        data = json.loads(resp.data)

        assert resp.status_code == 500
        assert data["error_message"] == "Unexpected error."

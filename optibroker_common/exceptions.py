import json
import logging

from flask import Response, current_app
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApplicationError(Exception):
    def __init__(self, message, code, http_code=500):
        super().__init__(message, code, http_code)
        self.message = message
        self.http_code = http_code
        self.code = code


def application_error(e):
    return Response(response=json.dumps({"error_message": e.message, "error_code": e.code}), status=e.http_code)


def unhandled_exception(e):
    if isinstance(e, HTTPException):
        return Response(
            response=json.dumps({"error_message": e.description, "error_code": e.code}),
            status=e.code,
            content_type="application/json"
        )
    current_app.logger.exception('Unhandled Exception: %s', repr(e))
    return Response(response=json.dumps({"error_message": "Unexpected error.", "error_code": "XXX"}), status=500)


def register_exception_handlers(app):
    app.register_error_handler(ApplicationError, application_error)
    app.register_error_handler(Exception, unhandled_exception)

    app.logger.info("Exception handlers registered")

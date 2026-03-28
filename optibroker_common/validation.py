import logging
from functools import wraps

from optibroker_common.authentication import has_permission

logger = logging.getLogger(__name__)

_auth_config = {}


def configure(algorithm, keycloak_server_url, secret_keys=None, get_realms_func=None):
    """
    Call this once at app startup to configure auth settings for the validation decorator.

    Args:
        algorithm: JWT algorithm (e.g. 'RS256').
        keycloak_server_url: Base URL of the Keycloak server.
        secret_keys: Optional list of valid secret keys for SecretKey auth.
        get_realms_func: Optional callable that returns a list of valid realm names.
    """
    _auth_config.update({
        "algorithm": algorithm,
        "keycloak_server_url": keycloak_server_url,
        "secret_keys": secret_keys,
        "get_realms_func": get_realms_func,
    })


def get_current_user(required_permissions=None, allow_secret_key=False):
    """
    Decorator to retrieve the current user and check their permissions.
    Restricts routes to specific permissions and optionally allows sqs_feeder_access.

    Must call configure() before using this decorator.
    """
    if required_permissions is None:
        required_permissions = []

    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not _auth_config:
                raise RuntimeError(
                    "optibroker_common.validation.configure() must be called before using get_current_user"
                )

            current_user = has_permission(
                required_permissions,
                algorithm=_auth_config["algorithm"],
                keycloak_server_url=_auth_config["keycloak_server_url"],
                secret_keys=_auth_config.get("secret_keys"),
                allow_secret_key=allow_secret_key,
                get_realms_func=_auth_config.get("get_realms_func"),
            )
            kwargs["current_user"] = current_user
            return f(*args, **kwargs)

        return wrapper
    return decorator

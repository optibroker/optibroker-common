import json
import logging

import jwt
import requests
from flask import request, abort
from jwt.exceptions import InvalidSignatureError, ExpiredSignatureError

from optibroker_common.cache import TTLCache

logger = logging.getLogger(__name__)

# In-memory cache of Keycloak JWKS (signing certs), keyed by issuer URL. Avoids
# fetching the OpenID config and JWKS from Keycloak on every request.
_jwks_cache = TTLCache()


def _fetch_jwks(issuer_url):
    """Fetch the JWKS document for an issuer via its OpenID configuration."""
    openid_config_url = f"{issuer_url}/.well-known/openid-configuration"
    openid_config = requests.get(openid_config_url).json()
    jwks_uri = openid_config['jwks_uri']
    return requests.get(jwks_uri).json()


def _get_jwks(issuer_url, force_refresh=False):
    """
    Return the JWKS for an issuer, using the in-memory cache when possible.

    Returns a ``(jwks, from_cache)`` tuple. ``from_cache`` is True when the
    result came from a warm cache entry (rather than a live fetch), which lets
    callers decide whether a missing key is worth a forced refresh.
    """
    if not force_refresh:
        cached = _jwks_cache.get(issuer_url)
        if cached is not None:
            return cached, True

    jwks = _fetch_jwks(issuer_url)
    _jwks_cache.set(issuer_url, jwks)
    return jwks, False


def _find_signing_key(jwks, kid):
    """Return the JWK dict matching ``kid`` from a JWKS document, or None."""
    for key in jwks.get('keys', []):
        if key.get('kid') == kid:
            return key
    return None


def _get_realms(get_realms_func, force_refresh=False):
    """
    Call a realm-provider function, passing ``force_refresh`` when supported.

    The provider is configured by each service and may or may not accept a
    ``force_refresh`` argument; fall back to a plain call for older providers so
    this stays backward compatible.
    """
    try:
        return get_realms_func(force_refresh=force_refresh)
    except TypeError:
        return get_realms_func()


def get_bearer_token():
    """
    Retrieve the Bearer token from the Authorization header.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    else:
        abort(401, description="Authorization header is missing or invalid.")


def get_public_key(issuer_url, kid, keycloak_server_url):
    """
    Retrieve the public key from Keycloak's OpenID configuration based on the key ID (kid).
    """
    issuer_url = issuer_url.replace('http://localhost:8080', keycloak_server_url)
    try:
        jwks, from_cache = _get_jwks(issuer_url)
        key = _find_signing_key(jwks, kid)

        # If the key isn't in a cached JWKS, Keycloak may have rotated its
        # signing keys since we cached them. Refresh once before giving up so a
        # key rotation doesn't require restarting the service.
        if key is None and from_cache:
            jwks, _ = _get_jwks(issuer_url, force_refresh=True)
            key = _find_signing_key(jwks, kid)

        if key is not None:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
    except requests.RequestException as req_err:
        abort(503, description=f"Failed to retrieve OpenID configuration: {req_err}")

    abort(400, description="Public key not found.")


def verify_jwt_or_secret_key(algorithm, keycloak_server_url, secret_keys=None):
    """
    Verify either a JWT token or a secret key.

    Args:
        algorithm: JWT algorithm (e.g. 'RS256').
        keycloak_server_url: Base URL of the Keycloak server.
        secret_keys: Optional list of valid secret keys for SecretKey auth.
    """
    if secret_keys is None:
        secret_keys = []

    auth_header = request.headers.get("Authorization")

    if not auth_header:
        abort(401, description="Authorization header is missing.")

    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        try:
            unverified_header = jwt.get_unverified_header(token)
            unverified_claims = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})

            kid = unverified_header['kid']
            issuer = unverified_claims['iss']

            public_key = get_public_key(issuer, kid, keycloak_server_url)

            verified_payload = jwt.decode(
                token, public_key, algorithms=[algorithm],
                options={"verify_aud": False}
            )
            return verified_payload

        except InvalidSignatureError:
            abort(401, description="Invalid token signature.")
        except ExpiredSignatureError:
            abort(401, description="Expired token signature.")
        except jwt.PyJWTError as jwt_err:
            abort(401, description=f"Token verification failed: {jwt_err}")

    elif auth_header.startswith("SecretKey "):
        secret_key = auth_header.split(" ")[1]
        if secret_key in secret_keys:
            return {
                "user": "sqs_feeder",
                "permissions": ["sqs_feeder_access"],
                "auth_method": "secret_key",
                "realm": request.headers.get("X-Keycloak-Realm")
            }
        else:
            abort(403, description="Invalid secret key.")

    abort(401, description="Authorization header is invalid.")


def get_current_user_permissions(algorithm, keycloak_server_url, secret_keys=None, get_realms_func=None):
    """
    Extract user permissions from the verified JWT payload.

    Args:
        algorithm: JWT algorithm.
        keycloak_server_url: Base URL of the Keycloak server.
        secret_keys: Optional list of valid secret keys.
        get_realms_func: Optional callable that returns a list of valid realm names.
    """
    verified_payload = verify_jwt_or_secret_key(algorithm, keycloak_server_url, secret_keys)

    if verified_payload.get('auth_method') != "secret_key":
        user_id = verified_payload.get("sub")
        roles = verified_payload.get("realm_access", {}).get("roles", [])
        realm_name = verified_payload.get("iss").split("/realms/")[-1]

        if not user_id:
            abort(401, description="Invalid token: Missing user_id.")

        # The realm may have been added to Keycloak after the realm list was
        # cached. If it isn't in the cached list, force a refresh before
        # rejecting so a new realm doesn't require restarting every API.
        if (get_realms_func is not None
                and realm_name not in get_realms_func()
                and realm_name not in _get_realms(get_realms_func, force_refresh=True)):
            abort(401, description="Invalid Realm: not in list of valid Realms.")

        return {"user_id": user_id, "permissions": roles, "realm": realm_name}

    return verified_payload


def has_permission(required_permissions, algorithm, keycloak_server_url,
                   secret_keys=None, allow_secret_key=False, get_realms_func=None):
    """
    Check if the current user has the required permissions.

    Args:
        required_permissions: List of permission strings required.
        algorithm: JWT algorithm.
        keycloak_server_url: Base URL of the Keycloak server.
        secret_keys: Optional list of valid secret keys.
        allow_secret_key: Whether to allow secret key auth on this route.
        get_realms_func: Optional callable that returns a list of valid realm names.
    """
    current_user = get_current_user_permissions(algorithm, keycloak_server_url, secret_keys, get_realms_func)

    user_permissions = current_user.get('permissions', [])
    auth_method = current_user.get('auth_method')

    if auth_method == "secret_key":
        if "sqs_feeder_access" in user_permissions and allow_secret_key:
            return current_user
        else:
            abort(403, description="SQS Feeder is not authorized for this route.")
    else:
        for permission in required_permissions:
            if permission not in user_permissions:
                abort(403, description=f"Missing permission: {permission}")

    return current_user

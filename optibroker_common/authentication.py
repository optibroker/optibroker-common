import json
import logging

import jwt
import requests
from flask import request, abort
from jwt.exceptions import InvalidSignatureError, ExpiredSignatureError

logger = logging.getLogger(__name__)


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
    openid_config_url = f"{issuer_url}/.well-known/openid-configuration"
    try:
        openid_config = requests.get(openid_config_url).json()
        jwks_uri = openid_config['jwks_uri']
        jwks = requests.get(jwks_uri).json()

        for key in jwks['keys']:
            if key['kid'] == kid:
                if isinstance(key, dict):
                    key = json.dumps(key)
                return jwt.algorithms.RSAAlgorithm.from_jwk(key)
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


def extract_actor(payload):
    """Return the real actor id from an RFC 8693 ``act`` (actor) claim.

    Keycloak's token-exchange impersonation flow embeds the user who initiated
    the impersonation in the token's ``act`` claim (``{"act": {"sub": "<id>"}}``).
    When a user "Steve" is acting as "Sarah", the token's ``sub`` is Sarah and
    ``act.sub`` is Steve.

    Returns ``(real_actor_id, is_impersonating)``: the actor's user id and True
    when an actor claim is present, otherwise ``(None, False)``.
    """
    act = payload.get("act")
    if isinstance(act, dict):
        actor_sub = act.get("sub")
        if actor_sub:
            return actor_sub, True
    return None, False


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

        if get_realms_func is not None and realm_name not in get_realms_func():
            abort(401, description="Invalid Realm: not in list of valid Realms.")

        # When the token was minted via impersonation (Keycloak token exchange),
        # user_id is the impersonated subject and real_actor_id is who is really
        # acting. For non-impersonated tokens the two are the same, so callers
        # can always attribute audit to real_actor_id.
        real_actor_id, is_impersonating = extract_actor(verified_payload)
        return {
            "user_id": user_id,
            "permissions": roles,
            "realm": realm_name,
            "is_impersonating": is_impersonating,
            "real_actor_id": real_actor_id or user_id,
        }

    return verified_payload


def get_impersonation_context():
    """Best-effort impersonation info for the current request, for audit use.

    Reads the bearer token from the request and decodes it WITHOUT verifying the
    signature -- the request has already been authenticated upstream; this is
    enrichment only. Returns a dict with ``is_impersonating``, ``real_actor_id``
    and ``impersonated_user_id``. When there is no impersonation (or no usable
    token) ``is_impersonating`` is False and ``real_actor_id`` falls back to the
    token subject.
    """
    default = {"is_impersonating": False, "real_actor_id": None, "impersonated_user_id": None}

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return default

    token = auth_header.split(" ")[1]
    try:
        claims = jwt.decode(token, options={"verify_signature": False, "verify_aud": False})
    except jwt.PyJWTError:
        return default

    subject = claims.get("sub")
    actor_id, is_impersonating = extract_actor(claims)
    return {
        "is_impersonating": is_impersonating,
        "real_actor_id": actor_id or subject,
        "impersonated_user_id": subject,
    }


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

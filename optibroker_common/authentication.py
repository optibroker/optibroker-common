import base64
import json
import logging
import os
import threading
import time

import jwt
import requests
from flask import request, abort
from jwt.exceptions import InvalidSignatureError, ExpiredSignatureError

logger = logging.getLogger(__name__)

# Header carrying an application-level impersonation assertion. The caller keeps
# their own (actor) Keycloak JWT in Authorization; this header, minted and signed
# by permissions-api, states which subject they are acting as. See
# apply_impersonation_context().
IMPERSONATION_HEADER = "X-Impersonation-Context"

# PEM public key used to verify impersonation assertions (RS256). The matching
# private key lives ONLY in permissions-api, which mints the assertions; every
# other service only ever verifies. Set via
# optibroker_common.validation.configure(impersonation_public_key=...) or the
# IMPERSONATION_PUBLIC_KEY environment variable.
_impersonation_public_key = None


def _normalise_pem(value):
    """Return a real PEM string from a PEM (optionally with escaped newlines) or a
    base64-encoded PEM. Returns None for empty input."""
    if not value:
        return None
    value = value.strip()
    if "-----BEGIN" in value:
        return value.replace("\\n", "\n")
    try:
        return base64.b64decode(value).decode("utf-8")
    except Exception:
        return value


def set_impersonation_public_key(value):
    """Configure the public key used to verify impersonation assertions."""
    global _impersonation_public_key
    _impersonation_public_key = _normalise_pem(value)


def _get_impersonation_public_key():
    if _impersonation_public_key:
        return _impersonation_public_key
    return _normalise_pem(os.environ.get("IMPERSONATION_PUBLIC_KEY"))


def get_bearer_token():
    """
    Retrieve the Bearer token from the Authorization header.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.split(" ")[1]
    else:
        abort(401, description="Authorization header is missing or invalid.")


def realm_from_trusted_issuer(issuer_url, keycloak_server_url):
    """The realm named by `issuer_url`, or 401 if that issuer is not ours.

    The issuer claim arrives on an UNVERIFIED token -- it is read before any
    signature has been checked, because it is what tells us which key to check
    the signature with. So it is an attacker's string until proven otherwise.

    Taking it at its word meant anyone could host their own JWKS, set
    iss to https://their-server/realms/<a-real-realm>, sign a token with their
    own key, and have us fetch their key and accept it. The realm allow-list did
    not help: the realm name was read from that same string, so any real realm
    passed. It was a complete authentication bypass on every service using this
    library -- the attacker chose the tenant and the roles.

    An issuer is ours only when it is exactly <keycloak_server_url>/realms/<realm>
    for one realm segment. Requiring "/realms/" immediately after the configured
    URL is what stops a look-alike host: https://our-keycloak.example.com.evil
    does not match https://our-keycloak.example.com + "/realms/".
    """
    server = (keycloak_server_url or '').rstrip('/')
    if not server:
        abort(401, description="Untrusted token issuer.")

    # Tokens minted against a Keycloak reached on localhost carry that as their
    # issuer. Rewritten before the check, never after it.
    issuer = (issuer_url or '').replace('http://localhost:8080', server)

    prefix = f"{server}/realms/"
    if not issuer.startswith(prefix):
        logger.warning("Rejected token from untrusted issuer: %s", issuer)
        abort(401, description="Untrusted token issuer.")

    realm = issuer[len(prefix):]
    # Exactly one path segment. Anything else is either not a Keycloak issuer or
    # is reaching for somewhere else on the server.
    if not realm or '/' in realm or realm in ('.', '..'):
        logger.warning("Rejected token from untrusted issuer: %s", issuer)
        abort(401, description="Untrusted token issuer.")

    return realm


# ── Caches ─────────────────────────────────────────────────────────────────
#
# Verifying a token used to cost four round trips to Keycloak on every request:
# an admin login and the realm list (for get_realms_func), then the realm's
# openid-configuration and its JWKS. About 0.7s per call, on every API (OB-78).
#
# Both are now cached per process. What is cached, and what is not:
#
# - Signing keys, per (trusted server, realm). The realm comes from
#   realm_from_trusted_issuer(), which has already refused any issuer that is
#   not ours, so an attacker-chosen `iss` can never select, populate or poison
#   an entry (OB-55). A key is only ever looked up in its own realm's entry.
# - The valid-realm list, per get_realms_func.
#
# A miss is never trusted as final. An unknown `kid` (keys rotated, or the realm
# was deleted and recreated) and an unknown realm (just onboarded) each trigger
# a refetch -- but at most once per REFRESH_MIN_INTERVAL for that entry, so a
# caller spraying made-up kids or realm names cannot turn the cache into a way
# of hammering Keycloak. Within that window the miss is simply refused.
#
# A realm that drops out of the list on refresh also loses its cached keys, so a
# deleted tenant's tokens stop verifying within REALMS_TTL.

JWKS_TTL = int(os.environ.get("KEYCLOAK_JWKS_CACHE_TTL", "300"))
REALMS_TTL = int(os.environ.get("KEYCLOAK_REALMS_CACHE_TTL", "60"))
REFRESH_MIN_INTERVAL = int(os.environ.get("KEYCLOAK_CACHE_MIN_REFRESH", "10"))

_cache_lock = threading.Lock()
_jwks_cache = {}    # (server, realm) -> {"keys": {kid: jwk_dict}, "fetched": t}
_realms_cache = {}  # get_realms_func -> {"realms": set, "fetched": t}


def clear_caches():
    """Forget every cached key and realm list (tests, or after a known rotation)."""
    with _cache_lock:
        _jwks_cache.clear()
        _realms_cache.clear()


def _fetch_jwks(server, realm):
    """The realm's signing keys, straight from our own Keycloak, as {kid: jwk}."""
    openid_config_url = f"{server}/realms/{realm}/.well-known/openid-configuration"
    try:
        openid_config = requests.get(openid_config_url).json()
        jwks_uri = openid_config['jwks_uri']
        # Our own Keycloak answered, so its jwks_uri is trustworthy -- but a
        # misconfigured or compromised realm should not be able to send us
        # somewhere else for the key either.
        if not jwks_uri.startswith(f"{server}/"):
            logger.warning("Keycloak returned a JWKS URI outside %s: %s", server, jwks_uri)
            abort(401, description="Untrusted token issuer.")
        jwks = requests.get(jwks_uri).json()
    except requests.RequestException as req_err:
        abort(503, description=f"Failed to retrieve OpenID configuration: {req_err}")
    return {key['kid']: key for key in jwks['keys']}


def get_public_key(issuer_url, kid, keycloak_server_url):
    """
    Retrieve the public key for `kid` from the realm named by a trusted issuer.
    """
    # Built from the Keycloak we are configured to trust and the realm it named,
    # never from the URL in the token.
    realm = realm_from_trusted_issuer(issuer_url, keycloak_server_url)
    server = keycloak_server_url.rstrip('/')
    cache_key = (server, realm)
    now = time.monotonic()

    with _cache_lock:
        entry = _jwks_cache.get(cache_key)
        fresh = entry is not None and now - entry["fetched"] < JWKS_TTL
        if fresh and kid in entry["keys"]:
            key = entry["keys"][kid]
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key))
        # Stale, or a kid we have not seen. Refetch -- unless we did so moments
        # ago, in which case the kid is simply unknown.
        may_refetch = entry is None or now - entry["fetched"] >= REFRESH_MIN_INTERVAL

    if may_refetch:
        keys = _fetch_jwks(server, realm)
        with _cache_lock:
            _jwks_cache[cache_key] = {"keys": keys, "fetched": time.monotonic()}
        if kid in keys:
            return jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(keys[kid]))

    abort(400, description="Public key not found.")


def realm_is_valid(realm_name, get_realms_func):
    """Whether `realm_name` is in get_realms_func()'s list, cached for REALMS_TTL.

    A realm missing from a fresh list triggers one rate-limited refresh, so a
    newly onboarded tenant is accepted at once. A realm gone from the refreshed
    list also has its signing keys evicted.
    """
    now = time.monotonic()
    with _cache_lock:
        entry = _realms_cache.get(get_realms_func)
        if entry is not None and now - entry["fetched"] < REALMS_TTL and realm_name in entry["realms"]:
            return True
        may_refetch = entry is None or now - entry["fetched"] >= REFRESH_MIN_INTERVAL \
            or now - entry["fetched"] >= REALMS_TTL
        previous = entry["realms"] if entry else set()

    if not may_refetch:
        return False

    realms = set(get_realms_func())
    with _cache_lock:
        _realms_cache[get_realms_func] = {"realms": realms, "fetched": time.monotonic()}
        for gone in previous - realms:
            for cache_key in [k for k in _jwks_cache if k[1] == gone]:
                del _jwks_cache[cache_key]
    return realm_name in realms


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
        # Same rule as the key fetch: the realm is whatever our own Keycloak
        # named, not whatever the string happened to end with.
        realm_name = realm_from_trusted_issuer(verified_payload.get("iss"), keycloak_server_url)

        if not user_id:
            abort(401, description="Invalid token: Missing user_id.")

        if get_realms_func is not None and not realm_is_valid(realm_name, get_realms_func):
            abort(401, description="Invalid Realm: not in list of valid Realms.")

        # When the token was minted via impersonation (Keycloak token exchange),
        # user_id is the impersonated subject and real_actor_id is who is really
        # acting. For non-impersonated tokens the two are the same, so callers
        # can always attribute audit to real_actor_id.
        real_actor_id, is_impersonating = extract_actor(verified_payload)
        current_user = {
            "user_id": user_id,
            "permissions": roles,
            "realm": realm_name,
            "is_impersonating": is_impersonating,
            "real_actor_id": real_actor_id or user_id,
        }

        # Application-level impersonation: if the caller also presents a valid,
        # signed impersonation assertion, resolve the request to the subject.
        return apply_impersonation_context(current_user)

    return verified_payload


def apply_impersonation_context(current_user):
    """Resolve the request to an impersonated subject when a valid assertion is
    present, otherwise return ``current_user`` unchanged.

    The caller authenticates as themselves (their own Keycloak JWT). An optional
    ``X-Impersonation-Context`` header -- a short-lived JWT minted and RS256-signed
    by permissions-api after it checked the caller's impersonation grant -- states
    which subject they are acting as, and carries the subject's realm roles so
    downstream permission checks apply the subject's access, not the actor's.

    Security properties enforced here:
      * signature verified with the impersonation public key, algorithm pinned to
        RS256 (no alg-confusion / ``none``);
      * expiry enforced (assertions are short-lived, re-minted as needed);
      * bound to the caller -- the assertion's ``actor_id`` must equal the
        authenticated user's id, so it cannot be replayed by anyone else;
      * realm-scoped -- must match the caller's realm.

    Fails closed: if an assertion is present but cannot be verified (or this
    service has no public key configured) the request is rejected, so a broken or
    forged header can never fall through and be treated as the actor.
    """
    assertion = request.headers.get(IMPERSONATION_HEADER)
    if not assertion:
        return current_user

    public_key = _get_impersonation_public_key()
    if not public_key:
        abort(401, description="Impersonation is not configured on this service.")

    try:
        claims = jwt.decode(assertion, public_key, algorithms=["RS256"])
    except ExpiredSignatureError:
        abort(401, description="Impersonation context has expired.")
    except jwt.PyJWTError as err:
        abort(401, description=f"Invalid impersonation context: {err}")

    actor_id = claims.get("actor_id")
    subject_id = claims.get("subject_id")
    assertion_realm = claims.get("realm")
    subject_roles = claims.get("roles", [])

    if not actor_id or not subject_id:
        abort(401, description="Malformed impersonation context.")

    # The assertion may only be used by the actor it was minted for, in-realm.
    if actor_id != current_user.get("user_id"):
        abort(403, description="Impersonation context does not belong to the caller.")
    if assertion_realm and assertion_realm != current_user.get("realm"):
        abort(403, description="Impersonation context realm mismatch.")

    return {
        **current_user,
        "user_id": subject_id,
        "permissions": subject_roles,
        "is_impersonating": True,
        "real_actor_id": actor_id,
        "impersonator_id": actor_id,
    }


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

    # Application-level impersonation assertion is authoritative when present.
    # Decoded WITHOUT verifying the signature -- this is audit enrichment only;
    # the authoritative verification already happened in apply_impersonation_context.
    assertion = request.headers.get(IMPERSONATION_HEADER)
    if assertion:
        try:
            claims = jwt.decode(assertion, options={"verify_signature": False})
            subject = claims.get("subject_id")
            actor = claims.get("actor_id")
            if subject and actor:
                return {
                    "is_impersonating": True,
                    "real_actor_id": actor,
                    "impersonated_user_id": subject,
                }
        except jwt.PyJWTError:
            pass

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

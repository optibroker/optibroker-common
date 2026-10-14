"""OB-253: current_user carries the caller's display name, from the verified
token, so services can attribute what someone did (activity authors, who
confirmed a vulnerability). It never names the impersonated subject as the
person who acted."""
from unittest.mock import patch

import pytest
from flask import Flask

from optibroker_common.authentication import (
    IMPERSONATION_HEADER,
    get_current_user_permissions,
    set_impersonation_public_key,
)
from tests.test_authentication import _IMP_PUBLIC_PEM, _make_assertion


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    return app


def token(**claims):
    return {"sub": "steve", "realm_access": {"roles": ["staff"]},
            "iss": "http://keycloak/realms/testrealm", **claims}


def current_user(app, payload, headers=None):
    with patch("optibroker_common.authentication.verify_jwt_or_secret_key", return_value=payload), \
            app.test_request_context(headers=headers or {}):
        return get_current_user_permissions("RS256", "http://keycloak")


@pytest.mark.parametrize("claims,name,username", [
    ({"name": "Steve Adviser", "preferred_username": "steve.a"}, "Steve Adviser", "steve.a"),
    ({"given_name": "Steve", "family_name": "Adviser"}, "Steve Adviser", None),
    ({"given_name": "Steve"}, "Steve", None),
    ({"preferred_username": "steve.a"}, None, "steve.a"),
    ({"name": "  ", "preferred_username": " steve.a "}, None, "steve.a"),
    ({}, None, None),
])
def test_the_name_comes_from_the_verified_token(app, claims, name, username):
    user = current_user(app, token(**claims))
    assert (user["name"], user["preferred_username"]) == (name, username)


def test_the_rest_of_current_user_is_unchanged(app):
    user = current_user(app, token(name="Steve Adviser"))
    assert user == {"user_id": "steve", "permissions": ["staff"], "realm": "testrealm",
                    "is_impersonating": False, "real_actor_id": "steve",
                    "name": "Steve Adviser", "preferred_username": None}


def test_under_token_exchange_impersonation_the_subject_is_not_named_as_the_actor(app):
    """The token's sub and name claims are the subject's (Sarah); the actor
    (Steve) is only in act.sub. Naming Sarah would credit her with Steve's
    actions, so no name is given; real_actor_id still identifies Steve."""
    user = current_user(app, {**token(name="Sarah Client", preferred_username="sarah"),
                              "sub": "sarah", "act": {"sub": "steve"}})
    assert user["is_impersonating"] is True and user["real_actor_id"] == "steve"
    assert (user["name"], user["preferred_username"]) == (None, None)


def test_under_app_level_impersonation_the_actor_keeps_their_own_name(app):
    """The bearer token is the actor's own; the assertion switches user_id to
    the subject. The name stays the actor's, matching real_actor_id."""
    set_impersonation_public_key(_IMP_PUBLIC_PEM)
    try:
        user = current_user(app, token(name="Steve Adviser", preferred_username="steve.a"),
                            headers={IMPERSONATION_HEADER: _make_assertion(actor_id="steve", subject_id="sarah")})
    finally:
        set_impersonation_public_key(None)
    assert (user["user_id"], user["real_actor_id"], user["is_impersonating"]) == ("sarah", "steve", True)
    assert (user["name"], user["preferred_username"]) == ("Steve Adviser", "steve.a")


def test_a_service_key_has_no_name(app):
    user = current_user(app, {"user": "sqs_feeder", "auth_method": "secret_key", "realm": "testrealm"})
    assert "name" not in user

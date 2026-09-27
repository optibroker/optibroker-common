"""OB-78: signing keys and the realm list are cached, without weakening OB-55.

Each case below is one of the merge criteria QA set on the ticket.
"""
import json
from unittest.mock import MagicMock, patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from flask import Flask
from werkzeug.exceptions import HTTPException

from optibroker_common import authentication as auth

SERVER = "https://keycloak.example.com"


@pytest.fixture
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    with app.app_context():
        yield app


def _jwk(kid):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk["kid"] = kid
    return jwk


KEY_A, KEY_B, KEY_OTHER_REALM = _jwk("a"), _jwk("b"), _jwk("a")


class FakeKeycloak:
    """Serves openid-configuration + JWKS per realm and counts the calls."""

    def __init__(self, keys_by_realm):
        self.keys_by_realm = keys_by_realm
        self.calls = []

    def get(self, url, *args, **kwargs):
        self.calls.append(url)
        realm = url.split("/realms/")[1].split("/")[0]
        resp = MagicMock()
        if url.endswith("/.well-known/openid-configuration"):
            resp.json.return_value = {"jwks_uri": f"{SERVER}/realms/{realm}/protocol/openid-connect/certs"}
        else:
            resp.json.return_value = {"keys": self.keys_by_realm.get(realm, [])}
        return resp


@pytest.fixture
def keycloak(monkeypatch):
    kc = FakeKeycloak({"fsw": [KEY_A], "other": [KEY_OTHER_REALM]})
    monkeypatch.setattr(auth.requests, "get", kc.get)
    return kc


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(auth.time, "monotonic", lambda: now[0])
    return now


def _key(kid, realm="fsw"):
    return auth.get_public_key(f"{SERVER}/realms/{realm}", kid, SERVER)


class TestSigningKeyCache:
    def test_a_key_is_fetched_once_then_served_from_cache(self, app, keycloak, clock):
        first, second = _key("a"), _key("a")

        assert first.public_numbers() == second.public_numbers()
        assert len(keycloak.calls) == 2  # openid-configuration + JWKS, once

    def test_it_expires(self, app, keycloak, clock):
        _key("a")
        clock[0] += auth.JWKS_TTL
        _key("a")

        assert len(keycloak.calls) == 4

    # Criterion 1: key rotation.
    def test_a_rotated_key_is_accepted_straight_away(self, app, keycloak, clock):
        _key("a")
        keycloak.keys_by_realm["fsw"] = [KEY_A, KEY_B]
        clock[0] += auth.REFRESH_MIN_INTERVAL

        assert _key("b") is not None

    # Criterion 2: unknown / forged kid cannot become a DoS, and is refused.
    def test_unknown_kids_refetch_at_most_once_per_interval(self, app, keycloak, clock):
        _key("a")
        for n in range(20):
            with pytest.raises(HTTPException) as exc:
                _key(f"made-up-{n}")
            assert exc.value.code == 400

        assert len(keycloak.calls) == 2  # nothing beyond the first fetch

    def test_an_unknown_kid_after_the_interval_refetches_once_and_is_refused(self, app, keycloak, clock):
        _key("a")
        clock[0] += auth.REFRESH_MIN_INTERVAL
        with pytest.raises(HTTPException):
            _key("made-up")

        assert len(keycloak.calls) == 4

    # Criterion 3a: a realm deleted and recreated has new keys.
    def test_a_recreated_realm_is_accepted_once_its_new_key_is_seen(self, app, keycloak, clock):
        _key("a")
        keycloak.keys_by_realm["fsw"] = [KEY_B]  # recreated: old key gone
        clock[0] += auth.REFRESH_MIN_INTERVAL

        assert _key("b") is not None

    # Criterion 4: OB-55 -- a forged issuer still fails closed with a warm cache.
    @pytest.mark.parametrize("issuer", [
        "https://attacker.example.com/realms/fsw",
        f"{SERVER}.evil.example.com/realms/fsw",
        f"{SERVER}/realms/fsw/../other",
    ])
    def test_a_forged_issuer_is_refused_even_with_the_realm_cached(self, app, keycloak, clock, issuer):
        _key("a")  # warm the fsw entry
        with pytest.raises(HTTPException) as exc:
            auth.get_public_key(issuer, "a", SERVER)

        assert exc.value.code == 401
        assert len(keycloak.calls) == 2

    # Criterion 5: no key is ever reused across realms.
    def test_keys_are_never_shared_between_realms(self, app, keycloak, clock):
        fsw = _key("a", realm="fsw")
        other = _key("a", realm="other")  # same kid, different realm and key

        assert fsw.public_numbers() != other.public_numbers()
        assert len(keycloak.calls) == 4


class TestRealmListCache:
    def _realms(self, *names):
        fn = MagicMock(return_value=list(names))
        return fn

    def test_the_list_is_fetched_once_within_its_ttl(self, app, clock):
        realms = self._realms("fsw")
        assert auth.realm_is_valid("fsw", realms)
        assert auth.realm_is_valid("fsw", realms)

        assert realms.call_count == 1

    # Criterion 3b: a newly onboarded realm works at once.
    def test_a_new_realm_triggers_one_refresh(self, app, clock):
        realms = self._realms("fsw")
        auth.realm_is_valid("fsw", realms)
        realms.return_value = ["fsw", "playwright1"]
        clock[0] += auth.REFRESH_MIN_INTERVAL

        assert auth.realm_is_valid("playwright1", realms)
        assert realms.call_count == 2

    def test_unknown_realm_names_do_not_refetch_within_the_interval(self, app, clock):
        realms = self._realms("fsw")
        auth.realm_is_valid("fsw", realms)
        for n in range(20):
            assert not auth.realm_is_valid(f"made-up-{n}", realms)

        assert realms.call_count == 1

    # Criterion 3c: a deleted realm stops verifying within REALMS_TTL, and its keys go.
    def test_a_deleted_realm_is_refused_after_the_ttl_and_its_keys_evicted(self, app, keycloak, clock):
        realms = self._realms("fsw")
        auth.realm_is_valid("fsw", realms)
        _key("a")
        realms.return_value = []
        clock[0] += auth.REALMS_TTL

        assert not auth.realm_is_valid("fsw", realms)
        assert (SERVER, "fsw") not in auth._jwks_cache


class TestPermissionsUseTheRealmCache:
    @patch("optibroker_common.authentication.verify_jwt_or_secret_key")
    def test_get_current_user_permissions_does_not_refetch_realms_per_request(self, mock_verify, app, clock):
        mock_verify.return_value = {"sub": "u1", "iss": f"{SERVER}/realms/fsw", "realm_access": {"roles": []}}
        realms = MagicMock(return_value=["fsw"])
        with app.test_request_context():
            for _ in range(5):
                auth.get_current_user_permissions("RS256", SERVER, get_realms_func=realms)

        assert realms.call_count == 1

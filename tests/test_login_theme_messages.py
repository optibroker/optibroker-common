"""Every piece of text the login theme shows comes from a message key that
exists. Keycloak prints a missing key as-is -- the page-expired button once
read "doRestartLogin" -- and msg() never returns null, so a FreeMarker
fallback like msg("x")!"Text" never applies."""
import re
from pathlib import Path

import pytest

from optibroker_common.login_theme.engine import BASE_THEME_DIR

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _keys(path):
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "!")):
            keys.add(line.split("=", 1)[0].strip())
    return keys


@pytest.mark.parametrize("kind", ["login", "email"])
def test_every_message_the_templates_use_exists(kind):
    defined = _keys(FIXTURES / f"keycloak22_{kind}_message_keys.txt")
    defined |= _keys(BASE_THEME_DIR / kind / "messages" / "messages_en.properties")
    missing = {}
    for ftl in (BASE_THEME_DIR / kind).rglob("*.ftl"):
        for key in re.findall(r"""msg\(\s*["']([^"'$]+)["']""", ftl.read_text(encoding="utf-8")):
            # "loginTotp." + policy type, and similar, are completed at runtime.
            if key not in defined and not key.endswith("."):
                missing.setdefault(ftl.name, set()).add(key)
    assert not missing, f"undefined message keys: {missing}"


def test_no_template_relies_on_a_fallback_that_never_applies():
    offenders = [
        f"{ftl.name}: {m}"
        for ftl in BASE_THEME_DIR.rglob("*.ftl")
        for m in re.findall(r"""msg\([^)]*\)!""", ftl.read_text(encoding="utf-8"))
    ]
    assert not offenders, offenders


def test_the_runtime_completed_keys_exist():
    defined = _keys(FIXTURES / "keycloak22_login_message_keys.txt")
    assert {"loginTotp.totp", "loginTotp.hotp"} <= defined
    ours = _keys(BASE_THEME_DIR / "login" / "messages" / "messages_en.properties")
    assert "fswAuthy" in ours  # the extra authenticator app the setup page lists

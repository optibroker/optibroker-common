"""A company can reword any page of its login theme: every piece of wording the
templates show is in the catalogue, and its overrides win over the theme's."""
import re

from optibroker_common.login_theme.engine import BASE_THEME_DIR, normalise_branding, render_theme, text_catalogue
from optibroker_common.login_theme.text import OVERRIDABLE_KEYS, PAGES

# Message keys the templates read that are not wording a company edits here:
# image paths, switches, the help URL (a branding field of its own), app
# names, and small fixed words.
NOT_WORDING = {
    "companyName", "fswLogo", "fswPanelLogo", "fswHeroImage", "fswShowIllustration", "fswShowCompanyName", "fswHelpUrl",
    "fswShowPassword", "fswOr", "fswTotpCopied", "fswOptional", "fswAuthy", "fswArrowLabel",
    "loginTotpTitle", "loginTotpType", "loginTotpAlgorithm", "loginTotpDigits", "loginTotpInterval",
    "loginTotpCounter", "requiredFields", "doTryAnotherWay", "noAccount", "doRegister",
}


def _template_keys():
    keys = set()
    for ftl in (BASE_THEME_DIR / "login").glob("*.ftl"):
        keys |= set(re.findall(r"""msg\(\s*["']([A-Za-z.]+)["']""", ftl.read_text(encoding="utf-8")))
    return {k for k in keys if not k.endswith(".")}


def test_every_page_wording_is_editable():
    in_catalogue = {e["key"] for page in PAGES for e in page["texts"]}
    missing = _template_keys() - in_catalogue - NOT_WORDING
    assert not missing, f"wording the editor cannot reach: {sorted(missing)}"


def test_every_entry_has_a_default():
    for page in text_catalogue():
        for entry in page["texts"]:
            if entry["key"] != "fswHelpUrl":
                assert entry["default"], f"{page['id']}/{entry['key']} has no default"
    login = next(p for p in text_catalogue() if p["id"] == "login")
    assert {e["key"]: e["default"] for e in login["texts"]}["doLogIn"] == "Log in"


def test_overrides_are_published_last_and_escaped():
    files = render_theme({"texts": {"doLogIn": "Sign in", "fswRestartLogin": "Start {again}, O'Brien"}})
    messages = files["login/messages/messages_en.properties"].decode()
    tail = messages.split("# The company's own wording.", 1)[1]
    assert "doLogIn=Sign in" in tail
    assert "fswRestartLogin=Start '{'again'}', O''Brien" in tail
    assert messages.index("doLogIn=Log in") < messages.index("doLogIn=Sign in")


def test_unknown_unchanged_and_blank_overrides_are_dropped():
    texts = normalise_branding({"texts": {
        "doLogIn": "Log in",          # the default
        "fswOtpTitle": "   ",          # blank
        "notAKey": "x",               # unknown
        "fswHeadline": "Hi",          # a branding field, set through "headline"
        "fswLogoutButton": " Sign  out ",
    }})["texts"]
    assert texts == {"fswLogoutButton": "Sign out"}
    assert "fswHeadline" not in OVERRIDABLE_KEYS


def test_nothing_is_appended_without_overrides():
    messages = render_theme({})["login/messages/messages_en.properties"].decode()
    assert "The company's own wording" not in messages

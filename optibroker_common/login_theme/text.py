"""Every piece of wording on the login theme's pages that a company may change,
page by page, in the order it appears.

An entry either names a branding field (the login headline, the 2FA title...)
or a message key the company may override. Overrides are stored in branding
"texts" and appended to the theme's messages, so anything a company leaves
alone keeps the theme's own wording -- and picks up any later change to it.

`role` tells an editor's preview where the text goes: title, subtitle, text,
label, placeholder, button, link or note.
"""
from pathlib import Path


def _entry(key, label, role, field=None):
    return {"key": key, "label": label, "role": role, **({"field": field} if field else {})}


PAGES = [
    {"id": "login", "label": "Log in", "texts": [
        _entry("fswHeadline", "Panel headline", "title", "headline"),
        _entry("fswTagline", "Panel tagline", "subtitle", "tagline"),
        _entry("fswWelcomeTitle", "Title", "title", "welcome_title"),
        _entry("fswWelcomeSubtitle", "Subtitle", "subtitle", "welcome_subtitle"),
        _entry("usernameOrEmail", "Username label", "label"),
        _entry("fswUsernamePlaceholder", "Username placeholder", "placeholder"),
        _entry("password", "Password label", "label"),
        _entry("fswPasswordPlaceholder", "Password placeholder", "placeholder"),
        _entry("rememberMe", "Remember me", "label"),
        _entry("doForgotPassword", "Forgot password link", "link"),
        _entry("doLogIn", "Log in button", "button"),
        _entry("fswSecurityTitle", "Security note title", "note", "security_title"),
        _entry("fswSecurityText", "Security note text", "note", "security_text"),
        _entry("fswFooterText", "Footer (after © year and company name)", "note", "footer_text"),
    ]},
    {"id": "totp", "label": "Authenticator setup", "texts": [
        _entry("fswTotpTitle", "Title", "title", "totp_title"),
        _entry("fswTotpSubtitle", "Subtitle", "subtitle", "totp_subtitle"),
        _entry("fswTotpInstallTitle", "Step 1 title", "label"),
        _entry("fswTotpInstallText", "Step 1 text", "text"),
        _entry("fswTotpScanTitle", "Step 2 title", "label"),
        _entry("fswTotpScanText", "Step 2 text", "text"),
        _entry("fswTotpCantScan", "Can't scan link", "link"),
        _entry("fswTotpHintTitle", "QR hint title", "note"),
        _entry("fswTotpHintText", "QR hint text", "note"),
        _entry("fswTotpManualTitle", "Step 2 title (entering the key)", "label"),
        _entry("fswTotpManualText", "Step 2 text (entering the key)", "text"),
        _entry("fswTotpCopy", "Copy key button", "link"),
        _entry("fswTotpScanInstead", "Scan instead link", "link"),
        _entry("fswTotpVerifyTitle", "Step 3 title", "label"),
        _entry("fswTotpVerifyText", "Step 3 text", "text"),
        _entry("fswTotpCode", "Code label", "label"),
        _entry("fswCodePlaceholder", "Code placeholder", "placeholder"),
        _entry("fswTotpDevice", "Device name label", "label"),
        _entry("fswTotpDevicePlaceholder", "Device name placeholder", "placeholder"),
        _entry("fswTotpNote", "One-time setup note", "note"),
        _entry("fswTotpSubmit", "Verify button", "button"),
        _entry("fswNeedHelp", "Help link text", "link"),
    ]},
    {"id": "otp", "label": "Security code", "texts": [
        _entry("fswOtpTitle", "Title", "title"),
        _entry("fswOtpSubtitle", "Subtitle", "subtitle"),
        _entry("fswWhichAuthenticator", "Which authenticator? (several devices)", "label"),
        _entry("loginOtpOneTime", "Code label", "label"),
        _entry("fswCodePlaceholder", "Code placeholder", "placeholder"),
        _entry("fswOtpButton", "Button", "button"),
        _entry("fswOtpLost", "Lost phone note", "note"),
    ]},
    {"id": "reset", "label": "Forgot password", "texts": [
        _entry("fswResetTitle", "Title", "title"),
        _entry("fswResetSubtitleEmail", "Subtitle", "subtitle"),
        _entry("fswResetSubtitleUsername", "Subtitle (no email login)", "subtitle"),
        _entry("fswEmailAddress", "Email label", "label"),
        _entry("fswEmailPlaceholder", "Email placeholder", "placeholder"),
        _entry("fswUsernameOnlyPlaceholder", "Username placeholder (no email login)", "placeholder"),
        _entry("fswSendResetLink", "Button", "button"),
        _entry("backToLogin", "Back to login link", "link"),
    ]},
    {"id": "update_password", "label": "New password", "texts": [
        _entry("fswUpdatePasswordTitle", "Title", "title"),
        _entry("fswUpdatePasswordSubtitle", "Subtitle", "subtitle"),
        _entry("passwordNew", "New password label", "label"),
        _entry("fswNewPasswordPlaceholder", "New password placeholder", "placeholder"),
        _entry("fswPwStrength", "Strength label", "note"),
        _entry("fswPwWeak", "Strength: weak", "note"),
        _entry("fswPwFair", "Strength: fair", "note"),
        _entry("fswPwGood", "Strength: good", "note"),
        _entry("fswPwStrong", "Strength: strong", "note"),
        _entry("fswPwRulesTitle", "Rules heading", "label"),
        _entry("fswPwRuleLength", "Rule: length", "text"),
        _entry("fswPwRuleMix", "Rule: mix", "text"),
        _entry("fswPwRuleUsername", "Rule: not the username", "text"),
        _entry("passwordConfirm", "Confirm label", "label"),
        _entry("fswConfirmPasswordPlaceholder", "Confirm placeholder", "placeholder"),
        _entry("fswPwMismatch", "Passwords don't match", "note"),
        _entry("doSubmit", "Button", "button"),
        _entry("backToLogin", "Back to login link", "link"),
    ]},
    {"id": "update_profile", "label": "Update details", "texts": [
        _entry("fswProfileTitle", "Title", "title"),
        _entry("fswProfileSubtitle", "Subtitle", "subtitle"),
        _entry("username", "Username label", "label"),
        _entry("email", "Email label", "label"),
        _entry("firstName", "First name label", "label"),
        _entry("lastName", "Last name label", "label"),
        _entry("doSubmit", "Button", "button"),
        _entry("doCancel", "Cancel button", "link"),
    ]},
    {"id": "verify_email", "label": "Verify email", "texts": [
        _entry("fswVerifyTitle", "Title", "title"),
        _entry("fswVerifySubtitle", "Subtitle", "subtitle"),
        _entry("fswVerifySent", "Sent to (followed by their email)", "text"),
        _entry("fswVerifyFollow", "Instructions", "text"),
        _entry("fswVerifyNotReceived", "Not received?", "text"),
        _entry("fswResendEmail", "Resend button", "button"),
        _entry("backToLogin", "Back to login link", "link"),
    ]},
    {"id": "expired", "label": "Page expired", "texts": [
        _entry("fswExpiredTitle", "Title", "title"),
        _entry("fswExpiredSubtitle", "Subtitle", "subtitle"),
        _entry("fswExpiredText", "Text", "text"),
        _entry("fswRestartLogin", "Restart button", "button"),
        _entry("fswContinueLogin", "Continue link", "link"),
    ]},
    {"id": "error", "label": "Error", "texts": [
        _entry("fswErrorTitle", "Title", "title"),
        _entry("fswErrorSubtitle", "Subtitle", "subtitle"),
        _entry("fswErrorDefault", "Message when there is no detail", "text"),
        _entry("fswBackToApp", "Back to the application button", "button"),
    ]},
    {"id": "info", "label": "Notice", "texts": [
        _entry("fswNotice", "Title when there is none", "title"),
        _entry("fswProceed", "Continue button", "button"),
        _entry("fswBackToApp", "Back to the application button", "button"),
    ]},
    {"id": "logout", "label": "Log out", "texts": [
        _entry("fswLogoutTitle", "Title", "title"),
        _entry("fswLogoutSubtitle", "Subtitle", "subtitle"),
        _entry("fswLogoutButton", "Log out button", "button"),
        _entry("fswBackToApp", "Back to the application link", "link"),
    ]},
]

# Keys a company may override through "texts" (field entries are branding fields).
OVERRIDABLE_KEYS = {e["key"] for page in PAGES for e in page["texts"] if "field" not in e}


def _read_messages(path):
    """{key: text} from a Keycloak messages file, with MessageFormat quoting undone."""
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "!")) or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.replace("'{'", "{").replace("'}'", "}").replace("''", "'")
    return values


def catalogue(messages_path, default_branding):
    """PAGES with each entry's default wording filled in."""
    messages = _read_messages(messages_path)
    pages = []
    for page in PAGES:
        texts = []
        for entry in page["texts"]:
            default = default_branding[entry["field"]] if "field" in entry else messages.get(entry["key"], "")
            texts.append({**entry, "default": default})
        pages.append({**page, "texts": texts})
    return pages

"""Each company gets its own Keycloak login/email theme, published to the bucket
Keycloak's pods sync themes from, under the realm's name (optibroker_common.login_theme)."""
import base64
import io
import json
import re
from unittest.mock import MagicMock

import pytest

from optibroker_common.login_theme.engine import (
    BRANDING_FILE, DEFAULT_BRANDING, DEFAULT_COLOUR, FONT_FILES, FONTS, FONTS_DIR, GENERATED_MARKER, TEXT_FIELDS,
    _message_unvalue, _message_value, _text_shade, decode_image, font_files,
    normalise_branding, render_theme, theme_tokens,
)
from optibroker_common.login_theme.store import ThemeStore

PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def _svg(body):
    return "data:image/svg+xml;base64," + base64.b64encode(body.encode()).decode()


class FakeS3:
    """Just enough of an S3 client: objects live in a dict keyed by (bucket, key)."""

    def __init__(self, objects=None):
        self.objects = dict(objects or {})
        self.exceptions = MagicMock()
        self.exceptions.NoSuchKey = type("NoSuchKey", (Exception,), {})
        self.put_object = MagicMock(side_effect=self._put)
        self.delete_object = MagicMock(side_effect=self._delete)

    def _put(self, Bucket, Key, Body, ContentType=None):
        self.objects[(Bucket, Key)] = Body if isinstance(Body, bytes) else Body.encode()

    def _delete(self, Bucket, Key):
        self.objects.pop((Bucket, Key), None)

    def get_object(self, Bucket, Key):
        if (Bucket, Key) not in self.objects:
            raise self.exceptions.NoSuchKey()
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def list_objects_v2(self, Bucket, Delimiter=None, Prefix="", ContinuationToken=None):
        keys = sorted(k for b, k in self.objects if b == Bucket and k.startswith(Prefix))
        if Delimiter:
            prefixes = sorted({k.split("/", 1)[0] + "/" for k in keys if "/" in k})
            return {"CommonPrefixes": [{"Prefix": p} for p in prefixes], "IsTruncated": False}
        return {"Contents": [{"Key": k} for k in keys], "IsTruncated": False}

    def keys(self, prefix):
        return sorted(k for _, k in self.objects if k.startswith(prefix))

    def text(self, key, bucket="themes"):
        return self.objects[(bucket, key)].decode()


@pytest.fixture
def themes_bucket():
    """The tests' bucket is called "themes" (see _service)."""
    yield


def _service(client):
    return ThemeStore(client, "themes")


class TestRender:
    def test_every_token_is_filled(self):
        files = render_theme({"company_name": "Acme Mortgages", "company_colour": "#123456"})
        assert not any(b"@@" in body for body in files.values())

    def test_ships_the_login_email_and_two_factor_pages(self):
        files = render_theme({"company_name": "Acme"})
        for path in ("login/login.ftl", "login/login-otp.ftl", "login/login-config-totp.ftl",
                     "login/login-reset-password.ftl", "login/login-update-password.ftl",
                     "login/template.ftl", "login/resources/css/style.css", "email/html/layout.ftl",
                     "email/theme.properties"):
            assert path in files

    def test_the_company_name_and_colour_are_used(self):
        files = render_theme({"company_name": "Acme Mortgages", "company_colour": "#123456"})
        assert b"companyName=Acme Mortgages" in files["login/messages/messages_en.properties"]
        assert b"Reset your password for Acme Mortgages" in files["email/messages/messages_en.properties"]
        assert b"--brand: #123456;" in files["login/resources/css/style.css"]
        assert b"rgba(18,52,86,.18)" in files["login/resources/css/style.css"]
        assert b"background:#123456" in files["email/html/layout.ftl"]

    def test_the_page_wording_is_the_companys(self):
        files = render_theme({"headline": "Homes for all", "welcome_title": "Hello again",
                              "totp_title": "Protect your account", "help_url": "https://acme.example/help"})
        messages = files["login/messages/messages_en.properties"].decode()
        assert "fswHeadline=Homes for all" in messages
        assert "fswWelcomeTitle=Hello again" in messages
        assert "fswTotpTitle=Protect your account" in messages
        assert "fswHelpUrl=https://acme.example/help" in messages

    def test_defaults_match_the_design(self):
        messages = render_theme({})["login/messages/messages_en.properties"].decode()
        assert "fswWelcomeTitle=Welcome back" in messages
        assert "fswSecurityTitle=Your information is protected" in messages
        assert "fswTotpTitle=Set up your authenticator app" in messages

    def test_images_are_referenced_only_when_uploaded(self):
        assert b"fswLogo=\n" in render_theme({})["login/messages/messages_en.properties"].replace(b"\r", b"")
        with_logo = render_theme({}, {"logo": "img/logo.png"})["login/messages/messages_en.properties"]
        assert b"fswLogo=img/logo.png" in with_logo

    def test_the_heading_font_and_illustration_switch(self):
        files = render_theme({"heading_font": "sans", "show_illustration": False})
        assert b"--heading-font: Inter" in files["login/resources/css/style.css"]
        assert b"fswShowIllustration=false" in files["login/messages/messages_en.properties"]

    def test_nothing_of_finance_south_west_is_left(self):
        for body in render_theme({"company_name": "Acme"}).values():
            assert b"Finance South West" not in body and b"FinanceSouthWest" not in body

    def test_the_stylesheet_and_fonts_get_a_new_url_when_anything_changes(self):
        # Keycloak lets browsers cache theme resources for 30 days at a URL that
        # never changes, so a cached old stylesheet would style the new pages.
        def version(branding):
            files = render_theme(branding)
            match = re.search(r'css/style\.css\?v=([0-9a-f]{12})"', files["login/template.ftl"].decode())
            assert match, "the stylesheet link carries a version"
            css = files["login/resources/css/style.css"].decode()
            assert f".woff2?v={match.group(1)}'" in css or "@font-face" not in css
            return match.group(1)

        same = version({"company_name": "Acme", "heading_font": "lora"})
        assert version({"company_name": "Acme", "heading_font": "lora"}) == same
        assert version({"company_name": "Acme", "heading_font": "lora", "company_colour": "#123456"}) != same

    def test_generated_themes_are_marked(self):
        assert GENERATED_MARKER.encode() in render_theme({})["login/theme.properties"]

    def test_freeotp_is_not_offered(self):
        totp = render_theme({})["login/login-config-totp.ftl"]
        assert b'a != "totpAppFreeOTPName"' in totp
        messages = render_theme({})["login/messages/messages_en.properties"]
        assert b"fswAuthy=Authy" in messages
        assert b"any authenticator app" in messages  # the list is suggestions, not a requirement


class TestBranding:
    @pytest.mark.parametrize("colour", [None, "", "green", "#12345", "javascript:alert(1)"])
    def test_a_missing_or_invalid_colour_falls_back_to_the_default(self, colour):
        assert theme_tokens({"company_colour": colour})["BRAND"] == DEFAULT_COLOUR

    def test_short_hex_and_no_hash_are_accepted(self):
        assert theme_tokens({"company_colour": "abc"})["BRAND"] == "#aabbcc"

    def test_panel_and_accent_derive_from_the_brand_unless_set(self):
        derived = theme_tokens({"company_colour": "#4e6b3f"})
        assert derived["PANEL"] != derived["BRAND"] and derived["ACCENT"] != derived["PANEL"]
        assert theme_tokens({"panel_colour": "#000000"})["PANEL"] == "#000000"

    def test_text_on_a_pale_brand_is_dark_and_on_a_deep_one_white(self):
        assert theme_tokens({"company_colour": "#f5c542"})["ON_BRAND"] == "#111827"
        assert theme_tokens({"company_colour": "#4e6b3f"})["ON_BRAND"] == "#ffffff"

    def test_brand_text_always_reads_on_white(self):
        assert _text_shade((0x4e, 0x6b, 0x3f)) == "#4e6b3f"  # already dark enough
        assert _text_shade((0xf5, 0xc5, 0x42)) != "#f5c542"  # yellow is darkened

    def test_unknown_keys_dropped_and_text_trimmed(self):
        branding = normalise_branding({"headline": "  Homes \n for   all ", "evil": "x", "heading_font": "comic"})
        assert branding["headline"] == "Homes for all"
        assert "evil" not in branding
        assert branding["heading_font"] == "serif"

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "https://a.b/\"onload"])
    def test_only_web_and_mail_help_links_are_kept(self, url):
        assert normalise_branding({"help_url": url})["help_url"] == ""
        assert normalise_branding({"help_url": "mailto:help@acme.example"})["help_url"] == "mailto:help@acme.example"

    def test_names_are_escaped_for_keycloak_messages(self):
        # MessageFormat drops a lone quote and treats braces as arguments.
        assert _message_value("O'Brien {Finance}") == "O''Brien '{'Finance'}'"
        assert _message_value("Acme\nLtd\\") == "Acme Ltd\\\\"
        assert _message_unvalue(_message_value("O'Brien {Finance} \\")) == "O'Brien {Finance} \\"


class TestLogoSize:
    """The company picks the logo's height and width; blank keeps its proportions."""

    def test_unset_is_the_standard_size(self):
        assert (DEFAULT_BRANDING["logo_height"], DEFAULT_BRANDING["logo_width"]) == (None, None)
        tokens = theme_tokens({})
        assert (tokens["LOGO_HEIGHT"], tokens["LOGO_PANEL_HEIGHT"]) == ("40px", "48px")
        assert (tokens["LOGO_WIDTH"], tokens["LOGO_MAX_WIDTH"]) == ("auto", "160px")

    def test_sizes_are_whole_pixels_within_bounds(self):
        branding = normalise_branding({"logo_height": "64", "logo_width": 250.4})
        assert (branding["logo_height"], branding["logo_width"]) == (64, 250)
        assert normalise_branding({"logo_height": 5})["logo_height"] == 16
        assert normalise_branding({"logo_height": 999})["logo_height"] == 200
        assert normalise_branding({"logo_width": 9000})["logo_width"] == 480

    @pytest.mark.parametrize("value", [None, "", 0, -3, "big", True, [40], "nan", "inf"])
    def test_blank_or_nonsense_means_unset(self, value):
        branding = normalise_branding({"logo_height": value, "logo_width": value})
        assert (branding["logo_height"], branding["logo_width"]) == (None, None)

    def test_sizes_are_not_wording(self):
        assert "logo_height" not in TEXT_FIELDS and "logo_width" not in TEXT_FIELDS
        messages = render_theme({"logo_height": 60})["login/messages/messages_en.properties"].decode().replace("\r", "")
        assert "fswLogoHeight" not in messages and "=60\n" not in messages

    def test_height_alone_keeps_the_proportions_on_the_card_and_panel(self):
        tokens = theme_tokens({"logo_height": 60})
        assert (tokens["LOGO_HEIGHT"], tokens["LOGO_PANEL_HEIGHT"]) == ("60px", "60px")
        assert tokens["LOGO_WIDTH"] == "auto"
        assert tokens["LOGO_MAX_WIDTH"] == "240px"  # four times the height, as 160px is to 40px
        assert theme_tokens({"logo_height": 200})["LOGO_MAX_WIDTH"] == "480px"
        assert theme_tokens({"logo_height": 16})["LOGO_MAX_WIDTH"] == "160px"

    def test_width_alone_keeps_the_proportions(self):
        tokens = theme_tokens({"logo_width": 300})
        assert (tokens["LOGO_HEIGHT"], tokens["LOGO_PANEL_HEIGHT"]) == ("auto", "auto")
        assert (tokens["LOGO_WIDTH"], tokens["LOGO_MAX_WIDTH"]) == ("300px", "300px")

    def test_both_set_is_a_box_the_logo_fits_inside(self):
        tokens = theme_tokens({"logo_height": 50, "logo_width": 120})
        assert (tokens["LOGO_HEIGHT"], tokens["LOGO_WIDTH"], tokens["LOGO_MAX_WIDTH"]) == ("50px", "120px", "120px")

    def test_the_stylesheet_uses_the_size(self):
        css = render_theme({"logo_height": 72, "logo_width": 200})["login/resources/css/style.css"].decode()
        assert "--logo-height: 72px;" in css and "--logo-panel-height: 72px;" in css
        assert "--logo-width: 200px;" in css and "--logo-max-width: 200px;" in css
        # The authenticator page's top bar stays compact whatever is chosen.
        assert re.search(r"\.fsw-topbar-brand \.fsw-mark-img \{[^}]*height: 32px", css)

    def test_a_size_change_gets_a_new_stylesheet_url(self):
        def version(branding):
            return re.search(r'css/style\.css\?v=([0-9a-f]{12})"',
                             render_theme(branding)["login/template.ftl"].decode()).group(1)
        assert version({"logo_height": 60}) != version({})

    def test_a_partial_update_keeps_the_size_and_null_clears_it(self, themes_bucket):
        client = FakeS3()
        service = _service(client)
        service.publish("acme", {"logo_height": 70, "logo_width": 210})
        service.publish("acme", {"tagline": "Since 1990"})
        stored = json.loads(client.text(f"acme/{BRANDING_FILE}"))
        assert (stored["logo_height"], stored["logo_width"]) == (70, 210)
        service.publish("acme", {"logo_width": None})
        stored = json.loads(client.text(f"acme/{BRANDING_FILE}"))
        assert (stored["logo_height"], stored["logo_width"]) == (70, None)


class TestFonts:
    def test_every_bundled_font_file_exists(self):
        for name in FONT_FILES:
            assert (FONTS_DIR / "files" / name).stat().st_size > 1000, name

    def test_system_fonts_need_no_files(self):
        branding = normalise_branding({})
        assert (branding["heading_font"], branding["body_font"]) == ("serif", "sans")
        assert font_files(branding) == []
        assert "@font-face" not in render_theme(branding)["login/resources/css/style.css"].decode()

    def test_a_bundled_font_is_declared_and_used(self):
        css = render_theme({"heading_font": "lora", "body_font": "work-sans"})["login/resources/css/style.css"].decode()
        assert "font-family: 'Lora'" in css and "url('../fonts/lora-latin-" in css
        assert "font-family: 'Work Sans'" in css
        assert "--heading-font: 'Lora', 'Iowan Old Style'" in css
        assert "--body-font: 'Work Sans', Inter" in css

    def test_headings_use_the_fonts_own_weight(self):
        # DM Serif Display only comes in 400; asking for 600 would fake a bold.
        assert theme_tokens({"heading_font": "dm-serif-display"})["HEADING_WEIGHT"] == "400"
        assert theme_tokens({"heading_font": "inter"})["HEADING_WEIGHT"] == "600"

    @pytest.mark.parametrize("font", ["comic-sans", "../../etc/passwd", None])
    def test_an_unknown_font_keeps_the_default(self, font):
        assert normalise_branding({"heading_font": font, "body_font": font})["body_font"] == "sans"

    def test_the_same_font_for_both_is_declared_once(self):
        css = theme_tokens({"heading_font": "inter", "body_font": "inter"})["FONT_FACES"]
        assert css.count("font-family: 'Inter'") == len(FONTS["inter"]["faces"])


class TestImages:
    def test_png_is_accepted(self):
        assert decode_image(PNG)[0] == "png"

    @pytest.mark.parametrize("data_url, reason", [
        ("not a data url", "data: URL"),
        ("data:text/html;base64,PGI+", "not supported"),
        ("data:image/png;base64,***", "base64"),
    ])
    def test_bad_uploads_are_refused(self, data_url, reason):
        with pytest.raises(ValueError, match=reason):
            decode_image(data_url)

    def test_too_large_is_refused(self):
        big = "data:image/png;base64," + base64.b64encode(b"x" * 1_000_001).decode()
        with pytest.raises(ValueError, match="1 MB"):
            decode_image(big)

    def test_a_plain_svg_is_accepted(self):
        assert decode_image(_svg('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h1"/></svg>'))[0] == "svg"

    @pytest.mark.parametrize("svg", [
        '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" onload="alert(1)"/>',
        '<svg xmlns="http://www.w3.org/2000/svg"><foreignObject/></svg>',
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:x="http://www.w3.org/1999/xlink">'
        '<image x:href="https://evil.example/a.png"/></svg>',
        '<!DOCTYPE svg [<!ENTITY a "b">]><svg xmlns="http://www.w3.org/2000/svg"/>',
        '<html/>',
    ])
    def test_scripted_or_external_svg_is_refused(self, svg):
        with pytest.raises(ValueError):
            decode_image(_svg(svg))


class TestPublish:
    def test_writes_every_file_under_the_realm(self, themes_bucket):
        client = FakeS3()
        result = _service(client).publish("acme", {"company_name": "Acme", "company_colour": "#123456"})
        keys = {c.kwargs["Key"] for c in client.put_object.call_args_list}
        assert "acme/login/login-otp.ftl" in keys
        assert f"acme/{BRANDING_FILE}" in keys
        assert all(k.startswith("acme/") for k in keys)
        assert {c.kwargs["Bucket"] for c in client.put_object.call_args_list} == {"themes"}
        assert result["files"] == len(keys)

    def test_replaces_a_theme_it_made_before(self, themes_bucket):
        client = FakeS3({("themes", "acme/login/theme.properties"): f"{GENERATED_MARKER}\n".encode()})
        _service(client).publish("acme", {"company_name": "Acme"})
        assert client.put_object.called

    def test_never_overwrites_a_hand_made_theme(self, themes_bucket):
        client = FakeS3({("themes", "fsw/login/theme.properties"): b"parent=keycloak\n"})
        with pytest.raises(RuntimeError, match="not made by the provisioner"):
            _service(client).publish("fsw", {"company_name": "Acme"})
        client.put_object.assert_not_called()

    def test_an_unset_bucket_fails_rather_than_guessing(self):
        with pytest.raises(RuntimeError, match="KEYCLOAK_THEMES_BUCKET"):
            ThemeStore(FakeS3(), None)

    def test_a_partial_update_keeps_the_rest_of_the_branding(self, themes_bucket):
        client = FakeS3()
        service = _service(client)
        service.publish("acme", {"company_name": "Acme", "headline": "Homes for all", "company_colour": "#123456"})
        service.publish("acme", {"tagline": "Since 1990"})
        stored = json.loads(client.text(f"acme/{BRANDING_FILE}"))
        assert stored["company_name"] == "Acme"
        assert (stored["headline"], stored["tagline"]) == ("Homes for all", "Since 1990")
        assert stored["company_colour"] == "#123456"

    def test_an_uploaded_logo_is_stored_kept_and_removable(self, themes_bucket):
        client = FakeS3()
        service = _service(client)
        service.publish("acme", {"company_name": "Acme"}, {"logo": PNG})
        [logo] = client.keys("acme/login/resources/img/")
        path = logo.split("/resources/", 1)[1]
        assert re.fullmatch(r"img/logo-[0-9a-f]{10}\.png", path)
        assert f"fswLogo={path}" in client.text("acme/login/messages/messages_en.properties")

        service.publish("acme", {"tagline": "x"})  # images left out are kept
        assert f"fswLogo={path}" in client.text("acme/login/messages/messages_en.properties")

        service.publish("acme", {}, {"logo": ""})
        assert client.keys("acme/login/resources/img/") == []
        assert f"fswLogo={path}" not in client.text("acme/login/messages/messages_en.properties")

    def test_a_replaced_logo_gets_a_new_name_and_the_old_file_goes(self, themes_bucket):
        # A new URL, because browsers may cache the old one for 30 days.
        client = FakeS3()
        service = _service(client)
        service.publish("acme", {}, {"logo": PNG})
        [first] = client.keys("acme/login/resources/img/")
        other_png = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\nother").decode()
        service.publish("acme", {}, {"logo": other_png})
        [second] = client.keys("acme/login/resources/img/")
        assert first != second and second.endswith(".png")
        service.publish("acme", {}, {"logo": _svg('<svg xmlns="http://www.w3.org/2000/svg"/>')})
        [third] = client.keys("acme/login/resources/img/")
        assert third.endswith(".svg")

    def test_chosen_fonts_are_copied_and_old_ones_removed(self, themes_bucket):
        client = FakeS3()
        service = _service(client)
        service.publish("acme", {"heading_font": "lora", "body_font": "inter"})
        fonts = client.keys("acme/login/resources/fonts/")
        assert fonts and all(k.rsplit("/", 1)[1].startswith(("lora-", "inter-")) for k in fonts)
        assert client.objects[("themes", fonts[0])][:4] == b"wOF2"

        service.publish("acme", {"heading_font": "serif"})  # body stays Inter
        assert all("/inter-" in k for k in client.keys("acme/login/resources/fonts/"))

        service.publish("acme", {"body_font": "sans"})
        assert client.keys("acme/login/resources/fonts/") == []

    def test_a_bad_image_writes_nothing(self, themes_bucket):
        client = FakeS3()
        with pytest.raises(ValueError):
            _service(client).publish("acme", {"company_name": "Acme"}, {"logo": "data:text/html;base64,PGI+"})
        client.put_object.assert_not_called()

    def test_an_unknown_image_slot_is_refused(self, themes_bucket):
        with pytest.raises(ValueError, match="Unknown image"):
            _service(FakeS3()).publish("acme", {}, {"favicon": PNG})


class TestStoredAndRepublish:
    def test_a_theme_from_before_branding_json_keeps_its_name_and_colour(self, themes_bucket):
        client = FakeS3({
            ("themes", "old/login/theme.properties"): f"{GENERATED_MARKER}\n".encode(),
            ("themes", "old/login/messages/messages_en.properties"): b"companyName=O''Brien '{'Ltd'}'\r\n",
            ("themes", "old/login/resources/css/style.css"): b":root{\n    --brand: #2a7f62;\n}",
        })
        branding, images = _service(client).stored("old")
        assert branding["company_name"] == "O'Brien {Ltd}"
        assert branding["company_colour"] == "#2a7f62"
        assert images == {}

    def test_republish_rebuilds_generated_themes_and_skips_hand_made_ones(self, themes_bucket):
        client = FakeS3({
            ("themes", "acme/login/theme.properties"): f"{GENERATED_MARKER}\n".encode(),
            ("themes", "acme/login/messages/messages_en.properties"): b"companyName=Acme\n",
            ("themes", "acme/login/resources/css/style.css"): b"--brand: #123456;",
            ("themes", "fsw/login/theme.properties"): b"parent=keycloak\n",
        })
        result = _service(client).republish_all()
        by_theme = {r["theme"]: r for r in result["themes"]}
        assert by_theme["acme"]["status"] == "published"
        assert by_theme["fsw"] == {"theme": "fsw", "status": "skipped", "reason": "made by hand"}
        assert "--brand: #123456;" in client.text("acme/login/resources/css/style.css")
        assert "fswWelcomeTitle=Welcome back" in client.text("acme/login/messages/messages_en.properties")
        assert client.text("fsw/login/theme.properties") == "parent=keycloak\n"

    def test_a_dry_run_writes_nothing(self, themes_bucket):
        client = FakeS3({("themes", "acme/login/theme.properties"): f"{GENERATED_MARKER}\n".encode()})
        result = _service(client).republish_all(dry_run=True)
        assert result["themes"][0]["status"] == "would publish"
        client.put_object.assert_not_called()

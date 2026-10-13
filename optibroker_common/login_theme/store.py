"""Company login themes in the bucket Keycloak's pods sync themes from.

Each theme is a folder named after the realm: the rendered base theme, the
company's images and fonts, and branding.json -- what it was last published
with, so it can be republished from a newer base without re-entering it.
"""
import hashlib
import json
import re
from pathlib import Path

from optibroker_common.login_theme.engine import (
    _CONTENT_TYPES, _IMAGE_CONTENT_TYPES, BRANDING_FILE, FONTS_DIR, GENERATED_MARKER, IMAGE_SLOTS,
    _message_unvalue, decode_image, font_files, normalise_branding, render_theme,
)


class ThemeStore:
    """Company themes in a Keycloak themes bucket, given an S3 client and the bucket."""

    def __init__(self, client, bucket):
        if not bucket:
            # Never guess a bucket: production's is shared by every company.
            raise RuntimeError("KEYCLOAK_THEMES_BUCKET is not set")
        self._client = client
        self._bucket_name = bucket

    def _bucket(self):
        return self._bucket_name

    def _get_client(self):
        return self._client

    def _get(self, key):
        """An object's bytes, or None if it is not in the bucket."""
        client = self._get_client()
        try:
            obj = client.get_object(Bucket=self._bucket(), Key=key)
        except client.exceptions.NoSuchKey:
            return None
        return obj["Body"].read()

    def _get_text(self, key):
        body = self._get(key)
        return None if body is None else body.decode("utf-8", errors="replace")

    def _existing_properties(self, theme):
        """The theme's login/theme.properties in the bucket, or None if absent."""
        return self._get_text(f"{theme}/login/theme.properties")

    def status(self, theme):
        """Whether the theme is in the bucket and was made by the provisioner."""
        existing = self._existing_properties(theme)
        return {
            "uploaded": existing is not None,
            "generated": existing is not None and GENERATED_MARKER in existing,
        }

    def _legacy_branding(self, theme):
        """Name and colour read back from a theme published before branding.json
        existed, so republishing it from the new base keeps them."""
        found = {}
        messages = self._get_text(f"{theme}/login/messages/messages_en.properties") or ""
        name = re.search(r"^companyName=(.*?)\r?$", messages, re.M)
        if name:
            found["company_name"] = _message_unvalue(name.group(1))
        css = self._get_text(f"{theme}/login/resources/css/style.css") or ""
        colour = re.search(r"--brand:\s*(#[0-9a-fA-F]{6})", css)
        if colour:
            found["company_colour"] = colour.group(1)
        return found

    def stored(self, theme):
        """(branding, images) the theme was last published with: its
        branding.json, else what can be read back from an older theme, else
        the defaults. `images` maps a slot to its path under login/resources."""
        raw = self._get_text(f"{theme}/{BRANDING_FILE}")
        if raw:
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}
            images = {k: v for k, v in (data.get("images") or {}).items()
                      if k in IMAGE_SLOTS and isinstance(v, str) and re.match(r"^img/[\w.-]+$", v)}
            return normalise_branding(data), images
        return normalise_branding(self._legacy_branding(theme)), {}

    def image(self, theme, slot):
        """(bytes, content type) of one of the theme's images, or None."""
        _, images = self.stored(theme)
        path = images.get(slot)
        if not path:
            return None
        body = self._get(f"{theme}/login/resources/{path}")
        if body is None:
            return None
        return body, _IMAGE_CONTENT_TYPES.get(path.rsplit(".", 1)[-1], "application/octet-stream")

    def publish(self, theme, branding=None, images=None):
        """Write the company's theme to <bucket>/<theme>/, replacing a previous
        generated one. Refuses to overwrite a theme someone made by hand.

        `branding` is merged over what the theme was last published with, so
        a partial update keeps the rest. `images` maps a slot to a data: URL to
        upload, or to "" / None to remove that image; a slot left out is kept.
        """
        existing = self._existing_properties(theme)
        if existing is not None and GENERATED_MARKER not in existing:
            raise RuntimeError(
                f"Theme '{theme}' already exists in the bucket and was not made by the "
                "provisioner; it has been left alone"
            )
        previous, current_images = self.stored(theme) if existing is not None else (normalise_branding({}), {})
        merged = normalise_branding({**previous, **(branding or {})})

        # Decode every upload before writing anything, so a bad image fails
        # the publish cleanly rather than half-way through.
        uploads, removals = {}, []
        for slot, value in (images or {}).items():
            if slot not in IMAGE_SLOTS:
                raise ValueError(f"Unknown image '{slot}'; expected one of {', '.join(IMAGE_SLOTS)}")
            if value:
                uploads[slot] = decode_image(value)
            elif slot in current_images:
                removals.append(current_images.pop(slot))

        client = self._get_client()
        bucket = self._bucket()
        for slot, (ext, body) in uploads.items():
            # Named by content, so a replaced image is a new URL rather than
            # one a browser may have cached for 30 days.
            path = f"img/{slot}-{hashlib.sha256(body).hexdigest()[:10]}.{ext}"
            if current_images.get(slot) not in (None, path):
                removals.append(current_images[slot])
            current_images[slot] = path
            client.put_object(Bucket=bucket, Key=f"{theme}/login/resources/{path}", Body=body,
                              ContentType=_IMAGE_CONTENT_TYPES[ext])
        for path in removals:
            client.delete_object(Bucket=bucket, Key=f"{theme}/login/resources/{path}")

        # The chosen fonts, and nothing left over from fonts chosen before.
        font_prefix = f"{theme}/login/resources/fonts/"
        wanted_fonts = font_files(merged)
        for name in wanted_fonts:
            client.put_object(Bucket=bucket, Key=font_prefix + name, Body=(FONTS_DIR / "files" / name).read_bytes(),
                              ContentType="font/woff2")
        for key in self._keys(font_prefix):
            if key[len(font_prefix):] not in wanted_fonts:
                client.delete_object(Bucket=bucket, Key=key)

        files = render_theme(merged, current_images)
        files[BRANDING_FILE] = json.dumps({**merged, "images": current_images}, indent=2).encode("utf-8")
        for rel, body in files.items():
            client.put_object(
                Bucket=bucket,
                Key=f"{theme}/{rel}",
                Body=body,
                ContentType=_CONTENT_TYPES.get(Path(rel).suffix, "application/octet-stream"),
            )
        return {"status": "published", "theme": theme, "bucket": bucket, "files": len(files) + len(wanted_fonts),
                "branding": merged, "images": current_images}

    def _keys(self, prefix):
        """Every key in the bucket under a prefix."""
        client = self._get_client()
        keys, token = [], None
        while True:
            kwargs = {"Bucket": self._bucket(), "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            page = client.list_objects_v2(**kwargs)
            keys += [o["Key"] for o in page.get("Contents", [])]
            if not page.get("IsTruncated"):
                return keys
            token = page.get("NextContinuationToken")

    def themes(self):
        """The name of every theme folder in the bucket."""
        client = self._get_client()
        names, token = [], None
        while True:
            kwargs = {"Bucket": self._bucket(), "Delimiter": "/"}
            if token:
                kwargs["ContinuationToken"] = token
            page = client.list_objects_v2(**kwargs)
            names += [p["Prefix"].rstrip("/") for p in page.get("CommonPrefixes", [])]
            if not page.get("IsTruncated"):
                return sorted(names)
            token = page.get("NextContinuationToken")

    def republish_all(self, dry_run=False):
        """Rebuild every provisioner-made theme from the current base, each with
        the branding it was last published with. Hand-made themes are skipped."""
        results = []
        for theme in self.themes():
            status = self.status(theme)
            if not status["generated"]:
                reason = "made by hand" if status["uploaded"] else "no login theme"
                results.append({"theme": theme, "status": "skipped", "reason": reason})
                continue
            if dry_run:
                branding, _ = self.stored(theme)
                results.append({"theme": theme, "status": "would publish", "company_name": branding["company_name"]})
                continue
            try:
                published = self.publish(theme)
                results.append({"theme": theme, "status": "published", "files": published["files"]})
            except Exception as e:  # one broken theme must not stop the rest
                results.append({"theme": theme, "status": "failed", "reason": str(e)})
        return {"bucket": self._bucket(), "dry_run": dry_run, "themes": results}

# Login theme fonts

The fonts a company can pick for its Keycloak login pages (login theme branding:
`heading_font`, `body_font`). Only the chosen fonts are copied into a company's
theme, so login pages serve them from Keycloak itself and never call Google.

`manifest.json` lists each font's family, the weight its headings use, and its
latin / latin-ext `@font-face` files in `files/`. To add a font or refresh them:

    python scripts/fetch_login_fonts.py optibroker_common/login_theme/fonts

All of these fonts are from Google Fonts under the SIL Open Font License 1.1
(https://openfontlicense.org), which allows them to be bundled and served.

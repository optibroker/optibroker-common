"""Download the login theme's selectable fonts (latin + latin-ext woff2) from
Google Fonts into <out>/files and write <out>/manifest.json.

    python scripts/fetch_login_fonts.py optibroker_common/login_theme/fonts
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

# id: (family, category, weights, heading weight)
FONTS = {
    "inter": ("Inter", "sans", "400;500;600;700", 600),
    "dm-sans": ("DM Sans", "sans", "400;500;600;700", 600),
    "lato": ("Lato", "sans", "400;700", 700),
    "montserrat": ("Montserrat", "sans", "400;500;600;700", 600),
    "nunito-sans": ("Nunito Sans", "sans", "400;500;600;700", 700),
    "open-sans": ("Open Sans", "sans", "400;500;600;700", 600),
    "poppins": ("Poppins", "sans", "400;500;600;700", 600),
    "source-sans-3": ("Source Sans 3", "sans", "400;500;600;700", 600),
    "work-sans": ("Work Sans", "sans", "400;500;600;700", 600),
    "playfair-display": ("Playfair Display", "serif", "400;500;600;700", 600),
    "merriweather": ("Merriweather", "serif", "400;700", 700),
    "lora": ("Lora", "serif", "400;500;600;700", 600),
    "libre-baskerville": ("Libre Baskerville", "serif", "400;700", 700),
    "fraunces": ("Fraunces", "serif", "400;500;600;700", 600),
    "source-serif-4": ("Source Serif 4", "serif", "400;500;600;700", 600),
    "dm-serif-display": ("DM Serif Display", "serif", "400", 400),
}
SUBSETS = ("latin", "latin-ext")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
FACE = re.compile(r"/\*\s*([\w-]+)\s*\*/\s*@font-face\s*\{([^}]*)\}", re.S)


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
        return r.read()


out = Path(sys.argv[1])
(out / "files").mkdir(parents=True, exist_ok=True)
manifest = {}
for font_id, (family, category, weights, heading_weight) in FONTS.items():
    query = f"family={family.replace(' ', '+')}:wght@{weights}&display=swap"
    css = get(f"https://fonts.googleapis.com/css2?{query}").decode()
    faces, seen = [], {}
    for subset, body in FACE.findall(css):
        if subset not in SUBSETS:
            continue
        url = re.search(r"url\((https://[^)]+\.woff2)\)", body).group(1)
        weight = re.search(r"font-weight:\s*([\d ]+);", body).group(1).strip()
        unicode_range = re.search(r"unicode-range:\s*([^;]+);", body).group(1).strip()
        if url not in seen:
            seen[url] = f"{font_id}-{subset}-{weight.replace(' ', '-')}.woff2"
            (out / "files" / seen[url]).write_bytes(get(url))
        faces.append({"weight": weight, "unicode_range": unicode_range, "file": seen[url]})
    # A variable font lists the same file once per weight; one face covers them all.
    by_file = {}
    for f in faces:
        by_file.setdefault(f["file"], []).append(f)
    merged = []
    for file, group in by_file.items():
        ws = sorted(int(w) for g in group for w in g["weight"].split())
        weight = str(ws[0]) if ws[0] == ws[-1] else f"{ws[0]} {ws[-1]}"
        merged.append({"weight": weight, "unicode_range": group[0]["unicode_range"], "file": file})
    manifest[font_id] = {"family": family, "category": category, "heading_weight": heading_weight, "faces": merged}
    sys.stdout.write(f"{family}: {len(merged)} faces\n")

(out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
total = sum(p.stat().st_size for p in (out / "files").iterdir())
sys.stdout.write(f"{len(list((out / 'files').iterdir()))} files, {total // 1024} KB\n")

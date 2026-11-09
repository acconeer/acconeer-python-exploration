# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Add Lucide icons to the app's icon font. Run as ``hatch run icons:update <names>``.

The app ships Lucide's icon font cut down to the icons it uses, with their
codepoints for qtawesome. This rebuilds both from Lucide's release, keeping
the icons already there and adding ``<names>``, as https://lucide.dev names
them.
"""

import argparse
import json
import sys
import urllib.request
from io import BytesIO
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont


LUCIDE_VERSION = "1.73.0"
RELEASE_URL = f"https://unpkg.com/lucide-static@{LUCIDE_VERSION}"
ICONS_DIR = Path("src/acconeer/exptool/app/resources/icons")


def _download(path: str) -> bytes:
    with urllib.request.urlopen(f"{RELEASE_URL}/{path}", timeout=60) as response:
        data: bytes = response.read()
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="Lucide names of the icons to add")
    args = parser.parse_args()

    charmap_path = ICONS_DIR / "lucide.json"
    names = set(json.loads(charmap_path.read_text())) | set(args.names)

    info = json.loads(_download("font/info.json"))
    unknown = sorted(names - info.keys())
    if unknown:
        sys.exit(f"Lucide {LUCIDE_VERSION} has no icons named {', '.join(unknown)}")
    charmap = {name: "0x" + info[name]["encodedCode"].lstrip("\\") for name in sorted(names)}

    font = TTFont(BytesIO(_download("font/lucide.ttf")))
    options = subset.Options()
    options.layout_features = []
    options.name_IDs = ["*"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=[int(code, 16) for code in charmap.values()])
    subsetter.subset(font)

    font.save(ICONS_DIR / "lucide.ttf")
    charmap_path.write_text(json.dumps(charmap, indent=1) + "\n", newline="\n")
    print(f"{len(charmap)} icons of Lucide {LUCIDE_VERSION} in {ICONS_DIR}")


if __name__ == "__main__":
    main()

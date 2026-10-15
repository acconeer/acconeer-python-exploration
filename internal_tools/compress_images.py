# Copyright (c) Acconeer AB, 2026
# All rights reserved

"""Shrink docs images in place. Run as ``hatch run docs:compress-images <paths>``.

Git keeps every byte of every committed image, so shrink before committing.
"""

import argparse
import io
import subprocess
import sys
from pathlib import Path

import imagequant
import oxipng
from PIL import Image, ImageOps


# Wider than any docs page shows, with room for high-DPI screens.
MAX_EDGE = 1920
JPEG_QUALITY = 75
SUFFIXES = (".png", ".jpg", ".jpeg")
# Smaller savings aren't worth a commit or a review comment.
MIN_SAVED = 10_000


def _fit(im: Image.Image) -> Image.Image:
    im = ImageOps.exif_transpose(im)
    if max(im.size) > MAX_EDGE:
        im.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    return im


def _jpeg(data: bytes) -> bytes:
    im = _fit(Image.open(io.BytesIO(data))).convert("RGB")
    out = io.BytesIO()
    im.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return out.getvalue()


def _png(data: bytes) -> bytes:
    im = Image.open(io.BytesIO(data))
    if im.mode == "P" and max(im.size) <= MAX_EDGE:
        # Quantizing a palette again loses detail on every run.
        return oxipng.optimize_from_memory(data, level=4)
    im = _fit(im).convert("RGBA")
    try:
        im = imagequant.quantize_pil_image(
            im, dithering_level=1.0, max_colors=256, min_quality=70, max_quality=95
        )
    except RuntimeError:
        pass  # Too many colours for a palette at that quality: keep full colour.
    out = io.BytesIO()
    im.save(out, "PNG")
    return oxipng.optimize_from_memory(out.getvalue(), level=4)


def _maybe_photo(data: bytes) -> bool:
    # Only a hint: some screenshots have more colours than some photos.
    im = _fit(Image.open(io.BytesIO(data))).convert("RGBA")
    if im.getchannel("A").getextrema()[0] < 255:
        return False  # JPEG can't keep the transparency.
    return im.convert("RGB").getcolors(1 << 14) is None


def _git(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True, check=True).stdout


def _committed(rev: str) -> list[tuple[Path, bytes]]:
    """The images ``rev`` adds or changes, as committed."""
    show = ["show", "--format=", "--name-only", "--diff-filter=AM", "--diff-merges=first-parent"]
    patterns = [f":(icase)*{suffix}" for suffix in SUFFIXES]
    names = _git(*show, rev, "--", *patterns).decode().splitlines()
    return [(Path(name), _git("show", f"{rev}:{name}")) for name in names]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--check", action="store_true", help="report savings, write nothing")
    parser.add_argument(
        "--rev", help="report on the images this commit adds or changes, instead of paths"
    )
    parser.add_argument(
        "--to-jpeg", action="store_true", help="replace the given PNG photos with JPEGs"
    )
    args = parser.parse_args()
    if bool(args.rev) == bool(args.paths):
        parser.error("give either paths or --rev")

    if args.to_jpeg:
        if args.rev or args.check:
            parser.error("--to-jpeg takes only paths")
        for png in args.paths:
            if png.suffix.lower() != ".png" or png.with_suffix(".jpg").exists():
                parser.error(f"{png}: --to-jpeg needs a .png with no .jpg beside it")
        for png in args.paths:
            jpg = png.with_suffix(".jpg")
            jpg.write_bytes(_jpeg(png.read_bytes()))
            png.unlink()
            print(f"{png} -> {jpg}: {jpg.stat().st_size / 1e3:.0f} kB. Update references to it.")
        return

    if args.rev:
        args.check = True
        files = _committed(args.rev)
    else:
        files = [(p, p.read_bytes()) for p in args.paths if p.suffix.lower() in SUFFIXES]

    flagged = False
    for path, data in files:
        suffix = path.suffix.lower()
        if suffix == ".png" and _maybe_photo(data):
            # A palette would make a photo grainy, so leave it for a person to judge.
            flagged = True
            print(f"{path}: over 16k colours. If it's a photo or render, rerun with --to-jpeg.")
            continue
        new = (_png if suffix == ".png" else _jpeg)(data)
        if len(new) >= 0.9 * len(data) or len(data) - len(new) < MIN_SAVED:
            continue
        flagged = True
        print(f"{path}: {len(data) / 1e3:.0f} -> {len(new) / 1e3:.0f} kB")
        if not args.check:
            path.write_bytes(new)

    if args.rev:
        # A report for the review skill: only a failure to run exits non-zero.
        if not flagged:
            print("nothing to shrink")
    elif args.check and flagged:
        sys.exit(1)


if __name__ == "__main__":
    main()

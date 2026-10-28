#!/usr/bin/env python3
"""Create deterministic responsive home images and compact frontend logo variants.

Home image variants are derived from the existing, persistent Django media files
at deploy time. They are not source assets and must not be committed to Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

from PIL import Image, __version__ as PILLOW_VERSION
from PIL import ImageDraw


HOME_VARIANT_VERSION = "home-hero-v1"
HOME_WIDTHS = (320, 480, 640, 800)
HOME_SOURCES = {
    "cohiba-bhk-56": "cigars/cohiba/bhk-56/cohiba-bhk-562-cigar.jpg",
    "cohiba-siglo-vi": "cigars/cohiba/siglo-vi/cohiba-siglo-vi7-cigar.jpg",
    "trinidad-casilda": "cigars/trinidad/casilda-habanos-collection-series/trinidad-casilda1-cigar.jpg",
    "cohiba-bhk-52": "cigars/cohiba/bhk-52/cohiba-bhk-52-cigar.jpg",
    "trinidad-ingenios": "cigars/trinidad/ingenios-limited-edition-series/trinidad-ingenios-cigar.jpg",
}
HOME_EXPECTED_DIMS = {
    "cohiba-bhk-56": (997, 139),
    "cohiba-siglo-vi": (999, 145),
    "trinidad-casilda": (998, 119),
    "cohiba-bhk-52": (996, 171),
    "trinidad-ingenios": (999, 101),
}
LOGO_SOURCE = "logo-motion.webp"
LOGO_WIDTHS = (112, 176, 188, 376, 564)
EXPORT_PARAMETERS = {
    "format": "webp",
    "quality": 82,
    "method": 6,
    "resampling": "lanczos",
    "home_widths": [*HOME_WIDTHS, "source"],
    "logo_widths": [*LOGO_WIDTHS, "source"],
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def save_variants(source: Image.Image, target_dir: Path, stem: str, widths: tuple[int, ...]) -> list[dict[str, object]]:
    source_width, source_height = source.size
    if source_width < 1 or source_height < 1:
        raise ValueError(f"Invalid source dimensions for {stem}: {source.size}")
    target_widths = sorted({min(width, source_width) for width in (*widths, source_width)})
    outputs = []
    target_dir.mkdir(parents=True, exist_ok=True)
    for width in target_widths:
        height = round(source_height * width / source_width)
        resized = source.resize((width, height), Image.Resampling.LANCZOS)
        if resized.mode not in ("RGB", "RGBA"):
            resized = resized.convert("RGBA" if "A" in resized.getbands() else "RGB")
        output = target_dir / f"{stem}-{width}.webp"
        resized.save(output, format="WEBP", quality=EXPORT_PARAMETERS["quality"], method=EXPORT_PARAMETERS["method"])
        outputs.append({"path": output.name, "width": width, "height": height, "bytes": output.stat().st_size})
    return outputs


def generate_home(media_root: Path) -> Path:
    output_dir = media_root / HOME_VARIANT_VERSION
    media_root.mkdir(parents=True, exist_ok=True)
    source_images: dict[str, tuple[str, Path, Image.Image]] = {}
    for stem, relative_source in HOME_SOURCES.items():
        source_path = media_root / relative_source
        if not source_path.is_file():
            raise FileNotFoundError(f"Missing existing home image source: {source_path}")
        with Image.open(source_path) as source:
            source.load()
            expected = HOME_EXPECTED_DIMS[stem]
            if source.size != expected:
                raise ValueError(f"Unexpected source dimensions for {source_path}: expected {expected}, got {source.size}")
            source_images[stem] = (relative_source, source_path, source.copy())

    manifest: dict[str, object] = {
        "version": HOME_VARIANT_VERSION,
        "pillow": PILLOW_VERSION,
        "export": EXPORT_PARAMETERS,
        "sources": {},
    }
    with tempfile.TemporaryDirectory(prefix=f".{HOME_VARIANT_VERSION}-", dir=media_root) as temp:
        stage_dir = Path(temp)
        staged_manifest: dict[str, object] = dict(manifest)
        staged_sources: dict[str, object] = {}
        for stem, (relative_source, source_path, source_image) in source_images.items():
            staged_sources[stem] = {
                "path": relative_source,
                "sha256": sha256(source_path),
                "width": source_image.width,
                "height": source_image.height,
                "variants": save_variants(source_image, stage_dir, stem, HOME_WIDTHS),
            }
        staged_manifest["sources"] = staged_sources
        (stage_dir / "manifest.json").write_text(json.dumps(staged_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        output_dir.mkdir(parents=True, exist_ok=True)
        for staged in sorted(stage_dir.iterdir(), key=lambda item: item.name == "manifest.json"):
            os.replace(staged, output_dir / staged.name)
    return output_dir


def generate_logos(public_root: Path) -> Path:
    source_path = public_root / LOGO_SOURCE
    if not source_path.is_file():
        raise FileNotFoundError(f"Missing tracked logo source: {source_path}")
    with Image.open(source_path) as source:
        source.load()
        with tempfile.TemporaryDirectory(prefix=".logo-motion-", dir=public_root) as temp:
            stage_dir = Path(temp)
            save_variants(source, stage_dir, "logo-motion", LOGO_WIDTHS)
            for staged in stage_dir.iterdir():
                os.replace(staged, public_root / staged.name)
    return public_root


def verify_fixture() -> None:
    """Exercise full home and transparent logo conversions without production media."""
    with tempfile.TemporaryDirectory(prefix="seo-22-image-fixture-") as temp:
        root = Path(temp)
        media_root = root / "media"
        for index, (stem, relative_path) in enumerate(HOME_SOURCES.items()):
            path = media_root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", HOME_EXPECTED_DIMS[stem], (70 + index * 20, 85, 105)).save(path, format="JPEG", quality=90)
        source_hashes = {path: sha256(media_root / path) for path in HOME_SOURCES.values()}
        first_output = generate_home(media_root)
        first_hashes = {path.name: sha256(path) for path in first_output.iterdir()}
        if len(json.loads((first_output / "manifest.json").read_text())["sources"]) != 5:
            raise RuntimeError("Fixture manifest did not record all five home images")
        generate_home(media_root)
        if {path.name: sha256(path) for path in first_output.iterdir()} != first_hashes:
            raise RuntimeError("Repeated home generation was not idempotent")
        if {path: sha256(media_root / path) for path in HOME_SOURCES.values()} != source_hashes:
            raise RuntimeError("Home generator modified a source JPEG")
        for path in first_output.glob("*.webp"):
            with Image.open(path) as image:
                image.verify()
        for stem, dimensions in HOME_EXPECTED_DIMS.items():
            expected_widths = [*HOME_WIDTHS, dimensions[0]]
            actual_widths = sorted(int(path.stem.rsplit("-", 1)[1]) for path in first_output.glob(f"{stem}-*.webp"))
            if actual_widths != sorted(set(expected_widths)):
                raise RuntimeError(f"Incomplete responsive home variants for {stem}: {actual_widths}")

        missing_root = root / "missing-media"
        try:
            generate_home(missing_root)
        except FileNotFoundError:
            if (missing_root / HOME_VARIANT_VERSION).exists():
                raise RuntimeError("Missing-source validation wrote partial outputs")
        else:
            raise RuntimeError("Missing-source fixture unexpectedly succeeded")

        public_root = root / "public"
        public_root.mkdir()
        logo_source = Image.new("RGBA", (640, 525), (0, 0, 0, 0))
        ImageDraw.Draw(logo_source).rectangle((270, 215, 370, 315), fill=(150, 25, 40, 255))
        logo_source.save(public_root / LOGO_SOURCE, format="WEBP", lossless=True)
        logo_source_hash = sha256(public_root / LOGO_SOURCE)
        generate_logos(public_root)
        logo_outputs = list(public_root.glob("logo-motion-*.webp"))
        logo_hashes = {path.name: sha256(path) for path in logo_outputs}
        generate_logos(public_root)
        if {path.name: sha256(path) for path in public_root.glob("logo-motion-*.webp")} != logo_hashes:
            raise RuntimeError("Repeated logo generation was not idempotent")
        if sha256(public_root / LOGO_SOURCE) != logo_source_hash:
            raise RuntimeError("Logo generator modified the source logo")
        logo_widths = set()
        for path in logo_outputs:
            with Image.open(path) as image:
                logo_widths.add(image.width)
                if image.mode != "RGBA" or image.getpixel((0, 0))[3] != 0 or image.getpixel((image.width // 2, image.height // 2))[3] == 0:
                    raise RuntimeError(f"Transparent logo was not preserved in {path.name}")
        if not {112, 176, 188, 376, 564, 640}.issubset(logo_widths):
            raise RuntimeError("Transparent logo fixture omitted a responsive width")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--media-root", type=Path, help="Django MEDIA_ROOT containing the five original JPEGs")
    parser.add_argument("--public-root", type=Path, help="frontend/public containing tracked logo-motion.webp")
    parser.add_argument("--check-fixture", action="store_true", help="Verify WebP output with a temporary synthetic JPEG")
    args = parser.parse_args()
    if args.check_fixture:
        verify_fixture()
        print("Responsive image fixture passed")
    if args.media_root:
        print(f"Generated home image variants: {generate_home(args.media_root.resolve())}")
    if args.public_root:
        print(f"Generated logo variants: {generate_logos(args.public_root.resolve())}")
    if not (args.check_fixture or args.media_root or args.public_root):
        parser.error("Choose --check-fixture, --media-root, or --public-root")


if __name__ == "__main__":
    main()

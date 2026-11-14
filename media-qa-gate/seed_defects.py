#!/usr/bin/env python3
"""Seed the five (six) defect kinds this surface actually produces.

The seeds are *derived copies* of real corpus artifacts (blur / resize /
crush / placeholder), written into ``media-qa-gate/seeded/``.  No new image
content is generated: every seed starts from a copied real artifact.

Seeded defect kinds (from the issue's list, restricted to what a Godot
screenshot pipeline for armored-archer actually produces):

  1. placeholder_1x1        - a 1x1 transparent/colour placeholder was
                              written instead of the capture
  2. solid_colour_frame     - the capture wrote a single flat colour frame
  3. wrong_dimensions       - the frame was exported at the wrong size
  4. blurred_frame          - the frame was captured/filtered out of focus
  5. crushed_exposure       - the frame was captured with collapsed exposure
  6. duplicate_frame        - the same frame was copied into two slots

Usage:
    python3 media-qa-gate/seed_defects.py [--corpus DIR] [--dest DIR]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))


def seed_placeholder_1x1(src: str, dst: str) -> None:
    with Image.open(src) as im:
        im.load()
        im.convert("RGBA").resize((1, 1), Image.NEAREST).save(dst)


def seed_solid_colour(src: str, dst: str) -> None:
    with Image.open(src) as im:
        im.load()
        solid = Image.new("RGB", im.size, (24, 26, 32))
        solid.save(dst)


def seed_wrong_dimensions(src: str, dst: str) -> None:
    with Image.open(src) as im:
        im.load()
        im.convert("RGB").resize((160, 120), Image.LANCZOS).save(dst)


def seed_blurred(src: str, dst: str) -> None:
    with Image.open(src) as im:
        im.load()
        im.convert("RGB").filter(ImageFilter.GaussianBlur(3)).save(dst)


def seed_crushed(src: str, dst: str) -> None:
    with Image.open(src) as im:
        im.load()
        rgb = im.convert("RGB")
        dark = Image.new("RGB", rgb.size, (0, 0, 0))
        blended = Image.blend(dark, rgb, 0.04)
        blended.save(dst)


def seed_duplicate(src: str, dst: str) -> None:
    shutil.copyfile(src, dst)


SEEDS = [
    {
        "id": "placeholder_1x1",
        "kind": "1x1 placeholder",
        "from": "android/screenshots/combat.png",
        "out": "placeholder_1x1.png",
        "fn": seed_placeholder_1x1,
        "expected_check": "dimensions",
    },
    {
        "id": "solid_colour_frame",
        "kind": "single-colour frame",
        "from": "android/screenshots/campaign.png",
        "out": "solid_colour_frame.png",
        "fn": seed_solid_colour,
        "expected_check": "blank",
    },
    {
        "id": "wrong_dimensions",
        "kind": "wrong dimensions",
        "from": "android/screenshots/main_menu.png",
        "out": "wrong_dimensions.png",
        "fn": seed_wrong_dimensions,
        "expected_check": "dimensions",
    },
    {
        "id": "blurred_frame",
        "kind": "blurred frame",
        "from": "ios/screenshots/iphone_5_5/campaign.png",
        "out": "blurred_frame.png",
        "fn": seed_blurred,
        "expected_check": "sharpness",
    },
    {
        "id": "crushed_exposure",
        "kind": "crushed exposure",
        "from": "ios/screenshots/iphone_6_7/combat.png",
        "out": "crushed_exposure.png",
        "fn": seed_crushed,
        "expected_check": "exposure",
    },
    {
        "id": "duplicate_frame_a",
        "kind": "duplicate frame, first copy of a slot pair",
        "from": "ios/screenshots/ipad/campaign.png",
        "out": "duplicate_slot/campaign.png",
        "fn": seed_duplicate,
        "expected_check": "duplicate",
        "expect_error": False,
        "note": "the first copy of the pair; the duplicate check can only "
                "fire on the second occurrence",
    },
    {
        "id": "duplicate_frame_b",
        "kind": "duplicate frame, second copy of the same slot pair",
        "from": "ios/screenshots/ipad/campaign.png",
        "out": "duplicate_slot/campaign_copy.png",
        "fn": seed_duplicate,
        "expected_check": "duplicate",
        "expect_error": True,
        "note": "pixel-identical to duplicate_slot/campaign.png in the same "
                "submission group",
    },
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=os.path.join(HERE, "corpus"))
    ap.add_argument("--dest", default=os.path.join(HERE, "seeded"))
    args = ap.parse_args()

    os.makedirs(args.dest, exist_ok=True)
    index = []
    for seed in SEEDS:
        src = os.path.join(args.corpus, seed["from"])
        if not os.path.isfile(src):
            print(f"seed_defects: missing source {src}", file=sys.stderr)
            return 2
        dst = os.path.join(args.dest, seed["out"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        seed["fn"](src, dst)
        index.append({
            "id": seed["id"],
            "kind": seed["kind"],
            "derived_from": seed["from"],
            "file": seed["out"],
            "expected_check": seed["expected_check"],
            "expect_error": seed.get("expect_error", True),
            "note": seed.get("note", ""),
        })
        print(f"seeded {seed['id']:18s} -> {os.path.relpath(dst, HERE)}")

    with open(os.path.join(args.dest, "seeds.json"), "w", encoding="utf-8") as fh:
        json.dump({"seeds": index}, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

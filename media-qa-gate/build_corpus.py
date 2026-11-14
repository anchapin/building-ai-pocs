#!/usr/bin/env python3
"""Build the media-qa-gate corpus from armored-archer's real store assets.

READ-ONLY with respect to the source repository: this script only reads
``<aa-root>/app_store_assets`` and writes copies plus a manifest into
``media-qa-gate/corpus/``.  The source tree is never modified.

Usage:
    python3 media-qa-gate/build_corpus.py [--aa-root PATH] [--dest PATH]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

DEFAULT_AA_ROOT = os.path.expanduser("~/workspace/armored-archer")

# Declared store dimensions, quoted from armored-archer's
# app_store_assets/SCREENSHOT_SPEC.md ("Platform Requirements").
SPEC_EXPECTED = {
    "ios/screenshots/iphone_6_7": [1290, 2796],
    "ios/screenshots/iphone_5_5": [1242, 2208],
    "ios/screenshots/ipad": [2048, 2732],
    "android/screenshots": [1080, 1920],   # portrait slots only
}
# Files in the android screenshot folder that are *not* portrait slots
# (landscape extras) - no declared spec, floor checks only.
NO_SPEC = {
    "android/screenshots/screenshot_1.png",
    "android/screenshots/screenshot_2.png",
    "android/screenshots/screenshot_3.png",
}


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aa-root", default=DEFAULT_AA_ROOT)
    ap.add_argument("--dest", default=os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "corpus"))
    args = ap.parse_args()

    src_root = os.path.join(args.aa_root, "app_store_assets")
    if not os.path.isdir(src_root):
        print(f"build_corpus: source not found: {src_root}", file=sys.stderr)
        return 2

    files = []
    for root, _dirs, names in os.walk(src_root):
        for name in sorted(names):
            if name.lower().endswith(".png"):
                files.append(os.path.join(root, name))
    files.sort()

    os.makedirs(args.dest, exist_ok=True)
    artifacts = []
    for path in files:
        rel = os.path.relpath(path, src_root).replace(os.sep, "/")
        dst = os.path.join(args.dest, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(path, dst)  # copy only; source untouched
        expected = None
        for prefix, dims in SPEC_EXPECTED.items():
            if rel.startswith(prefix + "/") and rel not in NO_SPEC:
                expected = dims
                break
        entry = {
            "file": rel,
            "source": f"armored-archer/app_store_assets/{rel}",
            "source_absolute": path,
            "bytes": os.path.getsize(path),
            "sha256": sha256(path),
            "group": os.path.dirname(rel),
        }
        if expected:
            entry["expected"] = expected
            entry["spec_ref"] = "app_store_assets/SCREENSHOT_SPEC.md"
        artifacts.append(entry)

    manifest = {
        "description": "Real armored-archer store artifacts copied "
                       "read-only into this worktree. No generated images.",
        "source_root": args.aa_root,
        "source_subtree": "app_store_assets",
        "count": len(artifacts),
        "artifacts": artifacts,
    }
    mpath = os.path.join(args.dest, "manifest.json")
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(f"copied {len(artifacts)} artifacts into {args.dest}")
    print(f"manifest: {mpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Head-to-head: mediaqa pixel floor vs armored-archer's RMSE screenshot suite.

Two things happen here:

1. The real suite is *invoked read-only* against armored-archer's
   ``scripts/compare-screenshots.py`` (it only reads the two inputs and
   writes the diff image this script points at).  If ImageMagick's
   ``compare`` binary is missing, the failure is recorded verbatim - the
   suite is not stubbed or re-implemented in place of it.

2. A pure-numpy *RMSE-equivalent* is computed for the same pairs, using
   the same arithmetic ImageMagick uses (8-bit RMSE normalised by 255, the
   value the suite parses out of ``compare``'s parentheses) and the suite's
   own threshold (0.01 normalised).  This is a measurement aid, clearly
   labelled as an emulation - it is NOT the suite.

Usage:
    python3 media-qa-gate/head_to_head.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "corpus")
SEEDED = os.path.join(HERE, "seeded")
AA_ROOT = os.path.expanduser("~/workspace/armored-archer")
RMSE_SUITE = os.path.join(AA_ROOT, "scripts", "compare-screenshots.py")
RMSE_THRESHOLD = 0.01  # from scripts/compare-screenshots.py --threshold default


def rmse_equivalent(a_path: str, b_path: str):
    """Normalised RMSE exactly as ImageMagick reports it for 8-bit images."""
    with Image.open(a_path) as ia, Image.open(b_path) as ib:
        ia = ia.convert("RGB")
        ib = ib.convert("RGB")
        if ia.size != ib.size:
            return None, ia.size, ib.size
        a = np.asarray(ia, dtype=np.float64)
        b = np.asarray(ib, dtype=np.float64)
        rmse8 = float(np.sqrt(((a - b) ** 2).mean()))
        return rmse8 / 255.0, ia.size, ib.size


def run_real_suite(current: str, baseline: str) -> str:
    """Invoke armored-archer's RMSE suite read-only; return its raw output."""
    if not os.path.isfile(RMSE_SUITE):
        return "suite script not found"
    if shutil.which("compare") is None:
        return ("SKIPPED: ImageMagick 'compare' binary is not installed on "
                "this VM - the suite cannot be executed here")
    out_dir = tempfile.mkdtemp(prefix="mediaqa-h2h-", dir=HERE)
    try:
        proc = subprocess.run(
            [sys.executable, RMSE_SUITE, "--current", current,
             "--baseline", baseline,
             "--output", os.path.join(out_dir, "diff.png")],
            capture_output=True, text=True)
        return (proc.stdout + proc.stderr).strip() + \
               f" [exit={proc.returncode}]"
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)


PAIRS = [
    # (label, current, baseline, note)
    ("placeholder_1x1 vs its source",
     os.path.join(SEEDED, "placeholder_1x1.png"),
     os.path.join(CORPUS, "android/screenshots/combat.png"),
     "single artifact, no baseline exists in the wild"),
    ("solid_colour_frame vs its source",
     os.path.join(SEEDED, "solid_colour_frame.png"),
     os.path.join(CORPUS, "android/screenshots/campaign.png"),
     "single artifact, no baseline exists in the wild"),
    ("wrong_dimensions vs its source",
     os.path.join(SEEDED, "wrong_dimensions.png"),
     os.path.join(CORPUS, "android/screenshots/main_menu.png"),
     "single artifact, no baseline exists in the wild"),
    ("blurred_frame vs its source",
     os.path.join(SEEDED, "blurred_frame.png"),
     os.path.join(CORPUS, "ios/screenshots/iphone_5_5/campaign.png"),
     "single artifact, no baseline exists in the wild"),
    ("crushed_exposure vs its source",
     os.path.join(SEEDED, "crushed_exposure.png"),
     os.path.join(CORPUS, "ios/screenshots/iphone_6_7/combat.png"),
     "single artifact, no baseline exists in the wild"),
    ("real duplicate pair (ipad screenshot_1 vs screenshot_2)",
     os.path.join(CORPUS, "ios/screenshots/ipad/screenshot_2.png"),
     os.path.join(CORPUS, "ios/screenshots/ipad/screenshot_1.png"),
     "two slots of one submission group that are pixel-identical"),
]


def main() -> int:
    rows = []
    for label, current, baseline, note in PAIRS:
        value, cur_size, base_size = rmse_equivalent(current, baseline)
        suite = run_real_suite(current, baseline)
        rows.append({
            "pair": label,
            "current": os.path.relpath(current, HERE),
            "baseline": os.path.relpath(baseline, HERE),
            "current_size": list(cur_size),
            "baseline_size": list(base_size),
            "rmse_equivalent_normalised": None if value is None else round(value, 6),
            "rmse_suite_verdict": "FAIL" if (value is None or value > RMSE_THRESHOLD) else "PASS",
            "note": note,
            "real_suite_output": suite,
        })

    print(f"RMSE suite script: {RMSE_SUITE}")
    print(f"threshold (normalised): {RMSE_THRESHOLD}")
    print("")
    print(f"{'pair':52s} {'rmse_eq':>10s} {'suite_verdict':>13s}")
    print("-" * 80)
    for r in rows:
        val = r["rmse_equivalent_normalised"]
        print(f"{r['pair']:52s} "
              f"{('n/a (size mismatch)' if val is None else f'{val:.6f}'):>10s} "
              f"{r['rmse_suite_verdict']:>13s}")
    print("")
    print("real suite output (first pair):")
    print("  " + rows[0]["real_suite_output"])
    with open(os.path.join(HERE, "head_to_head.json"), "w", encoding="utf-8") as fh:
        json.dump({"threshold": RMSE_THRESHOLD, "rows": rows}, fh, indent=2)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

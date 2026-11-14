#!/usr/bin/env python3
"""mediaqa - a universal pixel floor for gameplay / store screenshots.

This is POC #51 Phase 0 slice 1, issue #57: a *report-only* checker that
applies five universal pixel-level checks to a set of image artifacts:

    blank       no luminance structure at all (placeholder / solid frame)
    dimensions  degenerate or store-illegal geometry
    exposure    crushed (all-black) or blown-out (all-white) frames
    sharpness   blurred frames
    duplicate   byte/pixel-identical artifacts inside one submission group

Every finding is emitted as one line:

    error|warn <check> <measurement>; <fix hint>

Exit code is 1 when at least one ``error`` finding exists, otherwise 0.

Design rules for this slice (hard constraints from the issue):

* report-only - nothing here blocks a merge, a build, or a store upload;
* deterministic - no wall-clock dependence in any pass/fail decision, no
  unseeded randomness, no network access, no LLM/VLM in the decision path;
* pure Python + Pillow (+ NumPy) - no image toolchain provisioning.

The checker never writes to the scanned trees; it only reads them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from PIL import Image  # type: ignore
except ImportError as exc:  # pragma: no cover - environment guard
    raise SystemExit(
        "mediaqa requires Pillow (pip install Pillow). No fallback decoder is "
        "vendored on purpose: a hand-rolled PNG reader would be a liability."
    ) from exc

import numpy as np  # type: ignore

# --------------------------------------------------------------------------
# Thresholds.  Every number here is either a store spec limit quoted from
# armored-archer's app_store_assets/SCREENSHOT_SPEC.md or a measurement
# threshold chosen with a wide margin over the observed real corpus (see
# REPORT.md section "Threshold margins").
# --------------------------------------------------------------------------

# blank check
BLANK_STD_ERROR = 3.0          # luma std-dev below this = no structure
BLANK_STD_WARN = 5.0           # thin but non-zero structure
BLANK_MODAL_WARN = 0.995       # fraction of pixels sharing one exact colour

# dimensions check (Android phone spec: min 320px shortest side, max 3840px
# longest side; aspect sanity is a universal guard, not a store rule)
MIN_SIDE_PX = 320
MAX_SIDE_PX = 3840
ASPECT_MIN = 0.2
ASPECT_MAX = 5.0

# exposure check
DARK_FRAC_ERROR = 0.90         # >= 90 % of pixels at luma <= 3
DARK_FRAC_WARN = 0.50
MEAN_LUMA_MIN_ERROR = 8.0
MEAN_LUMA_MIN_WARN = 20.0
BRIGHT_FRAC_ERROR = 0.90       # >= 90 % of pixels at luma >= 252
BRIGHT_FRAC_WARN = 0.50
MEAN_LUMA_MAX_ERROR = 247.0
MEAN_LUMA_MAX_WARN = 235.0

# sharpness check (variance of the 3x3 Laplacian kernel)
SHARPNESS_ERROR = 20.0
SHARPNESS_WARN = 35.0

CHECKS = ("blank", "dimensions", "exposure", "sharpness", "duplicate")

IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff")


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclass
class Finding:
    level: str          # "error" | "warn"
    check: str
    measurement: str
    hint: str

    def line(self) -> str:
        return f"{self.level} {self.check} {self.measurement}; {self.hint}"


@dataclass
class Cell:
    """One check's result for one artifact."""

    check: str
    status: str = "ok"          # ok | warn | error
    measurement: str = ""
    detail: str = ""


@dataclass
class ArtifactResult:
    path: str
    group: str
    label: str = ""
    cells: Dict[str, Cell] = field(default_factory=dict)
    findings: List[Finding] = field(default_factory=list)
    seconds: float = 0.0
    error: bool = False

    def status(self) -> str:
        if self.error:
            return "error"
        if any(c.status == "warn" for c in self.cells.values()):
            return "warn"
        return "ok"


# --------------------------------------------------------------------------
# Image measurement helpers
# --------------------------------------------------------------------------


def _luma_array(img: "Image.Image") -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float64)


def _rgb_array(img: "Image.Image") -> np.ndarray:
    return np.asarray(img.convert("RGB"), dtype=np.uint8)


def laplacian_variance(luma: np.ndarray) -> float:
    """Variance of the 3x3 Laplacian (kernel [[0,1,0],[1,-4,1],[0,1,0]]).

    Computed with plain slicing (no SciPy dependency) and float32 to keep it
    fast and deterministic.
    """
    if luma.shape[0] < 3 or luma.shape[1] < 3:
        return 0.0
    a = luma.astype(np.float32, copy=False)
    lap = (
        -4.0 * a[1:-1, 1:-1]
        + a[:-2, 1:-1]
        + a[2:, 1:-1]
        + a[1:-1, :-2]
        + a[1:-1, 2:]
    )
    return float(lap.var())


def modal_colour_fraction(rgb: np.ndarray) -> float:
    """Fraction of pixels sharing the single most common exact RGB value."""
    flat = rgb.reshape(-1, 3).astype(np.int64)
    packed = (flat[:, 0] << 16) | (flat[:, 1] << 8) | flat[:, 2]
    counts = np.bincount(packed, minlength=1 << 24)
    return float(counts.max()) / float(packed.size)


# --------------------------------------------------------------------------
# The five checks
# --------------------------------------------------------------------------


def check_blank(img: "Image.Image") -> Tuple[Cell, List[Finding]]:
    luma = _luma_array(img)
    std = float(luma.std())
    mean = float(luma.mean())
    modal = modal_colour_fraction(_rgb_array(img))
    meas = f"luma_std={std:.3f} luma_mean={mean:.2f} modal_frac={modal:.4f}"
    cell = Cell("blank", measurement=meas)
    findings: List[Finding] = []
    if std < BLANK_STD_ERROR:
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "blank",
                meas,
                "frame carries no usable image content (blank / solid-colour "
                "capture); re-capture the scene with the renderer drawing it",
            )
        )
    elif std < BLANK_STD_WARN:
        cell.status = "warn"
        findings.append(
            Finding(
                "warn",
                "blank",
                meas,
                "frame is almost featureless; check that the capture "
                "actually rendered the scene",
            )
        )
    elif modal >= BLANK_MODAL_WARN:
        cell.status = "warn"
        findings.append(
            Finding(
                "warn",
                "blank",
                meas,
                "a single colour covers the whole frame; confirm this is "
                "not a solid-colour capture",
            )
        )
    return cell, findings


def check_dimensions(
    img: "Image.Image", expected: Optional[Sequence[int]] = None
) -> Tuple[Cell, List[Finding]]:
    w, h = img.size
    area = w * h
    aspect = (w / h) if h else 0.0
    meas = f"w={w} h={h} area={area} aspect={aspect:.3f}"
    cell = Cell("dimensions", measurement=meas)
    findings: List[Finding] = []
    if w < MIN_SIDE_PX or h < MIN_SIDE_PX:
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "dimensions",
                meas,
                f"image is smaller than the {MIN_SIDE_PX}px shortest-side "
                "floor; re-export at store resolution (a placeholder was "
                "written instead of the capture)",
            )
        )
    elif max(w, h) > MAX_SIDE_PX:
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "dimensions",
                meas,
                f"longest side exceeds the {MAX_SIDE_PX}px store limit; "
                "downscale before upload",
            )
        )
    elif not (ASPECT_MIN <= aspect <= ASPECT_MAX):
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "dimensions",
                meas,
                f"aspect ratio outside [{ASPECT_MIN}, {ASPECT_MAX}]; "
                "the frame is stretched or letterboxed to the wrong shape",
            )
        )
    elif expected is not None:
        exp_w, exp_h = int(expected[0]), int(expected[1])
        if (w, h) != (exp_w, exp_h):
            cell.status = "warn"
            findings.append(
                Finding(
                    "warn",
                    "dimensions",
                    f"{meas} expected={exp_w}x{exp_h}",
                    "geometry differs from the declared store spec; "
                    "re-capture at the specified resolution",
                )
            )
    return cell, findings


def check_exposure(img: "Image.Image") -> Tuple[Cell, List[Finding]]:
    luma = _luma_array(img)
    mean = float(luma.mean())
    dark = float((luma <= 3).mean())
    bright = float((luma >= 252).mean())
    meas = f"luma_mean={mean:.2f} dark_frac={dark:.4f} bright_frac={bright:.4f}"
    cell = Cell("exposure", measurement=meas)
    findings: List[Finding] = []
    if dark >= DARK_FRAC_ERROR or mean <= MEAN_LUMA_MIN_ERROR:
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "exposure",
                meas,
                "frame is crushed to black; re-capture with the scene "
                "actually lit (exposure/gain was collapsed)",
            )
        )
    elif bright >= BRIGHT_FRAC_ERROR or mean >= MEAN_LUMA_MAX_ERROR:
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "exposure",
                meas,
                "frame is blown out to white; re-capture with a lower "
                "exposure (the capture saturated)",
            )
        )
    elif (
        dark >= DARK_FRAC_WARN
        or bright >= BRIGHT_FRAC_WARN
        or mean <= MEAN_LUMA_MIN_WARN
        or mean >= MEAN_LUMA_MAX_WARN
    ):
        cell.status = "warn"
        findings.append(
            Finding(
                "warn",
                "exposure",
                meas,
                "exposure is close to a crushed/blown frame; check the "
                "capture lighting before upload",
            )
        )
    return cell, findings


def check_sharpness(img: "Image.Image") -> Tuple[Cell, List[Finding]]:
    luma = _luma_array(img)
    std = float(luma.std())
    lapvar = laplacian_variance(luma)
    meas = f"laplacian_var={lapvar:.3f} luma_std={std:.3f}"
    cell = Cell("sharpness", measurement=meas)
    findings: List[Finding] = []
    if std < BLANK_STD_ERROR:
        # A flat frame has no edges to be sharp or blurred about; the blank
        # check already owns that defect, so sharpness stays quiet.
        cell.measurement += " (flat frame: sharpness not applicable)"
        return cell, findings
    if lapvar < SHARPNESS_ERROR:
        cell.status = "error"
        findings.append(
            Finding(
                "error",
                "sharpness",
                meas,
                "frame is blurred (no usable edges); re-capture in focus "
                "or remove the blur/placeholder filter",
            )
        )
    elif lapvar < SHARPNESS_WARN:
        cell.status = "warn"
        findings.append(
            Finding(
                "warn",
                "sharpness",
                meas,
                "frame is soft; confirm the capture was in focus",
            )
        )
    return cell, findings


def pixel_fingerprint(img: "Image.Image") -> str:
    rgb = _rgb_array(img)
    h = hashlib.sha256()
    h.update(f"{rgb.shape[0]}x{rgb.shape[1]}:".encode())
    h.update(rgb.tobytes())
    return h.hexdigest()


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------


def iter_images(paths: Iterable[str]) -> List[str]:
    out: List[str] = []
    for p in paths:
        if os.path.isdir(p):
            for root, _dirs, files in os.walk(p):
                for name in sorted(files):
                    if name.lower().endswith(IMAGE_SUFFIXES):
                        out.append(os.path.join(root, name))
        elif os.path.isfile(p):
            out.append(p)
        else:
            print(f"mediaqa: skipping missing path {p}", file=sys.stderr)
    return sorted(out)


def group_of(path: str, roots: Sequence[str]) -> str:
    """Submission group = the directory the artifact lives in.

    Duplicate detection is scoped per group because a store submission is a
    set (one platform / one device folder). The same icon legitimately ships
    to two stores, so cross-group identity is only a warning.
    """
    ap = os.path.abspath(path)
    best = ""
    for root in roots:
        r = os.path.abspath(root)
        if os.path.isdir(r) and ap.startswith(r + os.sep):
            rel = os.path.relpath(os.path.dirname(ap), r)
            if rel not in (".", "") and len(rel) > len(best):
                best = rel
    if best:
        return best.replace(os.sep, "/")
    return os.path.basename(os.path.dirname(ap)) or "."


def load_manifest(path: Optional[str]) -> Dict[str, Dict]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    entries: Dict[str, Dict] = {}
    for item in data.get("artifacts", []):
        entries[item["file"]] = item
    return entries


def analyze(
    paths: Sequence[str],
    manifest: Optional[Dict[str, Dict]] = None,
    root: Optional[str] = None,
) -> List[ArtifactResult]:
    manifest = manifest or {}
    roots = [root] if root else list(paths)
    files = iter_images(paths)
    results: List[ArtifactResult] = []
    # fingerprint -> (group, first path)
    seen: Dict[str, Tuple[str, str]] = {}

    for path in files:
        started = time.perf_counter()
        group = group_of(path, roots)
        try:
            label = os.path.relpath(path, root) if root else os.path.basename(path)
        except ValueError:
            label = os.path.basename(path)
        res = ArtifactResult(path=path, group=group, label=label.replace(os.sep, "/"))
        try:
            with Image.open(path) as img:
                img.load()
                expected = None
                entry = manifest.get(os.path.relpath(path, root) if root else path)
                if entry and entry.get("expected"):
                    expected = entry["expected"]
                cells = [
                    check_blank(img),
                    check_dimensions(img, expected),
                    check_exposure(img),
                    check_sharpness(img),
                ]
                fingerprint = pixel_fingerprint(img)
                size = img.size
        except Exception as exc:  # unreadable file -> a hard error
            res.seconds = time.perf_counter() - started
            cell = Cell("blank", status="error", measurement="unreadable",
                        detail=str(exc))
            res.cells["blank"] = cell
            res.findings.append(
                Finding("error", "blank", f"unreadable={type(exc).__name__}",
                        "file cannot be decoded; re-export the asset")
            )
            res.error = True
            results.append(res)
            continue

        for cell, findings in cells:
            res.cells[cell.check] = cell
            res.findings.extend(findings)
            if cell.status == "error":
                res.error = True

        # duplicate check (needs the corpus-wide view)
        dup_cell = Cell("duplicate", measurement=f"pixel_sha={fingerprint[:12]}")
        if fingerprint in seen:
            prev_group, prev_path = seen[fingerprint]
            if prev_group == group:
                dup_cell.status = "error"
                dup_cell.detail = prev_path
                res.findings.append(
                    Finding(
                        "error",
                        "duplicate",
                        f"identical_pixels_of={os.path.basename(prev_path)} "
                        f"group={group}",
                        "artifact is pixel-identical to another file in the "
                        "same submission group; store reviewers reject "
                        "duplicated slots - capture a distinct scene",
                    )
                )
                res.error = True
            else:
                dup_cell.status = "warn"
                dup_cell.detail = prev_path
                res.findings.append(
                    Finding(
                        "warn",
                        "duplicate",
                        f"identical_pixels_of={os.path.basename(prev_path)} "
                        f"other_group={prev_group}",
                        "same pixels as an artifact in another submission "
                        "group; expected for shared icons, suspicious "
                        "otherwise",
                    )
                )
        else:
            seen[fingerprint] = (group, path)
        res.cells["duplicate"] = dup_cell

        res.seconds = time.perf_counter() - started
        results.append(res)
    return results


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def format_table(results: Sequence[ArtifactResult]) -> str:
    """Raw check x artifact table (the primary deliverable of this slice)."""
    labels = [r.label or os.path.basename(r.path) for r in results]
    name_w = max([len("artifact")] + [len(x) for x in labels])
    header = (
        "artifact".ljust(name_w)
        + "  | "
        + " | ".join(c.ljust(11) for c in CHECKS)
        + " | runtime_s"
    )
    sep = "-" * len(header)
    lines = [header, sep]
    for r, label in zip(results, labels):
        cells = []
        for c in CHECKS:
            cell = r.cells.get(c)
            if cell is None:
                cells.append("missing".ljust(11))
            elif cell.status == "error":
                cells.append("ERROR".ljust(11))
            elif cell.status == "warn":
                cells.append("warn".ljust(11))
            else:
                cells.append("ok".ljust(11))
        lines.append(
            label.ljust(name_w)
            + "  | "
            + " | ".join(cells)
            + f" | {r.seconds:.3f}"
        )
    return "\n".join(lines)


def print_report(results: Sequence[ArtifactResult], show_measurements: bool) -> None:
    for r in results:
        for f in r.findings:
            print(f"{r.path}: {f.line()}")
    print("")
    print(format_table(results))
    if show_measurements:
        print("")
        print("measurements:")
        for r in results:
            label = r.label or os.path.basename(r.path)
            for c in CHECKS:
                cell = r.cells.get(c)
                if cell is None:
                    continue
                print(f"  {label:44s} {c:11s} "
                      f"{cell.status:5s} {cell.measurement}")
    n_err = sum(1 for r in results if r.error)
    n_warn = sum(1 for r in results
                 if not r.error and r.status() == "warn")
    print("")
    print(f"artifacts={len(results)} errors={n_err} warned_artifacts={n_warn}")
    if results:
        avg = sum(r.seconds for r in results) / len(results)
        slowest = max(results, key=lambda r: r.seconds)
        print(f"runtime_avg_s={avg:.3f} runtime_max_s={slowest.seconds:.3f} "
              f"(slowest={os.path.basename(slowest.path)})")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Universal pixel floor for gameplay/store screenshots "
                    "(report-only; exit 1 on any error finding).")
    ap.add_argument("paths", nargs="+", help="image files or directories")
    ap.add_argument("--manifest", default=None,
                    help="JSON manifest with declared expected dimensions")
    ap.add_argument("--root", default=None,
                    help="root used for manifest keys and grouping "
                         "(default: the scanned directory)")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of text")
    ap.add_argument("--measurements", action="store_true",
                    help="also print the per-check measurement table")
    args = ap.parse_args(argv)

    root = args.root
    if root is None:
        dirs = [p for p in args.paths if os.path.isdir(p)]
        root = dirs[0] if len(dirs) == 1 else None

    manifest_path = args.manifest
    if manifest_path is None and root and os.path.isdir(root):
        # A corpus directory ships its own manifest.json (declaring the
        # expected store dimensions per artifact); use it automatically.
        candidate = os.path.join(root, "manifest.json")
        if os.path.isfile(candidate):
            manifest_path = candidate
    manifest = load_manifest(manifest_path)
    results = analyze(args.paths, manifest, root)

    if args.json:
        payload = {
            "artifacts": [
                {
                    "path": r.path,
                    "group": r.group,
                    "status": r.status(),
                    "seconds": round(r.seconds, 4),
                    "checks": {
                        c: {
                            "status": r.cells[c].status,
                            "measurement": r.cells[c].measurement,
                        }
                        for c in CHECKS
                        if c in r.cells
                    },
                    "findings": [
                        {"level": f.level, "check": f.check,
                         "measurement": f.measurement, "hint": f.hint}
                        for f in r.findings
                    ],
                }
                for r in results
            ],
            "errors": sum(1 for r in results if r.error),
        }
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_report(results, args.measurements)

    return 1 if any(r.error for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())

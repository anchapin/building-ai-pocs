#!/usr/bin/env python3
"""Headline runner for the drawing-verifier symbolic checker (SLICE 1 + 2).

One command reproduces the headline table:

    python3 drawing-verifier/run_headline.py

It runs the checker over every clean fixture and every injected-error variant
and prints:

  * the per-error-class catch table (how many injected errors of each class
    were caught),
  * the false-flag count on the clean fixtures,
  * the geometry error (floor area / WWR) of each clean fixture against its
    hand-built reference model.

No network access, no VLM, no absolute paths: everything is resolved relative
to this file.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import checker  # noqa: E402  (local module, path set above)

FIXTURE_DIR = os.path.join(HERE, "fixtures")
INJECTED_DIR = os.path.join(FIXTURE_DIR, "injected")
CASES_FILE = os.path.join(INJECTED_DIR, "cases.json")


def clean_fixtures() -> List[str]:
    """Clean fixture model files (reference models are excluded)."""
    names = [
        n
        for n in sorted(os.listdir(FIXTURE_DIR))
        if n.endswith(".json") and not n.endswith(".reference.json")
    ]
    return [os.path.join(FIXTURE_DIR, n) for n in names]


def relative(path: str) -> str:
    return os.path.relpath(path, HERE)


def load(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def geometry_errors(model_path: str) -> List[Tuple[str, str, float, float, float, float]]:
    """Compare computed geometry with the hand-built reference model.

    Returns rows of (element, kind, computed, reference, abs_error, pct_error).
    """
    reference_path = model_path[: -len(".json")] + ".reference.json"
    if not os.path.exists(reference_path):
        return []
    reference = load(reference_path)
    metrics = checker.compute_metrics(load(model_path))
    rows: List[Tuple[str, str, float, float, float, float]] = []

    for zid, ref in reference.get("zones", {}).items():
        computed = metrics["zones"].get(zid)
        if not computed:
            continue
        ref_area = float(ref["floor_area_m2"])
        pct_area = abs(computed["floor_area_m2"] - ref_area) / ref_area * 100.0
        rows.append(
            (zid, "floor_area_m2", computed["floor_area_m2"], ref_area,
             abs(computed["floor_area_m2"] - ref_area), pct_area)
        )
        ref_wwr = float(ref["wwr"])
        pct_wwr = abs(computed["wwr"] - ref_wwr) / ref_wwr * 100.0
        rows.append((zid, "wwr", computed["wwr"], ref_wwr, abs(computed["wwr"] - ref_wwr), pct_wwr))

    for wid, ref in reference.get("walls", {}).items():
        computed = metrics["walls"].get(wid)
        if not computed:
            continue
        ref_wwr = float(ref["wwr"])
        pct_wwr = abs(computed["wwr"] - ref_wwr) / ref_wwr * 100.0
        rows.append((wid, "wall_wwr", computed["wwr"], ref_wwr, abs(computed["wwr"] - ref_wwr), pct_wwr))

    return rows


def main() -> int:
    print("drawing-verifier headline -- SLICE 1 + 2 (symbolic checker only)")
    print("=" * 78)
    print()

    # ---------------------------------------------------------------- clean
    print("1. Clean fixtures (false-flag measurement)")
    print("-" * 78)
    print(f"{'fixture':<34}{'findings':>10}{'classes':>34}")
    clean_total = 0
    clean_flagged = 0
    clean_findings = 0
    for path in clean_fixtures():
        report = checker.check_model(load(path))
        classes = ", ".join(report["error_classes"]) or "-"
        print(f"{relative(path):<34}{report['n_findings']:>10}{classes:>34}")
        clean_total += 1
        clean_findings += report["n_findings"]
        if report["n_findings"]:
            clean_flagged += 1
    false_flag_rate = (clean_flagged / clean_total * 100.0) if clean_total else 0.0
    print()
    print(f"clean fixtures: {clean_total}   flagged: {clean_flagged}   "
          f"total findings: {clean_findings}   false-flag rate: {false_flag_rate:.1f}% "
          "(share of clean fixtures producing >=1 finding)")
    print()

    # ------------------------------------------------------------- injected
    print("2. Injected-error set (catch measurement)")
    print("-" * 78)
    cases = load(CASES_FILE)["cases"]
    by_class: Dict[str, List[bool]] = {}
    caught = 0
    for case in cases:
        path = os.path.join(INJECTED_DIR, case["variant"])
        report = checker.check_model(load(path))
        found = set(report["error_classes"])
        expected = set(case["expected_classes"])
        hit = expected.issubset(found)
        caught += 1 if hit else 0
        for cls in sorted(expected):
            by_class.setdefault(cls, []).append(hit)
        status = "CAUGHT " if hit else "MISSED "
        detail = ",".join(sorted(found)) or "-"
        print(f"{status}{case['variant']:<46}{case['injected_error'][:52]:<54}{detail}")
    catch_rate = caught / len(cases) * 100.0 if cases else 0.0
    print()
    print(f"{'error class':<32}{'injected':>10}{'caught':>8}{'catch rate':>13}")
    for cls in sorted(by_class):
        results = by_class[cls]
        print(f"{cls:<32}{len(results):>10}{sum(results):>8}{sum(results) / len(results) * 100.0:>12.0f}%")
    print()
    print(f"injected errors: {len(cases)}   caught: {caught}   catch rate: {catch_rate:.1f}%")
    print()

    # -------------------------------------------------------------- geometry
    print("3. Geometry error vs hand-built reference model")
    print("-" * 78)
    print(f"{'fixture':<22}{'element':<14}{'quantity':<16}{'computed':>11}{'reference':>11}{'abs err':>10}{'err %':>9}")
    worst_pct = 0.0
    for path in clean_fixtures():
        for element, kind, computed, reference, abs_err, pct in geometry_errors(path):
            worst_pct = max(worst_pct, pct)
            print(
                f"{relative(path).split(os.sep)[-1][:21]:<22}{element:<14}{kind:<16}"
                f"{computed:>11.4f}{reference:>11.4f}{abs_err:>10.4f}{pct:>8.2f}%"
            )
    print()
    print(f"worst geometry error on the clean fixtures: {worst_pct:.2f}% (threshold 5%)")
    print()

    # ---------------------------------------------------------- second reader
    print("4. Second reader")
    print("-" * 78)
    stub = checker.NoVLMSecondReader()
    result = stub.review({}, None)
    print(f"reader: {result.reader_id} -> agree={result.agree} ({result.reason})")
    print("no VLM is configured; second-reader agreement is NOT measured and never")
    print("contributes to pass/fail in this slice.")
    print()

    print("=" * 78)
    print(f"HEADLINE  catch rate {catch_rate:.1f}% ({caught}/{len(cases)})   "
          f"false-flag rate {false_flag_rate:.1f}% ({clean_flagged}/{clean_total})   "
          f"worst geometry error {worst_pct:.2f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())

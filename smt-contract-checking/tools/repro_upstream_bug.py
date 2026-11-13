#!/usr/bin/env python3
"""Reproduce the slice's counterexample inside the *upstream* pipeline.

This script does not modify anything in ``drawing-verifier/``: it imports
``drawing-verifier/checker.py`` read-only and runs its
``check_wall_adjacency`` over a model whose second opening is *contained* in
the span of the first one.  It shows that the defect the contracts expose is
reachable in the upstream POC (not merely a contract-authoring artefact).

Usage::

    python3 smt-contract-checking/tools/repro_upstream_bug.py
"""

from __future__ import annotations

import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POC_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(POC_DIR)
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)


def _load_upstream_checker():
    path = os.path.join(REPO_ROOT, "drawing-verifier", "checker.py")
    spec = importlib.util.spec_from_file_location("drawing_verifier_checker", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need the module registered
    spec.loader.exec_module(module)
    return module


def main() -> int:
    checker = _load_upstream_checker()

    # A 10 m wall carrying a 10 m opening (A) and a 0.02 m opening (B)
    # whose span lies inside A's span.  Both openings are schema-valid.
    model = {
        "schema_version": 1,
        "walls": [
            {
                "id": "w1",
                "start": [0.0, 0.0],
                "end": [10.0, 0.0],
                "thickness": 0.2,
                "height": 3.0,
            }
        ],
        "openings": [
            {
                "id": "A",
                "kind": "window",
                "host_wall": "w1",
                "center_offset": 5.0,
                "width": 10.0,
                "sill_height": 0.9,
                "head_height": 2.1,
            },
            {
                "id": "B",
                "kind": "window",
                "host_wall": "w1",
                "center_offset": 0.05,
                "width": 0.02,
                "sill_height": 0.9,
                "head_height": 2.1,
            },
        ],
        "zones": [],
        "schedules": [],
    }

    schema_findings = checker.validate_model(model)
    print(f"schema findings : {[f.error_class for f in schema_findings]}")

    findings = checker.check_wall_adjacency(model)
    print(f"adjacency findings: {len(findings)}")
    for finding in findings:
        print(f"  [{finding.severity}] {finding.error_class}: {finding.reason}")

    lo1, hi1 = 0.0, 10.0
    lo2, hi2 = 0.04, 0.06
    true_overlap = min(hi1, hi2) - max(lo1, lo2)
    print(f"true geometric overlap : {true_overlap:.3f} m")
    print(f"tolerance              : {checker.TOLERANCE_M:.3f} m")
    print(
        "verdict                : "
        + (
            "the upstream finding is a FALSE POSITIVE (true overlap is not "
            "above the tolerance) and its magnitude is wrong"
            if true_overlap <= checker.TOLERANCE_M
            else "the upstream finding is genuine"
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

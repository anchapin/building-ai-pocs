#!/usr/bin/env python3
"""Bounded offline search over the slice's contract space.

**This is not crosshair.**  The sandbox for this slice has no PyPI access
(``pip install crosshair`` fails with an SSL error to ``pypi.org``; see
REPORT.md, section "Environment"), so neither crosshair nor its z3 backend
could be installed.  This tool is the *fallback* evidence: it enumerates a
bounded, discrete input domain (a 50 mm grid over 0.00-1.00 m), evaluates
the contracts of every function in the slice on every point of that domain,
and reports the inputs on which a contract is violated.

It is deliberately weaker than a symbolic executor: it is exhaustive over a
finite grid, not over the reals, and it says so.  What it *can* do -- and
what crosshair would do -- is separate "the contract is wrong" from "the
code is wrong", because the classification rule is written down:

* a counterexample on an input that upstream's own schema validation
  (``drawing-verifier/checker.py::validate_model``) rejects before the
  geometry checks run is a **contract error** -- the contract as authored
  is missing a precondition that upstream enforces elsewhere;
* every other counterexample is a **real bug** in the upstream code, because
  the input is reachable in the upstream pipeline.

Usage::

    python3 smt-contract-checking/tools/contract_search.py
    python3 smt-contract-checking/tools/contract_search.py --json
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from typing import Any, Callable, Dict, Iterable, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
POC_DIR = os.path.dirname(HERE)
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)

from contracts import evaluate_contracts  # noqa: E402  (path set up above)
import geometry_slice as G  # noqa: E402  (path set up above)

#: The search grid: millimetres, 0 .. 1000 mm in 50 mm steps.
GRID_MM = list(range(0, 1001, 50))
GRID_M = [mm / 1000.0 for mm in GRID_MM]


def _rectangles() -> Iterable[Tuple[Any, ...]]:
    """Axis-aligned rectangles and degenerate polygons for ``polygon_area``."""
    corners = [0.0, 0.25, 0.5, 0.75, 1.0]
    for x1 in corners:
        for x2 in corners:
            for y1 in corners:
                for y2 in corners:
                    yield ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
    # a collapsed (zero-area) polygon and a collinear triple
    yield ((0.0, 0.0), (0.5, 0.0), (1.0, 0.0))
    yield ((0.0, 0.0), (0.0, 0.0), (0.0, 0.0))
    # a self-intersecting ("bow-tie") loop: shoelace gives the *difference*
    # of the two lobes, which is not a floor area
    yield ((0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (0.6, 1.0))


#: name -> (function, argument generator)
SEARCH_SPACE: Dict[str, Tuple[Callable[..., Any], Callable[[], Iterable[Dict[str, Any]]]]] = {
    "dist": (
        G.dist,
        lambda: (
            {"ax": a, "ay": b, "bx": c, "by": d}
            for a, b, c, d in itertools.product(GRID_M, GRID_M, GRID_M, GRID_M)
        ),
    ),
    "polygon_area": (G.polygon_area, lambda: ({"points": p} for p in _rectangles())),
    "glazed_area": (
        G.glazed_area,
        lambda: (
            {"width": w, "sill_height": s, "head_height": h}
            for w, s, h in itertools.product(GRID_M, GRID_M, GRID_M)
        ),
    ),
    "opening_span": (
        G.opening_span,
        lambda: (
            {"center_offset": c, "width": w}
            for c, w in itertools.product(GRID_M, GRID_M)
        ),
    ),
    "overlap_flag": (
        G.overlap_flag,
        lambda: (
            {"lo1": a, "hi1": b, "lo2": c, "hi2": d}
            for a, b, c, d in itertools.product(GRID_M, GRID_M, GRID_M, GRID_M)
        ),
    ),
    "overlap_length": (
        G.overlap_length,
        lambda: (
            {"lo1": a, "hi1": b, "lo2": c, "hi2": d}
            for a, b, c, d in itertools.product(GRID_M, GRID_M, GRID_M, GRID_M)
        ),
    ),
    "true_overlap": (
        G.true_overlap,
        lambda: (
            {"lo1": a, "hi1": b, "lo2": c, "hi2": d}
            for a, b, c, d in itertools.product(GRID_M, GRID_M, GRID_M, GRID_M)
        ),
    ),
    "wwr": (
        G.wwr,
        lambda: (
            {"glazed": g, "gross": r}
            for g, r in itertools.product(GRID_M, GRID_M)
        ),
    ),
}

#: Preconditions that upstream's schema validation enforces *before* the
#: geometry checks run (``drawing-verifier/checker.py::validate_model``).
#: A counterexample that needs one of them to be violated is a contract
#: error (the contract is missing a precondition upstream enforces
#: elsewhere), not a live upstream bug.
UPSTREAM_GUARDS: Dict[str, Tuple[str, Callable[[Dict[str, Any]], bool]]] = {
    "glazed_area": (
        "validate_model rejects an opening whose head_height <= sill_height",
        lambda kw: kw["head_height"] > kw["sill_height"],
    ),
    "opening_span": (
        "validate_model rejects an opening whose width <= 0",
        lambda kw: kw["width"] > 0.0,
    ),
    "overlap_flag": (
        "validate_model rejects an opening whose width <= 0",
        lambda kw: (kw["hi1"] - kw["lo1"]) > 0.0 and (kw["hi2"] - kw["lo2"]) > 0.0,
    ),
    "overlap_length": (
        "validate_model rejects an opening whose width <= 0",
        lambda kw: (kw["hi1"] - kw["lo1"]) > 0.0 and (kw["hi2"] - kw["lo2"]) > 0.0,
    ),
}


def classify(name: str, kwargs: Dict[str, Any]) -> Tuple[str, str]:
    """Classify a counterexample as a real bug or as a contract error."""
    guard = UPSTREAM_GUARDS.get(name)
    if guard is None:
        return (
            "real bug",
            "the input is reachable in the upstream pipeline "
            "(drawing-verifier/checker.py::check_wall_adjacency)",
        )
    reason, predicate = guard
    if not predicate(kwargs):
        return (
            "contract error",
            f"the input is rejected upstream before the geometry checks run: {reason}",
        )
    return (
        "real bug",
        "the input is reachable in the upstream pipeline",
    )


def search(name: str) -> Dict[str, Any]:
    fn, generator = SEARCH_SPACE[name]
    started = time.time()
    tried = 0
    in_domain = 0
    violations = 0
    by_class: Dict[str, int] = {"real bug": 0, "contract error": 0}
    counterexamples: List[Dict[str, Any]] = []
    for kwargs in generator():
        tried += 1
        outcome = evaluate_contracts(fn, kwargs)
        if not outcome["pre_ok"]:
            continue  # outside the contract's domain: not a counterexample
        in_domain += 1
        if outcome["post_ok"]:
            continue
        violations += 1
        kind, reason = classify(name, kwargs)
        by_class[kind] += 1
        entry = {
            "inputs": kwargs,
            "value": outcome["result"],
            "violated": [
                {"kind": k, "predicate": str(p)} for k, p in outcome["violated"]
            ],
            "classification": kind,
            "reason": reason,
        }
        if len(counterexamples) < 5:
            counterexamples.append(entry)
    return {
        "function": name,
        "inputs_tried": tried,
        "inputs_in_contract_domain": in_domain,
        "violating_inputs": violations,
        "by_classification": by_class,
        "counterexamples": counterexamples,
        "wall_seconds": round(time.time() - started, 3),
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        help="restrict the search to the named function (repeatable)",
    )
    args = parser.parse_args(argv)

    names = args.only if args.only else list(SEARCH_SPACE)
    started = time.time()
    results = [search(name) for name in names]
    total = round(time.time() - started, 3)

    if args.json:
        print(json.dumps({"results": results, "wall_seconds": total}, indent=2, default=str))
        return 0

    print("contract search (offline bounded grid; NOT crosshair)")
    print(f"grid: {len(GRID_M)} points, 0.000-1.000 m, 50 mm step")
    print()
    for res in results:
        print(f"--- {res['function']}")
        print(f"    inputs tried        : {res['inputs_tried']}")
        print(f"    inside contract dom.: {res['inputs_in_contract_domain']}")
        print(
            f"    violating inputs    : {res['violating_inputs']} "
            f"(real bug: {res['by_classification']['real bug']}, "
            f"contract error: {res['by_classification']['contract error']})"
        )
        for ce in res["counterexamples"]:
            print(
                f"      inputs={ce['inputs']} value={ce['value']} "
                f"-> {ce['classification']}: {ce['reason']}"
            )
        print(f"    wall seconds        : {res['wall_seconds']}")
        print()
    print(f"total wall seconds: {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

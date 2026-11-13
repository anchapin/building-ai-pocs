"""Run-output loading and field-manifest construction.

A *run output* here is a JSON document shaped after the Fluxion
``results.json`` premise of issue #37 (run id, status, solver block, inputs,
provenance, log lines, and a table of result *fields*).  This slice only ever
reads the in-folder fixtures.

The *field manifest* is the assembler's whole view of a run:

    name, unit, kind, and (optionally) the run's own declared reference band.

It deliberately carries **no series values** - the assembler cannot see the
data, so it cannot perform the diagnosis itself; it can only select a view.
``tests/test_manifest.py`` enforces that mechanically.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RUN_DIR = os.path.join(FIXTURE_DIR, "runs")
GROUND_TRUTH_DIR = os.path.join(FIXTURE_DIR, "ground_truth")

#: manifest entry keys - values are never among them
MANIFEST_KEYS = ("name", "unit", "kind", "reference_range")


class FixtureError(RuntimeError):
    """Raised when a fixture is missing or malformed."""


def load_run(run_id: str, run_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load one run-output fixture by id (or by path)."""
    if run_id.endswith(".json") and os.path.exists(run_id):
        path = run_id
    else:
        base = run_dir or RUN_DIR
        path = os.path.join(base, "%s.json" % run_id)
    if not os.path.exists(path):
        raise FixtureError("no such run fixture: %s" % path)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def list_runs(run_dir: Optional[str] = None) -> List[str]:
    """Run ids present in the fixture directory, sorted."""
    base = run_dir or RUN_DIR
    if not os.path.isdir(base):
        return []
    return sorted(
        os.path.splitext(name)[0]
        for name in os.listdir(base)
        if name.endswith(".json")
    )


def manifest_from_run(run: Dict[str, Any]) -> Dict[str, Any]:
    """Build the field manifest (names + units, never values) for a run.

    The manifest is the *only* thing the assembler is given.  Reference bands
    are metadata the run itself declares (they are not data), and are carried
    along so that ``DiffTable`` can flag out-of-range rows; they are never
    derived from the series values.
    """
    if not isinstance(run, dict):
        raise FixtureError("run output must be a JSON object")
    if "run_id" not in run:
        raise FixtureError("run output has no run_id")
    fields = run.get("fields") or {}
    if not isinstance(fields, dict):
        raise FixtureError("run output 'fields' must be an object")
    entries = []
    for name in sorted(fields):
        field = fields[name] or {}
        unit = field.get("unit")
        kind = field.get("kind", "series")
        reference = field.get("reference_range")
        entry = {
            "name": name,
            "unit": unit,
            "kind": kind,
            "reference_range": dict(reference) if isinstance(reference, dict) else None,
        }
        entries.append(entry)
    return {
        "run_id": run["run_id"],
        "run_name": run.get("run_name", run["run_id"]),
        "status": run.get("status", "unknown"),
        "entries": entries,
    }


def manifest_field_names(manifest: Dict[str, Any]) -> List[str]:
    return [entry["name"] for entry in manifest["entries"]]


def find_entry(manifest: Dict[str, Any], name: str) -> Optional[Dict[str, Any]]:
    for entry in manifest["entries"]:
        if entry["name"] == name:
            return entry
    return None


def load_ground_truth(case_id: str, gt_dir: Optional[str] = None) -> Dict[str, Any]:
    """Load the frozen ground-truth diagnosis for a case."""
    base = gt_dir or GROUND_TRUTH_DIR
    path = os.path.join(base, "%s.ground_truth.json" % case_id)
    if not os.path.exists(path):
        raise FixtureError("no ground truth for case: %s" % case_id)
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)

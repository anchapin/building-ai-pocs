"""Run-output loading and field-manifest construction.

A *run output* here is a JSON document shaped after the Fluxion
``results.json`` premise of issue #37 (run id, status, solver block, inputs,
provenance, log lines, and a table of result *fields*).

Slice 1 only ever read the in-folder fixtures.  Slice 2 (step 0) adds the
*real* Fluxion run output: the versioned standard results report
(``schemas/results_v1.schema.json``) that the engine emits for a completed
run.  Its shape is not the issue's premise shape, so it gets its own
loader and its own field-mapping table below - the manifest itself is
built exactly the same way (names + units, never values).

The *field manifest* is the assembler's whole view of a run:

    name, unit, kind, and (optionally) the run's own declared reference band.

It deliberately carries **no series values** - the assembler cannot see the
data, so it cannot perform the diagnosis itself; it can only select a view.
``tests/test_manifest.py`` enforces that mechanically.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Sequence

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
RUN_DIR = os.path.join(FIXTURE_DIR, "runs")
GROUND_TRUTH_DIR = os.path.join(FIXTURE_DIR, "ground_truth")

#: the real Fluxion run output used by slice 2 (step 0).  This is a *copy* of
#: a completed Fluxion run, byte for byte; see ``real_runs/PROVENANCE.md``.
REAL_RUN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "real_runs")
REAL_REPORT_FILE = "fluxion_standard_report.json"

#: the run id the lens uses for the real output.  It starts with ``run_`` on
#: purpose: that is the prefix the assembler recognises as a run id, so a
#: request naming *another* run is refused against the real output too.
REAL_RUN_ID = "run_fluxion_standard_report"

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


# --------------------------------------------------------------------------
# the real Fluxion run output (slice 2, step 0)
# --------------------------------------------------------------------------

#: The Fluxion standard results report (results_v1) -> the lens' field
#: names.  Every row is ``(lens name, unit, kind, path in the report)``:
#: the lens names a field the *report* carries, it never invents one, and
#: the unit is the unit the report's own schema declares for that path.
#:
#: ``("monthly", "*", ...)`` means "the same leaf under every month".
#:
#: The hourly end-use series is *not* embedded in the report (it is
#: referenced by its sha256 checksum), so the hourly rows carry no values
#: and the renderer shows "no data" for them - the lens never invents a
#: series it was not given.
STANDARD_REPORT_FIELDS = (
    ("heating_energy", "kWh", "scalar", ("annual", "end_use_kwh", "heating")),
    ("cooling_energy", "kWh", "scalar", ("annual", "end_use_kwh", "cooling")),
    ("lighting_energy", "kWh", "scalar", ("annual", "end_use_kwh", "lighting")),
    ("equipment_energy", "kWh", "scalar", ("annual", "end_use_kwh", "equipment")),
    ("total_energy", "kWh", "scalar", ("annual", "total_energy_kwh")),
    ("peak_heating", "kW", "scalar", ("annual", "peaks", "heating")),
    ("peak_cooling", "kW", "scalar", ("annual", "peaks", "cooling")),
    ("peak_lighting", "kW", "scalar", ("annual", "peaks", "lighting")),
    ("peak_equipment", "kW", "scalar", ("annual", "peaks", "equipment")),
    ("floor_area", "m2", "scalar", ("annual", "floor_area_m2")),
    ("zone_count", "1", "scalar", ("annual", "zone_count")),
    ("monthly_heating_energy", "kWh", "series", ("monthly", "*", "end_use_kwh", "heating")),
    ("monthly_cooling_energy", "kWh", "series", ("monthly", "*", "end_use_kwh", "cooling")),
    ("monthly_lighting_energy", "kWh", "series", ("monthly", "*", "end_use_kwh", "lighting")),
    ("monthly_equipment_energy", "kWh", "series", ("monthly", "*", "end_use_kwh", "equipment")),
    ("monthly_peak_heating", "kW", "series", ("monthly", "*", "end_use_peak_kw", "heating")),
    ("monthly_peak_cooling", "kW", "series", ("monthly", "*", "end_use_peak_kw", "cooling")),
    ("unmet_heating_hours", "h", "scalar", ("unmet_hours", "all_hours", "heating")),
    ("unmet_cooling_hours", "h", "scalar", ("unmet_hours", "all_hours", "cooling")),
    ("occupied_unmet_heating_hours", "h", "scalar", ("unmet_hours", "occupied", "heating")),
    ("occupied_unmet_cooling_hours", "h", "scalar", ("unmet_hours", "occupied", "cooling")),
    ("setpoint_tolerance", "°C", "scalar", ("unmet_hours", "tolerance_c")),
    ("hourly_heating_energy", "kWh", "series", ("hourly", "columns", "heating_kwh")),
    ("hourly_cooling_energy", "kWh", "series", ("hourly", "columns", "cooling_kwh")),
    ("hourly_lighting_energy", "kWh", "series", ("hourly", "columns", "lighting_kwh")),
    ("hourly_equipment_energy", "kWh", "series", ("hourly", "columns", "equipment_kwh")),
)


def load_standard_report(path: Optional[str] = None) -> Dict[str, Any]:
    """Load the real Fluxion standard results report (a completed run)."""
    target = path or os.path.join(REAL_RUN_DIR, REAL_REPORT_FILE)
    if not os.path.exists(target):
        raise FixtureError("no real run output: %s" % target)
    with open(target, "r", encoding="utf-8") as handle:
        report = json.load(handle)
    if not isinstance(report, dict):
        raise FixtureError("real run output must be a JSON object")
    for key in ("metadata", "annual", "hourly"):
        if key not in report:
            raise FixtureError("real run output has no %r block" % key)
    return report


def _report_leaf(report: Dict[str, Any], path: Sequence[Any]) -> Any:
    """The value at ``path`` in the report, or ``None`` when it is absent."""
    node: Any = report
    for step in path:
        if not isinstance(node, dict) or step not in node:
            return None
        node = node[step]
    return node


def _report_values(report: Dict[str, Any], path: Sequence[Any]) -> Optional[List[Any]]:
    """The values of a field of the report.

    A scalar path yields a one-element list; a ``"*"`` step collects the
    same leaf under every month.  ``None`` means the report does not carry
    the series (the hourly end-use series is referenced by checksum only).
    """
    if "*" in path:
        index = path.index("*")
        container = _report_leaf(report, path[:index])
        if not isinstance(container, list):
            return None
        values = []
        for item in container:
            leaf = _report_leaf(item, path[index + 1:])
            if leaf is None:
                return None
            values.append(leaf)
        return values
    leaf = _report_leaf(report, path)
    if leaf is None:
        return None
    if isinstance(leaf, list):
        return list(leaf)
    return [leaf]


def standard_report_to_run(report: Dict[str, Any]) -> Dict[str, Any]:
    """The real run output in the *run* shape the renderer reads.

    Same shape as the fixture runs (``run_id``, ``status``, ``fields`` with
    ``unit``/``kind``/``value``/``values``), so the renderer and the
    assembler need no special case.  Values come from the report and from
    nowhere else.
    """
    metadata = report.get("metadata") or {}
    fields: Dict[str, Any] = {}
    for name, unit, kind, path in STANDARD_REPORT_FIELDS:
        field: Dict[str, Any] = {"unit": unit, "kind": kind}
        values = _report_values(report, path)
        if values is not None:
            if kind == "series":
                field["values"] = values
            else:
                field["value"] = values[0]
        fields[name] = field
    return {
        "run_id": REAL_RUN_ID,
        "run_name": metadata.get("model_name", REAL_RUN_ID),
        "status": "ok",
        "provenance": {
            "source": "Fluxion standard results report (results_v1)",
            "schema_version": metadata.get("schema_version"),
            "tool_version": metadata.get("tool_version"),
            "model_source": metadata.get("model_source"),
            "step0_source": "real completed Fluxion run output (copy, see real_runs/PROVENANCE.md)",
        },
        "fields": fields,
    }


def report_field_values(report: Dict[str, Any], name: str) -> Optional[List[Any]]:
    """The values the real report carries for a lens field name.

    ``None`` when the report does not carry the series at all (the hourly
    end-use series is referenced by checksum only).  Used by the throwaway
    baseline of ``run_poc.py``, which reads the report directly.
    """
    for field_name, _unit, _kind, path in STANDARD_REPORT_FIELDS:
        if field_name == name:
            return _report_values(report, path)
    return None


def manifest_from_standard_report(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build the field manifest (names + units, never values) for the real run.

    Same contract as :func:`manifest_from_run`: the assembler sees the
    names, the units and the kinds only - never a series value.
    """
    metadata = report.get("metadata") or {}
    entries = []
    for name, unit, kind, _path in sorted(STANDARD_REPORT_FIELDS, key=lambda row: row[0]):
        entries.append(
            {
                "name": name,
                "unit": unit,
                "kind": kind,
                "reference_range": None,
            }
        )
    return {
        "run_id": REAL_RUN_ID,
        "run_name": metadata.get("model_name", REAL_RUN_ID),
        "status": "ok",
        "entries": entries,
    }

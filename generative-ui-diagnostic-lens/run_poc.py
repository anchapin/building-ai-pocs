#!/usr/bin/env python3
"""Run the Generative-UI diagnostic lens POC and print the headline table.

    python3 generative-ui-diagnostic-lens/run_poc.py

Everything is deterministic: no network, no model calls, no clock in the
output (except the timing comparison, which is a measurement).

The runner does four things:

1.  assembles the case requests and the adversarial requests,
2.  computes **binding validity mechanically** - every field binding of
    every generated spec is checked against the run's field manifest
    (the field exists, and its unit matches the unit the spec binds),
3.  checks, per case, whether the assembled lens contains the series the
    frozen ground truth depends on,
4.  compares the lens against a trivial throwaway-script baseline that
    produces the same view by reading the fixture JSON directly.
"""

from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import assembler  # noqa: E402
import catalog  # noqa: E402
import manifest as manifest_mod  # noqa: E402
import renderer  # noqa: E402
import uispec  # noqa: E402

sys.path.insert(0, os.path.join(HERE, "fixtures"))
import baseline_throwaway  # noqa: E402

CASE_REQUESTS = os.path.join(HERE, "fixtures", "case_requests.json")
ADVERSARIAL = os.path.join(HERE, "adversarial", "requests.json")
OUT_OF_CATALOG = os.path.join(HERE, "fixtures", "requests_out_of_catalog.json")

REPEATS = 50


# --------------------------------------------------------------------------
# loading
# --------------------------------------------------------------------------

def load_requests(path: str) -> list:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)["requests"]


def load_runs() -> dict:
    return {run_id: manifest_mod.load_run(run_id) for run_id in manifest_mod.list_runs()}


# --------------------------------------------------------------------------
# mechanical binding validity
# --------------------------------------------------------------------------

def check_bindings(spec: dict, manifest: dict) -> tuple:
    """Check every field binding of ``spec`` against ``manifest``.

    Returns ``(checked, valid, failures)``.  A binding is valid when the
    field exists in the manifest *and* the unit the spec binds is the unit
    the manifest declares for that field.
    """
    checked = 0
    valid = 0
    failures = []
    for index, component in enumerate(spec.get("components", [])):
        primitive = catalog.get_primitive(component.get("primitive"))
        if primitive is None:
            continue
        bindings = component.get("bindings") or {}
        bound_unit = bindings.get("unit")
        for name in sorted(bindings):
            if primitive.binding_kind(name) != "field":
                continue
            value = bindings[name]
            checked += 1
            entry = manifest_mod.find_entry(manifest, value)
            if entry is None:
                failures.append(
                    "component %d (%s): field %r is not in manifest %s"
                    % (index, component.get("primitive"), value, manifest.get("run_id"))
                )
                continue
            if bound_unit is not None:
                declared = catalog.normalize_unit(entry.get("unit"))
                asked = catalog.normalize_unit(bound_unit)
                if declared != asked:
                    failures.append(
                        "component %d (%s): field %r is %s, spec binds %s"
                        % (index, component.get("primitive"), value, declared, asked)
                    )
                    continue
            valid += 1
    return checked, valid, failures


# --------------------------------------------------------------------------
# the trivial throwaway-script baseline
# --------------------------------------------------------------------------

def baseline_view(run_path: str, field_names) -> list:
    """The throwaway script's view of the same information (see
    ``fixtures/baseline_throwaway.py``)."""
    return baseline_throwaway.view(run_path, field_names)


def lens_view(spec: dict, run: dict) -> list:
    """The lens' view of the same information."""
    html = renderer.render_spec(spec, run)
    lines = []
    for component in spec.get("components", []):
        bindings = component.get("bindings") or {}
        name = bindings.get("series") or bindings.get("field") or bindings.get("log_field")
        if not name:
            continue
        field = (run.get("fields") or {}).get(name) or {}
        values = field.get("values")
        unit = field.get("unit")
        value = values[-1] if values else field.get("value")
        lines.append("%s = %s %s" % (name, value, unit if unit else ""))
    return lines


def count_lines(*paths: str) -> int:
    total = 0
    for path in paths:
        with open(path, "r", encoding="utf-8") as handle:
            total += sum(1 for line in handle if line.strip())
    return total


# --------------------------------------------------------------------------
# the headline table
# --------------------------------------------------------------------------

def main() -> int:
    runs = load_runs()
    manifests = {run_id: manifest_mod.manifest_from_run(run) for run_id, run in runs.items()}

    case_requests = load_requests(CASE_REQUESTS)
    adversarial = load_requests(ADVERSARIAL)
    out_of_catalog = load_requests(OUT_OF_CATALOG)

    results = {}          # request id -> result
    binding_checked = 0
    binding_valid = 0
    binding_failures = []
    handling_failures = []

    print("=" * 78)
    print("Generative-UI diagnostic lens - POC slice 0 (read-only, deterministic)")
    print("=" * 78)

    # ---- case requests -------------------------------------------------
    print("\n[1] case requests (assembled against the run's field manifest)")
    case_rows = []
    for request in case_requests:
        run_id = request["run_id"]
        run = runs[run_id]
        manifest = manifests[run_id]
        result = assembler.assemble(request["request"], manifest)
        results[request["id"]] = result
        if result.get("status") == "refused":
            print("   %-24s REFUSED (%s)" % (request["id"], result["reason_code"]))
            binding_failures.append("%s: refused, no spec" % request["id"])
            continue
        checked, valid, failures = check_bindings(result, manifest)
        binding_checked += checked
        binding_valid += valid
        binding_failures.extend("%s: %s" % (request["id"], f) for f in failures)
        errors = uispec.validate_spec(result, manifest)
        if errors:
            binding_failures.append("%s: spec invalid %s" % (request["id"], errors))
        primitives = ",".join(c["primitive"] for c in result["components"])
        print(
            "   %-24s spec ok, %d component(s) [%s], bindings %d/%d"
            % (request["id"], len(result["components"]), primitives, valid, checked)
        )
        case_rows.append((request["id"], request["run_id"], len(result["components"])))

    # ---- adversarial ---------------------------------------------------
    print("\n[2] adversarial request set (every one must be refused or no-data)")
    adversarial_rows = []
    adversarial_handled = 0
    for request in adversarial:
        run_id = request["run_id"]
        manifest = manifests[run_id]
        result = assembler.assemble(request["request"], manifest)
        results[request["id"]] = result
        refused = result.get("status") == "refused"
        code = result.get("reason_code", "")
        expected = request.get("expect_code")
        handled = refused and (expected is None or code == expected)
        if handled:
            adversarial_handled += 1
        else:
            handling_failures.append(
                "%s: not handled as expected (got %s)" % (request["id"], code or "spec")
            )
        if not refused:
            # a spec was produced: it must still be valid and bind only real fields
            checked, valid, failures = check_bindings(result, manifest)
            binding_checked += checked
            binding_valid += valid
            binding_failures.extend("%s: %s" % (request["id"], f) for f in failures)
            if failures or uispec.validate_spec(result, manifest):
                adversarial_handled -= 1
        adversarial_rows.append(
            (request["id"], request["category"], "refused:" + code if refused else "SPEC", handled)
        )
        print(
            "   %-34s %-16s -> %-28s %s"
            % (
                request["id"],
                request["category"],
                ("refused: " + code) if refused else "SPEC (no-data)",
                "ok" if handled else "NOT HANDLED",
            )
        )

    # ---- out-of-catalog ------------------------------------------------
    print("\n[3] requests attempted that the closed catalog cannot express")
    out_rows = []
    for request in out_of_catalog:
        run_id = request["run_id"]
        manifest = manifests[run_id]
        result = assembler.assemble(request["request"], manifest)
        results[request["id"]] = result
        refused = result.get("status") == "refused"
        code = result.get("reason_code", "")
        expected = request.get("expect_code")
        ok = refused and (expected is None or code == expected)
        if not ok:
            handling_failures.append(
                "%s: expected %s, got %s" % (request["id"], expected, code or "SPEC")
            )
        out_rows.append((request["id"], request["intent"], code if refused else "SPEC", ok))
        print(
            "   %-28s %-42s -> %-28s %s"
            % (request["id"], request["intent"], code if refused else "SPEC", "ok" if ok else "NOT HANDLED")
        )

    # ---- binding validity ---------------------------------------------
    print("\n[4] binding validity (mechanical: field exists in manifest + unit matches)")
    print("   bindings valid: %d/%d" % (binding_valid, binding_checked))
    if binding_failures:
        print("   FAILURES:")
        for failure in binding_failures:
            print("     - %s" % failure)
    else:
        print("   failures: none")

    # ---- per-case diagnosis support ------------------------------------
    print("\n[5] per-case diagnosis support (does the lens contain the ground truth's series?)")
    support_rows = []
    for request in case_requests:
        if not request.get("diagnosis_case"):
            continue
        case_id = request.get("case_id")
        if not case_id:
            continue
        try:
            truth = manifest_mod.load_ground_truth(case_id)
        except manifest_mod.FixtureError:
            continue
        result = results.get(request["id"], {})
        bound = set()
        for component in result.get("components", []):
            for key, value in (component.get("bindings") or {}).items():
                if key in ("series", "field", "reference_series"):
                    bound.add(value)
        missing = [f for f in truth["key_fields"] if f not in bound]
        support_rows.append((case_id, len(truth["key_fields"]), len(missing), missing))
        print(
            "   %-22s ground-truth series bound: %d/%d%s"
            % (
                case_id,
                len(truth["key_fields"]) - len(missing),
                len(truth["key_fields"]),
                ("  MISSING: %s" % ", ".join(missing)) if missing else "",
            )
        )

    # ---- catalog coverage ----------------------------------------------
    print("\n[6] catalog coverage (closed catalog: 6 primitives, no additions)")
    attempts = {name: 0 for name in catalog.PRIMITIVE_NAMES}
    expressed = {name: 0 for name in catalog.PRIMITIVE_NAMES}
    all_requests = case_requests + adversarial + out_of_catalog
    for request in all_requests:
        triggers = assembler.find_triggers(request["request"])
        for trigger in triggers:
            primitive = assembler.TRIGGER_TO_PRIMITIVE.get(trigger.primitive)
            if primitive in attempts:
                attempts[primitive] += 1
        result = results.get(request["id"], {})
        for component in result.get("components", []):
            name = component.get("primitive")
            if name in expressed:
                expressed[name] += 1
    for name in catalog.PRIMITIVE_NAMES:
        print(
            "   %-16s attempted %2d, expressed %2d%s"
            % (name, attempts[name], expressed[name], "   <-- never expressed" if not expressed[name] else "")
        )
    inexpressible = [
        "%s (%s) -> %s" % (row[0], row[1], row[2]) for row in out_rows
    ]
    print("   inexpressible list (deliverable):")
    for item in inexpressible:
        print("     - %s" % item)

    # ---- timing vs a throwaway baseline --------------------------------
    print("\n[7] timing vs a trivial throwaway-script baseline")
    timings = []
    for request in case_requests[:3]:
        run_id = request["run_id"]
        run = runs[run_id]
        run_path = os.path.join(HERE, "fixtures", "runs", "%s.json" % run_id)
        fields = []
        for component in results.get(request["id"], {}).get("components", []):
            bindings = component.get("bindings") or {}
            name = bindings.get("series") or bindings.get("field")
            if name:
                fields.append(name)

        start = time.perf_counter()
        for _ in range(REPEATS):
            baseline_view(run_path, fields)
        baseline_ms = (time.perf_counter() - start) * 1000.0 / REPEATS

        start = time.perf_counter()
        for _ in range(REPEATS):
            manifest = manifest_mod.manifest_from_run(run)
            spec = assembler.assemble(request["request"], manifest)
            uispec.validate_spec(spec, manifest)
            lens_view(spec, run)
        lens_ms = (time.perf_counter() - start) * 1000.0 / REPEATS

        timings.append(
            (request["id"], baseline_ms, lens_ms, len(baseline_view(run_path, fields)))
        )
    baseline_lines = count_lines(os.path.join(HERE, "fixtures", "baseline_throwaway.py"))
    lens_lines = count_lines(
        os.path.join(HERE, "assembler.py"),
        os.path.join(HERE, "uispec.py"),
        os.path.join(HERE, "catalog.py"),
        os.path.join(HERE, "renderer.py"),
    )
    print(
        "   throwaway baseline script: %d lines (fixtures/baseline_throwaway.py); "
        "lens path (assembler+uispec+catalog+renderer): %d lines" % (baseline_lines, lens_lines)
    )
    for case_id, baseline_ms, lens_ms, out_lines in timings:
        print(
            "   %-22s baseline %6.3f ms/view (%d output lines)   lens %6.3f ms/view   ratio %5.1fx"
            % (case_id, baseline_ms, out_lines, lens_ms, lens_ms / baseline_ms if baseline_ms else float("nan"))
        )

    # ---- headline table ------------------------------------------------
    print("\n" + "=" * 78)
    print("HEADLINE")
    print("=" * 78)
    print("| metric                                   | value                |")
    print("| ---------------------------------------- | -------------------- |")
    print(
        "| binding validity (field exists + unit)   | %d/%d%s |"
        % (
            binding_valid,
            binding_checked,
            "" if not binding_failures else "  (with failures listed above)",
        )
    )
    print(
        "| adversarial handled (refusal / no-data)  | %d/%d |"
        % (adversarial_handled, len(adversarial))
    )
    print(
        "| catalog coverage (primitives expressed)  | %d/%d |"
        % (sum(1 for n in catalog.PRIMITIVE_NAMES if expressed[n]), len(catalog.PRIMITIVE_NAMES))
    )
    print(
        "| per-case ground-truth series bound      | %d/%d cases |"
        % (
            sum(1 for row in support_rows if not row[3]),
            len(support_rows),
        )
    )
    print(
        "| out-of-catalog requests refused          | %d/%d |"
        % (sum(1 for row in out_rows if row[3]), len(out_rows))
    )
    print(
        "| lens path vs throwaway baseline          | %s |"
        % ", ".join("%s %.3f vs %.3f ms" % (row[0], row[2], row[1]) for row in timings)
    )
    print("=" * 78)
    if binding_failures:
        print("RESULT: binding failures present - see section 4")
        return 1
    if handling_failures:
        print("RESULT: handling failures present:")
        for failure in handling_failures:
            print("  - %s" % failure)
        return 1
    print("RESULT: every binding valid, every adversarial request handled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

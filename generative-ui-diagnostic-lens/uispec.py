"""The JSON UI-spec format, its validator, and the refusal object.

A *UI spec* is the lens' only output.  It is a small, closed JSON document:

```json
{
  "schema_version": 1,
  "run_id": "run_ashrae140_case1",
  "case_id": "case1_ashrae140",
  "request": "plot zone1 air temperature ...",
  "components": [
    {"primitive": "TimeSeriesChart",
     "title": "Zone 1 air temperature",
     "bindings": {"series": "zone1_air_temperature", "unit": "°C"},
     "props": {"x_axis_label": "sample"}}
  ]
}
```

The validator is deliberately hostile: it rejects unknown primitives, unknown
fields (at document, component, binding and prop level) and unit mismatches
between a binding and the run's field manifest.  It never repairs a spec.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import catalog
from manifest import find_entry

SCHEMA_VERSION = 1

TOP_LEVEL_KEYS = ("schema_version", "run_id", "case_id", "request", "components")
REQUIRED_TOP_LEVEL = ("run_id", "request", "components")
COMPONENT_KEYS = ("primitive", "title", "bindings", "props")


def _err(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out = {"code": code, "message": message}
    out.update(extra)
    return out


def make_refusal(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    """The explicit-refusal object returned instead of a spec."""
    out = {"status": "refused", "reason_code": code, "message": message}
    out.update(extra)
    return out


def is_refusal(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("status") == "refused"


def validate_spec(spec: Any, manifest: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Validate ``spec`` against the catalog and the run's field manifest.

    Returns a list of error dicts (empty == valid).  Errors are ordered
    deterministically: document-level errors first, then components in order.
    """
    errors: List[Dict[str, Any]] = []

    if not isinstance(spec, dict):
        return [_err("spec_not_object", "spec must be a JSON object")]

    for key in sorted(spec):
        if key not in TOP_LEVEL_KEYS:
            errors.append(_err("unknown_field", "unknown top-level field: %s" % key, path=key))
    for key in REQUIRED_TOP_LEVEL:
        if key not in spec:
            errors.append(_err("missing_field", "missing required field: %s" % key, path=key))
    if errors:
        return errors

    if spec["schema_version"] != SCHEMA_VERSION:
        errors.append(
            _err("bad_schema_version", "schema_version must be %d" % SCHEMA_VERSION)
        )

    manifest_run_id = manifest.get("run_id")
    if manifest_run_id and spec["run_id"] != manifest_run_id:
        errors.append(
            _err(
                "run_mismatch",
                "spec run_id %r does not match manifest run_id %r"
                % (spec["run_id"], manifest_run_id),
            )
        )

    if not isinstance(spec["request"], str):
        errors.append(_err("bad_type", "request must be a string", path="request"))

    components = spec["components"]
    if not isinstance(components, list):
        errors.append(_err("bad_type", "components must be a list", path="components"))
        return errors

    for index, component in enumerate(components):
        errors.extend(_validate_component(component, index, manifest))
    return errors


def _validate_component(
    component: Any, index: int, manifest: Dict[str, Any]
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    where = {"component_index": index}

    if not isinstance(component, dict):
        return [_err("bad_type", "component must be a JSON object", **where)]

    for key in sorted(component):
        if key not in COMPONENT_KEYS:
            errors.append(
                _err("unknown_field", "unknown component field: %s" % key, path=key, **where)
            )
    if "primitive" not in component:
        errors.append(_err("missing_field", "component has no primitive", **where))
        return errors

    name = component["primitive"]
    primitive = catalog.get_primitive(name)
    if primitive is None:
        errors.append(
            _err("unknown_primitive", "unknown primitive: %r" % (name,), path="primitive", **where)
        )
        return errors

    if "title" in component and not isinstance(component["title"], str):
        errors.append(_err("bad_type", "title must be a string", path="title", **where))

    bindings = component.get("bindings", {})
    if not isinstance(bindings, dict):
        errors.append(_err("bad_type", "bindings must be an object", path="bindings", **where))
        return errors

    props = component.get("props", {})
    if not isinstance(props, dict):
        errors.append(_err("bad_type", "props must be an object", path="props", **where))
        return errors

    for key in sorted(props):
        if key not in primitive.props:
            errors.append(
                _err("unknown_prop", "primitive %s has no prop %r" % (name, key), path=key, **where)
            )

    for key in sorted(bindings):
        if key not in primitive.allowed_bindings():
            errors.append(
                _err(
                    "unknown_binding_field",
                    "primitive %s has no binding %r" % (name, key),
                    path=key,
                    **where,
                )
            )

    for key in primitive.required_bindings:
        if key not in bindings:
            errors.append(
                _err(
                    "missing_binding",
                    "primitive %s requires binding %r" % (name, key),
                    path=key,
                    **where,
                )
            )

    # field bindings must exist in the manifest; unit bindings must match
    bound_field = None
    for key in sorted(bindings):
        value = bindings[key]
        kind = primitive.binding_kind(key)
        if kind is None:
            continue
        if kind == "field":
            entry = find_entry(manifest, value)
            if entry is None:
                errors.append(
                    _err(
                        "unknown_field",
                        "field %r is not in the run's field manifest" % (value,),
                        path=key,
                        **where,
                    )
                )
            elif key == "series" or key == "field":
                bound_field = entry
            elif key == "reference_series":
                if entry.get("unit") != bindings.get("unit") and "unit" in bindings:
                    errors.append(
                        _err(
                            "unit_mismatch",
                            "reference_series %r has unit %r, spec says %r"
                            % (value, entry.get("unit"), bindings.get("unit")),
                            path=key,
                            **where,
                        )
                    )
        elif kind == "unit":
            canonical = catalog.normalize_unit(value)
            if canonical is None:
                errors.append(
                    _err(
                        "unknown_unit",
                        "%r is not a unit the lens can check" % (value,),
                        path=key,
                        **where,
                    )
                )
            else:
                if not primitive.accepts_unit(canonical):
                    errors.append(
                        _err(
                            "unit_not_accepted",
                            "primitive %s does not accept unit %r" % (name, canonical),
                            path=key,
                            **where,
                        )
                    )
                if bound_field is not None and bound_field.get("unit"):
                    expected = catalog.normalize_unit(bound_field["unit"])
                    if expected != canonical:
                        errors.append(
                            _err(
                                "unit_mismatch",
                                "bound field %r has unit %r, spec says %r"
                                % (bound_field["name"], expected, canonical),
                                path=key,
                                **where,
                            )
                        )
        elif kind == "number":
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                errors.append(
                    _err("bad_type", "binding %r must be a number" % key, path=key, **where)
                )
        elif kind == "int":
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                errors.append(
                    _err(
                        "bad_type",
                        "binding %r must be a positive integer" % key,
                        path=key,
                        **where,
                    )
                )
        elif kind == "string":
            if not isinstance(value, str) or not value.strip():
                errors.append(
                    _err("bad_type", "binding %r must be a non-empty string" % key, path=key, **where)
                )

    if name == "DiffTable":
        has_min = "reference_min" in bindings
        has_max = "reference_max" in bindings
        if has_min != has_max:
            errors.append(
                _err(
                    "incomplete_reference",
                    "reference_min and reference_max must be given together",
                    path="reference_min",
                    **where,
                )
            )
        if has_min and has_max:
            try:
                if float(bindings["reference_min"]) > float(bindings["reference_max"]):
                    errors.append(
                        _err(
                            "bad_reference",
                            "reference_min must not exceed reference_max",
                            path="reference_min",
                            **where,
                        )
                    )
            except (TypeError, ValueError):
                pass

    return errors


def spec_is_valid(spec: Any, manifest: Dict[str, Any]) -> bool:
    return not validate_spec(spec, manifest)


def make_spec(
    run_id: str,
    request: str,
    components: List[Dict[str, Any]],
    case_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a spec document (assembler output shape)."""
    spec: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "request": request,
        "components": components,
    }
    if case_id is not None:
        spec["case_id"] = case_id
    return spec

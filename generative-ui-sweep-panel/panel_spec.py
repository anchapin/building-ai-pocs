"""Panel-spec validation: the Phase 1 UI-spec format, extended for panels.

The *document shape* is the Phase 1 one, unchanged: top-level keys
``schema_version``, ``run_id``, ``case_id``, ``request``, ``components``;
a component is ``{primitive, title, bindings, props}``.  The Phase 1 module
``uispec`` is imported and reused (not copied): the top-level key list, the
component key list, the spec constructor and the refusal object all come
from there.

What is new is the *binding* vocabulary of the five panel primitives
(``ParamSlider``, ``ParamNumber``, ``ChoiceSelect``, ``SweepAxis``,
``RunButton``).  Their bindings are checked against the frozen scoped set
in ``schema``:

* ``parameter`` must name a scoped parameter,
* ``unit`` must be that parameter's declared unit,
* ``min`` / ``max`` must be exactly the parameter's frozen range (the panel
  may not widen a frozen range),
* ``value`` must be a submission the strict layer accepts,
* the sweep axis must be a scoped, numeric parameter with a sane range,
* the run button's ``enabled`` flag must agree with the validity of the
  panel state (it is disabled while any field is invalid).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

import panel_catalog
import schema

#: the Phase 1 spec format (re-exported)
TOP_LEVEL_KEYS = panel_catalog.TOP_LEVEL_KEYS
COMPONENT_KEYS = panel_catalog.COMPONENT_KEYS
SCHEMA_VERSION = panel_catalog.SCHEMA_VERSION


def _err(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"code": code, "message": message}
    out.update(extra)
    return out


def validate_panel_spec(spec: Any) -> List[Dict[str, Any]]:
    """Validate a panel spec; returns a list of errors (empty == valid)."""
    errors: List[Dict[str, Any]] = []

    if not isinstance(spec, dict):
        return [_err("bad_type", "the panel spec must be a JSON object")]

    for key in sorted(spec):
        if key not in TOP_LEVEL_KEYS:
            errors.append(
                _err("unknown_field", "unknown top-level field: %s" % key, path=key)
            )
    for key in ("run_id", "request", "components"):
        if key not in spec:
            errors.append(
                _err("missing_field", "missing required field: %s" % key, path=key)
            )
    if errors:
        return errors

    if spec["schema_version"] != SCHEMA_VERSION:
        errors.append(
            _err("bad_schema_version", "schema_version must be %d" % SCHEMA_VERSION)
        )
    if not isinstance(spec["request"], str):
        errors.append(_err("bad_type", "request must be a string", path="request"))

    components = spec["components"]
    if not isinstance(components, list):
        errors.append(
            _err("bad_type", "components must be a list", path="components")
        )
        return errors

    for index, component in enumerate(components):
        errors.extend(_validate_component(component, index, spec))
    return errors


def _validate_component(
    component: Any, index: int, spec: Dict[str, Any]
) -> List[Dict[str, Any]]:
    errors: List[Dict[str, Any]] = []
    where = {"component_index": index}

    if not isinstance(component, dict):
        return [_err("bad_type", "component must be a JSON object", **where)]

    for key in sorted(component):
        if key not in COMPONENT_KEYS:
            errors.append(
                _err(
                    "unknown_field",
                    "unknown component field: %s" % key,
                    path=key,
                    **where,
                )
            )
    if "primitive" not in component:
        errors.append(_err("missing_field", "component has no primitive", **where))
        return errors

    name = component["primitive"]
    primitive = panel_catalog.get_primitive(name)
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
                _err(
                    "unknown_prop",
                    "primitive %s has no prop %r" % (name, key),
                    path=key,
                    **where,
                )
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

    if name in panel_catalog.PANEL_PRIMITIVES:
        errors.extend(_validate_panel_bindings(name, bindings, where))
    else:
        # a Phase 1 (lens) primitive: reuse the Phase 1 component validator
        mini = {
            "schema_version": SCHEMA_VERSION,
            "run_id": spec.get("run_id", ""),
            "request": spec.get("request", ""),
            "components": [component],
        }
        for error in panel_catalog.phase1_uispec.validate_spec(mini, {}):
            errors.append(_err(error.get("code", "invalid"), error.get("message", ""), **where))
    return errors


def _validate_panel_bindings(
    name: str, bindings: Mapping[str, Any], where: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """The strict checks on the five panel primitives."""
    errors: List[Dict[str, Any]] = []

    parameter_name = bindings.get("parameter")
    spec = None
    if name in ("ParamSlider", "ParamNumber", "ChoiceSelect", "SweepAxis"):
        if not isinstance(parameter_name, str):
            errors.append(
                _err(
                    "bad_type",
                    "primitive %s: the parameter binding must be a parameter name"
                    % name,
                    path="parameter",
                    **where,
                )
            )
            return errors
        spec = schema.parameter(parameter_name)
        if spec is None:
            errors.append(
                _err(
                    "unknown_parameter",
                    "primitive %s: %r is not in the frozen scoped set"
                    % (name, parameter_name),
                    path="parameter",
                    **where,
                )
            )
            return errors

    # ---- unit ---------------------------------------------------------
    if "unit" in bindings:
        canonical = panel_catalog.normalize_unit(bindings["unit"])
        if canonical is None:
            errors.append(
                _err(
                    "unknown_unit",
                    "primitive %s: %r is not a unit the strict layer can check"
                    % (name, bindings["unit"]),
                    path="unit",
                    **where,
                )
            )
        elif spec is not None and canonical != panel_catalog.normalize_unit(spec.unit):
            errors.append(
                _err(
                    "unit_mismatch",
                    "primitive %s: parameter %s is declared in %s, the binding "
                    "says %s" % (name, spec.name, spec.unit, canonical),
                    path="unit",
                    **where,
                )
            )

    if spec is None:
        return errors

    # ---- frozen range (the panel may not widen it) ---------------------
    # (the SweepAxis carries the *sweep* range, which is checked against the
    # frozen range by the strict layer, not against the frozen range itself)
    for bound in ("min", "max"):
        if bound in bindings and name in ("ParamSlider", "ParamNumber"):
            frozen = spec.minimum if bound == "min" else spec.maximum
            value = bindings[bound]
            if frozen is None:
                errors.append(
                    _err(
                        "range_mismatch",
                        "primitive %s: parameter %s has no frozen %s (it is an "
                        "enumerated parameter)" % (name, spec.name, bound),
                        path=bound,
                        **where,
                    )
                )
            elif not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(
                    _err(
                        "bad_type",
                        "primitive %s: the %s binding must be a number" % (name, bound),
                        path=bound,
                        **where,
                    )
                )
            elif abs(float(value) - float(frozen)) > 1e-12:
                errors.append(
                    _err(
                        "range_mismatch",
                        "primitive %s: the %s binding (%s) is not the frozen %s "
                        "of %s (%s) - the panel may not widen a frozen range"
                        % (name, bound, value, bound, spec.name, frozen),
                        path=bound,
                        **where,
                    )
                )

    # ---- value --------------------------------------------------------
    if name in ("ParamSlider", "ParamNumber", "ChoiceSelect") and "value" in bindings:
        submission: Dict[str, Any] = {"value": bindings["value"]}
        if "unit" in bindings:
            submission["unit"] = bindings["unit"]
        result = schema.validate_state({spec.name: submission}, require_all=False)
        for error in result.errors:
            errors.append(
                _err(error["code"], error["message"], path="value", **where)
            )

    # ---- choices ------------------------------------------------------
    if name == "ChoiceSelect" and "choices" in bindings:
        listed = bindings["choices"]
        if not isinstance(listed, list) or tuple(listed) != tuple(spec.choices):
            errors.append(
                _err(
                    "bad_choice",
                    "primitive %s: the choices binding must be exactly the frozen "
                    "choice list (%s)" % (name, ", ".join(spec.choices)),
                    path="choices",
                    **where,
                )
            )

    # ---- sweep axis ---------------------------------------------------
    if name == "SweepAxis":
        axis = {
            "parameter": bindings.get("parameter"),
            "min": bindings.get("min"),
            "max": bindings.get("max"),
            "steps": bindings.get("steps"),
        }
        for error in schema.validate_sweep_axis(axis):
            errors.append(
                _err(error["code"], error["message"], path="axis", **where)
            )

    # ---- run button ---------------------------------------------------
    if name == "RunButton":
        enabled = bindings.get("enabled")
        if not isinstance(enabled, bool):
            errors.append(
                _err(
                    "bad_type",
                    "primitive RunButton: the enabled binding must be a boolean",
                    path="enabled",
                    **where,
                )
            )
        invalid = bindings.get("invalid_fields", [])
        if not isinstance(invalid, list) or any(
            not isinstance(item, str) for item in invalid
        ):
            errors.append(
                _err(
                    "bad_type",
                    "primitive RunButton: the invalid_fields binding must be a "
                    "list of parameter names",
                    path="invalid_fields",
                    **where,
                )
            )
        elif isinstance(enabled, bool) and enabled != (not invalid):
            errors.append(
                _err(
                    "inconsistent_run_button",
                    "primitive RunButton: enabled=%s contradicts the invalid "
                    "field list %s - the button is disabled while any field is "
                    "invalid" % (enabled, invalid),
                    path="enabled",
                    **where,
                )
            )

    return errors


def panel_state(spec: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
    """The panel submission the spec carries (parameter -> submission)."""
    state: Dict[str, Dict[str, Any]] = {}
    for component in spec.get("components", []):
        name = component.get("primitive")
        if name not in ("ParamSlider", "ParamNumber", "ChoiceSelect"):
            continue
        bindings = component.get("bindings", {}) or {}
        parameter_name = bindings.get("parameter")
        if not isinstance(parameter_name, str):
            continue
        submission: Dict[str, Any] = {"value": bindings.get("value")}
        if "unit" in bindings:
            submission["unit"] = bindings["unit"]
        state[parameter_name] = submission
    return state


def sweep_axis(spec: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """The sweep axis the spec carries (``None`` when there is none)."""
    for component in spec.get("components", []):
        if component.get("primitive") != "SweepAxis":
            continue
        bindings = component.get("bindings", {}) or {}
        axis: Dict[str, Any] = {
            "parameter": bindings.get("parameter"),
            "min": bindings.get("min"),
            "max": bindings.get("max"),
            "steps": bindings.get("steps"),
        }
        if "unit" in bindings:
            axis["unit"] = bindings["unit"]
        return axis
    return None


def invalid_fields(spec: Mapping[str, Any]) -> List[str]:
    """The parameters the strict layer rejects in this panel's state."""
    state = panel_state(spec)
    result = schema.validate_state(state, require_all=False)
    fields = []
    for error in result.errors:
        name = error.get("parameter")
        if name and name not in fields:
            fields.append(name)
    return fields


def run_button_enabled(spec: Mapping[str, Any]) -> bool:
    """Whether the run button of this panel is enabled (all fields valid)."""
    state = panel_state(spec)
    result = schema.validate_state(state, require_all=False)
    axis = sweep_axis(spec)
    if axis is not None and schema.validate_sweep_axis(axis):
        return False
    return result.ok

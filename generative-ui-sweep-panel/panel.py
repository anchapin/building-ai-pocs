"""Panel generation: a plain-language sweep request -> a validated panel spec.

Deterministic, rule-based, no LLM, no network, no randomness, no clock.
The assembler produces a **spec** and a **configuration** - it never runs
anything, never calls a solver, and never edits a geometry.

Request grammar (the whole of it)
----------------------------------

``sweep <parameter> from <min> to <max> [unit] in <steps> steps``
``set <parameter> to <value> [unit]``   (optional, repeatable)

Anything else is refused explicitly.  The parameter may be named by its
scoped name (``heating_setpoint_c``) or by a friendly alias
("heating setpoint").

The panel always exposes the **whole frozen scoped set** (that is the point
of a sweep panel over the scoped measures) and exactly one sweep axis.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import panel_catalog
import panel_spec
import schema

# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------

#: friendly alias -> scoped parameter name
ALIASES: Dict[str, str] = {
    "heating setpoint": "heating_setpoint_c",
    "occupied heating setpoint": "heating_setpoint_c",
    "heating setpoint occupied": "heating_setpoint_c",
    "unoccupied heating setpoint": "heating_setpoint_unoccupied_c",
    "heating setpoint unoccupied": "heating_setpoint_unoccupied_c",
    "cooling setpoint": "cooling_setpoint_c",
    "occupied cooling setpoint": "cooling_setpoint_c",
    "cooling setpoint occupied": "cooling_setpoint_c",
    "unoccupied cooling setpoint": "cooling_setpoint_unoccupied_c",
    "cooling setpoint unoccupied": "cooling_setpoint_unoccupied_c",
    "infiltration": "infiltration_ach",
    "infiltration rate": "infiltration_ach",
    "air change rate": "infiltration_ach",
    "internal gain": "internal_gain_w",
    "internal gains": "internal_gain_w",
    "window u value": "window_u_value_w_m2k",
    "window": "window_u_value_w_m2k",
    "wall u value": "wall_u_value_w_m2k",
    "wall": "wall_u_value_w_m2k",
    "roof u value": "roof_u_value_w_m2k",
    "roof": "roof_u_value_w_m2k",
    "cooling cop": "cooling_cop",
    "cop": "cooling_cop",
    "heating efficiency": "heating_efficiency",
    "solar absorptance": "solar_absorptance",
    "absorptance": "solar_absorptance",
    "heating capacity": "heating_capacity_kw",
    "simulation hours": "simulation_hours",
    "simulation length": "simulation_hours",
    "occupancy schedule": "occupancy_schedule",
    "schedule": "occupancy_schedule",
}

SWEEP_RE = re.compile(
    r"sweep\s+(?P<parameter>[a-z0-9]+(?:[ -][a-z0-9]+)*?)\s+from\s+"
    r"(?P<min>-?\d+(?:\.\d+)?)\s+to\s+(?P<max>-?\d+(?:\.\d+)?)(?P<rest>.*)$"
)

SET_RE = re.compile(
    r"set\s+(?P<parameter>[a-z0-9]+(?:[ -][a-z0-9]+)*?)\s+to\s+"
    r"(?P<value>-?\d+(?:\.\d+)?)(?P<rest>.*?)(?=\s+set\s+|$)"
)

STEPS_RE = re.compile(r"\b(?:in|over|across)\s+(\d+)\s+steps?\b")

#: words that introduce a unit and are not units themselves
UNIT_INTRODUCERS = frozenset({"in", "with", "using", "as", "at", "of"})

NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


def _unit_in_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    """Find a unit mention in ``text``.

    Returns ``(canonical_unit, offending_token)``: the first token that
    canonicalises as a unit, or the first token that does not canonicalise
    at all (an unknown unit, e.g. ``BTU/h`` on a °C parameter).
    """
    for token in text.split():
        if token in UNIT_INTRODUCERS:
            continue
        canonical = panel_catalog.normalize_unit(token)
        if canonical is None:
            return None, token
        return canonical, None
    return None, None



def _normalise(text: str) -> str:
    """Lower-case, underscores to spaces, punctuation to spaces."""
    lowered = text.lower().replace("_", " ")
    cleaned = re.sub(r"[^0-9a-z°./ -]+", " ", lowered)
    return re.sub(r"\s+", " ", cleaned).strip()


def _resolve_parameter(text: str) -> Optional[str]:
    """Map a parameter mention to a scoped parameter name (``None`` if none)."""
    key = _normalise(text).strip()
    if not key:
        return None
    if key in schema.PARAMETERS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    # "window u value w m2 k" style leftovers
    collapsed = key.replace(" ", "")
    for name in schema.SCOPED_PARAMETER_NAMES:
        if collapsed == name.replace("_", ""):
            return name
    return None


def _parse_number(text: str) -> Optional[float]:
    text = text.strip()
    if not NUMBER_RE.match(text):
        return None
    return float(text)


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------


def build_panel(request: str, case_id: Optional[str] = None) -> Dict[str, Any]:
    """Build a panel spec (or an explicit refusal) from a request."""
    if not isinstance(request, str) or not request.strip():
        return panel_catalog.make_refusal(
            "empty_request", "the request is blank"
        )

    text = _normalise(request)

    sweep_match = SWEEP_RE.search(text)
    if sweep_match is None:
        return panel_catalog.make_refusal(
            "no_known_intent",
            "the request does not name a sweep; the panel understands "
            "'sweep <parameter> from <min> to <max> in <steps> steps'",
        )

    axis_parameter = _resolve_parameter(sweep_match.group("parameter"))
    if axis_parameter is None:
        mention = sweep_match.group("parameter").strip()
        if schema.is_geometric_name(mention):
            return panel_catalog.make_refusal(
                "unknown_parameter",
                "the sweep axis names a structural / geometric parameter (%r): "
                "this POC sweeps the frozen scoped set only and never edits "
                "geometry" % mention,
                unmatched=mention,
            )
        return panel_catalog.make_refusal(
            "unknown_parameter",
            "the sweep axis names no parameter of the frozen scoped set: %r"
            % mention,
            unmatched=mention,
        )
    axis_spec = schema.parameter(axis_parameter)
    if axis_spec is None:
        return panel_catalog.make_refusal(
            "unknown_parameter",
            "the sweep axis parameter %r is not in the frozen scoped set"
            % axis_parameter,
            parameter=axis_parameter,
        )
    if axis_spec.type == schema.CHOICE:
        return panel_catalog.make_refusal(
            "unsupported_axis_type",
            "the sweep axis parameter %r is an enumerated parameter and cannot "
            "be swept numerically" % axis_parameter,
            parameter=axis_parameter,
        )

    axis_min = _parse_number(sweep_match.group("min"))
    axis_max = _parse_number(sweep_match.group("max"))

    rest = sweep_match.group("rest") or ""
    steps_match = STEPS_RE.search(rest)
    steps = int(steps_match.group(1)) if steps_match else 5
    unit_text = STEPS_RE.sub(" ", rest)

    axis_unit, offending = _unit_in_text(unit_text)
    if offending is not None:
        return panel_catalog.make_refusal(
            "unknown_unit",
            "%r is not a unit the strict layer can check" % offending,
        )
    if axis_unit is not None:
        declared = panel_catalog.normalize_unit(axis_spec.unit)
        if axis_unit != declared:
            return panel_catalog.make_refusal(
                "unit_mismatch",
                "parameter %s is declared in %s; the request asked for %s"
                % (axis_parameter, axis_spec.unit, axis_unit),
                parameter=axis_parameter,
            )

    axis = {
        "parameter": axis_parameter,
        "min": axis_min,
        "max": axis_max,
        "steps": steps,
    }
    axis_errors = schema.validate_sweep_axis(axis)
    if axis_errors:
        return panel_catalog.make_refusal(
            axis_errors[0]["code"],
            axis_errors[0]["message"],
            errors=axis_errors,
        )

    # ---- optional "set <parameter> to <value>" overrides ---------------
    overrides: Dict[str, Dict[str, Any]] = {}
    remainder = text[: sweep_match.start()] + " " + text[sweep_match.end() :]
    for match in SET_RE.finditer(remainder):
        name = _resolve_parameter(match.group("parameter"))
        if name is None:
            mention = match.group("parameter").strip()
            if schema.is_geometric_name(mention):
                return panel_catalog.make_refusal(
                    "unknown_parameter",
                    "the request sets a structural / geometric parameter (%r): "
                    "this POC never edits geometry" % mention,
                    unmatched=mention,
                )
            return panel_catalog.make_refusal(
                "unknown_parameter",
                "the request sets a parameter that is not in the frozen scoped "
                "set: %r" % mention,
                unmatched=mention,
            )
        param_spec = schema.parameter(name)
        value = _parse_number(match.group("value"))
        if value is None:
            return panel_catalog.make_refusal(
                "bad_type",
                "the request sets %r to a value that is not a number" % name,
                parameter=name,
            )
        unit_token, offending = _unit_in_text(match.group("rest") or "")
        if offending is not None:
            return panel_catalog.make_refusal(
                "unknown_unit",
                "%r is not a unit the strict layer can check" % offending,
                parameter=name,
            )
        if unit_token is not None:
            if unit_token != panel_catalog.normalize_unit(param_spec.unit):
                return panel_catalog.make_refusal(
                    "unit_mismatch",
                    "parameter %s is declared in %s; the request asked for %s. "
                    "The panel works in the declared SI unit; the strict layer "
                    "converts an imperial submission explicitly."
                    % (name, param_spec.unit, unit_token),
                    parameter=name,
                )
        overrides[name] = {"value": value, "unit": param_spec.unit}

    # ---- build the components -----------------------------------------
    state = schema.default_state()
    state.update(overrides)

    components: List[Dict[str, Any]] = []
    for param_spec in schema.FROZEN_SCOPED_PARAMETERS:
        submission = state[param_spec.name]
        if param_spec.primitive == "ChoiceSelect":
            components.append(
                {
                    "primitive": "ChoiceSelect",
                    "title": param_spec.label,
                    "bindings": {
                        "parameter": param_spec.name,
                        "value": submission["value"],
                        "choices": list(param_spec.choices),
                    },
                    "props": {
                        "title": param_spec.label,
                        "help": "frozen choices: %s" % ", ".join(param_spec.choices),
                    },
                }
            )
            continue
        bindings: Dict[str, Any] = {
            "parameter": param_spec.name,
            "unit": param_spec.unit,
            "value": submission["value"],
        }
        if param_spec.primitive == "ParamSlider":
            bindings["min"] = param_spec.minimum
            bindings["max"] = param_spec.maximum
        else:
            bindings["min"] = param_spec.minimum
            bindings["max"] = param_spec.maximum
        components.append(
            {
                "primitive": param_spec.primitive,
                "title": param_spec.label,
                "bindings": bindings,
                "props": {
                    "title": param_spec.label,
                    "unit_label": panel_catalog.unit_label(param_spec.unit),
                    "help": "frozen range %s - %s %s"
                    % (param_spec.minimum, param_spec.maximum, param_spec.unit),
                },
            }
        )

    axis_component = {
        "primitive": "SweepAxis",
        "title": "Sweep axis: %s" % axis_spec.label,
        "bindings": {
            "parameter": axis_parameter,
            "unit": axis_spec.unit,
            "min": axis_min,
            "max": axis_max,
            "steps": steps,
        },
        "props": {
            "title": "Sweep axis: %s" % axis_spec.label,
            "label": "%s %s to %s %s in %d steps"
            % (axis_min, axis_spec.unit, axis_max, axis_spec.unit, steps),
        },
    }
    components.append(axis_component)

    # ---- run button ----------------------------------------------------
    probe = {"components": components}
    invalid = panel_spec.invalid_fields(probe)
    components.append(
        {
            "primitive": "RunButton",
            "title": "Run sweep",
            "bindings": {"enabled": not invalid, "invalid_fields": invalid},
            "props": {
                "title": "Run sweep",
                "disabled_reason": (
                    "invalid fields: %s" % ", ".join(invalid) if invalid else ""
                ),
            },
        }
    )

    case = case_id or ("sweep_%s" % axis_parameter)
    spec = panel_catalog.make_spec(
        run_id="panel_%s" % case,
        request=request,
        components=components,
        case_id=case,
    )

    errors = panel_spec.validate_panel_spec(spec)
    if errors:
        return panel_catalog.make_refusal(
            "internal_validation_failure",
            "the assembled panel spec did not validate",
            errors=errors,
        )
    return spec


# --------------------------------------------------------------------------
# the write path: submit values, get a validated state back
# --------------------------------------------------------------------------


def submit(spec: Dict[str, Any], submission: Dict[str, Any]) -> schema.ValidationResult:
    """Submit panel values; the strict layer validates and normalises them.

    ``submission`` maps a parameter name to ``{"value": ..., "unit": ...}``.
    The result carries the normalised (SI) state and every imperial
    conversion that was applied, with the formula that produced it.
    """
    return schema.validate_state(submission, require_all=False)


def run_enabled(spec: Dict[str, Any]) -> bool:
    """Whether the panel's run button is enabled (all fields valid)."""
    return panel_spec.run_button_enabled(spec)

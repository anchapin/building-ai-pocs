"""Strict schema layer for the generative-UI sweep panel (issue #38).

This module is the ONLY place where a panel submission is judged, and the
ONLY place where the scoped parameter set lives.  It owns:

* the **frozen scoped parameter set** (written first, before any panel was
  built, and never widened afterwards),
* the strict validation of a panel submission: unknown parameters, wrong
  types, out-of-range values, unit mismatches,
* the **explicit** imperial -> SI conversion (never silent: every conversion
  is returned together with the formula that produced it).

Hard rules of this POC (issue #38):

* no solver, no network, no generated-code execution - this module only
  produces and checks data,
* no geometry: the frozen set contains no geometric parameter, and any
  attempt to sweep one is refused as an unknown parameter,
* the scoped set is frozen: it is a module-level constant and there is no
  API to add a parameter to it.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import panel_catalog

# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------

#: every rejection code this layer can produce (closed list)
ERROR_CODES: Tuple[str, ...] = (
    "unknown_parameter",
    "unknown_field",
    "bad_type",
    "missing_value",
    "missing_unit",
    "unknown_unit",
    "unit_mismatch",
    "out_of_range",
    "non_finite",
    "bad_choice",
    "inconsistent_setpoints",
    "unsupported_axis_type",
    "bad_axis",
)


def _err(code: str, message: str, **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"code": code, "message": message}
    out.update(extra)
    return out


# --------------------------------------------------------------------------
# the frozen scoped parameter set
# --------------------------------------------------------------------------

NUMBER = "number"
INTEGER = "integer"
CHOICE = "choice"


@dataclass(frozen=True)
class ParameterSpec:
    """One scoped parameter: name, type, SI unit, range, default, evidence."""

    name: str
    type: str
    unit: str
    minimum: Optional[float]
    maximum: Optional[float]
    default: Any
    primitive: str
    imperial_unit: Optional[str] = None
    choices: Tuple[str, ...] = ()
    label: str = ""
    evidence: str = ""
    evidence_kind: str = "in-repo"  # "in-repo" | "physical-bound" | "decision"

    @property
    def is_numeric(self) -> bool:
        return self.type in (NUMBER, INTEGER)

    def default_submission(self) -> Dict[str, Any]:
        """The submission the panel starts from (defaults are valid by fiat)."""
        if self.type == CHOICE:
            return {"value": self.default}
        return {"value": self.default, "unit": self.unit}


#: Evidence kinds, spelled out once:
#:
#: ``in-repo``        the value (or the parameter's existence) is attested by
#:                    a file inside this repository,
#: ``physical-bound`` the range is an engineering bound cited by the POC
#:                    (no Fluxion measure spec exists in this worktree - see
#:                    REPORT.md),
#: ``decision``       the value is a POC decision (e.g. a schedule enum).
#:
#: No range in this table is attested by a Fluxion measure spec: Fluxion is
#: not inside this worktree and the issue forbids reading outside it.
FROZEN_SCOPED_PARAMETERS: Tuple[ParameterSpec, ...] = (
    ParameterSpec(
        name="heating_setpoint_c",
        type=NUMBER,
        unit="°C",
        minimum=10.0,
        maximum=30.0,
        default=21.0,
        primitive="ParamSlider",
        imperial_unit="°F",
        label="Heating setpoint (occupied)",
        evidence=(
            "generative-ui-diagnostic-lens/fixtures/runs/run_ashrae140_case1.json "
            "inputs.heating_setpoint_c = 24.0; "
            "ss-dfa-surrogate-poc/src/gen_data.py HVAC.T_heat_set_occ = 21.0"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="heating_setpoint_unoccupied_c",
        type=NUMBER,
        unit="°C",
        minimum=5.0,
        maximum=25.0,
        default=17.0,
        primitive="ParamSlider",
        imperial_unit="°F",
        label="Heating setpoint (unoccupied)",
        evidence=(
            "ss-dfa-surrogate-poc/src/gen_data.py HVAC.T_heat_set_unocc = 17.0"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="cooling_setpoint_c",
        type=NUMBER,
        unit="°C",
        minimum=18.0,
        maximum=35.0,
        default=24.5,
        primitive="ParamSlider",
        imperial_unit="°F",
        label="Cooling setpoint (occupied)",
        evidence=(
            "ss-dfa-surrogate-poc/src/gen_data.py HVAC.T_cool_set_occ = 24.5"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="cooling_setpoint_unoccupied_c",
        type=NUMBER,
        unit="°C",
        minimum=20.0,
        maximum=40.0,
        default=28.0,
        primitive="ParamSlider",
        imperial_unit="°F",
        label="Cooling setpoint (unoccupied)",
        evidence=(
            "ss-dfa-surrogate-poc/src/gen_data.py HVAC.T_cool_set_unocc = 28.0"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="infiltration_ach",
        type=NUMBER,
        unit="1/h",
        minimum=0.0,
        maximum=10.0,
        default=0.35,
        primitive="ParamSlider",
        label="Infiltration air-change rate",
        evidence=(
            "generative-ui-diagnostic-lens/fixtures/runs/run_ashrae140_case1.json "
            "inputs.infiltration_ach = 0.35; upper bound 10 1/h is the "
            "engineering bound used by this POC (sheltered building, "
            "stack-driven infiltration)"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="internal_gain_w",
        type=NUMBER,
        unit="W",
        minimum=0.0,
        maximum=20000.0,
        default=1200.0,
        primitive="ParamNumber",
        imperial_unit="Btu/h",
        label="Internal gains (total)",
        evidence=(
            "generative-ui-diagnostic-lens/fixtures/runs/run_ashrae140_case1.json "
            "inputs.internal_gain_w = 1200.0"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="window_u_value_w_m2k",
        type=NUMBER,
        unit="W/m2.K",
        minimum=0.1,
        maximum=6.0,
        default=2.2,
        primitive="ParamSlider",
        imperial_unit="Btu/h.ft2.F",
        label="Window U-value",
        evidence=(
            "generative-ui-diagnostic-lens/README.md (adversarial request set) "
            "names a 'window U-value' request; the 0.1-6.0 W/(m2.K) band is the "
            "engineering bound used by this POC (ISO 10456 / EN ISO 10077 order "
            "of magnitude for glazing, no Fluxion measure spec in-worktree)"
        ),
        evidence_kind="physical-bound",
    ),
    ParameterSpec(
        name="wall_u_value_w_m2k",
        type=NUMBER,
        unit="W/m2.K",
        minimum=0.1,
        maximum=3.0,
        default=0.35,
        primitive="ParamSlider",
        imperial_unit="Btu/h.ft2.F",
        label="Wall U-value",
        evidence=(
            "engineering bound used by this POC (ISO 10456 order of magnitude "
            "for opaque envelope constructions); no Fluxion measure spec "
            "in-worktree"
        ),
        evidence_kind="physical-bound",
    ),
    ParameterSpec(
        name="roof_u_value_w_m2k",
        type=NUMBER,
        unit="W/m2.K",
        minimum=0.05,
        maximum=1.5,
        default=0.15,
        primitive="ParamSlider",
        imperial_unit="Btu/h.ft2.F",
        label="Roof U-value",
        evidence=(
            "engineering bound used by this POC (ISO 10456 order of magnitude "
            "for roof constructions); no Fluxion measure spec in-worktree"
        ),
        evidence_kind="physical-bound",
    ),
    ParameterSpec(
        name="cooling_cop",
        type=NUMBER,
        unit="1",
        minimum=1.0,
        maximum=6.5,
        default=3.2,
        primitive="ParamNumber",
        label="Cooling coefficient of performance",
        evidence=(
            "ss-dfa-surrogate-poc/src/gen_data.py HVAC.cop_a = 4.0, cop_min = 1.8 "
            "(COP(T_out) = max(1.8, 4.0 - 0.08 (T_out - 20))); upper bound 6.5 is "
            "the engineering bound used by this POC (Carnot limit with a 40 K lift)"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="heating_efficiency",
        type=NUMBER,
        unit="1",
        minimum=0.5,
        maximum=1.0,
        default=0.85,
        primitive="ParamNumber",
        label="Heater efficiency (COP-ish)",
        evidence="ss-dfa-surrogate-poc/src/gen_data.py HVAC.eta_heat = 0.85",
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="solar_absorptance",
        type=NUMBER,
        unit="1",
        minimum=0.1,
        maximum=0.99,
        default=0.6,
        primitive="ParamSlider",
        label="Solar absorptance",
        evidence=(
            "engineering bound used by this POC (opaque surface absorptance "
            "0.1-0.99); no Fluxion measure spec in-worktree"
        ),
        evidence_kind="physical-bound",
    ),
    ParameterSpec(
        name="heating_capacity_kw",
        type=NUMBER,
        unit="kW",
        minimum=1.0,
        maximum=500.0,
        default=8.0,
        primitive="ParamNumber",
        imperial_unit="kBtu/h",
        label="Heating capacity",
        evidence="ss-dfa-surrogate-poc/src/gen_data.py HVAC.Q_h_max = 8000.0 W = 8 kW",
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="simulation_hours",
        type=INTEGER,
        unit="h",
        minimum=1,
        maximum=8760,
        default=8760,
        primitive="ParamNumber",
        label="Simulation length",
        evidence=(
            "generative-ui-diagnostic-lens/fixtures/runs/run_ashrae140_case1.json "
            "inputs.run_hours = 24; the Phase 1 real-output report covers 8760 "
            "timesteps of 3600 s (REPORT.md slice 2)"
        ),
        evidence_kind="in-repo",
    ),
    ParameterSpec(
        name="occupancy_schedule",
        type=CHOICE,
        unit="1",
        minimum=None,
        maximum=None,
        default="office_standard",
        primitive="ChoiceSelect",
        choices=("office_standard", "school_shift", "residential_24h", "always_on"),
        label="Occupancy schedule",
        evidence=(
            "POC decision: the four schedules the panel can select; the Phase 1 "
            "lens has no schedule measure and no Fluxion measure spec is "
            "in-worktree"
        ),
        evidence_kind="decision",
    ),
)

#: name -> spec (the frozen set, as a lookup)
PARAMETERS: Dict[str, ParameterSpec] = {p.name: p for p in FROZEN_SCOPED_PARAMETERS}

#: the names of the frozen scoped set
SCOPED_PARAMETER_NAMES: Tuple[str, ...] = tuple(p.name for p in FROZEN_SCOPED_PARAMETERS)

#: names that are frozen OUT (geometry / structure) - the panel must refuse
#: them explicitly rather than treating them as "unknown typos"
NON_SCOPED_GEOSTRUCTURE_NAMES: Tuple[str, ...] = (
    "zone_area_m2",
    "floor_area_m2",
    "window_area_m2",
    "wall_thickness_m",
    "zone_count",
    "building_rotation_deg",
    "zone_geometry",
    "window_geometry",
    "structure",
)

#: words that mark a name as structural / geometric
GEOMETRIC_WORDS: Tuple[str, ...] = (
    "area",
    "thickness",
    "geometry",
    "structure",
    "rotation",
    "count",
    "volume",
    "width",
    "height",
    "length",
    "position",
    "coordinates",
    "aspect",
)


def is_geometric_name(name: str) -> bool:
    """True when a name looks structural / geometric.

    Used to give the *reason* for a refusal: an attempt to sweep a
    geometric quantity is refused as such, not as an unknown typo.
    """
    text = str(name).lower()
    words = [word for word in re.split(r"[^a-z0-9]+", text) if word]
    return any(word in GEOMETRIC_WORDS for word in words)


def parameter(name: str) -> Optional[ParameterSpec]:
    """The spec of a scoped parameter (``None`` if it is not scoped)."""
    return PARAMETERS.get(name)


def is_scoped(name: str) -> bool:
    return name in PARAMETERS


def default_state() -> Dict[str, Dict[str, Any]]:
    """The panel's starting state: every scoped parameter at its default."""
    return {spec.name: spec.default_submission() for spec in FROZEN_SCOPED_PARAMETERS}


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationResult:
    """The verdict of the strict layer on one submission."""

    ok: bool
    errors: Tuple[Dict[str, Any], ...]
    normalized: Dict[str, Dict[str, Any]]
    conversions: Tuple[Dict[str, Any], ...]

    @property
    def reason(self) -> str:
        """A readable one-line reason (the first error)."""
        if not self.errors:
            return "valid"
        return "%s: %s" % (self.errors[0]["code"], self.errors[0]["message"])

    def error_codes(self) -> Tuple[str, ...]:
        return tuple(e["code"] for e in self.errors)


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float))


def _validate_one(
    spec: ParameterSpec,
    submission: Any,
    errors: List[Dict[str, Any]],
    conversions: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Validate one parameter submission; return the normalised entry."""
    if not isinstance(submission, dict):
        errors.append(
            _err(
                "bad_type",
                "parameter %r: the submission must be an object with a 'value' "
                "(and, for numeric parameters, a 'unit')" % spec.name,
                parameter=spec.name,
            )
        )
        return None

    for key in sorted(submission):
        if key not in ("value", "unit"):
            errors.append(
                _err(
                    "unknown_field",
                    "parameter %r: the submission has no field %r (only 'value' "
                    "and 'unit' are allowed)" % (spec.name, key),
                    parameter=spec.name,
                )
            )

    if "value" not in submission:
        errors.append(
            _err(
                "missing_value",
                "parameter %r: the submission carries no value" % spec.name,
                parameter=spec.name,
            )
        )
        return None

    value = submission["value"]

    # ---- choice parameters -------------------------------------------
    if spec.type == CHOICE:
        if not isinstance(value, str):
            errors.append(
                _err(
                    "bad_type",
                    "parameter %r: the value must be one of the strings %s, not %s"
                    % (spec.name, ", ".join(spec.choices), type(value).__name__),
                    parameter=spec.name,
                )
            )
            return None
        if value not in spec.choices:
            errors.append(
                _err(
                    "bad_choice",
                    "parameter %r: %r is not one of the frozen choices (%s)"
                    % (spec.name, value, ", ".join(spec.choices)),
                    parameter=spec.name,
                )
            )
            return None
        if submission.get("unit") not in (None, ""):
            errors.append(
                _err(
                    "unit_mismatch",
                    "parameter %r: a choice parameter carries no unit (the "
                    "submission must not name one)" % spec.name,
                    parameter=spec.name,
                )
            )
            return None
        return {"value": value, "unit": spec.unit}

    # ---- numeric parameters ------------------------------------------
    if not _is_number(value):
        errors.append(
            _err(
                "bad_type",
                "parameter %r: the value must be a %s, not %s"
                % (spec.name, "number" if spec.type == NUMBER else "whole number",
                   type(value).__name__),
                parameter=spec.name,
            )
        )
        return None
    if not math.isfinite(float(value)):
        errors.append(
            _err(
                "non_finite",
                "parameter %r: the value %r is not a finite number"
                % (spec.name, value),
                parameter=spec.name,
            )
        )
        return None
    if spec.type == INTEGER and float(value) != int(value):
        errors.append(
            _err(
                "bad_type",
                "parameter %r: the value %r is not a whole number (the parameter "
                "is an integer)" % (spec.name, value),
                parameter=spec.name,
            )
        )
        return None

    unit = submission.get("unit")
    if unit is None or unit == "":
        errors.append(
            _err(
                "missing_unit",
                "parameter %r: the submission carries no unit (the parameter is "
                "declared in %s)" % (spec.name, spec.unit),
                parameter=spec.name,
            )
        )
        return None
    if not isinstance(unit, str):
        errors.append(
            _err(
                "bad_type",
                "parameter %r: the unit must be a string, not %s"
                % (spec.name, type(unit).__name__),
                parameter=spec.name,
            )
        )
        return None

    canonical = panel_catalog.normalize_unit(unit)
    if canonical is None:
        errors.append(
            _err(
                "unknown_unit",
                "parameter %r: %r is not a unit the strict layer can check"
                % (spec.name, unit),
                parameter=spec.name,
            )
        )
        return None

    declared = panel_catalog.normalize_unit(spec.unit)
    si_value = float(value)
    si_unit = declared
    if canonical != declared:
        if spec.imperial_unit and canonical == panel_catalog.normalize_unit(spec.imperial_unit):
            # explicit, shown conversion - never silent
            try:
                converted, formula = panel_catalog.convert(si_value, canonical, declared)
            except ValueError as exc:  # pragma: no cover - guarded by the table
                errors.append(
                    _err(
                        "unit_mismatch",
                        "parameter %r: cannot convert %s to %s (%s)"
                        % (spec.name, canonical, declared, exc),
                        parameter=spec.name,
                    )
                )
                return None
            conversions.append(
                {
                    "parameter": spec.name,
                    "submitted_value": value,
                    "submitted_unit": canonical,
                    "converted_value": converted,
                    "si_unit": declared,
                    "formula": formula,
                }
            )
            si_value = converted
        else:
            declared_dimension = panel_catalog.unit_dimension(declared)
            submitted_dimension = panel_catalog.unit_dimension(canonical)
            accepted = [declared]
            if spec.imperial_unit:
                accepted.append(panel_catalog.normalize_unit(spec.imperial_unit))
            if declared_dimension != submitted_dimension:
                message = (
                    "parameter %r is declared in %s (%s); the submitted unit %r is a "
                    "%s - a different quantity, and this layer never converts "
                    "between quantities"
                    % (
                        spec.name,
                        declared,
                        declared_dimension,
                        canonical,
                        submitted_dimension,
                    )
                )
            else:
                message = (
                    "parameter %r is declared in %s; the submitted unit %r is neither "
                    "the declared unit nor the declared imperial counterpart (%s) - "
                    "convert it explicitly and submit the declared unit"
                    % (
                        spec.name,
                        declared,
                        canonical,
                        ", ".join(accepted[1:]) or "none",
                    )
                )
            errors.append(
                _err("unit_mismatch", message, parameter=spec.name)
            )
            return None

    # ---- range ---------------------------------------------------------
    if spec.minimum is not None and si_value < float(spec.minimum) - 1e-12:
        errors.append(
            _err(
                "out_of_range",
                "parameter %r: %s is below the frozen minimum %s"
                % (
                    spec.name,
                    _amount(si_value, si_unit),
                    _amount(float(spec.minimum), si_unit),
                ),
                parameter=spec.name,
                minimum=spec.minimum,
                maximum=spec.maximum,
            )
        )
        return None
    if spec.maximum is not None and si_value > float(spec.maximum) + 1e-12:
        errors.append(
            _err(
                "out_of_range",
                "parameter %r: %s is above the frozen maximum %s"
                % (
                    spec.name,
                    _amount(si_value, si_unit),
                    _amount(float(spec.maximum), si_unit),
                ),
                parameter=spec.name,
                minimum=spec.minimum,
                maximum=spec.maximum,
            )
        )
        return None

    normalised_value: Any = si_value
    if spec.type == INTEGER:
        normalised_value = int(round(si_value))
    return {"value": normalised_value, "unit": si_unit}


def _fmt(value: float) -> str:
    text = ("%.6f" % float(value)).rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


def _amount(value: float, unit: str) -> str:
    """A value with its unit, readable for dimensionless quantities."""
    if unit == "1":
        return "%s (dimensionless)" % _fmt(value)
    return "%s %s" % (_fmt(value), unit)


def validate_state(
    state: Mapping[str, Any], require_all: bool = True
) -> ValidationResult:
    """Validate a whole panel submission.

    ``state`` maps a parameter name to ``{"value": ..., "unit": ...}``.  Every
    rejection is explicit: unknown parameters, wrong types, out-of-range
    values, unit mismatches.
    """
    errors: List[Dict[str, Any]] = []
    conversions: List[Dict[str, Any]] = []
    normalized: Dict[str, Dict[str, Any]] = {}

    if not isinstance(state, Mapping):
        return ValidationResult(
            ok=False,
            errors=(_err("bad_type", "the panel submission must be an object"),),
            normalized={},
            conversions=(),
        )

    for name in sorted(state):
        if name in PARAMETERS:
            continue
        if name in NON_SCOPED_GEOSTRUCTURE_NAMES or is_geometric_name(name):
            errors.append(
                _err(
                    "unknown_parameter",
                    "parameter %r is a structural / geometric parameter: it is not "
                    "in the frozen scoped set and this POC never edits geometry"
                    % name,
                    parameter=name,
                )
            )
        else:
            errors.append(
                _err(
                    "unknown_parameter",
                    "parameter %r is not in the frozen scoped set (%s)"
                    % (name, ", ".join(SCOPED_PARAMETER_NAMES)),
                    parameter=name,
                )
            )

    for name in SCOPED_PARAMETER_NAMES:
        if name not in state:
            if require_all:
                errors.append(
                    _err(
                        "missing_value",
                        "parameter %r: the submission carries no value" % name,
                        parameter=name,
                    )
                )
            continue
        entry = _validate_one(PARAMETERS[name], state[name], errors, conversions)
        if entry is not None:
            normalized[name] = entry

    # ---- cross-parameter consistency -----------------------------------
    heat = normalized.get("heating_setpoint_c")
    cool = normalized.get("cooling_setpoint_c")
    if heat and cool and float(cool["value"]) <= float(heat["value"]):
        errors.append(
            _err(
                "inconsistent_setpoints",
                "cooling_setpoint_c (%s °C) must be above heating_setpoint_c (%s °C)"
                % (_fmt(float(cool["value"])), _fmt(float(heat["value"]))),
                parameter="cooling_setpoint_c",
            )
        )
    heat_u = normalized.get("heating_setpoint_unoccupied_c")
    cool_u = normalized.get("cooling_setpoint_unoccupied_c")
    if heat_u and cool_u and float(cool_u["value"]) <= float(heat_u["value"]):
        errors.append(
            _err(
                "inconsistent_setpoints",
                "cooling_setpoint_unoccupied_c (%s °C) must be above "
                "heating_setpoint_unoccupied_c (%s °C)"
                % (_fmt(float(cool_u["value"])), _fmt(float(heat_u["value"]))),
                parameter="cooling_setpoint_unoccupied_c",
            )
        )

    return ValidationResult(
        ok=not errors,
        errors=tuple(errors),
        normalized=normalized,
        conversions=tuple(conversions),
    )


def validate_sweep_axis(axis: Any) -> List[Dict[str, Any]]:
    """Validate the sweep axis against the frozen scoped set.

    An axis that names an unscoped parameter (a geometry sweep, say) is
    refused here - this is the "no sweeps outside the frozen scoped set" rule.
    """
    errors: List[Dict[str, Any]] = []
    if not isinstance(axis, Mapping):
        return [_err("bad_axis", "the sweep axis must be an object")]

    for key in sorted(axis):
        if key not in ("parameter", "min", "max", "steps", "unit"):
            errors.append(
                _err("unknown_field", "the sweep axis has no field %r" % key)
            )

    name = axis.get("parameter")
    if not isinstance(name, str) or not name:
        errors.append(_err("bad_axis", "the sweep axis names no parameter"))
        return errors
    spec = PARAMETERS.get(name)
    if spec is None:
        if name in NON_SCOPED_GEOSTRUCTURE_NAMES or is_geometric_name(name):
            errors.append(
                _err(
                    "unknown_parameter",
                    "the sweep axis parameter %r is a structural / geometric "
                    "parameter: this POC sweeps the frozen scoped set only"
                    % name,
                    parameter=name,
                )
            )
        else:
            errors.append(
                _err(
                    "unknown_parameter",
                    "the sweep axis parameter %r is not in the frozen scoped set "
                    "(%s)" % (name, ", ".join(SCOPED_PARAMETER_NAMES)),
                    parameter=name,
                )
            )
        return errors

    if spec.type == CHOICE:
        errors.append(
            _err(
                "unsupported_axis_type",
                "the sweep axis parameter %r is an enumerated parameter and "
                "cannot be swept numerically" % name,
                parameter=name,
            )
        )
        return errors

    low = axis.get("min")
    high = axis.get("max")
    steps = axis.get("steps")

    if not _is_number(low) or not _is_number(high):
        errors.append(
            _err("bad_axis", "the sweep axis min and max must be numbers")
        )
        return errors
    if float(low) >= float(high):
        errors.append(
            _err(
                "bad_axis",
                "the sweep axis min (%s) must be below its max (%s)"
                % (_fmt(float(low)), _fmt(float(high))),
            )
        )
        return errors
    if isinstance(steps, bool) or not isinstance(steps, int) or steps < 2:
        errors.append(
            _err("bad_axis", "the sweep axis steps must be an integer of at least 2")
        )
        return errors

    if spec.minimum is not None and float(low) < float(spec.minimum) - 1e-12:
        errors.append(
            _err(
                "out_of_range",
                "the sweep axis min (%s) is below the frozen minimum of %s (%s %s)"
                % (_fmt(float(low)), name, _fmt(float(spec.minimum)), spec.unit),
                parameter=name,
            )
        )
    if spec.maximum is not None and float(high) > float(spec.maximum) + 1e-12:
        errors.append(
            _err(
                "out_of_range",
                "the sweep axis max (%s) is above the frozen maximum of %s (%s %s)"
                % (_fmt(float(high)), name, _fmt(float(spec.maximum)), spec.unit),
                parameter=name,
            )
        )
    return errors


def validate_panel_state(
    state: Mapping[str, Any], axis: Any, require_all: bool = True
) -> ValidationResult:
    """Validate a panel submission *and* its sweep axis together."""
    result = validate_state(state, require_all=require_all)
    axis_errors = validate_sweep_axis(axis)
    if axis_errors:
        return ValidationResult(
            ok=False,
            errors=tuple(result.errors) + tuple(axis_errors),
            normalized=result.normalized,
            conversions=result.conversions,
        )
    return result

"""Panel catalog: the Phase 1 catalog, *extended* (never forked) with the
five sweep-panel primitives of issue #38.

What is reused
--------------

The Phase 1 POC (``generative-ui-diagnostic-lens/``) owns the closed
six-primitive catalog, the unit vocabulary and the UI-spec document shape.
This module **imports** that module (it is not copied, and it is not
modified) and adds the five primitives the write-path panel needs:

``ParamSlider``   a continuous parameter, drawn as a slider
``ParamNumber``   a numeric parameter with an explicit typed field
``ChoiceSelect``  an enumerated parameter
``SweepAxis``     the axis a sweep runs along
``RunButton``     the (possibly disabled) run trigger

The Phase 1 ``Primitive`` dataclass is reused verbatim, so a panel primitive
and a lens primitive are described in exactly the same way (required /
optional bindings, binding kinds, accepted units, accepted dimensions, the
"no data" rendering, props).

Unit vocabulary
---------------

The Phase 1 unit table is reused as-is; this module *adds* the three
imperial units the strict layer needs for an explicit conversion
(``Btu/h``, ``kBtu/h``, ``Btu/h.ft2.F``) and one dimensional unit
(``1/h``).  There is still exactly ONE unit vocabulary: the Phase 1
``normalize_unit`` is applied first, the imperial extension second.
"""

from __future__ import annotations

import os
import sys
from typing import Dict, Optional, Tuple

# --------------------------------------------------------------------------
# reuse the Phase 1 modules (read-only; they are never modified here)
# --------------------------------------------------------------------------

_PHASE1_DIR = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, "generative-ui-diagnostic-lens")
)
if _PHASE1_DIR not in sys.path:
    sys.path.insert(0, _PHASE1_DIR)

import catalog as phase1_catalog  # noqa: E402  (path set up just above)
import uispec as phase1_uispec  # noqa: E402
import renderer as phase1_renderer  # noqa: E402

#: the Phase 1 spec format (re-exported, not re-implemented)
SCHEMA_VERSION = phase1_uispec.SCHEMA_VERSION
TOP_LEVEL_KEYS = phase1_uispec.TOP_LEVEL_KEYS
COMPONENT_KEYS = phase1_uispec.COMPONENT_KEYS
make_spec = phase1_uispec.make_spec
make_refusal = phase1_uispec.make_refusal
is_refusal = phase1_uispec.is_refusal

# --------------------------------------------------------------------------
# units: Phase 1 table + the imperial extension
# --------------------------------------------------------------------------

#: Phase 1 canonical unit -> (dimension, label)
UNIT_TABLE: Dict[str, Tuple[str, str]] = dict(phase1_catalog.UNIT_TABLE)

#: extra canonical units this POC adds (dimension, label, factor to its SI twin)
IMPERIAL_UNITS: Dict[str, Tuple[str, str, float]] = {
    "Btu/h": ("power", "Btu/h", 3.4121416331273),
    "kBtu/h": ("power", "kBtu/h", 3.4121416331273),
    "Btu/h.ft2.F": ("power_density", "Btu/h.ft2.F", 5.678263337),
}

#: extra canonical units this POC adds that are not imperial
EXTRA_UNITS: Dict[str, Tuple[str, str]] = {
    "1/h": ("air_change_rate", "1/h"),
}

#: alias -> canonical unit (Phase 1 aliases + the imperial/extra ones)
UNIT_ALIASES: Dict[str, str] = dict(phase1_catalog.UNIT_ALIASES)
UNIT_ALIASES.update(
    {
        "btuh": "Btu/h",
        "btu/h": "Btu/h",
        "btuperhour": "Btu/h",
        "kbtuh": "kBtu/h",
        "kbtu/h": "kBtu/h",
        "btuhft2f": "Btu/h.ft2.F",
        "btu/h.ft2.f": "Btu/h.ft2.F",
        "btu/h*ft2*f": "Btu/h.ft2.F",
        "btuperhsquarefootdegreefahrenheit": "Btu/h.ft2.F",
        "1h": "1/h",
        "ach": "1/h",
        "airchangesperhour": "1/h",
    }
)

#: unit -> factor/offset conversions that are *not* a plain factor.
#: ``value_si = value * factor + offset``
TEMPERATURE_CONVERSIONS: Dict[Tuple[str, str], Tuple[float, float]] = {
    ("°F", "°C"): (5.0 / 9.0, -32.0 * 5.0 / 9.0),
    ("K", "°C"): (1.0, -273.15),
}


def normalize_unit(token: Optional[str]) -> Optional[str]:
    """Canonicalise a unit token (Phase 1 first, then this POC's extension).

    Unknown tokens return ``None`` - they are never guessed at.
    """
    if token is None:
        return None
    canonical = phase1_catalog.normalize_unit(token)
    if canonical is not None:
        return canonical
    raw = token.strip()
    if raw in IMPERIAL_UNITS or raw in EXTRA_UNITS:
        return raw
    return UNIT_ALIASES.get(_unit_key(raw))


def _unit_key(token: str) -> str:
    """Alias-lookup key: lower-case, punctuation stripped (Phase 1 rule)."""
    text = token.strip().lower()
    text = text.replace("°", "deg").replace("²", "2").replace("³", "3")
    text = text.replace(".", "").replace("/", "").replace(" ", "").replace("_", "")
    return text


def unit_dimension(unit: Optional[str]) -> Optional[str]:
    """Dimension family of a canonical unit (``None`` if unknown)."""
    canonical = normalize_unit(unit)
    if canonical is None:
        return None
    if canonical in UNIT_TABLE:
        return UNIT_TABLE[canonical][0]
    if canonical in IMPERIAL_UNITS:
        return IMPERIAL_UNITS[canonical][0]
    if canonical in EXTRA_UNITS:
        return EXTRA_UNITS[canonical][0]
    return None


def unit_label(unit: Optional[str]) -> str:
    """Human label used on axes / cards; unknown units render as ``?``."""
    canonical = normalize_unit(unit)
    if canonical is None:
        return "?"
    if canonical in UNIT_TABLE:
        return UNIT_TABLE[canonical][1]
    if canonical in IMPERIAL_UNITS:
        return IMPERIAL_UNITS[canonical][1]
    if canonical in EXTRA_UNITS:
        return EXTRA_UNITS[canonical][1]
    return "?"


def convert(value: float, from_unit: str, to_unit: str) -> Tuple[float, str]:
    """Convert ``value`` from one canonical unit to another.

    Returns ``(converted_value, formula_text)``.  The formula text is
    always produced: a conversion is never silent.

    Raises ``ValueError`` when the two units are not convertible.
    """
    src = normalize_unit(from_unit)
    dst = normalize_unit(to_unit)
    if src is None or dst is None:
        raise ValueError("unknown unit in conversion %r -> %r" % (from_unit, to_unit))
    if src == dst:
        return float(value), "%s %s = %s %s (no conversion)" % (
            _num(value),
            src,
            _num(value),
            dst,
        )
    if (src, dst) in TEMPERATURE_CONVERSIONS:
        factor, offset = TEMPERATURE_CONVERSIONS[(src, dst)]
        out = float(value) * factor + offset
        if src == "°F":
            formula = "(%s − 32) × 5/9 = %s %s" % (_num(value), _num(out), dst)
        else:
            formula = "%s − 273.15 = %s %s" % (_num(value), _num(out), dst)
        return out, formula
    if src in IMPERIAL_UNITS and dst in UNIT_TABLE:
        src_dim, _label, factor = IMPERIAL_UNITS[src]
        if src_dim != UNIT_TABLE[dst][0]:
            raise ValueError("cannot convert %r to %r" % (from_unit, to_unit))
        out = float(value) * factor
        return out, "%s %s × %s = %s %s" % (_num(value), src, _num(factor), _num(out), dst)
    raise ValueError("cannot convert %r to %r" % (from_unit, to_unit))


def _num(value: float) -> str:
    """Short, deterministic number text (no locale, no randomness)."""
    text = ("%.6f" % float(value)).rstrip("0").rstrip(".")
    return text if text not in ("", "-") else "0"


# --------------------------------------------------------------------------
# primitives: Phase 1's, plus the five panel primitives
# --------------------------------------------------------------------------

Primitive = phase1_catalog.Primitive

#: the Phase 1 primitives, by name (the lens' six)
PHASE1_PRIMITIVES: Dict[str, Primitive] = dict(phase1_catalog._PRIMITIVES)

PANEL_PRIMITIVES: Dict[str, Primitive] = {}


def _register(primitive: Primitive) -> Primitive:
    PANEL_PRIMITIVES[primitive.name] = primitive
    return primitive


_register(
    Primitive(
        name="ParamSlider",
        summary="A continuous scoped parameter, drawn as a slider.",
        required_bindings=("parameter", "unit", "min", "max"),
        optional_bindings=("value", "step"),
        binding_kinds={
            "parameter": "parameter",
            "unit": "unit",
            "min": "number",
            "max": "number",
            "value": "number",
            "step": "number",
        },
        accepted_units=phase1_catalog.detectable_units()
        + tuple(EXTRA_UNITS)
        + tuple(IMPERIAL_UNITS),
        accepted_dimensions=(
            "temperature",
            "power",
            "power_density",
            "air_change_rate",
            "dimensionless",
        ),
        absent_binding_rendering=(
            "no data - the slider shows the parameter's declared range and no "
            "value is carried"
        ),
        props=("title", "unit_label", "help"),
        notes=(
            "the parameter must be one of the frozen scoped set; the range is "
            "the parameter's frozen range, never widened by the panel."
        ),
    )
)

_register(
    Primitive(
        name="ParamNumber",
        summary="A numeric scoped parameter with an explicit typed field.",
        required_bindings=("parameter", "unit", "value"),
        optional_bindings=("min", "max"),
        binding_kinds={
            "parameter": "parameter",
            "unit": "unit",
            "value": "number",
            "min": "number",
            "max": "number",
        },
        accepted_units=phase1_catalog.detectable_units()
        + tuple(EXTRA_UNITS)
        + tuple(IMPERIAL_UNITS),
        accepted_dimensions=(
            "temperature",
            "power",
            "power_density",
            "air_change_rate",
            "dimensionless",
            "time",
        ),
        absent_binding_rendering="no data - the field shows its declared unit and no value",
        props=("title", "unit_label", "help"),
        notes="integer parameters use the same primitive; the schema layer checks integrality.",
    )
)

_register(
    Primitive(
        name="ChoiceSelect",
        summary="An enumerated scoped parameter.",
        required_bindings=("parameter", "value"),
        optional_bindings=("choices",),
        binding_kinds={
            "parameter": "parameter",
            "value": "choice",
            "choices": "choice_list",
        },
        accepted_units=(),
        accepted_dimensions=(),
        absent_binding_rendering="no data - the selector lists its choices and carries no value",
        props=("title", "help"),
        notes="the choice list is the frozen one; the panel never widens it.",
    )
)

_register(
    Primitive(
        name="SweepAxis",
        summary="The axis a sweep runs along.",
        required_bindings=("parameter", "min", "max", "steps"),
        optional_bindings=("unit",),
        binding_kinds={
            "parameter": "parameter",
            "unit": "unit",
            "min": "number",
            "max": "number",
            "steps": "int",
        },
        accepted_units=phase1_catalog.detectable_units()
        + tuple(EXTRA_UNITS)
        + tuple(IMPERIAL_UNITS),
        accepted_dimensions=(
            "temperature",
            "power",
            "power_density",
            "air_change_rate",
            "dimensionless",
        ),
        absent_binding_rendering="no data - the axis carries no parameter",
        props=("title", "label"),
        notes="the axis parameter must be one of the frozen scoped set.",
    )
)

_register(
    Primitive(
        name="RunButton",
        summary="The run trigger; disabled while any field is invalid.",
        required_bindings=("enabled",),
        optional_bindings=("invalid_fields",),
        binding_kinds={"enabled": "boolean", "invalid_fields": "string_list"},
        accepted_units=(),
        accepted_dimensions=(),
        absent_binding_rendering="no data - the button is disabled and says why",
        props=("title", "disabled_reason"),
        notes=(
            "the button is a SPEC only: this POC never runs anything. The "
            "enabled flag is the strict layer's verdict on the panel state."
        ),
    )
)


def get_primitive(name: str) -> Optional[Primitive]:
    """Phase 1 primitive or panel primitive (``None`` if unknown)."""
    if name in PANEL_PRIMITIVES:
        return PANEL_PRIMITIVES[name]
    return PHASE1_PRIMITIVES.get(name)


def all_primitives() -> Dict[str, Primitive]:
    """Every primitive this POC knows: the Phase 1 six plus the panel five."""
    out: Dict[str, Primitive] = dict(PHASE1_PRIMITIVES)
    out.update(PANEL_PRIMITIVES)
    return out


#: the primitives this POC adds (the "catalog extension" of issue #38)
PANEL_PRIMITIVE_NAMES: Tuple[str, ...] = (
    "ParamSlider",
    "ParamNumber",
    "ChoiceSelect",
    "SweepAxis",
    "RunButton",
)

"""Catalog of the six diagnostic-lens primitives.

The catalog is CLOSED: exactly six primitives, no additions (issue #37).

Every primitive declares:

* the binding fields it requires (and the optional ones it understands),
* the units it accepts (canonical unit names and the unit *dimensions*),
* what it renders when a binding is absent (the "no data" rendering) — the
  lens never invents data to fill a gap.

Binding kinds used below:

* ``field`` — a field name that must exist in the run's field manifest,
* ``unit``  — a unit token (canonicalised via :func:`normalize_unit`),
* ``number`` — a plain numeric constant,
* ``string`` — a free-form identifier (e.g. a zone id),
* ``int``    — a positive integer (e.g. how many log lines to show).

The catalog is pure data + helpers: no I/O, no network, no model calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Dict, Mapping, Optional, Tuple

# --------------------------------------------------------------------------
# Units
# --------------------------------------------------------------------------

#: canonical unit -> (dimension, human-readable label)
UNIT_TABLE: Dict[str, Tuple[str, str]] = {
    "°C": ("temperature", "degC"),
    "°F": ("temperature", "degF"),
    "K": ("temperature", "K"),
    "W": ("power", "W"),
    "kW": ("power", "kW"),
    "MW": ("power", "MW"),
    "Wh": ("energy", "Wh"),
    "kWh": ("energy", "kWh"),
    "MWh": ("energy", "MWh"),
    "kg/s": ("mass_flow", "kg/s"),
    "g/s": ("mass_flow", "g/s"),
    "kg/kg": ("moisture", "kg/kg"),
    "g/kg": ("moisture", "g/kg"),
    "g/m3": ("moisture", "g/m3"),
    "kg/m3": ("moisture", "kg/m3"),
    "%": ("percentage", "%"),
    "%RH": ("percentage", "%RH"),
    "W/m2": ("power_density", "W/m2"),
    "W/m2.K": ("power_density", "W/m2.K"),
    "m": ("length", "m"),
    "m2": ("area", "m2"),
    "m3": ("volume", "m3"),
    "m3/h": ("volume_flow", "m3/h"),
    "Pa": ("pressure", "Pa"),
    "h": ("time", "h"),
    "min": ("time", "min"),
    "s": ("time", "s"),
    "1": ("dimensionless", "-"),
}

#: alias (lowercase, punctuation-normalised) -> canonical unit
UNIT_ALIASES: Dict[str, str] = {
    "degc": "°C",
    "degreecelsius": "°C",
    "celsius": "°C",
    "c": "°C",
    "degf": "°F",
    "degreefahrenheit": "°F",
    "fahrenheit": "°F",
    "f": "°F",
    "kelvin": "K",
    "w": "W",
    "watt": "W",
    "watts": "W",
    "kw": "kW",
    "kilowatt": "kW",
    "kilowatts": "kW",
    "mw": "MW",
    "megawatt": "MW",
    "wh": "Wh",
    "kwh": "kWh",
    "kilowatthour": "kWh",
    "mwh": "MWh",
    "kgs": "kg/s",
    "kgsec": "kg/s",
    "gs": "g/s",
    "kgkg": "kg/kg",
    "gkg": "g/kg",
    "gm3": "g/m3",
    "kgm3": "kg/m3",
    "percent": "%",
    "pct": "%",
    "rh": "%RH",
    "relativehumidity": "%RH",
    "wm2": "W/m2",
    "m": "m",
    "metre": "m",
    "meter": "m",
    "m2": "m2",
    "m3": "m3",
    "m3h": "m3/h",
    "pa": "Pa",
    "pascal": "Pa",
    "h": "h",
    "hr": "h",
    "hour": "h",
    "hours": "h",
    "min": "min",
    "minute": "min",
    "minutes": "min",
    "s": "s",
    "sec": "s",
    "second": "s",
    "seconds": "s",
    "1": "1",
    "none": "1",
    "dimensionless": "1",
}


def _unit_key(token: str) -> str:
    """Normalise a unit token for alias lookup (lower-case, no punctuation)."""
    text = token.strip().lower()
    text = text.replace("°", "deg").replace("²", "2").replace("³", "3")
    text = text.replace(".", "").replace("/", "").replace(" ", "").replace("_", "")
    return text


def normalize_unit(token: Optional[str]) -> Optional[str]:
    """Canonicalise a unit token, or return ``None`` if it is not a unit.

    Unknown unit tokens are *not* silently accepted: the validator rejects
    them, because a unit the lens cannot canonicalise is a unit it cannot
    check.
    """
    if token is None:
        return None
    raw = token.strip()
    if raw in UNIT_TABLE:
        return raw
    key = _unit_key(raw)
    if key in UNIT_ALIASES:
        return UNIT_ALIASES[key]
    # a few compound forms that survive punctuation stripping
    if key in ("w/m2k", "wm2k"):
        return "W/m2.K"
    return None


def unit_dimension(unit: Optional[str]) -> Optional[str]:
    """Dimension family of a canonical unit (``None`` if unknown)."""
    canonical = normalize_unit(unit)
    if canonical is None:
        return None
    return UNIT_TABLE[canonical][0]


def unit_label(unit: Optional[str]) -> str:
    """Human label used on axes / cards; unknown units render as ``?``."""
    canonical = normalize_unit(unit)
    if canonical is None:
        return "?"
    return UNIT_TABLE[canonical][1]


# --------------------------------------------------------------------------
# Primitives
# --------------------------------------------------------------------------

#: binding kinds, per primitive field name
BINDING_KINDS: Dict[str, Dict[str, str]] = {}


@dataclass(frozen=True)
class Primitive:
    """One catalog entry."""

    name: str
    summary: str
    required_bindings: Tuple[str, ...]
    optional_bindings: Tuple[str, ...]
    binding_kinds: Mapping[str, str]
    accepted_units: Tuple[str, ...]
    accepted_dimensions: Tuple[str, ...]
    absent_binding_rendering: str
    props: Tuple[str, ...] = ()
    notes: str = ""

    def allowed_bindings(self) -> Tuple[str, ...]:
        return tuple(self.required_bindings) + tuple(self.optional_bindings)

    def binding_kind(self, name: str) -> Optional[str]:
        return self.binding_kinds.get(name)

    def accepts_unit(self, unit: Optional[str]) -> bool:
        """True if ``unit`` is a unit this primitive can carry."""
        canonical = normalize_unit(unit)
        if canonical is None:
            return False
        if not self.accepted_dimensions:
            return False
        return UNIT_TABLE[canonical][0] in self.accepted_dimensions


_TEMPERATURE = ("temperature",)
_POWER = ("power", "energy")
_MOIST = ("moisture", "percentage", "mass_flow", "power_density")
_NUMERIC = (
    "temperature",
    "power",
    "energy",
    "mass_flow",
    "moisture",
    "percentage",
    "power_density",
    "length",
    "area",
    "volume",
    "volume_flow",
    "pressure",
    "time",
    "dimensionless",
)

_PRIMITIVES: Dict[str, Primitive] = {}


def _register(primitive: Primitive) -> Primitive:
    _PRIMITIVES[primitive.name] = primitive
    return primitive


_register(
    Primitive(
        name="TimeSeriesChart",
        summary="Time series with unit-labelled axes.",
        required_bindings=("series", "unit"),
        optional_bindings=(),
        binding_kinds={"series": "field", "unit": "unit"},
        accepted_units=("°C", "°F", "K", "W", "kW", "kg/s", "kg/kg", "%", "W/m2"),
        accepted_dimensions=_NUMERIC,
        absent_binding_rendering=(
            "no data - the chart keeps its unit-labelled axes but shows no data "
            "for the bound series"
        ),
        props=("title", "x_axis_label"),
        notes="x axis is the run's own sample index/time; never extrapolated.",
    )
)

_register(
    Primitive(
        name="DiffTable",
        summary="Case value vs reference range, out-of-range rows flagged.",
        required_bindings=("series", "unit"),
        optional_bindings=("reference_min", "reference_max", "reference_series"),
        binding_kinds={
            "series": "field",
            "unit": "unit",
            "reference_min": "number",
            "reference_max": "number",
            "reference_series": "field",
        },
        accepted_units=("°C", "°F", "K", "W", "kW", "kg/s", "kg/kg", "%"),
        accepted_dimensions=_NUMERIC,
        absent_binding_rendering=(
            "no data - the reference-range column shows no data when no "
            "reference band is bound"
        ),
        props=("title", "aggregation"),
        notes=(
            "out-of-range flagging needs a reference band; with no band the "
            "row is rendered but never flagged."
        ),
    )
)

_register(
    Primitive(
        name="KPICard",
        summary="Named scalar with unit.",
        required_bindings=("field", "unit"),
        optional_bindings=(),
        binding_kinds={"field": "field", "unit": "unit"},
        accepted_units=("°C", "°F", "K", "W", "kW", "MWh", "kg/s", "kg/kg", "%", "m3/h"),
        accepted_dimensions=_NUMERIC,
        absent_binding_rendering="no data - the card shows the name and no value",
        props=("title", "label", "aggregation"),
    )
)

_register(
    Primitive(
        name="ZoneHighlight",
        summary="Zone/surface id plus its series, schematic only.",
        required_bindings=("zone_id", "series", "unit"),
        optional_bindings=(),
        binding_kinds={"zone_id": "string", "series": "field", "unit": "unit"},
        accepted_units=("°C", "°F", "K", "%", "%RH", "kg/kg", "W/m2"),
        accepted_dimensions=_TEMPERATURE + ("percentage", "moisture", "power_density"),
        absent_binding_rendering=(
            "no data - the schematic zone is drawn but carries no data for the "
            "bound series"
        ),
        props=("title",),
        notes="schematic only: no geometry is reconstructed and none is invented.",
    )
)

_register(
    Primitive(
        name="LogTail",
        summary="Last N lines of the run log.",
        required_bindings=("log_field", "count"),
        optional_bindings=(),
        binding_kinds={"log_field": "field", "count": "int"},
        accepted_units=(),
        accepted_dimensions=(),
        absent_binding_rendering="no data - the run log is unavailable",
        props=("title",),
    )
)

_register(
    Primitive(
        name="ParamInspector",
        summary="Read-only inputs / provenance view.",
        required_bindings=(),
        optional_bindings=("field",),
        binding_kinds={"field": "field"},
        accepted_units=(),
        accepted_dimensions=(),
        absent_binding_rendering="no data - no input or provenance entries are available",
        props=("title", "section"),
        notes="read-only: the lens never edits, patches or re-runs inputs.",
    )
)

for _p in _PRIMITIVES.values():
    for _b, _k in _p.binding_kinds.items():
        BINDING_KINDS.setdefault(_p.name, {})[_b] = _k


PRIMITIVE_NAMES: Tuple[str, ...] = (
    "TimeSeriesChart",
    "DiffTable",
    "KPICard",
    "ZoneHighlight",
    "LogTail",
    "ParamInspector",
)

assert set(PRIMITIVE_NAMES) == set(_PRIMITIVES), "catalog drift"


def get_primitive(name: str) -> Optional[Primitive]:
    """Return the primitive definition, or ``None`` for an unknown name."""
    return _PRIMITIVES.get(name)


def catalog() -> Dict[str, Primitive]:
    """The whole catalog as a fresh dict."""
    return dict(_PRIMITIVES)


def catalog_listing() -> list:
    """Stable, human-readable listing of the catalog (used by the POC runner)."""
    out = []
    for name in PRIMITIVE_NAMES:
        p = _PRIMITIVES[name]
        out.append(
            {
                "primitive": name,
                "summary": p.summary,
                "required_bindings": list(p.required_bindings),
                "optional_bindings": list(p.optional_bindings),
                "accepted_units": list(p.accepted_units),
                "accepted_dimensions": list(p.accepted_dimensions),
                "absent_binding_rendering": p.absent_binding_rendering,
            }
        )
    return out

"""Deterministic static-HTML renderer for a UI spec.

Pure standard library, no build step, no JavaScript framework, no network.
The renderer is the *only* place that touches series values; it never invents
them.  A binding that cannot be satisfied from the run output renders as
``no data``.

The output is deterministic: the same (spec, run) pair always produces
byte-identical HTML (no timestamps, no random ids).
"""

from __future__ import annotations

import html
from typing import Any, Dict, List, Optional, Sequence

import catalog

NO_DATA = "no data"


def _esc(text: Any) -> str:
    return html.escape(str(text), quote=True)


def _fmt(value: Any) -> str:
    if value is None:
        return NO_DATA
    if isinstance(value, float):
        text = ("%.4f" % value).rstrip("0").rstrip(".")
        return text if text not in ("", "-") else "0"
    return str(value)


def _values(run: Dict[str, Any], field_name: str) -> Optional[List[Any]]:
    fields = run.get("fields") or {}
    field = fields.get(field_name)
    if field is None:
        return None
    values = field.get("values")
    if values is None:
        scalar = field.get("value")
        if scalar is None:
            return None
        return [scalar]
    if not isinstance(values, list):
        return None
    return list(values)


def _numeric(values: Sequence[Any]) -> List[float]:
    out = []
    for value in values:
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out.append(float(value))
    return out


def _aggregate(values: Sequence[Any], how: str) -> Optional[float]:
    nums = _numeric(values)
    if not nums:
        return None
    if how == "mean":
        return sum(nums) / len(nums)
    if how == "sum":
        return sum(nums)
    if how == "max":
        return max(nums)
    if how == "min":
        return min(nums)
    return nums[-1]


def _svg_series(values: Sequence[float], unit: str, title: str) -> str:
    width, height = 520, 200
    pad_l, pad_r, pad_t, pad_b = 64, 16, 24, 40
    lo, hi = min(values), max(values)
    if hi == lo:
        hi = lo + 1.0
    n = len(values)

    def x_of(i: int) -> float:
        if n == 1:
            return pad_l + (width - pad_l - pad_r) / 2.0
        return pad_l + (width - pad_l - pad_r) * i / float(n - 1)

    def y_of(v: float) -> float:
        return pad_t + (height - pad_t - pad_b) * (hi - v) / (hi - lo)

    points = " ".join("%.2f,%.2f" % (x_of(i), y_of(v)) for i, v in enumerate(values))
    out = ['<svg class="chart" viewBox="0 0 %d %d" role="img" aria-label="%s">' % (width, height, _esc(title))]
    out.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d" />' % (pad_l, pad_t, pad_l, height - pad_b))
    out.append('<line class="axis" x1="%d" y1="%d" x2="%d" y2="%d" />' % (pad_l, height - pad_b, width - pad_r, height - pad_b))
    out.append('<polyline class="series" points="%s" />' % points)
    out.append('<text class="axis-label" x="%d" y="14">%s</text>' % (pad_l, _esc(unit)))
    out.append('<text class="axis-label" x="%d" y="%d">sample</text>' % (pad_l, height - 12))
    out.append('<text class="axis-label" x="8" y="%d">%s</text>' % (pad_t + 10, _esc(_fmt(lo))))
    out.append('<text class="axis-label" x="8" y="%d">%s</text>' % (pad_t - 6, _esc(_fmt(hi))))
    out.append("</svg>")
    return "".join(out)


def render_spec(spec: Dict[str, Any], run: Dict[str, Any], title: str = "Diagnostic lens") -> str:
    """Render a validated spec against a run output into static HTML."""
    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head><meta charset="utf-8" />')
    parts.append("<title>%s</title>" % _esc(title))
    parts.append(
        "<style>body{font-family:system-ui,sans-serif;margin:1.5rem;}"
        ".component{border:1px solid #ccc;border-radius:6px;padding:.75rem;margin:.75rem 0;}"
        ".nodata{color:#a00;font-style:italic;}"
        ".out{background:#fdd;}"
        "table{border-collapse:collapse;}td,th{border:1px solid #ccc;padding:.25rem .5rem;}"
        ".series{fill:none;stroke:#036;stroke-width:2;}.axis{stroke:#333;stroke-width:1;}"
        ".axis-label{font-size:11px;fill:#333;}</style>"
    )
    parts.append("</head><body>")
    parts.append("<h1>%s</h1>" % _esc(title))
    parts.append('<p class="meta">run %s &middot; request: %s</p>' % (_esc(spec.get("run_id", "?")), _esc(spec.get("request", ""))))

    for component in spec.get("components", []):
        parts.append(_render_component(component, run))

    parts.append("</body></html>")
    return "\n".join(parts)


def _render_component(component: Dict[str, Any], run: Dict[str, Any]) -> str:
    name = component.get("primitive", "?")
    bindings = component.get("bindings", {}) or {}
    props = component.get("props", {}) or {}
    heading = props.get("title") or component.get("title") or name
    body: str
    if name == "TimeSeriesChart":
        body = _render_timeseries(bindings, props, run)
    elif name == "DiffTable":
        body = _render_diff_table(bindings, props, run)
    elif name == "KPICard":
        body = _render_kpi(bindings, props, run)
    elif name == "ZoneHighlight":
        body = _render_zone(bindings, props, run)
    elif name == "LogTail":
        body = _render_log_tail(bindings, props, run)
    elif name == "ParamInspector":
        body = _render_params(bindings, props, run)
    else:
        body = '<p class="nodata">%s</p>' % _esc(NO_DATA)
    return '<section class="component" data-primitive="%s"><h2>%s</h2>%s</section>' % (
        _esc(name),
        _esc(heading),
        body,
    )


def _render_timeseries(bindings: Dict[str, Any], props: Dict[str, Any], run: Dict[str, Any]) -> str:
    series = bindings.get("series")
    unit = bindings.get("unit")
    if not series:
        return '<p class="nodata">%s</p>' % _esc(NO_DATA)
    values = _values(run, series)
    if not values:
        return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(series))
    nums = _numeric(values)
    if not nums:
        return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(series))
    chart = _svg_series(nums, catalog.unit_label(unit), series)
    label = "<p>%s &middot; unit %s &middot; n=%d</p>" % (
        _esc(series),
        _esc(catalog.unit_label(unit)),
        len(nums),
    )
    return label + chart


def _render_diff_table(bindings: Dict[str, Any], props: Dict[str, Any], run: Dict[str, Any]) -> str:
    series = bindings.get("series")
    unit = bindings.get("unit")
    if not series:
        return '<p class="nodata">%s</p>' % _esc(NO_DATA)
    values = _values(run, series)
    if not values:
        return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(series))
    how = props.get("aggregation", "last")
    value = _aggregate(values, how)

    ref_min = bindings.get("reference_min")
    ref_max = bindings.get("reference_max")
    ref_series = bindings.get("reference_series")
    ref_text = NO_DATA
    ref_value_text = NO_DATA
    deviation_text = NO_DATA
    flag = ""
    if ref_series:
        ref_values = _values(run, ref_series)
        if ref_values:
            ref_value = _aggregate(ref_values, how)
            ref_value_text = _fmt(ref_value)
            if isinstance(value, (int, float)) and isinstance(ref_value, (int, float)):
                deviation_text = "%+.4f" % (value - ref_value)
    if ref_min is not None and ref_max is not None:
        ref_text = "%s .. %s" % (_fmt(ref_min), _fmt(ref_max))
        if isinstance(value, (int, float)):
            if value < float(ref_min) or value > float(ref_max):
                flag = '<span class="out">out of range</span>'
    elif ref_series and ref_value_text != NO_DATA:
        ref_text = ref_value_text
    rows = [
        "<table><tr><th>field</th><th>value</th><th>reference range</th>"
        "<th>reference series</th><th>deviation</th><th>flag</th></tr>",
        "<tr><td>%s</td><td>%s %s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            _esc(series),
            _fmt(value),
            _esc(catalog.unit_label(unit)),
            ref_text,
            ref_value_text,
            deviation_text,
            flag or "&mdash;",
        ),
        "</table>",
    ]
    return "".join(rows)


def _render_kpi(bindings: Dict[str, Any], props: Dict[str, Any], run: Dict[str, Any]) -> str:
    field = bindings.get("field")
    unit = bindings.get("unit")
    if not field:
        return '<p class="nodata">%s</p>' % _esc(NO_DATA)
    values = _values(run, field)
    if not values:
        return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(field))
    value = _aggregate(values, props.get("aggregation", "last"))
    label = props.get("label") or field
    return '<div class="kpi"><div class="kpi-label">%s</div><div class="kpi-value">%s %s</div></div>' % (
        _esc(label),
        _fmt(value),
        _esc(catalog.unit_label(unit)),
    )


def _render_zone(bindings: Dict[str, Any], props: Dict[str, Any], run: Dict[str, Any]) -> str:
    zone_id = bindings.get("zone_id")
    series = bindings.get("series")
    unit = bindings.get("unit")
    if not zone_id:
        return '<p class="nodata">%s</p>' % _esc(NO_DATA)
    svg = [
        '<svg class="zone" viewBox="0 0 240 140" role="img" aria-label="schematic zone %s">' % _esc(zone_id),
        '<rect x="30" y="25" width="180" height="90" fill="#eef" stroke="#036" stroke-width="2" />',
        '<text x="120" y="75" text-anchor="middle" font-size="14">%s</text>' % _esc(zone_id),
        "</svg>",
    ]
    if not series:
        return "".join(svg) + '<p class="nodata">%s</p>' % _esc(NO_DATA)
    values = _values(run, series)
    if not values:
        return "".join(svg) + '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(series))
    value = _aggregate(values, "last")
    return (
        "".join(svg)
        + "<p>%s &middot; %s %s</p>" % (_esc(series), _fmt(value), _esc(catalog.unit_label(unit)))
    )


def _render_log_tail(bindings: Dict[str, Any], props: Dict[str, Any], run: Dict[str, Any]) -> str:
    log_field = bindings.get("log_field")
    count = bindings.get("count", 20)
    if not log_field:
        return '<p class="nodata">%s</p>' % _esc(NO_DATA)
    values = _values(run, log_field)
    if not values:
        return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(log_field))
    lines = [str(v) for v in values][-int(count):]
    if not lines:
        return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(log_field))
    body = "<pre class=\"log\">%s</pre>" % _esc("\n".join(lines))
    return body


def _render_params(bindings: Dict[str, Any], props: Dict[str, Any], run: Dict[str, Any]) -> str:
    field = bindings.get("field")
    section = props.get("section", "inputs")
    if field:
        values = _values(run, field)
        if not values:
            return '<p class="nodata">%s (%s)</p>' % (_esc(NO_DATA), _esc(field))
        value = _aggregate(values, "last")
        rows = [
            "<table><tr><th>parameter</th><th>value</th></tr>",
            "<tr><td>%s</td><td>%s</td></tr>" % (_esc(field), _fmt(value)),
            "</table>",
        ]
        return "".join(rows)
    if section == "provenance":
        prov = run.get("provenance") or {}
        if not prov:
            return '<p class="nodata">%s</p>' % _esc(NO_DATA)
        rows = ["<table><tr><th>key</th><th>value</th></tr>"]
        for key in sorted(prov):
            rows.append("<tr><td>%s</td><td>%s</td></tr>" % (_esc(key), _esc(prov[key])))
        rows.append("</table>")
        return "".join(rows)
    inputs = run.get("inputs") or {}
    if not inputs:
        return '<p class="nodata">%s</p>' % _esc(NO_DATA)
    rows = ["<table><tr><th>input</th><th>value</th></tr>"]
    for key in sorted(inputs):
        rows.append("<tr><td>%s</td><td>%s</td></tr>" % (_esc(key), _fmt(inputs[key])))
    rows.append("</table>")
    return "".join(rows)


def spec_series(spec: Dict[str, Any]) -> List[str]:
    """Field names bound by a spec (used for binding-validity reporting)."""
    names: List[str] = []
    for component in spec.get("components", []):
        for key, value in (component.get("bindings") or {}).items():
            if key in ("series", "field", "reference_series") and isinstance(value, str):
                names.append(value)
    return names

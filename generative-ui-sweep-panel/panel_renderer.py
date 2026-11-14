"""Static-HTML renderer for a panel spec.

The Phase 1 renderer is imported and reused (its escaping helper, its
"no data" wording and its stylesheet conventions); this module adds the
panel controls.  The renderer is deterministic: the same spec always
produces byte-identical HTML (no timestamps, no random ids).

The renderer never runs anything: the run button is rendered *disabled*
when the strict layer says the panel is invalid, and it carries no
action of its own.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import panel_catalog
import panel_spec
import schema

_esc = panel_catalog.phase1_renderer._esc
NO_DATA = panel_catalog.phase1_renderer.NO_DATA


def _fmt(value: Any) -> str:
    if value is None:
        return NO_DATA
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        text = ("%.6f" % value).rstrip("0").rstrip(".")
        return text if text not in ("", "-") else "0"
    return str(value)


STYLE = (
    "body{font-family:system-ui,sans-serif;margin:1.5rem;}"
    ".component{border:1px solid #ccc;border-radius:6px;padding:.75rem;margin:.75rem 0;}"
    ".nodata{color:#a00;font-style:italic;}"
    ".control{display:flex;gap:.75rem;align-items:center;margin:.25rem 0;}"
    ".control label{min-width:18rem;}"
    ".unit{color:#555;}"
    ".invalid{border-color:#a00;background:#fff5f5;}"
    "table{border-collapse:collapse;}td,th{border:1px solid #ccc;padding:.25rem .5rem;}"
    "button{padding:.4rem .9rem;}"
    "button[disabled]{opacity:.5;}"
)


def render_panel(spec: Mapping[str, Any], title: str = "Sweep panel") -> str:
    """Render a panel spec into static HTML."""
    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head><meta charset="utf-8" />')
    parts.append("<title>%s</title>" % _esc(title))
    parts.append("<style>%s</style>" % STYLE)
    parts.append("</head><body>")
    parts.append("<h1>%s</h1>" % _esc(title))
    parts.append(
        '<p class="meta">run %s &middot; case %s &middot; request: %s</p>'
        % (
            _esc(spec.get("run_id", "?")),
            _esc(spec.get("case_id", "?")),
            _esc(spec.get("request", "")),
        )
    )

    live_enabled = panel_spec.run_button_enabled(spec)
    live_invalid = panel_spec.invalid_fields(spec)
    for component in spec.get("components", []):
        parts.append(_render_component(component, live_enabled, live_invalid))

    parts.append("</body></html>")
    return "\n".join(parts)


def _render_component(
    component: Mapping[str, Any],
    live_enabled: bool = True,
    live_invalid: Optional[List[str]] = None,
) -> str:
    name = component.get("primitive", "?")
    bindings = component.get("bindings", {}) or {}
    props = component.get("props", {}) or {}
    heading = props.get("title") or component.get("title") or name

    if name == "ParamSlider":
        body = _render_slider(bindings, props)
    elif name == "ParamNumber":
        body = _render_number(bindings, props)
    elif name == "ChoiceSelect":
        body = _render_choice(bindings, props)
    elif name == "SweepAxis":
        body = _render_axis(bindings, props)
    elif name == "RunButton":
        body = _render_button(bindings, props, live_enabled, live_invalid or [])
    else:
        body = '<p class="nodata">%s</p>' % _esc(NO_DATA)

    css = "component"
    if name in ("ParamSlider", "ParamNumber", "ChoiceSelect"):
        parameter_name = bindings.get("parameter")
        spec = schema.parameter(parameter_name) if isinstance(parameter_name, str) else None
        if spec is not None:
            result = schema.validate_state(
                {spec.name: {"value": bindings.get("value"), "unit": bindings.get("unit")}},
                require_all=False,
            )
            if not result.ok:
                css = "component invalid"
    return '<section class="%s" data-primitive="%s"><h2>%s</h2>%s</section>' % (
        css,
        _esc(name),
        _esc(heading),
        body,
    )


def _render_slider(bindings: Mapping[str, Any], props: Mapping[str, Any]) -> str:
    parameter_name = bindings.get("parameter", "?")
    unit = bindings.get("unit", "")
    low = bindings.get("min")
    high = bindings.get("max")
    value = bindings.get("value")
    return (
        '<div class="control"><label for="f_%s">%s</label>'
        '<input type="range" id="f_%s" min="%s" max="%s" step="any" value="%s" />'
        '<span class="unit">%s</span> <span class="value">%s %s</span></div>'
        % (
            _esc(parameter_name),
            _esc(props.get("title", parameter_name)),
            _esc(parameter_name),
            _fmt(low),
            _fmt(high),
            _fmt(value),
            _esc(unit),
            _fmt(value),
            _esc(unit),
        )
    )


def _render_number(bindings: Mapping[str, Any], props: Mapping[str, Any]) -> str:
    parameter_name = bindings.get("parameter", "?")
    unit = bindings.get("unit", "")
    value = bindings.get("value")
    step = "1" if isinstance(value, int) and not isinstance(value, bool) else "any"
    return (
        '<div class="control"><label for="f_%s">%s</label>'
        '<input type="number" id="f_%s" step="%s" value="%s" />'
        '<span class="unit">%s</span> <span class="value">%s %s</span></div>'
        % (
            _esc(parameter_name),
            _esc(props.get("title", parameter_name)),
            _esc(parameter_name),
            step,
            _fmt(value),
            _esc(unit),
            _fmt(value),
            _esc(unit),
        )
    )


def _render_choice(bindings: Mapping[str, Any], props: Mapping[str, Any]) -> str:
    parameter_name = bindings.get("parameter", "?")
    choices = bindings.get("choices") or []
    value = bindings.get("value")
    options = "".join(
        '<option value="%s"%s>%s</option>'
        % (_esc(choice), " selected" if choice == value else "", _esc(choice))
        for choice in choices
    )
    return (
        '<div class="control"><label for="f_%s">%s</label>'
        '<select id="f_%s">%s</select></div>'
        % (_esc(parameter_name), _esc(props.get("title", parameter_name)), _esc(parameter_name), options)
    )


def _render_axis(bindings: Mapping[str, Any], props: Mapping[str, Any]) -> str:
    return (
        "<p><strong>%s</strong></p><p class=\"unit\">%s</p>"
        % (_esc(props.get("label", "")), _esc(props.get("title", "")))
    )


def _render_button(
    bindings: Mapping[str, Any],
    props: Mapping[str, Any],
    live_enabled: bool = True,
    live_invalid: Optional[List[str]] = None,
) -> str:
    live_invalid = live_invalid or []
    # the button is enabled only when the strict layer says every field of
    # the *current* panel state is valid - the stored flag can never make an
    # invalid panel runnable
    enabled = bool(bindings.get("enabled")) and live_enabled and not live_invalid
    reason = props.get("disabled_reason") or (
        "invalid fields: %s" % ", ".join(live_invalid) if live_invalid else ""
    )
    return (
        '<button type="button"%s>%s</button>%s'
        % (
            "" if enabled else " disabled",
            _esc(props.get("title", "Run sweep")),
            ('<p class="nodata">%s</p>' % _esc(reason)) if reason else "",
        )
    )

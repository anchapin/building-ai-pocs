"""Panel generation: the catalog extension, the spec, the run button."""

import json

import pytest

import panel
import panel_catalog
import panel_renderer
import panel_spec
import schema

import panel_requests


def test_the_catalog_extension_adds_five_panel_primitives():
    """The Phase 1 six are reused; the five panel primitives are added."""
    assert set(panel_catalog.PANEL_PRIMITIVE_NAMES) == {
        "ParamSlider",
        "ParamNumber",
        "ChoiceSelect",
        "SweepAxis",
        "RunButton",
    }
    assert len(panel_catalog.PHASE1_PRIMITIVES) == 6
    assert len(panel_catalog.all_primitives()) == 11
    for name in panel_catalog.PANEL_PRIMITIVE_NAMES:
        assert panel_catalog.get_primitive(name) is not None


def test_every_request_builds_a_valid_panel():
    for entry in panel_requests.PANEL_REQUESTS:
        spec = panel.build_panel(entry["request"])
        assert not panel_catalog.is_refusal(spec), entry["id"]
        assert panel_spec.validate_panel_spec(spec) == [], entry["id"]
        axis = panel_spec.sweep_axis(spec)
        assert axis["parameter"] == entry["axis"]


def test_a_panel_exposes_the_whole_frozen_scoped_set():
    spec = panel.build_panel("sweep heating setpoint from 18 to 26 in 5 steps")
    controls = {
        component["bindings"]["parameter"]
        for component in spec["components"]
        if component["primitive"] in ("ParamSlider", "ParamNumber", "ChoiceSelect")
    }
    assert controls == set(schema.SCOPED_PARAMETER_NAMES)


def test_a_panel_carries_the_phase_1_spec_shape():
    """The document format is the Phase 1 one, not a fork of it."""
    spec = panel.build_panel("sweep heating setpoint from 18 to 26 in 5 steps")
    assert set(spec) <= set(panel_catalog.TOP_LEVEL_KEYS)
    for key in ("schema_version", "run_id", "request", "components"):
        assert key in spec
    for component in spec["components"]:
        assert set(component) <= set(panel_catalog.COMPONENT_KEYS)


def test_a_panel_may_not_widen_a_frozen_range():
    spec = panel.build_panel("sweep heating setpoint from 18 to 26 in 5 steps")
    broken = json.loads(json.dumps(spec))
    for component in broken["components"]:
        if component["primitive"] == "ParamSlider" and component["bindings"]["parameter"] == "heating_setpoint_c":
            component["bindings"]["max"] = 90.0
    errors = panel_spec.validate_panel_spec(broken)
    assert any(e["code"] == "range_mismatch" for e in errors)


def test_the_run_button_is_disabled_while_a_field_is_invalid():
    spec = panel.build_panel("sweep heating setpoint from 18 to 26 in 5 steps")
    assert panel_spec.run_button_enabled(spec) is True

    broken = json.loads(json.dumps(spec))
    for component in broken["components"]:
        if (
            component["primitive"] == "ParamSlider"
            and component["bindings"]["parameter"] == "cooling_setpoint_c"
        ):
            component["bindings"]["value"] = 15.0
    assert panel_spec.invalid_fields(broken) == ["cooling_setpoint_c"]
    assert panel_spec.run_button_enabled(broken) is False

    html = panel_renderer.render_panel(broken)
    assert "disabled" in html


def test_a_geometry_sweep_is_refused():
    spec = panel.build_panel("sweep zone area from 10 to 20 in 3 steps")
    assert panel_catalog.is_refusal(spec)
    assert spec["reason_code"] == "unknown_parameter"
    assert "structural" in spec["message"]


def test_an_unscoped_axis_is_refused():
    spec = panel.build_panel("sweep wall thickness from 0.1 to 0.5 in 3 steps")
    assert panel_catalog.is_refusal(spec)
    assert spec["reason_code"] == "unknown_parameter"


def test_a_request_without_a_sweep_is_refused():
    spec = panel.build_panel("show me the panel")
    assert panel_catalog.is_refusal(spec)
    assert spec["reason_code"] == "no_known_intent"


def test_the_assembler_is_deterministic():
    first = panel.build_panel("sweep cooling cop from 2.0 to 4.0 in 3 steps")
    second = panel.build_panel("sweep cooling cop from 2.0 to 4.0 in 3 steps")
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_the_renderer_is_deterministic():
    spec = panel.build_panel("sweep cooling cop from 2.0 to 4.0 in 3 steps")
    assert panel_renderer.render_panel(spec) == panel_renderer.render_panel(spec)

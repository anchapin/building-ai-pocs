"""The renderer: static HTML, deterministic, never invents data."""

import re

import manifest as manifest_mod
import renderer
import uispec


def _spec(components):
    return uispec.make_spec(
        run_id="run_ashrae140_case1",
        request="chart zone1 supply air temperature",
        components=components,
    )


def test_rendering_is_deterministic():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "TimeSeriesChart",
                "title": "zone1 air temperature",
                "bindings": {"series": "zone1_air_temperature", "unit": "°C"},
                "props": {"title": "zone1 air temperature"},
            }
        ]
    )
    first = renderer.render_spec(spec, run)
    second = renderer.render_spec(spec, run)
    assert first == second
    assert first.startswith("<!DOCTYPE html>")


def test_absent_binding_renders_no_data():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "TimeSeriesChart",
                "title": "nothing",
                "bindings": {"series": "zone1_supply_air_temperature", "unit": "°C"},
                "props": {},
            }
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "no data" in html


def test_a_field_without_values_renders_no_data():
    """zone1_supply_air_temperature is declared by the run but carries no values."""
    run = manifest_mod.load_run("run_ashrae140_case1")
    assert run["fields"]["zone1_supply_air_temperature"]["values"] == []
    spec = _spec(
        [
            {
                "primitive": "TimeSeriesChart",
                "title": "supply air",
                "bindings": {"series": "zone1_supply_air_temperature", "unit": "°C"},
                "props": {},
            }
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "no data" in html
    assert "<polyline" not in html


def test_unknown_primitive_renders_no_data():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec([{"primitive": "HeatMap", "title": "x", "bindings": {}, "props": {}}])
    html = renderer.render_spec(spec, run)
    assert "no data" in html


def test_diff_table_flags_an_out_of_range_value():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "DiffTable",
                "title": "zone1 air temperature",
                "bindings": {
                    "series": "zone1_air_temperature",
                    "unit": "°C",
                    "reference_min": 20.0,
                    "reference_max": 24.0,
                },
                "props": {"aggregation": "max"},
            }
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "out of range" in html
    assert "26.588" in html


def test_diff_table_shows_the_deviation_from_a_reference_series():
    run = manifest_mod.load_run("run_ground_coupled_case2")
    spec = uispec.make_spec(
        run_id="run_ground_coupled_case2",
        request="compare floor boundary temperature with the ground baseline",
        components=[
            {
                "primitive": "DiffTable",
                "title": "floor boundary temperature",
                "bindings": {
                    "series": "floor_boundary_temperature",
                    "unit": "°C",
                    "reference_min": 9.2,
                    "reference_max": 9.6,
                    "reference_series": "ground_baseline_temperature",
                },
                "props": {"aggregation": "last"},
            }
        ],
    )
    html = renderer.render_spec(spec, run)
    assert "9.4" in html
    # the deviation column carries a signed number (floor boundary vs baseline)
    assert re.search(r"[-+]\d+\.\d{4}", html)


def test_kpi_card_shows_the_scalar_and_unit():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "KPICard",
                "title": "total heating energy",
                "bindings": {"field": "total_heating_energy", "unit": "kWh"},
                "props": {"label": "total heating energy"},
            }
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "412.6" in html
    assert "kWh" in html


def test_log_tail_shows_the_last_lines():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "LogTail",
                "title": "run log",
                "bindings": {"log_field": "run_log", "count": 2},
                "props": {},
            }
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "writing result fields" in html
    assert "results written, status=ok" in html
    assert "run started" not in html


def test_zone_highlight_is_schematic_only():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "ZoneHighlight",
                "title": "zone1",
                "bindings": {
                    "zone_id": "zone1",
                    "series": "zone1_air_temperature",
                    "unit": "°C",
                },
                "props": {},
            }
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "zone1" in html
    assert "<svg" in html


def test_param_inspector_shows_inputs_and_provenance():
    run = manifest_mod.load_run("run_ashrae140_case1")
    spec = _spec(
        [
            {
                "primitive": "ParamInspector",
                "title": "run inputs",
                "bindings": {},
                "props": {"section": "inputs"},
            },
            {
                "primitive": "ParamInspector",
                "title": "run provenance",
                "bindings": {},
                "props": {"section": "provenance"},
            },
        ]
    )
    html = renderer.render_spec(spec, run)
    assert "heating_setpoint_c" in html
    assert "seed" in html


def test_spec_series_lists_the_bound_fields():
    spec = _spec(
        [
            {
                "primitive": "TimeSeriesChart",
                "title": "x",
                "bindings": {"series": "zone1_air_temperature", "unit": "°C"},
                "props": {},
            }
        ]
    )
    assert renderer.spec_series(spec) == ["zone1_air_temperature"]

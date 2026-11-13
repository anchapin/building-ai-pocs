"""The UI-spec validator must reject unknown primitives, fields and unit mismatches."""

import copy

import manifest as manifest_mod
import uispec

import pytest


@pytest.fixture()
def run():
    return manifest_mod.load_run("run_ashrae140_case1")


@pytest.fixture()
def man(run):
    return manifest_mod.manifest_from_run(run)


def _spec(**overrides):
    spec = {
        "schema_version": 1,
        "run_id": "run_ashrae140_case1",
        "request": "chart zone1 air temperature",
        "components": [
            {
                "primitive": "TimeSeriesChart",
                "title": "zone1 air temperature",
                "bindings": {"series": "zone1_air_temperature", "unit": "°C"},
                "props": {"x_axis_label": "sample"},
            }
        ],
    }
    spec.update(overrides)
    return spec


def test_valid_spec_has_no_errors(man):
    assert uispec.validate_spec(_spec(), man) == []
    assert uispec.spec_is_valid(_spec(), man)


def test_unknown_primitive_is_rejected(man):
    spec = _spec()
    spec["components"][0]["primitive"] = "HeatMap"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_primitive" in codes


def test_unknown_top_level_field_is_rejected(man):
    spec = _spec()
    spec["surprise"] = 1
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_field" in codes


def test_unknown_component_field_is_rejected(man):
    spec = _spec()
    spec["components"][0]["colour"] = "red"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_field" in codes


def test_unknown_prop_is_rejected(man):
    spec = _spec()
    spec["components"][0]["props"]["y_axis_label"] = "degC"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_prop" in codes


def test_unknown_binding_field_is_rejected(man):
    spec = _spec()
    spec["components"][0]["bindings"]["secondary"] = "zone2_air_temperature"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_binding_field" in codes


def test_missing_required_binding_is_rejected(man):
    spec = _spec()
    del spec["components"][0]["bindings"]["unit"]
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "missing_binding" in codes


def test_field_not_in_manifest_is_rejected(man):
    spec = _spec()
    spec["components"][0]["bindings"]["series"] = "zone9_air_temperature"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_field" in codes


def test_unit_mismatch_against_the_manifest_is_rejected(man):
    spec = _spec()
    spec["components"][0]["bindings"]["unit"] = "kW"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unit_mismatch" in codes


def test_unknown_unit_is_rejected(man):
    spec = _spec()
    spec["components"][0]["bindings"]["unit"] = "furlongs"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unknown_unit" in codes


def test_run_mismatch_is_rejected(man):
    spec = _spec(run_id="run_ground_coupled_case2")
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "run_mismatch" in codes


def test_bad_types_are_rejected(man):
    spec = _spec()
    spec["components"] = "not a list"
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "bad_type" in codes


def test_incomplete_reference_band_is_rejected(man):
    spec = _spec()
    spec["components"][0]["primitive"] = "DiffTable"
    spec["components"][0]["bindings"] = {
        "series": "zone1_air_temperature",
        "unit": "°C",
        "reference_min": 20.0,
    }
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "incomplete_reference" in codes


def test_reference_series_with_a_different_unit_is_rejected(man):
    spec = _spec()
    spec["components"][0]["primitive"] = "DiffTable"
    spec["components"][0]["bindings"] = {
        "series": "zone1_air_temperature",
        "unit": "°C",
        "reference_series": "total_heating_energy",
    }
    codes = [e["code"] for e in uispec.validate_spec(spec, man)]
    assert "unit_mismatch" in codes


def test_validator_never_repairs(man):
    """A rejected spec is reported, not silently fixed."""
    spec = _spec()
    spec["components"][0]["primitive"] = "HeatMap"
    errors = uispec.validate_spec(spec, man)
    assert errors
    assert spec["components"][0]["primitive"] == "HeatMap"


def test_refusal_object_shape():
    refusal = uispec.make_refusal("unknown_field", "nope")
    assert uispec.is_refusal(refusal)
    assert refusal["reason_code"] == "unknown_field"
    assert not uispec.is_refusal({"status": "ok"})

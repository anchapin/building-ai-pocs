"""The strict schema layer: the frozen scoped set and its rejections."""

import math

import pytest

import panel_catalog
import schema


def test_the_scoped_set_is_frozen_and_bounded():
    """12-15 parameters, each with a type, a unit, a range and a default."""
    assert 12 <= len(schema.FROZEN_SCOPED_PARAMETERS) <= 15
    for spec in schema.FROZEN_SCOPED_PARAMETERS:
        assert spec.name in schema.PARAMETERS
        assert spec.type in (schema.NUMBER, schema.INTEGER, schema.CHOICE)
        assert spec.unit
        if spec.type == schema.CHOICE:
            assert spec.choices
            assert spec.default in spec.choices
        else:
            assert spec.minimum is not None and spec.maximum is not None
            assert spec.minimum <= spec.default <= spec.maximum
        assert spec.evidence


def test_the_scoped_set_holds_no_geometry():
    """No geometric / structural parameter may be in the frozen set."""
    for spec in schema.FROZEN_SCOPED_PARAMETERS:
        assert spec.name not in schema.NON_SCOPED_GEOSTRUCTURE_NAMES
        for banned in ("area", "thickness", "geometry", "zone_count", "rotation"):
            assert banned not in spec.name


def test_an_unknown_parameter_is_refused():
    result = schema.validate_state({"zone_area_m2": {"value": 10.0, "unit": "m2"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "unknown_parameter"


def test_a_wrong_type_is_refused():
    result = schema.validate_state({"heating_setpoint_c": {"value": "21", "unit": "°C"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "bad_type"


def test_an_out_of_range_value_is_refused():
    result = schema.validate_state({"cooling_cop": {"value": -3.0, "unit": "1"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "out_of_range"
    assert "frozen minimum" in result.errors[0]["message"]


def test_a_unit_mismatch_is_refused():
    result = schema.validate_state({"heating_setpoint_c": {"value": 21.0, "unit": "kW"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "unit_mismatch"


def test_an_unknown_unit_is_refused():
    result = schema.validate_state({"heating_setpoint_c": {"value": 21.0, "unit": "lux"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "unknown_unit"


def test_a_missing_unit_is_refused():
    result = schema.validate_state({"internal_gain_w": {"value": 1200.0}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "missing_unit"


def test_a_non_finite_value_is_refused():
    result = schema.validate_state({"cooling_cop": {"value": float("nan"), "unit": "1"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "non_finite"


def test_an_unknown_choice_is_refused():
    result = schema.validate_state({"occupancy_schedule": {"value": "nope"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "bad_choice"


def test_an_extra_submission_field_is_refused():
    result = schema.validate_state(
        {"heating_setpoint_c": {"value": 21.0, "unit": "°C", "extra": 1}}, require_all=False
    )
    assert not result.ok
    assert result.errors[0]["code"] == "unknown_field"


def test_inconsistent_setpoints_are_refused():
    result = schema.validate_state(
        {
            "heating_setpoint_c": {"value": 21.0, "unit": "°C"},
            "cooling_setpoint_c": {"value": 20.0, "unit": "°C"},
        },
        require_all=False,
    )
    assert not result.ok
    assert any(e["code"] == "inconsistent_setpoints" for e in result.errors)


def test_an_imperial_submission_is_converted_explicitly():
    """The conversion is applied *and* shown - never silent."""
    result = schema.validate_state({"heating_setpoint_c": {"value": 68.0, "unit": "°F"}}, require_all=False)
    assert result.ok
    assert result.normalized["heating_setpoint_c"]["value"] == pytest.approx(20.0)
    assert result.normalized["heating_setpoint_c"]["unit"] == "°C"
    assert len(result.conversions) == 1
    conversion = result.conversions[0]
    assert conversion["submitted_unit"] == "°F"
    assert conversion["si_unit"] == "°C"
    assert conversion["formula"]


def test_a_fahrenheit_value_submitted_as_celsius_is_refused():
    result = schema.validate_state({"heating_setpoint_c": {"value": 68.0, "unit": "°C"}}, require_all=False)
    assert not result.ok
    assert result.errors[0]["code"] == "out_of_range"


def test_an_imperial_u_value_converts_and_is_range_checked():
    ok = schema.validate_state(
        {"window_u_value_w_m2k": {"value": 0.5, "unit": "Btu/h.ft2.F"}}, require_all=False
    )
    assert ok.ok
    assert ok.normalized["window_u_value_w_m2k"]["value"] == pytest.approx(2.83913, abs=1e-4)
    assert ok.conversions[0]["formula"]

    bad = schema.validate_state(
        {"window_u_value_w_m2k": {"value": 100.0, "unit": "Btu/h.ft2.F"}}, require_all=False
    )
    assert not bad.ok
    assert bad.errors[0]["code"] == "out_of_range"


def test_a_sweep_axis_outside_the_frozen_set_is_refused():
    errors = schema.validate_sweep_axis(
        {"parameter": "zone_area_m2", "min": 10.0, "max": 20.0, "steps": 3}
    )
    assert errors
    assert errors[0]["code"] == "unknown_parameter"


def test_a_sweep_axis_outside_the_frozen_range_is_refused():
    errors = schema.validate_sweep_axis(
        {"parameter": "heating_setpoint_c", "min": 5.0, "max": 40.0, "steps": 5}
    )
    assert errors
    assert errors[0]["code"] == "out_of_range"


def test_a_sweep_axis_on_an_enumerated_parameter_is_refused():
    errors = schema.validate_sweep_axis(
        {"parameter": "occupancy_schedule", "min": 1.0, "max": 4.0, "steps": 4}
    )
    assert errors
    assert errors[0]["code"] == "unsupported_axis_type"


def test_the_default_state_is_valid():
    result = schema.validate_state(schema.default_state())
    assert result.ok, result.errors
    assert len(result.normalized) == len(schema.FROZEN_SCOPED_PARAMETERS)

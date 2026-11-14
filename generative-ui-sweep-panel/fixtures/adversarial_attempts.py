"""The adversarial set for the sweep panel (issue #38, done-definition item 4).

Every entry is an *attempt* to get something invalid through the write path.
Every one of them must be rejected by the strict schema layer with a
readable reason; the harness prints each rejection verbatim.

``kind``:

* ``"state"``  - a panel submission (parameter -> {"value", "unit"}),
* ``"axis"``   - a sweep axis ({"parameter", "min", "max", "steps"}),
* ``"raw"``    - a submission that is not even an object.

``expected`` is the rejection code the harness expects; a different code is
reported as a failure with the actual message.
"""

from __future__ import annotations

ADVERSARIAL_ATTEMPTS = [
    {
        "id": "adv01_negative_cop",
        "description": "negative cooling COP (a COP below 1 is unphysical)",
        "kind": "state",
        "submission": {"cooling_cop": {"value": -3.0, "unit": "1"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv02_cop_above_max",
        "description": "cooling COP above the frozen maximum",
        "kind": "state",
        "submission": {"cooling_cop": {"value": 9.0, "unit": "1"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv03_sub_absolute_zero_celsius",
        "description": "a temperature below absolute zero, submitted in °C",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": -273.15, "unit": "°C"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv04_sub_absolute_zero_kelvin",
        "description": "a temperature below absolute zero, submitted in K",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": -300.0, "unit": "K"}},
        "expected": "unit_mismatch",
    },
    {
        "id": "adv05_u_value_zero",
        "description": "window U-value of 0 (no heat flow at all)",
        "kind": "state",
        "submission": {"window_u_value_w_m2k": {"value": 0.0, "unit": "W/m2.K"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv06_u_value_ten_x",
        "description": "window U-value ten times the frozen maximum",
        "kind": "state",
        "submission": {"window_u_value_w_m2k": {"value": 22.0, "unit": "W/m2.K"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv07_unscoped_parameter",
        "description": "an unscoped parameter (zone floor area)",
        "kind": "state",
        "submission": {"zone_area_m2": {"value": 120.0, "unit": "m2"}},
        "expected": "unknown_parameter",
    },
    {
        "id": "adv08_unscoped_parameter_2",
        "description": "another unscoped parameter (solar panel area)",
        "kind": "state",
        "submission": {"solar_panel_area_m2": {"value": 12.0, "unit": "m2"}},
        "expected": "unknown_parameter",
    },
    {
        "id": "adv09_fahrenheit_value_as_celsius",
        "description": "a °F value submitted as °C (68 °F labelled °C)",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": 68.0, "unit": "°C"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv10_string_value",
        "description": "a string where a number is required",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": "21", "unit": "°C"}},
        "expected": "bad_type",
    },
    {
        "id": "adv11_boolean_value",
        "description": "a boolean where a number is required",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": True, "unit": "°C"}},
        "expected": "bad_type",
    },
    {
        "id": "adv12_wrong_dimension_unit",
        "description": "a temperature parameter submitted in kW",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": 21.0, "unit": "kW"}},
        "expected": "unit_mismatch",
    },
    {
        "id": "adv13_unknown_unit",
        "description": "a unit the strict layer cannot check (lux on a °C parameter)",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": 21.0, "unit": "lux"}},
        "expected": "unknown_unit",
    },
    {
        "id": "adv13b_imperial_unit_wrong_quantity",
        "description": "an imperial unit of a different quantity (Btu/h on a °C parameter)",
        "kind": "state",
        "submission": {"heating_setpoint_c": {"value": 21.0, "unit": "BTU/h"}},
        "expected": "unit_mismatch",
    },
    {
        "id": "adv14_missing_unit",
        "description": "a numeric submission with no unit at all",
        "kind": "state",
        "submission": {"internal_gain_w": {"value": 1200.0}},
        "expected": "missing_unit",
    },
    {
        "id": "adv15_fractional_integer",
        "description": "a fractional value for an integer parameter",
        "kind": "state",
        "submission": {"simulation_hours": {"value": 8760.5, "unit": "h"}},
        "expected": "bad_type",
    },
    {
        "id": "adv16_negative_infiltration",
        "description": "a negative infiltration rate",
        "kind": "state",
        "submission": {"infiltration_ach": {"value": -0.5, "unit": "1/h"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv17_absorptance_above_one",
        "description": "a solar absorptance above 1",
        "kind": "state",
        "submission": {"solar_absorptance": {"value": 1.2, "unit": "1"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv18_negative_internal_gain",
        "description": "a negative internal gain",
        "kind": "state",
        "submission": {"internal_gain_w": {"value": -100.0, "unit": "W"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv19_zero_capacity",
        "description": "a heating capacity of zero",
        "kind": "state",
        "submission": {"heating_capacity_kw": {"value": 0.0, "unit": "kW"}},
        "expected": "out_of_range",
    },
    {
        "id": "adv20_unknown_choice",
        "description": "a choice value outside the frozen choice list",
        "kind": "state",
        "submission": {"occupancy_schedule": {"value": "weekend_shutdown"}},
        "expected": "bad_choice",
    },
    {
        "id": "adv21_geometry_sweep_attempt",
        "description": "a sweep along a geometric parameter (zone floor area)",
        "kind": "axis",
        "axis": {"parameter": "zone_area_m2", "min": 50.0, "max": 200.0, "steps": 4},
        "expected": "unknown_parameter",
    },
    {
        "id": "adv22_structure_sweep_attempt",
        "description": "a sweep along a structural parameter (wall thickness)",
        "kind": "axis",
        "axis": {"parameter": "wall_thickness_m", "min": 0.1, "max": 0.5, "steps": 3},
        "expected": "unknown_parameter",
    },
    {
        "id": "adv23_inconsistent_setpoints",
        "description": "a cooling setpoint below the heating setpoint",
        "kind": "state",
        "submission": {
            "heating_setpoint_c": {"value": 21.0, "unit": "°C"},
            "cooling_setpoint_c": {"value": 20.0, "unit": "°C"},
        },
        "expected": "inconsistent_setpoints",
    },
    {
        "id": "adv24_unknown_submission_field",
        "description": "a submission carrying an extra field",
        "kind": "state",
        "submission": {
            "heating_setpoint_c": {"value": 21.0, "unit": "°C", "note": "sneaky"}
        },
        "expected": "unknown_field",
    },
    {
        "id": "adv25_not_a_number",
        "description": "a NaN value",
        "kind": "state",
        "submission": {"cooling_cop": {"value": float("nan"), "unit": "1"}},
        "expected": "non_finite",
    },
    {
        "id": "adv26_axis_out_of_range",
        "description": "a sweep axis wider than the frozen range of the parameter",
        "kind": "axis",
        "axis": {"parameter": "heating_setpoint_c", "min": 5.0, "max": 40.0, "steps": 5},
        "expected": "out_of_range",
    },
    {
        "id": "adv27_axis_min_above_max",
        "description": "a sweep axis whose min is above its max",
        "kind": "axis",
        "axis": {"parameter": "heating_setpoint_c", "min": 30.0, "max": 10.0, "steps": 5},
        "expected": "bad_axis",
    },
    {
        "id": "adv28_axis_single_step",
        "description": "a sweep axis with a single step",
        "kind": "axis",
        "axis": {"parameter": "heating_setpoint_c", "min": 18.0, "max": 26.0, "steps": 1},
        "expected": "bad_axis",
    },
    {
        "id": "adv29_imperial_value_out_of_range",
        "description": "an imperial submission whose explicit conversion leaves the range",
        "kind": "state",
        "submission": {
            "window_u_value_w_m2k": {"value": 100.0, "unit": "Btu/h.ft2.F"}
        },
        "expected": "out_of_range",
    },
    {
        "id": "adv30_axis_choice_parameter",
        "description": "a sweep axis on an enumerated parameter",
        "kind": "axis",
        "axis": {"parameter": "occupancy_schedule", "min": 1.0, "max": 4.0, "steps": 4},
        "expected": "unsupported_axis_type",
    },
    {
        "id": "adv31_submission_not_an_object",
        "description": "a submission that is not an object at all",
        "kind": "raw",
        "submission": ["heating_setpoint_c", 21.0],
        "expected": "bad_type",
    },
    {
        "id": "adv32_unscoped_parameter_shadowing",
        "description": "a plausible-looking but unscoped parameter name",
        "kind": "state",
        "submission": {"heating_setpoint": {"value": 21.0, "unit": "°C"}},
        "expected": "unknown_parameter",
    },
]

"""Hand-written configurations for the equivalence harness (issue #38).

These are written **by hand**, as literals, *before* the panel-generated
configurations they are compared against: they are the reference, not a
copy of the output.  The harness compares the two byte for byte (canonical
JSON: sorted keys, two-space indent, UTF-8).

Each configuration is the scoped-measure block of one sweep:

* ``sweep``  - the axis the sweep runs along,
* ``inputs`` - every parameter of the frozen scoped set, in SI units.

The default values below are the frozen defaults of
``generative-ui-sweep-panel/schema.py``; sweep ``sweep_heating_setpoint_c``
carries a non-default value (20.0 °C), because that sweep submits
``68 °F`` and the strict layer converts it explicitly to 20.0 °C.
"""

from __future__ import annotations

#: sweep 1 - heating setpoint, submitted as 68 °F -> 20.0 °C
SWEEP_HEATING_SETPOINT = {
    "schema_version": 1,
    "case_id": "sweep_heating_setpoint_c",
    "sweep": {
        "parameter": "heating_setpoint_c",
        "min": 18.0,
        "max": 26.0,
        "steps": 5,
        "unit": "°C",
    },
    "inputs": {
        "heating_setpoint_c": 20.0,
        "heating_setpoint_unoccupied_c": 17.0,
        "cooling_setpoint_c": 24.5,
        "cooling_setpoint_unoccupied_c": 28.0,
        "infiltration_ach": 0.35,
        "internal_gain_w": 1200.0,
        "window_u_value_w_m2k": 2.2,
        "wall_u_value_w_m2k": 0.35,
        "roof_u_value_w_m2k": 0.15,
        "cooling_cop": 3.2,
        "heating_efficiency": 0.85,
        "solar_absorptance": 0.6,
        "heating_capacity_kw": 8.0,
        "simulation_hours": 8760,
        "occupancy_schedule": "office_standard",
    },
}

#: sweep 2 - cooling setpoint, all other values at their frozen defaults
SWEEP_COOLING_SETPOINT = {
    "schema_version": 1,
    "case_id": "sweep_cooling_setpoint_c",
    "sweep": {
        "parameter": "cooling_setpoint_c",
        "min": 22.0,
        "max": 28.0,
        "steps": 4,
        "unit": "°C",
    },
    "inputs": {
        "heating_setpoint_c": 21.0,
        "heating_setpoint_unoccupied_c": 17.0,
        "cooling_setpoint_c": 24.5,
        "cooling_setpoint_unoccupied_c": 28.0,
        "infiltration_ach": 0.35,
        "internal_gain_w": 1200.0,
        "window_u_value_w_m2k": 2.2,
        "wall_u_value_w_m2k": 0.35,
        "roof_u_value_w_m2k": 0.15,
        "cooling_cop": 3.2,
        "heating_efficiency": 0.85,
        "solar_absorptance": 0.6,
        "heating_capacity_kw": 8.0,
        "simulation_hours": 8760,
        "occupancy_schedule": "office_standard",
    },
}

#: sweep 3 - infiltration air-change rate
SWEEP_INFILTRATION = {
    "schema_version": 1,
    "case_id": "sweep_infiltration_ach",
    "sweep": {
        "parameter": "infiltration_ach",
        "min": 0.1,
        "max": 1.0,
        "steps": 5,
        "unit": "1/h",
    },
    "inputs": {
        "heating_setpoint_c": 21.0,
        "heating_setpoint_unoccupied_c": 17.0,
        "cooling_setpoint_c": 24.5,
        "cooling_setpoint_unoccupied_c": 28.0,
        "infiltration_ach": 0.35,
        "internal_gain_w": 1200.0,
        "window_u_value_w_m2k": 2.2,
        "wall_u_value_w_m2k": 0.35,
        "roof_u_value_w_m2k": 0.15,
        "cooling_cop": 3.2,
        "heating_efficiency": 0.85,
        "solar_absorptance": 0.6,
        "heating_capacity_kw": 8.0,
        "simulation_hours": 8760,
        "occupancy_schedule": "office_standard",
    },
}

#: sweep 4 - window U-value
SWEEP_WINDOW_U_VALUE = {
    "schema_version": 1,
    "case_id": "sweep_window_u_value_w_m2k",
    "sweep": {
        "parameter": "window_u_value_w_m2k",
        "min": 1.0,
        "max": 3.0,
        "steps": 3,
        "unit": "W/m2.K",
    },
    "inputs": {
        "heating_setpoint_c": 21.0,
        "heating_setpoint_unoccupied_c": 17.0,
        "cooling_setpoint_c": 24.5,
        "cooling_setpoint_unoccupied_c": 28.0,
        "infiltration_ach": 0.35,
        "internal_gain_w": 1200.0,
        "window_u_value_w_m2k": 2.2,
        "wall_u_value_w_m2k": 0.35,
        "roof_u_value_w_m2k": 0.15,
        "cooling_cop": 3.2,
        "heating_efficiency": 0.85,
        "solar_absorptance": 0.6,
        "heating_capacity_kw": 8.0,
        "simulation_hours": 8760,
        "occupancy_schedule": "office_standard",
    },
}

#: sweep 5 - cooling COP
SWEEP_COOLING_COP = {
    "schema_version": 1,
    "case_id": "sweep_cooling_cop",
    "sweep": {
        "parameter": "cooling_cop",
        "min": 2.0,
        "max": 4.0,
        "steps": 3,
        "unit": "1",
    },
    "inputs": {
        "heating_setpoint_c": 21.0,
        "heating_setpoint_unoccupied_c": 17.0,
        "cooling_setpoint_c": 24.5,
        "cooling_setpoint_unoccupied_c": 28.0,
        "infiltration_ach": 0.35,
        "internal_gain_w": 1200.0,
        "window_u_value_w_m2k": 2.2,
        "wall_u_value_w_m2k": 0.35,
        "roof_u_value_w_m2k": 0.15,
        "cooling_cop": 3.2,
        "heating_efficiency": 0.85,
        "solar_absorptance": 0.6,
        "heating_capacity_kw": 8.0,
        "simulation_hours": 8760,
        "occupancy_schedule": "office_standard",
    },
}

#: the reference configurations, in the order the harness runs them
HANDWRITTEN_CONFIGS = (
    ("sweep_heating_setpoint_c", SWEEP_HEATING_SETPOINT),
    ("sweep_cooling_setpoint_c", SWEEP_COOLING_SETPOINT),
    ("sweep_infiltration_ach", SWEEP_INFILTRATION),
    ("sweep_window_u_value_w_m2k", SWEEP_WINDOW_U_VALUE),
    ("sweep_cooling_cop", SWEEP_COOLING_COP),
)

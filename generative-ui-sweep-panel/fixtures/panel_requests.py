"""The representative panel requests used by the harness (issue #38).

Each entry is a plain-language request the assembler must turn into a
panel spec.  The set covers every control primitive of the panel and every
kind of scoped parameter (continuous, numeric, integer).
"""

from __future__ import annotations

PANEL_REQUESTS = (
    {
        "id": "req01",
        "request": "sweep heating setpoint from 18 to 26 in 5 steps",
        "axis": "heating_setpoint_c",
    },
    {
        "id": "req02",
        "request": "sweep cooling setpoint from 22 to 28 in 4 steps",
        "axis": "cooling_setpoint_c",
    },
    {
        "id": "req03",
        "request": "sweep infiltration from 0.1 to 1.0 in 5 steps",
        "axis": "infiltration_ach",
    },
    {
        "id": "req04",
        "request": "sweep window u value from 1.0 to 3.0 in 3 steps",
        "axis": "window_u_value_w_m2k",
    },
    {
        "id": "req05",
        "request": "sweep cooling cop from 2.0 to 4.0 in 3 steps",
        "axis": "cooling_cop",
    },
    {
        "id": "req06",
        "request": "sweep wall u value from 0.2 to 0.6 in 3 steps",
        "axis": "wall_u_value_w_m2k",
    },
    {
        "id": "req07",
        "request": "sweep roof u value from 0.1 to 0.3 in 3 steps",
        "axis": "roof_u_value_w_m2k",
    },
    {
        "id": "req08",
        "request": "sweep internal gain from 600 to 2400 in 5 steps",
        "axis": "internal_gain_w",
    },
    {
        "id": "req09",
        "request": "sweep heating capacity from 4 to 16 in 4 steps",
        "axis": "heating_capacity_kw",
    },
    {
        "id": "req10",
        "request": "sweep simulation hours from 24 to 8760 in 4 steps",
        "axis": "simulation_hours",
    },
    {
        "id": "req11",
        "request": "sweep unoccupied heating setpoint from 10 to 20 in 3 steps",
        "axis": "heating_setpoint_unoccupied_c",
    },
    {
        "id": "req12",
        "request": "sweep solar absorptance from 0.3 to 0.9 in 4 steps",
        "axis": "solar_absorptance",
    },
    {
        "id": "req13",
        "request": "sweep heating efficiency from 0.7 to 0.95 in 3 steps",
        "axis": "heating_efficiency",
    },
    {
        "id": "req14",
        "request": "sweep unoccupied cooling setpoint from 24 to 32 in 3 steps",
        "axis": "cooling_setpoint_unoccupied_c",
    },
)

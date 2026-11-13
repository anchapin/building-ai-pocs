#!/usr/bin/env python3
"""Generator for the three seeded run-output fixtures and their ground truth.

Run with:

    python3 generative-ui-diagnostic-lens/fixtures/gen_fixtures.py

It writes (deterministically, same bytes on every run):

    fixtures/runs/run_ashrae140_case1.json
    fixtures/runs/run_ground_coupled_case2.json
    fixtures/runs/run_humid_latent_case3.json
    fixtures/ground_truth/case1_ashrae140.ground_truth.json
    fixtures/ground_truth/case2_ground_coupled.ground_truth.json
    fixtures/ground_truth/case3_humid_latent.ground_truth.json

The ground-truth files are written FIRST, before the run outputs they
describe, and their diagnosis text is hand-written here (it is *not*
derived from the assembler, the renderer or any measurement).  The
assembler is a separate module and never reads the ground truth.

The run outputs are shaped after the Fluxion ``results.json`` premise of
issue #37 (run id, status, solver block, inputs, provenance, log lines and
a table of result fields).  They are SYNTHETIC fixtures: no Fluxion run
was executed to produce them.

Units in this file: temperatures degC, powers W/kW, energy kWh, humidity %RH.
"""

from __future__ import annotations

import json
import math
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
RUN_DIR = os.path.join(HERE, "runs")
GROUND_TRUTH_DIR = os.path.join(HERE, "ground_truth")

HOURS = 24


def _r(value: float, digits: int = 3) -> float:
    return round(value + 0.0, digits)


def _write(path: str, payload: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True, ensure_ascii=False)
        handle.write("\n")


# --------------------------------------------------------------------------
# ground truth (written first, by hand)
# --------------------------------------------------------------------------

def ground_truths() -> list:
    """The frozen diagnoses.  Hand-written, written before the run outputs."""
    return [
        {
            "case_id": "case1_ashrae140",
            "run_id": "run_ashrae140_case1",
            "title": "ASHRAE-140-style case with one perturbed input",
            "frozen": True,
            "written_before_assembler": True,
            "perturbation": {
                "input": "heating_setpoint_c",
                "reference_value": 20.0,
                "perturbed_value": 24.0,
                "unit": "degC",
                "applied_at_hour": 8,
                "note": (
                    "The heating setpoint input was raised by 4.0 K at hour 8 "
                    "and held there for the rest of the run."
                ),
            },
            "diagnosis": (
                "Zone 1 air temperature leaves its reference band from hour 9 "
                "onwards because the heating setpoint input was perturbed from "
                "20.0 degC to 24.0 degC at hour 8: zone1_air_temperature rises "
                "to 26.588 degC at hour 23 while the reference band is "
                "20.0..24.0 degC. Zone 2 air temperature stays inside the band "
                "over the same window (20.976..22.001 degC), so the excursion "
                "is local to the zone driven by the perturbed input, not a "
                "global shift of the run."
            ),
            "key_fields": ["zone1_air_temperature", "zone2_air_temperature"],
            "supporting_fields": ["total_heating_energy"],
            "expected_observations": {
                "zone1_air_temperature_max": 26.588,
                "zone1_air_temperature_reference_max": 24.0,
                "zone1_air_temperature_out_of_range": True,
                "zone2_air_temperature_min": 20.976,
                "zone2_air_temperature_max": 22.001,
                "zone2_air_temperature_out_of_range": False,
                "first_out_of_range_hour": 9,
            },
        },
        {
            "case_id": "case2_ground_coupled",
            "run_id": "run_ground_coupled_case2",
            "title": "Ground-coupled floor, boundary temperature vs a 9.4 degC baseline",
            "frozen": True,
            "written_before_assembler": True,
            "perturbation": {
                "input": None,
                "note": "No input is perturbed in this case; it is a baseline case.",
            },
            "diagnosis": (
                "The ground-coupled floor is behaving as a large, nearly "
                "constant thermal sink: floor_boundary_temperature stays within "
                "0.162 K of the constant 9.4 degC ground baseline "
                "(ground_baseline_temperature) for all 24 samples (9.240..9.562 "
                "degC), while zone1_air_temperature stays at 20.411..21.601 "
                "degC, inside its own band. The diagnosis lives in the "
                "floor-boundary series compared against the 9.4 degC baseline, "
                "not in the zone air temperature."
            ),
            "key_fields": ["floor_boundary_temperature", "ground_baseline_temperature"],
            "supporting_fields": ["zone1_air_temperature"],
            "expected_observations": {
                "baseline_value": 9.4,
                "floor_boundary_temperature_max_abs_deviation": 0.162,
                "floor_boundary_temperature_min": 9.24,
                "floor_boundary_temperature_max": 9.562,
                "floor_boundary_temperature_out_of_band": False,
                "zone1_air_temperature_out_of_range": False,
            },
        },
        {
            "case_id": "case3_humid_latent",
            "run_id": "run_humid_latent_case3",
            "title": "Humid-climate latent load; the signal is moisture, not temperature",
            "frozen": True,
            "written_before_assembler": True,
            "perturbation": {
                "input": None,
                "note": "No input is perturbed in this case; it is a baseline case.",
            },
            "diagnosis": (
                "The anomaly in this run is a moisture/latent one: "
                "zone1_relative_humidity climbs from 55.054 %RH to 77.920 %RH "
                "and leaves its 40..70 %RH reference band from hour 16 onwards, "
                "while zone1_latent_load rises with it from 118.251 W to "
                "413.815 W. The dry-bulb signal zone1_air_temperature stays "
                "within 1.249 K of 24 degC over the same window "
                "(22.751..25.193 degC), so a diagnosis built on temperature "
                "alone would miss the excursion."
            ),
            "key_fields": ["zone1_relative_humidity", "zone1_latent_load"],
            "supporting_fields": ["zone1_air_temperature"],
            "expected_observations": {
                "zone1_relative_humidity_max": 77.92,
                "zone1_relative_humidity_reference_max": 70.0,
                "zone1_relative_humidity_out_of_range": True,
                "first_out_of_range_hour": 16,
                "zone1_latent_load_max": 413.815,
                "zone1_air_temperature_max_abs_deviation_from_24": 1.249,
            },
        },
    ]


# --------------------------------------------------------------------------
# run outputs
# --------------------------------------------------------------------------

def _log_lines(prefix: str) -> list:
    return [
        "%s: run started, seed=14001" % prefix,
        "%s: reading input table (6 entries)" % prefix,
        "%s: solver block: initialising" % prefix,
        "%s: solver block: converged in 24 steps" % prefix,
        "%s: writing result fields" % prefix,
        "%s: results written, status=ok" % prefix,
    ]


def case1_run() -> dict:
    rng = random.Random(14001)
    zone1 = []
    zone2 = []
    for h in range(HOURS):
        if h < 8:
            zone1.append(_r(21.0 + 0.4 * math.sin(h / 3.0) + rng.uniform(-0.05, 0.05)))
        else:
            zone1.append(_r(24.0 + 2.6 * (h - 8) / 15.0 + rng.uniform(-0.05, 0.05)))
        zone2.append(_r(21.5 + 0.5 * math.sin((h + 2) / 4.0) + rng.uniform(-0.05, 0.05)))
    return {
        "run_id": "run_ashrae140_case1",
        "run_name": "ASHRAE-140-style case 1 (perturbed heating setpoint)",
        "status": "ok",
        "solver": {"name": "fixture-solver", "iterations": 24, "converged": True},
        "inputs": {
            "heating_setpoint_c": 24.0,
            "outdoor_temperature_c": 6.0,
            "internal_gain_w": 1200.0,
            "infiltration_ach": 0.35,
            "zone_count": 2,
            "run_hours": HOURS,
        },
        "provenance": {
            "fixture": "gen_fixtures.py",
            "seed": "14001",
            "reference": "ASHRAE-140-style",
            "step0_source": "in-folder fixture (no live Fluxion run)",
        },
        "fields": {
            "zone1_air_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": {"min": 20.0, "max": 24.0},
                "values": zone1,
            },
            "zone2_air_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": {"min": 20.0, "max": 24.0},
                "values": zone2,
            },
            "zone1_supply_air_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": None,
                "values": [],
            },
            "total_heating_energy": {
                "unit": "kWh",
                "kind": "scalar",
                "reference_range": None,
                "value": 412.6,
            },
            "run_log": {
                "unit": None,
                "kind": "log",
                "reference_range": None,
                "values": _log_lines("case1"),
            },
        },
    }


def case2_run() -> dict:
    rng = random.Random(90210)
    floor = []
    baseline = []
    zone = []
    for h in range(HOURS):
        floor.append(_r(9.4 + 0.15 * math.sin(2.0 * math.pi * h / HOURS) + rng.uniform(-0.02, 0.02)))
        baseline.append(9.4)
        zone.append(_r(21.0 + 0.6 * math.sin((h + 1) / 5.0) + rng.uniform(-0.05, 0.05)))
    return {
        "run_id": "run_ground_coupled_case2",
        "run_name": "Ground-coupled floor case (9.4 degC baseline)",
        "status": "ok",
        "solver": {"name": "fixture-solver", "iterations": 24, "converged": True},
        "inputs": {
            "ground_coupling": "adiabatic_slab_9p4C",
            "ground_baseline_c": 9.4,
            "slab_thickness_m": 0.3,
            "zone_count": 1,
            "run_hours": HOURS,
        },
        "provenance": {
            "fixture": "gen_fixtures.py",
            "seed": "90210",
            "reference": "ground-coupled floor style",
            "step0_source": "in-folder fixture (no live Fluxion run)",
        },
        "fields": {
            "floor_boundary_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": {"min": 9.2, "max": 9.6},
                "values": floor,
            },
            "ground_baseline_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": {"min": 9.4, "max": 9.4},
                "values": baseline,
            },
            "zone1_air_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": {"min": 20.0, "max": 26.0},
                "values": zone,
            },
            "total_heating_energy": {
                "unit": "kWh",
                "kind": "scalar",
                "reference_range": None,
                "value": 305.1,
            },
            "run_log": {
                "unit": None,
                "kind": "log",
                "reference_range": None,
                "values": _log_lines("case2"),
            },
        },
    }


def case3_run() -> dict:
    rng = random.Random(31415)
    rh = []
    latent = []
    temp = []
    for h in range(HOURS):
        rh.append(_r(55.0 + 23.0 * (h / 23.0) + rng.uniform(-0.3, 0.3)))
        latent.append(_r(120.0 + 290.0 * (h / 23.0) + rng.uniform(-4.0, 4.0)))
        temp.append(_r(24.0 + 1.2 * math.sin((h + 3) / 4.0) + rng.uniform(-0.05, 0.05)))
    return {
        "run_id": "run_humid_latent_case3",
        "run_name": "Humid-climate latent-load case (moisture signal)",
        "status": "ok",
        "solver": {"name": "fixture-solver", "iterations": 24, "converged": True},
        "inputs": {
            "outdoor_humidity_ratio": 0.019,
            "outdoor_temperature_c": 31.0,
            "latent_fraction": 0.42,
            "zone_count": 1,
            "run_hours": HOURS,
        },
        "provenance": {
            "fixture": "gen_fixtures.py",
            "seed": "31415",
            "reference": "humid-climate latent load style",
            "step0_source": "in-folder fixture (no live Fluxion run)",
        },
        "fields": {
            "zone1_relative_humidity": {
                "unit": "%RH",
                "kind": "series",
                "reference_range": {"min": 40.0, "max": 70.0},
                "values": rh,
            },
            "zone1_latent_load": {
                "unit": "W",
                "kind": "series",
                "reference_range": None,
                "values": latent,
            },
            "zone1_air_temperature": {
                "unit": "°C",
                "kind": "series",
                "reference_range": {"min": 20.0, "max": 26.0},
                "values": temp,
            },
            "total_cooling_energy": {
                "unit": "kWh",
                "kind": "scalar",
                "reference_range": None,
                "value": 980.4,
            },
            "run_log": {
                "unit": None,
                "kind": "log",
                "reference_range": None,
                "values": _log_lines("case3"),
            },
        },
    }


def main() -> int:
    truths = ground_truths()
    # ground truth FIRST
    for truth in truths:
        _write(
            os.path.join(GROUND_TRUTH_DIR, "%s.ground_truth.json" % truth["case_id"]),
            truth,
        )
    # then the run outputs the truth describes
    for run in (case1_run(), case2_run(), case3_run()):
        _write(os.path.join(RUN_DIR, "%s.json" % run["run_id"]), run)
    print("wrote %d ground-truth files and %d run fixtures" % (len(truths), 3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

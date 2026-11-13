"""The fixtures are seeded, reproducible and matched by their frozen ground truth."""

import json
import os
import sys

import manifest as manifest_mod

import pytest


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "fixtures"))
import gen_fixtures  # noqa: E402


def test_generator_output_matches_the_checked_in_fixtures():
    """Regenerating the fixtures yields exactly the checked-in documents."""
    for run in (gen_fixtures.case1_run(), gen_fixtures.case2_run(), gen_fixtures.case3_run()):
        path = os.path.join(HERE, "fixtures", "runs", "%s.json" % run["run_id"])
        with open(path, "r", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        assert on_disk == run


def test_ground_truth_matches_the_generator():
    for truth in gen_fixtures.ground_truths():
        path = os.path.join(
            HERE, "fixtures", "ground_truth", "%s.ground_truth.json" % truth["case_id"]
        )
        with open(path, "r", encoding="utf-8") as handle:
            on_disk = json.load(handle)
        assert on_disk == truth


def test_the_generator_is_deterministic():
    assert gen_fixtures.case1_run() == gen_fixtures.case1_run()
    assert gen_fixtures.case2_run() == gen_fixtures.case2_run()
    assert gen_fixtures.case3_run() == gen_fixtures.case3_run()


def test_case1_records_the_perturbation_as_ground_truth():
    truth = manifest_mod.load_ground_truth("case1_ashrae140")
    perturbation = truth["perturbation"]
    assert perturbation["input"] == "heating_setpoint_c"
    assert perturbation["reference_value"] == 20.0
    assert perturbation["perturbed_value"] == 24.0
    run = manifest_mod.load_run("run_ashrae140_case1")
    assert run["inputs"]["heating_setpoint_c"] == 24.0
    values = run["fields"]["zone1_air_temperature"]["values"]
    assert max(values) > 24.0


def test_case2_has_a_constant_9p4_degc_baseline():
    truth = manifest_mod.load_ground_truth("case2_ground_coupled")
    assert truth["expected_observations"]["baseline_value"] == 9.4
    run = manifest_mod.load_run("run_ground_coupled_case2")
    baseline = run["fields"]["ground_baseline_temperature"]["values"]
    assert set(baseline) == {9.4}
    floor = run["fields"]["floor_boundary_temperature"]["values"]
    assert max(abs(v - 9.4) for v in floor) < 0.2


def test_case3_is_a_moisture_case_not_a_temperature_case():
    truth = manifest_mod.load_ground_truth("case3_humid_latent")
    run = manifest_mod.load_run("run_humid_latent_case3")
    assert run["fields"]["zone1_relative_humidity"]["unit"] == "%RH"
    assert run["fields"]["zone1_latent_load"]["unit"] == "W"
    assert "humidity" in truth["diagnosis"].lower()
    assert "latent" in truth["diagnosis"].lower()


def test_ground_truth_key_fields_exist_in_the_run():
    for truth in gen_fixtures.ground_truths():
        run = manifest_mod.load_run(truth["run_id"])
        for name in truth["key_fields"]:
            assert name in run["fields"]

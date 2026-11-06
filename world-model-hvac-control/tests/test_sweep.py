"""Tests for the slice-2 multi-seed sweep (``run_sweep.py``).

The end-to-end test is deliberately tiny (200 training steps, one seed, the
``baeda_3dem`` smoke building): it pins the sweep's JSON schema and the
three-controller evaluation, not the slice-2 headline numbers -- those come
from the real sweep run, whose output is recorded in ``REPORT.md``.
"""

import json
import os
import subprocess
import sys

import pytest

from run_sweep import build_parser, evaluate_constant


def test_parser_defaults_and_overrides():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.dataset == "baeda_3dem"
    assert args.building == "Building_1"
    assert args.timesteps == 10000
    assert args.seeds == "0,1,2"
    assert args.eval_start_step == 0
    assert args.eval_episode_steps == 168
    assert args.eval_on == []

    args = parser.parse_args(
        [
            "--dataset",
            "tx_travis_county_neighborhood",
            "--building",
            "resstock-amy2018-2021-release-1-102188",
            "--seeds",
            "0,1,2",
            "--eval-start-step",
            "4368",
            "--eval-on",
            "vt_chittenden_county_neighborhood:resstock-amy2018-2021-release-1-112208",
        ]
    )
    assert args.dataset == "tx_travis_county_neighborhood"
    assert args.seeds == "0,1,2"
    assert args.eval_start_step == 4368
    assert args.eval_on == [
        "vt_chittenden_county_neighborhood:resstock-amy2018-2021-release-1-112208"
    ]


def test_evaluate_constant_do_nothing(dataset_name, building_name):
    """The do-nothing reference runs one full episode and reports metrics."""

    from citylearn_env import CityLearnHVACEnv

    env = CityLearnHVACEnv(
        dataset=dataset_name,
        building=building_name,
        episode_time_steps=24,
        seed=0,
    )
    try:
        summary = evaluate_constant(env, 0.0, 1)
    finally:
        env.close()

    assert summary["episodes"] == 1
    # A nominal 24-step episode yields 23 transitions (see test_survey.py).
    assert summary["steps"] == 23
    assert summary["energy_kwh_mean"] >= 0.0
    assert summary["comfort_violations_mean"] >= 0.0
    assert summary["indoor_temperature_min_c"] <= summary["indoor_temperature_max_c"]


def _run_sweep(poc_dir, out_dir):
    command = [
        sys.executable,
        os.path.join(poc_dir, "run_sweep.py"),
        "--dataset",
        "baeda_3dem",
        "--building",
        "Building_1",
        "--timesteps",
        "200",
        "--seeds",
        "0",
        "--eval-start-step",
        "0",
        "--eval-episode-steps",
        "24",
        "--out",
        out_dir,
        "--quiet",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    assert completed.returncode == 0, completed.stderr[-4000:]
    return completed


@pytest.fixture(scope="module")
def sweep_run(poc_dir, tmp_path_factory):
    out_dir = str(tmp_path_factory.mktemp("sweep"))
    completed = _run_sweep(poc_dir, out_dir)
    files = sorted(os.listdir(out_dir))
    assert files, "the sweep did not write a results file"
    with open(os.path.join(out_dir, files[0]), encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload, completed


def test_sweep_json_schema(sweep_run):
    payload, _ = sweep_run

    assert set(payload) >= {"run", "per_seed", "headline", "runtime"}
    run = payload["run"]
    assert run["algo"] == "SAC"
    assert run["seeds"] == [0]
    assert run["timesteps_per_seed"] == 200
    assert run["train_dataset"] == "baeda_3dem"

    seed_block = payload["per_seed"]["0"]
    assert "baeda_3dem:Building_1" in seed_block
    for controller in ("sac", "rule_based_fixed_setpoint", "do_nothing"):
        block = seed_block["baeda_3dem:Building_1"][controller]
        for key in (
            "energy_kwh_mean",
            "comfort_violations_mean",
            "comfort_violation_c_mean",
            "indoor_temperature_min_c",
            "indoor_temperature_max_c",
        ):
            assert key in block, (controller, key)

    for controller in ("sac", "rule_based_fixed_setpoint", "do_nothing"):
        headline = payload["headline"][f"baeda_3dem:Building_1::{controller}"]
        assert headline["energy_kwh_per_episode"]["n"] == 1
        assert headline["comfort_violations_per_episode"]["n"] == 1


def test_sweep_prints_headline_table(sweep_run):
    _, completed = sweep_run

    assert "sac" in completed.stdout
    assert "do_nothing" in completed.stdout
    assert "train timesteps/seed:" in completed.stdout

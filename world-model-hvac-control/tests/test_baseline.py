"""Tests for the model-free baseline harness (slice 1)."""

import json
import os
import subprocess
import sys

import pytest

from run_baseline import build_parser


REQUIRED_RESULT_KEYS = (
    "energy_kwh_mean",
    "comfort_violations_mean",
    "comfort_violation_c_mean",
    "episodes",
    "steps",
)


def test_parser_defaults_and_overrides():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.dataset == "baeda_3dem"
    assert args.building == "Building_1"
    assert args.timesteps == 2000
    assert args.seed == 0
    assert args.out == "results"

    args = parser.parse_args(
        ["--building", "Building_3", "--timesteps", "123", "--seed", "7", "--out", "somewhere"]
    )
    assert args.building == "Building_3"
    assert args.timesteps == 123
    assert args.seed == 7
    assert args.out == "somewhere"


def _run_baseline(poc_dir, out_dir, seed=0, timesteps=200):
    command = [
        sys.executable,
        os.path.join(poc_dir, "run_baseline.py"),
        "--building",
        "Building_1",
        "--timesteps",
        str(timesteps),
        "--seed",
        str(seed),
        "--out",
        out_dir,
        "--eval-episodes",
        "1",
        "--learning-starts",
        "50",
        "--batch-size",
        "32",
        "--quiet",
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600)
    assert completed.returncode == 0, completed.stderr[-4000:]
    return completed


@pytest.fixture(scope="module")
def baseline_run(poc_dir, tmp_path_factory):
    out_dir = str(tmp_path_factory.mktemp("baseline"))
    completed = _run_baseline(poc_dir, out_dir)
    files = sorted(os.listdir(out_dir))
    assert files, "the harness did not write a results file"
    with open(os.path.join(out_dir, files[0]), encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload, completed


def test_results_json_schema(baseline_run):
    payload, _ = baseline_run

    assert set(payload) >= {"run", "results", "runtime"}
    run = payload["run"]
    for key in ("timesteps", "seed", "config", "algo"):
        if key == "config":
            continue
        assert key in run, key
    assert run["algo"] == "SAC"
    assert run["seed"] == 0
    assert run["timesteps"] == 200
    assert run["dataset"] == "baeda_3dem"
    assert run["building"] == "Building_1"

    for block in ("sac", "rule_based_fixed_setpoint"):
        assert block in payload["results"]
        for key in REQUIRED_RESULT_KEYS:
            assert key in payload["results"][block], (block, key)
        assert payload["results"][block]["energy_kwh_mean"] >= 0.0
        assert payload["results"][block]["comfort_violations_mean"] >= 0.0

    assert "wall_time_s" in payload["runtime"]


def test_harness_prints_headline_table(baseline_run):
    _, completed = baseline_run

    assert "SAC (model-free baseline)" in completed.stdout
    assert "rule-based fixed setpoint" in completed.stdout
    assert "train timesteps:" in completed.stdout


def test_determinism_same_seed_same_results(poc_dir, tmp_path):
    out_a = str(tmp_path / "a")
    out_b = str(tmp_path / "b")
    _run_baseline(poc_dir, out_a, seed=3, timesteps=200)
    _run_baseline(poc_dir, out_b, seed=3, timesteps=200)

    file_a = os.path.join(out_a, sorted(os.listdir(out_a))[0])
    file_b = os.path.join(out_b, sorted(os.listdir(out_b))[0])
    with open(file_a, encoding="utf-8") as handle:
        payload_a = json.load(handle)
    with open(file_b, encoding="utf-8") as handle:
        payload_b = json.load(handle)

    # the deterministic part of the report must be identical
    assert payload_a["run"] == payload_b["run"]
    assert payload_a["results"] == payload_b["results"]

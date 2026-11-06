"""Tests for the learned world model + MPC planner (slice 3).

Env-free: every test here runs on synthetic data or on the committed
slice-2 sweep JSON, so this file stays fast (<60 s) and does not need a
CityLearn download.  The full pipeline (train + MPC eval) is exercised
by ``run_world_model.py`` and its committed ``results/*.json``.
"""

import json
import os

import numpy as np
import pytest

from citylearn_env import OBSERVATION_NAMES
from run_world_model import sac_reference_rows
from world_model import (
    MPCController,
    TransitionBatch,
    WorldModel,
    build_history,
    energy_from_observation,
    violation_from_observation,
)

OBS_DIM = len(OBSERVATION_NAMES)
INDOOR = OBSERVATION_NAMES.index("indoor_dry_bulb_temperature")
HEATING_SP = OBSERVATION_NAMES.index("heating_set_point")
COOLING_SP = OBSERVATION_NAMES.index("cooling_set_point")
NET_KWH = OBSERVATION_NAMES.index("net_electricity_consumption_kwh")


def _synthetic_batch(n=64, seed=0):
    rng = np.random.default_rng(seed)
    observations = rng.normal(20.0, 5.0, size=(n, OBS_DIM))
    observations[:, HEATING_SP] = 20.0
    observations[:, COOLING_SP] = 24.0
    actions = rng.uniform(-1.0, 1.0, size=(n, 1))
    next_observations = observations + rng.normal(0.0, 0.5, size=(n, OBS_DIM))
    next_observations[:, INDOOR] = observations[:, INDOOR] + 0.3 * actions[:, 0]
    return TransitionBatch(
        observations=observations,
        actions=actions,
        next_observations=next_observations,
        energies=np.abs(rng.normal(0.01, 0.005, size=n)),
        violations=np.abs(rng.normal(0.5, 0.5, size=n)),
    )


def test_transition_batch_concatenate_and_split():
    first = _synthetic_batch(40, seed=1)
    second = _synthetic_batch(24, seed=2)
    joined = TransitionBatch.concatenate([first, second])

    assert len(joined) == 64
    assert joined.observations.shape == (64, OBS_DIM)
    train, heldout = joined.split(0.5)
    assert len(train) == 32 and len(heldout) == 32
    # split is chronological: the held-out part starts where train ends
    assert np.array_equal(heldout.observations[0], joined.observations[32])

    with pytest.raises(ValueError):
        TransitionBatch.concatenate([])


def test_build_history_pads_with_first_frame():
    observations = np.arange(3 * OBS_DIM, dtype=np.float64).reshape(3, OBS_DIM)
    history = build_history(observations, stack=3)

    assert history.shape == (3, 3, OBS_DIM)
    # first row: padded with the oldest frame, newest last
    assert np.array_equal(history[0, 0], observations[0])
    assert np.array_equal(history[0, 2], observations[0])
    assert np.array_equal(history[2, 0], observations[0])
    assert np.array_equal(history[2, 2], observations[2])

    with pytest.raises(ValueError):
        build_history(observations, stack=0)


def test_world_model_fit_predict_synthetic():
    batch = _synthetic_batch()
    model = WorldModel(obs_dim=OBS_DIM, n_actions=1, hidden=32, stack=3, seed=0)

    with pytest.raises(RuntimeError):
        model.predict(np.zeros((2, 3, OBS_DIM)), np.zeros((2, 1)))

    fit = model.fit(batch, iterations=50)
    assert model.trained
    assert fit["n_transitions"] == 64
    assert np.isfinite(fit["final_loss"])

    history = build_history(batch.observations[:4], 3)
    prediction = model.predict(history, batch.actions[:4])
    assert prediction.shape == (4, OBS_DIM)
    assert np.all(np.isfinite(prediction))

    diagnostic = model.one_step_error(batch)
    assert diagnostic["n"] == 64
    assert np.isfinite(diagnostic["mae"])
    assert np.isfinite(diagnostic["persistence_mae"])
    assert set(diagnostic["per_observation"]) == set(OBSERVATION_NAMES)


def test_mpc_plan_is_bounded_and_model_only():
    batch = _synthetic_batch()
    model = WorldModel(obs_dim=OBS_DIM, n_actions=1, hidden=32, stack=3, seed=0)
    model.fit(batch, iterations=50)

    def fresh_controller():
        return MPCController(model, horizon=4, num_samples=8, num_iterations=2, seed=0)

    observation = batch.observations[0]
    first = fresh_controller().plan(observation)
    second = fresh_controller().plan(observation)

    assert first.shape == (1,)
    assert np.all(np.isfinite(first))
    assert np.all(first >= -1.0) and np.all(first <= 1.0)
    # same model + same seed + same observation -> same action (no env read)
    assert np.allclose(first, second)


def test_violation_and_energy_from_observation():
    observation = np.zeros((1, OBS_DIM), dtype=np.float64)
    observation[0, INDOOR] = 25.0
    observation[0, HEATING_SP] = 20.0
    observation[0, COOLING_SP] = 24.0
    observation[0, NET_KWH] = 0.7

    assert violation_from_observation(observation)[0] == pytest.approx(1.0)
    assert energy_from_observation(observation)[0] == pytest.approx(0.7)

    observation[0, INDOOR] = 22.0
    assert violation_from_observation(observation)[0] == pytest.approx(0.0)


def test_sac_reference_rows_match_committed_sweep(poc_dir):
    path = os.path.join(
        poc_dir,
        "results",
        "sweep_sac_tx_travis_county_neighborhood_resstock-amy2018-2021-release-1-102188_s0-1-2.json",
    )
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)

    rows = sac_reference_rows(payload)

    tx = "tx_travis_county_neighborhood:resstock-amy2018-2021-release-1-102188"
    ca = "ca_alameda_county_neighborhood:resstock-amy2018-2021-release-1-102040"
    vt = "vt_chittenden_county_neighborhood:resstock-amy2018-2021-release-1-112208"
    assert rows[tx]["energy_kwh"]["mean"] == pytest.approx(1.1895, abs=1e-4)
    assert rows[tx]["comfort_violation_c"]["mean"] == pytest.approx(323.0967, abs=1e-4)
    assert rows[ca]["energy_kwh"]["mean"] == pytest.approx(3.4044, abs=1e-4)
    assert rows[ca]["comfort_violation_c"]["mean"] == pytest.approx(171.3821, abs=1e-4)
    assert rows[vt]["energy_kwh"]["mean"] == pytest.approx(1.4234, abs=1e-4)
    assert rows[vt]["comfort_violation_c"]["mean"] == pytest.approx(347.2945, abs=1e-4)
    for row in rows.values():
        assert row["energy_kwh"]["n"] == 3

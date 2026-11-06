"""Tests for the CityLearn HVAC environment wrapper (slice 1)."""

import numpy as np
import pytest

from citylearn_env import (
    OBSERVATION_DIM,
    OBSERVATION_NAMES,
    CityLearnHVACEnv,
    FixedSetpointController,
    run_rule_based_episode,
)


@pytest.fixture(scope="module")
def env(dataset_name, building_name):
    environment = CityLearnHVACEnv(
        dataset=dataset_name,
        building=building_name,
        episode_time_steps=24,
        seed=0,
    )
    yield environment
    environment.close()


def test_reset_returns_observation_and_info(env):
    observation, info = env.reset()

    assert observation.shape == env.observation_space.shape
    assert observation.dtype == np.float32
    assert np.all(np.isfinite(observation))
    assert info["building_ids"] == env.building_ids
    assert info["climate_id"] == env.climate_id
    assert env.observation_space.shape[0] == OBSERVATION_DIM * env.n_buildings


def test_observation_contract_is_fixed_length(env):
    observation, _ = env.reset()
    block = observation[:OBSERVATION_DIM]

    assert len(OBSERVATION_NAMES) == OBSERVATION_DIM
    assert block.size == OBSERVATION_DIM
    # the fixed set points and the comfort band are physically sensible
    assert 10.0 <= block[OBSERVATION_NAMES.index("heating_set_point")] <= 30.0
    assert 10.0 <= block[OBSERVATION_NAMES.index("cooling_set_point")] <= 35.0
    assert block[OBSERVATION_NAMES.index("cooling_set_point")] >= block[
        OBSERVATION_NAMES.index("heating_set_point")
    ]


def test_step_contract_finite_observations_energy_and_comfort(env):
    observation, _ = env.reset()
    controller = FixedSetpointController()

    for _ in range(20):
        action = controller.act(observation)
        assert action.shape == env.action_space.shape
        assert np.all(action >= env.action_space.low)
        assert np.all(action <= env.action_space.high)

        observation, reward, terminated, truncated, info = env.step(action)

        assert observation.shape == env.observation_space.shape
        assert np.all(np.isfinite(observation))
        assert info["energy_kwh"] >= 0.0
        assert info["comfort_violation_c"] >= 0.0
        assert isinstance(info["comfort_violation"], bool)
        assert np.isfinite(reward)
        if terminated or truncated:
            observation, _ = env.reset()


def test_rule_based_episode_reports_metrics(env):
    summary = run_rule_based_episode(env, steps=100)

    assert summary["steps"] == 100
    assert summary["energy_kwh"] >= 0.0
    assert summary["comfort_violation_c"] >= 0.0
    assert 0 <= summary["comfort_violations"] <= summary["steps"]


def test_action_expansion_is_clipped(env):
    # an out-of-contract action must still produce a valid CityLearn action
    citylearn_action = env._to_citylearn_action(np.array([5.0] * env.n_buildings, dtype=np.float32))

    assert citylearn_action.shape == env._action_low.shape
    assert np.all(citylearn_action >= env._action_low - 1e-6)
    assert np.all(citylearn_action <= env._action_high + 1e-6)


def test_wrong_action_size_raises(env):
    with pytest.raises(ValueError):
        env._to_citylearn_action(np.zeros(env.n_buildings + 3, dtype=np.float32))

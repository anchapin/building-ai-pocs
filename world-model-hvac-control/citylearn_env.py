"""Thin simulator wrapper for POC #4 -- world-model HVAC control (slice 1).

The wrapper sits on top of CityLearn (``citylearn==3.2.0``) and exposes a
small, *fixed* action / observation contract so that

* slice 1's model-free baseline (stable-baselines3),
* slice 2's model-free baseline sweep, and
* slice 3's learned world model + MPC planner

all speak the same interface and can be compared on an *unseen*
building / climate.

Action contract
---------------
One scalar per building, ``float32`` in ``[-1, 1]``::

    a < 0 : cooling intensity = |a|  (fraction of the cooling device's
            nominal power made available)
    a > 0 : heating intensity =  a   (fraction of the heating device's
            nominal power made available)

The scalar is expanded into CityLearn's native per-device action vector
(``heating_device``, ``cooling_device``, ``cooling_or_heating_device``);
storage / EV / deferrable-load actions are held at 0 for slice 1.

Observation contract
--------------------
Ten floats per building, in this fixed order
(:data:`OBSERVATION_NAMES`):

    outdoor_dry_bulb_temperature, indoor_dry_bulb_temperature,
    heating_set_point, cooling_set_point, comfort_band,
    net_electricity_consumption_kwh, cooling_demand_kwh,
    heating_demand_kwh, hour_of_day, day_of_year

The vector length therefore depends only on the number of buildings, not on
the data set -- which is what makes an unseen-building / unseen-climate
evaluation expressible.

Step info
---------
``energy_kwh``              net electricity consumed in the step, [kWh]
``comfort_violation_c``     degrees outside the comfort band in the step, [degC]
``comfort_violation``       bool, ``comfort_violation_c > 0``
``building_ids`` / ``climate_id``  identifiers of the simulated buildings

Nothing in this module is a real building: every number comes from the
CityLearn simulator, and a simulated energy saving is **not** a real saving.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

import gymnasium as gym
import numpy as np

__all__ = [
    "OBSERVATION_NAMES",
    "OBSERVATION_DIM",
    "CityLearnHVACEnv",
    "FixedSetpointController",
    "resolve_dataset_schema",
    "run_rule_based_episode",
]

OBSERVATION_NAMES: Tuple[str, ...] = (
    "outdoor_dry_bulb_temperature",
    "indoor_dry_bulb_temperature",
    "heating_set_point",
    "cooling_set_point",
    "comfort_band",
    "net_electricity_consumption_kwh",
    "cooling_demand_kwh",
    "heating_demand_kwh",
    "hour_of_day",
    "day_of_year",
)
OBSERVATION_DIM: int = len(OBSERVATION_NAMES)

# Keys of CityLearn actions that are driven by the HVAC control signal.
_HVAC_ACTION_KEYS = ("cooling_or_heating_device", "cooling_device", "heating_device")


def resolve_dataset_schema(dataset: str, root: Optional[str] = None) -> str:
    """Return the CityLearn ``schema`` argument for ``dataset``.

    If a local copy exists in ``<root>/data/datasets/<dataset>/schema.json``
    it is used directly (CityLearn accepts a directory path and reads
    ``schema.json`` from it); otherwise the data set name is returned and
    CityLearn downloads it once into its cache directory. Either way the
    data set is never committed to git.

    ``root`` defaults to the directory containing this module (i.e. the
    ``world-model-hvac-control`` folder); it is exposed so that callers
    and tests can point the lookup at a different tree.
    """

    if root is None:
        root = os.path.dirname(os.path.abspath(__file__))
    local_dir = os.path.join(root, "data", "datasets", dataset)
    if os.path.isfile(os.path.join(local_dir, "schema.json")):
        return local_dir
    return dataset


def _series_last(series: Any) -> float:
    """Return the last element of a CityLearn time series as a float."""

    if series is None:
        return 0.0
    array = np.asarray(series, dtype=np.float64)
    if array.size == 0:
        return 0.0
    value = float(array[-1])
    return value if np.isfinite(value) else 0.0


class CityLearnHVACEnv(gym.Env):
    """Gymnasium environment exposing a fixed HVAC action / observation contract.

    Parameters
    ----------
    dataset : str
        CityLearn data set name (e.g. ``"baeda_3dem"``). If a local copy
        exists in ``<poc>/data/datasets/<dataset>`` it is used directly
        (CityLearn accepts a schema path), otherwise CityLearn downloads the
        data set once into its cache directory; either way the data set is
        never committed to git.
    building : str
        Name of the building inside the data set (e.g. ``"Building_1"``).
    episode_time_steps : int
        Number of time steps per episode.
    start_step : int
        First time step of the episode window inside the data set. 0
        (default) keeps CityLearn's sequential episode windows; > 0 pins
        every reset to the single window
        ``[start_step, start_step + episode_time_steps - 1]``. Slice 2
        uses this to evaluate on windows with non-degenerate comfort set
        points (finding F3).
    seed : int
        Seed handed to the simulator.
    energy_weight, comfort_weight : float
        Weights of the reward function
        ``-(energy_weight * energy_kwh + comfort_weight * comfort_violation_c)``.
    solar_generation : bool
        Whether rooftop PV is simulated. ``False`` (the default) keeps the
        simulation free of the optional PySAM dependency that PV auto-sizing
        needs, and keeps the energy metric about consumption only.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        dataset: str = "baeda_3dem",
        building: str = "Building_1",
        episode_time_steps: int = 24,
        start_step: int = 0,
        seed: int = 0,
        energy_weight: float = 1.0,
        comfort_weight: float = 0.5,
        solar_generation: bool = False,
        citylearn_env: Optional[Any] = None,
    ) -> None:
        super().__init__()

        from citylearn.citylearn import CityLearnEnv  # local import: heavy

        self.dataset = dataset
        self.building = building
        self.episode_time_steps = int(episode_time_steps)
        self.start_step = int(start_step)
        self.seed = int(seed)
        self.energy_weight = float(energy_weight)
        self.comfort_weight = float(comfort_weight)
        self.solar_generation = bool(solar_generation)

        if citylearn_env is None:
            # start_step == 0 keeps CityLearn's default sequential episode
            # windows (episode 0 covers steps 0..N-1, episode 1 covers
            # N..2N-1, ...). start_step > 0 pins EVERY reset to the single
            # window [start_step, start_step + N - 1] via CityLearn's
            # episode-splits list, so evaluation replays one fixed window.
            if self.start_step > 0:
                episode_arg: Any = [
                    (self.start_step, self.start_step + self.episode_time_steps - 1)
                ]
            else:
                episode_arg = self.episode_time_steps
            citylearn_env = CityLearnEnv(
                schema=resolve_dataset_schema(dataset),
                buildings=[building],
                episode_time_steps=episode_arg,
                random_seed=self.seed,
                central_agent=True,
                solar_generation=self.solar_generation,
            )
        self.env = citylearn_env

        self.buildings: List[Any] = list(self.env.buildings)
        self.n_buildings = len(self.buildings)

        # -- action plumbing -------------------------------------------------
        self._action_slices: List[Tuple[int, str, int]] = []
        offset = 0
        for i, building in enumerate(self.buildings):
            for key in building.active_actions:
                self._action_slices.append((i, key, offset))
                offset += 1
        self._n_actions = offset

        action_space = self.env.action_space
        self._action_low = np.asarray(action_space[0].low, dtype=np.float32)
        self._action_high = np.asarray(action_space[0].high, dtype=np.float32)

        # -- observation plumbing -------------------------------------------
        self.observation_space = gym.spaces.Box(
            low=-np.inf, high=np.inf, shape=(OBSERVATION_DIM * self.n_buildings,), dtype=np.float32
        )
        self.action_space = gym.spaces.Box(
            low=-1.0, high=1.0, shape=(self.n_buildings,), dtype=np.float32
        )

    # ------------------------------------------------------------------
    # identifiers
    # ------------------------------------------------------------------
    @property
    def building_ids(self) -> List[str]:
        """Identifiers of the simulated buildings (``"<dataset>:<building>"``)."""

        return [f"{self.dataset}:{getattr(b, 'name', self.building)}" for b in self.buildings]

    @property
    def climate_id(self) -> str:
        """Identifier of the climate of the simulated data set."""

        return self.dataset

    @property
    def env_id(self) -> str:
        """Unique identifier of this (data set, building) pair."""

        return f"{self.dataset}:{self.building}"

    # ------------------------------------------------------------------
    # gym API
    # ------------------------------------------------------------------
    def reset(self, *, seed: Optional[int] = None, options: Optional[Dict[str, Any]] = None):
        if seed is not None:
            self.seed = int(seed)
            np.random.seed(self.seed)
        self.env.reset(seed=self.seed)
        observation = self._observation()
        return observation, self._info(0.0, 0.0)

    def step(self, action: Sequence[float]):
        citylearn_action = self._to_citylearn_action(action)
        self.env.step([citylearn_action])
        energy, violation = self._energy_and_violation()
        observation = self._observation()
        reward = -(self.energy_weight * energy + self.comfort_weight * violation)
        terminated = bool(self.env.terminated)
        truncated = bool(self.env.truncated)
        return observation, float(reward), terminated, truncated, self._info(energy, violation)

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _to_citylearn_action(self, action: Sequence[float]) -> np.ndarray:
        """Expand the per-building HVAC scalar into CityLearn's action vector."""

        signal = np.asarray(action, dtype=np.float32).reshape(-1)
        if signal.size != self.n_buildings:
            raise ValueError(
                f"expected {self.n_buildings} action value(s), got {signal.size}"
            )

        out = np.zeros(self._n_actions, dtype=np.float32)
        for building_index, key, offset in self._action_slices:
            value = float(signal[building_index])
            if key == "cooling_or_heating_device":
                out[offset] = value
            elif key == "cooling_device":
                out[offset] = max(0.0, -value)
            elif key == "heating_device":
                out[offset] = max(0.0, value)
            else:
                # storage / EV / deferrable loads are not controlled in slice 1
                out[offset] = 0.0

        return np.clip(out, self._action_low, self._action_high).astype(np.float32)

    def _building_state(self, building: Any) -> Dict[str, float]:
        time_step = int(getattr(self.env, "time_step", 0))
        indoor = _series_last(building.indoor_dry_bulb_temperature)
        heating_set_point = _series_last(building.indoor_dry_bulb_temperature_heating_set_point)
        cooling_set_point = _series_last(building.indoor_dry_bulb_temperature_cooling_set_point)
        comfort_band = _series_last(building.comfort_band)
        energy = _series_last(building.net_electricity_consumption)
        cooling_demand = _series_last(building.cooling_demand)
        heating_demand = _series_last(building.heating_demand)
        outdoor = _series_last(getattr(building, "weather", None).outdoor_dry_bulb_temperature)

        return {
            "outdoor_dry_bulb_temperature": outdoor,
            "indoor_dry_bulb_temperature": indoor,
            "heating_set_point": heating_set_point,
            "cooling_set_point": cooling_set_point,
            "comfort_band": comfort_band,
            "net_electricity_consumption_kwh": energy,
            "cooling_demand_kwh": cooling_demand,
            "heating_demand_kwh": heating_demand,
            "hour_of_day": float(time_step % 24),
            "day_of_year": float((time_step // 24) % 365),
        }

    def _observation(self) -> np.ndarray:
        values: List[float] = []
        for building in self.buildings:
            state = self._building_state(building)
            values.extend(float(state[name]) for name in OBSERVATION_NAMES)
        observation = np.asarray(values, dtype=np.float32)
        if not np.all(np.isfinite(observation)):
            raise ValueError("non-finite observation produced by the simulator")
        return observation

    def _energy_and_violation(self) -> Tuple[float, float]:
        energy = 0.0
        violation = 0.0
        for building in self.buildings:
            state = self._building_state(building)
            energy += max(0.0, state["net_electricity_consumption_kwh"])
            indoor = state["indoor_dry_bulb_temperature"]
            heating_set_point = state["heating_set_point"]
            cooling_set_point = state["cooling_set_point"]
            violation += max(0.0, heating_set_point - indoor) + max(0.0, indoor - cooling_set_point)
        return energy, violation

    def _info(self, energy: float, violation: float) -> Dict[str, Any]:
        return {
            "energy_kwh": float(energy),
            "comfort_violation_c": float(violation),
            "comfort_violation": bool(violation > 0.0),
            "building_ids": self.building_ids,
            "climate_id": self.climate_id,
        }


class FixedSetpointController:
    """Rule-based controller that tracks the data set's fixed comfort band.

    The controller is deterministic: it looks at the current indoor
    temperature and the (fixed) heating / cooling set points of the data set
    and returns the HVAC signal that closes the gap, capped at full power.

    Parameters
    ----------
    deadband : float
        Extra tolerance, in [degC], added around the comfort band.
    """

    def __init__(self, deadband: float = 0.0) -> None:
        self.deadband = float(deadband)

    def act(self, observation: Sequence[float]) -> np.ndarray:
        observation = np.asarray(observation, dtype=np.float32).reshape(-1)
        n_buildings = observation.size // OBSERVATION_DIM
        actions = np.zeros(n_buildings, dtype=np.float32)
        for i in range(n_buildings):
            block = observation[i * OBSERVATION_DIM : (i + 1) * OBSERVATION_DIM]
            indoor = float(block[OBSERVATION_NAMES.index("indoor_dry_bulb_temperature")])
            heating_set_point = float(block[OBSERVATION_NAMES.index("heating_set_point")])
            cooling_set_point = float(block[OBSERVATION_NAMES.index("cooling_set_point")])
            if indoor > cooling_set_point + self.deadband:
                actions[i] = -min(1.0, (indoor - cooling_set_point - self.deadband) / 2.0)
            elif indoor < heating_set_point - self.deadband:
                actions[i] = min(1.0, (heating_set_point - indoor - self.deadband) / 2.0)
            else:
                actions[i] = 0.0
        return actions


def run_rule_based_episode(
    env: CityLearnHVACEnv, steps: int = 100, controller: Optional[FixedSetpointController] = None
) -> Dict[str, Any]:
    """Run ``steps`` time steps with the rule-based controller and summarise.

    Used by the smoke test: asserts finite observations, non-negative energy
    and a comfort metric for every step.
    """

    controller = controller or FixedSetpointController()
    observation, _ = env.reset()
    total_energy = 0.0
    total_violation = 0.0
    violations = 0
    n_steps = 0
    for _ in range(int(steps)):
        action = controller.act(observation)
        observation, reward, terminated, truncated, info = env.step(action)
        total_energy += float(info["energy_kwh"])
        total_violation += float(info["comfort_violation_c"])
        violations += int(bool(info["comfort_violation"]))
        n_steps += 1
        if terminated or truncated:
            observation, _ = env.reset()
    return {
        "steps": n_steps,
        "energy_kwh": total_energy,
        "comfort_violation_c": total_violation,
        "comfort_violations": violations,
    }

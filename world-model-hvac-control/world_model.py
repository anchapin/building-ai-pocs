"""Learned world model + MPC planner for POC #4 (slice 3).

The slice-2 sweep established the protocol this module implements:

* the *train* set is the RESStock Texas neighbourhood building
  ``resstock-amy2018-2021-release-1-102188`` (both HVAC directions are
  actuated and net electricity responds to the action -- findings F1/F2);
* the *held-out* sets are the Vermont and California RESStock buildings
  (unseen buildings AND unseen climates);
* every set is scored on the SAME fixed June window (start step 4368,
  168 nominal steps -> 167 transitions) so the numbers are comparable
  with the committed SAC sweep headline.

What this module provides
-------------------------
``WorldModel``
    A small latent-dynamics MLP.  It maps a short *history* of the
    fixed 10-floats-per-building observation plus the HVAC action to the
    CHANGE of the observation (``delta`` parameterisation, so that
    "predict the current observation" is the zero prediction).  The
    history is a cheap stand-in for the simulator's latent thermal state:
    the CityLearn building dynamics is an LSTM with an internal state
    that the 10-floats observation does not expose, so a one-frame
    model cannot predict the response to an action (see the slice-3
    diagnostics in ``REPORT.md``).

``MPCController``
    A cross-entropy-method (CEM) shooting planner that uses ONLY the
    learned model.  It has no reference to the environment: planning is a
    pure function of the current observation history and the model.

``collect_transitions``
    Collects ``(obs, action, next_obs)`` transitions from a real
    environment.  Every real environment step is counted, because the
    issue-#4 gate caps the world-model arm at 1,000 real-environment
    steps.

Nothing here is a real building: every number comes from the CityLearn
simulator, and a simulated energy saving is **not** a real saving.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from citylearn_env import OBSERVATION_NAMES

__all__ = [
    "TransitionBatch",
    "WorldModel",
    "MPCController",
    "collect_transitions",
    "energy_from_observation",
    "violation_from_observation",
]

_IDX = {name: i for i, name in enumerate(OBSERVATION_NAMES)}

# Physical sanity clamps applied to *predicted* observations.  They keep a
# mis-specified model from producing physically absurd indoor temperatures
# during multi-step rollouts; they are not a modelling choice that can
# flatter the controller (they only clip values the simulator never
# produces).
_PREDICTION_CLIP: Dict[str, Tuple[float, float]] = {
    "outdoor_dry_bulb_temperature": (-60.0, 70.0),
    "indoor_dry_bulb_temperature": (-40.0, 80.0),
    "heating_set_point": (-40.0, 80.0),
    "cooling_set_point": (-40.0, 80.0),
    "comfort_band": (0.0, 30.0),
    "net_electricity_consumption_kwh": (0.0, 1000.0),
    "cooling_demand_kwh": (0.0, 1000.0),
    "heating_demand_kwh": (0.0, 1000.0),
    "hour_of_day": (0.0, 24.0),
    "day_of_year": (0.0, 366.0),
}


@dataclasses.dataclass
class TransitionBatch:
    """A batch of real-environment transitions."""

    observations: np.ndarray  # (N, obs_dim) float64
    actions: np.ndarray  # (N, n_actions) float64
    next_observations: np.ndarray  # (N, obs_dim) float64
    energies: np.ndarray  # (N,) float64, kWh consumed in the transition
    violations: np.ndarray  # (N,) float64, comfort violation degrees

    def __len__(self) -> int:
        return int(self.observations.shape[0])

    @staticmethod
    def concatenate(batches: Sequence["TransitionBatch"]) -> "TransitionBatch":
        batches = [b for b in batches if len(b) > 0]
        if not batches:
            raise ValueError("no transitions to concatenate")
        return TransitionBatch(
            observations=np.concatenate([b.observations for b in batches], axis=0),
            actions=np.concatenate([b.actions for b in batches], axis=0),
            next_observations=np.concatenate([b.next_observations for b in batches], axis=0),
            energies=np.concatenate([b.energies for b in batches], axis=0),
            violations=np.concatenate([b.violations for b in batches], axis=0),
        )

    def split(self, fraction: float) -> Tuple["TransitionBatch", "TransitionBatch"]:
        """Split into a train part and a held-out part (chronological)."""

        n = len(self)
        cut = int(math.floor(n * float(fraction)))
        cut = max(1, min(n - 1, cut))
        return self[:cut], self[cut:]

    def __getitem__(self, item: Any) -> "TransitionBatch":
        if isinstance(item, slice):
            return TransitionBatch(
                observations=self.observations[item],
                actions=self.actions[item],
                next_observations=self.next_observations[item],
                energies=self.energies[item],
                violations=self.violations[item],
            )
        raise TypeError("TransitionBatch supports slicing only")


def _blocks(observation: np.ndarray) -> np.ndarray:
    """Reshape a flat observation into ``(n, buildings, 10)``."""

    observation = np.atleast_2d(np.asarray(observation, dtype=np.float64))
    n_buildings = observation.shape[1] // len(OBSERVATION_NAMES)
    return observation.reshape(observation.shape[0], n_buildings, len(OBSERVATION_NAMES))


def energy_from_observation(observation: np.ndarray) -> np.ndarray:
    """Net electricity [kWh] of a (possibly batched) observation."""

    blocks = _blocks(observation)
    energy = np.maximum(0.0, blocks[:, :, _IDX["net_electricity_consumption_kwh"]])
    return energy.sum(axis=1)


def violation_from_observation(observation: np.ndarray) -> np.ndarray:
    """Comfort violation [degC] of a (possibly batched) observation.

    Same definition as :meth:`citylearn_env.CityLearnHVACEnv._energy_and_violation`:
    the degrees outside the (heating set point, cooling set point) band.
    """

    blocks = _blocks(observation)
    indoor = blocks[:, :, _IDX["indoor_dry_bulb_temperature"]]
    heating = blocks[:, :, _IDX["heating_set_point"]]
    cooling = blocks[:, :, _IDX["cooling_set_point"]]
    violation = np.maximum(0.0, heating - indoor) + np.maximum(0.0, indoor - cooling)
    return violation.sum(axis=1)


def build_history(observations: np.ndarray, stack: int) -> np.ndarray:
    """Build the stacked history of a *sequence* of observations.

    ``observations`` is ``(T, obs_dim)`` and the result is
    ``(T, stack, obs_dim)``: for every time step the last ``stack``
    frames (oldest first), padded at the beginning with the oldest
    available frame.
    """

    observations = np.atleast_2d(np.asarray(observations, dtype=np.float64))
    stack = int(stack)
    if stack < 1:
        raise ValueError("stack must be >= 1")
    history = np.empty((observations.shape[0], stack, observations.shape[1]), dtype=np.float64)
    for index in range(observations.shape[0]):
        start = max(0, index - stack + 1)
        frames = observations[start : index + 1]
        if frames.shape[0] < stack:
            pad = np.repeat(frames[:1], stack - frames.shape[0], axis=0)
            frames = np.concatenate([pad, frames], axis=0)
        history[index] = frames
    return history


class WorldModel:
    """Latent-dynamics MLP: ``(observation history, action) -> next observation``.

    The network is a plain multi-layer perceptron with two hidden layers.
    Inputs and (delta) targets are standardised with the statistics of
    the training split; the model stores those statistics so that
    prediction is a pure function of the weights.

    Parameters
    ----------
    obs_dim : int
        Flattened observation length (10 per building).
    n_actions : int
        Number of HVAC scalars (1 per building).
    hidden : int
        Width of the hidden layers.
    stack : int
        Number of past observation frames fed to the network.
    seed : int
        Seed for the weight initialisation (and therefore for training).
    delta_targets : bool
        Predict the change of the observation instead of the observation.
    """

    def __init__(
        self,
        obs_dim: int = len(OBSERVATION_NAMES),
        n_actions: int = 1,
        hidden: int = 128,
        stack: int = 3,
        seed: int = 0,
        delta_targets: bool = True,
    ) -> None:
        import torch
        from torch import nn

        self.obs_dim = int(obs_dim)
        self.n_actions = int(n_actions)
        self.hidden = int(hidden)
        self.stack = int(stack)
        self.seed = int(seed)
        # The network predicts the CHANGE of the observation (delta
        # targets).  "Predict the current observation unchanged" is then
        # the zero prediction, which makes the model learn the action ->
        # response mapping instead of the absolute levels of one building.
        self.delta_targets = bool(delta_targets)

        torch.manual_seed(self.seed)
        self.net = nn.Sequential(
            nn.Linear(self.stack * self.obs_dim + self.n_actions, self.hidden),
            nn.ReLU(),
            nn.Linear(self.hidden, self.hidden),
            nn.ReLU(),
            nn.Linear(self.hidden, self.obs_dim),
        )
        self.net.eval()

        self._x_mean = np.zeros(self.stack * self.obs_dim + self.n_actions, dtype=np.float64)
        self._x_std = np.ones(self.stack * self.obs_dim + self.n_actions, dtype=np.float64)
        self._y_mean = np.zeros(self.obs_dim, dtype=np.float64)
        self._y_std = np.ones(self.obs_dim, dtype=np.float64)
        self.trained = False
        self.training_history: List[float] = []

    # ------------------------------------------------------------------
    # training
    # ------------------------------------------------------------------
    def fit(
        self,
        batch: TransitionBatch,
        iterations: int = 2000,
        learning_rate: float = 1e-3,
        batch_size: int = 64,
        weight_decay: float = 1e-5,
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Fit the model on real-environment transitions."""

        import torch
        from torch import nn

        if len(batch) < 2:
            raise ValueError("need at least two transitions to fit the world model")

        history = build_history(batch.observations, self.stack)
        x = np.concatenate([history.reshape(len(batch), -1), batch.actions], axis=1)
        y = batch.next_observations
        if self.delta_targets:
            y = y - batch.observations

        self._x_mean = x.mean(axis=0)
        self._x_std = np.maximum(x.std(axis=0), 1e-6)
        self._y_mean = y.mean(axis=0)
        self._y_std = np.maximum(y.std(axis=0), 1e-6)

        xs = torch.tensor((x - self._x_mean) / self._x_std, dtype=torch.float32)
        ys = torch.tensor((y - self._y_mean) / self._y_std, dtype=torch.float32)

        optimizer = torch.optim.Adam(
            self.net.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay)
        )
        loss_fn = nn.MSELoss()
        generator = torch.Generator().manual_seed(self.seed)

        n = xs.shape[0]
        for iteration in range(int(iterations)):
            index = torch.randint(0, n, (min(batch_size, n),), generator=generator)
            prediction = self.net(xs[index])
            loss = loss_fn(prediction, ys[index])
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            if iteration % 100 == 0:
                self.training_history.append(float(loss.item()))
                if verbose:
                    print(f"[world-model] iteration {iteration}: loss {float(loss.item()):.6f}")

        self.trained = True
        # Record the loss at the final iteration (the loop above only logs
        # every 100th iteration, so the last logged value is stale by up to
        # 99 steps).  Re-evaluate once on a fixed batch for the record.
        with torch.no_grad():
            final_prediction = self.net(xs[: min(batch_size, n)])
            final_loss = float(loss_fn(final_prediction, ys[: min(batch_size, n)]).item())
        self.training_history.append(final_loss)
        return {
            "iterations": int(iterations),
            "final_loss": final_loss,
            "n_transitions": int(n),
            "stack": int(self.stack),
        }

    # ------------------------------------------------------------------
    # prediction
    # ------------------------------------------------------------------
    def predict(self, history: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """Predict the next observation for a batch of ``(history, action)`` pairs.

        ``history`` is ``(N, stack, obs_dim)`` (or ``(N, stack * obs_dim)``)
        with the most recent frame last.
        """

        import torch

        if not self.trained:
            raise RuntimeError("the world model has not been fitted")

        history = np.asarray(history, dtype=np.float64)
        if history.ndim == 2:
            history = history.reshape(history.shape[0], self.stack, self.obs_dim)
        if history.ndim != 3 or history.shape[1:] != (self.stack, self.obs_dim):
            raise ValueError(
                f"history must be (N, {self.stack}, {self.obs_dim}), got {history.shape}"
            )
        actions = np.atleast_2d(np.asarray(actions, dtype=np.float64))
        if actions.shape[0] == 1 and history.shape[0] > 1:
            actions = np.repeat(actions, history.shape[0], axis=0)

        x = np.concatenate([history.reshape(history.shape[0], -1), actions], axis=1)
        xs = torch.tensor((x - self._x_mean) / self._x_std, dtype=torch.float32)
        with torch.no_grad():
            ys = self.net(xs).cpu().numpy().astype(np.float64)
        delta = ys * self._y_std + self._y_mean
        if self.delta_targets:
            prediction = history[:, -1, :] + delta
        else:
            prediction = delta

        n_buildings = max(1, self.obs_dim // len(OBSERVATION_NAMES))
        blocks = prediction.reshape(prediction.shape[0], n_buildings, len(OBSERVATION_NAMES))
        for name, (low, high) in _PREDICTION_CLIP.items():
            index = _IDX[name]
            blocks[:, :, index] = np.clip(blocks[:, :, index], low, high)
        return blocks.reshape(prediction.shape[0], self.obs_dim)

    # ------------------------------------------------------------------
    # diagnostics
    # ------------------------------------------------------------------
    def one_step_error(self, batch: TransitionBatch) -> Dict[str, Any]:
        """One-step prediction error on a (held-out) batch.

        This is a *diagnostic*, never a gate.  It is reported next to the
        trivial baseline: predicting the current observation unchanged
        (persistence).
        """

        if not self.trained:
            raise RuntimeError("the world model has not been fitted")
        history = build_history(batch.observations, self.stack)
        prediction = self.predict(history, batch.actions)
        error = prediction - batch.next_observations
        persistence = batch.observations - batch.next_observations

        per_observation = {}
        for name in OBSERVATION_NAMES:
            index = _IDX[name]
            per_observation[name] = {
                "mae": float(np.mean(np.abs(error[:, index]))),
                "persistence_mae": float(np.mean(np.abs(persistence[:, index]))),
            }

        return {
            "n": len(batch),
            "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error**2))),
            "persistence_mae": float(np.mean(np.abs(persistence))),
            "per_observation": per_observation,
        }


class MPCController:
    """Cross-entropy-method shooting planner that uses ONLY the model.

    The controller holds a :class:`WorldModel` and never holds (or looks
    at) an environment.  ``plan`` maps an observation to an action; the
    caller executes that action in the real environment and calls
    ``plan`` again (receding horizon).

    Parameters
    ----------
    model : WorldModel
        The learned model used for all rollouts.
    horizon : int
        Planning horizon (number of steps rolled out inside the model).
    num_samples : int
        Candidate action sequences sampled per CEM iteration.
    num_iterations : int
        CEM refinement iterations.
    elite_fraction : float
        Fraction of candidates kept as elites.
    energy_weight, comfort_weight : float
        Weights of the planning cost.  They mirror the SAC reward of the
        slice-2 sweep (``-(1.0 * energy + 0.5 * violation)``) so the two
        controllers optimise the same objective.
    seed : int
        Seed of the planner's random number generator.
    """

    def __init__(
        self,
        model: WorldModel,
        horizon: int = 12,
        num_samples: int = 64,
        num_iterations: int = 4,
        elite_fraction: float = 0.25,
        energy_weight: float = 1.0,
        comfort_weight: float = 0.5,
        seed: int = 0,
    ) -> None:
        self.model = model
        self.horizon = int(horizon)
        self.num_samples = int(num_samples)
        self.num_iterations = int(num_iterations)
        self.elite_fraction = float(elite_fraction)
        self.energy_weight = float(energy_weight)
        self.comfort_weight = float(comfort_weight)
        self.seed = int(seed)
        self.rng = np.random.default_rng(self.seed)
        self.num_rollouts = 0  # number of model rollouts (NOT env steps)
        self.num_predictions = 0  # number of model prediction calls
        self._frames: List[np.ndarray] = []  # recent observation frames

    # ------------------------------------------------------------------
    def reset(self) -> None:
        """Forget the observation history (call between episodes)."""

        self._frames = []

    def _history(self, observation: np.ndarray) -> np.ndarray:
        """Stack the last ``model.stack`` frames, newest last."""

        self._frames.append(np.asarray(observation, dtype=np.float64).copy())
        if len(self._frames) > self.model.stack:
            self._frames = self._frames[-self.model.stack :]
        frames = list(self._frames)
        if len(frames) < self.model.stack:
            frames = [frames[0]] * (self.model.stack - len(frames)) + frames
        return np.asarray(frames, dtype=np.float64).reshape(1, self.model.stack, self.model.obs_dim)

    def _cost(self, history: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """Roll the model forward and score a batch of action sequences."""

        total = np.zeros(history.shape[0], dtype=np.float64)
        current_history = history
        for step in range(self.horizon):
            action = actions[:, step, :]
            prediction = self.model.predict(current_history, action)
            self.num_predictions += 1
            total += self.energy_weight * energy_from_observation(prediction)
            total += self.comfort_weight * violation_from_observation(prediction)
            current_history = np.concatenate(
                [current_history[:, 1:, :], prediction[:, None, :]], axis=1
            )
        return total

    def plan(self, observation: Sequence[float]) -> np.ndarray:
        """Return the action to execute for ``observation`` (model only)."""

        history = self._history(observation)
        n_actions = self.model.n_actions
        horizon = self.horizon
        n_samples = self.num_samples

        mean = np.zeros((horizon, n_actions), dtype=np.float64)
        std = np.full((horizon, n_actions), 0.5, dtype=np.float64)
        n_elite = max(1, int(round(self.elite_fraction * n_samples)))

        best_action = np.zeros(n_actions, dtype=np.float64)
        best_cost = np.inf
        for _ in range(self.num_iterations):
            noise = self.rng.normal(size=(n_samples, horizon, n_actions))
            candidates = np.clip(mean + std * noise, -1.0, 1.0)
            states = np.repeat(history, n_samples, axis=0)
            costs = self._cost(states, candidates)
            self.num_rollouts += n_samples
            elite_index = np.argsort(costs)[:n_elite]
            elites = candidates[elite_index]
            mean = elites.mean(axis=0)
            std = np.maximum(elites.std(axis=0), 0.05)
            if float(costs[elite_index[0]]) < best_cost:
                best_cost = float(costs[elite_index[0]])
                # first action of the best candidate sequence
                best_action = elites[0][0].copy()

        return best_action.astype(np.float32)


def collect_transitions(
    env: Any,
    num_steps: int,
    rng: np.random.Generator,
    action_low: float = -1.0,
    action_high: float = 1.0,
) -> TransitionBatch:
    """Collect ``num_steps`` real-environment transitions with random actions.

    Every call of ``env.step`` is one *real* environment step and is
    counted in the returned batch length; the caller is responsible for
    keeping the total within the issue-#4 budget of 1,000 steps.

    The exploration policy is a mixture of uniform random actions and
    "do nothing", so the model sees the whole action range (both HVAC
    directions) as well as the passive behaviour of the building.
    """

    observations: List[np.ndarray] = []
    actions: List[np.ndarray] = []
    next_observations: List[np.ndarray] = []
    energies: List[float] = []
    violations: List[float] = []

    observation, _ = env.reset()
    n_actions = int(getattr(env, "n_buildings", 1))
    steps = 0
    while steps < int(num_steps):
        if rng.random() < 0.2:
            action = np.zeros(n_actions, dtype=np.float64)
        else:
            action = rng.uniform(action_low, action_high, size=n_actions)
        next_observation, _, terminated, truncated, info = env.step(action)
        observations.append(np.asarray(observation, dtype=np.float64).copy())
        actions.append(np.asarray(action, dtype=np.float64).copy())
        next_observations.append(np.asarray(next_observation, dtype=np.float64).copy())
        energies.append(float(info["energy_kwh"]))
        violations.append(float(info["comfort_violation_c"]))
        steps += 1
        observation = next_observation
        if terminated or truncated:
            observation, _ = env.reset()

    return TransitionBatch(
        observations=np.asarray(observations, dtype=np.float64),
        actions=np.asarray(actions, dtype=np.float64),
        next_observations=np.asarray(next_observations, dtype=np.float64),
        energies=np.asarray(energies, dtype=np.float64),
        violations=np.asarray(violations, dtype=np.float64),
    )

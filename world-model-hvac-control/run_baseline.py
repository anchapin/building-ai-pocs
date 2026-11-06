"""Model-free baseline harness for POC #4 (world-model HVAC control, slice 1).

Trains a model-free RL controller (stable-baselines3 **SAC**) on ONE CityLearn
building / climate and writes a results JSON with energy, comfort violations,
timesteps, seed and the full configuration.

Why SAC and not PPO: the HVAC action is a continuous power fraction
(``[-1, 1]``), SAC is the off-policy algorithm CityLearn itself ships as a
reference baseline (``citylearn.agents.sac``), and SAC re-uses its replay
buffer, which is the property that matters later: the world-model + MPC
controller of slice 3 is compared against the *same* environment-step budget.

This is a **smoke** harness: it proves the loop works end to end. The
multi-seed sweep and the held-out (unseen building / climate) evaluation are
slice 2 -- see ``REPORT.md`` for the protocol.

Example
-------
    python run_baseline.py --building Building_1 --timesteps 2000 --seed 0 \\
        --out results/
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citylearn_env import CityLearnHVACEnv, FixedSetpointController  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Train the model-free (SAC) baseline on one CityLearn building.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", default="baeda_3dem", help="CityLearn data set name")
    parser.add_argument("--building", default="Building_1", help="building inside the data set")
    parser.add_argument("--timesteps", type=int, default=2000, help="environment steps used for training")
    parser.add_argument("--seed", type=int, default=0, help="random seed")
    parser.add_argument("--out", default="results", help="output directory for the results JSON")
    parser.add_argument("--run-name", default=None, help="name of the results file (without extension)")
    parser.add_argument("--episode-time-steps", type=int, default=24, help="time steps per episode")
    parser.add_argument("--eval-episodes", type=int, default=2, help="episodes used to evaluate the trained policy")
    parser.add_argument("--energy-weight", type=float, default=1.0, help="reward weight on energy [kWh]")
    parser.add_argument("--comfort-weight", type=float, default=0.5, help="reward weight on comfort violation [degC]")
    parser.add_argument("--buffer-size", type=int, default=10000, help="SAC replay buffer size")
    parser.add_argument("--learning-starts", type=int, default=100, help="SAC steps collected before learning starts")
    parser.add_argument("--batch-size", type=int, default=64, help="SAC minibatch size")
    parser.add_argument("--learning-rate", type=float, default=3e-4, help="SAC learning rate")
    parser.add_argument("--gamma", type=float, default=0.99, help="SAC discount factor")
    parser.add_argument("--quiet", action="store_true", help="do not print the progress bar")
    return parser


def set_global_seed(seed: int) -> None:
    """Seed every RNG that can influence the run."""

    import random

    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    torch.set_num_threads(1)


def evaluate_policy(env: CityLearnHVACEnv, model: Any, episodes: int) -> Dict[str, Any]:
    """Roll the trained policy out deterministically and summarise the episode."""

    energies: List[float] = []
    violations: List[int] = []
    violation_degrees: List[float] = []
    steps = 0
    for _ in range(max(1, int(episodes))):
        observation, _ = env.reset()
        episode_energy = 0.0
        episode_violation_degrees = 0.0
        episode_violations = 0
        while True:
            action, _ = model.predict(observation, deterministic=True)
            observation, _, terminated, truncated, info = env.step(action)
            episode_energy += float(info["energy_kwh"])
            episode_violation_degrees += float(info["comfort_violation_c"])
            episode_violations += int(bool(info["comfort_violation"]))
            steps += 1
            if terminated or truncated:
                break
        energies.append(episode_energy)
        violations.append(episode_violations)
        violation_degrees.append(episode_violation_degrees)
    return {
        "episodes": len(energies),
        "steps": steps,
        "energy_kwh_mean": float(np.mean(energies)),
        "energy_kwh_total": float(np.sum(energies)),
        "comfort_violations_mean": float(np.mean(violations)),
        "comfort_violations_total": int(np.sum(violations)),
        "comfort_violation_c_mean": float(np.mean(violation_degrees)),
    }


def evaluate_rule_based(env: CityLearnHVACEnv, episodes: int) -> Dict[str, Any]:
    """Reference rule-based controller (fixed set point) on the same episodes."""

    controller = FixedSetpointController()
    energies: List[float] = []
    violations: List[int] = []
    violation_degrees: List[float] = []
    steps = 0
    for _ in range(max(1, int(episodes))):
        observation, _ = env.reset()
        episode_energy = 0.0
        episode_violation_degrees = 0.0
        episode_violations = 0
        while True:
            action = controller.act(observation)
            observation, _, terminated, truncated, info = env.step(action)
            episode_energy += float(info["energy_kwh"])
            episode_violation_degrees += float(info["comfort_violation_c"])
            episode_violations += int(bool(info["comfort_violation"]))
            steps += 1
            if terminated or truncated:
                break
        energies.append(episode_energy)
        violations.append(episode_violations)
        violation_degrees.append(episode_violation_degrees)
    return {
        "episodes": len(energies),
        "steps": steps,
        "energy_kwh_mean": float(np.mean(energies)),
        "energy_kwh_total": float(np.sum(energies)),
        "comfort_violations_mean": float(np.mean(violations)),
        "comfort_violations_total": int(np.sum(violations)),
        "comfort_violation_c_mean": float(np.mean(violation_degrees)),
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    set_global_seed(args.seed)

    from stable_baselines3 import SAC

    env = CityLearnHVACEnv(
        dataset=args.dataset,
        building=args.building,
        episode_time_steps=args.episode_time_steps,
        seed=args.seed,
        energy_weight=args.energy_weight,
        comfort_weight=args.comfort_weight,
    )

    model = SAC(
        "MlpPolicy",
        env,
        seed=args.seed,
        buffer_size=args.buffer_size,
        learning_starts=args.learning_starts,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        gamma=args.gamma,
        verbose=0,
        device="cpu",
    )

    start = time.time()
    model.learn(total_timesteps=int(args.timesteps), progress_bar=not args.quiet)
    wall_time = time.time() - start

    evaluation = evaluate_policy(env, model, args.eval_episodes)
    rule_based = evaluate_rule_based(env, args.eval_episodes)

    config = {
        "algo": "SAC",
        "library": "stable-baselines3",
        "dataset": args.dataset,
        "building": args.building,
        "episode_time_steps": args.episode_time_steps,
        "timesteps": int(args.timesteps),
        "seed": int(args.seed),
        "energy_weight": args.energy_weight,
        "comfort_weight": args.comfort_weight,
        "buffer_size": args.buffer_size,
        "learning_starts": args.learning_starts,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "gamma": args.gamma,
        "eval_episodes": args.eval_episodes,
        "observation_dim": int(env.observation_space.shape[0]),
        "action_dim": int(env.action_space.shape[0]),
        "building_ids": env.building_ids,
        "climate_id": env.climate_id,
    }

    results = {
        "run": config,
        "results": {"sac": evaluation, "rule_based_fixed_setpoint": rule_based},
        "runtime": {
            "wall_time_s": round(wall_time, 3),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "python": platform.python_version(),
        },
    }

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    run_name = args.run_name or f"baseline_sac_{args.dataset}_{args.building}_seed{args.seed}"
    out_path = os.path.join(out_dir, f"{run_name}.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"wrote {out_path}")
    print(
        f"{'controller':<28}{'energy_kwh/ep':>16}{'comfort viol./ep':>20}{'viol. [degC]/ep':>18}"
    )
    for name, block in (
        ("SAC (model-free baseline)", evaluation),
        ("rule-based fixed setpoint", rule_based),
    ):
        print(
            f"{name:<28}{block['energy_kwh_mean']:>16.3f}"
            f"{block['comfort_violations_mean']:>20.2f}{block['comfort_violation_c_mean']:>18.3f}"
        )
    print(f"train timesteps: {args.timesteps}  wall time: {wall_time:.1f} s  seed: {args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

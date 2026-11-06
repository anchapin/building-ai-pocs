"""Multi-seed SAC baseline sweep for POC #4 (world-model HVAC control, slice 2).

Trains the model-free SAC baseline on ONE (building, climate) train set at
>=3 seeds and evaluates every seed on the train set AND on each held-out
(unseen building / climate) set, with energy and comfort violations reported
separately. The world-model arm of slice 3 is compared against this sweep's
headline table, so the sweep fixes the protocol slice 3 must beat:

* training episodes use CityLearn's sequential windows (``start_step=0``),
  so the agent sees the whole year while training;
* evaluation replays ONE fixed window per set (``--eval-start-step`` > 0,
  ``--eval-episode-steps`` long), so every seed is scored on identical
  episodes and the numbers are comparable across seeds and controllers;
* the rule-based fixed-setpoint controller is evaluated on the same windows
  as a reference that needs no training.

Example
-------
    python run_sweep.py --dataset tx_travis_county_neighborhood \\
        --building Building_1 --timesteps 10000 --seeds 0,1,2 \\
        --eval-start-step 4368 --eval-episode-steps 168 \\
        --eval-on vt_chittenden_county_neighborhood:Building_1 \\
        --eval-on ca_alameda_county_neighborhood:Building_1 \\
        --out results/
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# CityLearn's battery-sizing data lives in the cache directory. The worktree
# cache (``<poc>/.cache``) already holds it (downloaded once from the
# CityLearn GitHub release); default to it so runs do not depend on the
# shared-egress GitHub API rate limit. An explicitly set XDG_CACHE_HOME wins.
os.environ.setdefault(
    "XDG_CACHE_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citylearn_env import CityLearnHVACEnv  # noqa: E402
from run_baseline import evaluate_policy, evaluate_rule_based, set_global_seed  # noqa: E402


def evaluate_constant(env: CityLearnHVACEnv, action_value: float, episodes: int) -> Dict[str, Any]:
    """Roll a CONSTANT action out and summarise it, same schema as the other evaluators.

    Slice 2 uses action 0.0 (do nothing) as the F3 reference: on the slice-1
    building the best controller was "do nothing", so a sweep window only
    counts as actionable if a controller beats do-nothing on comfort.
    """

    from citylearn_env import OBSERVATION_NAMES as _OBS_NAMES

    indoor_index = _OBS_NAMES.index("indoor_dry_bulb_temperature")
    energies: List[float] = []
    violations: List[int] = []
    violation_degrees: List[float] = []
    indoor_temperatures: List[float] = []
    steps = 0
    for _ in range(max(1, int(episodes))):
        observation, _ = env.reset()
        indoor_temperatures.append(float(observation[indoor_index]))
        action = np.full(env.n_buildings, float(action_value), dtype=np.float32)
        episode_energy = 0.0
        episode_violation_degrees = 0.0
        episode_violations = 0
        while True:
            observation, _, terminated, truncated, info = env.step(action)
            indoor_temperatures.append(float(observation[indoor_index]))
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
        "indoor_temperature_min_c": float(np.min(indoor_temperatures)),
        "indoor_temperature_max_c": float(np.max(indoor_temperatures)),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Multi-seed SAC baseline sweep with held-out evaluation (slice 2).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", default="baeda_3dem", help="train data set name")
    parser.add_argument("--building", default="Building_1", help="train building inside the data set")
    parser.add_argument("--timesteps", type=int, default=10000, help="environment steps used for training, per seed")
    parser.add_argument("--seeds", default="0,1,2", help="comma separated random seeds")
    parser.add_argument("--episode-time-steps", type=int, default=24, help="time steps per training episode")
    parser.add_argument(
        "--eval-start-step",
        type=int,
        default=0,
        help="first time step of the fixed evaluation window (0 = sequential windows, as in training)",
    )
    parser.add_argument(
        "--eval-episode-steps",
        type=int,
        default=168,
        help="time steps per evaluation episode (the fixed window length)",
    )
    parser.add_argument(
        "--eval-on",
        action="append",
        default=[],
        metavar="DATASET:BUILDING",
        help="held-out set to evaluate on (repeatable); the train set is always evaluated too",
    )
    parser.add_argument("--energy-weight", type=float, default=1.0, help="reward weight on energy [kWh]")
    parser.add_argument("--comfort-weight", type=float, default=0.5, help="reward weight on comfort violation [degC]")
    parser.add_argument("--buffer-size", type=int, default=10000, help="SAC replay buffer size")
    parser.add_argument("--learning-starts", type=int, default=100, help="SAC steps collected before learning starts")
    parser.add_argument("--batch-size", type=int, default=64, help="SAC minibatch size")
    parser.add_argument("--learning-rate", type=float, default=3e-4, help="SAC learning rate")
    parser.add_argument("--gamma", type=float, default=0.99, help="SAC discount factor")
    parser.add_argument("--out", default="results", help="output directory for the sweep JSON")
    parser.add_argument("--run-name", default=None, help="name of the sweep file (without extension)")
    parser.add_argument("--quiet", action="store_true", help="do not print the progress bar")
    return parser


def parse_eval_target(spec: str) -> Tuple[str, str]:
    """Parse a ``DATASET:BUILDING`` held-out spec."""

    if ":" not in spec:
        raise ValueError(f"expected DATASET:BUILDING, got {spec!r}")
    dataset, building = spec.split(":", 1)
    return dataset.strip(), building.strip()


def _mean_std(values: List[float]) -> Dict[str, float]:
    return {"mean": float(np.mean(values)), "std": float(np.std(values)), "n": len(values)}


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip() != ""]
    if len(seeds) < 1:
        raise ValueError("--seeds must list at least one seed")

    from stable_baselines3 import SAC

    held_out = [parse_eval_target(spec) for spec in args.eval_on]
    eval_sets = [(args.dataset, args.building)] + held_out

    config = {
        "algo": "SAC",
        "library": "stable-baselines3",
        "train_dataset": args.dataset,
        "train_building": args.building,
        "episode_time_steps": int(args.episode_time_steps),
        "eval_start_step": int(args.eval_start_step),
        "eval_episode_steps": int(args.eval_episode_steps),
        "eval_sets": [f"{d}:{b}" for d, b in eval_sets],
        "timesteps_per_seed": int(args.timesteps),
        "seeds": seeds,
        "energy_weight": args.energy_weight,
        "comfort_weight": args.comfort_weight,
        "buffer_size": args.buffer_size,
        "learning_starts": args.learning_starts,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "gamma": args.gamma,
    }

    per_seed: Dict[str, Any] = {}
    overall_start = time.time()
    for seed in seeds:
        set_global_seed(seed)
        train_env = CityLearnHVACEnv(
            dataset=args.dataset,
            building=args.building,
            episode_time_steps=args.episode_time_steps,
            start_step=0,
            seed=seed,
            energy_weight=args.energy_weight,
            comfort_weight=args.comfort_weight,
        )
        model = SAC(
            "MlpPolicy",
            train_env,
            seed=seed,
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
        train_wall_time = time.time() - start

        seed_results: Dict[str, Any] = {"train_wall_time_s": round(train_wall_time, 3)}
        for dataset, building in eval_sets:
            eval_env = CityLearnHVACEnv(
                dataset=dataset,
                building=building,
                episode_time_steps=args.eval_episode_steps,
                start_step=args.eval_start_step,
                seed=seed,
                energy_weight=args.energy_weight,
                comfort_weight=args.comfort_weight,
            )
            # A fixed evaluation window replays identically on every reset,
            # so one episode is the whole evaluation for that window.
            episodes = 1 if args.eval_start_step > 0 else 2
            seed_results[f"{dataset}:{building}"] = {
                "sac": evaluate_policy(eval_env, model, episodes),
                "rule_based_fixed_setpoint": evaluate_rule_based(eval_env, episodes),
                "do_nothing": evaluate_constant(eval_env, 0.0, episodes),
            }
            eval_env.close()
        train_env.close()
        per_seed[str(seed)] = seed_results
        print(f"[seed {seed}] train {train_wall_time:.1f} s; evaluated on {len(eval_sets)} set(s)")

    headline: Dict[str, Any] = {}
    for dataset, building in eval_sets:
        key = f"{dataset}:{building}"
        for controller in ("sac", "rule_based_fixed_setpoint", "do_nothing"):
            energies = [per_seed[str(s)][key][controller]["energy_kwh_mean"] for s in seeds]
            violations = [per_seed[str(s)][key][controller]["comfort_violations_mean"] for s in seeds]
            violation_degrees = [
                per_seed[str(s)][key][controller]["comfort_violation_c_mean"] for s in seeds
            ]
            indoor_min = [per_seed[str(s)][key][controller]["indoor_temperature_min_c"] for s in seeds]
            indoor_max = [per_seed[str(s)][key][controller]["indoor_temperature_max_c"] for s in seeds]
            headline[f"{key}::{controller}"] = {
                "energy_kwh_per_episode": _mean_std(energies),
                "comfort_violations_per_episode": _mean_std(violations),
                "comfort_violation_c_per_episode": _mean_std(violation_degrees),
                "indoor_temperature_min_c": min(indoor_min),
                "indoor_temperature_max_c": max(indoor_max),
            }

    results = {
        "run": config,
        "per_seed": per_seed,
        "headline": headline,
        "runtime": {
            "wall_time_s": round(time.time() - overall_start, 3),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "python": platform.python_version(),
        },
    }

    out_dir = os.path.abspath(args.out)
    os.makedirs(out_dir, exist_ok=True)
    run_name = args.run_name or (
        f"sweep_sac_{args.dataset}_{args.building}_"
        f"s{'-'.join(str(s) for s in seeds)}"
    )
    out_path = os.path.join(out_dir, f"{run_name}.json")
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2, sort_keys=True)
        handle.write("\n")

    print(f"\nwrote {out_path}")
    print(
        f"{'set :: controller':<58}{'energy kWh/ep':>16}"
        f"{'comfort viol./ep':>20}{'viol. [degC]/ep':>18}"
    )
    for key, block in headline.items():
        energy = block["energy_kwh_per_episode"]
        violations = block["comfort_violations_per_episode"]
        degrees = block["comfort_violation_c_per_episode"]
        print(
            f"{key:<58}{energy['mean']:>10.3f} ± {energy['std']:<5.3f}"
            f"{violations['mean']:>14.2f} ± {violations['std']:<5.2f}"
            f"{degrees['mean']:>12.3f} ± {degrees['std']:<5.3f}"
        )
    print(f"train timesteps/seed: {args.timesteps}  seeds: {seeds}  wall time: {time.time() - overall_start:.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

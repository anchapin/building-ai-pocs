"""World-model + MPC arm for POC #4 (slice 3).

Runs the learned-world-model controller against the *committed* slice-2
SAC sweep headline on the SAME fixed sets and the SAME June window:

* train set (in-distribution): ``tx_travis_county_neighborhood`` /
  ``resstock-amy2018-2021-release-1-102188``;
* held-out sets (unseen buildings AND unseen climates):
  ``vt_chittenden_county_neighborhood`` /
  ``resstock-amy2018-2021-release-1-102188``-style RESStock Vermont
  building ``resstock-amy2018-2021-release-1-112208`` and
  ``ca_alameda_county_neighborhood`` /
  ``resstock-amy2018-2021-release-1-102040``;
* evaluation window: start step 4368, 168 nominal steps (167 transitions).

The issue-#4 budget is **1,000 real-environment steps** for the whole
world-model arm.  Every real step is counted here: the training
transitions AND the evaluation rollouts.  Model rollouts inside the
planner are NOT environment steps and are counted separately.

Example
-------
    python run_world_model.py --dataset tx_travis_county_neighborhood \\
        --building resstock-amy2018-2021-release-1-102188 \\
        --seeds 0,1,2 --train-steps 320 --heldout-steps 80 \\
        --eval-start-step 4368 --eval-episode-steps 168 \\
        --eval-on vt_chittenden_county_neighborhood:resstock-amy2018-2021-release-1-112208 \\
        --eval-on ca_alameda_county_neighborhood:resstock-amy2018-2021-release-1-102040 \\
        --out results --quiet
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citylearn_env import CityLearnHVACEnv  # noqa: E402
from world_model import (  # noqa: E402
    MPCController,
    TransitionBatch,
    WorldModel,
    collect_transitions,
)

# The issue-#4 budget: real-environment steps per seed (training + evaluation).
ENV_STEP_BUDGET = 1000

# Windows (start step inside the data set) used by the "year" training arm:
# four spread-out weeks, none of which is the June evaluation window, so the
# in-distribution evaluation is not scored on data the model was fitted on.
YEAR_WINDOWS: Tuple[int, ...] = (0, 2904, 5832, 8000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="World-model + MPC transfer evaluation (slice 3).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--dataset", default="tx_travis_county_neighborhood", help="train data set")
    parser.add_argument(
        "--building",
        default="resstock-amy2018-2021-release-1-102188",
        help="train building inside the train data set",
    )
    parser.add_argument("--seeds", default="0,1,2", help="comma separated random seeds")
    parser.add_argument(
        "--train-steps",
        type=int,
        default=320,
        help="real-environment steps collected for fitting the model, per seed",
    )
    parser.add_argument(
        "--heldout-steps",
        type=int,
        default=80,
        help="real-environment steps collected for the held-out diagnostic split, per seed",
    )
    parser.add_argument(
        "--train-window",
        choices=("june", "year"),
        default="june",
        help="'june': collect training transitions on the evaluation window of the "
        "train set; 'year': collect them on four spread-out windows of the train "
        "set's year (no overlap with the evaluation window)",
    )
    parser.add_argument(
        "--eval-start-step", type=int, default=4368, help="first step of the fixed evaluation window"
    )
    parser.add_argument(
        "--eval-episode-steps", type=int, default=168, help="nominal steps of the evaluation window"
    )
    parser.add_argument(
        "--eval-on",
        action="append",
        default=[],
        metavar="DATASET:BUILDING",
        help="held-out set to evaluate on (repeatable); the train set is always evaluated too",
    )
    parser.add_argument("--horizon", type=int, default=12, help="MPC planning horizon (steps)")
    parser.add_argument("--num-samples", type=int, default=64, help="CEM candidates per iteration")
    parser.add_argument("--num-iterations", type=int, default=4, help="CEM refinement iterations")
    parser.add_argument("--train-iterations", type=int, default=2000, help="gradient steps of the world model")
    parser.add_argument("--learning-rate", type=float, default=1e-3, help="world-model learning rate")
    parser.add_argument("--hidden", type=int, default=128, help="hidden layer width of the world model")
    parser.add_argument(
        "--stack", type=int, default=3, help="number of past observation frames fed to the model"
    )
    parser.add_argument("--energy-weight", type=float, default=1.0, help="planning cost weight on energy")
    parser.add_argument("--comfort-weight", type=float, default=0.5, help="planning cost weight on comfort")
    parser.add_argument(
        "--sac-sweep",
        default=os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "results",
            "sweep_sac_tx_travis_county_neighborhood_resstock-amy2018-2021-release-1-102188_s0-1-2.json",
        ),
        help="committed slice-2 SAC sweep JSON used as the comparison baseline",
    )
    parser.add_argument("--out", default="results", help="output directory for the result JSON")
    parser.add_argument("--run-name", default=None, help="name of the result file (without extension)")
    parser.add_argument("--quiet", action="store_true", help="do not print the progress output")
    return parser


def parse_eval_target(spec: str) -> Tuple[str, str]:
    """Parse a ``DATASET:BUILDING`` held-out spec."""

    if ":" not in spec:
        raise ValueError(f"expected DATASET:BUILDING, got {spec!r}")
    dataset, building = spec.split(":", 1)
    return dataset.strip(), building.strip()


def _mean_std(values: Sequence[float]) -> Dict[str, Any]:
    values = [float(v) for v in values]
    return {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "n": len(values),
        "values": values,
    }


def make_env(dataset: str, building: str, start_step: int, episode_steps: int, seed: int):
    return CityLearnHVACEnv(
        dataset=dataset,
        building=building,
        episode_time_steps=int(episode_steps),
        start_step=int(start_step),
        seed=int(seed),
        solar_generation=False,
    )


def collect_training_data(
    dataset: str,
    building: str,
    train_window: str,
    eval_start_step: int,
    eval_episode_steps: int,
    train_steps: int,
    heldout_steps: int,
    seed: int,
) -> Tuple[TransitionBatch, TransitionBatch, int]:
    """Collect the training and held-out transitions (real environment steps).

    Returns ``(train_batch, heldout_batch, env_steps)``.  The two splits
    are collected with *different* random streams, so the held-out split
    is not simply the tail of the training data.
    """

    rng_train = np.random.default_rng(seed * 1000 + 11)
    rng_heldout = np.random.default_rng(seed * 1000 + 29)

    if train_window == "june":
        env = make_env(dataset, building, eval_start_step, eval_episode_steps, seed)
        try:
            train_batch = collect_transitions(env, train_steps, rng_train)
            heldout_batch = collect_transitions(env, heldout_steps, rng_heldout)
        finally:
            env.close()
    else:
        # Spread the (small) training budget over four windows of the year.
        windows = YEAR_WINDOWS
        per_window_train = max(1, train_steps // len(windows))
        per_window_heldout = max(1, heldout_steps // len(windows))
        train_parts: List[TransitionBatch] = []
        heldout_parts: List[TransitionBatch] = []
        for index, window in enumerate(windows):
            env = make_env(dataset, building, window, eval_episode_steps, seed + index)
            try:
                train_parts.append(collect_transitions(env, per_window_train, rng_train))
                heldout_parts.append(collect_transitions(env, per_window_heldout, rng_heldout))
            finally:
                env.close()
        train_batch = TransitionBatch.concatenate(train_parts)
        heldout_batch = TransitionBatch.concatenate(heldout_parts)

    env_steps = len(train_batch) + len(heldout_batch)
    return train_batch, heldout_batch, env_steps


def evaluate_mpc(env: CityLearnHVACEnv, controller: MPCController) -> Dict[str, Any]:
    """Run one MPC episode in the real environment (model-only planning)."""

    from citylearn_env import OBSERVATION_NAMES as _NAMES

    indoor_index = _NAMES.index("indoor_dry_bulb_temperature")
    controller.reset()
    observation, _ = env.reset()
    energy = 0.0
    violation_degrees = 0.0
    violations = 0
    steps = 0
    indoor: List[float] = [float(observation[indoor_index])]
    actions: List[float] = []
    while True:
        action = controller.plan(observation)
        observation, _, terminated, truncated, info = env.step(action)
        energy += float(info["energy_kwh"])
        violation_degrees += float(info["comfort_violation_c"])
        violations += int(bool(info["comfort_violation"]))
        actions.append(float(np.mean(action)))
        indoor.append(float(observation[indoor_index]))
        steps += 1
        if terminated or truncated:
            break
    return {
        "episodes": 1,
        "steps": steps,
        "energy_kwh_mean": float(energy),
        "energy_kwh_total": float(energy),
        "comfort_violations_mean": float(violations),
        "comfort_violations_total": int(violations),
        "comfort_violation_c_mean": float(violation_degrees),
        "indoor_temperature_min_c": float(np.min(indoor)),
        "indoor_temperature_max_c": float(np.max(indoor)),
        "mean_action": float(np.mean(actions)),
        "model_rollouts": int(controller.num_rollouts),
        "model_predictions": int(controller.num_predictions),
    }


def _load_sac_reference(path: str) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def sac_reference_rows(payload: Dict[str, Any], controller: str = "sac") -> Dict[str, Dict[str, Any]]:
    """Return ``{set_id: {mean, std, per-seed values}}`` for one controller."""

    rows: Dict[str, Dict[str, Any]] = {}
    per_seed = payload.get("per_seed", {})
    set_ids = set()
    for seed in sorted(per_seed):
        seed_block = per_seed[seed]
        if not isinstance(seed_block, dict):
            continue
        for set_id, block in seed_block.items():
            if isinstance(block, dict) and controller in block:
                set_ids.add(set_id)
    for set_id in sorted(set_ids):
        values = []
        comfort = []
        for seed in sorted(per_seed):
            seed_block = per_seed[seed]
            if not isinstance(seed_block, dict):
                continue
            block = seed_block.get(set_id, {}).get(controller)
            if block is None:
                continue
            values.append(float(block["energy_kwh_mean"]))
            comfort.append(float(block["comfort_violation_c_mean"]))
        if not values:
            continue
        rows[set_id] = {
            "energy_kwh": _mean_std(values),
            "comfort_violation_c": _mean_std(comfort),
        }
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip() != ""]
    if not seeds:
        raise ValueError("--seeds must list at least one seed")

    held_out = [parse_eval_target(spec) for spec in args.eval_on]
    eval_sets = [(args.dataset, args.building)] + held_out

    start_time = time.time()
    per_seed: Dict[str, Any] = {}
    headline: Dict[str, Any] = {}

    for seed in seeds:
        seed_start = time.time()
        train_batch, heldout_batch, train_env_steps = collect_training_data(
            dataset=args.dataset,
            building=args.building,
            train_window=args.train_window,
            eval_start_step=args.eval_start_step,
            eval_episode_steps=args.eval_episode_steps,
            train_steps=args.train_steps,
            heldout_steps=args.heldout_steps,
            seed=seed,
        )

        model = WorldModel(
            obs_dim=train_batch.observations.shape[1],
            n_actions=train_batch.actions.shape[1],
            hidden=args.hidden,
            stack=args.stack,
            seed=seed,
        )
        fit_info = model.fit(
            train_batch,
            iterations=args.train_iterations,
            learning_rate=args.learning_rate,
        )
        diagnostic = model.one_step_error(heldout_batch)

        seed_block: Dict[str, Any] = {
            "world_model": {
                "architecture": "MLP latent dynamics (obs, action) -> next obs",
                "obs_dim": int(model.obs_dim),
                "n_actions": int(model.n_actions),
                "hidden": int(args.hidden),
                "stack": int(args.stack),
                "fit": fit_info,
                "heldout_one_step_error": diagnostic,
                "train_env_steps": int(train_env_steps),
            },
            "sets": {},
        }

        eval_env_steps = 0
        for dataset, building in eval_sets:
            controller = MPCController(
                model,
                horizon=args.horizon,
                num_samples=args.num_samples,
                num_iterations=args.num_iterations,
                energy_weight=args.energy_weight,
                comfort_weight=args.comfort_weight,
                seed=seed,
            )
            env = make_env(dataset, building, args.eval_start_step, args.eval_episode_steps, seed)
            try:
                summary = evaluate_mpc(env, controller)
            finally:
                env.close()
            eval_env_steps += int(summary["steps"])
            set_id = f"{dataset}:{building}"
            seed_block["sets"][set_id] = summary
            if not args.quiet:
                print(
                    f"[seed {seed}] {set_id}: energy {summary['energy_kwh_mean']:.3f} kWh, "
                    f"comfort {summary['comfort_violation_c_mean']:.1f} degC, "
                    f"steps {summary['steps']}"
                )

        total_env_steps = train_env_steps + eval_env_steps
        seed_block["env_steps"] = {
            "training_collection": int(train_env_steps),
            "evaluation_rollouts": int(eval_env_steps),
            "total": int(total_env_steps),
            "budget": int(ENV_STEP_BUDGET),
            "within_budget": bool(total_env_steps <= ENV_STEP_BUDGET),
        }
        seed_block["wall_time_s"] = float(time.time() - seed_start)
        per_seed[str(seed)] = seed_block

        if total_env_steps > ENV_STEP_BUDGET:
            raise RuntimeError(
                f"seed {seed} used {total_env_steps} real environment steps, "
                f"above the issue-#4 budget of {ENV_STEP_BUDGET}"
            )

    # -- headline table -------------------------------------------------
    sac_payload = _load_sac_reference(args.sac_sweep) if os.path.isfile(args.sac_sweep) else {}
    sac_rows = sac_reference_rows(sac_payload) if sac_payload else {}

    for set_id in sorted({key for seed in per_seed for key in per_seed[seed]["sets"]}):
        energies = [per_seed[seed]["sets"][set_id]["energy_kwh_mean"] for seed in per_seed]
        comfort = [per_seed[seed]["sets"][set_id]["comfort_violation_c_mean"] for seed in per_seed]
        violations = [per_seed[seed]["sets"][set_id]["comfort_violations_mean"] for seed in per_seed]
        block: Dict[str, Any] = {
            "energy_kwh_per_episode": _mean_std(energies),
            "comfort_violation_c_per_episode": _mean_std(comfort),
            "comfort_violations_per_episode": _mean_std(violations),
        }
        sac_row = sac_rows.get(set_id)
        if sac_row is not None:
            sac_energy = sac_row["energy_kwh"]["mean"]
            sac_comfort = sac_row["comfort_violation_c"]["mean"]
            mpc_energy = block["energy_kwh_per_episode"]["mean"]
            mpc_comfort = block["comfort_violation_c_per_episode"]["mean"]
            percent = 100.0 * (mpc_energy - sac_energy) / sac_energy if sac_energy else float("nan")
            comfort_equal = bool(mpc_comfort <= sac_comfort + 1e-9)
            block["sac_reference"] = {
                "energy_kwh_per_episode": sac_row["energy_kwh"],
                "comfort_violation_c_per_episode": sac_row["comfort_violation_c"],
            }
            block["vs_sac"] = {
                "energy_percent_difference": float(percent),
                "comfort_equal": comfort_equal,
                "comfort_percent_difference": float(
                    100.0 * (mpc_comfort - sac_comfort) / sac_comfort if sac_comfort else float("nan")
                ),
                "gate_energy_win_at_equal_comfort": bool(comfort_equal and percent <= -5.0),
            }
        headline[set_id] = block

    payload = {
        "run": {
            "algo": "world model (MLP latent dynamics) + CEM shooting MPC",
            "library": "numpy + torch",
            "train_dataset": args.dataset,
            "train_building": args.building,
            "train_window": args.train_window,
            "eval_start_step": int(args.eval_start_step),
            "eval_episode_steps": int(args.eval_episode_steps),
            "eval_sets": [f"{d}:{b}" for d, b in eval_sets],
            "seeds": seeds,
            "train_steps_per_seed": int(args.train_steps),
            "heldout_steps_per_seed": int(args.heldout_steps),
            "env_step_budget": int(ENV_STEP_BUDGET),
            "horizon": int(args.horizon),
            "num_samples": int(args.num_samples),
            "num_iterations": int(args.num_iterations),
            "energy_weight": float(args.energy_weight),
            "comfort_weight": float(args.comfort_weight),
            "sac_reference_file": os.path.basename(args.sac_sweep),
        },
        "per_seed": per_seed,
        "headline": headline,
        "runtime": {
            "python": platform.python_version(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "wall_time_s": float(time.time() - start_time),
        },
    }

    os.makedirs(args.out, exist_ok=True)
    run_name = args.run_name or (
        f"worldmodel_{args.train_window}_{args.dataset}_{args.building}_s{'-'.join(str(s) for s in seeds)}"
    )
    path = os.path.join(args.out, f"{run_name}.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)

    # -- printed table ---------------------------------------------------
    print("")
    print("world-model + MPC transfer table (June window, 167 steps/episode)")
    print(f"{'set':<70} {'energy kWh/ep':>16} {'comfort degC/ep':>18} {'% vs SAC':>10}")
    for set_id in sorted(headline):
        block = headline[set_id]
        energy = block["energy_kwh_per_episode"]
        comfort = block["comfort_violation_c_per_episode"]
        comparison = block.get("vs_sac", {})
        percent = comparison.get("energy_percent_difference")
        percent_text = f"{percent:+.1f}%" if percent is not None else "n/a"
        print(
            f"{set_id:<70} {energy['mean']:>7.3f} +/- {energy['std']:>4.3f} "
            f"{comfort['mean']:>10.1f} +/- {comfort['std']:>5.1f} {percent_text:>10}"
        )
    env_steps = [per_seed[seed]["env_steps"]["total"] for seed in per_seed]
    print(f"real environment steps per seed: {min(env_steps)}-{max(env_steps)} "
          f"(budget {ENV_STEP_BUDGET})")
    print(f"results written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

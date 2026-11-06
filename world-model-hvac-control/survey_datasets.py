"""Survey candidate CityLearn data sets / buildings for HVAC responsiveness.

Why this exists
---------------
Slice 1 of POC #4 found three blocking findings (F1--F3 in ``REPORT.md``):

* **F1** -- on ``baeda_3dem`` / ``Building_1`` the net-electricity metric
  does not move at all when the HVAC action changes (0.567642 kWh for
  action 0, full heat and full cool alike), so a sweep on that building
  measures nothing.
* **F2** -- ``baeda_3dem`` is cooling-only (``heating_device.nominal_power``
  is 0.0), so the heating half of the action contract is a no-op there.
* **F3** -- the comfort set points at the start of the data set are
  degenerate (30 / 30 degC), so no controller can improve comfort.

This script answers those questions empirically: for every candidate data
set / building it runs short **constant-action** rollouts (action 0, full
heat, full cool) through the very same :class:`CityLearnHVACEnv` the RL
harness uses, and prints one row per building with

* the heating / cooling device ``nominal_power`` (is the device actuated?),
* the net electricity [kWh] under each constant action,
* the cooling / heating demand [kWh] under each constant action,
* the heating / cooling set point range and the indoor temperature range
  over the episode window.

A building is *responsive* when the spread between the actions is clearly
above numerical noise (see :func:`is_responsive`).

Example
-------
    python survey_datasets.py --episode-steps 24
    python survey_datasets.py --datasets baeda_3dem --out results/survey.json

Data sets are resolved through :func:`citylearn_env.resolve_dataset_schema`:
a local copy under ``data/datasets/<name>/`` is used when present, otherwise
CityLearn downloads the data set once into its cache directory. Either way
they are never committed to git. The local copies used by slice 2 were
extracted from the CityLearn v3.2.0 release tarball; re-fetching them is a
matter of re-running the download, not of any committed artifact.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

# CityLearn's battery-sizing data lives in the cache directory. The worktree
# cache (``<poc>/.cache``) already holds it (downloaded once from the
# CityLearn GitHub release); default to it so runs do not depend on the
# shared-egress GitHub API rate limit. An explicitly set XDG_CACHE_HOME wins.
os.environ.setdefault(
    "XDG_CACHE_HOME", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from citylearn_env import OBSERVATION_NAMES, CityLearnHVACEnv, resolve_dataset_schema  # noqa: E402

__all__ = [
    "CANDIDATE_DATASETS",
    "ACTIONS",
    "probe_building",
    "survey",
    "is_responsive",
    "format_table",
]

#: Candidate data sets from the slice-1 report.  ``None`` means "all
#: buildings of the data set" (the list is resolved lazily, after the data
#: set has been downloaded).
CANDIDATE_DATASETS: Sequence[Optional[str]] = (
    "baeda_3dem",
    "citylearn_challenge_2020_climate_zone_1",
    "citylearn_challenge_2020_climate_zone_2",
    "citylearn_challenge_2020_climate_zone_3",
    "citylearn_challenge_2020_climate_zone_4",
    "tx_travis_county_neighborhood",
    "vt_chittenden_county_neighborhood",
    "ca_alameda_county_neighborhood",
)

#: Constant actions probed on every building.
ACTIONS: Dict[str, float] = {"none": 0.0, "full_heat": 1.0, "full_cool": -1.0}

#: A spread below this is numerical noise, not a control effect.
NOISE_FLOOR_KWH = 1e-3

_OBS = {name: i for i, name in enumerate(OBSERVATION_NAMES)}


def _nominal_power(building: Any, device_name: str) -> float:
    """Return ``nominal_power`` of a building device (0.0 when absent)."""

    device = getattr(building, device_name, None)
    if device is None:
        return 0.0
    value = getattr(device, "nominal_power", 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _building_names(dataset: str) -> List[str]:
    """Return the building names of a CityLearn data set."""

    from citylearn.citylearn import CityLearnEnv  # local import: heavy

    env = CityLearnEnv(
        schema=resolve_dataset_schema(dataset),
        buildings=None,
        episode_time_steps=1,
        random_seed=0,
        central_agent=True,
    )
    try:
        return [str(building.name) for building in env.buildings]
    finally:
        env.close()


def probe_building(
    dataset: str,
    building: str,
    episode_steps: int = 24,
    seed: int = 0,
    start_step: int = 0,
) -> Dict[str, Any]:
    """Run constant-action rollouts on one building and summarise them.

    The three actions are scored on the SAME episode window: a fresh
    environment is constructed per action, because with ``start_step == 0``
    CityLearn advances to the next sequential window on every reset and
    reusing one env would confound action effects with day-to-day weather
    variation. With ``start_step > 0`` the wrapper pins the window anyway.

    Returns a dictionary with the schema of one table row; on failure the
    dictionary has ``"error"`` set and ``"ok": False``.
    """

    row: Dict[str, Any] = {
        "dataset": dataset,
        "building": building,
        "episode_steps": int(episode_steps),
        "start_step": int(start_step),
        "seed": int(seed),
        "ok": False,
    }

    def _new_env() -> CityLearnHVACEnv:
        # A FRESH environment per rollout: with start_step == 0 CityLearn
        # advances to the next sequential episode window on every reset, so
        # reusing one env would score the three actions on three DIFFERENT
        # days. A fresh env always starts at episode 0 (the same window);
        # with start_step > 0 the wrapper pins the window anyway.
        return CityLearnHVACEnv(
            dataset=dataset,
            building=building,
            episode_time_steps=int(episode_steps),
            seed=int(seed),
            start_step=int(start_step),
        )

    env = _new_env()
    try:
        sim_building = env.buildings[0]
        row["heating_nominal_power_kw"] = _nominal_power(sim_building, "heating_device")
        row["cooling_nominal_power_kw"] = _nominal_power(sim_building, "cooling_device")
        row["active_actions"] = [str(a) for a in getattr(sim_building, "active_actions", [])]
    finally:
        env.close()

    # Setpoint / indoor ranges accumulate over ALL three rollouts, so the
    # reported ranges describe the episode window, not one action only.
    indoor: List[float] = []
    heating_setpoints: List[float] = []
    cooling_setpoints: List[float] = []

    for action_name, action_value in ACTIONS.items():
        env = _new_env()
        try:
            observation, _ = env.reset()
            action = np.full(env.n_buildings, action_value, dtype=np.float32)
            energy = 0.0
            cooling_demand = 0.0
            heating_demand = 0.0
            steps = 0
            while True:
                observation, _, terminated, truncated, info = env.step(action)
                energy += float(info["energy_kwh"])
                cooling_demand += float(observation[_OBS["cooling_demand_kwh"]])
                heating_demand += float(observation[_OBS["heating_demand_kwh"]])
                indoor.append(float(observation[_OBS["indoor_dry_bulb_temperature"]]))
                heating_setpoints.append(float(observation[_OBS["heating_set_point"]]))
                cooling_setpoints.append(float(observation[_OBS["cooling_set_point"]]))
                steps += 1
                if terminated or truncated:
                    break

            row[f"net_electricity_kwh__{action_name}"] = energy
            row[f"cooling_demand_kwh__{action_name}"] = cooling_demand
            row[f"heating_demand_kwh__{action_name}"] = heating_demand
            row[f"steps__{action_name}"] = steps
        finally:
            env.close()

    row["indoor_temperature_min_c"] = min(indoor)
    row["indoor_temperature_max_c"] = max(indoor)
    row["heating_setpoint_min_c"] = min(heating_setpoints)
    row["heating_setpoint_max_c"] = max(heating_setpoints)
    row["cooling_setpoint_min_c"] = min(cooling_setpoints)
    row["cooling_setpoint_max_c"] = max(cooling_setpoints)

    net = [row[f"net_electricity_kwh__{name}"] for name in ACTIONS]
    thermal = [
        row[f"cooling_demand_kwh__{name}"] + row[f"heating_demand_kwh__{name}"] for name in ACTIONS
    ]
    row["net_electricity_spread_kwh"] = max(net) - min(net)
    row["thermal_demand_spread_kwh"] = max(thermal) - min(thermal)
    row["net_electricity_responsive"] = is_responsive(row["net_electricity_spread_kwh"])
    row["thermal_demand_responsive"] = is_responsive(row["thermal_demand_spread_kwh"])
    row["heating_actuated"] = bool(row["heating_nominal_power_kw"] > 0.0)
    row["ok"] = True

    return row


def is_responsive(spread_kwh: float, noise_floor: float = NOISE_FLOOR_KWH) -> bool:
    """Return whether an energy spread is above the numerical noise floor."""

    return bool(abs(float(spread_kwh)) > float(noise_floor))


def survey(
    datasets: Sequence[str],
    episode_steps: int = 24,
    seed: int = 0,
    start_step: int = 0,
    buildings: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    """Probe every building of every data set; failures are recorded, not fatal."""

    rows: List[Dict[str, Any]] = []
    for dataset in datasets:
        try:
            names = list(buildings) if buildings else _building_names(dataset)
        except Exception as exc:  # pragma: no cover - depends on network
            rows.append(
                {
                    "dataset": dataset,
                    "building": None,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[skip] {dataset}: failed to load data set ({type(exc).__name__}: {exc})")
            traceback.print_exc(file=sys.stdout)
            continue

        for name in names:
            try:
                row = probe_building(
                    dataset, name, episode_steps=episode_steps, seed=seed, start_step=start_step
                )
            except Exception as exc:  # pragma: no cover - depends on data set
                row = {
                    "dataset": dataset,
                    "building": name,
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                traceback.print_exc(file=sys.stdout)
            rows.append(row)
            print(f"[done] {dataset} / {name}")
    return rows


def format_table(rows: Sequence[Dict[str, Any]]) -> str:
    """Render the survey rows as a fixed-width table."""

    header = (
        f"{'dataset':<44}{'building':<14}{'heat kW':>9}{'cool kW':>9}"
        f"{'net@0':>9}{'net@heat':>10}{'net@cool':>10}{'spread':>10}"
        f"{'coolD@cool':>12}{'heatD@heat':>12}{'sp_min':>8}{'cp_min':>8}{'in_min':>8}"
    )
    lines = [header, "-" * len(header)]
    for row in rows:
        if not row.get("ok"):
            lines.append(f"{row.get('dataset', '?'):<44}{'-':<14}FAILED: {row.get('error', '?')}")
            continue
        lines.append(
            f"{row['dataset']:<44}{row['building']:<14}"
            f"{row['heating_nominal_power_kw']:>9.2f}{row['cooling_nominal_power_kw']:>9.2f}"
            f"{row['net_electricity_kwh__none']:>9.4f}"
            f"{row['net_electricity_kwh__full_heat']:>10.4f}"
            f"{row['net_electricity_kwh__full_cool']:>10.4f}"
            f"{row['net_electricity_spread_kwh']:>10.4f}"
            f"{row['cooling_demand_kwh__full_cool']:>12.4f}"
            f"{row['heating_demand_kwh__full_heat']:>12.4f}"
            f"{row['heating_setpoint_min_c']:>8.2f}{row['cooling_setpoint_min_c']:>8.2f}"
            f"{row['indoor_temperature_min_c']:>8.2f}"
        )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Survey CityLearn data sets / buildings: constant-action rollouts "
            "that show whether the energy metric responds to control."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--datasets",
        default=",".join(d for d in CANDIDATE_DATASETS if d),
        help="comma separated CityLearn data set names",
    )
    parser.add_argument("--buildings", default=None, help="comma separated building names (default: all)")
    parser.add_argument("--episode-steps", type=int, default=24, help="time steps per constant-action rollout")
    parser.add_argument("--start-step", type=int, default=0, help="first time step of the episode window")
    parser.add_argument("--seed", type=int, default=0, help="simulator seed")
    parser.add_argument("--out", default=None, help="optional path of a JSON file with the raw survey rows")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    datasets = [d.strip() for d in args.datasets.split(",") if d.strip()]
    buildings = (
        [b.strip() for b in args.buildings.split(",") if b.strip()] if args.buildings else None
    )

    rows = survey(
        datasets,
        episode_steps=args.episode_steps,
        seed=args.seed,
        start_step=args.start_step,
        buildings=buildings,
    )
    print()
    print(format_table(rows))

    if args.out:
        out_dir = os.path.dirname(os.path.abspath(args.out))
        os.makedirs(out_dir, exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "config": {
                        "datasets": datasets,
                        "buildings": buildings,
                        "episode_steps": args.episode_steps,
                        "start_step": args.start_step,
                        "seed": args.seed,
                        "noise_floor_kwh": NOISE_FLOOR_KWH,
                    },
                    "rows": rows,
                },
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
        print(f"wrote {args.out}")

    failures = [r for r in rows if not r.get("ok")]
    print(f"\nprobed {len(rows)} building(s); {len(failures)} failure(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

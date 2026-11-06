"""Benchmark the surrogate-vs-EnergyPlus speedup (issue #3, >=50x gate).

Measures, on this machine:
  * the surrogate: batched free-running PINN rollout of `--zones` zones
    x `--steps` hourly steps (default 5 x 8760, i.e. one annual run per
    zone), timed over `--trials` repeats (median reported);
  * EnergyPlus (only with --eplus-dir): the 5ZoneAirCooled full-year run
    against the Chicago TMY3 weather file shipped with the install,
    timed wall-clock, and the speedup = E+ wall time / surrogate time.

EnergyPlus is NOT installed by this script and is NOT committed to the
repo: download the official Linux tarball (EnergyPlus 26.2.0 was used
for the slice-2 numbers), extract it somewhere, and pass its root as
--eplus-dir.  Without --eplus-dir only the surrogate time is measured
and the speedup is reported as not measured.

What the number means: the surrogate solves a 2R2C RC model per zone;
EnergyPlus solves the full 5-zone building with HVAC/airflow.  The
comparison is wall-clock for an annual rollout of the same 5 zones, not
equal fidelity -- read it as "how much faster the surrogate answers",
not as "the surrogate replaces EnergyPlus".  The slice-2 measurement
on this VM was ~1.2x (surrogate ~10.0 s, EnergyPlus ~11.6 s wall):
the >=50x gate is NOT met, because the rollout is a Python loop over
8760 steps with a per-step torch call on a tiny model.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluate import load_pinn  # noqa: E402
from models import rollout_pinn, series_features  # noqa: E402
from train import load_arm_series  # noqa: E402


def _tile(series: dict, steps: int) -> np.ndarray:
    n0 = len(series["t_zone"])
    reps = steps // n0 + 1
    return series_features(
        np.tile(series["t_zone"], reps)[:steps],
        np.tile(series["t_out"], reps)[:steps],
        np.tile(series["t_set"], reps)[:steps],
        np.tile(series["q_int"], reps)[:steps],
    )


def surrogate_time(data_dir: str, steps: int, zones: int, trials: int) -> float:
    """Median wall time [s] of a batched zones x steps PINN rollout."""
    pinn = load_pinn(data_dir)
    if pinn is None:
        raise SystemExit(f"no trained PINN arm in {data_dir} "
                         "(run train.py --arm pinn first)")
    model, std, std_b, _ckpt = pinn
    series, params = load_arm_series(data_dir, "test_weather")
    feats_list, wall0_list, plist = [], [], []
    for i in range(zones):
        s = series[i % len(series)]
        feats_list.append(_tile(s, steps))
        wall0_list.append(s["t_wall"][11])
        plist.append(params[i % len(params)])
    feats = np.stack(feats_list)
    wall0 = np.array(wall0_list, dtype=np.float64)
    times = []
    for _ in range(trials):
        t0 = time.perf_counter()
        pred = rollout_pinn(model, std, std_b, feats, wall0, plist, 12)
        times.append(time.perf_counter() - t0)
        assert np.isfinite(pred).all(), "non-finite rollout"
    return float(np.median(times))


def energyplus_time(eplus_dir: str) -> float:
    """Wall time [s] of the 5ZoneAirCooled full-year EnergyPlus run."""
    binary = os.path.join(eplus_dir, "energyplus")
    idf = os.path.join(eplus_dir, "ExampleFiles", "5ZoneAirCooled.idf")
    epw = os.path.join(
        eplus_dir, "WeatherData",
        "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw")
    for path in (binary, idf, epw):
        if not os.path.exists(path):
            raise SystemExit(f"EnergyPlus file not found: {path}")
    with tempfile.TemporaryDirectory(prefix="eplus-bench-") as out_dir:
        t0 = time.perf_counter()
        r = subprocess.run([binary, "-w", epw, "-d", out_dir, idf],
                           capture_output=True, text=True)
        dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise SystemExit(f"EnergyPlus failed (rc={r.returncode}):\n"
                         f"{r.stdout[-500:]}\n{r.stderr[-500:]}")
    return dt


def main() -> None:
    ap = argparse.ArgumentParser(description="Surrogate-vs-EnergyPlus speedup")
    ap.add_argument("--data-dir", type=str,
                    default=os.path.join(os.path.dirname(
                        os.path.dirname(os.path.abspath(__file__))), "data"),
                    help="directory holding model_pinn.pt + the data splits")
    ap.add_argument("--steps", type=int, default=8760)
    ap.add_argument("--zones", type=int, default=5)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--eplus-dir", type=str, default=None,
                    help="EnergyPlus install root (ExampleFiles + WeatherData)")
    args = ap.parse_args()

    t_sur = surrogate_time(args.data_dir, args.steps, args.zones, args.trials)
    print(f"surrogate: {args.zones}-zone x {args.steps}-step PINN rollout "
          f"median wall time = {t_sur:.2f} s ({args.trials} trials)")
    if args.eplus_dir is None:
        print("EnergyPlus: not measured in this run "
              "(pass --eplus-dir <install root> to measure the speedup)")
        return
    t_eplus = energyplus_time(args.eplus_dir)
    print(f"EnergyPlus: 5ZoneAirCooled full-year wall time = {t_eplus:.2f} s")
    print(f"speedup (EnergyPlus / surrogate) = {t_eplus / t_sur:.2f}x "
          f"(issue #3 gate: >= 50x)")


if __name__ == "__main__":
    main()

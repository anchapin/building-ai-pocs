"""Synthetic data generation for the neural-operator surrogate POC (slice 1).

The ground truth is generated *from the RC model itself* (`rc_model.py`), so
the data is self-consistent: the zone temperature, the wall temperature and
the HVAC load of every series are an exact trajectory of the 2R2C model.

Split design (recorded in `splits.json` and in REPORT.md):

    weather profiles : mild, hot_spell, cold_snap
    setpoint schedules: fixed, setback, varying
    RC families      : {light, heavy} mass x {low, high} window U

    train          : weather in {mild, hot_spell} x setpoint in {fixed, setback}
    val            : same combinations as train, different realisation
    test_id        : same combinations as train, different realisation
                     -> IN-DISTRIBUTION holdout
    test_weather   : weather = cold_snap (UNSEEN weather), setpoint seen
    test_setpoint  : setpoint = varying (UNSEEN setpoint), weather seen
    test_both      : weather = cold_snap AND setpoint = varying

The extrapolation combinations (cold_snap, varying) never appear in train or
val; this is asserted by tests/test_gen_data.py.

Outputs (default `data/`, git-ignored scratch):
    train.npz val.npz test_id.npz test_weather.npz test_setpoint.npz
    test_both.npz splits.json
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np

from rc_model import RCParams, rollout_numpy

WEATHERS = ("mild", "hot_spell", "cold_snap")
SETPOINTS = ("fixed", "setback", "varying")
FAMILIES = (("light", "low"), ("light", "high"), ("heavy", "low"), ("heavy", "high"))

# Project layout: <repo>/neural-operator-surrogate/{src,tests,data}
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_DIR = os.path.join(PROJECT_DIR, "data")

SPLIT_NAMES = ("train", "val", "test_id", "test_weather", "test_setpoint", "test_both")

# Which (weather, setpoint) combinations belong to which split.
SPLIT_COMBOS: Dict[str, List[Tuple[str, str]]] = {
    "train": [("mild", "fixed"), ("mild", "setback"),
              ("hot_spell", "fixed"), ("hot_spell", "setback")],
    "val": [("mild", "fixed"), ("mild", "setback"),
            ("hot_spell", "fixed"), ("hot_spell", "setback")],
    "test_id": [("mild", "fixed"), ("mild", "setback"),
                ("hot_spell", "fixed"), ("hot_spell", "setback")],
    "test_weather": [("cold_snap", "fixed"), ("cold_snap", "setback")],
    "test_setpoint": [("mild", "varying"), ("hot_spell", "varying")],
    "test_both": [("cold_snap", "varying")],
}

# Number of RC families / repetitions used per (split, combination).
SPLIT_FAMILIES: Dict[str, int] = {
    "train": 4, "val": 2, "test_id": 2,
    "test_weather": 2, "test_setpoint": 2, "test_both": 2,
}

FLOOR_AREA = 45.0  # m2
WINDOW_AREA = 6.0  # m2


# --------------------------------------------------------------------------
# exogenous drivers
# --------------------------------------------------------------------------

def weather_profile(kind: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """Synthetic hourly outdoor temperature [degC] for a weather pattern."""
    h = np.arange(n, dtype=np.float64)
    diurnal = 2.0 * np.pi * (h - 9.0) / 24.0
    if kind == "mild":
        t = 12.0 + 4.0 * np.sin(diurnal) + 2.0 * np.sin(2.0 * np.pi * h / (26.0 * 24.0))
    elif kind == "hot_spell":
        t = (24.0 + 5.0 * np.sin(diurnal)
             + 9.0 * np.sin(2.0 * np.pi * (h - 0.15 * n) / (0.9 * n)))
    elif kind == "cold_snap":
        cold = 7.0 * np.exp(-0.5 * ((h - 0.65 * n) / (0.08 * n)) ** 2)
        t = -3.0 + 3.0 * np.sin(diurnal) - cold
    else:
        raise ValueError(f"unknown weather pattern: {kind}")
    t = t + rng.normal(0.0, 0.3, n)
    return t


def setpoint_schedule(kind: str, n: int, rng: np.random.Generator) -> np.ndarray:
    """Synthetic hourly setpoint schedule [degC]."""
    h = np.arange(n, dtype=np.float64)
    hod = np.arange(n) % 24
    if kind == "fixed":
        t = np.full(n, 21.0)
    elif kind == "setback":
        t = np.where((hod >= 7) & (hod < 23), 21.0, 16.0)
    elif kind == "varying":
        t = (19.5 + 2.5 * np.sin(2.0 * np.pi * h / (9.0 * 24.0))
             + 1.5 * np.sin(2.0 * np.pi * h / (2.5 * 24.0) + 1.1))
        walk = np.cumsum(rng.normal(0.0, 0.05, n))
        walk = walk - np.mean(walk)
        t = t + walk
    else:
        raise ValueError(f"unknown setpoint schedule: {kind}")
    return t


def internal_gains(n: int, rng: np.random.Generator) -> np.ndarray:
    """Hourly internal gains [W] (occupancy + equipment)."""
    h = np.arange(n)
    hod = h % 24
    day = h // 24
    occupied = np.where((hod >= 8) & (hod <= 18), 180.0, 35.0)
    weekend = np.isin(day % 7, [5, 6])
    q = np.where(weekend, occupied * 0.6, occupied)
    q = q + rng.normal(0.0, 8.0, n)
    return np.clip(q, 0.0, None)


# --------------------------------------------------------------------------
# RC parameters
# --------------------------------------------------------------------------

def family_params(mass: str, u_level: str, rng: np.random.Generator) -> RCParams:
    """RC parameters of a family, jittered per realisation."""
    if mass == "light":
        c_air, c_wall = 1.0e6, 1.5e7
    elif mass == "heavy":
        c_air, c_wall = 2.2e6, 6.0e7
    else:
        raise ValueError(mass)
    if u_level == "low":
        u_win = 1.1
    elif u_level == "high":
        u_win = 3.2
    else:
        raise ValueError(u_level)

    return RCParams(
        C_air=c_air * float(rng.uniform(0.9, 1.1)),
        R_wall=0.03,
        C_wall=c_wall * float(rng.uniform(0.85, 1.15)),
        R_air=0.05,
        U_win=u_win * float(rng.uniform(0.95, 1.05)),
        A_win=WINDOW_AREA,
        UA_inf=0.15 * FLOOR_AREA * float(rng.uniform(0.9, 1.1)),
        K_sup=3.0,
        T_sup_heat_max=45.0,
        T_sup_cool_min=13.0,
        Q_heat_max=6000.0,
        Q_cool_max=6000.0,
        T_init=20.0,
    )


# --------------------------------------------------------------------------
# series generation
# --------------------------------------------------------------------------

def synth_series(params: RCParams, weather: str, setpoint: str, n_steps: int,
                 rng: np.random.Generator) -> Dict[str, np.ndarray]:
    """One synthetic series, generated from the RC model itself."""
    t_out = weather_profile(weather, n_steps, rng)
    t_set = setpoint_schedule(setpoint, n_steps, rng)
    q_int = internal_gains(n_steps, rng)
    roll = rollout_numpy(params, t_out, t_set, q_int)
    return {
        "t_out": t_out,
        "t_set": t_set,
        "q_int": q_int,
        "t_zone": roll["t_air"],
        "t_wall": roll["t_wall"],
        "q_sup": roll["q_sup"],
    }


def series_rng(seed: int, split: str, combo_idx: int, family_idx: int,
               rep_idx: int) -> np.random.Generator:
    """Deterministic per-series RNG (stable across runs and machines)."""
    key = [int(seed), SPLIT_NAMES.index(split), int(combo_idx), int(family_idx),
           int(rep_idx)]
    return np.random.default_rng(key)


def build_split(split: str, seed: int, n_steps: int) -> Tuple[Dict[str, np.ndarray], List[Dict]]:
    """Build one split; returns (flat arrays, per-series metadata)."""
    arrays: Dict[str, List[np.ndarray]] = {k: [] for k in
                                           ("t_out", "t_set", "q_int", "t_zone",
                                            "t_wall", "q_sup")}
    series_ids: List[int] = []
    meta: List[Dict] = []
    sid = 0
    for combo_idx, (weather, setpoint) in enumerate(SPLIT_COMBOS[split]):
        for family_idx in range(SPLIT_FAMILIES[split]):
            mass, u_level = FAMILIES[family_idx % len(FAMILIES)]
            rng = series_rng(seed, split, combo_idx, family_idx, 0)
            params = family_params(mass, u_level, rng)
            s = synth_series(params, weather, setpoint, n_steps, rng)
            for k in arrays:
                arrays[k].append(s[k])
            series_ids.extend([sid] * n_steps)
            meta.append({
                "series_id": sid,
                "weather": weather,
                "setpoint": setpoint,
                "mass": mass,
                "u_level": u_level,
                "n_steps": int(n_steps),
                "params": params.to_dict(),
            })
            sid += 1
    flat = {k: np.concatenate(v) for k, v in arrays.items()}
    flat["series_id"] = np.asarray(series_ids, dtype=np.int32)
    return flat, meta


def save_split(split: str, seed: int, n_steps: int, out_dir: str) -> Dict:
    flat, meta = build_split(split, seed, n_steps)
    path = os.path.join(out_dir, f"{split}.npz")
    np.savez_compressed(path, **flat)
    return {"split": split, "n_series": len(meta), "n_steps": n_steps,
            "n_rows": int(flat["t_out"].size), "file": os.path.basename(path),
            "series": meta}


def load_split(out_dir: str, split: str) -> Dict[str, np.ndarray]:
    """Load a split npz into flat arrays."""
    path = os.path.join(out_dir, f"{split}.npz")
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def iter_series(flat: Dict[str, np.ndarray]) -> List[Dict[str, np.ndarray]]:
    """Split a flat split into a list of per-series dicts."""
    sid = flat["series_id"]
    out = []
    for s in np.unique(sid):
        m = sid == s
        out.append({k: v[m] for k, v in flat.items() if k != "series_id"})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate synthetic RC-model data")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--steps", type=int, default=720,
                    help="hours per series (default 720 = 30 days)")
    ap.add_argument("--out-dir", type=str, default=DEFAULT_DATA_DIR)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    summary = {"seed": args.seed, "steps": args.steps,
               "weathers": list(WEATHERS), "setpoints": list(SETPOINTS),
               "families": [list(f) for f in FAMILIES],
               "splits": {}}
    for split in SPLIT_NAMES:
        info = save_split(split, args.seed, args.steps, args.out_dir)
        summary["splits"][split] = info
        print(f"[gen_data] {split:13s} series={info['n_series']:3d} "
              f"steps/series={info['n_steps']:4d} rows={info['n_rows']:6d} "
              f"-> {info['file']}")

    with open(os.path.join(args.out_dir, "splits.json"), "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)
    print(f"[gen_data] wrote {os.path.join(args.out_dir, 'splits.json')} "
          f"(seed={args.seed})")


if __name__ == "__main__":
    main()

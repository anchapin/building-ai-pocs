"""Evaluation harness for the neural-operator surrogate POC (slice 1).

One command prints the headline table:

    python src/evaluate.py --seed 42

Reported per split (in-distribution and the two extrapolation axes), for
every arm, with the sample counts:

  * zone-temperature RMSE / MAE  (free-running rollout, degC)
  * HVAC-load RMSE / MAE(free-running rollout, W)
  * heat-balance residual (%)     (physics consistency of the rollout)
  * peak-load error (W and %)     (reported separately from the mean error)

The plain-MLP baseline (arm (a)) is the only surrogate arm in this slice.
There is NO physics-informed / neural-operator arm yet and NO EnergyPlus
baseline, so this script deliberately does not compute (and does not claim)
an extrapolation win factor or a speed-up factor.

Usage:
    python src/evaluate.py --seed 42 [--data-dir data] [--out-dir data]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Tuple

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_data import DEFAULT_DATA_DIR, iter_series, load_split  # noqa: E402
from models import (Standardizer, ZoneMLP, predict_windows,  # noqa: E402
window_features)
from rc_model import DT, RCParams, balance_residual_pct  # noqa: E402

SPLITS = ("val", "test_id", "test_weather", "test_setpoint", "test_both")

SPLIT_LABEL = {
    "val": "val (in-distribution)",
    "test_id": "test_id (in-distribution)",
    "test_weather": "test_weather (UNSEEN weather)",
    "test_setpoint": "test_setpoint (UNSEEN setpoint)",
    "test_both": "test_both (UNSEEN weather+setpoint)",
}


def load_model(data_dir: str):
    ckpt = torch.load(os.path.join(data_dir, "model.pt"),
  map_location="cpu", weights_only=False)
    model = ZoneMLP(ckpt["input_dim"], tuple(ckpt["hidden"]))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    std = Standardizer.from_dict(ckpt["standardizer"])
    return model, std, ckpt


def rollout_mlp(model, std, s: Dict[str, np.ndarray], window: int,
                target: str = "level") -> np.ndarray:
    """Free-running rollout of the MLP (only the first `window` steps are given)."""
    n = len(s["t_zone"])
    t_hat = s["t_zone"].astype(np.float64).copy()
    for k in range(window, n):
        x = window_features(t_hat, s["t_out"], s["t_set"], s["q_int"], window, k)
        pred = float(predict_windows(model, std, x[None, :])[0])
        t_hat[k] = t_hat[k - 1] + pred if target == "delta" else pred
    return t_hat


def wall_states(params: RCParams, t_pre: np.ndarray, w0: float,
      dt: float = DT) -> np.ndarray:
    """Mass node trajectory driven by the given (pre-step) zone temperatures."""
    w = np.empty(len(t_pre) + 1, dtype=np.float64)
    w[0] = w0
    for i, ta in enumerate(t_pre):
        q_aw = (ta - w[i]) / params.R_wall
        w[i + 1] = w[i] + dt / params.C_wall * q_aw
    return w


def series_metrics(params: RCParams, s: Dict[str, np.ndarray], t_hat: np.ndarray,
         window: int) -> Dict[str, float]:
    """Metrics of one free-running rollout."""
    n = len(s["t_zone"])
    k0, k1 = window, n  # evaluated target indices [k0, k1)
    true_t = s["t_zone"][k0:k1]
    pred_t = t_hat[k0:k1]
    err_t = pred_t - true_t

    # HVAC load implied by the surrogate trajectory vs the reference load.
    q_hat = np.array([
        (min(max(s["t_set"][k] + params.K_sup * (s["t_set"][k] - t_hat[k]),
       params.T_sup_cool_min), params.T_sup_heat_max) - t_hat[k]) / params.R_air
        for k in range(k0 - 1, k1 - 1)
    ])
    q_hat = np.clip(q_hat, -params.Q_cool_max, params.Q_heat_max)
    q_ref = s["q_sup"][k0 - 1: k1 - 1]
    err_q = q_hat - q_ref

    peak_ref = float(np.max(np.abs(q_ref)))
    peak_hat = float(np.max(np.abs(q_hat)))
    peak_err = peak_hat - peak_ref
    peak_err_pct = 100.0 * peak_err / peak_ref if peak_ref > 0 else float("nan")

    # Heat-balance residual of the rollout (pre-step states drive the flows).
    # Segment of steps: a = window-1 .. b = n-2  (n = n-window steps).
    # The state array holds [state before step a, ..., state after step b].
    a = k0 - 1
    b = k1 - 2
    t_pre = t_hat[a: b + 1]
    q_int_seg = s["q_int"][a: b + 1]
    t_out_seg = s["t_out"][a: b + 1]
    air_states = t_hat[a - 1: b + 1]
    wall = wall_states(params, t_pre, float(s["t_wall"][a - 1]))
    hb = balance_residual_pct(params, air_states, wall, q_hat, q_int_seg, t_out_seg)

    return {
        "n": k1 - k0,
        "rmse_t": float(np.sqrt(np.mean(err_t ** 2))),
        "mae_t": float(np.mean(np.abs(err_t))),
        "rmse_q": float(np.sqrt(np.mean(err_q ** 2))),
        "mae_q": float(np.mean(np.abs(err_q))),
        "hb_resid_pct": float(hb),
        "peak_q_err_w": peak_err,
        "peak_q_err_pct": peak_err_pct,
    }


def reference_metrics(params: RCParams, s: Dict[str, np.ndarray],
  window: int) -> Dict[str, float]:
    """Metrics of the RC reference rollout on the same segment (ground truth)."""
    n = len(s["t_zone"])
    k0, k1 = window, n
    a = k0 - 1
    b = k1 - 2
    t_pre = s["t_zone"][a: b + 1]
    q_int_seg = s["q_int"][a: b + 1]
    t_out_seg = s["t_out"][a: b + 1]
    air_states = s["t_zone"][a - 1: b + 1]
    wall = s["t_wall"][a - 1: b + 1]
    hb = balance_residual_pct(params, air_states, wall, s["q_sup"][a: b + 1],
q_int_seg, t_out_seg)
    return {
        "n": k1 - k0,
        "rmse_t": 0.0,
        "mae_t": 0.0,
        "rmse_q": 0.0,
        "mae_q": 0.0,
        "hb_resid_pct": float(hb),
        "peak_q_err_w": 0.0,
        "peak_q_err_pct": 0.0,
    }


def evaluate_split(model, std, data_dir: str, split: str, window: int,
         splits_meta: Dict, target: str = "level") -> List[Dict]:
    flat = load_split(data_dir, split)
    series = iter_series(flat)
    meta = {int(m["series_id"]): m for m in splits_meta["splits"][split]["series"]}
    rows = []
    for i, s in enumerate(series):
        sid = int(meta[i]["series_id"])
        params = RCParams.from_dict(meta[i]["params"])
        t_hat = rollout_mlp(model, std, s, window, target=target)
        rows.append({"arm": "MLP (plain)", "split": split, "series": sid,
 **series_metrics(params, s, t_hat, window)})
        rows.append({"arm": "RC reference (ground truth)", "split": split, "series": sid,
 **reference_metrics(params, s, window)})
    return rows


def aggregate(rows: List[Dict], arm: str, split: str) -> Dict:
    sel = [r for r in rows if r["arm"] == arm and r["split"] == split]
    n = sum(r["n"] for r in sel)
    # pooled RMSE over all evaluated steps of all series:
    # sqrt(sum_i(rmse_i^2 * n_i) / sum_i(n_i)) — the sum (not the mean) of
    # the per-series squared errors, so the pooled RMSE is >= the pooled
    # MAE and equals the RMSE of the concatenated errors.
    rmse_t = float(np.sqrt(np.sum([r["rmse_t"] ** 2 * r["n"] for r in sel]) / n))
    mae_t = float(np.sum([r["mae_t"] * r["n"] for r in sel]) / n)
    rmse_q = float(np.sqrt(np.sum([r["rmse_q"] ** 2 * r["n"] for r in sel]) / n))
    mae_q = float(np.sum([r["mae_q"] * r["n"] for r in sel]) / n)
    return {
        "arm": arm,
        "split": split,
        "n_series": len(sel),
        "n_steps": n,
        "rmse_t": rmse_t,
        "mae_t": mae_t,
        "rmse_q": rmse_q,
        "mae_q": mae_q,
        "hb_resid_pct": float(np.mean([r["hb_resid_pct"] for r in sel])),
        "peak_q_err_w": float(np.mean([r["peak_q_err_w"] for r in sel])),
        "peak_q_err_pct": float(np.mean([r["peak_q_err_pct"] for r in sel])),
    }


HEADER = ("{:<34} {:<28} {:>5} {:>8} {:>9} {:>9} {:>9} {:>9} {:>10} {:>11} {:>9}"
.format("split", "arm", "Nser", "Nsteps", "RMSE_T[C]", "MAE_T[C]",
        "RMSE_Q[W]", "MAE_Q[W]", "HBresid[%]", "PeakQerr[W]", "PeakQerr[%]"))


def format_row(r: Dict) -> str:
    return ("{:<34} {:<28} {:>5d} {:>8d} {:>9.4f} {:>9.4f} {:>9.2f} {:>9.2f} "
  "{:>10.3e} {:>11.2f} {:>9.3f}"
  .format(SPLIT_LABEL.get(r["split"], r["split"]), r["arm"], r["n_series"],
r["n_steps"], r["rmse_t"], r["mae_t"], r["rmse_q"], r["mae_q"],
r["hb_resid_pct"], r["peak_q_err_w"], r["peak_q_err_pct"]))


def main() -> None:
    ap = argparse.ArgumentParser(description="Headline evaluation table")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--data-dir", type=str, default=DEFAULT_DATA_DIR)
    ap.add_argument("--out-dir", type=str, default=DEFAULT_DATA_DIR)
    ap.add_argument("--threads", type=int, default=1)
    args = ap.parse_args()

    torch.set_num_threads(args.threads)

    model, std, ckpt = load_model(args.data_dir)
    window = int(ckpt["window"])
    # The checkpoint records the target parameterisation the model was
    # trained with ("level" or "delta"); checkpoints that predate the key
    # were trained with the old level default. Never assume: a delta
    # model rolled out as level (or vice versa) diverges or misreports.
    target = str(ckpt.get("target", "level"))
    with open(os.path.join(args.data_dir, "splits.json")) as fh:
        splits_meta = json.load(fh)

    lines: List[str] = []
    lines.append("=" * 148)
    lines.append("Neural-operator surrogate POC - slice 1 headline table")
    lines.append(f"seed={args.seed}  model_seed={ckpt.get('seed')}  window={window}  "
       f"target=next-step zone temperature [degC] (parameterisation={target})")
    lines.append(f"data_dir={args.data_dir}  data_seed={splits_meta.get('seed')}  "
       f"steps/series={splits_meta.get('steps')}")
    lines.append("arms: 'MLP (plain)' = plain-MLP baseline (issue #3 arm (a)); "
       "'RC reference' = the 2R2C ground truth itself")
    lines.append("-" * 148)
    lines.append(HEADER)
    lines.append("-" * 148)

    summary = []
    for split in SPLITS:
        rows = evaluate_split(model, std, args.data_dir, split, window,
                              splits_meta, target=target)
        for arm in ("RC reference (ground truth)", "MLP (plain)"):
            agg = aggregate(rows, arm, split)
            summary.append(agg)
            lines.append(format_row(agg))
        lines.append("-" * 148)

    lines.append("NOT claimed in this slice: (1) no physics-informed / neural-operator "
       "arm exists yet, so no extrapolation win factor;")
    lines.append("        (2) no EnergyPlus baseline, so no speed-up factor; "
       "(3) no Go/Conditional/No-go verdict - that label belongs to the "
       "full POC.")
    lines.append("=" * 148)
    text = "\n".join(lines)
    print(text)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "headline_table.txt"), "w") as fh:
        fh.write(text + "\n")
    with open(os.path.join(args.out_dir, "headline_table.json"), "w") as fh:
        json.dump(summary, fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()

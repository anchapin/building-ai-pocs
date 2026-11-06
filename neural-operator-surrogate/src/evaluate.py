"""Evaluation harness for the neural-operator surrogate POC (slices 1-3).

One command prints the headline table:

    python src/evaluate.py --seed 42

Reported per split (in-distribution and the two extrapolation axes), for
every arm, with the sample counts:

  * zone-temperature RMSE / MAE  (free-running rollout, degC)
  * HVAC-load RMSE / MAE(free-running rollout, W)
  * heat-balance residual (%)     (physics consistency of the rollout)
  * peak-load error (W and %)     (reported separately from the mean error)

The arms (all trained on the same data, splits and seed):

  * 'MLP (plain)'            - plain-MLP baseline (issue #3 arm (a)),
  * 'PINN (PI-DeepONet)'     - physics-informed arm, physics loss with the
                                TRUE per-series RC parameters (arm (b)),
  * 'PINN (nominal params)'  - the same arm with the NOMINAL (train-median)
                                RC parameters in the physics loss: the
                                parameter-mismatch experiment,
  * 'SharedEnc-RC'           - NeuralBES-style shared-encoder differentiable
                                RC model (issue #3 arm (c)), true base
                                parameters,
  * 'SharedEnc-RC (nominal base)' - the same arm with the nominal base
                                parameters,
  * 'RC reference'           - the 2R2C ground truth itself.

The speedup vs EnergyPlus is NOT computed here (see `benchmark_speedup.py`
and REPORT.md).

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
from models import (PINNZone, SharedEncoderRC, Standardizer, ZoneMLP,  # noqa: E402
                    median_params, predict_windows, rollout_pinn,
                    rollout_shared, series_features, window_features)
from rc_model import DT, RCParams, balance_residual_pct  # noqa: E402

SPLITS = ("val", "test_id", "test_weather", "test_setpoint", "test_both")

SPLIT_LABEL = {
    "val": "val (in-distribution)",
    "test_id": "test_id (in-distribution)",
    "test_weather": "test_weather (UNSEEN weather)",
    "test_setpoint": "test_setpoint (UNSEEN setpoint)",
    "test_both": "test_both (UNSEEN weather+setpoint)",
}

# The out-of-distribution splits of issue #3 (the extrapolation axis).
EXTRAPOLATION_SPLITS = ("test_weather", "test_setpoint", "test_both")

# Issue #3 gates.
GATE_EXTRAP_RMSE_REL = 0.20   # >= 20% RMSE reduction vs the MLP baseline
GATE_HB_RESID_PCT = 5.0       # < 5% heat-balance residual

ARM_MLP = "MLP (plain)"
ARM_PINN = "PINN (PI-DeepONet)"
ARM_PINN_NOM = "PINN (nominal params)"
ARM_SHARED = "SharedEnc-RC"
ARM_SHARED_NOM = "SharedEnc-RC (nominal base)"
ARM_REF = "RC reference (ground truth)"


def load_model(data_dir: str):
    ckpt = torch.load(os.path.join(data_dir, "model.pt"),
  map_location="cpu", weights_only=False)
    model = ZoneMLP(ckpt["input_dim"], tuple(ckpt["hidden"]))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    std = Standardizer.from_dict(ckpt["standardizer"])
    return model, std, ckpt


def load_pinn(data_dir: str, filename: str = "model_pinn.pt"):
    """Load a trained PINN arm (returns None if it has not been trained)."""
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        return None
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = PINNZone(ckpt["input_dim"], ckpt["input_dim_branch"],
                     tuple(ckpt["hidden"]))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    std = Standardizer.from_dict(ckpt["standardizer"])
    std_b = Standardizer.from_dict(ckpt["standardizer_branch"])
    return model, std, std_b, ckpt


def load_shared(data_dir: str, filename: str = "model_shared.pt"):
    """Load a trained shared-encoder RC arm (None if it has not been trained)."""
    path = os.path.join(data_dir, filename)
    if not os.path.exists(path):
        return None
    ckpt = torch.load(path, map_location="cpu", weights_only=False)
    model = SharedEncoderRC(ckpt["input_dim"], tuple(ckpt["hidden"]),
                             int(ckpt.get("latent", 32)))
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    std = Standardizer.from_dict(ckpt["standardizer"])
    return model, std, ckpt


def split_params_list(splits_meta: Dict, split: str) -> List[Dict[str, float]]:
    """The true RC parameters of every series of a split."""
    return [dict(m["params"]) for m in splits_meta["splits"][split]["series"]]


def nominal_params(splits_meta: Dict) -> Dict[str, float]:
    """Nominal (train-median) RC parameters: the mismatch experiment."""
    return median_params(split_params_list(splits_meta, "train"))


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


def rollout_pinn_series(model, std, std_b, s: Dict[str, np.ndarray],
                        window: int, params: Dict[str, float],
                        branch_offset: int = 0) -> np.ndarray:
    """Free-running rollout of the PINN on one series (numpy in/out).

    The first `window` steps are the warm start (the truth); from then on
    the model's own predictions drive the rollout.
    """
    feats = series_features(s["t_zone"], s["t_out"], s["t_set"], s["q_int"])
    wall0 = np.array([s["t_wall"][window - 1]], dtype=np.float64)
    out = rollout_pinn(model, std, std_b, feats[None, ...], wall0, [params],
                       window, branch_offset=branch_offset)
    return out[0].astype(np.float64)


def rollout_shared_series(model, std, s: Dict[str, np.ndarray],
                          window: int, params: Dict[str, float]) -> np.ndarray:
    """Free-running rollout of the shared-encoder RC arm on one series."""
    feats = series_features(s["t_zone"], s["t_out"], s["t_set"], s["q_int"])
    wall0 = np.array([s["t_wall"][window - 1]], dtype=np.float64)
    out = rollout_shared(model, std, feats[None, ...], wall0, [params], window)
    return out[0].astype(np.float64)


def build_surrogate_arms(data_dir: str, splits_meta: Dict) -> List[Dict]:
    """Every trained surrogate arm present in `data_dir` (arm descriptors).

    Each descriptor carries the model, its standardiser, the RC-parameter
    mode it was trained with ("true" = per-series true parameters, which
    the rollout must reproduce; "nominal" = the train-median parameters
    for every series) and its display label.
    """
    arms: List[Dict] = []
    for filename, label, kind in (
            ("model_pinn.pt", ARM_PINN, "pinn"),
            ("model_pinn_nominal.pt", ARM_PINN_NOM, "pinn"),
            ("model_shared.pt", ARM_SHARED, "shared"),
            ("model_shared_nominal.pt", ARM_SHARED_NOM, "shared")):
        path = os.path.join(data_dir, filename)
        if not os.path.exists(path):
            continue
        if kind == "pinn":
            model, std, std_b, ckpt = load_pinn(data_dir, filename)
            arms.append({"label": label, "kind": kind, "model": model,
                         "std": std, "std_b": std_b, "ckpt": ckpt,
                         "params_mode": str(ckpt.get("rc_params_mode", "true")),
                         "file": filename})
        else:
            model, std, ckpt = load_shared(data_dir, filename)
            arms.append({"label": label, "kind": kind, "model": model,
                         "std": std, "ckpt": ckpt,
                         "params_mode": str(ckpt.get("rc_params_mode", "true")),
                         "file": filename})
    return arms


def rollout_surrogate(arm: Dict, s: Dict[str, np.ndarray], window: int,
                      params_true: Dict[str, float],
                      params_nominal: Dict[str, float]) -> np.ndarray:
    """Free-running rollout of one surrogate arm on one series."""
    params = params_true if arm["params_mode"] == "true" else params_nominal
    if arm["kind"] == "pinn":
        return rollout_pinn_series(arm["model"], arm["std"], arm["std_b"], s,
                                   window, params,
                                   branch_offset=int(arm["ckpt"].get(
                                       "branch_offset", 0)))
    return rollout_shared_series(arm["model"], arm["std"], s, window, params)


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


def aligned_series_metrics(params: RCParams, s: Dict[str, np.ndarray],
                            t_hat: np.ndarray, window: int) -> Dict[str, float]:
    """Physics-aligned metrics of a surrogate rollout.

    Same segment as `series_metrics`, but the HVAC load implied by the
    surrogate trajectory is evaluated on the *pre-step* zone temperature
    and the mass node is propagated with the *pre-step* air temperature
    -- exactly the convention of the RC model itself (`q_sup[k]` is
    computed from the state at index k-1).  The slice-1 `series_metrics`
    evaluates the implied load on the post-step temperature, which is one
    step off: even the exact ground-truth trajectory scores 0.02-2.96%
    instead of ~1e-14%, so that metric systematically penalises any
    surrogate rollout.

    This function decides the physics gates (<5% heat-balance residual),
    because it measures the same quantity the physics loss trains.  It is
    applied identically to every arm.
    """
    from rc_model import controller_numpy

    n = len(s["t_zone"])
    k0, k1 = window, n
    a, b = k0 - 1, k1 - 2
    q_int_seg = s["q_int"][a: b + 1]
    t_out_seg = s["t_out"][a: b + 1]
    pre_air = t_hat[a - 1: b]              # pre-step air of steps a..b
    air_states = t_hat[a - 1: b + 1]
    wall = np.empty(len(pre_air) + 1, dtype=np.float64)
    wall[0] = float(s["t_wall"][a - 1])
    for j in range(len(pre_air)):
        q_aw = (pre_air[j] - wall[j]) / params.R_wall
        wall[j + 1] = wall[j] + DT / params.C_wall * q_aw
    q_hat = np.array([
        controller_numpy(params, float(t_hat[k - 1]), float(s["t_set"][k]))
        for k in range(a, b + 1)])
    q_ref = s["q_sup"][a: b + 1]
    err_q = q_hat - q_ref
    peak_ref = float(np.max(np.abs(q_ref)))
    peak_hat = float(np.max(np.abs(q_hat)))
    hb = balance_residual_pct(params, air_states, wall, q_hat, q_int_seg,
                              t_out_seg)
    err_t = t_hat[k0:k1] - s["t_zone"][k0:k1]
    return {
        "n": k1 - k0,
        "rmse_t": float(np.sqrt(np.mean(err_t ** 2))),
        "mae_t": float(np.mean(np.abs(err_t))),
        "rmse_q": float(np.sqrt(np.mean(err_q ** 2))),
        "mae_q": float(np.mean(np.abs(err_q))),
        "hb_resid_pct": float(hb),
        "peak_q_err_w": peak_hat - peak_ref,
        "peak_q_err_pct": (100.0 * (peak_hat - peak_ref) / peak_ref
                           if peak_ref > 0 else float("nan")),
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
         splits_meta: Dict, target: str = "level",
         arms: List[Dict] = None) -> List[Dict]:
    flat = load_split(data_dir, split)
    series = iter_series(flat)
    meta = {int(m["series_id"]): m for m in splits_meta["splits"][split]["series"]}
    nom = nominal_params(splits_meta)
    rows = []
    for i, s in enumerate(series):
        sid = int(meta[i]["series_id"])
        params = RCParams.from_dict(meta[i]["params"])
        t_hat = rollout_mlp(model, std, s, window, target=target)
        rows.append({"arm": ARM_MLP, "split": split, "series": sid,
 **series_metrics(params, s, t_hat, window)})
        for arm in (arms or []):
            t_arm = rollout_surrogate(arm, s, window, params.to_dict(), nom)
            rows.append({"arm": arm["label"], "split": split, "series": sid,
 **series_metrics(params, s, t_arm, window)})
        rows.append({"arm": ARM_REF, "split": split, "series": sid,
 **reference_metrics(params, s, window)})
    return rows


def evaluate_split_aligned(model, std, data_dir: str, split: str, window: int,
         splits_meta: Dict, target: str = "level",
         arms: List[Dict] = None) -> List[Dict]:
    """Same as `evaluate_split`, but with the physics-aligned metrics."""
    flat = load_split(data_dir, split)
    series = iter_series(flat)
    meta = {int(m["series_id"]): m for m in splits_meta["splits"][split]["series"]}
    nom = nominal_params(splits_meta)
    rows = []
    for i, s in enumerate(series):
        sid = int(meta[i]["series_id"])
        params = RCParams.from_dict(meta[i]["params"])
        t_hat = rollout_mlp(model, std, s, window, target=target)
        rows.append({"arm": ARM_MLP, "split": split, "series": sid,
 **aligned_series_metrics(params, s, t_hat, window)})
        for arm in (arms or []):
            t_arm = rollout_surrogate(arm, s, window, params.to_dict(), nom)
            rows.append({"arm": arm["label"], "split": split, "series": sid,
 **aligned_series_metrics(params, s, t_arm, window)})
        rows.append({"arm": ARM_REF, "split": split, "series": sid,
 **aligned_series_metrics(params, s, s["t_zone"].astype(np.float64), window)})
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


def gate_summary(summary: List[Dict], aligned: List[Dict],
                 arm_labels: List[str]) -> List[str]:
    """Per-split gate verdicts (issue #3) of every surrogate arm vs the MLP."""
    by = {(r["arm"], r["split"]): r for r in summary}
    ab = {(r["arm"], r["split"]): r for r in aligned}
    lines = []
    lines.append("GATE SUMMARY (issue #3)")
    lines.append(f"  extrapolation gate: the surrogate's RMSE_T must be <= "
                 f"{100 * (1 - GATE_EXTRAP_RMSE_REL):.0f}% of the MLP RMSE_T "
                 f"(>= {100 * GATE_EXTRAP_RMSE_REL:.0f}% reduction)")
    lines.append(f"  heat-balance gate : the surrogate's heat-balance residual "
                 f"must be < {GATE_HB_RESID_PCT:.1f}% (physics-aligned metric, "
                 f"identical for every arm)")
    lines.append("  peak-load error is reported separately from the mean error")
    for label in arm_labels:
        lines.append("")
        lines.append(f"  arm: {label}")
        lines.append(f"  {'split':<34} {'RMSE_T MLP':>11} {'RMSE_T arm':>12} "
                     f"{'reduction':>10} {'>=20% gate':>11} {'HBresid arm':>13} "
                     f"{'<5% gate':>10} {'PeakQerr arm':>14}")
        for split in SPLITS:
            mlp = by.get((ARM_MLP, split))
            arm = by.get((label, split))
            aarm = ab.get((label, split))
            if mlp is None or arm is None or aarm is None:
                continue
            red = (100.0 * (1.0 - arm["rmse_t"] / mlp["rmse_t"])
                   if mlp["rmse_t"] else float("nan"))
            extrap = split in EXTRAPOLATION_SPLITS
            gate_txt = ("n/a (in-dist)" if not extrap
                        else ("MET" if red >= 100 * GATE_EXTRAP_RMSE_REL
                              else "NOT MET"))
            hb_gate = ("MET" if aarm["hb_resid_pct"] < GATE_HB_RESID_PCT
                       else "NOT MET")
            lines.append(f"  {SPLIT_LABEL.get(split, split):<34} "
                         f"{mlp['rmse_t']:>11.4f} {arm['rmse_t']:>12.4f} "
                         f"{red:>9.2f}% {gate_txt:>11} "
                         f"{aarm['hb_resid_pct']:>13.3f} "
                         f"{hb_gate:>10} {aarm['peak_q_err_pct']:>14.3f}")
    return lines


def mismatch_summary(summary: List[Dict], aligned: List[Dict]) -> List[str]:
    """Parameter-mismatch experiment: PINN with nominal vs true RC parameters."""
    by = {(r["arm"], r["split"]): r for r in summary}
    ab = {(r["arm"], r["split"]): r for r in aligned}
    lines = []
    lines.append("PARAMETER-MISMATCH EXPERIMENT (physics loss / rollout with "
                 "NOMINAL train-median RC parameters vs the TRUE per-series "
                 "parameters)")
    lines.append(f"  {'split':<34} {'RMSE_T true':>12} {'RMSE_T nominal':>14} "
                 f"{'delta %':>9} {'HBresid true':>13} {'HBresid nominal':>15}")
    for split in SPLITS:
        t = by.get((ARM_PINN, split))
        n = by.get((ARM_PINN_NOM, split))
        at = ab.get((ARM_PINN, split))
        an = ab.get((ARM_PINN_NOM, split))
        if t is None or n is None:
            continue
        delta = (100.0 * (n["rmse_t"] - t["rmse_t"]) / t["rmse_t"]
                 if t["rmse_t"] else float("nan"))
        lines.append(f"  {SPLIT_LABEL.get(split, split):<34} "
                     f"{t['rmse_t']:>12.4f} {n['rmse_t']:>14.4f} "
                     f"{delta:>8.2f}% "
                     f"{(at['hb_resid_pct'] if at else float('nan')):>13.3f} "
                     f"{(an['hb_resid_pct'] if an else float('nan')):>15.3f}")
    return lines


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

    surrogate_arms = build_surrogate_arms(args.data_dir, splits_meta)
    arm_labels = [a["label"] for a in surrogate_arms]
    arms = [ARM_REF, ARM_MLP] + arm_labels

    lines: List[str] = []
    lines.append("=" * 148)
    lines.append("Neural-operator surrogate POC - slice 3 headline table")
    lines.append(f"seed={args.seed}  model_seed={ckpt.get('seed')}  window={window}  "
       f"target=next-step zone temperature [degC] (parameterisation={target})")
    lines.append(f"data_dir={args.data_dir}  data_seed={splits_meta.get('seed')}  "
       f"steps/series={splits_meta.get('steps')}")
    lines.append("arms: 'MLP (plain)' = plain-MLP baseline (issue #3 arm (a)); "
       "'PINN (PI-DeepONet)' = physics-informed arm trained with a "
       "multi-step rollout loss + the heat-balance residual, physics loss "
       "with the TRUE per-series RC parameters (issue #3 arm (b)); "
       "'PINN (nominal params)' = the same arm with the NOMINAL "
       "(train-median) RC parameters in the physics loss (parameter-mismatch "
       "experiment); 'SharedEnc-RC' = NeuralBES-style shared-encoder "
       "differentiable RC model (issue #3 arm (c)); 'SharedEnc-RC (nominal "
       "base)' = the same arm on the nominal base parameters; 'RC reference' "
       "= the 2R2C ground truth itself")
    lines.append("-" * 148)
    lines.append(HEADER)
    lines.append("-" * 148)

    summary = []
    aligned: List[Dict] = []
    for split in SPLITS:
        rows = evaluate_split(model, std, args.data_dir, split, window,
                              splits_meta, target=target, arms=surrogate_arms)
        for arm in arms:
            agg = aggregate(rows, arm, split)
            summary.append(agg)
            lines.append(format_row(agg))
        lines.append("-" * 148)

    if surrogate_arms:
        # Physics-aligned metrics: the implied HVAC load of a surrogate
        # rollout is evaluated on the PRE-step zone temperature and the
        # mass node is propagated with the PRE-step air temperature, as
        # the RC model does.  The slice-1 metric uses the post-step
        # temperature, which is one step off (the exact ground truth
        # scores 0.02-2.96% there instead of ~1e-14%), so it
        # systematically penalises any surrogate rollout.  The <5%
        # heat-balance gate is decided on the aligned metric, applied
        # identically to every arm.
        lines.append("PHYSICS-ALIGNED METRICS (implied HVAC load and mass-node "
                     "dynamics evaluated on the PRE-step zone temperature, "
                     "as in the RC model)")
        lines.append(HEADER)
        lines.append("-" * 148)
        for split in SPLITS:
            arows = evaluate_split_aligned(model, std, args.data_dir, split,
                                            window, splits_meta, target=target,
                                            arms=surrogate_arms)
            for arm in arms:
                agg = aggregate(arows, arm, split)
                aligned.append(agg)
                lines.append(format_row(agg))
            lines.append("-" * 148)

    lines.extend(gate_summary(summary, aligned, arm_labels))
    if ARM_PINN_NOM in arm_labels:
        lines.append("")
        lines.extend(mismatch_summary(summary, aligned))

    lines.append("NOT claimed in this slice: (1) the Go/Conditional/No-go verdict is "
       "not printed by this script - it is in REPORT.md (the closing slice);")
    lines.append("        (2) speed-up vs EnergyPlus is not computed here - see REPORT.md "
       "and src/benchmark_speedup.py (the >=50x gate is measured on a vectorised "
       "rollout, or reported as not re-attempted with the reason).")
    lines.append("=" * 148)
    text = "\n".join(lines)
    print(text)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "headline_table.txt"), "w") as fh:
        fh.write(text + "\n")
    with open(os.path.join(args.out_dir, "headline_table.json"), "w") as fh:
        json.dump({"summary": summary, "aligned": aligned,
                   "arms": arm_labels}, fh, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()

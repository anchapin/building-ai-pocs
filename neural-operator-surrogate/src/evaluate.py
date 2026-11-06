"""Evaluation harness for the neural-operator surrogate POC (slice 1).

One command prints the headline table:

    python src/evaluate.py --seed 42

Reported per split (in-distribution and the two extrapolation axes), for
every arm, with the sample counts:

  * zone-temperature RMSE / MAE  (free-running rollout, degC)
  * HVAC-load RMSE / MAE(free-running rollout, W)
  * heat-balance residual (%)     (physics consistency of the rollout)
  * peak-load error (W and %)     (reported separately from the mean error)

The plain-MLP baseline (arm (a)) and the physics-informed PI-DeepONet-style
arm (b, slice 2) are both evaluated here, on the same splits and with the
same metrics.  There is NO EnergyPlus baseline on this machine, so this
script deliberately does not compute (and does not claim) a speed-up
factor.

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
from models import (PINNZone, Standardizer, ZoneMLP, predict_windows,  # noqa: E402
                    rollout_pinn, series_features, window_features)
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
         pinn: Tuple = None) -> List[Dict]:
    flat = load_split(data_dir, split)
    series = iter_series(flat)
    meta = {int(m["series_id"]): m for m in splits_meta["splits"][split]["series"]}
    rows = []
    for i, s in enumerate(series):
        sid = int(meta[i]["series_id"])
        params = RCParams.from_dict(meta[i]["params"])
        t_hat = rollout_mlp(model, std, s, window, target=target)
        rows.append({"arm": ARM_MLP, "split": split, "series": sid,
 **series_metrics(params, s, t_hat, window)})
        if pinn is not None:
            p_model, p_std, p_std_b, p_ckpt = pinn
            t_pinn = rollout_pinn_series(p_model, p_std, p_std_b, s, window,
                                         params.to_dict(),
                                         branch_offset=int(p_ckpt.get(
                                             "branch_offset", 0)))
            rows.append({"arm": ARM_PINN, "split": split, "series": sid,
 **series_metrics(params, s, t_pinn, window)})
        rows.append({"arm": ARM_REF, "split": split, "series": sid,
 **reference_metrics(params, s, window)})
    return rows


def evaluate_split_aligned(model, std, data_dir: str, split: str, window: int,
         splits_meta: Dict, target: str = "level",
         pinn: Tuple = None) -> List[Dict]:
    """Same as `evaluate_split`, but with the physics-aligned metrics."""
    flat = load_split(data_dir, split)
    series = iter_series(flat)
    meta = {int(m["series_id"]): m for m in splits_meta["splits"][split]["series"]}
    rows = []
    for i, s in enumerate(series):
        sid = int(meta[i]["series_id"])
        params = RCParams.from_dict(meta[i]["params"])
        t_hat = rollout_mlp(model, std, s, window, target=target)
        rows.append({"arm": ARM_MLP, "split": split, "series": sid,
 **aligned_series_metrics(params, s, t_hat, window)})
        if pinn is not None:
            p_model, p_std, p_std_b, p_ckpt = pinn
            t_pinn = rollout_pinn_series(p_model, p_std, p_std_b, s, window,
                                         params.to_dict(),
                                         branch_offset=int(p_ckpt.get(
                                             "branch_offset", 0)))
            rows.append({"arm": ARM_PINN, "split": split, "series": sid,
 **aligned_series_metrics(params, s, t_pinn, window)})
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


def gate_summary(summary: List[Dict], aligned: List[Dict]) -> List[str]:
    """Per-split gate verdicts (issue #3) of the PINN arm against the MLP."""
    by = {(r["arm"], r["split"]): r for r in summary}
    ab = {(r["arm"], r["split"]): r for r in aligned}
    lines = []
    lines.append("GATE SUMMARY (issue #3)")
    lines.append(f"  extrapolation gate: PINN RMSE_T must be <= "
                 f"{100 * (1 - GATE_EXTRAP_RMSE_REL):.0f}% of the MLP RMSE_T "
                 f"(>= {100 * GATE_EXTRAP_RMSE_REL:.0f}% reduction)")
    lines.append(f"  heat-balance gate : PINN heat-balance residual must be "
                 f"< {GATE_HB_RESID_PCT:.1f}% (physics-aligned metric, "
                 f"identical for every arm)")
    lines.append("  peak-load error is reported separately from the mean error")
    lines.append("")
    lines.append(f"  {'split':<34} {'RMSE_T MLP':>11} {'RMSE_T PINN':>12} "
                 f"{'reduction':>10} {'>=20% gate':>11} {'HBresid PINN':>13} "
                 f"{'<5% gate':>10} {'PeakQerr PINN':>14}")
    for split in SPLITS:
        mlp = by.get((ARM_MLP, split))
        pinn = by.get((ARM_PINN, split))
        apinn = ab.get((ARM_PINN, split))
        if mlp is None or pinn is None or apinn is None:
            continue
        red = (100.0 * (1.0 - pinn["rmse_t"] / mlp["rmse_t"])
               if mlp["rmse_t"] else float("nan"))
        extrap = split in EXTRAPOLATION_SPLITS
        gate_txt = ("n/a (in-dist)" if not extrap
                    else ("MET" if red >= 100 * GATE_EXTRAP_RMSE_REL else "NOT MET"))
        hb_gate = "MET" if apinn["hb_resid_pct"] < GATE_HB_RESID_PCT else "NOT MET"
        lines.append(f"  {SPLIT_LABEL.get(split, split):<34} "
                     f"{mlp['rmse_t']:>11.4f} {pinn['rmse_t']:>12.4f} "
                     f"{red:>9.2f}% {gate_txt:>11} "
                     f"{apinn['hb_resid_pct']:>13.3f} "
                     f"{hb_gate:>10} {apinn['peak_q_err_pct']:>14.3f}")
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
    pinn = load_pinn(args.data_dir)
    with open(os.path.join(args.data_dir, "splits.json")) as fh:
        splits_meta = json.load(fh)

    arms = [ARM_REF, ARM_MLP] + ([ARM_PINN] if pinn is not None else [])

    lines: List[str] = []
    lines.append("=" * 148)
    lines.append("Neural-operator surrogate POC - slice 2 headline table")
    lines.append(f"seed={args.seed}  model_seed={ckpt.get('seed')}  window={window}  "
       f"target=next-step zone temperature [degC] (parameterisation={target})")
    lines.append(f"data_dir={args.data_dir}  data_seed={splits_meta.get('seed')}  "
       f"steps/series={splits_meta.get('steps')}")
    lines.append("arms: 'MLP (plain)' = plain-MLP baseline (issue #3 arm (a)); "
       "'PINN (PI-DeepONet)' = physics-informed arm trained with a "
       "multi-step rollout loss + the heat-balance residual (issue #3 "
       "arm (b)); 'RC reference' = the 2R2C ground truth itself")
    lines.append("-" * 148)
    lines.append(HEADER)
    lines.append("-" * 148)

    summary = []
    aligned: List[Dict] = []
    for split in SPLITS:
        rows = evaluate_split(model, std, args.data_dir, split, window,
                              splits_meta, target=target, pinn=pinn)
        for arm in arms:
            agg = aggregate(rows, arm, split)
            summary.append(agg)
            lines.append(format_row(agg))
        lines.append("-" * 148)

    if pinn is not None:
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
                                            pinn=pinn)
            for arm in arms:
                agg = aggregate(arows, arm, split)
                aligned.append(agg)
                lines.append(format_row(agg))
            lines.append("-" * 148)

    lines.extend(gate_summary(summary, aligned))

    lines.append("NOT claimed in this slice: (1) no Go/Conditional/No-go verdict - that label "
       "belongs to the full POC, after all three arms and the speed-up gate exist;")
    lines.append("        (2) speed-up vs EnergyPlus is measured, not claimed here - see REPORT.md "
       "(5-zone annual rollout ~1x on this machine; the >=50x gate is NOT met).")
    lines.append("=" * 148)
    text = "\n".join(lines)
    print(text)

    os.makedirs(args.out_dir, exist_ok=True)
    with open(os.path.join(args.out_dir, "headline_table.txt"), "w") as fh:
        fh.write(text + "\n")
    with open(os.path.join(args.out_dir, "headline_table.json"), "w") as fh:
        json.dump({"summary": summary, "aligned": aligned}, fh, indent=2,
                  sort_keys=True)


if __name__ == "__main__":
    main()

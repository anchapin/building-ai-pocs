"""Train the surrogates of the neural-operator POC on the synthetic data.

Two arms share the SAME data, the SAME splits, the SAME seed and the SAME
target (next-step zone temperature [degC]):

  * `--arm mlp`  (default) — the plain-MLP baseline, issue #3 arm (a),
    trained one-step (teacher forced).  This code path is unchanged from
    slice 1.
  * `--arm pinn` — the physics-informed / PI-DeepONet-style arm, issue #3
    arm (b), trained with a **multi-step (rollout) loss** plus the
    **heat-balance residual** of the differentiable 2R2C zone model.

Target (one, and the same for every later arm): the **next-step zone
temperature** [degC].  Inputs: a fixed window of the last `window` hourly
steps of (outdoor temperature, setpoint, internal gains, zone temperature,
hour-of-day encoding).

Two equivalent parameterisations of that target are supported:
  * `--target level`: the network predicts t_zone[k] (default);
  * `--target delta`: the network predicts t_zone[k] - t_zone[k-1] and the
    previous level is added back at prediction time.

Slice-1 finding (2026-11-06, seed 42, same data, same 60 epochs): the
delta-trained model DIVERGES in free-running rollout on 5 of 8 validation
series (RMSE_T up to 1e33 degC, blow-up starting around step 150-350),
while the level-trained model stays bounded on every split (val RMSE_T
3.84 degC). One-step teacher-forced RMSE is similar for both (val 0.11
vs 0.09 degC), so the instability is a rollout property, not a fit
property: a one-step-trained delta model has a positive-feedback loop
once its own predictions enter the input window. Do NOT switch the
default back to delta without multi-step (rollout) loss — the PINN arm of
slice 2 does exactly that (multi-step rollout loss), but the shared default
target stays `level` for every arm.

Artefacts are written to `data/` (git-ignored scratch):
    model.pt / train_metrics.json           - MLP arm   (slice 1)
    model_pinn.pt / train_metrics_pinn.json  - PINN arm  (slice 2)

Usage:
    python src/train.py --seed 42
    python src/train.py --seed 42 --arm pinn
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Dict, List, Tuple

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_data import DEFAULT_DATA_DIR, iter_series, load_split  # noqa: E402
from models import (PINNZone, SharedEncoderRC, Standardizer, build_branch,  # noqa: E402
                    build_windows, count_parameters, make_model, make_pinn,
                    make_shared, median_params, pinn_rollout_torch,
                    predict_windows, rc_param_tensors, rollout_pinn,
                    rollout_shared, series_features, shared_rollout_torch)
from rc_model import RCParams  # noqa: E402


def collect_windows(data_dir: str, split: str, window: int, target: str = "delta"):
    """Build the windows of a split (windows never cross series borders).

    Returns (x, y, prev, level, n_series) where `y` is the regression
    target in the chosen parameterisation, `prev` is t_zone[k-1] and
    `level` is the true t_zone[k].
    """
    series = iter_series(load_split(data_dir, split))
    xs, ys, ps, ls = [], [], [], []
    for s in series:
        x, level = build_windows(s["t_zone"], s["t_out"], s["t_set"], s["q_int"], window)
        prev = s["t_zone"][window - 1: window - 1 + len(level)]
        y = level - prev if target == "delta" else level
        xs.append(x)
        ys.append(y)
        ps.append(prev)
        ls.append(level)
    return (np.concatenate(xs), np.concatenate(ys), np.concatenate(ps),
            np.concatenate(ls), len(series))


# --------------------------------------------------------------------------
# PINN arm (issue #3 arm (b)) — slice 2
# --------------------------------------------------------------------------

def load_arm_series(data_dir: str, split: str) -> Tuple[List[Dict], List[Dict]]:
    """Series of a split together with their (known) RC parameters.

    The physics-informed arm needs the zone parameters to evaluate the
    heat-balance residual.  They are treated as KNOWN (identified offline
    for the zone under study), which is the standard assumption of a
    physics-informed surrogate; the report states this explicitly.
    """
    series = iter_series(load_split(data_dir, split))
    with open(os.path.join(data_dir, "splits.json")) as fh:
        meta = json.load(fh)["splits"][split]["series"]
    metas = {int(m["series_id"]): m for m in meta}
    out_series: List[Dict] = []
    out_params: List[Dict] = []
    for i, s in enumerate(series):
        sid = int(meta[i]["series_id"])
        out_series.append({
            "t_zone": s["t_zone"], "t_out": s["t_out"], "t_set": s["t_set"],
            "q_int": s["q_int"], "t_wall": s["t_wall"], "q_sup": s["q_sup"],
        })
        out_params.append(RCParams.from_dict(metas[sid]["params"]).to_dict())
    return out_series, out_params


def nominal_params_for(data_dir: str) -> Dict[str, float]:
    """Nominal (train-median) RC parameters of the zone under study.

    Used by the parameter-mismatch experiment: a surrogate that only knows
    a *nominal* zone instead of the true per-series parameters.
    """
    _, tr_params = load_arm_series(data_dir, "train")
    return median_params(tr_params)


def resolve_params(params_mode: str, data_dir: str,
                   series_params: List[Dict[str, float]]) -> List[Dict[str, float]]:
    """RC parameters used by the physics loss / rollout of an arm.

    `params_mode` is "true" (the per-series true parameters, the
    assumption of slices 1-2) or "nominal" (the train-median parameters
    for every series -- the parameter-mismatch experiment).
    """
    if params_mode == "true":
        return list(series_params)
    if params_mode == "nominal":
        nominal = nominal_params_for(data_dir)
        return [dict(nominal) for _ in series_params]
    raise ValueError(f"unknown rc-params mode: {params_mode}")


def train_pinn(args) -> None:
    """Train the physics-informed (PI-DeepONet-style) arm.

    Loss (all terms in the same physical units, degC unless stated):

        L = w_one  * MSE_one_step      (teacher-forced next-step fit)
          + w_roll * MSE_rollout       (multi-step / rollout component)
          + w_phys * MSE_physics       (heat-balance residual, relative)

    The rollout component unrolls the surrogate over `--pinn-horizon`
    steps from the true history and compares the whole trajectory with the
    truth; the physics component is the residual of the differentiable
    2R2C zone equations along that same rollout (in W, normalised by
    `--phys-scale` W).
    """
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(args.threads)

    if args.target != "level":
        raise SystemExit("the PINN arm only supports --target level "
                         "(the shared default); delta is not used here.")

    t_start = time.time()
    tr_series, tr_params = load_arm_series(args.data_dir, "train")
    va_series, va_params = load_arm_series(args.data_dir, "val")
    # "true" = per-series true RC parameters (assumption of slices 1-2);
    # "nominal" = the train-median parameters for every series (the
    # parameter-mismatch experiment of slice 3).
    tr_params = resolve_params(args.rc_params, args.data_dir, tr_params)
    va_params = resolve_params(args.rc_params, args.data_dir, va_params)

    # one-step windows (identical construction to the MLP arm)
    xs, ys, bs = [], [], []
    for s in tr_series:
        x, y = build_windows(s["t_zone"], s["t_out"], s["t_set"], s["q_int"],
                             args.window)
        xs.append(x)
        ys.append(y)
        bs.append(build_branch(s["t_out"], s["t_set"], s["q_int"], args.window,
                               offset=args.branch_offset))
    x_tr = np.concatenate(xs)
    y_tr = np.concatenate(ys)
    b_tr = np.concatenate(bs)
    std = Standardizer.fit(x_tr, y_tr)
    std_b = Standardizer.fit_x(b_tr)

    model = make_pinn(x_tr.shape[1], b_tr.shape[1], tuple(args.hidden),
                      seed=args.seed)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = torch.nn.MSELoss()

    xt = torch.as_tensor(std.transform_x(x_tr), dtype=torch.float32)
    yt = torch.as_tensor(std.transform_y(y_tr), dtype=torch.float32)
    bt = torch.as_tensor(std_b.transform_x(b_tr), dtype=torch.float32)

    n = len(xt)
    rng = np.random.default_rng(args.seed)
    horizon = args.pinn_horizon
    best_val = float("inf")
    best_state = None
    best_epoch = -1
    history: List[Dict] = []

    # full feature matrices of every training series (one per series)
    tr_feats = [series_features(s["t_zone"], s["t_out"], s["t_set"], s["q_int"])
                for s in tr_series]
    tr_len = [len(f) for f in tr_feats]

    def rollout_batch(starts: List[Tuple[int, int]]):
        """Free-running rollouts of the surrogate on the given (series, start) pairs.

        All rollouts are stacked into ONE batch, so the horizon is walked
        once per call (vectorised over the batch) and autograd flows
        through the whole multi-step rollout.
        """
        feats = np.stack([tr_feats[i][k - args.window: k + horizon]
                          for i, k in starts])
        wall0 = np.array([tr_series[i]["t_wall"][k - 1] for i, k in starts],
                         dtype=np.float64)
        params = [tr_params[i] for i, _ in starts]
        fb = torch.as_tensor(feats, dtype=torch.float32)
        wb = torch.as_tensor(wall0, dtype=torch.float64)
        pt = rc_param_tensors(params)
        pred, resid = pinn_rollout_torch(model, std, std_b, fb, wb, pt,
                                         args.window,
                                         branch_offset=args.branch_offset)
        truth = fb[:, args.window:, 3]
        l_roll = torch.mean((pred[:, args.window:] - truth) ** 2)
        # heat-balance residual in W: C_air/dt * (T_pred - T_implied)
        c_air = pt["C_air"].to(torch.float32).unsqueeze(1)
        r_w = resid[:, args.window:] * (c_air / 3600.0)
        l_phys = torch.mean((r_w / args.phys_scale) ** 2)
        return l_roll, l_phys

    for epoch in range(args.epochs):
        model.train()
        perm = rng.permutation(n)
        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, n, args.batch_size):
            idx = perm[i: i + args.batch_size]
            starts = []
            for _ in range(args.pinn_rollout_per_series):
                for si in range(len(tr_series)):
                    lo = args.window
                    hi = tr_len[si] - horizon
                    starts.append((si, int(rng.integers(lo, hi))))
            opt.zero_grad()
            out = model(xt[idx], bt[idx])
            l_one = loss_fn(out, yt[idx])
            l_roll, l_phys = rollout_batch(starts)
            loss = (args.w_one * l_one + args.w_roll * l_roll
                    + args.w_phys * l_phys)
            loss.backward()
            opt.step()
            epoch_loss += float(loss.item())
            n_batches += 1
        epoch_loss /= max(n_batches, 1)

        v_rmse = pinn_val_rollout_rmse(model, std, std_b, va_series, va_params,
                                       args.window,
                                       branch_offset=args.branch_offset)
        history.append({"epoch": epoch, "train_loss": epoch_loss,
                        "val_rollout_rmse_c": v_rmse})
        if v_rmse < best_val:
            best_val = v_rmse
            best_epoch = epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        if epoch % 10 == 0 or epoch == args.epochs - 1:
            print(f"[train:pinn] epoch {epoch:3d} loss={epoch_loss:.6f} "
                  f"val_rollout_rmse={v_rmse:.4f} degC")

    if best_state is not None:
        model.load_state_dict(best_state)
    wall_time = time.time() - t_start

    def one_step_rmse(split: str) -> float:
        series, _ = load_arm_series(args.data_dir, split)
        xa, ya, ba = [], [], []
        for s in series:
            x, y = build_windows(s["t_zone"], s["t_out"], s["t_set"], s["q_int"],
                                 args.window)
            xa.append(x)
            ya.append(y)
            ba.append(build_branch(s["t_out"], s["t_set"], s["q_int"], args.window,
                                   offset=args.branch_offset))
        xa = np.concatenate(xa)
        ya = np.concatenate(ya)
        ba = np.concatenate(ba)
        xb = torch.as_tensor(std.transform_x(xa), dtype=torch.float32)
        bb = torch.as_tensor(std_b.transform_x(ba), dtype=torch.float32)
        model.eval()
        with torch.no_grad():
            pred = model(xb, bb).numpy()
        pred = std.inverse_y(pred)
        return float(np.sqrt(np.mean((pred - ya) ** 2)))

    tr_rmse = one_step_rmse("train")
    va_rmse = one_step_rmse("val")
    te_rmse = one_step_rmse("test_id")
    va_roll = pinn_val_rollout_rmse(model, std, std_b, va_series, va_params,
                                    args.window, branch_offset=args.branch_offset)

    os.makedirs(args.out_dir, exist_ok=True)
    suffix = "" if args.rc_params == "true" else "_nominal"
    ckpt_file = f"model_pinn{suffix}.pt"
    metrics_file = f"train_metrics_pinn{suffix}.json"
    ckpt = {
        "arm": "pinn",
        "state_dict": model.state_dict(),
        "window": args.window,
        "hidden": list(args.hidden),
        "input_dim": int(x_tr.shape[1]),
        "input_dim_branch": int(b_tr.shape[1]),
        "seed": args.seed,
        "target": "level",
        "branch_offset": args.branch_offset,
        "rc_params_mode": args.rc_params,
        "standardizer": std.to_dict(),
        "standardizer_branch": std_b.to_dict(),
    }
    torch.save(ckpt, os.path.join(args.out_dir, ckpt_file))

    metrics = {
        "arm": "pinn",
        "seed": args.seed,
        "target": "next-step zone temperature [degC]",
        "target_parameterisation": "level",
        "branch_offset": args.branch_offset,
        "rc_params_mode": args.rc_params,
        "window": args.window,
        "hidden": list(args.hidden),
        "parameters": count_parameters(model),
        "epochs": args.epochs,
        "best_epoch": best_epoch,
        "wall_time_s": wall_time,
        "pinn_horizon": horizon,
        "w_one": args.w_one,
        "w_roll": args.w_roll,
        "w_phys": args.w_phys,
        "phys_scale_w": args.phys_scale,
        "train_rmse_c": tr_rmse,
        "val_rmse_c": va_rmse,
        "test_id_rmse_c": te_rmse,
        "val_rollout_rmse_c": va_roll,
        "history": history,
    }
    with open(os.path.join(args.out_dir, metrics_file), "w") as fh:
        json.dump(metrics, fh, indent=2, sort_keys=True)

    print(f"[train:pinn] parameters={metrics['parameters']}  "
          f"best_epoch={best_epoch}  wall_time={wall_time:.1f}s  "
          f"rc_params={args.rc_params}")
    print(f"[train:pinn] one-step RMSE  train={tr_rmse:.4f}  val={va_rmse:.4f}  "
          f"test_id={te_rmse:.4f} degC")
    print(f"[train:pinn] free-running val rollout RMSE={va_roll:.4f} degC")
    print(f"[train:pinn] wrote {os.path.join(args.out_dir, ckpt_file)} "
          f"and {metrics_file}")


# --------------------------------------------------------------------------
# shared-encoder differentiable RC arm (issue #3 arm (c)) — slice 3
# --------------------------------------------------------------------------

def shared_one_step_rmse(model, std, data_dir: str, split: str, window: int,
                         params_mode: str = "true") -> float:
    """Teacher-forced one-step RMSE [degC] of the shared-encoder arm."""
    model.eval()
    series, params = load_arm_series(data_dir, split)
    params = resolve_params(params_mode, data_dir, params)
    num = 0.0
    den = 0
    with torch.no_grad():
        for s, prm in zip(series, params):
            feats = series_features(s["t_zone"], s["t_out"], s["t_set"],
                                    s["q_int"])
            n = len(feats)
            ks = np.arange(window, n)
            slices = np.stack([feats[k - window: k + 1] for k in ks])
            wall0 = np.array([s["t_wall"][k - 1] for k in ks], dtype=np.float64)
            p = rc_param_tensors([prm] * len(ks))
            pred, _ = shared_rollout_torch(
                model, std, torch.as_tensor(slices, dtype=torch.float32),
                torch.as_tensor(wall0, dtype=torch.float64), p, window)
            truth = slices[:, window, 3]
            num += float(np.sum((pred[:, window].numpy() - truth) ** 2))
            den += len(ks)
    return float(np.sqrt(num / max(den, 1)))


def shared_val_rollout_rmse(model, std, series_list, params_list,
                            window: int) -> float:
    """Free-running rollout RMSE [degC] of the shared-encoder arm."""
    model.eval()
    feats = np.stack([
        series_features(s["t_zone"], s["t_out"], s["t_set"], s["q_int"])
        for s in series_list])
    wall0 = np.array([s["t_wall"][window - 1] for s in series_list],
                     dtype=np.float64)
    pred = rollout_shared(model, std, feats, wall0, params_list, window)
    err = pred[:, window:] - feats[:, window:, 3]
    return float(np.sqrt(np.mean(err ** 2)))


def train_shared(args) -> None:
    """Train the shared-encoder differentiable RC model (issue #3 arm (c)).

    Loss (both terms in degC):

        L = w_one  * MSE_one_step  (teacher-forced single RC step)
          + w_roll * MSE_rollout   (multi-step free-running rollout)

    There is deliberately NO heat-balance-residual term: the physics is
    *structural* in this arm (the network predicts RC parameter
    corrections and a small heat flow; the differentiable 2R2C integrator
    produces the temperature), so the residual of the model's own
    equations is identically zero.  The heat-balance gate is therefore
    decided on the trajectory against the TRUE physics, as for every arm.
    """
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(args.threads)

    if args.target != "level":
        raise SystemExit("the shared-encoder arm only supports --target level "
                         "(the shared default).")

    t_start = time.time()
    tr_series, tr_params = load_arm_series(args.data_dir, "train")
    va_series, va_params = load_arm_series(args.data_dir, "val")
    tr_params = resolve_params(args.rc_params, args.data_dir, tr_params)
    va_params = resolve_params(args.rc_params, args.data_dir, va_params)

    xs = []
    for s in tr_series:
        x, _ = build_windows(s["t_zone"], s["t_out"], s["t_set"], s["q_int"],
                             args.window)
        xs.append(x)
    x_tr = np.concatenate(xs)
    std = Standardizer.fit_x(x_tr)   # input statistics only (no target)

    model = make_shared(int(x_tr.shape[1]), tuple(args.hidden), args.latent,
                        seed=args.seed)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = torch.nn.MSELoss()

    tr_feats = [series_features(s["t_zone"], s["t_out"], s["t_set"], s["q_int"])
                for s in tr_series]
    tr_len = [len(f) for f in tr_feats]

    n = len(x_tr)
    rng = np.random.default_rng(args.seed)
    horizon = args.shared_horizon
    best_val = float("inf")
    best_state = None
    best_epoch = -1
    history: List[Dict] = []

    for epoch in range(args.epochs):
        model.train()
        perm = rng.permutation(n)
        epoch_loss = 0.0
        n_batches = 0
        for i in range(0, n, args.batch_size):
            idx = perm[i: i + args.batch_size]
            # ---- one-step (teacher forced) ----
            starts1 = []
            for _ in range(len(idx)):
                si = int(rng.integers(len(tr_series)))
                kk = int(rng.integers(args.window, tr_len[si]))
                starts1.append((si, kk))
            feats1 = np.stack([tr_feats[si][kk - args.window: kk + 1]
                               for si, kk in starts1])
            wall1 = np.array([tr_series[si]["t_wall"][kk - 1]
                              for si, kk in starts1], dtype=np.float64)
            p1 = rc_param_tensors([tr_params[si] for si, _ in starts1])
            f1 = torch.as_tensor(feats1, dtype=torch.float32)
            w1 = torch.as_tensor(wall1, dtype=torch.float64)
            pred1, _ = shared_rollout_torch(model, std, f1, w1, p1, args.window)
            l_one = loss_fn(pred1[:, args.window], f1[:, args.window, 3])

            # ---- multi-step (rollout) ----
            starts = []
            for _ in range(args.shared_rollout_per_series):
                for si in range(len(tr_series)):
                    lo = args.window
                    hi = tr_len[si] - horizon
                    starts.append((si, int(rng.integers(lo, hi))))
            feats = np.stack([tr_feats[si][kk - args.window: kk + horizon]
                              for si, kk in starts])
            wall0 = np.array([tr_series[si]["t_wall"][kk - 1]
                              for si, kk in starts], dtype=np.float64)
            pt = rc_param_tensors([tr_params[si] for si, _ in starts])
            fb = torch.as_tensor(feats, dtype=torch.float32)
            wb = torch.as_tensor(wall0, dtype=torch.float64)
            pred, _ = shared_rollout_torch(model, std, fb, wb, pt, args.window)
            truth = fb[:, args.window:, 3]
            l_roll = torch.mean((pred[:, args.window:] - truth) ** 2)

            opt.zero_grad()
            loss = args.w_one * l_one + args.w_roll * l_roll
            loss.backward()
            opt.step()
            epoch_loss += float(loss.item())
            n_batches += 1
        epoch_loss /= max(n_batches, 1)

        v_rmse = shared_val_rollout_rmse(model, std, va_series, va_params,
                                         args.window)
        history.append({"epoch": epoch, "train_loss": epoch_loss,
                        "val_rollout_rmse_c": v_rmse})
        if v_rmse < best_val:
            best_val = v_rmse
            best_epoch = epoch
            best_state = {k: v.detach().clone()
                          for k, v in model.state_dict().items()}
        if epoch % 10 == 0 or epoch == args.epochs - 1:
            print(f"[train:shared] epoch {epoch:3d} loss={epoch_loss:.6f} "
                  f"val_rollout_rmse={v_rmse:.4f} degC")

    if best_state is not None:
        model.load_state_dict(best_state)
    wall_time = time.time() - t_start

    tr_rmse = shared_one_step_rmse(model, std, args.data_dir, "train",
                                   args.window, args.rc_params)
    va_rmse = shared_one_step_rmse(model, std, args.data_dir, "val",
                                   args.window, args.rc_params)
    te_rmse = shared_one_step_rmse(model, std, args.data_dir, "test_id",
                                   args.window, args.rc_params)
    va_roll = shared_val_rollout_rmse(model, std, va_series, va_params,
                                       args.window)

    os.makedirs(args.out_dir, exist_ok=True)
    suffix = "" if args.rc_params == "true" else "_nominal"
    ckpt_file = f"model_shared{suffix}.pt"
    metrics_file = f"train_metrics_shared{suffix}.json"
    ckpt = {
        "arm": "shared",
        "state_dict": model.state_dict(),
        "window": args.window,
        "hidden": list(args.hidden),
        "latent": args.latent,
        "input_dim": int(x_tr.shape[1]),
        "seed": args.seed,
        "target": "level",
        "rc_params_mode": args.rc_params,
        "standardizer": std.to_dict(),
    }
    torch.save(ckpt, os.path.join(args.out_dir, ckpt_file))

    metrics = {
        "arm": "shared",
        "seed": args.seed,
        "target": "next-step zone temperature [degC]",
        "target_parameterisation": "level",
        "rc_params_mode": args.rc_params,
        "window": args.window,
        "hidden": list(args.hidden),
        "latent": args.latent,
        "parameters": count_parameters(model),
        "epochs": args.epochs,
        "best_epoch": best_epoch,
        "wall_time_s": wall_time,
        "shared_horizon": horizon,
        "w_one": args.w_one,
        "w_roll": args.w_roll,
        "train_rmse_c": tr_rmse,
        "val_rmse_c": va_rmse,
        "test_id_rmse_c": te_rmse,
        "val_rollout_rmse_c": va_roll,
        "history": history,
    }
    with open(os.path.join(args.out_dir, metrics_file), "w") as fh:
        json.dump(metrics, fh, indent=2, sort_keys=True)

    print(f"[train:shared] parameters={metrics['parameters']}  "
          f"best_epoch={best_epoch}  wall_time={wall_time:.1f}s  "
          f"rc_params={args.rc_params}")
    print(f"[train:shared] one-step RMSE  train={tr_rmse:.4f}  val={va_rmse:.4f}  "
          f"test_id={te_rmse:.4f} degC")
    print(f"[train:shared] free-running val rollout RMSE={va_roll:.4f} degC")
    print(f"[train:shared] wrote {os.path.join(args.out_dir, ckpt_file)} "
          f"and {metrics_file}")


def pinn_val_rollout_rmse(model, std, std_b, series_list, params_list,
                          window: int, branch_offset: int = 0) -> float:
    """Free-running rollout RMSE [degC] of the PINN on a list of series."""
    model.eval()
    n_all = len(series_list)
    feats = np.stack([
        series_features(s["t_zone"], s["t_out"], s["t_set"], s["q_int"])
        for s in series_list])
    wall0 = np.array([s["t_wall"][window - 1] for s in series_list],
                     dtype=np.float64)
    pred = rollout_pinn(model, std, std_b, feats, wall0, params_list, window,
                        branch_offset=branch_offset)
    err = pred[:, window:] - feats[:, window:, 3]
    return float(np.sqrt(np.mean(err ** 2)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Train a surrogate arm")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--data-dir", type=str, default=DEFAULT_DATA_DIR)
    ap.add_argument("--out-dir", type=str, default=DEFAULT_DATA_DIR)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--window", type=int, default=12)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--hidden", type=int, nargs="+", default=[128, 128])
    ap.add_argument("--target", type=str, default="level", choices=["level", "delta"],
                    help="regression target: 'level' = t_zone[k], "
                         "'delta' = t_zone[k] - t_zone[k-1] (delta diverges in "
                         "free-running rollout with one-step training; see "
                         "module docstring)")
    ap.add_argument("--threads", type=int, default=1)
    # ---- PINN arm (slice 2) -------------------------------------------
    ap.add_argument("--arm", type=str, default="mlp",
                    choices=["mlp", "pinn", "shared"],
                    help="'mlp' = plain-MLP baseline (slice 1); 'pinn' = "
                         "physics-informed PI-DeepONet-style arm with a "
                         "multi-step rollout loss and a heat-balance "
                         "residual loss (slice 2); 'shared' = NeuralBES-style "
                         "shared-encoder differentiable RC model (slice 3, "
                         "issue #3 arm (c))")
    ap.add_argument("--rc-params", type=str, default="true",
                    choices=["true", "nominal"],
                    help="RC parameters used by the physics loss / rollout: "
                         "'true' = the per-series true parameters (the "
                         "assumption of slices 1-2); 'nominal' = the "
                         "train-median parameters for every series (the "
                         "parameter-mismatch experiment of slice 3)")
    ap.add_argument("--pinn-horizon", type=int, default=24,
                    help="rollout horizon (steps) of the multi-step loss")
    ap.add_argument("--pinn-rollout-per-series", type=int, default=2,
                    help="number of random rollout windows drawn per training "
                         "series and per optimiser step")
    ap.add_argument("--w-one", type=float, default=1.0,
                    help="weight of the one-step (teacher-forced) data loss")
    ap.add_argument("--w-roll", type=float, default=1.0,
                    help="weight of the multi-step (rollout) data loss")
    ap.add_argument("--w-phys", type=float, default=1.0,
                    help="weight of the heat-balance residual loss")
    ap.add_argument("--phys-scale", type=float, default=100.0,
                    help="normalisation scale [W] of the heat-balance "
                         "residual loss")
    ap.add_argument("--branch-offset", type=int, default=0,
                    help="PINN branch offset: 0 = branch sees the drivers "
                         "of the step being predicted (physically "
                         "available, and what the heat-balance residual "
                         "needs); 1 = branch sees the previous step's "
                         "drivers, i.e. exactly the information the "
                         "plain-MLP window contains (information-matched "
                         "comparison)")
    # ---- shared-encoder RC arm (slice 3) ------------------------------
    ap.add_argument("--latent", type=int, default=32,
                    help="size of the shared-encoder latent code (arm (c))")
    ap.add_argument("--shared-horizon", type=int, default=24,
                    help="rollout horizon (steps) of the multi-step loss of "
                         "the shared-encoder arm")
    ap.add_argument("--shared-rollout-per-series", type=int, default=2,
                    help="number of random rollout windows drawn per "
                         "training series and per optimiser step (arm (c))")
    args = ap.parse_args()

    if args.arm == "pinn":
        train_pinn(args)
        return

    if args.arm == "shared":
        train_shared(args)
        return

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    torch.set_num_threads(args.threads)  # deterministic reductions on CPU

    t_start = time.time()
    x_tr, y_tr, _, _, n_tr_series = collect_windows(args.data_dir, "train",
                                                     args.window, args.target)
    x_va, y_va, _, _, n_va_series = collect_windows(args.data_dir, "val",
                                                     args.window, args.target)
    x_te, y_te, _, _, n_te_series = collect_windows(args.data_dir, "test_id",
                                                     args.window, args.target)
    std = Standardizer.fit(x_tr, y_tr)

    model = make_model(x_tr.shape[1], tuple(args.hidden), seed=args.seed)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    loss_fn = torch.nn.MSELoss()

    xt = torch.as_tensor(std.transform_x(x_tr), dtype=torch.float32)
    yt = torch.as_tensor(std.transform_y(y_tr), dtype=torch.float32)
    xv = torch.as_tensor(std.transform_x(x_va), dtype=torch.float32)

    n = len(xt)
    rng = np.random.default_rng(args.seed)
    best_val = float("inf")
    best_state = None
    best_epoch = -1
    history = []

    for epoch in range(args.epochs):
        model.train()
        perm = rng.permutation(n)
        epoch_loss = 0.0
        for i in range(0, n, args.batch_size):
            idx = perm[i: i + args.batch_size]
            opt.zero_grad()
            pred = model(xt[idx])
            loss = loss_fn(pred, yt[idx])
            loss.backward()
            opt.step()
            epoch_loss += float(loss.item()) * len(idx)
        epoch_loss /= n

        model.eval()
        with torch.no_grad():
            vpred = model(xv).numpy()
        v_rmse = float(np.sqrt(np.mean((std.inverse_y(vpred) - y_va) ** 2)))
        history.append({"epoch": epoch, "train_loss": epoch_loss,
                        "val_rmse_target": v_rmse})
        if v_rmse < best_val:
            best_val = v_rmse
            best_epoch = epoch
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
        if epoch % 20 == 0 or epoch == args.epochs - 1:
            print(f"[train] epoch {epoch:3d} loss={epoch_loss:.6f} "
                  f"val_rmse(target)={v_rmse:.5f}")

    if best_state is not None:
        model.load_state_dict(best_state)
    wall_time = time.time() - t_start

    def rmse_level(split: str) -> float:
        """One-step RMSE in degC (level space) on a split."""
        x, y, prev, level, _ = collect_windows(args.data_dir, split, args.window,
                                                args.target)
        pred = predict_windows(model, std, x)
        pred_level = pred + prev if args.target == "delta" else pred
        return float(np.sqrt(np.mean((pred_level - level) ** 2)))

    tr_rmse = rmse_level("train")
    va_rmse = rmse_level("val")
    te_rmse = rmse_level("test_id")

    os.makedirs(args.out_dir, exist_ok=True)
    ckpt = {
        "state_dict": model.state_dict(),
        "window": args.window,
        "hidden": list(args.hidden),
        "input_dim": int(x_tr.shape[1]),
        "seed": args.seed,
        "target": args.target,
        "standardizer": std.to_dict(),
    }
    torch.save(ckpt, os.path.join(args.out_dir, "model.pt"))

    metrics = {
        "seed": args.seed,
        "target": "next-step zone temperature [degC]",
        "target_parameterisation": args.target,
        "window": args.window,
        "hidden": list(args.hidden),
        "parameters": count_parameters(model),
        "epochs": args.epochs,
        "best_epoch": best_epoch,
        "wall_time_s": wall_time,
        "n_train_series": n_tr_series,
        "n_val_series": n_va_series,
        "n_test_id_series": n_te_series,
        "n_train_windows": int(len(x_tr)),
        "n_val_windows": int(len(x_va)),
        "n_test_id_windows": int(len(x_te)),
        "train_rmse_c": tr_rmse,
        "val_rmse_c": va_rmse,
        "test_id_rmse_c": te_rmse,
        "history": history,
    }
    with open(os.path.join(args.out_dir, "train_metrics.json"), "w") as fh:
        json.dump(metrics, fh, indent=2, sort_keys=True)

    print(f"[train] parameters={metrics['parameters']}  best_epoch={best_epoch}  "
          f"wall_time={wall_time:.1f}s")
    print(f"[train] one-step RMSE  train={tr_rmse:.4f}  val={va_rmse:.4f}  "
          f"test_id={te_rmse:.4f} degC")
    print(f"[train] wrote {os.path.join(args.out_dir, 'model.pt')} and "
          f"train_metrics.json")


if __name__ == "__main__":
    main()

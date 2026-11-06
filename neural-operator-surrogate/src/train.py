"""Train the plain-MLP baseline (arm (a) of issue #3) on the synthetic data.

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
default back to delta without multi-step (rollout) loss — that is slice-2
work, not a one-line change.

Artefacts are written to `data/` (git-ignored scratch):
    model.pt            - weights + config + scaler statistics
    train_metrics.json  - timings, parameter count, RMSEs

Usage:
    python src/train.py --seed 42
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gen_data import DEFAULT_DATA_DIR, iter_series, load_split  # noqa: E402
from models import (Standardizer, build_windows, count_parameters,  # noqa: E402
                    make_model, predict_windows)


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


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the plain-MLP baseline")
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
    args = ap.parse_args()

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

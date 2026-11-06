"""Tests of the PINN / PI-DeepONet arm (slice 2).

Covers:
  * build_branch offset alignment: row counts match build_windows and
    offset 1 lags the drivers by exactly one step (regression test for
    the slice-2 supervisor fix: the original slice returned
    exo[window - offset:], one row too many for offset 1),
  * the heat-balance residual of the TRUE trajectory is ~0 through
    pinn_rollout_torch (the residual implementation must vanish on the
    exact RC dynamics),
  * the PINN rollout is deterministic, finite, and warm-starts on truth,
  * a saved PINN checkpoint round-trips its branch_offset (evaluate.py
    reads it to reproduce the information-matched ablation).
"""

from __future__ import annotations

import os

import numpy as np
import torch

from models import (PINNZone, Standardizer, build_branch, build_windows,
                    make_pinn, pinn_rollout_torch, rollout_pinn,
                    series_features)
from rc_model import RCParams, rollout_numpy


def _inputs(n: int = 240, seed: int = 0):
    rng = np.random.default_rng(seed)
    t_out = 12.0 + 6.0 * np.sin(2 * np.pi * np.arange(n) / 24.0) + rng.normal(0, 0.5, n)
    t_set = np.where(np.arange(n) % 24 < 16, 21.0, 17.0)
    q_int = rng.uniform(30.0, 250.0, n)
    return t_out, t_set, q_int


def test_build_branch_offset_alignment():
    """build_branch rows must match build_windows rows for every offset."""
    n, window = 720, 12
    t_out, t_set, q_int = _inputs(n=n)
    t_zone = np.zeros(n)
    x, y = build_windows(t_zone, t_out, t_set, q_int, window)
    assert x.shape[0] == n - window == y.shape[0]
    b0 = build_branch(t_out, t_set, q_int, window, offset=0)
    b1 = build_branch(t_out, t_set, q_int, window, offset=1)
    assert b0.shape == (n - window, 5)
    assert b1.shape == (n - window, 5)
    # offset 0, row i = drivers of step k = window + i
    np.testing.assert_array_equal(b0[0], [t_out[window], t_set[window],
                                          q_int[window],
                                          np.sin(2 * np.pi * window / 24.0),
                                          np.cos(2 * np.pi * window / 24.0)])
    # offset 1, row i = drivers of step k - 1 (the lagged drivers)
    np.testing.assert_array_equal(b1[0], [t_out[window - 1], t_set[window - 1],
                                          q_int[window - 1],
                                          np.sin(2 * np.pi * (window - 1) / 24.0),
                                          np.cos(2 * np.pi * (window - 1) / 24.0)])
    # offset 1 is exactly offset 0 shifted by one row
    np.testing.assert_array_equal(b1[1:], b0[:-1])


class _TruthModel(torch.nn.Module):
    """Returns the true next-step zone temperature, standardised.

    The rollout calls forward once per predicted step, in order, so a
    stateful counter replays the true trajectory.  Used to prove the
    physics residual vanishes on the exact RC dynamics.
    """

    def __init__(self, targets_std):
        super().__init__()
        self.targets = [float(v) for v in targets_std]
        self.i = 0

    def forward(self, x, b):
        v = self.targets[self.i]
        self.i += 1
        return torch.as_tensor([v], dtype=torch.float32)


def test_pinn_rollout_true_trajectory_residual_near_zero():
    """The heat-balance residual of the exact RC trajectory is ~0."""
    p = RCParams()
    window = 12
    n = 240
    t_out, t_set, q_int = _inputs(n=n)
    roll = rollout_numpy(p, t_out, t_set, q_int)
    t_zone = roll["t_air"]
    t_wall = roll["t_wall"]

    y_mean, y_std = 20.0, 1.0
    std = Standardizer(np.zeros(window * 6), np.ones(window * 6), y_mean, y_std)
    std_b = Standardizer(np.zeros(5), np.ones(5), 0.0, 1.0)
    targets_std = (t_zone[window:] - y_mean) / y_std
    model = _TruthModel(targets_std)

    feats = series_features(t_zone, t_out, t_set, q_int)
    fb = torch.as_tensor(feats[None, ...], dtype=torch.float32)
    wb = torch.as_tensor([t_wall[window - 1]], dtype=torch.float64)
    from models import rc_param_tensors
    pt = rc_param_tensors([p.to_dict()])
    pred, resid = pinn_rollout_torch(model, std, std_b, fb, wb, pt, window)
    pred_np = pred.numpy()[0]
    resid_np = resid.numpy()[0]
    # the replayed trajectory is the truth (up to float32 rounding)
    np.testing.assert_allclose(pred_np[window:], t_zone[window:], atol=1e-4)
    # ... so its heat-balance residual must vanish
    assert float(np.max(np.abs(resid_np[window:]))) < 1e-2, (
        "residual of the exact trajectory: max %.3e degC"
        % float(np.max(np.abs(resid_np[window:]))))


def test_pinn_rollout_deterministic_finite_and_warm_starts():
    """Same seed -> same model -> same rollout; warm start is truth."""
    p = RCParams()
    window = 12
    n = 240
    t_out, t_set, q_int = _inputs(n=n)
    roll = rollout_numpy(p, t_out, t_set, q_int)
    feats = series_features(roll["t_air"], t_out, t_set, q_int)
    wall0 = np.array([roll["t_wall"][window - 1]], dtype=np.float64)

    std = Standardizer(np.zeros(window * 6), np.ones(window * 6), 20.0, 1.0)
    std_b = Standardizer(np.zeros(5), np.ones(5), 0.0, 1.0)
    m1 = make_pinn(window * 6, 5, seed=42)
    m2 = make_pinn(window * 6, 5, seed=42)
    for a, b in zip(m1.parameters(), m2.parameters()):
        torch.testing.assert_close(a, b)

    pred1 = rollout_pinn(m1, std, std_b, feats[None, ...], wall0,
                         [p.to_dict()], window)
    pred2 = rollout_pinn(m1, std, std_b, feats[None, ...], wall0,
                         [p.to_dict()], window)
    np.testing.assert_array_equal(pred1, pred2)
    assert np.isfinite(pred1).all()
    # warm-start steps are the truth, not predictions (float32 rounding in
    # the rollout, so compare with a tolerance, not exactly)
    np.testing.assert_allclose(pred1[0, :window], feats[:window, 3], atol=1e-4)


def test_pinn_checkpoint_round_trips_branch_offset(tmp_path):
    """load_pinn must recover the branch_offset a checkpoint was trained with."""
    import evaluate

    std = Standardizer(np.zeros(72), np.ones(72), 20.0, 1.0)
    std_b = Standardizer(np.zeros(5), np.ones(5), 0.0, 1.0)
    model = PINNZone(72, 5)
    ckpt = {
        "arm": "pinn",
        "state_dict": model.state_dict(),
        "window": 12,
        "hidden": [128, 128],
        "input_dim": 72,
        "input_dim_branch": 5,
        "seed": 42,
        "target": "level",
        "branch_offset": 1,
        "standardizer": std.to_dict(),
        "standardizer_branch": std_b.to_dict(),
    }
    path = os.path.join(str(tmp_path), "model_pinn.pt")
    torch.save(ckpt, path)
    _, _, _, loaded = evaluate.load_pinn(str(tmp_path))
    assert int(loaded.get("branch_offset", 0)) == 1

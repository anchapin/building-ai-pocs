"""Surrogate models and feature construction for the neural-operator POC.

Slice 1 ships only the plain-MLP baseline (arm (a) of issue #3): a small
fully-connected network that maps a fixed window of past inputs to the
next-step zone temperature.  The same feature builder and the same target
are re-used by the physics-informed / neural-operator arm (slice 2), so both
arms see identical data.

Slice 2 adds the PI-DeepONet-style arm (issue #3 arm (b)):

  * `PINNZone` — a DeepONet-style trunk/branch network.  The *trunk*
    encodes the state history (the same window of past inputs the MLP
    uses), the *branch* encodes the driving inputs at the step being
    predicted, and the prediction is the inner product of the two
    embeddings (plus a bias).  This is the operator-learning structure:
    the trunk is the "input function" (the history of the zone), the
    branch is the "output location" (the hour whose temperature we want).
  * `pinn_rollout_torch` — a *differentiable* free-running rollout of the
    PINN that also returns the per-step **heat-balance residual** of the
    zone, computed from the differentiable 2R2C equations of `rc_model.py`.
    That residual is the physics loss of the PINN arm; the multi-step
    (rollout) temperature error is the data loss.

Both arms keep the SAME target (next-step zone temperature, `level`
parameterisation) and the SAME feature builder, so the comparison is
like-for-like.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import torch
from torch import nn

# Feature order inside one time step of the input window.
FEATURE_NAMES = ("t_out", "t_set", "q_int", "t_zone", "sin_hod", "cos_hod")
N_FEATURES = len(FEATURE_NAMES)


class ZoneMLP(nn.Module):
    """Plain MLP baseline: window of past inputs -> next zone temperature."""

    def __init__(self, n_inputs: int, hidden: Sequence[int] = (128, 128)):
        super().__init__()
        layers: list[nn.Module] = []
        prev = n_inputs
        for h in hidden:
            layers.append(nn.Linear(prev, h))
            layers.append(nn.SiLU())
            prev = h
        layers.append(nn.Linear(prev, 1))
        self.net = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


@dataclass
class Standardizer:
    """Feature/target z-scoring (statistics fitted on the training split)."""

    x_mean: np.ndarray
    x_std: np.ndarray
    y_mean: float
    y_std: float

    @staticmethod
    def fit(x: np.ndarray, y: np.ndarray) -> "Standardizer":
        return Standardizer(x.mean(axis=0), x.std(axis=0) + 1e-8,
                            float(y.mean()), float(y.std() + 1e-8))

    @staticmethod
    def fit_x(x: np.ndarray) -> "Standardizer":
        """Fit only the input statistics (target statistics stay neutral)."""
        return Standardizer(x.mean(axis=0), x.std(axis=0) + 1e-8, 0.0, 1.0)

    def transform_x(self, x: np.ndarray) -> np.ndarray:
        return (x - self.x_mean) / self.x_std

    def transform_y(self, y: np.ndarray) -> np.ndarray:
        return (y - self.y_mean) / self.y_std

    def inverse_y(self, y: np.ndarray) -> np.ndarray:
        return y * self.y_std + self.y_mean

    def to_dict(self) -> Dict:
        return {"x_mean": self.x_mean, "x_std": self.x_std,
                "y_mean": np.asarray(self.y_mean), "y_std": np.asarray(self.y_std)}

    @staticmethod
    def from_dict(d: Dict) -> "Standardizer":
        return Standardizer(np.asarray(d["x_mean"]), np.asarray(d["x_std"]),
                            float(d["y_mean"]), float(d["y_std"]))


def hod_features(hours: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Sin/cos encoding of the hour of day (period 24 h)."""
    ang = 2.0 * np.pi * (hours % 24) / 24.0
    return np.sin(ang), np.cos(ang)


def window_features(t_zone: np.ndarray, t_out: np.ndarray, t_set: np.ndarray,
                    q_int: np.ndarray, window: int, k: int,
                    hour_offset: int = 0) -> np.ndarray:
    """Feature vector predicting `t_zone[k]` from the *past* `window` steps.

    The window covers indices k-window .. k-1 (strictly the past), so the
    target value itself is never an input.
    """
    if k < window:
        raise ValueError("not enough history for the requested window")
    n = len(t_zone)
    hours = np.arange(hour_offset, hour_offset + n)
    sin_h, cos_h = hod_features(hours)
    feats = np.stack([t_out, t_set, q_int, t_zone, sin_h, cos_h], axis=1)
    return feats[k - window: k].reshape(-1)


def build_windows(t_zone: np.ndarray, t_out: np.ndarray, t_set: np.ndarray,
                  q_int: np.ndarray, window: int,
                  hour_offset: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """Sliding windows of the past `window` steps.

    Returns X with shape (n - window, window * N_FEATURES) and the
    next-step target y = t_zone[k], where the window of X holds the
    strictly-past steps k-window .. k-1.
    """
    n = len(t_zone)
    if n < window + 1:
        raise ValueError("series shorter than the window")
    hours = np.arange(hour_offset, hour_offset + n)
    sin_h, cos_h = hod_features(hours)
    feats = np.stack([t_out, t_set, q_int, t_zone, sin_h, cos_h], axis=1)
    idx = np.arange(window, n)
    win = np.stack([feats[k - window: k] for k in idx], axis=0)
    x = win.reshape(len(idx), window * N_FEATURES)
    y = t_zone[idx]
    return x, y


def make_model(input_dim: int, hidden: Sequence[int] = (128, 128),
               seed: int = 42) -> ZoneMLP:
    """Deterministically initialised MLP."""
    torch.manual_seed(seed)
    model = ZoneMLP(input_dim, hidden)
    return model


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def predict_windows(model: ZoneMLP, std: Standardizer, x: np.ndarray,
                    batch_size: int = 4096) -> np.ndarray:
    """Batched prediction in physical units (degC)."""
    model.eval()
    out: list[np.ndarray] = []
    with torch.no_grad():
        for i in range(0, len(x), batch_size):
            xb = torch.as_tensor(std.transform_x(x[i: i + batch_size]), dtype=torch.float32)
            yb = model(xb).numpy()
            out.append(std.inverse_y(yb))
    return np.concatenate(out) if out else np.zeros(0)


# --------------------------------------------------------------------------
# slice 2: PI-DeepONet-style physics-informed surrogate (issue #3 arm (b))
# --------------------------------------------------------------------------

# Driving (exogenous) inputs of one time step: everything except the zone
# temperature itself.  These are the inputs of the DeepONet *branch*.
EXO_NAMES = ("t_out", "t_set", "q_int", "sin_hod", "cos_hod")
N_EXO = len(EXO_NAMES)


def series_features(t_zone: np.ndarray, t_out: np.ndarray, t_set: np.ndarray,
                    q_int: np.ndarray, hour_offset: int = 0) -> np.ndarray:
    """Full feature matrix of one series, shape (n, N_FEATURES).

    Identical layout to `build_windows` (see FEATURE_NAMES), so the MLP
    and the PINN arm see exactly the same inputs.
    """
    n = len(t_zone)
    hours = np.arange(hour_offset, hour_offset + n)
    sin_h, cos_h = hod_features(hours)
    return np.stack([t_out, t_set, q_int, t_zone, sin_h, cos_h], axis=1)


def build_branch(t_out: np.ndarray, t_set: np.ndarray, q_int: np.ndarray,
                 window: int, hour_offset: int = 0, offset: int = 0) -> np.ndarray:
    """Branch features aligned with the `build_windows` targets.

    Row i corresponds to the target index k = window + i, i.e. the driving
    inputs of the step whose zone temperature is being predicted.

    `offset` shifts the driver information by that many steps:
      * offset 0 (default): the drivers of the step being predicted
        (physically available at prediction time, and what the
        heat-balance residual of that step needs);
      * offset 1: the drivers of the *previous* step, i.e. exactly the
        information the plain-MLP window contains (its window stops at
        k-1).  Used for the information-matched comparison.
    """
    n = len(t_out)
    hours = np.arange(hour_offset, hour_offset + n)
    sin_h, cos_h = hod_features(hours)
    exo = np.stack([t_out, t_set, q_int, sin_h, cos_h], axis=1)
    # Row i is the drivers of step k - offset, where k = window + i is the
    # target index; the slice must end at n - offset so the row count
    # matches build_windows (n - window rows) for every offset.
    return exo[window - offset: n - offset]


def _mlp_stack(n_in: int, hidden: Sequence[int]) -> nn.Sequential:
    layers: list[nn.Module] = []
    prev = n_in
    for h in hidden:
        layers.append(nn.Linear(prev, h))
        layers.append(nn.SiLU())
        prev = h
    return nn.Sequential(*layers)


class PINNZone(nn.Module):
    """PI-DeepONet-style zone surrogate: trunk (history) x branch (drivers).

    The prediction of the next-step zone temperature is the (scaled)
    inner product of the trunk embedding of the past window and the branch
    embedding of the driving inputs of the step being predicted.
    """

    def __init__(self, n_trunk: int, n_branch: int,
                 hidden: Sequence[int] = (128, 128)):
        super().__init__()
        self.hidden = tuple(hidden)
        self.trunk = _mlp_stack(n_trunk, hidden)
        self.branch = _mlp_stack(n_branch, hidden)
        self.bias = nn.Parameter(torch.zeros(1))

    def forward(self, x: torch.Tensor, b: torch.Tensor) -> torch.Tensor:
        t = self.trunk(x)
        br = self.branch(b)
        return (t * br).sum(dim=-1) / math.sqrt(t.shape[-1]) + self.bias


def make_pinn(input_dim_trunk: int, input_dim_branch: int,
              hidden: Sequence[int] = (128, 128), seed: int = 42) -> PINNZone:
    """Deterministically initialised PI-DeepONet-style model."""
    torch.manual_seed(seed)
    return PINNZone(input_dim_trunk, input_dim_branch, hidden)


def rc_param_tensors(params_list: Sequence[Dict[str, float]]) -> Dict[str, torch.Tensor]:
    """Batch the (per-series) RC parameters into float64 tensors.

    `UA_win` is the product U_win * A_win (window conductance).  The
    remaining entries are the controller parameters of `rc_model.py`.
    """
    def col(name: str) -> torch.Tensor:
        return torch.as_tensor([float(p[name]) for p in params_list],
                               dtype=torch.float64)

    return {
        "C_air": col("C_air"),
        "C_wall": col("C_wall"),
        "R_wall": col("R_wall"),
        "R_air": col("R_air"),
        "UA_win": col("U_win") * col("A_win"),
        "UA_inf": col("UA_inf"),
        "K_sup": col("K_sup"),
        "T_sup_heat_max": col("T_sup_heat_max"),
        "T_sup_cool_min": col("T_sup_cool_min"),
        "Q_heat_max": col("Q_heat_max"),
        "Q_cool_max": col("Q_cool_max"),
    }


def pinn_rollout_torch(model: PINNZone, std_trunk: Standardizer,
                        std_branch: Standardizer, feats: torch.Tensor,
                        wall0: torch.Tensor, p: Dict[str, torch.Tensor],
                        window: int, dt: float = 3600.0,
                        branch_offset: int = 0):
    """Differentiable free-running rollout of the PINN + physics residual.

    Parameters
    ----------
    feats : (B, n, N_FEATURES) float tensor of *physical* features.  The
        zone-temperature column holds the truth for the first `window`
        steps (the warm start) and is overwritten by the predictions
        afterwards.
    wall0 : (B,) float64 tensor with the mass-node state *before* the
        first modelled step (t_wall[k0 - 1] in the data convention).
    p : batched RC parameters (see `rc_param_tensors`).
    branch_offset : the branch (driving-input) features are taken from
        step `k - branch_offset` instead of step `k`.  Offset 0 = the
        drivers of the step being predicted (physically available);
        offset 1 = the lagged drivers, i.e. exactly the information the
        plain-MLP window contains (information-matched comparison).

    Returns
    -------
    pred : (B, n) float tensor of zone temperatures [degC] (the first
        `window` entries are the warm-start truth).
    resid : (B, n) float tensor with the per-step heat-balance residual
        [degC]:  pred[k] minus the temperature the differentiable 2R2C
        equations produce from the pre-step state.  Zero for the
        warm-start steps (no prediction is made there).

    Conventions (identical to `rc_model.py` and to `evaluate.py`):
      * data index k is the state *after* step k, so the pre-step state of
        step k is the zone temperature at index k-1;
      * the mass node follows  dT_wall/dt = (T_air - T_wall)/R_wall  and
        is initialised with the true wall state of the segment start.
    """
    b, n, _ = feats.shape
    dtype = torch.float32
    x_mean = torch.as_tensor(std_trunk.x_mean, dtype=dtype)
    x_std = torch.as_tensor(std_trunk.x_std, dtype=dtype)
    b_mean = torch.as_tensor(std_branch.x_mean, dtype=dtype)
    b_std = torch.as_tensor(std_branch.x_std, dtype=dtype)
    y_mean = float(std_trunk.y_mean)
    y_std = float(std_trunk.y_std)

    hist = feats[:, :window].clone()
    pred = feats[:, :, 3].clone()
    resid = torch.zeros(b, n, dtype=dtype)
    wall = wall0.clone()

    p64 = {k: v.to(torch.float64) for k, v in p.items()}
    for k in range(window, n):
        x = (hist.reshape(b, -1) - x_mean) / x_std
        kb = max(k - branch_offset, 0)
        br = (feats[:, kb][:, [0, 1, 2, 4, 5]] - b_mean) / b_std
        out = model(x, br)
        t_next = out * y_std + y_mean
        pred[:, k] = t_next

        # ---- heat-balance residual of step k (differentiable) ----------
        a_pre = hist[:, -1, 3].to(torch.float64)          # pre-step air state
        t_out = feats[:, k, 0].to(torch.float64)
        t_set = feats[:, k, 1].to(torch.float64)
        q_int = feats[:, k, 2].to(torch.float64)
        q_aw = (a_pre - wall) / p64["R_wall"]
        q_win = p64["UA_win"] * (t_out - a_pre)
        q_inf = p64["UA_inf"] * (t_out - a_pre)
        err = t_set - a_pre
        t_sup = torch.clamp(t_set + p64["K_sup"] * err,
                             p64["T_sup_cool_min"], p64["T_sup_heat_max"])
        q_sup = torch.clamp((t_sup - a_pre) / p64["R_air"],
                            -p64["Q_cool_max"], p64["Q_heat_max"])
        implied = a_pre + (dt / p64["C_air"]) * (
            -q_aw + q_win + q_inf + q_int + q_sup)
        resid[:, k] = (t_next.to(torch.float64) - implied).to(dtype)

        # mass node: propagate with the *pre-step* air state
        wall = wall + (dt / p64["C_wall"]) * q_aw

        new_row = feats[:, k].clone()
        new_row[:, 3] = t_next
        hist = torch.cat([hist[:, 1:], new_row.unsqueeze(1)], dim=1)

    return pred, resid


def rollout_pinn(model: PINNZone, std_trunk: Standardizer,
                 std_branch: Standardizer, feats_np: np.ndarray,
                 wall0_np: np.ndarray, params_list: Sequence[Dict[str, float]],
                 window: int, branch_offset: int = 0) -> np.ndarray:
    """Free-running rollout of the PINN over a batch of series (numpy I/O).

    `feats_np` has shape (B, n, N_FEATURES); the returned array has shape
    (B, n) and holds the predicted zone temperature [degC] (the first
    `window` entries are the warm-start truth).
    """
    model.eval()
    feats = torch.as_tensor(np.asarray(feats_np), dtype=torch.float32)
    wall0 = torch.as_tensor(np.asarray(wall0_np), dtype=torch.float64)
    p = rc_param_tensors(params_list)
    with torch.no_grad():
        pred, _ = pinn_rollout_torch(model, std_trunk, std_branch, feats,
                                      wall0, p, window,
                                      branch_offset=branch_offset)
    return pred.numpy()

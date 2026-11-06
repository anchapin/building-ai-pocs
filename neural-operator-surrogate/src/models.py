"""Surrogate models and feature construction for the neural-operator POC.

Slice 1 ships only the plain-MLP baseline (arm (a) of issue #3): a small
fully-connected network that maps a fixed window of past inputs to the
next-step zone temperature.  The same feature builder and the same target
will be re-used by the physics-informed / neural-operator arm in slice 2, so
both arms see identical data.
"""

from __future__ import annotations

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

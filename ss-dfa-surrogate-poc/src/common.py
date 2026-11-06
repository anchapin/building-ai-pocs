"""Shared data handling, normalisation, metrics, and seeding.

Split rule (enforced here): every scaler is fitted on the TRAIN year only.
There is no shuffling across split boundaries and no overlapping windows
between years - each year is windowed independently.
"""

import json
import math
import resource
from pathlib import Path

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

FEATURES = ["t_out", "ghi", "q_int", "q_heat", "q_cool"]  # exogenous inputs
TARGETS = ["t_zone", "e_heat", "e_cool"]
N_HISTORY = 24          # hours of history given to every model
IDX_T = 5               # position of the autoregressive zone temperature in x_t


def set_seed(seed: int):
    np.random.seed(seed)
    torch.manual_seed(seed)


def load_year(year: int, envelope: str = "base") -> dict:
    d = np.load(DATA / f"year{year}_{envelope}.npz")
    return {k: d[k] for k in d.files}


class Scaler:
    """Standardisation. fit() is only ever called on training-year data."""

    def __init__(self):
        self.mean = None
        self.std = None

    def fit(self, x: np.ndarray):
        self.mean = x.mean(axis=0)
        self.std = x.std(axis=0) + 1e-8
        return self

    def transform(self, x: np.ndarray) -> np.ndarray:
        return (x - self.mean) / self.std

    def inverse(self, x: np.ndarray) -> np.ndarray:
        return x * self.std + self.mean


def build_arrays(year: int, envelope: str, sx: Scaler, ss: Scaler, sy: Scaler,
                 fit: bool = False) -> dict:
    """Load one year and return scaled exogenous inputs, state, and targets.

    Y[t] = (t_zone[t+1], e_heat[t], e_cool[t]).  The final hour has no target.
    """
    d = load_year(year, envelope)
    X = np.stack([d[f] for f in FEATURES], axis=1).astype(np.float64)
    S = d["t_zone"].astype(np.float64)
    Y = np.stack([np.concatenate([S[1:], S[-1:]]), d["e_heat"], d["e_cool"]], axis=1)
    Y = Y[:-1].astype(np.float64)          # aligned with X/S rows 0..n-2
    X, S = X[:-1], S[:-1]

    if fit:
        sx.fit(X); ss.fit(S.reshape(-1, 1)); sy.fit(Y)
    Xs = sx.transform(X)
    Ss = ss.transform(S.reshape(-1, 1))[:, 0]
    Ys = sy.transform(Y)
    return dict(X=Xs, S=Ss, Y=Ys, X_raw=X, S_raw=S, Y_raw=Y, n=len(S))


def windows(arr: dict, L: int = N_HISTORY):
    """Return (Xw [N,L,6], Yw [N,3], Yall [N,L,3]) for one year.

    Xw[i] covers input steps i-L+1 .. i;  Yw[i] is the target for the
    prediction made at step i (i.e. T_zone[i+1] and energies at step i).
    Yall gives the same target at every step inside the window - used only by
    the SS-DFA readout, which is applied at every step. Windows never cross a
    year boundary.
    """
    X, S, Y, n = arr["X"], arr["S"], arr["Y"], arr["n"]
    Feat = np.concatenate([X, S.reshape(-1, 1)], axis=1)   # (n, 6)
    idx = np.arange(L - 1, n)
    Xw = np.stack([Feat[i - L + 1: i + 1] for i in idx])   # (N, L, 6)
    Yw = Y[idx].astype(np.float32)                          # (N, 3)
    Yall = np.stack([Y[i - L + 1: i + 1] for i in idx]).astype(np.float32)
    return Xw.astype(np.float32), Yw, Yall


# ------------------------------------------------------------------ metrics --
def metrics(y_true, y_pred):
    """MAE, RMSE, ASHRAE Guideline 14 NMBE and CV(RMSE)."""
    y = np.asarray(y_true, float).ravel()
    p = np.asarray(y_pred, float).ravel()
    err = p - y
    mae = np.mean(np.abs(err))
    rmse = math.sqrt(np.mean(err ** 2))
    nmbe = 100.0 * np.sum(y - p) / (len(y) * np.mean(y)) if np.mean(y) != 0 else float("nan")
    cvrmse = 100.0 * rmse / np.mean(y) if np.mean(y) != 0 else float("nan")
    return dict(mae=float(mae), rmse=float(rmse), nmbe=float(nmbe), cvrmse=float(cvrmse))


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def hottest_coldest_weeks(t_out: np.ndarray):
    """Return (hottest_week_start_hour, coldest_week_start_hour) by 168 h mean."""
    w = t_out[: len(t_out) // 168 * 168].reshape(-1, 168).mean(axis=1)
    return int(np.argmax(w) * 168), int(np.argmin(w) * 168)


def save_json(obj, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=float))

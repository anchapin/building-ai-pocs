"""Client-side (local) model for the federated-calibration POC (slice 1).

This is the model a *single building* can calibrate with its own data only:

    C dT/dt = UA * (T_out - T) + s * P_sched(t) + g_sol * S(t) + Q_hvac(T, T_set)

with the four calibration unknowns

    C     : zone capacitance            [J/K]
    UA    : envelope + infiltration UA  [W/K]
    s     : internal-gain scale         [-]
    g_sol : solar-gain scale            [W]

The thermostat law (`K_PROP`, power limits), the occupancy profile shape
and the clear-sky shape are treated as *known* by every client -- they are
documented conventions, not private data, so they do not violate the
no-raw-data boundary.  What no client can know is the day's cloud
modulation of the solar gain: the truth's solar term is
`g_sol * clear_sky(t) * cloud(t)` while the client model only has
`g_sol * clear_sky(t)`.  That mismatch is the deliberate model
misspecification of the POC.

Why a grey-box RC fit rather than a neural network?  The issue asks for
"local PINN/RC models".  A 4-parameter RC model is (i) identifiable from a
few days of hourly data, (ii) physically interpretable, so a FedAvg
average of the parameters is a meaningful object, and (iii) cheap enough
(CPU, seconds) that the whole comparison can be run over several seeds.
The physics is *in* the forward model, so the training loss below is a
heat-balance (physics) residual: the local fit is physics-informed by
construction, not by a penalty term bolted onto a black box.

Training loss (simulation-error / one-step-ahead form, the standard
grey-box identification objective):

    T_pred[k+1] = T[k] + dt/C * (UA*(T_out[k]-T[k]) + s*P[k] + Q_hvac(T[k], T_set[k]))
    L(theta)     = mean_k (T_pred[k+1] - T_meas[k+1])^2

The parameters are optimised in log space (positivity) with Adam.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import torch

# The thermostat law and the occupancy profile shape are public conventions.
DT = 3600.0
K_PROP = 40.0
Q_HEAT_MAX = 3000.0
Q_COOL_MAX = 2500.0
P_OCCUPIED = 120.0
P_UNOCCUPIED = 25.0
OCCUPY_START = 7
OCCUPY_END = 19

PARAM_NAMES: Tuple[str, ...] = ("C", "UA", "s", "g_sol")

# Nominal starting point shared by every client and every federated round.
NOMINAL_PARAMS: Dict[str, float] = {"C": 3.0e6, "UA": 18.0, "s": 1.0,
                                    "g_sol": 400.0}


def occupancy_profile(n: int) -> np.ndarray:
    """Known occupancy/equipment profile shape [W]."""
    hod = np.arange(n) % 24
    occupied = (hod >= OCCUPY_START) & (hod < OCCUPY_END)
    return np.where(occupied, P_OCCUPIED, P_UNOCCUPIED)


def clear_sky(n: int) -> np.ndarray:
    """Public clear-sky shape [-]."""
    hod = np.arange(n) % 24
    return np.maximum(0.0, np.sin(np.pi * (hod - 6.0) / 12.0))


def _torch(x) -> torch.Tensor:
    return torch.as_tensor(np.asarray(x, dtype=np.float64))


def params_to_vector(params: Mapping[str, float]) -> torch.Tensor:
    """Physical parameters -> log-space vector (the optimised object)."""
    return torch.stack([torch.log(torch.tensor(float(params[k]), dtype=torch.float64))
                         for k in PARAM_NAMES])


def vector_to_params(z: torch.Tensor) -> Dict[str, float]:
    """Log-space vector -> physical parameters."""
    out: Dict[str, float] = {}
    with torch.no_grad():
        for i, k in enumerate(PARAM_NAMES):
            out[k] = float(torch.exp(z[i]))
    return out


def thermostat_power(t: torch.Tensor, t_set: torch.Tensor) -> torch.Tensor:
    """Proportional thermostat power [W] (positive = heating)."""
    return torch.clamp(K_PROP * (t_set - t), -Q_COOL_MAX, Q_HEAT_MAX)


def one_step_prediction(z: torch.Tensor, t_zone: torch.Tensor, t_out: torch.Tensor,
                        t_set: torch.Tensor, p_sched: torch.Tensor,
                        clear: torch.Tensor) -> torch.Tensor:
    """One-step-ahead zone temperature [degC] from the current measured state."""
    c = torch.exp(z[0])
    ua = torch.exp(z[1])
    s = torch.exp(z[2])
    g_sol = torch.exp(z[3])
    q_hv = thermostat_power(t_zone, t_set)
    t_next = t_zone + DT / c * (ua * (t_out - t_zone) + s * p_sched
                                + g_sol * clear + q_hv)
    return t_next


def heat_balance_loss(z: torch.Tensor, series: Mapping[str, torch.Tensor]
                      ) -> torch.Tensor:
    """Mean squared one-step heat-balance residual [degC^2]."""
    t_zone = series["t_zone"]
    pred = one_step_prediction(z, t_zone[:-1], series["t_out"][:-1],
                                series["t_set"][:-1], series["p_sched"][:-1],
                                series["clear_sky"][:-1])
    return torch.mean((pred - t_zone[1:]) ** 2)


@dataclass
class LocalFit:
    """Result of a local (single-building) calibration."""

    params: Dict[str, float]
    loss: float
    steps: int
    history: List[float]


def as_torch_series(series: Mapping[str, np.ndarray]) -> Dict[str, torch.Tensor]:
    return {k: _torch(v) for k, v in series.items()}


def fit_local(series: Mapping[str, np.ndarray],
              init_params: Optional[Mapping[str, float]] = None,
              steps: int = 400, lr: float = 0.05,
              start: int = 0, end: Optional[int] = None) -> LocalFit:
    """Calibrate the four physical parameters on ONE building's own data.

    Only the slice [start, end) of the local series is used, so the same
    routine implements the isolated-local arm with a restricted data
    budget.
    """
    ts = as_torch_series(series)
    n = len(ts["t_zone"])
    end = n if end is None else int(end)
    sl = {k: v[start:end] for k, v in ts.items()}
    z = params_to_vector(init_params or NOMINAL_PARAMS).clone().requires_grad_(True)
    opt = torch.optim.Adam([z], lr=lr)
    history: List[float] = []
    for _ in range(int(steps)):
        opt.zero_grad()
        loss = heat_balance_loss(z, sl)
        loss.backward()
        opt.step()
        history.append(float(loss.detach()))
    with torch.no_grad():
        final = float(heat_balance_loss(z, sl))
    return LocalFit(params=vector_to_params(z), loss=final, steps=int(steps),
                    history=history)


def rollout(params: Mapping[str, float], series: Mapping[str, np.ndarray],
            start: int = 0, end: Optional[int] = None,
            t_init: Optional[float] = None) -> np.ndarray:
    """Free-running rollout of the calibrated model [degC].

    The rollout is *open loop* in the temperature: it integrates the model
    with the measured weather/setpoint inputs and never re-anchors on the
    measured zone temperature (except for the initial condition).
    """
    t_out = np.asarray(series["t_out"], dtype=np.float64)
    t_set = np.asarray(series["t_set"], dtype=np.float64)
    p_sched = np.asarray(series["p_sched"], dtype=np.float64)
    clear = np.asarray(series["clear_sky"], dtype=np.float64)
    t_meas = np.asarray(series["t_zone"], dtype=np.float64)
    n = len(t_out)
    end = n if end is None else int(end)
    c = float(params["C"])
    ua = float(params["UA"])
    s = float(params["s"])
    g_sol = float(params["g_sol"])
    cur = float(t_meas[start] if t_init is None else t_init)
    out = np.empty(end - start, dtype=np.float64)
    for k in range(start, end):
        err = t_set[k] - cur
        q_hv = float(np.clip(K_PROP * err, -Q_COOL_MAX, Q_HEAT_MAX))
        out[k - start] = cur
        cur = cur + DT / c * (ua * (t_out[k] - cur) + s * p_sched[k]
                              + g_sol * clear[k] + q_hv)
    return out


def rmse(pred: np.ndarray, truth: np.ndarray) -> float:
    pred = np.asarray(pred, dtype=np.float64)
    truth = np.asarray(truth, dtype=np.float64)
    if pred.size == 0:
        return float("nan")
    return float(np.sqrt(np.mean((pred - truth) ** 2)))


def one_step_rmse(params: Mapping[str, float],
                  series: Mapping[str, np.ndarray],
                  start: int = 0, end: Optional[int] = None) -> float:
    """Teacher-forced one-step RMSE [degC] of the calibrated parameters."""
    ts = as_torch_series(series)
    n = len(ts["t_zone"])
    end = n if end is None else int(end)
    with torch.no_grad():
        z = params_to_vector(params)
        pred = one_step_prediction(z, ts["t_zone"][start:end - 1],
                                   ts["t_out"][start:end - 1],
                                   ts["t_set"][start:end - 1],
                                   ts["p_sched"][start:end - 1],
                                   ts["clear_sky"][start:end - 1])
        truth = ts["t_zone"][start + 1:end]
        return float(torch.sqrt(torch.mean((pred - truth) ** 2)))


def rmse_on_window(params: Mapping[str, float], series: Mapping[str, np.ndarray],
                   start: int, end: int) -> float:
    """Free-running rollout RMSE [degC] over the window [start, end)."""
    pred = rollout(params, series, start=start, end=end)
    truth = np.asarray(series["t_zone"], dtype=np.float64)[start:end]
    return rmse(pred, truth)


def fit_pooled(series_list: Sequence[Mapping[str, np.ndarray]],
               init_params: Optional[Mapping[str, float]] = None,
               steps: int = 400, lr: float = 0.05) -> LocalFit:
    """Centralised reference: one parameter set fitted on POOLED data.

    This is the "upper bound" reference of the issue: it may see every
    building's raw time-series at once, which the federated server may not.
    """
    ts = [as_torch_series(s) for s in series_list]
    z = params_to_vector(init_params or NOMINAL_PARAMS).clone().requires_grad_(True)
    opt = torch.optim.Adam([z], lr=lr)
    history: List[float] = []
    for _ in range(int(steps)):
        opt.zero_grad()
        losses = [heat_balance_loss(z, s) for s in ts]
        loss = torch.stack(losses).mean()
        loss.backward()
        opt.step()
        history.append(float(loss.detach()))
    with torch.no_grad():
        final = float(torch.stack([heat_balance_loss(z, s) for s in ts]).mean())
    return LocalFit(params=vector_to_params(z), loss=final, steps=int(steps),
                    history=history)


def params_equal(a: Mapping[str, float], b: Mapping[str, float],
                 tol: float = 1e-12) -> bool:
    return all(abs(float(a[k]) - float(b[k])) <= tol for k in PARAM_NAMES)


def mean_params(params_list: Iterable[Mapping[str, float]]
                ) -> Dict[str, float]:
    """Element-wise mean of a list of parameter dicts (the FedAvg step)."""
    items = list(params_list)
    if not items:
        raise ValueError("no parameter updates to average")
    return {k: float(np.mean([float(p[k]) for p in items])) for k in PARAM_NAMES}

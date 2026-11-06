"""Differentiable 2R2C zone thermal model (PyTorch) + pure-numpy reference.

This is the physics core of the "neural-operator surrogate" POC (slice 1).
It is deliberately small, explicit and named-parameter based so that a later
slice can put a physics residual straight into a training loss.

Model topology (2R2C)
----------------------
Two thermal nodes, two capacitances, two resistances plus explicit
window / infiltration paths:

    outdoor  --(U_win*A_win)--+
    outdoor  --(UA_inf)--------+--> [zone air node, C_air] --(R_wall)-- [mass node, C_wall]
    HVAC supply air (via R_air) --+

State equations (explicit Euler, dt = 3600 s):

    Q_aw   = (T_air - T_wall) / R_wall          # air <-> mass
    Q_win  = U_win * A_win * (T_out - T_air)    # window (negative = heat loss)
    Q_inf  = UA_inf * (T_out - T_air)           # infiltration
    Q_sup  = (T_sup - T_air) / R_air            # HVAC supply-air heat into zone

    C_air * dT_air/dt = -Q_aw + Q_win + Q_inf + Q_int + Q_sup
    C_wall * dT_wall/dt = Q_aw

The HVAC controller is a simple proportional supply-air controller, written
with `torch.clamp` so it stays differentiable a.e.:

    err    = T_set - T_air
    T_sup  = clamp(T_set + K_sup * err, T_sup_cool_min, T_sup_heat_max)
    Q_sup  = clamp((T_sup - T_air) / R_air, -Q_cool_max, Q_heat_max)

Everything in `rollout_torch` is plain tensor algebra, so autograd flows
through a full multi-step rollout (proven in tests/).

`rollout_numpy` is an independent, non-differentiable reference
implementation used to cross-check the torch rollout (agreement <= 1e-6).
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import torch

# Explicit-Euler time step [s] (hourly data).
DT = 3600.0


@dataclass(frozen=True)
class RCParams:
    """Named RC parameters of the zone.

    Units: C_* [J/K], R_* [K/W], U_win [W/m2K], A_win [m2], UA_inf [W/K],
    K_sup [-] (supply-air proportional gain), Q_*_max [W], T_init [degC].
    """

    C_air: float = 2.0e6          # zone air + light mass capacitance
    R_wall: float = 0.03           # zone-air <-> mass resistance
    C_wall: float = 2.0e7          # mass (wall) capacitance
    R_air: float = 0.05            # supply-air path resistance
    U_win: float = 1.8             # window U-value
    A_win: float = 6.0             # window area
    UA_inf: float = 8.0            # infiltration conductance
    K_sup: float = 3.0             # supply-air proportional controller gain
    T_sup_heat_max: float = 45.0   # max supply air temperature
    T_sup_cool_min: float = 13.0   # min supply air temperature
    Q_heat_max: float = 6000.0     # heating capacity limit
    Q_cool_max: float = 6000.0     # cooling capacity limit
    T_init: float = 20.0           # initial zone temperature

    def to_dict(self) -> Dict[str, float]:
        return asdict(self)

    def to_torch(self, requires_grad: bool = True) -> Dict[str, torch.Tensor]:
        """Tensor view of the parameters (leaf tensors, autograd-capable)."""
        out: Dict[str, torch.Tensor] = {}
        for k, v in self.to_dict().items():
            t = torch.tensor(float(v), dtype=torch.float64)
            if requires_grad:
                t.requires_grad_(True)
            out[k] = t
        return out

    @staticmethod
    def from_dict(d: Dict[str, float]) -> "RCParams":
        fields = {f for f in RCParams.__dataclass_fields__}
        return RCParams(**{k: float(v) for k, v in d.items() if k in fields})


# --------------------------------------------------------------------------
# controller
# --------------------------------------------------------------------------

def controller_torch(p: Dict[str, torch.Tensor], t_air: torch.Tensor,
                     t_set: torch.Tensor) -> torch.Tensor:
    """Proportional supply-air controller -> HVAC heat into the zone [W].

    Positive = heating, negative = cooling. Differentiable a.e.
    """
    err = t_set - t_air
    t_sup = t_set + p["K_sup"] * err
    t_sup = torch.clamp(t_sup, p["T_sup_cool_min"], p["T_sup_heat_max"])
    q = (t_sup - t_air) / p["R_air"]
    return torch.clamp(q, -p["Q_cool_max"], p["Q_heat_max"])


def controller_numpy(p: RCParams, t_air: float, t_set: float) -> float:
    """Numpy twin of `controller_torch` (reference implementation)."""
    err = t_set - t_air
    t_sup = t_set + p.K_sup * err
    t_sup = float(np.clip(t_sup, p.T_sup_cool_min, p.T_sup_heat_max))
    q = (t_sup - t_air) / p.R_air
    return float(np.clip(q, -p.Q_cool_max, p.Q_heat_max))


# --------------------------------------------------------------------------
# one step
# --------------------------------------------------------------------------

def step_torch(p: Dict[str, torch.Tensor], t_air: torch.Tensor, t_wall: torch.Tensor,
               t_out: torch.Tensor, t_set: torch.Tensor, q_int: torch.Tensor,
               dt: float = DT):
    """One explicit-Euler step. Returns (t_air_next, t_wall_next, q_sup)."""
    q_aw = (t_air - t_wall) / p["R_wall"]
    q_win = p["U_win"] * p["A_win"] * (t_out - t_air)
    q_inf = p["UA_inf"] * (t_out - t_air)
    q_sup = controller_torch(p, t_air, t_set)

    t_air_next = t_air + dt / p["C_air"] * (-q_aw + q_win + q_inf + q_int + q_sup)
    t_wall_next = t_wall + dt / p["C_wall"] * q_aw
    return t_air_next, t_wall_next, q_sup


def step_numpy(p: RCParams, t_air: float, t_wall: float, t_out: float,
               t_set: float, q_int: float, dt: float = DT):
    """Numpy twin of `step_torch`."""
    q_aw = (t_air - t_wall) / p.R_wall
    q_win = p.U_win * p.A_win * (t_out - t_air)
    q_inf = p.UA_inf * (t_out - t_air)
    q_sup = controller_numpy(p, t_air, t_set)

    t_air_next = t_air + dt / p.C_air * (-q_aw + q_win + q_inf + q_int + q_sup)
    t_wall_next = t_wall + dt / p.C_wall * q_aw
    return t_air_next, t_wall_next, q_sup


# --------------------------------------------------------------------------
# rollouts
# --------------------------------------------------------------------------

def rollout_torch(p: Dict[str, torch.Tensor], t_out: Sequence[torch.Tensor],
                  t_set: Sequence[torch.Tensor], q_int: Sequence[torch.Tensor],
                  t_air0: Optional[torch.Tensor] = None,
                  t_wall0: Optional[torch.Tensor] = None,
                  dt: float = DT) -> Dict[str, torch.Tensor]:
    """Full differentiable rollout.

    Returns dict with 't_air', 't_wall', 'q_sup' (1-D tensors, length N).
    """
    n = len(t_out)
    if len(t_set) != n or len(q_int) != n:
        raise ValueError("t_out, t_set, q_int must have the same length")

    if t_air0 is None:
        t_air0 = p["T_init"]
    if t_wall0 is None:
        t_wall0 = p["T_init"]

    t_air = t_air0
    t_wall = t_wall0
    air_list, wall_list, q_list = [], [], []
    for k in range(n):
        t_air, t_wall, q_sup = step_torch(
            p, t_air, t_wall, t_out[k], t_set[k], q_int[k], dt=dt)
        air_list.append(t_air)
        wall_list.append(t_wall)
        q_list.append(q_sup)

    return {
        "t_air": torch.stack(air_list),
        "t_wall": torch.stack(wall_list),
        "q_sup": torch.stack(q_list),
        "t_air0": t_air0,
        "t_wall0": t_wall0,
    }


def rollout_numpy(p: RCParams, t_out: np.ndarray, t_set: np.ndarray,
                  q_int: np.ndarray, t_air0: Optional[float] = None,
                  t_wall0: Optional[float] = None, dt: float = DT) -> Dict[str, np.ndarray]:
    """Pure-numpy reference rollout (no torch), same equations."""
    t_out = np.asarray(t_out, dtype=np.float64)
    t_set = np.asarray(t_set, dtype=np.float64)
    q_int = np.asarray(q_int, dtype=np.float64)
    n = len(t_out)
    if len(t_set) != n or len(q_int) != n:
        raise ValueError("t_out, t_set, q_int must have the same length")

    t_air = p.T_init if t_air0 is None else float(t_air0)
    t_wall = p.T_init if t_wall0 is None else float(t_wall0)
    air0, wall0 = t_air, t_wall

    air = np.empty(n, dtype=np.float64)
    wall = np.empty(n, dtype=np.float64)
    qsup = np.empty(n, dtype=np.float64)
    for k in range(n):
        t_air, t_wall, q = step_numpy(p, t_air, t_wall, t_out[k], t_set[k], q_int[k], dt=dt)
        air[k] = t_air
        wall[k] = t_wall
        qsup[k] = q
    return {"t_air": air, "t_wall": wall, "q_sup": qsup,
            "t_air0": float(air0), "t_wall0": float(wall0)}


# --------------------------------------------------------------------------
# energy balance bookkeeping
# --------------------------------------------------------------------------

def heat_flows(p: RCParams, t_air: float, t_wall: float, t_out: float,
               q_sup: float, q_int: float) -> Dict[str, float]:
    """Individual heat flows [W] for a given state (used for residuals)."""
    return {
        "q_aw": (t_air - t_wall) / p.R_wall,
        "q_win": p.U_win * p.A_win * (t_out - t_air),
        "q_inf": p.UA_inf * (t_out - t_air),
        "q_sup": q_sup,
        "q_int": q_int,
    }


def balance_residual_pct(p: RCParams, t_air_states: Sequence[float],
                         t_wall_states: Sequence[float], q_sup: Sequence[float],
                         q_int: Sequence[float], t_out: Sequence[float],
                         dt: float = DT) -> float:
    """Relative heat-balance residual over a window [%].

    State convention (identical for the RC reference and for a surrogate
    rollout): `t_air_states` / `t_wall_states` hold n+1 states, i.e. the
    initial state followed by the n post-step states; `q_sup`, `q_int` and
    `t_out` hold n values, one per step (the heat flows of step k are
    evaluated on the *pre-step* state, i.e. on `states[:-1]`).

        E_in   = sum_k dt * (q_sup + q_int)              # injected into the zone
        E_out  = sum_k dt * (q_win + q_inf)               # exchange with outdoors
        dU     = C_air*(T_air[-1]-T_air[0]) + C_wall*(T_wall[-1]-T_wall[0])
        scale  = sum_k dt * (|q_sup| + |q_win| + |q_inf| + q_int) + |dU|
        residual % = 100 * |E_in + E_out - dU| / scale

    For the exact RC rollout this is ~0 (float round-off only); for a
    surrogate rollout it measures how far the surrogate trajectory violates
    the physics of the zone.
    """
    t_air_states = np.asarray(t_air_states, dtype=np.float64)
    t_wall_states = np.asarray(t_wall_states, dtype=np.float64)
    q_sup = np.asarray(q_sup, dtype=np.float64)
    q_int = np.asarray(q_int, dtype=np.float64)
    t_out = np.asarray(t_out, dtype=np.float64)
    if not (len(t_wall_states) == len(t_air_states)):
        raise ValueError("state sequences must have the same length")
    n = len(q_sup)
    if not (len(q_int) == len(t_out) == n) or len(t_air_states) != n + 1:
        raise ValueError("flows must have length n, states length n+1")

    pre_air = t_air_states[:-1]
    q_win = p.U_win * p.A_win * (t_out - pre_air)
    q_inf = p.UA_inf * (t_out - pre_air)

    e_in = dt * float(np.sum(q_sup + q_int))
    e_out = dt * float(np.sum(q_win + q_inf))
    du = (p.C_air * (t_air_states[-1] - t_air_states[0])
          + p.C_wall * (t_wall_states[-1] - t_wall_states[0]))
    scale = dt * float(np.sum(np.abs(q_sup) + np.abs(q_win) + np.abs(q_inf) + q_int)) + abs(du)
    if scale <= 0.0:
        return 0.0
    return 100.0 * abs(e_in + e_out - du) / scale


def residual_from_rollout(p: RCParams, roll: Dict[str, np.ndarray],
                           q_int: Sequence[float], t_out: Sequence[float],
                           dt: float = DT) -> float:
    """Heat-balance residual [%] of an RC (numpy) rollout."""
    t_air_states = np.concatenate(([roll["t_air0"]], roll["t_air"]))
    t_wall_states = np.concatenate(([roll["t_wall0"]], roll["t_wall"]))
    return balance_residual_pct(p, t_air_states, t_wall_states, roll["q_sup"],
                                q_int, t_out, dt=dt)


def wall_trajectory(p: RCParams, t_air: np.ndarray, t_wall0: float,
                    dt: float = DT) -> np.ndarray:
    """Propagate the mass node with the RC wall dynamics driven by `t_air`."""
    t_air = np.asarray(t_air, dtype=np.float64)
    wall = np.empty(len(t_air), dtype=np.float64)
    tw = float(t_wall0)
    for k in range(len(t_air)):
        q_aw = (t_air[k] - tw) / p.R_wall
        tw = tw + dt / p.C_wall * q_aw
        wall[k] = tw
    return wall


__all__ = [
    "DT", "RCParams", "controller_torch", "controller_numpy", "step_torch",
    "step_numpy", "rollout_torch", "rollout_numpy", "heat_flows",
    "balance_residual_pct", "residual_from_rollout", "wall_trajectory",
]

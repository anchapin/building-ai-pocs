"""Tests of the differentiable RC zone model (slice 1).

Covers:
  * torch rollout vs the pure-numpy reference (<= 1e-6),
  * autograd gradient flow through a full rollout (parameter grads populated),
  * energy conservation of the RC model itself over a closed cycle (< 1%),
  * torch/numpy controller agreement.
"""

from __future__ import annotations

import numpy as np
import torch

from rc_model import (DT, RCParams, balance_residual_pct, controller_numpy,
                      controller_torch, residual_from_rollout, rollout_numpy,
                      rollout_torch)


def _inputs(n: int = 240, seed: int = 0):
    rng = np.random.default_rng(seed)
    t_out = 12.0 + 6.0 * np.sin(2 * np.pi * np.arange(n) / 24.0) + rng.normal(0, 0.5, n)
    t_set = np.where(np.arange(n) % 24 < 16, 21.0, 17.0)
    q_int = rng.uniform(30.0, 250.0, n)
    return t_out, t_set, q_int


def test_torch_vs_numpy_rollout_agreement():
    p = RCParams()
    t_out, t_set, q_int = _inputs()
    pt = p.to_torch()
    r = rollout_torch(pt,
                      torch.as_tensor(t_out, dtype=torch.float64),
                      torch.as_tensor(t_set, dtype=torch.float64),
                      torch.as_tensor(q_int, dtype=torch.float64))
    rn = rollout_numpy(p, t_out, t_set, q_int)
    for key in ("t_air", "t_wall", "q_sup"):
        d = float(np.max(np.abs(r[key].detach().numpy() - rn[key])))
        assert d <= 1e-6, f"{key}: torch-vs-numpy mismatch {d:.3e} > 1e-6"


def test_controller_agreement():
    p = RCParams()
    pt = p.to_torch()
    for t_air, t_set in [(15.0, 21.0), (25.0, 21.0), (21.0, 16.0), (12.0, 21.0)]:
        q_t = float(controller_torch(pt,
                                    torch.tensor(t_air, dtype=torch.float64),
                                    torch.tensor(t_set, dtype=torch.float64)).detach())
        q_n = controller_numpy(p, t_air, t_set)
        assert abs(q_t - q_n) <= 1e-9


def test_autograd_gradient_flows_through_rollout():
    """A loss on the rollout must produce parameter gradients."""
    p = RCParams()
    pt = p.to_torch()
    t_out, t_set, q_int = _inputs(n=120)
    r = rollout_torch(pt,
                      torch.as_tensor(t_out, dtype=torch.float64),
                      torch.as_tensor(t_set, dtype=torch.float64),
                      torch.as_tensor(q_int, dtype=torch.float64))
    target = torch.linspace(18.0, 24.0, r["t_air"].shape[0], dtype=torch.float64)
    loss = torch.mean((r["t_air"] - target) ** 2) + 0.1 * torch.mean(r["q_sup"] ** 2)
    loss.backward()

    assert loss.item() > 0.0
    grads = {k: (v.grad is not None) for k, v in pt.items()}
    for name in ("C_air", "R_wall", "C_wall", "R_air", "U_win", "UA_inf"):
        assert grads[name], f"no gradient for {name}"
        assert torch.isfinite(pt[name].grad).all()
        assert float(pt[name].grad.abs().sum()) > 0.0, f"zero gradient for {name}"


def test_energy_conservation_closed_cycle():
    """RC model energy balance over a closed (periodic) cycle < 1%."""
    p = RCParams()
    n = 24 * 60  # 60 days: settle onto the periodic orbit
    h = np.arange(n)
    t_out = 10.0 + 5.0 * np.sin(2 * np.pi * (h - 9) / 24.0)
    t_set = 20.0 + 2.0 * np.sin(2 * np.pi * h / 24.0)
    q_int = np.full(n, 150.0)
    roll = rollout_numpy(p, t_out, t_set, q_int)

    # closed cycle = last 24 h of the (settled) trajectory
    a = n - 24
    air_states = np.concatenate(([roll["t_air0"]], roll["t_air"]))[a: a + 25]
    wall_states = np.concatenate(([roll["t_wall0"]], roll["t_wall"]))[a: a + 25]
    resid = balance_residual_pct(p, air_states, wall_states,
                                 roll["q_sup"][a: a + 24], q_int[a: a + 24], t_out[a: a + 24])
    assert resid < 1.0, f"heat-balance residual {resid:.4f}% >= 1%"
    # the exact model must be far better than the 1% acceptance bound
    assert resid < 1e-6, f"RC model residual {resid:.3e}% is not machine precision"


def test_residual_of_rollout_is_zero():
    p = RCParams()
    t_out, t_set, q_int = _inputs(n=100)
    roll = rollout_numpy(p, t_out, t_set, q_int)
    resid = residual_from_rollout(p, roll, q_int, t_out)
    assert resid < 1e-6

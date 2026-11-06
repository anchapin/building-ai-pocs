"""Tests of the shared-encoder differentiable RC arm (slice 3).

Covers:
  * the zero-init property: an UNTRAINED SharedEncoderRC reproduces the
    RC reference trajectory exactly when given the TRUE per-series
    parameters (its heads are initialised at zero, so the corrections
    vanish and the rollout IS the 2R2C model). This pins the honest
    reading of the slice-3 headline table: the arm-(c) ~0 error with
    true base parameters is structural, not learned, and must never be
    presented as a surrogate win. The genuine test is the NOMINAL base.
  * the same untrained model with NOMINAL (train-median) parameters does
    NOT reproduce the truth -- the nominal variant is a real test.
  * the shared rollout is deterministic, finite, and warm-starts on truth,
  * a saved shared checkpoint round-trips its rc_params_mode (evaluate.py
    reads it to choose true vs nominal rollout parameters),
  * median_params returns the per-parameter median used by the
    parameter-mismatch experiment.
"""

from __future__ import annotations

import os

import numpy as np
import torch

from models import (Standardizer, make_shared, median_params,
                    rollout_shared, series_features)
from rc_model import RCParams, rollout_numpy


def _inputs(n: int = 240, seed: int = 0):
    rng = np.random.default_rng(seed)
    t_out = 12.0 + 6.0 * np.sin(2 * np.pi * np.arange(n) / 24.0) + rng.normal(0, 0.5, n)
    t_set = np.where(np.arange(n) % 24 < 16, 21.0, 17.0)
    q_int = rng.uniform(30.0, 250.0, n)
    return t_out, t_set, q_int


def _truth(n: int = 240, seed: int = 0):
    p = RCParams()
    t_out, t_set, q_int = _inputs(n=n, seed=seed)
    roll = rollout_numpy(p, t_out, t_set, q_int)
    return p, roll, (t_out, t_set, q_int)


def _std(window: int = 12):
    return Standardizer(np.zeros(window * 6), np.ones(window * 6), 20.0, 1.0)


def test_shared_untrained_is_rc_reference_with_true_params():
    """Untrained shared encoder + true params == the RC reference.

    The heads are zero-initialised, so the parameter corrections vanish
    and the neural heat flow is zero: the rollout integrates the exact
    2R2C equations. If this ever fails, the zero-init contract broke.
    """
    p, roll, (t_out, t_set, q_int) = _truth()
    window = 12
    feats = series_features(roll["t_air"], t_out, t_set, q_int)
    wall0 = np.array([roll["t_wall"][window - 1]], dtype=np.float64)
    model = make_shared(window * 6, (128, 128), 32, seed=42)
    pred = rollout_shared(model, _std(window), feats[None, ...], wall0,
                          [p.to_dict()], window)
    np.testing.assert_allclose(pred[0, window:], roll["t_air"][window:],
                               atol=1e-4)


def test_shared_untrained_nominal_params_differ_from_truth():
    """Untrained shared encoder + NOMINAL params does not reproduce truth.

    The nominal (train-median) parameters are wrong for this series, so
    the rollout must deviate measurably -- otherwise the nominal variant
    would be as vacuous as the true-parameter one.
    """
    p, roll, (t_out, t_set, q_int) = _truth()
    window = 12
    feats = series_features(roll["t_air"], t_out, t_set, q_int)
    wall0 = np.array([roll["t_wall"][window - 1]], dtype=np.float64)
    # median of {1.8, 2.7, 3.6} is 2.7, i.e. genuinely different from the
    # true U_win = 1.8 (the earlier draft used 0.9/1.5x, whose median IS 1.8).
    nominal = median_params([p.to_dict(),
                             dict(p.to_dict(), U_win=p.U_win * 1.5),
                             dict(p.to_dict(), U_win=p.U_win * 2.0)])
    model = make_shared(window * 6, (128, 128), 32, seed=42)
    pred = rollout_shared(model, _std(window), feats[None, ...], wall0,
                          [nominal], window)
    rmse = float(np.sqrt(np.mean((pred[0, window:]
                                  - roll["t_air"][window:]) ** 2)))
    assert rmse > 0.1, "nominal rollout unexpectedly matches truth: %.4f" % rmse


def test_shared_rollout_deterministic_finite_and_warm_starts():
    """Same seed -> same model -> same rollout; warm start is truth."""
    p, roll, (t_out, t_set, q_int) = _truth()
    window = 12
    feats = series_features(roll["t_air"], t_out, t_set, q_int)
    wall0 = np.array([roll["t_wall"][window - 1]], dtype=np.float64)
    std = _std(window)
    m1 = make_shared(window * 6, (128, 128), 32, seed=42)
    m2 = make_shared(window * 6, (128, 128), 32, seed=42)
    for a, b in zip(m1.parameters(), m2.parameters()):
        torch.testing.assert_close(a, b)
    pred1 = rollout_shared(m1, std, feats[None, ...], wall0,
                           [p.to_dict()], window)
    pred2 = rollout_shared(m1, std, feats[None, ...], wall0,
                           [p.to_dict()], window)
    np.testing.assert_array_equal(pred1, pred2)
    assert np.isfinite(pred1).all()
    np.testing.assert_allclose(pred1[0, :window], feats[:window, 3], atol=1e-4)


def test_shared_checkpoint_round_trips_rc_params_mode(tmp_path):
    """load_shared must recover the rc_params_mode a checkpoint was trained with."""
    import evaluate

    std = Standardizer(np.zeros(72), np.ones(72), 20.0, 1.0)
    model = make_shared(72, (128, 128), 32, seed=42)
    ckpt = {
        "arm": "shared",
        "state_dict": model.state_dict(),
        "window": 12,
        "hidden": [128, 128],
        "latent": 32,
        "input_dim": 72,
        "seed": 42,
        "target": "level",
        "rc_params_mode": "nominal",
        "standardizer": std.to_dict(),
    }
    path = os.path.join(str(tmp_path), "model_shared.pt")
    torch.save(ckpt, path)
    _, _, loaded = evaluate.load_shared(str(tmp_path))
    assert str(loaded.get("rc_params_mode")) == "nominal"


def test_median_params_is_per_parameter_median():
    """median_params takes the median of each parameter independently."""
    rows = [{"a": 1.0, "b": 10.0},
            {"a": 3.0, "b": 20.0},
            {"a": 2.0, "b": 30.0}]
    out = median_params(rows)
    assert out == {"a": 2.0, "b": 20.0}

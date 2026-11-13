"""Known-value tests for the reference biquadratic generator + LS comparator.

Supervisor-completed during collection of the slice-1 worker (the worker hit
its step cap after writing src/curves.py and src/run_measurements.py but
before tests/report). These tests pin exactly the slice acceptance checks:

- the generator reproduces the published reference curve at known points;
- the least-squares refit recovers the generating coefficients on
  unrestricted (full operating box) noise-free data within tolerance;
- the restricted-training refit still recovers the coefficients on
  noise-free data (the comparator the PySR arm is judged against).
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from curves import (  # noqa: E402
    OPERATING_RANGE,
    REFERENCE_COEFFS,
    TRAIN_BOX,
    generate_dataset,
    ls_biquadratic_fit,
    rmse,
)

CAP = REFERENCE_COEFFS["ChillerCentCapFT"]


def test_generator_known_points():
    # evaluate(0, 0) is the intercept by construction of the biquadratic form.
    assert float(CAP.evaluate(0.0, 0.0)) == pytest.approx(CAP.a)
    # A hand-computed point: x=1, y=30.
    expected = (
        CAP.a + CAP.b + CAP.c + 30.0 * CAP.d + 900.0 * CAP.e + 30.0 * CAP.f
    )
    assert float(CAP.evaluate(1.0, 30.0)) == pytest.approx(expected, rel=1e-12)


def test_dataset_is_deterministic_per_seed():
    a = generate_dataset(7, 50, TRAIN_BOX)
    b = generate_dataset(7, 50, TRAIN_BOX)
    assert np.array_equal(a.x, b.x) and np.array_equal(a.y, b.y)
    # Noise-free samples lie exactly on the curve.
    assert rmse(CAP.evaluate(a.x[:, 0], a.x[:, 1]), a.y) == pytest.approx(0.0, abs=1e-12)


def test_ls_refit_recovers_coefficients_on_full_box():
    full = {"plr": OPERATING_RANGE["plr"], "temp_c": OPERATING_RANGE["temp_c"]}
    data = generate_dataset(0, 2000, full)
    fit, _ = ls_biquadratic_fit(data.x, data.y)
    assert np.allclose(fit.as_vector(), CAP.as_vector(), rtol=0, atol=1e-8)


def test_ls_refit_recovers_coefficients_on_restricted_box_noise_free():
    data = generate_dataset(1, 2000, TRAIN_BOX)
    fit, _ = ls_biquadratic_fit(data.x, data.y)
    assert np.allclose(fit.as_vector(), CAP.as_vector(), rtol=0, atol=1e-6)

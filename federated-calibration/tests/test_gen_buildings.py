"""Tests of the synthetic building generator (slice 1).

Covers:
  * the population is deterministic for a fixed seed (identical series),
  * a different seed gives a different population,
  * the generated series have the expected shape and no NaNs,
  * the client-side model of `local_model.py`, fed with the TRUE
    parameters, reproduces the generated zone temperature -- the two
    independent implementations of the physics agree.
"""

from __future__ import annotations

import numpy as np
import pytest

from gen_buildings import (CLIENT_SPECS, HELDOUT_SPECS, clear_sky,
                           generate_population, occupancy_profile)
from local_model import NOMINAL_PARAMS, rollout


def test_same_seed_gives_identical_series():
    c1, h1 = generate_population(42, 96)
    c2, h2 = generate_population(42, 96)
    assert len(c1) == len(CLIENT_SPECS)
    assert len(h1) == len(HELDOUT_SPECS)
    for a, b in list(zip(c1, c2)) + list(zip(h1, h2)):
        assert a.name == b.name
        for key in ("t_out", "t_set", "p_sched", "t_zone"):
            assert np.array_equal(a.__dict__[key], b.__dict__[key]), (
                "%s.%s differs between two runs of the same seed" % (a.name, key))
        assert a.truth == b.truth


def test_different_seed_gives_different_population():
    c1, _ = generate_population(42, 96)
    c2, _ = generate_population(43, 96)
    assert not np.array_equal(c1[0].t_zone, c2[0].t_zone)


def test_series_are_well_formed():
    clients, heldout = generate_population(7, 96)
    for b in clients + heldout:
        series = b.client_series()
        assert len(series["t_zone"]) == 96
        assert len(series["t_out"]) == len(series["t_set"]) == 96
        assert np.all(np.isfinite(series["t_zone"]))
        assert np.all(np.isfinite(series["t_out"]))
        # a habitable building: the zone temperature stays in a plausible band
        assert series["t_zone"].min() > 5.0
        assert series["t_zone"].max() < 40.0
        # the public shapes are what the client model assumes
        assert np.allclose(series["clear_sky"], clear_sky(96))
        assert np.allclose(series["p_sched"], occupancy_profile(96))


def test_truth_parameters_reproduce_the_generated_series():
    """The client-side model with the TRUE parameters must track the truth.

    This cross-checks the two independent implementations of the physics
    (generator in `gen_buildings.py`, client model in `local_model.py`).
    A residual of the order of the cloud misspecification (the client
    model cannot know the cloud factor) is expected, and bounded.
    """
    clients, _ = generate_population(11, 240)
    b = clients[1]
    series = b.client_series()
    truth_params = {"C": b.truth.C, "UA": b.truth.UA, "s": b.truth.s,
                    "g_sol": b.truth.g_sol}
    pred = rollout(truth_params, series, start=0, end=len(series["t_zone"]))
    rmse = float(np.sqrt(np.mean((pred - series["t_zone"]) ** 2)))
    assert rmse < 0.5, "truth parameters should track the series, rmse=%r" % rmse
    # and the nominal parameters must be clearly worse
    pred_nom = rollout(NOMINAL_PARAMS, series, start=0,
                       end=len(series["t_zone"]))
    rmse_nom = float(np.sqrt(np.mean((pred_nom - series["t_zone"]) ** 2)))
    assert rmse_nom > rmse

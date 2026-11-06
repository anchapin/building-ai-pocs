"""Tests of the FedAvg harness (slice 1).

Covers:
  * averaging identical updates is the identity,
  * averaging N updates is the element-wise mean,
  * a FedAvg run leaves the server's global parameters equal to the mean
    of the last round's client updates,
  * the server refuses anything that is not a scalar parameter update
    (raw data must never reach it).
"""

from __future__ import annotations

import numpy as np
import pytest

from federate import Client, FedAvgServer, run_fedavg
from gen_buildings import generate_population
from local_model import NOMINAL_PARAMS, PARAM_NAMES, mean_params


def _clients(n=3, hours=96):
    clients, _ = generate_population(5, hours)
    return [Client(b.name, b.client_series()) for b in clients[:n]]


def test_averaging_identical_updates_is_the_identity():
    upd = {"C": 1.23e6, "UA": 12.5, "s": 0.9, "g_sol": 321.0}
    out = mean_params([upd, upd, upd])
    for k in PARAM_NAMES:
        assert out[k] == pytest.approx(upd[k], rel=1e-12, abs=1e-12)


def test_averaging_n_updates_is_the_mean():
    upd = {"C": 1.0e6, "UA": 10.0, "s": 1.0, "g_sol": 300.0}
    upd2 = {"C": 3.0e6, "UA": 20.0, "s": 2.0, "g_sol": 500.0}
    out = mean_params([upd, upd2])
    assert out["C"] == pytest.approx(2.0e6)
    assert out["UA"] == pytest.approx(15.0)
    assert out["s"] == pytest.approx(1.5)
    assert out["g_sol"] == pytest.approx(400.0)


def test_server_aggregate_is_the_mean_of_the_updates():
    server = FedAvgServer(NOMINAL_PARAMS)
    updates = [{"C": 1.0e6, "UA": 10.0, "s": 1.0, "g_sol": 300.0},
               {"C": 3.0e6, "UA": 20.0, "s": 3.0, "g_sol": 500.0},
               {"C": 2.0e6, "UA": 30.0, "s": 2.0, "g_sol": 400.0}]
    got = server.aggregate(updates)
    assert got["C"] == pytest.approx(2.0e6)
    assert got["UA"] == pytest.approx(20.0)
    assert got["s"] == pytest.approx(2.0)
    assert got["g_sol"] == pytest.approx(400.0)
    assert server.global_params == got
    assert server.n_aggregations == 1


def test_fedavg_global_equals_mean_of_last_round_updates():
    clients = _clients()
    server = FedAvgServer(NOMINAL_PARAMS)
    records = run_fedavg(clients, server, rounds=3, local_steps=10, lr=0.05)
    last = records[-1].client_params
    for k in PARAM_NAMES:
        expected = float(np.mean([u[k] for u in last]))
        assert server.global_params[k] == pytest.approx(expected, rel=1e-12)


def test_server_rejects_non_scalar_updates():
    server = FedAvgServer(NOMINAL_PARAMS)
    series = np.arange(10.0)
    with pytest.raises(TypeError):
        server.aggregate([{"C": series, "UA": 1.0, "s": 1.0, "g_sol": 1.0}])
    with pytest.raises(TypeError):
        server.aggregate([series])
    with pytest.raises(TypeError):
        server.aggregate([{"C": 1e6, "UA": 1.0, "s": 1.0, "g_sol": 1.0,
                           "t_zone": series}])
    with pytest.raises(ValueError):
        server.aggregate([])

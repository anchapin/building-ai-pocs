"""Tests of the no-raw-data boundary (slice 1).

The claim under test: *only parameter updates cross the client/server
boundary*.  Concretely:

  * after a federated round, no client object holds another building's
    time-series,
  * the server object holds no array at all (only scalars and dicts of
    scalars),
  * everything a client returns is a scalar parameter.
"""

from __future__ import annotations

import numpy as np
import pytest

from federate import Client, FedAvgServer, run_fedavg
from gen_buildings import generate_population
from local_model import PARAM_NAMES


def _population(n=4, hours=96):
    clients, _ = generate_population(9, hours)
    return clients


def test_client_holds_no_other_buildings_series():
    buildings = _population()
    clients = [Client(b.name, b.client_series()) for b in buildings]
    # Only the private series are building-specific: p_sched and clear_sky
    # are public deterministic shapes (the same function of n for every
    # building, by design), so they are identical across buildings and carry
    # no private information -- the cross-building check covers t_out/t_zone.
    private_keys = ("t_out", "t_zone")
    for i, (client, b) in enumerate(zip(clients, buildings)):
        own = b.client_series()
        for key, arr in own.items():
            assert any(np.array_equal(arr, held) for held in client.series_arrays), (
                "client %d lost its own %s series" % (i, key))
        for j, other in enumerate(buildings):
            if j == i:
                continue
            for key in private_keys:
                arr = other.client_series()[key]
                assert not any(np.array_equal(arr, held) for held in client.series_arrays), (
                    "client %d holds building %s's %s series" % (i, other.name, key))


def test_client_update_returns_scalars_only():
    buildings = _population(n=2)
    clients = [Client(b.name, b.client_series()) for b in buildings]
    upd = clients[0].local_update({"C": 3e6, "UA": 18.0, "s": 1.0, "g_sol": 400.0},
                                   steps=5)
    assert set(upd) == set(PARAM_NAMES)
    for k, v in upd.items():
        assert isinstance(v, float), (k, type(v))
        assert np.isfinite(v)


def test_server_holds_no_arrays_after_a_full_run():
    buildings = _population()
    clients = [Client(b.name, b.client_series()) for b in buildings]
    server = FedAvgServer({"C": 3e6, "UA": 18.0, "s": 1.0, "g_sol": 400.0})
    run_fedavg(clients, server, rounds=2, local_steps=5)

    def _walk(obj, seen=None, path="server"):
        seen = seen if seen is not None else []
        for name, value in vars(obj).items():
            p = "%s.%s" % (path, name)
            if isinstance(value, np.ndarray):
                seen.append(p)
            elif isinstance(value, dict):
                for k, v in value.items():
                    if isinstance(v, np.ndarray):
                        seen.append("%s[%s]" % (p, k))
                    elif not isinstance(v, (int, float, str)):
                        seen.extend(_walk(v, seen, p))
            elif isinstance(value, (list, tuple)):
                for i, v in enumerate(value):
                    if isinstance(v, np.ndarray):
                        seen.append("%s[%d]" % (p, i))
                    elif isinstance(v, dict):
                        for k, vv in v.items():
                            if isinstance(vv, np.ndarray):
                                seen.append("%s[%d][%s]" % (p, i, k))
            elif hasattr(value, "__dict__") and not isinstance(value, (str, int, float)):
                seen.extend(_walk(value, seen, p))
        return seen

    assert _walk(server) == [], "the server must not hold any array"
    # and the global parameters are plain floats
    for k, v in server.global_params.items():
        assert isinstance(v, float)


def test_client_data_is_never_modified_by_the_federation():
    buildings = _population(n=2)
    clients = [Client(b.name, b.client_series()) for b in buildings]
    before = [np.copy(a) for a in clients[0].series_arrays]
    server = FedAvgServer({"C": 3e6, "UA": 18.0, "s": 1.0, "g_sol": 400.0})
    run_fedavg(clients, server, rounds=2, local_steps=5)
    for arr, ref in zip(clients[0].series_arrays, before):
        assert np.array_equal(arr, ref)

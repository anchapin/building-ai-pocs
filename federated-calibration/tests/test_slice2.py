"""Tests of the slice-2 experiment code (verdict slice).

Covers:
  * partial participation: subset selection (size, sorted, deterministic,
    validation) and the per-round participant bookkeeping,
  * heterogeneity modes: client specs per mode, truth-parameter spread
    (wide > baseline, clustered tight within / far across clusters, iid
    near-identical),
  * the extra one-shot baselines reported under partial participation,
  * the slice-1 artefact shape is unchanged for the default configuration
    (byte-identical results), and the slice-2 driver is deterministic.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from evaluate import run_seed
from federate import Client, FedAvgServer, run_fedavg, select_participants
from gen_buildings import CLIENT_SPECS, client_specs, generate_population
from local_model import NOMINAL_PARAMS, PARAM_NAMES
from run_slice2 import CONFIGS, summarise


def _clients(n=9, hours=96, seed=5):
    clients, _ = generate_population(seed, hours)
    return [Client(b.name, b.client_series()) for b in clients[:n]]


# ---------------------------------------------------------------------------
# select_participants
# ---------------------------------------------------------------------------

def test_select_participants_full_returns_everyone():
    clients = _clients()
    rng = np.random.default_rng(0)
    assert select_participants(clients, 1.0, rng) == list(range(9))


def test_select_participants_half_returns_five_sorted_unique():
    clients = _clients()
    rng = np.random.default_rng(42)
    idx = select_participants(clients, 0.5, rng)
    assert len(idx) == 5  # ceil(0.5 * 9)
    assert idx == sorted(set(idx))
    assert all(0 <= i < 9 for i in idx)


def test_select_participants_is_deterministic_for_a_seed():
    clients = _clients()
    a = select_participants(clients, 0.5, np.random.default_rng(7))
    b = select_participants(clients, 0.5, np.random.default_rng(7))
    assert a == b


def test_select_participants_rejects_bad_fractions_and_empty():
    clients = _clients()
    for bad in (0.0, -0.1, 1.01, 2.0):
        with pytest.raises(ValueError):
            select_participants(clients, bad, np.random.default_rng(0))
    with pytest.raises(ValueError):
        select_participants([], 0.5, np.random.default_rng(0))


def test_run_fedavg_partial_records_participants():
    clients = _clients(n=9)
    server = FedAvgServer(NOMINAL_PARAMS)
    records = run_fedavg(clients, server, rounds=4, local_steps=5,
                         participation=0.5, seed=11)
    assert len(records) == 4
    for r in records:
        assert len(r.participants) == 5
        assert r.participants == sorted(set(r.participants))
    # every client takes part in at least one of four rounds with p=0.5
    seen = set()
    for r in records:
        seen.update(r.participants)
    assert len(seen) >= 5


def test_run_fedavg_full_participation_records_everyone():
    clients = _clients(n=3)
    server = FedAvgServer(NOMINAL_PARAMS)
    records = run_fedavg(clients, server, rounds=2, local_steps=5)
    assert records[0].participants == [0, 1, 2]


# ---------------------------------------------------------------------------
# heterogeneity modes
# ---------------------------------------------------------------------------

def test_client_specs_baseline_and_wide_match_slice1():
    assert client_specs("baseline") == list(CLIENT_SPECS)
    assert client_specs("wide") == list(CLIENT_SPECS)


def test_client_specs_clustered_is_three_groups_of_three():
    specs = client_specs("clustered")
    assert len(specs) == 9
    assert [s[1] for s in specs] == (["light"] * 3 + ["heavy"] * 3
                                    + ["medium"] * 3)
    assert [s[2] for s in specs] == (["cold"] * 3 + ["hot"] * 3
                                    + ["temperate"] * 3)


def test_client_specs_iid_is_one_archetype():
    specs = client_specs("iid")
    assert len(specs) == 9
    assert all(s[1:] == ("medium", "temperate") for s in specs)


def test_client_specs_rejects_unknown_mode():
    with pytest.raises(ValueError):
        client_specs("nope")


def _truth_matrix(heterogeneity, seed=42, hours=240):
    clients, _ = generate_population(seed, hours,
                                     heterogeneity=heterogeneity)
    return np.array([[b.truth.C, b.truth.UA, b.truth.s, b.truth.g_sol]
                     for b in clients])


def test_truth_spread_wide_exceeds_baseline():
    base = _truth_matrix("baseline")
    wide = _truth_matrix("wide")
    # same archetypes, wider per-building spread: the relative std of every
    # parameter is larger under "wide" than under "baseline"
    for j in range(4):
        assert (np.std(wide[:, j]) / np.mean(wide[:, j])
                > np.std(base[:, j]) / np.mean(base[:, j]))


def test_truth_spread_clustered_tight_within_far_across():
    m = _truth_matrix("clustered")
    for lo in (0, 3, 6):
        within = np.std(m[lo:lo + 3], axis=0) / np.mean(m[lo:lo + 3], axis=0)
        # 3 draws only: uniform (0.9, 1.1) has expected rel-std 0.058, so
        # 0.10 allows sampling noise while staying tight.
        assert np.all(within < 0.10)
    # cluster means are far apart relative to the within-cluster spread
    means = np.array([np.mean(m[lo:lo + 3], axis=0) for lo in (0, 3, 6)])
    assert np.std(means[:, 0]) / np.mean(means[:, 0]) > 0.15  # C
    assert np.std(means[:, 1]) / np.mean(means[:, 1]) > 0.15  # UA


def test_truth_spread_iid_near_identical():
    m = _truth_matrix("iid")
    rel_std = np.std(m, axis=0) / np.mean(m, axis=0)
    # 9 draws: uniform (0.95, 1.05) has expected rel-std 0.029, so 0.05
    # allows sampling noise while staying far below the baseline spread (~0.23).
    assert np.all(rel_std < 0.05)


def test_heldout_buildings_unchanged_by_mode():
    _, held_base = generate_population(42, 240, heterogeneity="baseline")
    for mode in ("wide", "clustered", "iid"):
        _, held = generate_population(42, 240, heterogeneity=mode)
        for a, b in zip(held_base, held):
            assert a.truth == b.truth
            assert a.name == b.name


# ---------------------------------------------------------------------------
# evaluate.py under partial participation / heterogeneity
# ---------------------------------------------------------------------------

def test_run_seed_partial_participation_reports_extra_baselines():
    res = run_seed(42, hours=240, participation=0.5, verbose=False)
    rows = res["heldout"]["holdout-H1"]
    variants = [r["variant"] for r in rows]
    assert any(v.startswith("zero-shot, parameter-mean of round-1 online")
               for v in variants)
    assert any(v.startswith("zero-shot, parameter-mean of all")
               for v in variants)
    assert "zero-shot, parameter-mean of 9 client models" in variants
    diag = res["federated_diagnostics"]
    assert diag["participation"] == 0.5
    assert len(diag["participants_per_round"]) == 15
    assert all(len(p) == 5 for p in diag["participants_per_round"])
    assert 1 <= diag["distinct_participants"] <= 9


def test_run_seed_default_config_keeps_slice1_shape():
    res = run_seed(42, hours=240, verbose=False)
    assert "heterogeneity" not in res["config"]
    assert "participation" not in res["config"]
    assert "participation" not in res["federated_diagnostics"]
    assert "heterogeneity" not in res["federated_diagnostics"]
    assert "distinct_participants" not in res["federated_diagnostics"]


def test_run_seed_partial_participation_is_deterministic():
    a = run_seed(43, hours=240, participation=0.5, verbose=False)
    b = run_seed(43, hours=240, participation=0.5, verbose=False)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_run_seed_heterogeneity_modes_run():
    for mode in ("wide", "clustered", "iid"):
        res = run_seed(42, hours=240, heterogeneity=mode, verbose=False)
        assert res["config"]["heterogeneity"] == mode
        fed = [r for r in res["heldout"]["holdout-H1"]
               if r["variant"] == "zero-shot, FedAvg over 9 clients"][0]
        assert np.isfinite(fed["rmse_rollout"])


# ---------------------------------------------------------------------------
# run_slice2 driver
# ---------------------------------------------------------------------------

def test_slice2_configs_cover_the_discriminating_axes():
    labels = [c[0] for c in CONFIGS]
    assert any("participation" in l for l in labels)
    assert any("wide" in l for l in labels)
    assert any("clustered" in l for l in labels)
    assert any("iid" in l for l in labels)
    assert CONFIGS[0][1:] == ("baseline", 1.0)  # first is the control


def test_summarise_gate_math_on_one_seed():
    from run_slice2 import run_config
    results = run_config([42], "baseline", 1.0, verbose=False)
    summary = summarise("baseline (slice-1 control)", results)
    fed_h1 = summary["heldout"]["holdout-H1"][
        "zero-shot, FedAvg over 9 clients"]["mean"]
    pm_h1 = summary["heldout"]["holdout-H1"][
        "zero-shot, parameter-mean of 9 client models"]["mean"]
    assert np.isfinite(fed_h1) and np.isfinite(pm_h1)
    gate = summary["heldout"]["holdout-H1"]["_gate"][
        "zero-shot, parameter-mean of 9 client models"]
    # improvement_pct is +ve when FedAvg beats the row; slice 1 (3 seeds)
    # has FedAvg ~6% worse than parameter-mean, so the 1-seed gate must be
    # negative and of the same order, not a sign error the other way.
    assert gate["improvement_pct"] < 0.0
    assert gate["improvement_pct"] > -30.0

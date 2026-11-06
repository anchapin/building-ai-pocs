"""Tests of the MLP baseline and of the evaluation harness (slice 1).

Covers:
  * the MLP trains, its test RMSE is finite and recorded,
  * evaluate.py reproduces the headline table from the saved artefacts,
  * the headline table is deterministic (identical bytes on a re-run),
  * the table reports every required column with its N.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def _run(script, *args):
    cmd = [sys.executable, os.path.join(SRC, script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def _pipeline(tmp_path, steps=72, epochs=3, window=6, target="level"):
    data_dir = str(tmp_path / "data")
    _run("gen_data.py", "--seed", "42", "--steps", str(steps), "--out-dir", data_dir)
    _run("train.py", "--seed", "42", "--epochs", str(epochs), "--window", str(window),
         "--target", target, "--data-dir", data_dir, "--out-dir", data_dir)
    return data_dir


def test_evaluate_honours_checkpoint_target(tmp_path):
    """The rollout must use the parameterisation the model was trained with.

    A delta-trained model rolled out as level (or vice versa) misreports
    or diverges; evaluate.py reads the target from model.pt and prints it.
    """
    data_dir = _pipeline(tmp_path, target="level")
    out = _run("evaluate.py", "--seed", "42", "--data-dir", data_dir,
               "--out-dir", data_dir).stdout
    assert "(parameterisation=level)" in out
    with open(os.path.join(data_dir, "headline_table.json")) as fh:
        table = json.load(fh)
    # headline_table.json holds both metric blocks; the gate rows live in
    # "summary" (the "aligned" block is the physics-aligned second table).
    for row in table["summary"]:
        assert np.isfinite(row["rmse_t"]) and row["rmse_t"] < 1e6, (
            "level-model rollout diverged: %r" % row)


def test_mlp_trains_and_records_metrics(tmp_path):
    data_dir = _pipeline(tmp_path)
    with open(os.path.join(data_dir, "train_metrics.json")) as fh:
        m = json.load(fh)
    assert m["parameters"] > 0
    assert np.isfinite(m["train_rmse_c"]) and np.isfinite(m["val_rmse_c"])
    assert np.isfinite(m["test_id_rmse_c"])
    assert m["test_id_rmse_c"] > 0.0
    assert m["wall_time_s"] > 0.0
    assert os.path.exists(os.path.join(data_dir, "model.pt"))


def test_evaluate_reproduces_headline_table(tmp_path):
    data_dir = _pipeline(tmp_path)
    out = _run("evaluate.py", "--seed", "42", "--data-dir", data_dir,
               "--out-dir", data_dir).stdout
    for token in ("RMSE_T[C]", "HBresid[%]", "PeakQerr[W]", "PeakQerr[%]",
                  "test_weather (UNSEEN weather)", "test_setpoint (UNSEEN setpoint)",
                  "Nser", "Nsteps"):
        assert token in out, f"headline table is missing {token!r}"
    assert "verdict" in out  # explicit statement that no verdict is claimed
    assert "NOT claimed in this slice" in out
    assert os.path.exists(os.path.join(data_dir, "headline_table.txt"))


def test_evaluate_is_deterministic(tmp_path):
    data_dir = _pipeline(tmp_path)
    first = _run("evaluate.py", "--seed", "42", "--data-dir", data_dir,
                 "--out-dir", data_dir).stdout
    second = _run("evaluate.py", "--seed", "42", "--data-dir", data_dir,
                  "--out-dir", data_dir).stdout
    assert first == second, "the headline table is not reproducible"

    with open(os.path.join(data_dir, "headline_table.json")) as fh:
        table = json.load(fh)
    assert len(table["summary"]) > 0
    assert isinstance(table["aligned"], list)
    for row in table["summary"]:
        assert row["n_series"] > 0 and row["n_steps"] > 0
        assert np.isfinite(row["rmse_t"]) and np.isfinite(row["rmse_q"])
        assert np.isfinite(row["hb_resid_pct"])
        assert np.isfinite(row["peak_q_err_w"])
        # Pooled RMSE is never below the pooled MAE (regression test for
        # the aggregate() double-division bug, which understated every
        # RMSE in the headline table by sqrt(n_series)).
        assert row["rmse_t"] >= row["mae_t"] - 1e-12
        assert row["rmse_q"] >= row["mae_q"] - 1e-12


def test_aggregate_pooled_rmse_matches_direct_computation():
    """aggregate() must equal the RMSE of the concatenated per-step errors."""
    sys.path.insert(0, SRC)
    from evaluate import aggregate

    rows = [
        {"arm": "MLP (plain)", "split": "val", "series": 0, "n": 100,
         "rmse_t": 2.0, "mae_t": 1.5, "rmse_q": 40.0, "mae_q": 30.0,
         "hb_resid_pct": 10.0, "peak_q_err_w": 5.0, "peak_q_err_pct": 1.0},
        {"arm": "MLP (plain)", "split": "val", "series": 1, "n": 300,
         "rmse_t": 4.0, "mae_t": 3.0, "rmse_q": 80.0, "mae_q": 60.0,
         "hb_resid_pct": 20.0, "peak_q_err_w": 15.0, "peak_q_err_pct": 2.0},
    ]
    agg = aggregate(rows, "MLP (plain)", "val")
    # Direct pooled computation: sqrt(sum(rmse_i^2 * n_i) / sum(n_i)).
    assert agg["rmse_t"] == np.sqrt((2.0 ** 2 * 100 + 4.0 ** 2 * 300) / 400)
    assert agg["rmse_q"] == np.sqrt((40.0 ** 2 * 100 + 80.0 ** 2 * 300) / 400)
    assert agg["mae_t"] == (1.5 * 100 + 3.0 * 300) / 400
    assert agg["mae_q"] == (30.0 * 100 + 60.0 * 300) / 400
    assert agg["rmse_t"] >= agg["mae_t"]
    assert agg["rmse_q"] >= agg["mae_q"]
    assert agg["n_series"] == 2 and agg["n_steps"] == 400

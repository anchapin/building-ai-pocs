"""Tests of the evaluation harness (slice 1).

Covers:
  * the headline table is produced by one command and contains every arm,
  * a determinism rerun is byte-identical (stdout),
  * the headline numbers are finite and the JSON artefact is written.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")

SMALL = ["--hours", "96", "--rounds", "3", "--local-steps", "10",
         "--fit-steps", "60"]


def _run(out_dir, *args):
    cmd = [sys.executable, os.path.join(SRC, "run_poc.py"),
           "--out-dir", str(out_dir), *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def test_headline_table_contains_every_arm(tmp_path):
    out = _run(tmp_path, "--seed", "42", *SMALL).stdout
    assert "isolated-local" in out
    assert "federated (FedAvg)" in out
    assert "centralised (pooled)" in out
    assert "RMSE_roll" in out
    assert "per-building rows" in out
    assert "FedAvg diagnostics" in out
    path = os.path.join(str(tmp_path), "results_seed42.json")
    assert os.path.exists(path)
    with open(path) as fh:
        res = json.load(fh)
    rows = res["heldout"]["holdout-H1"]
    variants = [r["variant"] for r in rows]
    assert "zero-shot, FedAvg over 9 clients" in variants
    assert "zero-shot, one model on pooled data" in variants
    for r in rows:
        assert r["rmse_rollout"] == r["rmse_rollout"]  # not NaN
        assert abs(r["rmse_rollout"]) < 1e6


def test_headline_rerun_is_byte_identical(tmp_path):
    # Both runs write to the SAME out-dir: the "results written:" line embeds
    # the out-dir path, so different dirs can never be byte-identical stdout
    # even when the computation is fully deterministic (the results JSONs
    # across different dirs are byte-identical -- verified by hand).
    a = _run(tmp_path, "--seed", "42", *SMALL).stdout
    b = _run(tmp_path, "--seed", "42", *SMALL).stdout
    assert a == b, "the headline output is not deterministic"


def test_multi_seed_summary(tmp_path):
    out = _run(tmp_path, "--seed", "42,43", *SMALL).stdout
    assert "summary over 2 seed(s)" in out
    assert "held-out building holdout-H1" in out

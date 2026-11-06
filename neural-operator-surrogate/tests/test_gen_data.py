"""Tests of the synthetic data generation and of the split design (slice 1).

The extrapolation guarantees are *proven* here, not asserted in prose:
  * the unseen weather pattern (cold_snap) never appears in train/val,
  * the unseen setpoint schedule (varying) never appears in train/val,
  * every split contains real series (no empty arm),
  * the stored ground truth is an exact trajectory of the RC model itself.
"""

from __future__ import annotations

import numpy as np
import pytest

from gen_data import (SPLIT_COMBOS, SPLIT_NAMES, build_split, iter_series,
                      load_split, save_split)
from rc_model import RCParams, rollout_numpy


def test_split_combination_membership():
    train_weather = {w for w, _ in SPLIT_COMBOS["train"]}
    train_setpoint = {s for _, s in SPLIT_COMBOS["train"]}
    assert "cold_snap" not in train_weather, "extrapolation weather leaked into train"
    assert "varying" not in train_setpoint, "extrapolation setpoint leaked into train"
    # val must be in-distribution as well
    assert set(SPLIT_COMBOS["val"]) <= set(SPLIT_COMBOS["train"])
    assert set(SPLIT_COMBOS["test_id"]) <= set(SPLIT_COMBOS["train"])
    # the extrapolation splits hold out exactly the intended axis
    assert {w for w, _ in SPLIT_COMBOS["test_weather"]} == {"cold_snap"}
    assert {s for _, s in SPLIT_COMBOS["test_setpoint"]} == {"varying"}
    assert {w for w, _ in SPLIT_COMBOS["test_both"]} == {"cold_snap"}
    assert {s for _, s in SPLIT_COMBOS["test_both"]} == {"varying"}


def test_no_leakage_between_splits():
    """Weather/setpoint combinations of the extrapolation splits must be
    absent from the training split (checked on the generated data)."""
    for split in SPLIT_NAMES:
        flat, meta = build_split(split, seed=42, n_steps=48)
        combos = {(m["weather"], m["setpoint"]) for m in meta}
        if split in ("train", "val", "test_id"):
            assert "cold_snap" not in {w for w, _ in combos}
            assert "varying" not in {s for _, s in combos}
        if split == "test_weather":
            assert {w for w, _ in combos} == {"cold_snap"}
            assert {s for _, s in combos} <= {"fixed", "setback"}
        if split == "test_setpoint":
            assert {s for _, s in combos} == {"varying"}
            assert {w for w, _ in combos} <= {"mild", "hot_spell"}
        if split == "test_both":
            assert combos == {("cold_snap", "varying")}


def test_every_split_has_data():
    for split in SPLIT_NAMES:
        flat, meta = build_split(split, seed=42, n_steps=48)
        assert len(meta) > 0, f"split {split} is empty"
        assert flat["t_out"].size == 48 * len(meta)
        assert np.all(np.isfinite(flat["t_zone"]))


def test_data_is_generated_from_the_rc_model():
    """The stored ground truth must be an exact RC trajectory."""
    flat, meta = build_split("train", seed=42, n_steps=48)
    series = iter_series(flat)
    m = meta[0]
    params = RCParams.from_dict(m["params"])
    s = series[0]
    roll = rollout_numpy(params, s["t_out"], s["t_set"], s["q_int"])
    assert np.max(np.abs(roll["t_air"] - s["t_zone"])) <= 1e-9
    assert np.max(np.abs(roll["t_wall"] - s["t_wall"])) <= 1e-9
    assert np.max(np.abs(roll["q_sup"] - s["q_sup"])) <= 1e-9


def test_generation_is_deterministic_for_a_fixed_seed():
    a, _ = build_split("test_setpoint", seed=7, n_steps=48)
    b, _ = build_split("test_setpoint", seed=7, n_steps=48)
    for k in ("t_out", "t_set", "q_int", "t_zone", "t_wall", "q_sup"):
        assert np.array_equal(a[k], b[k])
    c, _ = build_split("test_setpoint", seed=8, n_steps=48)
    assert not np.array_equal(a["t_zone"], c["t_zone"])


def test_save_and_load_roundtrip(tmp_path):
    info = save_split("test_weather", seed=42, n_steps=48, out_dir=str(tmp_path))
    assert info["n_series"] > 0
    flat = load_split(str(tmp_path), "test_weather")
    assert flat["t_out"].size == info["n_rows"]

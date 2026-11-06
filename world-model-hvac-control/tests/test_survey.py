"""Tests for the slice-2 data set survey (``survey_datasets.py``).

The discriminating tests pin the two properties slice 2 established
empirically: ``baeda_3dem`` / ``Building_1`` does not respond to the HVAC
action at all (slice-1 finding F1), while the RESStock building responds
monotonically on the SAME episode window -- the property the fresh-env-per-
action fix in :func:`survey_datasets.probe_building` exists to protect (the
pre-fix survey scored the three actions on three different days and reported
a spurious "full heat uses less energy than do-nothing" for tx_travis).
"""

import os

import pytest

from citylearn_env import resolve_dataset_schema
from survey_datasets import is_responsive, probe_building

TX_DATASET = "tx_travis_county_neighborhood"
TX_BUILDING = "resstock-amy2018-2021-release-1-102188"


def test_is_responsive_noise_floor():
    assert is_responsive(0.0) is False
    assert is_responsive(1e-4) is False
    assert is_responsive(1e-3) is False
    assert is_responsive(1.1e-3) is True
    assert is_responsive(7.37) is True


def test_resolve_dataset_schema_prefers_local_copy(poc_dir):
    resolved = resolve_dataset_schema("baeda_3dem")
    assert resolved == os.path.join(poc_dir, "data", "datasets", "baeda_3dem")
    assert os.path.isfile(os.path.join(resolved, "schema.json"))

    assert resolve_dataset_schema("no-such-dataset") == "no-such-dataset"


def test_probe_baeda_net_electricity_unresponsive():
    """Slice-1 finding F1, reproduced: net electricity is action-independent."""

    row = probe_building("baeda_3dem", "Building_1", episode_steps=24, seed=0)

    assert row["ok"] is True
    assert row["net_electricity_kwh__none"] == pytest.approx(
        row["net_electricity_kwh__full_heat"], abs=1e-9
    )
    assert row["net_electricity_kwh__none"] == pytest.approx(
        row["net_electricity_kwh__full_cool"], abs=1e-9
    )
    assert row["net_electricity_spread_kwh"] == pytest.approx(0.0, abs=1e-6)
    assert row["net_electricity_responsive"] is False
    assert row["heating_actuated"] is False
    # A nominal 24-step episode yields 23 transitions: CityLearn terminates
    # when time_step reaches the episode end (slice 1's smoke run showed the
    # same: 2 episodes = 46 steps).
    assert row["steps__none"] == row["steps__full_heat"] == row["steps__full_cool"] == 23


def test_probe_same_window_response_is_monotonic():
    """On one window, heating and cooling both cost MORE than do-nothing.

    This fails on the pre-fix survey (shared env across resets scored the
    three actions on three different days; tx_travis then showed full heat
    at 5.93 kWh vs 8.98 kWh for do-nothing) and passes with the fresh-env-
    per-action probe (13.01 / 16.35 vs 8.98 kWh).
    """

    row = probe_building(TX_DATASET, TX_BUILDING, episode_steps=24, seed=0)

    assert row["ok"] is True
    assert row["heating_actuated"] is True
    assert row["heating_nominal_power_kw"] > 0.0
    assert row["cooling_nominal_power_kw"] > 0.0
    assert row["net_electricity_kwh__full_heat"] > row["net_electricity_kwh__none"]
    assert row["net_electricity_kwh__full_cool"] > row["net_electricity_kwh__none"]
    assert row["net_electricity_responsive"] is True
    # See the baeda test: a nominal 24-step episode yields 23 transitions.
    assert row["steps__none"] == row["steps__full_heat"] == row["steps__full_cool"] == 23

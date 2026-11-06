"""Shared pytest fixtures for the POC #4 slice-1 tests."""

import os
import sys

import pytest

POC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)


@pytest.fixture(scope="session")
def poc_dir() -> str:
    """Absolute path of the ``world-model-hvac-control`` folder."""

    return POC_DIR


@pytest.fixture(scope="session")
def dataset_name() -> str:
    """CityLearn data set used by the tests (downloaded once into the cache)."""

    return "baeda_3dem"


@pytest.fixture(scope="session")
def building_name() -> str:
    """Building used by the tests."""

    return "Building_1"

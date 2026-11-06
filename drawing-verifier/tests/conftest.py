"""Make the drawing-verifier package importable from the tests."""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
POC_DIR = os.path.dirname(HERE)
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)

FIXTURE_DIR = os.path.join(POC_DIR, "fixtures")
INJECTED_DIR = os.path.join(FIXTURE_DIR, "injected")
CASES_FILE = os.path.join(INJECTED_DIR, "cases.json")


def pytest_addoption(parser):
    parser.addoption("--poc-dir", action="store", default=POC_DIR, help="unused placeholder")


@pytest.fixture(scope="session")
def poc_dir():
    return POC_DIR


@pytest.fixture(scope="session")
def fixture_dir():
    return FIXTURE_DIR


@pytest.fixture(scope="session")
def injected_dir():
    return INJECTED_DIR


@pytest.fixture(scope="session")
def cases():
    import json

    with open(CASES_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)["cases"]


@pytest.fixture()
def clean_model():
    """The small office fixture, loaded and deep-copied per test."""
    import copy
    import json

    with open(os.path.join(FIXTURE_DIR, "small_office.json"), "r", encoding="utf-8") as handle:
        return copy.deepcopy(json.load(handle))

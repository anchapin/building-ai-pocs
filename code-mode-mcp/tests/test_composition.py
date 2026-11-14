"""The agent-side composition (arms/composition.py) must reproduce the frozen
golden for every task - this is an independent implementation of the task
semantics (the first one is the frozen reference in workload.py)."""
import json
import os

import composition
import workload

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def golden(task_id):
    with open(os.path.join(HERE, "golden", workload.GOLDEN_FILES[task_id]), encoding="utf-8") as fh:
        return json.load(fh)


def test_compose_T1_matches_golden(elevation_data):
    assert composition.compose_T1(elevation_data) == golden("T1")


def test_compose_T2_matches_golden(elevation_data):
    assert composition.compose_T2(elevation_data) == golden("T2")


def test_compose_T3_matches_golden(elevation_data):
    assert composition.compose_T3(elevation_data) == golden("T3")


def test_compose_T4_matches_golden(elevation_data, crop_results):
    assert composition.compose_T4(elevation_data, crop_results) == golden("T4")


def test_compose_T5_matches_golden(elevation_data, summary):
    assert composition.compose_T5(elevation_data, summary) == golden("T5")


def test_composition_is_not_the_reference_code():
    """Guard against the gate becoming vacuous: the two implementations are
    separate modules."""
    import workload as frozen
    assert composition.compose_T1.__module__ == "composition"
    assert frozen.ref_T1.__module__ == "workload"

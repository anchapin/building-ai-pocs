"""The code-mode programs, executed by pydantic-monty, must reproduce the
frozen golden exactly, and must stay inside the documented Monty subset."""
import json
import os

import pytest

import code_mode
import monty_programs
import workload

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def golden(task_id):
    with open(os.path.join(HERE, "golden", workload.GOLDEN_FILES[task_id]), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def monty_results(server):
    arm = code_mode.CodeModeArm(server)
    records = arm.run(monty_programs.PROGRAMS)
    return {rec["task_id"]: rec for rec in records}, arm.errors


@pytest.mark.parametrize("task_id", workload.TASK_IDS)
def test_program_output_matches_golden(monty_results, task_id):
    records, errors = monty_results
    assert not errors, errors
    record = records[task_id]
    assert record["error"] is None
    assert record["output"] == golden(task_id)


def test_agent_facing_call_count_is_one(monty_results):
    records, _ = monty_results
    for task_id, record in records.items():
        assert record["calls"] == 1, task_id


def test_host_call_counts_match_the_pinned_plan(monty_results, elevation_data):
    """The program makes exactly the calls the pinned call plan makes."""
    records, _ = monty_results
    for task_id in workload.TASK_IDS:
        expected = len(workload.sequential_call_plan(task_id, elevation_data))
        assert records[task_id]["host_calls"] == expected, task_id


def test_context_bytes_are_the_final_string_only(monty_results):
    records, _ = monty_results
    for task_id, record in records.items():
        final = json.dumps(record["output"], sort_keys=True, separators=(",", ":"))
        assert record["context_bytes"] == len(final.encode("utf-8"))
        assert record["context_bytes"] < record["bytes_returned"]


def test_programs_stay_inside_the_monty_subset():
    """No third-party imports, no classes, no generators, no `del`."""
    forbidden = ["import numpy", "import pandas", "import scipy", "class ",
                 "yield ", "del ", "__import__", "eval(", "exec("]
    for task_id, program in monty_programs.PROGRAMS.items():
        for token in forbidden:
            assert token not in program, (task_id, token)


def test_aggregate_variant_also_matches_the_golden(server):
    arm = code_mode.CodeModeArm(server)
    record = arm.run_one("T5-aggregate", monty_programs.T5_AGGREGATE_PROGRAM)
    assert record["error"] is None
    assert record["output"] == golden("T5")
    assert record["host_calls"] == 3  # list_sheets, extract_all_elevations, summarise_findings

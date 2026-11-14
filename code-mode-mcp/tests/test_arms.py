"""Arm-level tests: the Sequential MCP client (built inside code-mode-mcp/),
the pinned call plan, and the byte accounting."""
import asyncio
import json
import os

import common
import sequential
import workload

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def golden(task_id):
    with open(os.path.join(HERE, "golden", workload.GOLDEN_FILES[task_id]), encoding="utf-8") as fh:
        return json.load(fh)


def test_pinned_plan_has_no_aggregate_call_in_the_sequential_arm():
    for task_id in workload.TASK_IDS:
        tools = [tool for tool, _ in workload.extraction_calls(task_id)]
        assert "extract_all_elevations" not in tools
        assert tools[0] == "list_sheets"
        assert tools.count("list_sheets") == 1


def test_aggregate_plan_is_only_in_the_sensitivity_row():
    tools = [tool for tool, _ in workload.aggregate_call_plan("T5")]
    assert tools == ["list_sheets", "extract_all_elevations", "summarise_findings"]


def test_byte_accounting_is_utf8_length():
    assert common.nbytes("abc") == 3
    assert common.nbytes("\u00e9") == 2  # one character, two UTF-8 bytes
    assert common.nbytes("") == 0


def test_sequential_arm_T1_matches_golden_and_accounts_bytes():
    arm = sequential.SequentialArm(common.SERVER_SCRIPT)
    records = asyncio.run(arm.run(["T1"]))
    record = records[0]
    assert record["output"] == golden("T1")
    assert record["calls"] == 5
    assert record["bytes_returned"] == record["context_bytes"]
    # list_sheets() + the four extract_elevation_openings() results
    assert record["bytes_returned"] == 13140
    assert record["call_list"].startswith("list_sheets()")


def test_sequential_arm_T5_matches_golden():
    arm = sequential.SequentialArm(common.SERVER_SCRIPT)
    records = asyncio.run(arm.run(["T5"]))
    record = records[0]
    assert record["output"] == golden("T5")
    assert record["calls"] == 6
    assert "summarise_findings(<10 findings>)" in record["call_list"]


def test_sequential_arm_T4_makes_one_crop_per_ground_opening():
    arm = sequential.SequentialArm(common.SERVER_SCRIPT)
    records = asyncio.run(arm.run(["T4"]))
    record = records[0]
    assert record["output"] == golden("T4")
    assert record["calls"] == 14
    assert record["call_list"].count("get_crop(") == 9


def test_aggregate_sensitivity_row_matches_the_golden():
    arm = sequential.SequentialArm(common.SERVER_SCRIPT)
    record = asyncio.run(arm.run_aggregate_sensitivity("T5"))
    assert record["output"] == golden("T5")
    assert record["calls"] == 3

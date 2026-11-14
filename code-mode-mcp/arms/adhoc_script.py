#!/usr/bin/env python3
"""Ad-hoc script arm - ONE ordinary Python script that imports the spike
server module directly and does the same work the other two arms do.

This is the "the model just writes a script" baseline: no MCP protocol, no
sandbox, no context plumbing - the script calls the server functions in
process, composes the answer, and prints it.

The composition itself (grouping / counting / range arithmetic) is the same
agent-side code the Sequential arm uses (``composition.py``); that is the
control: the only thing this arm changes relative to the Sequential arm is HOW
the tool results are obtained (direct import instead of the MCP transport) and
HOW the answer reaches the agent (the script's output instead of a chain of
intermediate results in the context).

Usage:  python adhoc_script.py <report.json>
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import composition  # noqa: E402
import workload  # noqa: E402

SERVER_DIR = os.environ.get("MATCHLINE_SERVER_DIR", "/home/hatch/workspace/mka-phase0/route-b/arm-b/server")
SERVER_SCRIPT = os.path.join(SERVER_DIR, "matchline_mcp_server.py")

ELEVATIONS = workload.ELEVATIONS


def load_server():
    spec = importlib.util.spec_from_file_location("matchline_mcp_server", SERVER_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def nbytes(text: str) -> int:
    return len(text.encode("utf-8"))


def run_task(server, task_id: str) -> dict:
    """One task: call the tools (pinned plan), compose, measure."""
    texts = []
    calls = []
    elevation_data = {}
    crop_results = []
    summary = None

    start = time.perf_counter()

    # list_sheets() once, then one extract per elevation the task needs.
    texts.append(server.list_sheets())
    calls.append("list_sheets()")
    for sheet in workload.TASKS_BY_ID[task_id]["elevations"]:
        text = server.extract_elevation_openings(sheet)
        texts.append(text)
        calls.append("extract_elevation_openings(%s)" % sheet)
        elevation_data[sheet] = json.loads(text)

    if workload.TASKS_BY_ID[task_id]["needs_crops"]:
        for req in workload.crop_requests(elevation_data):
            text = server.get_crop(req["sheet"], req["bbox_px"][0], req["bbox_px"][1],
                                   req["bbox_px"][2], req["bbox_px"][3], req["label"])
            texts.append(text)
            calls.append("get_crop(%s,%s)" % (req["sheet"], req["label"]))
            crop_results.append(json.loads(text))

    if workload.TASKS_BY_ID[task_id]["needs_summary"]:
        text = server.summarise_findings(json.dumps(workload.FINDINGS))
        texts.append(text)
        calls.append("summarise_findings(<10 findings>)")
        summary = json.loads(text)

    if task_id == "T1":
        produced = composition.compose_T1(elevation_data)
    elif task_id == "T2":
        produced = composition.compose_T2(elevation_data)
    elif task_id == "T3":
        produced = composition.compose_T3(elevation_data)
    elif task_id == "T4":
        produced = composition.compose_T4(elevation_data, crop_results)
    else:
        produced = composition.compose_T5(elevation_data, summary)

    wall = time.perf_counter() - start
    bytes_returned = sum(nbytes(t) for t in texts)
    return {
        "task_id": task_id,
        "arm": "ad-hoc",
        "calls": 1,
        "host_calls": len(calls),
        "call_list": ", ".join(calls),
        "bytes_returned": bytes_returned,
        "context_bytes": nbytes(json.dumps(produced, sort_keys=True, separators=(",", ":"))),
        "wall_time_s": wall,
        "output": produced,
    }


def main(argv):
    out_path = argv[1]
    setup_start = time.perf_counter()
    server = load_server()
    setup = time.perf_counter() - setup_start
    records = [run_task(server, task_id) for task_id in workload.TASK_IDS]
    report = {"arm": "ad-hoc", "setup_seconds": setup, "records": records}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, sort_keys=True)
    print("ad-hoc arm wrote %s (%d tasks)" % (out_path, len(records)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

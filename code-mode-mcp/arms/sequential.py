"""Sequential MCP arm - a NEW MCP client, written inside code-mode-mcp/.

Modelled on the read-only reference client
``/home/hatch/workspace/mka-phase0/work/test_mcp_client.py`` (never edited):
the same stdio transport, the same ``ClientSession`` handshake, the same
``call_tool`` + ``content[0].text`` read-out.

The pinned call plan (issue #50 brief):

  * ``list_sheets()`` exactly once,
  * then ``extract_elevation_openings(sheet)`` exactly once per elevation the
    task needs,
  * plus the task's own extra calls (get_crop for T4, summarise_findings for
    T5),
  * ``extract_all_elevations()`` is NOT used in the Sequential arm proper; it
    appears only in the separately reported sensitivity row.

Byte accounting: every tool result that the client reads is a result that
would enter the agent's context, so
``context_bytes = sum over ALL intermediate results`` and
``bytes_returned`` is the same sum.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# The MCP client logs one INFO line per request; silence it so the
# measurement output stays readable.
logging.getLogger("mcp").setLevel(logging.WARNING)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import composition  # noqa: E402
import workload  # noqa: E402
from common import nbytes  # noqa: E402

ARM_NAME = "sequential"


class SequentialArm:
    """Drives the real MCP server over stdio, one persistent session."""

    def __init__(self, server_script: str):
        self.server_script = server_script
        self.records = []
        # The MCP server logs its request trace to stderr; silence it so the
        # measurement output stays readable.
        self._errlog = open(os.devnull, "w")

    def _params(self):
        return StdioServerParameters(command=sys.executable, args=[self.server_script],
                                     errlog=self._errlog)

    # -- low level ---------------------------------------------------------
    async def _call(self, session, tool: str, args: dict) -> str:
        result = await session.call_tool(tool, args)
        if getattr(result, "isError", False):
            raise RuntimeError("MCP tool %s failed: %s" % (tool, result.content))
        return result.content[0].text

    async def _run_plan(self, session, plan, use_aggregate: bool = False) -> dict:
        """Run a pinned call plan, collecting every intermediate result."""
        texts = []
        call_list = []
        elevation_data = {}
        crop_results = []
        summary = None

        for tool, args in plan:
            text = await self._call(session, tool, args)
            texts.append(text)
            call_list.append((tool, args))
            if tool == "extract_elevation_openings":
                elevation_data[args["sheet"]] = json.loads(text)
            elif tool == "extract_all_elevations":
                elevation_data.update(json.loads(text))
            elif tool == "get_crop":
                crop_results.append(json.loads(text))
            elif tool == "summarise_findings":
                summary = json.loads(text)

        return {
            "texts": texts,
            "call_list": call_list,
            "elevation_data": elevation_data,
            "crop_results": crop_results,
            "summary": summary,
        }

    @staticmethod
    def _compose(task_id: str, run: dict):
        data = run["elevation_data"]
        if task_id == "T1":
            return composition.compose_T1(data)
        if task_id == "T2":
            return composition.compose_T2(data)
        if task_id == "T3":
            return composition.compose_T3(data)
        if task_id == "T4":
            return composition.compose_T4(data, run["crop_results"])
        if task_id == "T5":
            return composition.compose_T5(data, run["summary"])
        raise ValueError("unknown task %r" % task_id)

    # -- public ------------------------------------------------------------
    async def run(self, task_ids) -> list:
        params = self._params()
        setup_start = time.perf_counter()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                setup = time.perf_counter() - setup_start
                for task_id in task_ids:
                    self.records.append(await self._task(session, task_id))
        self.setup_seconds = setup
        return self.records

    async def _task(self, session, task_id: str) -> dict:
        # The plan needs the extraction results (T4's crop bboxes come out of
        # them), so the plan is completed after the extraction calls; the
        # resulting call ORDER is identical to the pinned plan.
        start = time.perf_counter()
        run = await self._run_plan(session, workload.extraction_calls(task_id))
        if workload.TASKS_BY_ID[task_id]["needs_crops"]:
            for req in workload.crop_requests(run["elevation_data"]):
                text = await self._call(session, "get_crop", {
                    "sheet": req["sheet"],
                    "x0": req["bbox_px"][0], "y0": req["bbox_px"][1],
                    "x1": req["bbox_px"][2], "y1": req["bbox_px"][3],
                    "label": req["label"],
                })
                run["texts"].append(text)
                run["call_list"].append(("get_crop", {
                    "sheet": req["sheet"], "label": req["label"]}))
                run["crop_results"].append(json.loads(text))
        if workload.TASKS_BY_ID[task_id]["needs_summary"]:
            text = await self._call(session, "summarise_findings", {
                "findings_json": json.dumps(workload.FINDINGS)})
            run["texts"].append(text)
            run["call_list"].append(("summarise_findings", {"findings_json": "<10 findings>"}))
            run["summary"] = json.loads(text)

        produced = self._compose(task_id, run)
        wall = time.perf_counter() - start

        bytes_returned = sum(nbytes(t) for t in run["texts"])
        return {
            "task_id": task_id,
            "arm": ARM_NAME,
            "calls": len(run["call_list"]),
            "host_calls": len(run["call_list"]),
            "call_list": workload.describe_calls(run["call_list"]),
            "bytes_returned": bytes_returned,
            "context_bytes": bytes_returned,
            "wall_time_s": wall,
            "output": produced,
        }

    async def run_aggregate_sensitivity(self, task_id: str) -> dict:
        """The separately reported sensitivity row: the composite task using
        the server's aggregate extract_all_elevations() call."""
        params = self._params()
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                start = time.perf_counter()
                run = await self._run_plan(session, workload.aggregate_call_plan(task_id))
                produced = self._compose(task_id, run)
                wall = time.perf_counter() - start
        bytes_returned = sum(nbytes(t) for t in run["texts"])
        return {
            "task_id": task_id,
            "arm": "sequential-aggregate",
            "calls": len(run["call_list"]),
            "host_calls": len(run["call_list"]),
            "call_list": workload.describe_calls(run["call_list"]),
            "bytes_returned": bytes_returned,
            "context_bytes": bytes_returned,
            "wall_time_s": wall,
            "output": produced,
        }


def run_arm(server_script: str, task_ids) -> tuple:
    """Convenience wrapper: run the arm and return (records, setup seconds)."""
    arm = SequentialArm(server_script)
    records = asyncio.run(arm.run(task_ids))
    return records, getattr(arm, "setup_seconds", None)

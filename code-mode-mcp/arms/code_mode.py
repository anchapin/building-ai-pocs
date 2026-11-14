"""Code-mode arm - the same work done by a program inside Monty.

Host functions are the spike server's own five functions with their REAL
signatures (imported from the read-only server module, never edited):

    list_sheets() -> str
    extract_elevation_openings(sheet: str) -> str
    extract_all_elevations() -> str
    get_crop(sheet: str, x0: int, y0: int, x1: int, y1: int, label: str) -> str
    summarise_findings(findings_json: str) -> str

Byte accounting (exactly as the brief defines it):

  * bytes_returned  = sum over ALL tool-result texts the program received
    (the bytes that crossed the tool boundary),
  * context_bytes   = the UTF-8 length of the FINAL returned string only -
    in code mode the intermediate results never reach the model's context.

Call counting: the agent-facing call count is 1 (one code execution); the
number of host calls the program made is reported separately as
``host_calls`` so the underlying work stays visible.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import nbytes  # noqa: E402

ARM_NAME = "code-mode"

#: Modules probed inside the Monty sandbox, so that the report can state what
#: the subset actually blocked instead of discovering it mid-run.
SUBSET_PROBE_MODULES = ["json", "re", "math", "statistics", "collections",
                         "itertools", "functools", "decimal", "string"]

HOST_FUNCTION_NAMES = [
    "list_sheets",
    "extract_elevation_openings",
    "extract_all_elevations",
    "get_crop",
    "summarise_findings",
]


class CodeModeArm:
    """Runs one program per task in a Monty session (one pool, warm workers)."""

    def __init__(self, server_module):
        self.server = server_module
        self.records = []
        self.errors = []

    def _host_functions(self, counter: dict):
        lookup = {}
        for name in HOST_FUNCTION_NAMES:
            fn = getattr(self.server, name)

            def make(fn):
                def wrapper(*args, **kwargs):
                    result = fn(*args, **kwargs)
                    counter["calls"].append(fn.__name__)
                    counter["bytes"] += nbytes(result)
                    return result
                return wrapper
            lookup[name] = make(fn)
        return lookup

    def run(self, programs: dict) -> list:
        from pydantic_monty import Monty
        with Monty() as pool:
            self.setup_seconds = 0.0
            for task_id, program in programs.items():
                self.records.append(self._run_one(pool, task_id, program))
        return self.records

    def run_one(self, label: str, program: str) -> dict:
        """Run a single program in its own pool (used for the aggregate
        sensitivity variant of the composite task)."""
        from pydantic_monty import Monty
        with Monty() as pool:
            return self._run_one(pool, label, program)

    @staticmethod
    def subset_probe() -> dict:
        """Which stdlib modules the Monty sandbox actually offers.

        Recorded so the report states the subset limits that were hit rather
        than discovering them in the middle of a run.  (The programs in
        monty_programs.py need only ``json``; ``statistics`` is NOT available
        in the sandbox even though the brief lists it as supported.)"""
        from pydantic_monty import Monty
        outcome = {}
        with Monty() as pool:
            with pool.checkout() as session:
                for name in SUBSET_PROBE_MODULES:
                    try:
                        session.feed_run("import %s" % name)
                        outcome[name] = "available"
                    except Exception as exc:
                        outcome[name] = "blocked: %s: %s" % (type(exc).__name__, exc)
        return outcome

    def _run_one(self, pool, task_id: str, program: str) -> dict:
        counter = {"calls": [], "bytes": 0}
        lookup = self._host_functions(counter)
        with pool.checkout() as session:
            start = time.perf_counter()
            try:
                result = session.feed_run(program, external_lookup=lookup)
                error = None
            except Exception as exc:  # MontyRuntimeError, MontyTypingError, ...
                result = None
                error = "%s: %s" % (type(exc).__name__, exc)
                self.errors.append({"task_id": task_id, "error": error})
            wall = time.perf_counter() - start
        if error is not None:
            return {
                "task_id": task_id, "arm": ARM_NAME, "calls": 1,
                "host_calls": len(counter["calls"]), "call_list": "",
                "bytes_returned": counter["bytes"], "context_bytes": 0,
                "wall_time_s": wall, "output": None, "error": error,
            }
        return {
            "task_id": task_id,
            "arm": ARM_NAME,
            "calls": 1,
            "host_calls": len(counter["calls"]),
            "call_list": ", ".join(counter["calls"]),
            "bytes_returned": counter["bytes"],
            "context_bytes": nbytes(result),
            "wall_time_s": wall,
            "output": json.loads(result),
            "error": None,
        }

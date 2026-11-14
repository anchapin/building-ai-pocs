#!/usr/bin/env python3
"""Three-arm measurement runner for issue #50, Phase 0 (code-mode vs
sequential MCP vs ad-hoc script) on the Matchline MCP spike server's real
workload.

    /home/hatch/workspace/fixtrees/bap50-venv/bin/python code-mode-mcp/run_measure.py

It runs, on this machine, over the same frozen tasks:

  * the Sequential arm  - a NEW MCP client (arms/sequential.py) built inside
    code-mode-mcp/, modelled on the read-only reference client
    /home/hatch/workspace/mka-phase0/work/test_mcp_client.py;
  * the Code-mode arm   - programs executed by pydantic-monty 1.3.0 with the
    server's own five functions bound as host functions (arms/code_mode.py,
    arms/monty_programs.py);
  * the Ad-hoc arm      - ONE ordinary Python script importing the server
    module directly (arms/adhoc_script.py);

plus the separately reported sensitivity row: the composite task with the
server's aggregate extract_all_elevations() call.

Every arm's output is checked against the frozen golden JSON; a mismatch is
reported verbatim, never rounded away.  The results are written to
code-mode-mcp/results.json and printed as the results table of REPORT.md.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "arms"))

import code_mode  # noqa: E402
import common  # noqa: E402
import monty_programs  # noqa: E402
import sequential  # noqa: E402
import workload  # noqa: E402

RESULTS_PATH = os.path.join(HERE, "results.json")
ADHOC_REPORT = os.path.join(tempfile.gettempdir(), "cm50_adhoc_report.json")


# --- environment smoke check ----------------------------------------------

def smoke_check() -> dict:
    """The pre-provisioned venv smoke check required before any measurement."""
    out = {"ok": True, "checks": []}
    for name in ("pydantic_monty", "mcp", "cv2", "numpy", "PIL"):
        try:
            __import__(name)
            out["checks"].append("%s: import ok" % name)
        except Exception as exc:
            out["ok"] = False
            out["checks"].append("%s: FAILED %s: %s" % (name, type(exc).__name__, exc))
    try:
        server = workload.load_server()
        sheets = json.loads(server.list_sheets())
        out["checks"].append("server module: list_sheets() -> %d sheets" % len(sheets["sheets"]))
    except Exception as exc:
        out["ok"] = False
        out["checks"].append("server module: FAILED %s: %s" % (type(exc).__name__, exc))
    out["python"] = sys.executable
    out["pydantic_monty_version"] = getattr(__import__("pydantic_monty"), "__version__", "unknown")
    return out


# --- arms ------------------------------------------------------------------

def run_sequential(task_ids):
    arm = sequential.SequentialArm(common.SERVER_SCRIPT)
    records = asyncio_run(arm.run(task_ids))
    return records, getattr(arm, "setup_seconds", 0.0)


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)


def run_adhoc(task_ids):
    cmd = [sys.executable, os.path.join(HERE, "arms", "adhoc_script.py"), ADHOC_REPORT]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("ad-hoc arm failed (%d):\n%s\n%s" % (proc.returncode, proc.stdout, proc.stderr))
    with open(ADHOC_REPORT, encoding="utf-8") as fh:
        return json.load(fh)


def run_code_mode():
    server = workload.load_server()
    arm = code_mode.CodeModeArm(server)
    records = arm.run(monty_programs.PROGRAMS)
    return records


def combine(runs, label):
    """Merge the repetitions of one arm into one record per task.

    The reported wall time is the MEDIAN of the repetitions (the runs are
    noisy at the 0.1 s level); the correctness gate is applied to EVERY
    repetition, and the outputs must be identical across repetitions.
    """
    import statistics as host_statistics
    merged = []
    for index, record in enumerate(runs[0]):
        times = [r[index]["wall_time_s"] for r in runs]
        outputs = [json.dumps(r[index]["output"], sort_keys=True) for r in runs]
        merged.append({
            "task_id": record["task_id"],
            "arm": record["arm"],
            "calls": record["calls"],
            "host_calls": record["host_calls"],
            "call_list": record["call_list"],
            "bytes_returned": record["bytes_returned"],
            "context_bytes": record["context_bytes"],
            "wall_time_s": host_statistics.median(times),
            "wall_times_s": times,
            "repeats": len(times),
            "output": record["output"],
            "error": record.get("error"),
            "outputs_stable": len(set(outputs)) == 1,
        })
    return merged


# --- table -----------------------------------------------------------------

def fmt(value) -> str:
    if isinstance(value, float):
        return "%.3f" % value
    return str(value)


def print_table(records) -> None:
    header = ["Task", "Arm", "Calls (agent)", "Host calls", "Bytes returned",
              "Context bytes", "Wall s", "Correct"]
    print("| " + " | ".join(header) + " |")
    print("| " + " | ".join("---" for _ in header) + " |")
    for rec in records:
        print("| " + " | ".join([
            rec["task_id"], rec["arm"], str(rec["calls"]), str(rec["host_calls"]),
            str(rec["bytes_returned"]), str(rec["context_bytes"]),
            fmt(rec["wall_time_s"]), rec["correctness"],
        ]) + " |")


def print_call_lists(records) -> None:
    print()
    print("Exact call lists (per task, per arm):")
    for rec in records:
        print("  %s / %s: %s" % (rec["task_id"], rec["arm"], rec["call_list"]))


# --- verdict ---------------------------------------------------------------

def verdict(records) -> dict:
    """The pre-registered bars of issue #50, applied to the measured numbers.

    Precedence (documented in REPORT.md): environment-blocked > Kill >
    Proceed > Park > Conditional.

    * Proceed: on the composite task (T5) code-mode cuts context bytes by
      >= 70 % AND tool calls by >= 80 % versus sequential, all five tasks are
      expressible in the Monty subset and every output is exact.
    * Kill: context saving < 40 % or call saving < 50 % on the composite, or
      >= 2 of the 5 tasks inexpressible, or a correctness mismatch traced to
      Monty semantics.
    * Park: code-mode wins on the numbers but the ad-hoc arm is within ~10 %
      on every measure (call count, context bytes, wall time) - the
      deliverable is then the prompt-steer recommendation.
    * Otherwise: "Conditional - bars not met".
    """
    def find(task_id, arm):
        for rec in records:
            if rec["task_id"] == task_id and rec["arm"] == arm:
                return rec
        return None

    seq = find("T5", "sequential")
    code = find("T5", "code-mode")
    adhoc = find("T5", "ad-hoc")

    context_saving = 1.0 - (code["context_bytes"] / seq["context_bytes"])
    call_saving = 1.0 - (code["calls"] / seq["calls"])

    inexpressible = [r["task_id"] for r in records
                     if r["arm"] == "code-mode" and r.get("error")]
    code_mismatches = [r["task_id"] for r in records
                       if r["arm"] == "code-mode" and r["correctness"] != "exact"]

    # ad-hoc vs code-mode, composite task, every measure
    measures = {
        "calls": (code["calls"], adhoc["calls"]),
        "context_bytes": (code["context_bytes"], adhoc["context_bytes"]),
        "wall_time_s": (code["wall_time_s"], adhoc["wall_time_s"]),
    }
    adhoc_within_10 = {}
    for name, (c, a) in measures.items():
        base = abs(c) if c else 1.0
        adhoc_within_10[name] = abs(a - c) / base <= 0.10
    adhoc_close = all(adhoc_within_10.values())

    bars_met = (context_saving >= 0.70 and call_saving >= 0.80
                and not inexpressible and not code_mismatches)
    kill_context = context_saving < 0.40
    kill_calls = call_saving < 0.50
    kill_inexpressible = len(inexpressible) >= 2
    kill_mismatch = bool(code_mismatches)

    if kill_context or kill_calls or kill_inexpressible or kill_mismatch:
        label = "Kill"
        why = ("context saving %.1f %% / call saving %.1f %%; inexpressible %d; "
               "mismatches %s" % (context_saving * 100, call_saving * 100,
                                  len(inexpressible), code_mismatches))
    elif bars_met and adhoc_close:
        label = "Park"
        why = ("code-mode beats sequential (context %.1f %%, calls %.1f %%) but the "
               "ad-hoc arm is within 10 %% on every measure" %
               (context_saving * 100, call_saving * 100))
    elif bars_met:
        label = "Proceed"
        why = ("context saving %.1f %% (>= 70 %%) and call saving %.1f %% (>= 80 %%) "
               "on T5" % (context_saving * 100, call_saving * 100))
    else:
        label = "Conditional - bars not met"
        why = ("context saving %.1f %%, call saving %.1f %%; inexpressible %d; "
               "mismatches %s" % (context_saving * 100, call_saving * 100,
                                  len(inexpressible), code_mismatches))

    return {
        "label": label,
        "why": why,
        "context_saving_T5": context_saving,
        "call_saving_T5": call_saving,
        "inexpressible_tasks": inexpressible,
        "code_mode_mismatches": code_mismatches,
        "adhoc_within_10pct": adhoc_within_10,
        "adhoc_close_to_code_mode": adhoc_close,
        "bars_met": bars_met,
    }


# --- main ------------------------------------------------------------------

def main() -> int:
    overall_start = time.perf_counter()
    smoke = smoke_check()
    print("== environment smoke check ==")
    for line in smoke["checks"]:
        print("  " + line)
    print("  python: %s" % smoke["python"])
    print("  pydantic_monty: %s" % smoke["pydantic_monty_version"])
    if not smoke["ok"]:
        print("ENVIRONMENT BLOCKED - verdict would be 'Inconclusive - environment-blocked'")
        return 2

    task_ids = workload.TASK_IDS
    repeats = int(os.environ.get("CM50_REPEATS", "3"))

    print("\n== sequential arm (new MCP client inside code-mode-mcp/) ==")
    seq_runs = []
    seq_setups = []
    for _ in range(repeats):
        records, setup = run_sequential(task_ids)
        seq_runs.append(records)
        seq_setups.append(setup)
    seq_records = combine(seq_runs, "sequential")
    print("  session setup: %s s" % ", ".join("%.3f" % s for s in seq_setups))

    print("\n== code-mode arm (pydantic-monty) ==")
    cm_runs = []
    cm_errors = []
    for _ in range(repeats):
        server = workload.load_server()
        cm_arm = code_mode.CodeModeArm(server)
        cm_runs.append(cm_arm.run(monty_programs.PROGRAMS))
        cm_errors.extend(cm_arm.errors)
    cm_records = combine(cm_runs, "code-mode")

    print("\n== code-mode arm, aggregate sensitivity variant of T5 ==")
    server = workload.load_server()
    cm_arm = code_mode.CodeModeArm(server)
    cm_agg_runs = []
    for _ in range(repeats):
        cm_agg_runs.append([cm_arm.run_one("T5-aggregate", monty_programs.T5_AGGREGATE_PROGRAM)])
    cm_agg = combine(cm_agg_runs, "code-mode-aggregate")

    print("\n== ad-hoc arm (one ordinary script) ==")
    adhoc_runs = []
    adhoc_setups = []
    for _ in range(repeats):
        report = run_adhoc(task_ids)
        adhoc_runs.append(report["records"])
        adhoc_setups.append(report["setup_seconds"])
    adhoc_records = combine(adhoc_runs, "ad-hoc")
    print("  script setup: %s s" % ", ".join("%.3f" % s for s in adhoc_setups))

    print("\n== sequential arm, aggregate sensitivity row for T5 ==")
    seq_agg_runs = []
    for _ in range(repeats):
        seq_agg_runs.append([asyncio_run(
            sequential.SequentialArm(common.SERVER_SCRIPT).run_aggregate_sensitivity("T5"))])
    seq_agg = combine(seq_agg_runs, "sequential-aggregate")

    records = []
    records.extend(seq_records)
    records.extend(cm_records)
    records.extend(adhoc_records)

    # correctness gate
    for rec in records:
        if rec.get("output") is None:
            rec["correctness"] = "NO OUTPUT"
            rec["mismatch"] = rec.get("error", "")
            continue
        if common.matches_golden(rec["task_id"], rec["output"]):
            rec["correctness"] = "exact"
            rec["mismatch"] = ""
        else:
            rec["correctness"] = "MISMATCH"
            rec["mismatch"] = common.diff_golden(rec["task_id"], rec["output"])

    print("\n== results table ==")
    print_table(records)
    for rec in records:
        if not rec.get("outputs_stable", True):
            print("FINDING: %s / %s produced DIFFERENT outputs across repetitions"
                  % (rec["task_id"], rec["arm"]))
        if rec.get("mismatch"):
            print("FINDING: %s / %s does not match the frozen golden:\n%s"
                  % (rec["task_id"], rec["arm"], rec["mismatch"]))

    print("\n== sensitivity row (aggregate extract_all_elevations) ==")
    sensitivity = []
    for rec in (seq_agg[0], cm_agg[0]):
        rec["correctness"] = "exact" if common.matches_golden("T5", rec["output"]) else "MISMATCH"
        rec["mismatch"] = "" if rec["correctness"] == "exact" else common.diff_golden("T5", rec["output"])
        sensitivity.append(rec)
        print("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
            rec["task_id"], rec["arm"], rec["calls"], rec["host_calls"],
            rec["bytes_returned"], rec["context_bytes"],
            fmt(rec["wall_time_s"]), rec["correctness"]))
        print("    calls: %s" % rec["call_list"])

    print_call_lists(records)

    v = verdict(records)
    print("\n== verdict ==")
    print("  label: %s" % v["label"])
    print("  why:   %s" % v["why"])
    print("  context saving on T5: %.1f %%" % (v["context_saving_T5"] * 100))
    print("  call saving on T5:    %.1f %%" % (v["call_saving_T5"] * 100))
    print("  ad-hoc within 10%% of code-mode: %s" % v["adhoc_within_10pct"])

    out = {
        "environment": smoke,
        "repeats": repeats,
        "records": records,
        "sensitivity": sensitivity,
        "verdict": v,
        "setup_seconds": {"sequential": seq_setups, "ad-hoc": adhoc_setups},
        "total_wall_time_s": time.perf_counter() - overall_start,
        "monty_errors": cm_errors,
        "monty_subset_probe": code_mode.CodeModeArm.subset_probe(),
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True, default=str)
    print("\nwrote %s" % RESULTS_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())

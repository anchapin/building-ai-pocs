# code-mode-mcp — Phase 0 measurement (building-ai-pocs issue #50)

Does **code mode** (the model writes a program that calls the tools
programmatically) beat **sequential MCP tool calling** on the Matchline MCP
spike server's real workload — and does it beat the **ad-hoc script** baseline
(an ordinary Python script that imports the server module directly)?

This folder is the whole Phase 0 deliverable: a frozen five-task workload with
golden outputs, three measurement arms, the results table, the tests and
`REPORT.md` (verdict + claims).

Nothing outside this folder is changed: the spike server
(`/home/hatch/workspace/mka-phase0/route-b/arm-b/server/matchline_mcp_server.py`)
and the reference MCP client
(`/home/hatch/workspace/mka-phase0/work/test_mcp_client.py`) are read/called,
never edited. The only writes outside the folder are the evidence-crop PNGs
that the server's own `get_crop` tool writes into the server's crops directory.

## Reproduce

```sh
# 1. the test suite (28 tests)
/home/hatch/workspace/fixtrees/bap50-venv/bin/python -m pytest code-mode-mcp/ -q

# 2. the three-arm measurement (prints the results table and the verdict,
#    writes code-mode-mcp/results.json)
/home/hatch/workspace/fixtrees/bap50-venv/bin/python code-mode-mcp/run_measure.py
```

Both commands use the pre-provisioned interpreter
`/home/hatch/workspace/fixtrees/bap50-venv/bin/python` (pydantic-monty 1.3.0,
mcp 1.30.0, opencv-python-headless, numpy, Pillow). Nothing is installed.

## What is here

| Path | What it is |
| --- | --- |
| `workload.py` | **The frozen workload**: the five canonical tasks, the pinned per-task call plans, the reference implementations that define the golden outputs, and the `freeze` mode that wrote the golden JSON and printed the freeze hashes. |
| `golden/` | The five frozen golden JSON outputs plus `golden_manifest.json` (the sha256 hashes that evidence the freeze). |
| `arms/sequential.py` | The Sequential arm: a **new** MCP client (stdio transport, `ClientSession`), modelled on the read-only reference client. Pinned plan: `list_sheets()` once, then `extract_elevation_openings(sheet)` once per elevation the task needs. |
| `arms/monty_programs.py` | The five code-mode programs, written for the Monty subset (no third-party imports, no classes, no generators, no `del`). |
| `arms/code_mode.py` | The Code-mode arm: runs those programs under pydantic-monty with the server's own five functions bound as host functions (real signatures). |
| `arms/adhoc_script.py` | The Ad-hoc arm: one ordinary Python script that imports the server module directly. |
| `arms/composition.py` | The agent-side composition (the deterministic stand-in for the agent's reasoning — no LLM is called anywhere in this POC). An implementation independent of the frozen reference. |
| `arms/common.py` | Byte accounting, golden loading, the correctness gate. |
| `run_measure.py` | The measurement runner: runs the three arms over the same tasks on this machine, checks every output against the golden, prints the results table and the verdict, writes `results.json`. |
| `tests/` | The pytest suite (freeze integrity, composition vs golden, Monty programs vs golden, sequential arm end-to-end). |
| `REPORT.md` | The verdict, the measurement, the claims. |

## The frozen tasks

| Task | Question | Sheets used |
| --- | --- | --- |
| T1 | elevation × floor-band opening-count matrix | all four elevations |
| T2 | width-consistency check: group openings by rounded width across elevations, flag groups whose sill/head disagree by > 0.05 m | all four elevations |
| T3 | per-band sill/head range table across all elevations | all four elevations |
| T4 | evidence crop for every Ground-band opening on all four elevations | all four elevations |
| T5 | composite "audit prep": T1 + T3 + `summarise_findings()` on a fixed findings list | all four elevations |

## Byte and call accounting (exactly as the brief defines it)

* **bytes returned** = the UTF-8 length of the tool-result text as returned.
* **Sequential context bytes** = the sum over **all** intermediate results.
* **Code-mode context bytes** = the **final returned string only**.
* **Calls (agent)** = the calls the agent itself makes: N tool calls for the
  Sequential arm, **1** (one code execution) for the Code-mode and Ad-hoc arms.
  The number of host calls the program made is reported separately as
  *host calls*, so the underlying work stays visible.
* Wall time = the task's own tool calls plus its composition, median of 3
  repetitions (one-off session/script setup is reported separately).

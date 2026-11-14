# Code-mode (programmatic tool calling) for the Matchline MCP server — Phase 0 report (issue #50)

**Verdict: Park**

Code-mode beats sequential MCP tool calling decisively on the pre-registered
bars — and the ad-hoc script baseline ties code-mode on every deterministic
measure. The honest deliverable is therefore the Park deliverable from the
issue: a one-line prompt steer for the Route B prompt ("compose extraction
calls in a local script"), not a new `run_code` tool. Phase 1 (adding
`run_code` to the spike server) stays gated on Alex's separate tap and is
not justified by these numbers.

Completion note: the worker run (balanced, MiniMax-M2.7, 60/60 steps,
61,405 tokens out, grade 83) built the workload, all three arms, the tests
and the first measurement run, and hit the step cap before writing this
report. The supervisor independently re-ran the full measurement
(`run_measure.py`, exit 0) and the test suite (28 passed) at collection and
wrote this report from the two runs' `results.json` outputs; every number
below is from one of those two runs, labelled as such.

## The bars, and what was measured

Pre-registered in issue #50 §Phase 0:

- **Proceed**: code-mode cuts context bytes ≥70% AND tool-call count ≥80%
  vs sequential on the composite task (T5), all five tasks expressible in
  the Monty subset, outputs exact.
- **Kill**: context saving <40% or call saving <50% on T5, or ≥2 of 5 tasks
  inexpressible, or any correctness mismatch traced to Monty semantics.
- **Park**: code-mode wins on the numbers but the ad-hoc arm is within ~10%
  on every measure.

Measured on T5 (audit-prep composite), identical in both runs:

- Context saving **90.1%** (13,672 → 1,354 bytes) — Proceed bar met.
- Call saving **83.3%** (6 → 1 calls) — Proceed bar met.
- All 15 arm/task outputs **exact** vs the frozen golden JSON; zero
  Monty-semantics mismatches; zero inexpressible tasks.

Against the ad-hoc arm, per task, in both runs: calls **1 = 1** and context
bytes **identical** (402 / 8,140 / 563 / 2,100 / 1,354) — the ad-hoc script
returns the same final result and nothing else enters context, exactly as
code-mode does. The only measure that ever differed is wall time, and it is
not stable: run 1 (worker) had ad-hoc outside 10% on wall time (T5: ad-hoc
1.165 s vs code-mode 1.702 s — the script was *faster*), run 2 (supervisor
re-run) had it inside 10% (1.196 s vs 1.215 s). A verdict that flips on a
~1-second wall-time comparison across two runs of the same code is not
evidence of a tool's marginal value; on the deterministic measures the
marginal value over "just write a script" is zero. **Park.**

## Results table (run 2, supervisor re-run; run 1 agreed on every calls/bytes/correctness cell)

| task | arm | calls | context bytes | wall s (run 2) | wall s (run 1) | correctness |
|---|---|---|---|---|---|---|
| T1 count matrix | sequential | 5 | 13,140 | 1.498 | 1.559 | exact |
| T1 | code-mode | 1 | 402 | 1.244 | 1.299 | exact |
| T1 | ad-hoc | 1 | 402 | 1.390 | 1.487 | exact |
| T2 width consistency | sequential | 5 | 13,140 | 1.258 | 1.366 | exact |
| T2 | code-mode | 1 | 8,140 | 1.247 | 1.298 | exact |
| T2 | ad-hoc | 1 | 8,140 | 1.209 | 1.369 | exact |
| T3 band ranges | sequential | 5 | 13,140 | 1.245 | 1.254 | exact |
| T3 | code-mode | 1 | 563 | 1.240 | 1.274 | exact |
| T3 | ad-hoc | 1 | 563 | 1.219 | 1.255 | exact |
| T4 ground-band crops | sequential | 14 | 14,673 | 3.399 | 3.617 | exact |
| T4 | code-mode | 1 | 2,100 | 3.550 | 3.784 | exact |
| T4 | ad-hoc | 1 | 2,100 | 3.367 | 3.230 | exact |
| T5 audit prep (composite) | sequential | 6 | 13,672 | 1.222 | 1.337 | exact |
| T5 | code-mode | 1 | 1,354 | 1.215 | 1.702 | exact |
| T5 | ad-hoc | 1 | 1,354 | 1.196 | 1.165 | exact |
| T5 sensitivity | sequential via `extract_all_elevations` | 3 | 14,475 | 1.629 | 1.418 | exact |

Sequential call plan (pinned in the brief): `list_sheets` once, then
`extract_elevation_openings(sheet)` per elevation; T4 adds one `get_crop`
per Ground-band opening; T5 adds `summarise_findings`. The sensitivity row
uses the server's aggregate tool, as the brief required it reported
separately: even against the aggregate baseline, code-mode's context bytes
are 1,354 vs 14,475 (the aggregate returns everything; code-mode returns
only the composed result).

## Environment and freeze

- Interpreter (pre-provisioned by the supervisor after the Goldfish review
  found worker-side package indexes unreachable): 
  `/home/hatch/workspace/fixtrees/bap50-venv/bin/python` — pydantic-monty
  1.3.0 (+ client/runtime 1.3.0), mcp 1.30.0, opencv-python-headless,
  numpy, Pillow. Smoke checks in `results.json`: all imports ok; the server
  module's `list_sheets()` returns 11 sheets. Install was ~46 s and ~319 MB
  total venv, on the workspace disk (TMPDIR there, per the gate-lift note).
- Monty API as installed: `pydantic_monty.Monty` / external (OS) functions
  for the host functions; host functions return str JSON exactly as the MCP
  tools do; `summarise_findings` is called with a JSON string.
- Monty subset probe (corrects the issue's desk-check): `json`, `re`,
  `math`, `collections`, `functools`, `itertools` are available inside
  Monty 1.3.0; **`statistics`, `decimal` and `string` are blocked**
  (ModuleNotFoundError). None of the five canonical tasks needed a blocked
  module; the reference implementations were written against the available
  subset. The issue's premise that `statistics` is supported does not hold
  for the pinned version.
- Freeze: workload frozen before any timing — `workload.py` sha256
  `f668a5a0aeb7812171a91bc1b2a4fd8169e6885e9bc667f38e26f2ee27eaefcf` and
  per-task golden sha256s are recorded in `golden/golden_manifest.json`.
- Tests: `python3 -m pytest code-mode-mcp/ -q` → **28 passed** (supervisor
  re-run with the venv interpreter).
- Task (4)'s crops were written by the server's own `get_crop` into its
  existing crops directory, as briefed; no server code was changed.

## What Park means here

- Do NOT build the Phase 1 `run_code` tool on this evidence. The pattern
  (compose calls locally, return only the result) is validated; the
  sandboxed tool's marginal value over the ad-hoc route the Route B agent
  already has is not — it ties on calls and bytes and its wall-time edge
  is run-to-run noise.
- The deliverable is the prompt steer: in the Route B prompt, instruct the
  agent to compose extraction calls in a local script (importing the server
  module or driving it via an MCP client) instead of reasoning over
  intermediate JSON in context. Where the steer cannot apply — MCP clients
  with no local code execution — the capability argument for `run_code`
  (premise 4a/4c of the issue) remains open and untested by this Phase 0;
  that is a different spike, not a Phase 1 justification.
- Revisit only if a workload appears whose intermediate results are much
  larger than this server's ~13 KB per pass (premise 3's modest ceiling is
  the binding constraint), or if a no-local-execution client becomes a real
  consumer.

## Claims

- [observed] On the composite task T5, code-mode cut context bytes by 90.1% (13,672 → 1,354) and tool calls by 83.3% (6 → 1) versus the pinned sequential arm — source: `code-mode-mcp/results.json` verdict block, reproduced identically (calls/bytes/correctness) by two independent `run_measure.py` executions.
- [observed] All 15 arm/task outputs matched the frozen golden JSON exactly in both runs, with zero Monty-semantics mismatches and zero inexpressible tasks — source: `code-mode-mcp/results.json` records (correctness: exact ×15) and `golden/golden_manifest.json`.
- [observed] The ad-hoc script arm tied code-mode on calls (1 per task) and context bytes (identical per task) in both runs; only wall time differed, and its within-10% status flipped between runs (run 1 T5: ad-hoc 1.165 s vs code-mode 1.702 s; run 2: 1.196 s vs 1.215 s) — source: the two `results.json` verdict blocks quoted in §"The bars".
- [observed] Inside pydantic-monty 1.3.0, `statistics`, `decimal` and `string` raise ModuleNotFoundError while `json`, `re`, `math`, `collections`, `functools`, `itertools` import — source: `code-mode-mcp/results.json` monty_subset_probe.
- [decision] Verdict is Park, per the issue's pre-registered Park rule: code-mode wins against sequential, but the ad-hoc arm is within ~10% on every deterministic measure, so the deliverable is the prompt steer, not a `run_code` tool; Phase 1 remains gated on Alex's separate tap.

# POC #43 — SMT contract checking (CrossHair / deal) on a Python solver slice

**Verdict: Conditional (env-blocked)** (slice 1, 2026-11-13). The contract
approach paid for itself on this slice — contract-driven search found a real
upstream bug the example tests missed — but the issue's gate cannot be called
Go: the SMT leg itself (CrossHair/Z3) never ran, because the packages could
not be installed in the worker sandbox (PyPI unreachable, no cached wheels).
Supervisor note: this REPORT.md and README.md were completed by the
supervisor at collection — the worker hit its step cap after finishing the
code, tests, and search tools; all numbers below were re-run and verified by
the supervisor.

## Premise

- The slice is pure Python (stdlib only, plain floats, no I/O, no numpy, no
  dynamic dispatch): 8 functions copied or mechanically adapted from
  `drawing-verifier/checker.py` — `dist`, `polygon_area`, `glazed_area`,
  `opening_span`, `overlap_flag`, `overlap_length`, `true_overlap` (new
  ground-truth helper), `wwr`. Full attribution table in `geometry_slice.py`.
- Contracts live in `contracts.py` (285 lines including the contract
  definitions and domain notes); example + property tests total 255 lines.

## What ran instead of CrossHair

`tools/run_crosshair.sh` records the intended `crosshair check` invocation.
Install attempts failed in the sandbox: `pip install crosshair` →
"Could not find a version that satisfies the requirement crosshair (from
versions: none)"; direct PyPI access fails with SSL errors
(`SSLError: wrong version number`) — the worker sandbox has no working PyPI
route and no cached crosshair/deal/icontract/z3 wheels.

The contracts were therefore exercised two other ways:

1. **Offline bounded grid search** (`tools/contract_search.py`, 21-point
   grid, 0.000–1.000 m at 50 mm steps; total wall time 5.7 s, re-run by the
   supervisor):
   - `overlap_flag`: 2,605 violating inputs of 28,336 in-domain — 1,263
     classified real bug (reachable upstream), 1,342 contract error
     (inputs upstream validation rejects first).
   - `glazed_area`: 4,200 violating inputs, all contract error
     (`head_height <= sill_height` is rejected by upstream `validate_model`
     before the geometry runs — the contract, not the code, was wrong).
   - `dist`, `polygon_area`, `opening_span`, `true_overlap`, `wwr`: clean.
2. **Hypothesis property tests** (`tests/test_contracts_hypothesis.py`)
   independently reproduce the overlap counterexample; the slice suite is
   21 passed, 5 xfailed (the xfails pin the known contract/bug cases).

## The real bug

`tools/repro_upstream_bug.py` (supervisor re-run): two openings with a true
geometric overlap of **0.020 m** — below the 0.05 m tolerance, so no finding
should fire — produce an upstream error finding claiming an overlap of
**9.960 m**. Both the flag and the magnitude are wrong in
`drawing-verifier/checker.py`'s `check_wall_adjacency` overlap test. This is
a candidate follow-up bug issue against the drawing verifier; it is NOT
fixed in this POC (the slice copies upstream behaviour deliberately).

## Gate assessment

- Go requires CrossHair to find a real counterexample or prove the slice
  clean within budget. CrossHair never ran, so Go cannot be claimed —
  even though the substitute search did find a real counterexample.
- No-go (timeouts/state explosion on a toy slice) also cannot be claimed:
  nothing timed out; the blocker was package installation, not the technique.
- Contract cost: ~285 lines of contracts/tools scaffolding vs 255 lines of
  tests on an 8-function slice — too early to judge the maintenance-cost
  leg; the counterexample yield (one real upstream bug, one contract error
  found and corrected) is the positive signal.

## Claims

- [observed] CrossHair/Z3/deal could not be installed in the worker sandbox (pip "from versions: none"; PyPI SSL failures) — source: worker transcript, install commands and outputs, slice 1 run 2026-11-13.
- [observed] The bounded grid search found 1,263 real-bug violations of the `overlap_flag` contract and 4,200 contract-error violations for `glazed_area` — source: `python3 smt-contract-checking/tools/contract_search.py`, re-run by the supervisor at collection (total wall 5.7 s).
- [observed] Upstream `check_wall_adjacency` emits a false-positive error claiming a 9.960 m overlap for a true 0.020 m overlap under a 0.050 m tolerance — source: `python3 smt-contract-checking/tools/repro_upstream_bug.py`, re-run by the supervisor at collection.
- [observed] The slice test suite passes: 21 passed, 5 xfailed — source: `python3 -m pytest smt-contract-checking/ -q`, re-run by the supervisor at collection.
- [unsupported] That CrossHair would find the same counterexamples, or prove the clean functions clean — the SMT leg never ran in this environment.
- [inference] Contract-first checking has positive yield on realistic pure-Python slices in this repo (one real bug + one contract correction on 8 functions), so a re-run in an environment with CrossHair available is worth one more slice before a Go/No-go call.
- [decision] Verdict Conditional (env-blocked): re-run the CrossHair leg where PyPI (or a wheel cache) is available; file the drawing-verifier overlap bug separately.

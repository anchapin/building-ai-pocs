# POC #43 — SMT contract checking (CrossHair / deal) on a Python solver slice

Slice 1. Verdict: **Conditional (env-blocked)** — see REPORT.md.

A small pure-Python geometry slice copied from `drawing-verifier/checker.py`
(see the attribution table in `geometry_slice.py`), with contracts capturing
its real invariants (`contracts.py`), example + Hypothesis property tests
(`tests/`), an offline bounded counterexample search (`tools/contract_search.py`),
and a reproduction of the upstream overlap bug the search found
(`tools/repro_upstream_bug.py`). `tools/run_crosshair.sh` runs the intended
CrossHair check when the package is available; in this run's sandbox PyPI was
unreachable, so CrossHair/Z3 could not be installed and the SMT leg is
untested — the contracts were exercised by the bounded search and Hypothesis
instead.

## Run

```bash
python3 -m pytest smt-contract-checking/ -q          # 21 passed, 5 xfailed
python3 smt-contract-checking/tools/contract_search.py
python3 smt-contract-checking/tools/repro_upstream_bug.py
```

# Generative-UI parametric sweep panel (POC #38)

Phase 2 of the generative-UI pair: a task-scoped *input* panel — generated from a request like "run a parametric sweep on glazing U-value and HVAC COP" — where every control binds to a strict, unit-aware schema, so a generated sweep configuration is provably identical to the hand-written one and every invalid value is rejected at the schema layer.

Reuses the Phase 1 catalog/spec/renderer format from `../generative-ui-diagnostic-lens/`; does not fork it. Spec only — no generated code is executed, no protocol (A2UI / AG-UI / MCP Apps) is adopted, and nothing here changes Fluxion.

## Reproduce

```sh
python3 generative-ui-sweep-panel/run_poc.py
python3 -m pytest generative-ui-sweep-panel/ -q
```

`run_poc.py` prints the frozen scoped parameter set (15 parameters), panel binding validity (14/14), the explicit imperial-conversion behaviour, the RunButton invalid-field behaviour, the full adversarial set with verbatim rejection reasons (33/33 rejected), the configuration-equivalence harness (5/5 byte-for-byte, SHA-256 shown), the strict-layer vs assembler effort split, and the headline table.

Verdict and full reasoning: see `REPORT.md` (**Conditional** — configuration-level bars met, strict layer dominated effort, solver-run equivalence not observed from inside this repo).

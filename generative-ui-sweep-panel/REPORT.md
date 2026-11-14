# POC #38 — Generative-UI parametric sweep panel (write path, schema-locked)

**Verdict: Conditional**

Configuration-level equivalence and schema rejection are met in full, but two of the issue's own Conditional conditions apply: the strict layer dominated the build effort (>50% of code lines), and solver-run equivalence was not observed — Fluxion is not inside this repo, so no generated configuration was run through `fluxion apply-measures` or a simulation in this POC. The honest recommendation stands: invest in the strict schema layer as a Fluxion feature first; panel generation is the cheap part.

## Headline results (all from `python3 generative-ui-sweep-panel/run_poc.py`, reproduced by the supervisor at collection)

| metric | result |
|---|---|
| frozen scoped parameters | 15 |
| panels generated | 14 |
| panel binding validity | 14/14 (failures: none) |
| adversarial attempts rejected | 33/33 |
| configuration equivalence (byte-for-byte) | 5/5 |
| solver-run equivalence | NOT OBSERVED — Fluxion is not inside this worktree |
| generated code executed | none (spec + configuration only) |
| protocol adopted | none (A2UI / AG-UI / MCP Apps not used) |

Tests: `python3 -m pytest generative-ui-sweep-panel/ -q` → 36 passed. Phase 1 suite unchanged and green: `python3 -m pytest generative-ui-diagnostic-lens/ -q` → 90 passed.

## What was built

- `schema.py` — the strict schema layer: the frozen scoped set (15 parameters, each with type, explicit SI unit, min/max, default; evidence kinds: in-repo=10, physical-bound=4, decision=1), a `unit` field on every descriptor, and a validator that *rejects* — never warns on — unknown parameters, wrong types, out-of-range values, and unit mismatches. Imperial inputs are converted only explicitly, with the conversion shown (e.g. 68 °F → 20 °C, formula printed); the same numeric value submitted as °C (68 °C) is refused as out of range.
- `panel_spec.py` / `panel_catalog.py` — the Phase 1 spec format extended with input primitives: `ParamSlider`, `ParamNumber`, `ChoiceSelect`, `SweepAxis`, `RunButton` (rendered disabled while any field is invalid).
- `panel.py` / `config.py` / `panel_renderer.py` — the assembler (spec only, no generated code), the configuration writer, and the renderer.
- `fixtures/` — panel requests, hand-written configurations, and the adversarial set.
- `run_poc.py` — the single reproduce command; prints every section below verbatim.

## Equivalence (configuration level)

Five representative sweeps (heating setpoint, cooling setpoint, infiltration, window U-value, cooling COP): the panel-generated configuration and the hand-written configuration have identical SHA-256 hashes in all 5 cases (5/5 byte-for-byte). This is configuration equivalence only — it does not show the two configurations produce identical simulation outputs, because no solver ran here.

## Adversarial set

33 attempts, 33 rejected at the schema layer, zero reached a measure or a solver: negative COP, COP above the frozen maximum, sub-absolute-zero temperatures in °C and K, U-value of 0 and 10× the physical range, unscoped parameters, a °F value submitted as °C, and a structural (geometry) parameter sweep attempt, among others. Every rejection reason is printed verbatim by `run_poc.py` section [5].

## Effort split (code lines, from run_poc.py section [7])

- Strict layer (schema 792 + spec 349 + catalog 302): **1,443 lines**
- Assembler (panel 330 + config 65 + renderer 178): **573 lines**

The strict layer is ~72% of the layer code — well over the issue's 50% Conditional threshold. That is the headline cost finding: the safety property this POC exists to test is not in the panel generation at all; it is in the schema layer, and that layer is most of the work.

## What promotion into Fluxion tooling would require

1. A real solver-run equivalence pass: run panel-generated and hand-written configurations through `fluxion apply-measures` + simulation and compare outputs to the solver's determinism tolerance (the step this POC could not observe from inside this repo).
2. The strict descriptor (unit field + reject-don't-warn validation) adopted into `FluxionMeasure.arguments()` / `parse_arguments()` upstream, scoped to the frozen parameter set first.
3. Only then, panel generation as a front-end over that upstream schema.

## Claims

- [observed] 15 frozen scoped parameters, each with an explicit SI unit, range and default — `run_poc.py` section [1] prints the set; ranges are in-repo evidence (10), cited physical bounds (4), or a labelled decision (1) because no Fluxion measure spec exists in this repo.
- [observed] Panel binding validity 14/14 and adversarial rejection 33/33 at the schema layer — `run_poc.py` sections [2] and [5]; 36 POC tests pass.
- [observed] Panel-generated and hand-written configurations are byte-for-byte identical for 5/5 representative sweeps — SHA-256 hashes printed in `run_poc.py` section [6].
- [unsupported] Solver-run equivalence: no Fluxion solver or `apply-measures` run was executed in this POC; any claim that generated sweeps produce identical simulation outputs is unproven here.
- [inference] The strict schema layer is the dominant cost of the approach (~72% of layer code lines), so the schema layer — not panel generation — is where a Fluxion investment would go first.
- [decision] Verdict Conditional, per the issue's own rules: equivalence/rejection bars met at the configuration level, strict layer >50% of effort, solver equivalence unobserved.

## Provenance

Built by a plan-coder worker (balanced, minimax/MiniMax-M2.7, 65,181 tokens out, 60/60 steps — it hit the step cap while polishing tests; the supervisor verified the full diff, re-ran `run_poc.py` and both test suites at collection, and authored this REPORT.md and the README from the verbatim harness output).

# Generative-UI diagnostic lens for Fluxion results — POC report (slice 1)

**Conditional**

> Supervisor note: the worker (MiniMax-M2.7, balanced) built the full code slice and hit its 60-step cap while writing the README; this REPORT.md was authored by the supervisor from the worker's verified outputs (66/66 tests, `run_poc.py` headline table — both re-run by the supervisor at collection). No number below comes from the worker's prose alone.

## Step-0 limitation

This slice runs against in-folder FIXTURE run outputs shaped after the issue's documented Fluxion `results.json` premise (issue #37, premise verified by the issue author 2026-11-13 in the fluxion clone). Step 0 against a real live Fluxion run output is NOT verified by this slice; the report's verdict is therefore at most **Conditional**, and its Claims section types live-Fluxion binding as [unsupported] and fixture-run results as [observed] only.

## What was built

A closed 6-primitive catalog (`TimeSeriesChart`, `DiffTable`, `KPICard`, `ZoneHighlight`, `LogTail`, `ParamInspector`), a JSON UI-spec format with a deterministic validator that rejects unknown primitives, unknown fields, and unit mismatches (absent bindings render "no data"), a static-HTML renderer, and a deterministic rule-based assembler (no LLM, no network) that maps a request plus a field manifest (names + units only) to a spec or an explicit refusal. Three seeded fixture cases with ground truths frozen before assembly: an ASHRAE-140-style perturbed case, a ground-coupled-floor case vs the 9.4 °C constant, and a humid-climate latent-load case whose signal is moisture.

## Headline results (reproduce: `python3 generative-ui-diagnostic-lens/run_poc.py`)

| Metric | Result |
|---|---|
| Binding validity (field exists in manifest + unit matches) | 14/14, failures: none |
| Adversarial handled (refusal / explicit no-data) | 14/14 (set asked for ≥10) |
| Per-case diagnosis support (ground-truth series bound) | 3/3 cases, 2/2 series each |
| Out-of-catalog requests refused (not silently approximated) | 6/6 |
| Catalog coverage | 6/6 primitives expressed at least once |
| Test suite | 66 passed (`python3 -m pytest generative-ui-diagnostic-lens/ -q`) |

## Timing — the bar is NOT met in this setting

The issue's time criterion (median lens time-to-diagnosis < 50% of a throwaway-script baseline) was measured as scripted wall-clock per view, and the lens **loses**: case 1 0.690 ms vs baseline 0.053 ms (12.9×), case 2 0.534 vs 0.059 ms (9.1×), case 3 0.518 vs 0.059 ms (8.7×). The baseline is a 27-line script reading the same tiny fixture JSON directly; the lens path is 1,663 lines (assembler + spec + catalog + renderer). On fixture-scale data the assembly overhead dominates and there is no engineer-in-the-loop time saving to measure — the honest reading is that the time claim is unproven here, not that it fails at real-run scale. It is reported as missed, per the issue's "do not average it away" rule for its criteria.

## Adversarial results

14 adversarial requests (nonexistent fields, wrong units, another run's data by id and in words, mid-run solver state, a zone that does not exist, mixed known+unknown fields) — all 14 refused with a named refusal code or rendered as explicit no-data. Zero invented bindings.

## Catalog coverage — the inexpressible list (a deliverable)

Requests the closed catalog cannot express, all correctly refused: whole-building floor-plan heat map; side-by-side comparison of two runs; scatter plot of one field against another; animated view of the solver converging; change an input and re-run (write path — out of scope by design); a request with no field in it at all.

## Verdict reasoning

Binding validity (the POC's central claim) held at 100% on fixtures, the adversarial set was clean, and diagnosis support was 3/3 — so this is not a No-go. It cannot be a Go: step 0 against a real Fluxion run output was not verified in this slice, and the time criterion was missed in the fixture setting. **Conditional**: the assembly/validation mechanism survives; what survives is a lens for monitoring-style requests over a verified manifest, pending step 0.

## What would change the recommendation

- Running the assembler against real Fluxion `results.json` outputs from the three seeded cases (ASHRAE 140 perturbed case, #4785 ground-coupled floor, a humid-climate latent case) with the same mechanical binding check — 100% there upgrades toward Go; any invented binding there is a No-go.
- A timing measurement at real-run scale with an engineer in the loop, where the throwaway-script baseline is a real script written against a real run's output, not a 27-line fixture reader.

## Claims

- [observed] Binding validity is 14/14 with no failures, adversarial handling is 14/14, and per-case ground-truth series binding is 3/3 cases (2/2 series each) — source: `python3 generative-ui-diagnostic-lens/run_poc.py` headline table, re-run by the supervisor at collection.
- [observed] The test suite passes: 66 passed — source: `python3 -m pytest generative-ui-diagnostic-lens/ -q`, re-run by the supervisor at collection.
- [observed] The lens path is slower than the trivial throwaway-script baseline on fixture data (ratios 12.9× / 9.1× / 8.7× per case) — source: `run_poc.py` timing section quoted above.
- [unsupported] The assembler binds correctly to real live Fluxion run outputs — no real Fluxion output was used in this slice; fixtures were shaped after the issue's documented premise only.
- [inference] Assembly accuracy, not rendering or protocol choice, is the risk this POC isolates, and the deterministic validator is what makes an invented binding mechanically detectable — source: the validator's reject paths exercised by the adversarial set in `run_poc.py` section [2].

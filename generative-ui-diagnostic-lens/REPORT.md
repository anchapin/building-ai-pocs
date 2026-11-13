# Generative-UI diagnostic lens for Fluxion results — POC report (slices 1 and 2)

**Verdict: Go on the binding/adversarial gate (upgraded from Conditional); the time criterion remains missed and is reported, not waived.**

> Supervisor note (slice 1): the worker (MiniMax-M2.7, balanced) built the full code slice and hit its 60-step cap while writing the README; this REPORT.md was authored by the supervisor from the worker's verified outputs (66/66 tests, `run_poc.py` headline table — both re-run by the supervisor at collection). No number below comes from the worker's prose alone.

> Slice-2 note (this slice): step 0 was executed against a **real, completed Fluxion run output** — a byte-verified copy of the versioned standard results report (`real_runs/fluxion_standard_report.json`, sha256 `1d783a1e…1146b`, provenance in `real_runs/PROVENANCE.md`). Slice 2's own results are in **"Slice 2"** below; every slice-1 number is unchanged, and the Claims section at the end is re-typed after slice 2.

## Step-0 limitation (slice 1 — superseded by slice 2)

Slice 1 ran against in-folder FIXTURE run outputs shaped after the issue's documented Fluxion `results.json` premise (issue #37, premise verified by the issue author 2026-11-13 in the fluxion clone). Step 0 against a real live Fluxion run output was NOT verified by slice 1; slice 1's verdict was therefore at most **Conditional**, and its Claims section typed live-Fluxion binding as [unsupported] and fixture-run results as [observed] only. **Slice 2 closed that gap** — see below.

## What was built

A closed 6-primitive catalog (`TimeSeriesChart`, `DiffTable`, `KPICard`, `ZoneHighlight`, `LogTail`, `ParamInspector`), a JSON UI-spec format with a deterministic validator that rejects unknown primitives, unknown fields, and unit mismatches (absent bindings render "no data"), a static-HTML renderer, and a deterministic rule-based assembler (no LLM, no network) that maps a request plus a field manifest (names + units only) to a spec or an explicit refusal. Three seeded fixture cases with ground truths frozen before assembly: an ASHRAE-140-style perturbed case, a ground-coupled-floor case vs the 9.4 °C constant, and a humid-climate latent-load case whose signal is moisture.

## Headline results — slice 1 (fixtures) (reproduce: `python3 generative-ui-diagnostic-lens/run_poc.py`)

| Metric | Result |
|---|---|
| Binding validity (field exists in manifest + unit matches) | 14/14, failures: none |
| Adversarial handled (refusal / explicit no-data) | 14/14 (set asked for ≥10) |
| Per-case diagnosis support (ground-truth series bound) | 3/3 cases, 2/2 series each |
| Out-of-catalog requests refused (not silently approximated) | 6/6 |
| Catalog coverage | 6/6 primitives expressed at least once |
| Test suite | 66 passed (`python3 -m pytest generative-ui-diagnostic-lens/ -q`) |

## Timing — the bar is NOT met in this setting (slice 1)

The issue's time criterion (median lens time-to-diagnosis < 50% of a throwaway-script baseline) was measured as scripted wall-clock per view, and the lens **loses**: case 1 0.690 ms vs baseline 0.053 ms (12.9×), case 2 0.534 vs 0.059 ms (9.1×), case 3 0.518 vs 0.059 ms (8.7×). The baseline is a 27-line script reading the same tiny fixture JSON directly; the lens path is 1,663 lines (assembler + spec + catalog + renderer). On fixture-scale data the assembly overhead dominates and there is no engineer-in-the-loop time saving to measure — the honest reading is that the time claim is unproven here, not that it fails at real-run scale. It is reported as missed, per the issue's "do not average it away" rule for its criteria.

## Adversarial results (slice 1)

14 adversarial requests (nonexistent fields, wrong units, another run's data by id and in words, mid-run solver state, a zone that does not exist, mixed known+unknown fields) — all 14 refused with a named refusal code or rendered as explicit no-data. Zero invented bindings.

## Catalog coverage — the inexpressible list (a deliverable)

Requests the closed catalog cannot express, all correctly refused: whole-building floor-plan heat map; side-by-side comparison of two runs; scatter plot of one field against another; animated view of the solver converging; change an input and re-run (write path — out of scope by design); a request with no field in it at all.

## Verdict reasoning (slice 1)

Binding validity (the POC's central claim) held at 100% on fixtures, the adversarial set was clean, and diagnosis support was 3/3 — so this is not a No-go. It cannot be a Go: step 0 against a real Fluxion run output was not verified in this slice, and the time criterion was missed in the fixture setting. **Conditional**: the assembly/validation mechanism survives; what survives is a lens for monitoring-style requests over a verified manifest, pending step 0.

## What would change the recommendation (slice 1)

- Running the assembler against real Fluxion `results.json` outputs from the three seeded cases (ASHRAE 140 perturbed case, #4785 ground-coupled floor, a humid-climate latent case) with the same mechanical binding check — 100% there upgrades toward Go; any invented binding there is a No-go.
- A timing measurement at real-run scale with an engineer in the loop, where the throwaway-script baseline is a real script written against a real run's output, not a 27-line fixture reader.

## Slice 2 — step 0 against a real Fluxion run output

### Step 0: the real output and its provenance

A **real, completed Fluxion run output** was obtained read-only; no Fluxion
simulation was run, nothing in Fluxion was modified. The artifact is the
versioned standard results report that the Fluxion engine emits for a
completed run (`schemas/results_v1.schema.json`, `schema_version` 1.0.0):

| item | value |
|---|---|
| artifact | `tests/reference_data/results_v1/standard_report.json` of the Fluxion clone (`anchapin/fluxion`, branch `develop`), introduced by commit `31c038e3`, merged as `30a13ba6` (PR #4606) |
| copy in this POC | `generative-ui-diagnostic-lens/real_runs/fluxion_standard_report.json` (2 201 kB, byte-for-byte) |
| sha256 | `1d783a1eba6f3ca621ad846d0fa15ee04e3033297b89c75d557a22f3c7c1146b` — identical in the upstream clone and in the copy, and re-checked by `run_poc.py` section [8] and by `tests/test_real_manifest.py` on every test run |
| full provenance | `generative-ui-diagnostic-lens/real_runs/PROVENANCE.md` |
| what the run was | model "Untitled Simulation" (`model-file:examples/minimal.flux`), annual period, 1 year, 8 760 timesteps of 3 600 s |

### What the real output is — and what it is not

* It is **not** the issue #37 premise shape (`run_id`, `status`, solver block, inputs, provenance, log lines, table of result fields). A read-only search of the Fluxion clone found **no** JSON document carrying a `"run_id"` or a `"fields"` key, so the slice-1 fixture shape is a *shaped premise*, not a copy of an artifact that exists in the repo. The lens therefore got the real output its own loader and its own field-mapping table (`manifest.py`: `STANDARD_REPORT_FIELDS`, `load_standard_report`, `standard_report_to_run`, `manifest_from_standard_report`); the manifest contract itself is unchanged — names + units + kinds, never values.
* The **hourly end-use series is not embedded** in the report: the report carries its sha256 checksum only. The lens has no hourly values to draw, renders "no data" for that view, and does not invent the series.
* The report carries **no log lines** and **no run inputs**, so the LogTail view of the real run is an explicit refusal (`no_log_field`).
* `annual.eui_kwh_per_m2` is left out of the manifest on purpose: the closed catalog's unit vocabulary has no `kWh/m2`, and a field whose unit the lens cannot canonicalise cannot be unit-checked.

### The manifest built from the real output

26 fields, names and units only (`manifest.py`): the four annual end-use
energies (kWh), the four annual peaks (kW), the total energy (kWh), floor
area (m2), zone count (1), the four monthly end-use series (kWh), the
monthly heating/cooling peak series (kW), the unmet-hours counters for the
occupied and all-hours conventions (h), the setpoint tolerance (°C), and
the four hourly end-use series (kWh, **no values** — checksum only).

### Binding validity against the REAL manifest

Mechanically checked, exactly as in slice 1 (the field exists in the
manifest **and** the unit the spec binds is the unit the manifest
declares), over the real-output request set (`real_runs/requests.json`, 9
requests):

| Metric | Result |
|---|---|
| Binding validity on the REAL manifest | **8/8** — failures: **none** |
| Invented bindings (a field the real run does not carry) | **0** |
| Real-output requests refused explicitly | 1/9 (`no_log_field` — the report carries no log lines) |
| Real-output requests that produced a spec | 8/9 (11 components) |
| Seeded-case requests against the REAL manifest | 3/3 refused `unknown_field` — the real run carries none of the seeded cases' fields (`zone1_air_temperature`, …), which is the correct outcome, not a defect |
| Adversarial set against the REAL manifest | **14/14** handled (explicit refusal, correct code in 12/14) |

No failure therefore has to be quoted: the failure list is empty. (Had
there been one, the harness prints it verbatim — field, the unit the
manifest declares, the unit the spec binds, and the offending spec
fragment — e.g. `component 0 (KPICard): field 'x' is kWh, spec binds kW |
spec fragment: {...}`.)

**Two adversarial requests changed refusal code against the real manifest**
and are named here rather than averaged away: `adv02_wrong_unit_kw` and
`adv06_wrong_unit_variant` expect `unit_mismatch` but got `unknown_field`,
because the real run has no `zone1_air_temperature` field at all — there is
no unit to mismatch. Both are still **refused**: 14/14 handled, **0**
silently invented bindings.

**Advisories (not invalid bindings, but reported):** three bindings name a
*scalar* field where a *series* is wanted — `total_energy` in a
`TimeSeriesChart`, and `heating_energy` / `cooling_energy` in a
`DiffTable`. The field exists and the unit matches, so the mechanical
binding check passes; the view simply cannot plot a scalar as a series.
This is a lens-side nicety (the request wording asked for a chart of a
total), not a binding defect, and it is reported rather than hidden.

### Timing at real-output scale

Same measurement as slice 1 section [7]: per-view wall clock, median of
10 repeats, against a throwaway script that reads the report JSON directly
and prints the named fields. Two variants are measured because the report
is 2.2 MB and file I/O dominates: the baseline re-reads the file on every
call (what a throwaway script does), while the lens path is measured once
with the report already parsed and once re-reading it per view.

| request | baseline (re-reads the report) | lens (report pre-parsed) | lens (report re-read, like-for-like) |
|---|---|---|---|
| `real01_kpi_heating_energy` | 43.3 ms/view | 0.33 ms/view | 45.0 ms/view (1.04×) |
| `real02_chart_monthly_heating` | 40.0 ms/view | 0.35 ms/view | 37.8 ms/view (0.95×) |
| `real03_kpi_peak_heating` | 39.4 ms/view | 0.31 ms/view | 30.1 ms/view (0.77×) |
| `real04_chart_hourly_heating` | 56.8 ms/view | 0.32 ms/view | 74.8 ms/view (1.32×) |
| `real05_kpi_unmet_heating_hours` | 52.5 ms/view | 0.34 ms/view | 43.2 ms/view (0.82×) |
| `real06_chart_total_energy` | 50.4 ms/view | 0.30 ms/view | 43.6 ms/view (0.86×) |
| `real07_diff_table_heating_cooling` | 39.7 ms/view | 0.38 ms/view | 29.1 ms/view (0.73×) |

**The time criterion (< 50% of the baseline) is still NOT met, and is
reported, not waived.** At real-output scale the lens is *on par with* the
throwaway script (0.73×–1.32× like-for-like; the spread is measurement
noise around a cost that both sides pay: parsing 2.2 MB of JSON), never
below half of it. The lens' own work (manifest + assembly + validation +
render) is 0.30–0.38 ms per view — that part *is* fast; but the
end-to-end "time-to-diagnosis" the criterion talks about is dominated by
reading the artifact, and the lens cannot beat a script that only reads the
artifact. Slice 1's fixture-scale result (12.9× / 9.1× / 8.7× slower) is
not re-litigated here; re-measured on this machine it reproduced between
9× and 25×, i.e. the same conclusion with a wider spread.

### Verdict reasoning (slice 2)

The parent gate for issue #37 is: *100% binding validity + a clean
adversarial set on the REAL output → upgrade toward Go; any invented
binding on the real output → No-go; no real output obtainable → Conditional
with the blocker named.*

* A real output **was** obtainable (no blocker to name).
* Binding validity on the real manifest: **8/8 = 100%**, failures: none.
* Invented bindings on the real output: **0**.
* Adversarial set on the real manifest: **14/14** handled, no invented
  binding.

The gate's Go condition is therefore met, and the report is **upgraded from
Conditional toward Go**; by the parent's own wording that binding result
alone ungates issue #38. The time criterion remains missed (measured above,
at real scale this time) and is reported, not waived: the *time* claim of
the POC stays unsupported. If the parent reads the time criterion as
blocking, the honest downgrade is **Conditional** with the blocker named —
"the lens is not faster than a throwaway script at real-run scale; both are
dominated by parsing the run artifact" — and no other blocker.

### What would change the recommendation (slice 2)

* A timing measurement with an engineer in the loop at real-run scale
  (the criterion is about time-to-diagnosis, not about scripted per-view
  wall clock), or a baseline that does the same *diagnosis* work rather
  than the same *reading* work.
* The seeded cases re-run as **real** Fluxion runs: the three seeded-case
  requests are refused against the real manifest because the real run is a
  different simulation; binding them against real outputs of the three
  seeded cases would also test per-case diagnosis support on real data.
* The three scalar-as-series advisories could be turned into a hard
  refusal or a "single point" rendering by the catalog — a lens-side
  change, out of scope for this slice.

## Claims (re-typed after slice 2)

- [observed] The assembler binds correctly to a **real, completed Fluxion
  run output**: binding validity 8/8 on the real manifest with **no**
  failures and **no** invented binding, and the adversarial set handled
  14/14 against that manifest — source: `run_poc.py` section [8] (run
  output: `real_runs/fluxion_standard_report.json`, sha256
  `1d783a1e…1146b`, a byte-verified copy of the upstream completed run;
  provenance in `real_runs/PROVENANCE.md`).
- [observed] The real output is the versioned standard results report
  (`results_v1`, `schema_version` 1.0.0) of a completed Fluxion run — and
  it is **not** the issue #37 premise shape: no JSON document in the
  Fluxion clone carries `"run_id"`/`"fields"`, so the slice-1 fixture
  shape is a shaped premise, not a copy of a repo artifact — source:
  `real_runs/PROVENANCE.md` (read-only search of the clone).
- [observed] The three seeded-case requests are **refused**
  (`unknown_field`) against the real manifest, because that run carries
  none of their fields; the refusal is explicit and correct — source:
  `run_poc.py` section [8a].
- [observed] The lens does **not** invent data it was not given on the real
  output: the hourly series (referenced by checksum only) renders "no
  data", and the LogTail view of the report (which carries no log lines)
  is refused `no_log_field` — source: `run_poc.py` section [8b],
  `tests/test_real_manifest.py`.
- [observed] The test suite passes: **90 passed**
  (`python3 -m pytest generative-ui-diagnostic-lens/ -q`; 80 before this
  slice, 7 new manifest tests + 3 new harness assertions) — source: the
  pytest run in this slice.
- [observed] The time criterion is **missed** and is reported, not waived:
  at real-output scale the lens is on par with the throwaway baseline
  (0.73×–1.32× like-for-like, never below 0.5×) because both are dominated
  by parsing the 2.2 MB report; slice 1's fixture result (12.9× / 9.1× /
  8.7× slower) is unchanged as a finding — source: `run_poc.py` sections
  [7] and [8d].
- [observed] Slice-1 results are unchanged: binding validity 14/14,
  adversarial 14/14, ground-truth series bound 3/3 cases, out-of-catalog
  refused 6/6, catalog coverage 6/6 — source: `run_poc.py` headline table.
- [inference] Assembly accuracy, not rendering or protocol choice, is the
  risk this POC isolates, and the deterministic validator is what makes an
  invented binding mechanically detectable — this now holds on a real
  artifact too, where the failure mode is not hypothetical: source: the
  validator's reject paths exercised by the adversarial set in `run_poc.py`
  sections [2] and [8c].
- [inference] The lens's field naming is the fragile part of the mapping,
  not the mechanism: three advisories bind a scalar where a series is
  wanted. The catalogue is closed and the mapping table is explicit, so
  this is a naming/wording issue in the request set rather than a binding
  error — source: `run_poc.py` section [8e] advisories.

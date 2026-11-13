# Generative-UI Diagnostic Lens — POC slice 0 (read-only, deterministic)

**Status:** slice 0 built and measured on in-folder fixtures.  The verdict is
**Conditional** (see `REPORT.md`).

A *diagnostic lens* turns a plain-language question about a building-simulation
run ("chart zone 1 air temperature and show it against the reference range")
into a **validated UI specification** over a **closed catalog of six
primitives**, or into an **explicit refusal**.  It never invents data, never
calls a model, never touches the network, and never writes anything back to
the run.

This slice is **standalone**: it reads JSON run-output fixtures that are
shaped after the Fluxion `results.json` premise of issue #37.  It is *not*
wired into Fluxion, it does not execute or patch a solver, it adopts no
protocol (A2UI / AG-UI / MCP Apps), and it has no write path.

---

## Reproduce

One command, end to end:

```sh
python3 generative-ui-diagnostic-lens/run_poc.py
```

It prints the headline table (binding validity, adversarial handling,
catalog coverage, per-case diagnosis support, timing against a throwaway
baseline).  The test suite:

```sh
python3 -m pytest generative-ui-diagnostic-lens/ -q
```

Regenerate the fixtures (deterministic — the same bytes every time):

```sh
python3 generative-ui-diagnostic-lens/fixtures/gen_fixtures.py
```

---

## 1. The catalog (closed: six primitives, no additions)

`catalog.py` holds the whole catalog.  Every primitive declares the binding
fields it requires, the units it accepts, and what it renders when a binding
is absent (always `no data`, never a made-up value).

| Primitive | Required bindings | What it shows | Absent-binding rendering |
| --- | --- | --- | --- |
| `TimeSeriesChart` | `series` (field), `unit` | series vs the run's sample index, unit-labelled axes | `no data` — axes keep their unit label, no polyline is drawn |
| `DiffTable` | `series` (field), `unit` | case value vs reference range, out-of-range rows flagged | `no data` — the reference column shows `no data` |
| `KPICard` | `field` (field), `unit` | one named scalar with its unit | `no data` — the card shows the name and no value |
| `ZoneHighlight` | `zone_id` (string), `series` (field), `unit` | schematic zone box + the series bound to it (schematic only, no geometry) | `no data` — the schematic zone is drawn, without data |
| `LogTail` | `log_field` (field), `count` (int) | the last N lines of the run log | `no data` — the run log is unavailable |
| `ParamInspector` | — (optional `field`) | read-only inputs / provenance view | `no data` — no input or provenance entries are available |

Optional bindings: `DiffTable` also understands `reference_min`,
`reference_max` and `reference_series`; `TimeSeriesChart` understands the
props `title` and `x_axis_label`; `KPICard` understands `label` and
`aggregation`; `ParamInspector` understands the `section` prop
(`inputs` / `provenance`).

## 2. The UI-spec format

A spec is a small, closed JSON document:

```json
{
  "schema_version": 1,
  "run_id": "run_ashrae140_case1",
  "case_id": "case1_ashrae140",
  "request": "chart zone1 air temperature ...",
  "components": [
    {"primitive": "TimeSeriesChart",
     "title": "zone1 air temperature",
     "bindings": {"series": "zone1_air_temperature", "unit": "°C"},
     "props": {"title": "zone1 air temperature", "x_axis_label": "sample"}}
  ]
}
```

`uispec.py` validates it and **rejects** (never repairs):

* an unknown primitive (`unknown_primitive`),
* an unknown field at document, component, binding or prop level
  (`unknown_field`, `unknown_binding_field`, `unknown_prop`),
* a missing required binding (`missing_binding`),
* a field that is not in the run's field manifest (`unknown_field`),
* a unit that does not match the manifest's unit for that field
  (`unit_mismatch`), or a unit the lens cannot canonicalise (`unknown_unit`),
* a spec built for another run (`run_mismatch`).

`renderer.py` turns a validated spec plus a run output into static HTML
(Python standard library only — no npm, no React build, no JavaScript).  The
same (spec, run) pair always produces byte-identical HTML.

## 3. The assembler

`assembler.py` is deterministic, rule-based, and offline.  It sees the run's
**field manifest** (names + units + the run's own declared reference band)
and never the series values, so it cannot diagnose anything itself — it can
only decide *which* primitive carries *which* declared field.

1. The request is scanned for trigger phrases (`chart`, `diff table`,
   `kpi card`, `highlight zone`, `run log`, `inputs`, `provenance`, …);
   longest phrase wins.
2. Each trigger owns the text that follows it.
3. Inside that text the significant words are matched against the manifest's
   field names.  A field is mentioned when a window of significant words
   matches the field name's words (same count, same words, any order) — so a
   bare "temperature" never matches `zone1_air_temperature`.
4. Significant words that no field name accounts for are treated as a
   mention of a field the manifest does not have → refusal.
5. A unit named in the request must match the unit of every field it binds.

Refusal codes: `empty_request`, `mid_run_state_unavailable`, `run_mismatch`,
`different_run_requested`, `no_known_intent`, `unknown_field`,
`ambiguous_field`, `unknown_unit`, `unit_mismatch`, `no_log_field`,
`no_zone_id`.  A refusal is a first-class result, not an error.

## 4. Fixtures and frozen ground truth

`fixtures/gen_fixtures.py` emits three seeded run outputs and their ground
truth, deterministically:

| Case | Run | Signal |
| --- | --- | --- |
| `case1_ashrae140` | `run_ashrae140_case1` | ASHRAE-140-style case; the heating setpoint input is perturbed from 20.0 °C to 24.0 °C at hour 8 and zone 1 leaves its 20.0–24.0 °C reference band |
| `case2_ground_coupled` | `run_ground_coupled_case2` | ground-coupled floor: the boundary-temperature series against a constant 9.4 °C baseline |
| `case3_humid_latent` | `run_humid_latent_case3` | humid climate: the signal is a moisture / latent-load pair, not temperature |

The ground truth is written **first** (`fixtures/ground_truth/*.ground_truth.json`),
by hand, before the run outputs it describes and before the assembler ever
sees them: each file holds the diagnosis in prose, the fields the diagnosis
depends on, and the numbers a correct lens must be able to show.

`fixtures/case_requests.json` holds the requests that are assembled against
those runs (including the requests that exercise `ZoneHighlight`, `LogTail`,
`ParamInspector`, and one field that is declared but carries no values — it
must render `no data`).

`fixtures/baseline_throwaway.py` is the trivial comparison point: it reads
the fixture JSON directly and prints the same view, in 27 lines, with no
validation and no refusal behaviour.

## 5. Adversarial request set

`adversarial/requests.json` holds 14 requests that must all end in a refusal
or a no-data spec — never in an invented binding:

* nonexistent fields (`CO2 generation rate`, `annual chiller electricity
  consumption`, `window U-value`, a mixed known/unknown request),
* wrong units (`zone1 air temperature in kW`, in two phrasings),
* another run's data (by run id, and in words),
* mid-run solver state (in two phrasings),
* plus variants: a field that belongs to a different run, a zone that does
  not exist.

`fixtures/requests_out_of_catalog.json` holds the intents the closed
catalog **cannot** express (floor-plan heat map, cross-run comparison,
scatter plot, live solver animation, edit-and-re-run).  Those are the
inexpressible list of the catalog-coverage table; all of them are refused.

## 6. Limits of this slice

* **Step-0 limitation (verbatim from the brief):** this slice runs against
  in-folder FIXTURE run outputs shaped after the issue's documented Fluxion
  `results.json` premise (issue #37, premise verified by the issue author
  2026-11-13 in the fluxion clone).  Step 0 against a real live Fluxion run
  output is NOT verified by this slice; the report's verdict is therefore at
  most **Conditional**, and its Claims section must type that claim as
  [unsupported] for live-Fluxion binding and [observed] only for the
  fixture runs actually executed.
* No write path, no solver execution or patching, no Fluxion integration, no
  protocol adoption (A2UI / AG-UI / MCP Apps), no hosted services, no
  secrets or paid APIs, no packages beyond the Python standard library.

See the repo README for the POC rules and the claim-typing convention.

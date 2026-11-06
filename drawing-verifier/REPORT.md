# REPORT — drawing-verifier, SLICE 1 (symbolic checker)

**Conditional** — the symbolic-checker half of the POC is demonstrated
and measured on this slice's hand-built fixtures; the VLM second-reader half
is deferred pending VLM selection, and no Matchline extraction run was
performed in this slice.

* POC: VLM + neuro-symbolic verifier hardening drawing-to-BEM (Matchline).
* Slice 1 scope: the symbolic checker, its fixtures, its injected-error test
  set, and the geometry-error measurement.
* Not in this slice: any VLM wiring, any Matchline extraction run, any
  integration with Fluxion or Matchline, any other POC in this repo.

---

## 1. What was built

* `drawing-verifier/checker.py` — pure-Python (stdlib only) checker:
  schema validation, four symbolic checks (zone closure, wall adjacency,
  window-to-wall ratio, schedule-symbol cross-check), a `SecondReader`
  protocol plus a `NoVLMSecondReader` stub, and a CLI that exits non-zero
  when findings exist.
* `drawing-verifier/fixtures/` — three hand-built clean buildings
  (`small_office`, `two_unit_house`, `studio_loft`), each with a
  hand-built reference model (`*.reference.json`) whose floor areas and WWRs
  were computed by hand arithmetic, plus a 12-case injected-error set
  (`fixtures/injected/`, listed in `fixtures/injected/cases.json`).
* `drawing-verifier/run_headline.py` — one command that reproduces the
  headline table (catch rate, false-flag rate, geometry error).
* `drawing-verifier/tests/` — 41 pytest tests covering the schema, the four
  checks, the injected-error set end-to-end, the false-flag measurement and
  the geometry arithmetic.
* `drawing-verifier/README.md` — the input schema, the four checks, the
  stated tolerance (0.05 m) and the stated WWR band (0.05–0.55).

Reproduce everything:

```sh
python3 -m pytest drawing-verifier/tests/ -q
python3 drawing-verifier/run_headline.py
```

## 2. Headline numbers (measured on this slice's fixtures)

| Metric | Value | POC Go bar | Holds on these fixtures? |
| --- | --- | --- | --- |
| Injected errors caught | **12 / 12 = 100 %** | >= 80 % | yes |
| False-flag rate on clean fixtures | **0 / 3 = 0.0 %** | < 10 % | yes |
| Worst geometry error vs hand-built model | **0.10 %** | < 5 % | yes |

**These numbers hold for this slice's fixtures only.** They say nothing about
Matchline extraction: this slice never ran an extraction, so no claim is made
about catching errors in a real drawing-to-BEM pipeline.

### 2.1 Per-error-class catch table

| Error class | Injected | Caught | Catch rate |
| --- | --- | --- | --- |
| `opening_host_missing` | 1 | 1 | 100 % |
| `opening_outside_wall` | 1 | 1 | 100 % |
| `opening_overlap` | 1 | 1 | 100 % |
| `schedule_duplicate_tag` | 1 | 1 | 100 % |
| `schedule_symbol_duplicate` | 1 | 1 | 100 % |
| `schedule_tag_missing` | 1 | 1 | 100 % |
| `schema_invalid` | 2 | 2 | 100 % |
| `wwr_out_of_band` | 1 | 1 | 100 % |
| `zone_not_closed` | 2 | 2 | 100 % |
| `zone_opening_missing` | 1 | 1 | 100 % |
| **total** | **12** | **12** | **100 %** |

Every injected variant produced exactly the expected error class (and nothing
else), and every clean fixture produced zero findings.

### 2.2 Geometry error vs the hand-built reference model

| Fixture | Element | Quantity | Computed | Reference (hand) | Abs error | Error % |
| --- | --- | --- | --- | --- | --- | --- |
| small_office | z_office | floor area (m2) | 24.0000 | 24.0 | 0.0000 | 0.00 % |
| small_office | z_office | WWR | 0.1500 | 0.150 | 0.0000 | 0.00 % |
| small_office | w3 | wall WWR | 0.2000 | 0.200 | 0.0000 | 0.00 % |
| two_unit_house | z_unit_a | floor area (m2) | 20.0000 | 20.0 | 0.0000 | 0.00 % |
| two_unit_house | z_unit_a | WWR | 0.1200 | 0.120 | 0.0000 | 0.00 % |
| two_unit_house | z_unit_b | floor area (m2) | 16.0000 | 16.0 | 0.0000 | 0.00 % |
| two_unit_house | z_unit_b | WWR | 0.0900 | 0.090 | 0.0000 | 0.00 % |
| two_unit_house | ha3 | wall WWR | 0.1600 | 0.160 | 0.0000 | 0.00 % |
| two_unit_house | hb3 | wall WWR | 0.1200 | 0.120 | 0.0000 | 0.00 % |
| studio_loft | z_studio | floor area (m2) | 20.0000 | 20.0 | 0.0000 | 0.00 % |
| studio_loft | z_studio | WWR | 0.3000 | 0.300 | 0.0000 | 0.00 % |
| studio_loft | l1 | wall WWR | 0.3333 | 0.333 | 0.0003 | 0.10 % |

**Plain statement on the < 5 % bar:** on these fixtures the geometry error
does hold — the worst deviation is 0.10 % (a rounding artefact in the hand
reference 1/3 vs the computed 0.3333), far below 5 %. Stated plainly, though:
this is a *self-consistency* measurement, because the fixtures are hand-built
from the same dimensions the checker reads. It is not evidence about
extraction accuracy from real drawings; that is slice 2's job.

## 3. What the checks actually detect, and their known limits

The four checks cover the eight error families the brief asked for:

| Injected error | Caught by |
| --- | --- |
| door deleted | `zone_opening_missing` (zone still cites the missing opening id) |
| wall scaled x2 | `zone_not_closed` (loop no longer closes) |
| zone loop unclosed | `zone_not_closed` |
| schedule symbol swapped | `schedule_symbol_duplicate` |
| duplicate schedule tag | `schedule_duplicate_tag` |
| dangling schedule reference | `schedule_tag_missing` |
| door with no host wall | `opening_host_missing` |
| window longer than its host wall | `opening_outside_wall` |
| overlapping windows on one wall | `opening_overlap` |
| over-glazing | `wwr_out_of_band` (flagged, not clamped) |
| malformed fixture | `schema_invalid` |

Known limits, stated honestly:

* **A door deleted together with its zone reference is invisible.** The
  checker sees reference integrity, not drawing intent; if the extraction
  drops a door and the zone list drops it too, nothing flags it. Detecting
  that needs a second source of truth (the drawing) — i.e. the deferred VLM
  reader, or a drawing-side cross-check.
* **A "scaled" wall is caught as a closure failure**, not as a scale error.
  The checker reports the geometric symptom (the loop does not close), not
  the cause (a 2x scale). A closed loop that was uniformly scaled would not
  be flagged at all.
* **The WWR band (0.05–0.55) is a plausibility heuristic**, not a code
  requirement. It is stated in the README and in the code, it is applied only
  to walls/zones that carry glazing, and it is a warning-severity finding.
* **Floor areas are centre-line areas** (shoelace over wall centrelines);
  wall thickness is carried in the model but not added to the area, so the
  numbers are "clear internal" areas, not gross areas.
* The error set is small and hand-built (12 cases, 3 buildings). A 100 %
  catch rate on 12 hand-made cases is weak evidence; it demonstrates that the
  checks fire and are quiet on clean input, not that they generalise.

## 4. What failed / was not done in this slice

* **VLM second reader: not wired, deliberately.** `checker.SecondReader` is a
  protocol and `checker.NoVLMSecondReader` is a stub that always returns
  `agree=None` ("no VLM configured"). No model was selected, downloaded or
  called; no API keys, no paid calls, no network access. **The VLM agreement
  measurement is deferred pending VLM selection (an Alex decision)**, and no
  agreement numbers are reported here — inventing them would be dishonest.
* **No Matchline extraction run.** The checker consumes structured-geometry
  JSON fixtures only. Slice 2 owns the extraction wiring. Consequently the
  headline numbers describe the checker on fixtures, not the checker on
  Matchline output.
* **No BEM / energy simulation** was run; nothing here claims an energy
  impact, an energy-saving figure, or ASHRAE 140 compliance.
* Nothing outside `drawing-verifier/` was touched; no Fluxion/Matchline
  integration; no other POC folder was modified; no workflow files.

## 5. What would change the recommendation

* **Slice 2 (extraction wiring):** running the checker over a Matchline
  extraction on real drawings. If the catch rate on real extraction output
  drops below ~80 %, or the false-flag rate on clean real drawings exceeds
  ~10 %, the recommendation is downgraded towards No-go for the verifier as a
  Matchline gate (it would then be usable only as an advisory report).
* **VLM selection (Alex):** until a VLM is chosen, the second-reader half of
  the POC is unmeasured. If the VLM's agreement on the same fixture set is
  poor, or its findings are dominated by hallucinations, the neuro-symbolic
  combination may be dropped in favour of the symbolic checks alone — in
  which case the POC's value proposition (a VLM verifier) is not met and the
  label should become No-go for the VLM variant.
* **A larger, less hand-made error set** (errors sampled from real
  extraction failures rather than injected by hand) would be needed before
  the 100 % catch rate could be quoted as anything more than a smoke test.
* **Closing the "silently deleted opening" gap** (a door removed together
  with its zone reference) would need either a drawing-side cross-check or
  the VLM reader; without one of those, the symbolic checker alone cannot
  claim to cover all eight injected-error families in the wild.

## 6. Verification commands run

```sh
$ python3 -m pytest drawing-verifier/tests/ -q
41 passed in 1.32s

$ python3 drawing-verifier/run_headline.py
...
HEADLINE  catch rate 100.0% (12/12)   false-flag rate 0.0% (0/3)   worst geometry error 0.10%
```

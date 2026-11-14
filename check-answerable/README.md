# check-answerable (issue #56, Phase 0 slice 1, Parts A + B)

**Status:** Slice 1 Parts A + B complete — a frozen, hand-labelled set of 24
questions and a standalone, table-only `check_answerable` prototype. **Part C
is not done — awaiting Route B returns.**

A frozen question set and a pure capability table that answers *“can this
question be answered from this sheet?”* — **without any LLM classification**:
the caller states the question class explicitly.

This folder is **standalone**: stdlib only, no model/API call, no detector, no
parser, no server, no import from any other folder of this repository. It
touches nothing outside `check-answerable/`.

---

## 1. Files

| File | What it is |
| --- | --- |
| `frozen_questions.json` | **Part A** — the 24 hand-labelled questions: id, question text, question class, sheet type, label (`answerable`/`partial`/`unanswerable`), per-question evidence citation. Frozen at 2026-11-14, **before** the prototype was run against it. |
| `capability_table.py` | **Part B** — the capability-table function `capability(question_class, sheet_type)` and the closed vocabularies (verdicts, reason codes, question classes, sheet types). |
| `run_agreement.py` | Runs the frozen set through the table and prints the raw per-class agreement table, the disagreements, the false-answerable count and the gate verdict. |
| `tests/` | pytest suite pinning every frozen label against the table function, plus the reason-code and gate disciplines. |
| `REPORT.md` | The slice report: raw agreement table, disagreements, gate verdict, claims, limits. |

Reproduce everything with two commands:

```sh
python3 -m pytest check-answerable/ -q
python3 check-answerable/run_agreement.py
```

## 2. The capability model (primitives → table)

The table is not a list of memorized answers; it is derived from a small set
of *capability primitives* by an explicit, ordered rule list.

**Primitives**

* *Sheet types* and whether they are processed: `elevation`, `floor_plan`,
  `section`, `schedule` are the processed domains; `*_raster` variants carry
  no vector geometry; `elevation_unscaled` has no verified drawing scale.
* *Detectors*: window detection exists for elevation sheets; **no** door
  detector exists (doors appear only as outlines).
* *Parsers*: schedule tables are **not** parsed; floor-plan and section sheets
  are **not** processed at all.
* *Precision*: window width is not recoverable at schedule precision.

**Documented question classes** (issue #56, Part A class table)

| Question class | Sheet | Base verdict | Reason code |
| --- | --- | --- | --- |
| `elevation_window_count` | elevation | covered | — |
| `elevation_window_band_count` | elevation | covered | — |
| `elevation_sill_height` | elevation | covered | — |
| `elevation_head_height` | elevation | covered | — |
| `elevation_door_count` | elevation | uncovered | `outline_only_not_detected` |
| `floor_plan_extraction` | floor_plan | uncovered | `sheet_not_processed` |
| `section_extraction` | section | uncovered | `sheet_not_processed` |
| `schedule_extraction` | schedule | uncovered | `no_parser` |
| `window_width_at_schedule_precision` | schedule | partial | `precision_insufficient` |

**Rule order** (`capability()` applies the first rule that fires)

1. unknown class / sheet type → raises `UnknownQuestionClass` /
   `UnknownSheetType` (a closed vocabulary, not a soft verdict);
2. raster sheet → `raster_missing` (covered classes drop to *uncovered*,
   the partial class keeps *partial*);
3. sheet type not processed → *uncovered* / `sheet_not_processed`;
4. sheet type is not the class's own domain → *uncovered* /
   `sheet_not_processed`; the single exception is
   `window_width_at_schedule_precision` on an elevation → *partial* /
   `precision_insufficient` (the elevation gives a width, but not at schedule
   precision);
5. sheet scale unverified and the class needs a measured length (sill/head
   height) → *partial* / `scale_unverified`;
6. otherwise the class's documented base verdict and reason code.

**Reason codes** (closed set, from issue #56): `no_detector`,
`outline_only_not_detected`, `sheet_not_processed`, `precision_insufficient`,
`scale_unverified`, `no_parser`, `raster_missing`. A *covered* row carries
`reason_code = None` — there is no degradation to explain; every *partial* and
*uncovered* row carries exactly one code from the closed set (asserted by the
tests).

## 3. The gate

Proceed requires **≥ 90 % overall agreement AND zero false-answerable** (a
question labelled `unanswerable` that comes back fully answerable). The
false-answerable count is reported as a headline number of its own, never
averaged into the agreement rate. See `REPORT.md` for the measured result.

## Claims

- [observed] The frozen question set holds 24 hand-labelled questions, each with a question class, a sheet type, a label and an evidence citation — source: `check-answerable/frozen_questions.json` (n = 24).
- [observed] Every one of the 24 frozen labels matches the verdict the capability table returns for its (class, sheet type) pair — source: `python3 -m pytest check-answerable/ -q` (43 passed) and `python3 check-answerable/run_agreement.py` (24/24 = 100.0 %).
- [observed] No question labelled `unanswerable` was classified fully answerable — source: `python3 check-answerable/run_agreement.py` (false-answerable: 0).
- [inference] The prototype's table is consistent with the issue's documented class table on every frozen question — from the 24/24 agreement and 0 false-answerable cited above.
- [unsupported] That agreement is *not* independent validation of the documented classes — carried as an assumption; the table and the labels share one source (the issue's class table), so the run is a consistency check, not a second opinion; it is not a premise for any verdict in this artifact.
- [decision] Part C is not attempted in this slice — operator, 2026-11-14.

# REPORT — check-answerable, issue #56 Phase 0 slice 1 (Parts A + B)

**Proceed (for this slice's scope only)** — the frozen set and the capability
table agree on 24/24 = 100.0 % of questions, with **zero** false-answerable
questions. Part C was **not** attempted.

* Scope: **Part A** (frozen, hand-labelled question set) and **Part B**
  (standalone, table-only `check_answerable` prototype + agreement run).
* **Not** in this slice: Part C (Route B comparison — not done, awaiting Route B
  returns), Phase 1, any LLM classification, any detector/parser/server work,
  any edit outside `check-answerable/`.
* Verdict scope: this is a **consistency check between a hand-written label set
  and a hand-written capability table that share one source** (the issue's
  documented class table). It is *not* independent validation of those classes,
  and it says nothing about Matchline's real extraction behaviour — no
  extraction was run.

---

## 1. What was built

* `check-answerable/frozen_questions.json` — **Part A**. 24 questions
  hand-labelled `answerable` / `partial` / `unanswerable`, each with a
  question class, a sheet type and a per-question evidence citation. Frozen
  (i.e. written down) **before** the prototype was run against it.
* `check-answerable/capability_table.py` — **Part B**. The capability-table
  function `capability(question_class, sheet_type) -> Capability`, the closed
  vocabularies (verdicts, reason codes, question classes, sheet types), and
  the capability primitives (sheet processing, detector inventory, parser
  inventory, precision limits) the table is derived from. Stdlib only; no LLM
  call, no model, no network; the caller passes the question class explicitly.
* `check-answerable/run_agreement.py` — one command that runs the frozen set
  through the table and prints the raw per-class table, the disagreements, the
  false-answerable count and the gate verdict.
* `check-answerable/tests/` — 43 pytest tests, of which 24 are the pinning
  test (one per frozen question: the frozen label must equal the table's
  verdict), plus reason-code, closed-vocabulary, no-false-answerable and gate
  tests.

## 2. Headline — agreement per class (raw)

Command:

```sh
python3 check-answerable/run_agreement.py
```

Output (verbatim):

```
check-answerable - capability-table agreement on the frozen set
frozen set: check-answerable/frozen_questions.json (n = 24)

RAW PER-CLASS AGREEMENT TABLE
question_class                         n  agree  agreement  expected_label actual_label  false_ans
elevation_window_count                 4      4     100.0%  answerable    answerable    0
elevation_window_band_count            3      3     100.0%  answerable    answerable    0
elevation_sill_height                  3      3     100.0%  answerable    answerable    0
elevation_head_height                 2      2     100.0%  answerable    answerable    0
elevation_door_count                  3      3     100.0%  unanswerable  unanswerable  0
floor_plan_extraction                 2      2     100.0%  unanswerable  unanswerable  0
section_extraction                    2      2     100.0%  unanswerable  unanswerable  0
schedule_extraction                   2      2     100.0%  unanswerable  unanswerable  0
window_width_at_schedule_precision     3      3     100.0%  partial       partial       0
OVERALL                               24     24     100.0%  -             -             0

overall agreement: 24/24 = 100.0%  (gate: >= 90%)
false-answerable (unanswerable question returned as fully answerable): 0

DISAGREEMENTS (0) - none

GATE: Proceed (overall agreement meets; false-answerable zero)
```

**False-answerable count: 0.** No question labelled `unanswerable` (Q13–Q21,
9 questions) was classified fully answerable. This is the headline discipline
and it is reported on its own line, not folded into the agreement rate.

## 3. Disagreements

**None.** Every one of the 24 frozen questions agrees with the capability
table, so there is no expected-vs-actual list to print. The machinery that
would print it (`run_agreement.py`, section "DISAGREEMENTS") is exercised by
the test suite only on the agreeing path; if a future label or table row
disagreed, the runner prints the question id, expected verdict, actual verdict
and the reason code for each.

## 4. The gate

| Gate condition | Required | Measured | Holds |
| --- | --- | --- | --- |
| Overall agreement | ≥ 90 % | 100.0 % (24/24) | yes |
| False-answerable | 0 | 0 | yes |

**Proceed** — for the scope of Parts A + B only. Part C remains **not done —
awaiting Route B returns**.

## 5. Label discipline

* The labels were written down **before** the prototype was run: the frozen
  set file was created first, and the prototype function was written
  afterwards, against the class table rather than against the answers.
* **No label was changed after a run.** The frozen file as committed is the
  file the run used; `frozen_at` in the file records 2026-11-14.
* Every label carries a per-question evidence citation naming the issue's
  documented class row it derives from (e.g. Q13 → *issue #56 Part A class
  table row 'elevation doors' -> uncovered*).

### 5.1 A gap in the evidence source, reported rather than papered over

The issue file (`ISSUE.md`) was **not present in this worktree** at labelling
time — the worktree contains only the repository folders, and no `ISSUE.md`
file. The labels were therefore derived from the issue's documented class
table **as enumerated verbatim in the Phase 0 slice 1 brief**:

* covered — elevation window counts, elevation window bands, elevation
  sill-head heights;
* uncovered — elevation doors, floor-plan/section extraction, schedules;
* partial — window width at schedule precision.

Each frozen question's `evidence` field cites that enumeration row-by-row, and
the file's `evidence_source` field records that the issue file itself was
absent. If the issue text differs from the brief's enumeration, the labels —
not the table — are what would need re-derivation, and the affected rows are
the nine class rows listed above.

## 6. Honest limits of this result

* **The run is a consistency check, not independent validation.** Both the
  labels and the table are derived from the same documented class table, so
  100 % agreement says the table faithfully encodes the documented model; it
  does not independently confirm that the model is right about Matchline.
* **No extraction was run.** Nothing here measures real drawing-to-BEM
  behaviour; the prototype is a table, and the sheets are not read.
* **No LLM classification.** The prototype accepts an explicit question class
  from the caller. It cannot classify a free-text question, and it does not
  try to; classification is out of scope for this slice.
* **Reason codes outside the frozen set.** `raster_missing` and
  `scale_unverified` are reachable in the table (raster sheet variants, and
  the unscaled elevation) but are not exercised by the 24 frozen questions,
  because the issue documents class-level verdicts and not sheet-quality
  variants. They are pinned by unit tests instead.
* **Part C** (comparison against Route B returns) is **not done — awaiting
  Route B returns**; it was not attempted.

## 7. Files touched

* `check-answerable/frozen_questions.json` (new)
* `check-answerable/capability_table.py` (new)
* `check-answerable/run_agreement.py` (new)
* `check-answerable/tests/conftest.py` (new)
* `check-answerable/tests/test_capability_table.py` (new)
* `check-answerable/README.md` (new)
* `check-answerable/REPORT.md` (new)
* `WORKER_REPORT.md` (new, worktree root)

No existing folder, POC, detector, MCP server, Route B package or matchline
repo file was modified.

## Claims

- [observed] The frozen set holds 24 hand-labelled questions with per-question evidence citations — source: `check-answerable/frozen_questions.json` (n = 24, `frozen_at` 2026-11-14).
- [observed] The capability table agrees with every frozen label: 24/24 = 100.0 % overall, 100.0 % in every one of the nine classes — source: `python3 check-answerable/run_agreement.py` (raw table, section 2).
- [observed] False-answerable count is 0 — no `unanswerable` question was classified fully answerable — source: `python3 check-answerable/run_agreement.py` (false-answerable: 0) and `python3 -m pytest check-answerable/ -q` (43 passed).
- [observed] The suite pins each of the 24 frozen labels individually against `capability(question_class, sheet_type)` — source: `check-answerable/tests/test_capability_table.py` (`test_frozen_label_is_pinned_against_the_capability_table`, 24 parametrized cases).
- [observed] The issue file `ISSUE.md` was not present in the worktree at labelling time — source: `find . -name "ISSUE*" -not -path "./.git/*"` (no output) in the worktree root.
- [inference] The prototype's table is a faithful encoding of the issue's documented class table — from the 24/24 agreement, the 0 false-answerable count, and the class-by-class rows cited above.
- [unsupported] That the documented class table is itself correct about Matchline's real capabilities — carried as an assumption; no extraction was run, so it is NOT a premise for the verdict above and it must not be read as one.
- [unsupported] That 100 % agreement demonstrates the approach would survive a genuinely independent label set — carried as an assumption; the labels and the table share one source, so this is a consistency check only.
- [decision] Label this slice Proceed for Parts A + B, and leave Part C undone pending Route B returns — operator, 2026-11-14.

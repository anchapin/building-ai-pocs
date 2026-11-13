# REPORT — drawing-verifier, SLICE 1 + SLICE 2 + SLICE 3 (symbolic checker)

**Conditional** — the symbolic-checker half of the POC is demonstrated
and measured on this slice's hand-built fixtures; the VLM second-reader half
is deferred pending VLM selection, and no Matchline extraction run was
performed in this slice.

* POC: VLM + neuro-symbolic verifier hardening drawing-to-BEM (Matchline).
* Slice 1 scope: the symbolic checker, its fixtures, its injected-error test
  set, and the geometry-error measurement.
* Slice 2 scope (this addendum, section 7 onwards): checker hardening only —
  a schedule/geometry count-consistency cross-check, a larger injected-error
  set (24 cases) and more clean fixtures (6).  Slice 2 did **not** wire the
  VLM and did **not** run any Matchline extraction.
* Not in this slice: any VLM wiring, any Matchline extraction run, any
  integration with Fluxion or Matchline, any other POC in this repo.
* Slice 3 scope (the addendum at the end of this file, section 13 onwards):
  checker hardening only — a shared-wall zone-membership check (check 6), a
  shared-wall door added to a clean fixture, three new injected cases (27 in
  total) and six clean fixtures.  Slice 3 did **not** wire the VLM and did
  **not** run any Matchline extraction.

---

## 1. What was built

* `drawing-verifier/checker.py` — pure-Python (stdlib only) checker:
  schema validation, four symbolic checks (zone closure, wall adjacency,
  window-to-wall ratio, schedule-symbol cross-check), a `SecondReader`
  protocol plus a `NoVLMSecondReader` stub, and a CLI that exits non-zero
  when findings exist. *(Slice 2 added a fifth check, the
  schedule/geometry count-consistency cross-check — see section 7.)*
* `drawing-verifier/fixtures/` — three hand-built clean buildings
  (`small_office`, `two_unit_house`, `studio_loft`), each with a
  hand-built reference model (`*.reference.json`) whose floor areas and WWRs
  were computed by hand arithmetic, plus a 12-case injected-error set
  (`fixtures/injected/`, listed in `fixtures/injected/cases.json`).
  *(Slice 2: six clean fixtures and 24 injected cases.)*
* `drawing-verifier/run_headline.py` — one command that reproduces the
  headline table (catch rate, false-flag rate, geometry error).
* `drawing-verifier/tests/` — 41 pytest tests covering the schema, the four
  checks, the injected-error set end-to-end, the false-flag measurement and
  the geometry arithmetic. *(Slice 2: 58 tests.)*
* `drawing-verifier/README.md` — the input schema, the checks, the
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

*(Slice 2 re-measured this table on a larger fixture set — 24/24 caught,
0/6 false flags, 0.10 % worst geometry error; see the slice-2 addendum in
section 8.)*

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
  reader, or a drawing-side cross-check. *(Slice 2 closed the part of this
  gap that can be closed inside the model — see the slice-2 addendum,
  section 9, for exactly what is now caught and what is still not.)*
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

---

# SLICE 2 ADDENDUM — checker hardening

Base commit of this slice: `5bc2090e24e97b255e3a1b3c29c5aee21b13f6c9`
(`origin/main` as cut for this worktree).  Everything below was done inside
`drawing-verifier/` only; nothing else in the repo was touched.

## 7. What slice 2 added

### 7.1 A schedule/geometry count-consistency cross-check (new check 5)

Slice 1 stated the gap honestly: *"a door deleted together with its zone
reference is invisible — the checker sees reference integrity, not drawing
intent"*.  Slice 2 closes that gap **inside the model**, using the schedule
table as a second source of truth: a schedule entry may now declare *how
many* elements carry its mark.

Schema extension (optional, backwards compatible):

```json
{"tag_id": "t_door_01", "symbol": "D01", "value": "Single swing door 900 x 2100",
 "kind": "door", "count": 1}
```

* `kind` — one of `opening` (default), `door`, `window`, `zone`.
* `count` — a positive integer: the quantity the schedule declares.
* A schedule entry **without** `count` takes no part in the new check, so a
  schedule table carrying no quantities stays silent (no false flags).
* The validator rejects a non-positive or non-integer `count` and an unknown
  `kind` as `schema_invalid`.

New check function `checker.check_schedule_geometry_consistency`, registered
in `checker.CHECKS` as `schedule_geometry_consistency`.  It emits three
error classes:

| Error class | What it compares | Fires when |
| --- | --- | --- |
| `schedule_geometry_count_mismatch` | schedule quantity vs the number of geometry openings carrying that tag (filtered by `kind`) | an opening was silently deleted, duplicated, re-tagged or re-classified, or the schedule quantity is wrong |
| `zone_schedule_count_mismatch` | a zone-level schedule mark (`kind: "zone"`) vs the length of that zone's opening list | the zone's opening list no longer matches the quantity the schedule declares for the zone |
| `zone_opening_not_listed` | the geometry openings vs the zone opening lists | an opening hosted on a wall that belongs to exactly one zone is not listed in that zone (only the zone reference was dropped) |

Scope notes (how false positives were avoided):

* the global count check only looks at schedule entries that carry a
  `count`, so it never guesses;
* `zone_opening_not_listed` stays quiet when the host wall is shared by
  several zones, because such a wall has no unambiguous owner (asserted by
  `tests/test_schedule_consistency.py::test_shared_wall_openings_are_not_reported_as_unlisted`);
* the check is skipped entirely when the model is schema-invalid (the
  checker reports `schema_invalid` and does not run semantic checks — this
  behaviour was not changed).

### 7.2 The silently-deleted-opening case, before and after the check

`fixtures/injected/small_office_dropped_door.json` deletes the door `d1`
from the geometry **and** from the zone's opening list, while the schedule
still lists one door.  Proof that the new check is what catches it:

```
$ python3 - <<'EOF'
import json, sys
sys.path.insert(0, '.')
import checker
model = json.load(open('fixtures/injected/small_office_dropped_door.json'))
checker.CHECKS = tuple(c for c in checker.CHECKS if c[0] != 'schedule_geometry_consistency')
r = checker.check_model(model)
print("WITHOUT the new check: n_findings =", r["n_findings"], "classes =", r["error_classes"])
checker.CHECKS = tuple(c for c in checker.CHECKS)
import importlib; importlib.reload(checker)
r2 = checker.check_model(model)
print("WITH    the new check: n_findings =", r2["n_findings"], "classes =", r2["error_classes"])
EOF
WITHOUT the new check: n_findings = 0 classes = []
WITH    the new check: n_findings = 2 classes = ['schedule_geometry_count_mismatch', 'zone_schedule_count_mismatch']
```

The same discriminating test exists as a pytest case
(`test_dropped_door_with_dropped_zone_ref_is_silent_without_the_check` and
`test_dropped_window_with_dropped_zone_ref_is_flagged`), so the gap cannot
silently reopen.

### 7.3 Fixture and error-set growth

| | before (slice 1) | after (slice 2) |
| --- | --- | --- |
| clean fixtures (with hand-built reference models) | 3 | **6** |
| injected-error cases | 12 | **24** |
| checker checks | 4 | **5** |
| pytest tests | 41 | **58** |

New clean fixtures (all with a `*.reference.json` holding hand-computed
floor areas and WWRs, and the arithmetic written out in the file):

| Fixture | Geometry | Zones |
| --- | --- | --- |
| `classroom_block.json` | 8.0 x 6.0 m classroom + 8.0 x 2.0 m corridor sharing a wall | `z_classroom` (48.0 m2), `z_corridor` (16.0 m2) |
| `l_shaped_retail.json` | 12.0 x 8.0 m minus a 4.0 x 3.0 m notch, glazed shopfront | `z_shop` (84.0 m2) |
| `three_room_apartment.json` | 12.0 x 9.0 m split into living / kitchen / bathroom | `z_living` (63.0 m2), `z_kitchen` (20.0 m2), `z_bath` (25.0 m2) |

New injected cases (12): `small_office_dropped_door`,
`small_office_dropped_window`, `small_office_schedule_count_wrong`,
`small_office_zone_count_wrong`, `two_unit_house_retagged_window`,
`two_unit_house_door_kind_swapped`, `two_unit_house_zone_ref_dropped`,
`classroom_block_dropped_window`, `l_shaped_retail_extra_window`,
`l_shaped_retail_unclosed_loop`, `l_shaped_retail_duplicate_symbol`,
`studio_loft_negative_count`.

The three original clean fixtures were **not** deleted; they were given the
optional schedule quantities (`kind` / `count`) so that the new check is
exercised on them as well.  Their geometry and their hand-built reference
models are unchanged.

## 8. Re-measured headline numbers (slice 2)

`python3 drawing-verifier/run_headline.py`:

| Metric | Slice 1 | **Slice 2** | POC Go bar | Holds? |
| --- | --- | --- | --- | --- |
| Injected errors caught | 12 / 12 = 100 % | **24 / 24 = 100 %** | >= 80 % | yes |
| False-flag rate on clean fixtures | 0 / 3 = 0.0 % | **0 / 6 = 0.0 %** | < 10 % | yes |
| Worst geometry error vs hand-built model | 0.10 % | **0.10 %** | < 5 % | yes |

Per-error-class catch table (slice 2):

| Error class | Injected | Caught | Catch rate |
| --- | --- | --- | --- |
| `opening_host_missing` | 1 | 1 | 100 % |
| `opening_outside_wall` | 1 | 1 | 100 % |
| `opening_overlap` | 1 | 1 | 100 % |
| `schedule_duplicate_tag` | 1 | 1 | 100 % |
| `schedule_geometry_count_mismatch` | 7 | 7 | 100 % |
| `schedule_symbol_duplicate` | 2 | 2 | 100 % |
| `schedule_tag_missing` | 1 | 1 | 100 % |
| `schema_invalid` | 3 | 3 | 100 % |
| `wwr_out_of_band` | 1 | 1 | 100 % |
| `zone_not_closed` | 3 | 3 | 100 % |
| `zone_opening_missing` | 1 | 1 | 100 % |
| `zone_opening_not_listed` | 1 | 1 | 100 % |
| `zone_schedule_count_mismatch` | 6 | 6 | 100 % |
| **total** | **24** | **24** | **100 %** |

The false-flag measurement now covers **all six** clean fixtures (0 findings
on each).  The geometry-error measurement now covers 6 fixtures / 13 zones /
8 walls; the worst deviation is still 0.10 % (the `studio_loft` rounding
artefact 1/3 vs 0.3333), every other deviation is <= 0.05 %.

## 9. Is the "silently deleted opening" gap closed?

**Partly — and the boundary is now explicit.**

Closed by slice 2 (all of these are in the injected set and are caught):

* an opening deleted from the geometry **and** from its zone reference,
  while the schedule still lists it (`small_office_dropped_door`,
  `small_office_dropped_window`, `classroom_block_dropped_window`);
* an opening re-tagged to another schedule mark, so the mark counts no
  longer agree with the geometry (`two_unit_house_retagged_window`);
* an opening re-classified (door -> window) so the "door" quantity no longer
  agrees with the geometry (`two_unit_house_door_kind_swapped`);
* an extra opening added to the geometry (`l_shaped_retail_extra_window`);
* only the zone reference dropped, the opening itself surviving in the
  geometry (`two_unit_house_zone_ref_dropped` -> `zone_opening_not_listed`
  and `zone_schedule_count_mismatch`).

**Still NOT covered (stated plainly):**

* **An opening deleted from the geometry, from the zone references AND from
  the schedule at the same time is still invisible.**  Every count in the
  model then agrees with every other count; there is nothing left to
  disagree with.  This case is *not* in the injected set because the checker
  cannot catch it — only a drawing-side reader (the deferred VLM second
  reader) could.
* The same is true for an opening that was **never in the schedule** (a
  schedule table that carries no quantities at all): the count check has
  nothing to compare against and stays silent by design.
* A zone whose schedule mark has no `count` is not judged at all, so a zone
  opening list can drift silently in that case.
* An opening hosted on a wall **shared by several zones** is not checked for
  zone membership (no unambiguous owner), so a wrong zone assignment for
  such an opening is not reported.
* The count check compares *quantities*, not *positions*: a door that was
  deleted and a spurious one added, keeping the count equal, is not
  detected by check 5 (it may still be caught by the geometry checks, e.g.
  if the spurious door is misplaced).
* The check compares the model against itself (schedule vs geometry).  It
  does not compare either of them against the drawing.

## 10. What slice 2 still does not do

* **No VLM selection or wiring.**  `checker.SecondReader` remains a
  protocol and `checker.NoVLMSecondReader` remains a stub that always
  returns `agree=None`.  No model was selected, downloaded, called or
  paid for; there is no agreement number to report, and none is invented.
  This is still deferred pending an Alex decision.
* **No Matchline extraction run, and no attempt to reach one.**  The
  isolation rules for this slice forbid fetching, installing or running
  Matchline code; the extraction wiring was deferred by the supervisor and
  was deliberately **not** worked around.  The checker still consumes
  structured-geometry JSON fixtures only.  Consequently the headline numbers
  above describe the checker on fixtures, **not** the checker on Matchline
  output, and this slice makes no claim whatsoever about real Matchline
  extraction.
* **No BEM / energy simulation**; nothing here claims an energy impact,
  an energy-saving figure or ASHRAE 140 compliance.
* Nothing outside `drawing-verifier/` was touched; no Fluxion/Matchline
  integration; no other POC folder was modified; no workflow files; no
  commits, pushes or merges.

## 11. Label reassessment

The label stays **Conditional**.

The slice-2 evidence supports the *symbolic* half a little more strongly
(one more check, 24/24 injected errors caught, 0/6 false flags, three more
clean fixtures), but it does not change the two facts that keep the POC
conditional:

1. the VLM half of the POC is still unmeasured (no reader was selected or
   run), and
2. the checker has still never seen a real extraction, so every number here
   is a self-consistency measurement on hand-built fixtures.

Nothing in slice 2 justifies moving to *Go* (no real-drawing evidence), and
nothing justifies moving to *No-go* (the symbolic checker demonstrably
catches every error family it is aimed at and stays quiet on clean input).

## 12. Verification commands run (slice 2)

```sh
$ python3 -m pytest drawing-verifier/tests/ -q
58 passed in 3.08s

$ python3 drawing-verifier/run_headline.py
...
HEADLINE  catch rate 100.0% (24/24)   false-flag rate 0.0% (0/6)   worst geometry error 0.10%

$ python3 drawing-verifier/checker.py drawing-verifier/fixtures/small_office.json
model: drawing-verifier/fixtures/small_office.json
findings: 0
no findings
$ echo $?
0
```

(The CLI exits 1 on a model with findings, e.g.
`python3 drawing-verifier/checker.py drawing-verifier/fixtures/injected/small_office_dropped_door.json`
prints the two count-mismatch findings and exits 1.)

---

# SLICE 3 ADDENDUM — shared-wall zone membership

(Slices 1 and 2 above are unchanged; this addendum only adds slice 3.)

## 13. What slice 3 added

Slice 2 left one gap open and named it in §9: *"An opening hosted on a wall
shared by several zones is not checked for zone membership (no unambiguous
owner), so a wrong zone assignment for such an opening is not reported."*
Check 5 deliberately stayed quiet there because the owner of a shared wall is
ambiguous.  Slice 3 does not guess the owner — it **defines the membership
rule** and checks the model against it.

### Check 6 — `shared_wall_zone_membership`

New function `checker.check_shared_wall_zone_membership(model)`, registered
in `checker.CHECKS` after `schedule_geometry_consistency`:

```python
CHECKS = (
    ("zone_closure", check_zone_closure),
    ("wall_adjacency", check_wall_adjacency),
    ("window_to_wall_ratio", check_window_to_wall_ratio),
    ("schedule_cross_check", check_schedules),
    ("schedule_geometry_consistency", check_schedule_geometry_consistency),
    ("shared_wall_zone_membership", check_shared_wall_zone_membership),
)
```

It runs only when the model is schema-valid (unchanged behaviour: a
`schema_invalid` model reports the schema findings and no semantic checks
run).  Check 5's behaviour is unchanged — including the
"no unambiguous owner" quiet rule — and is still pinned by
`tests/test_schedule_consistency.py::test_shared_wall_openings_are_not_reported_as_unlisted`.
(Its part-(b) code now calls the shared `_wall_ownership_maps` helper; the
logic is identical.)
The `wall_owners` / `listed_in` maps are now built by a shared helper
(`checker._wall_ownership_maps`) used by check 5 and check 6, so both look at
exactly the same membership data.

**The convention (also documented in `README.md`):** a shared-wall opening is
listed in **exactly one** adjacent zone for takeoff — the zone it "belongs"
to.  The check therefore requires listing in **at least one** adjacent zone
and forbids listing by **any** non-adjacent zone.  Listing the opening in
**both** adjacent zones is **tolerated**, not flagged: a shared wall between
two spaces is a legitimate modelling choice, and inventing a false flag for
it would be worse than saying nothing.

Two error classes:

* `shared_wall_opening_unlisted` — the opening is hosted on a wall shared by
  **two or more** zones and is listed in the `openings` of **none** of those
  adjacent zones: the door survives in the geometry but belongs to no zone.
* `shared_wall_opening_wrong_zone` — the opening is listed in the `openings`
  of a zone that does **not** border its host wall (one finding per offending
  zone).  This applies **regardless of the owner count**, so it also closes
  the hole where a single-owner opening is listed both by its (correct) owner
  — check 5 is quiet there — and by a zone that does not border its host
  wall.

The single-owner *unlisted* case remains check 5's `zone_opening_not_listed`;
check 6 does not duplicate it.  Openings whose host wall does not exist are
left to check 2 (`opening_host_missing`) — their membership is undefined.

## 14. The clean-fixture addition

`fixtures/classroom_block.json` (the fixture that already had a shared wall
`c3` between `z_classroom` and `z_corridor`) now carries an internal door on
that shared wall:

```json
{"id": "d_internal", "kind": "door", "host_wall": "c3", "center_offset": 4.0,
 "width": 0.9, "sill_height": 0.0, "head_height": 2.1, "schedule_tag": "t_door_01"}
```

It is listed in `z_classroom`'s `openings` only (the convention above).
Schedule quantities were updated so that check 5 stays green:
`t_door_01` count 2 → **3** (three doors carry the mark: `d_cls`, `d_cor`,
`d_internal`) and `t_zone_classroom` count 3 → **4** (the zone lists four
openings); `t_zone_corridor` is unchanged (2) because the door is not listed
there.

`fixtures/three_room_apartment.json` was extended the same way, because the
wrong-zone fault needs a zone that does **not** border the shared wall:
`d_internal` on wall `p7` (owned by `z_living` and `z_kitchen`), listed in
`z_living` only, with `t_door_01` count 3 → **4** and `t_zone_living`
count 4 → **5**.  `z_bath` does not border `p7`, which is what the
wrong-zone injected case uses.

**The hand-built reference models did not change.**  A door carries no glass
area (`opening_glass_area` is 0 for doors) and the floor areas are computed
from the wall loops, which were not touched; the re-measured geometry error
below is bit-for-bit the slice-2 measurement (worst 0.10 %, everything else
<= 0.05 %).  No `*.reference.json` file was edited.

All six clean fixtures still produce **0 findings**.

## 15. Re-measured headline numbers (slice 3)

`python3 drawing-verifier/run_headline.py`:

| Metric | Slice 1 | Slice 2 | **Slice 3** | POC Go bar | Holds? |
| --- | --- | --- | --- | --- | --- |
| Injected errors caught | 12 / 12 = 100 % | 24 / 24 = 100 % | **27 / 27 = 100 %** | >= 80 % | yes |
| False-flag rate on clean fixtures | 0 / 3 = 0.0 % | 0 / 6 = 0.0 % | **0 / 6 = 0.0 %** | < 10 % | yes |
| Worst geometry error vs hand-built model | 0.10 % | 0.10 % | **0.10 %** | < 5 % | yes |

Per-error-class catch table (slice 3):

| Error class | Injected | Caught | Catch rate |
| --- | --- | --- | --- |
| `opening_host_missing` | 1 | 1 | 100 % |
| `opening_outside_wall` | 1 | 1 | 100 % |
| `opening_overlap` | 1 | 1 | 100 % |
| `schedule_duplicate_tag` | 1 | 1 | 100 % |
| `schedule_geometry_count_mismatch` | 7 | 7 | 100 % |
| `schedule_symbol_duplicate` | 2 | 2 | 100 % |
| `schedule_tag_missing` | 1 | 1 | 100 % |
| `schema_invalid` | 3 | 3 | 100 % |
| `shared_wall_opening_unlisted` | 1 | 1 | 100 % |
| `shared_wall_opening_wrong_zone` | 2 | 2 | 100 % |
| `wwr_out_of_band` | 1 | 1 | 100 % |
| `zone_not_closed` | 3 | 3 | 100 % |
| `zone_opening_missing` | 1 | 1 | 100 % |
| `zone_opening_not_listed` | 1 | 1 | 100 % |
| `zone_schedule_count_mismatch` | 6 | 6 | 100 % |
| **total** | **27** | **27** | **100 %** |

No prior number regressed: the injected set grew from 24 to 27 cases, the
catch rate stays at 100 %, the false-flag rate stays at 0.0 % and the worst
geometry error stays at 0.10 %.

The three new injected cases (all registered in
`fixtures/injected/cases.json`):

| Variant | Base | Injected fault | Expected class |
| --- | --- | --- | --- |
| `classroom_block_shared_door_unlisted` | `classroom_block` | the shared-wall door `d_internal` is listed in no zone at all | `shared_wall_opening_unlisted` |
| `three_room_apartment_shared_door_wrong_zone` | `three_room_apartment` | the shared-wall door `d_internal` (wall `p7`) is additionally listed in `z_bath`, which does not border `p7` | `shared_wall_opening_wrong_zone` |
| `two_unit_house_door_wrong_zone` | `two_unit_house` | the single-owner door `dA` (wall `ha1`) is additionally listed in `z_unit_b`, which does not border `ha1` | `shared_wall_opening_wrong_zone` |

**Note on how the faults are made "quiet":** in the two cases that add or
remove a zone reference, the corresponding zone quantity mark
(`t_zone_classroom`, `t_zone_bath`, `t_zone_bedroom`) is adjusted to match
the new zone list.  Without that, check 5 (`zone_schedule_count_mismatch`)
would catch the case and it would not be discriminating.  With it, the model
is self-consistent in every other respect and **check 6 is the only check
that fires** — which is exactly what the discriminating tests assert (0
findings with check 6 removed, exactly the one expected class with check 6
present).

## 16. Still not covered (updated §9)

**Now covered by slice 3 (moved out of the §9 "still NOT covered" list):**

* an opening hosted on a wall shared by several zones is now checked for
  zone membership: it must be listed in at least one adjacent zone
  (`shared_wall_opening_unlisted`) and must not be listed by a non-adjacent
  zone (`shared_wall_opening_wrong_zone`).

**Still NOT covered (stated plainly):**

* **An opening deleted from the geometry, from the zone references AND from
  the schedule at the same time is still invisible.**  Every count in the
  model then agrees with every other count; there is nothing left to
  disagree with.  Only a drawing-side reader (the deferred VLM second
  reader) could catch it.
* The same is true for an opening that was **never in the schedule** (a
  schedule table that carries no quantities at all): the count check has
  nothing to compare against and stays silent by design.
* A zone whose schedule mark has no `count` is not judged at all, so a zone
  opening list can drift silently in that case.
* The count check compares *quantities*, not *positions*: a door that was
  deleted and a spurious one added, keeping the count equal, is not
  detected by check 5 (it may still be caught by the geometry checks, e.g.
  if the spurious door is misplaced).
* The check compares the model against itself (schedule vs geometry, zone
  membership vs wall ownership).  It does not compare either of them against
  the drawing.
* Check 6 does not judge *which* adjacent zone owns a shared-wall opening
  (both adjacent zones are acceptable, and the choice between them is a
  modelling decision, not an error).

## 17. Label reassessment (slice 3)

The label stays **Conditional**.

Slice 3 strengthens the symbolic half a little further (sixth check, 27/27
injected errors caught, 0/6 false flags), but the two facts that keep the POC
conditional are unchanged:

1. **the VLM half of the POC is still unmeasured** — no reader was
   selected, downloaded or run, `checker.SecondReader` is still a protocol
   and `checker.NoVLMSecondReader` is still a stub; no agreement number
   exists and none is invented; and
2. **the checker has still never seen a real extraction** — every number in
   this addendum is a self-consistency measurement on hand-built fixtures,
   not on Matchline output.

## 18. Verification commands run (slice 3)

```sh
$ python3 -m pytest drawing-verifier/tests/ -q
74 passed in 0.33s

$ python3 drawing-verifier/run_headline.py
...
HEADLINE  catch rate 100.0% (27/27)   false-flag rate 0.0% (0/6)   worst geometry error 0.10%

$ python3 drawing-verifier/checker.py drawing-verifier/fixtures/classroom_block.json
model: drawing-verifier/fixtures/classroom_block.json
findings: 0
no findings
$ echo $?
0

$ python3 drawing-verifier/checker.py drawing-verifier/fixtures/injected/classroom_block_shared_door_unlisted.json
model: drawing-verifier/fixtures/injected/classroom_block_shared_door_unlisted.json
findings: 1
[error] shared_wall_opening_unlisted: d_internal: opening 'd_internal' is hosted on wall 'c3', which is shared by zones ['z_classroom', 'z_corridor'], but it is listed in none of their opening lists -- it belongs to no zone
$ echo $?
1
```

## Claims

- [observed] Slice-3 headline: 27 / 27 injected errors caught (100 %), 0 / 6 clean fixtures false-flagged (0.0 %), worst geometry error 0.10 % against the hand-built reference models — source: `python3 drawing-verifier/run_headline.py` output quoted in REPORT.md §15 and §18.
- [observed] The earlier slices' headlines were 12 / 12 caught, 0 / 3 false flags, 0.10 % worst geometry error (slice 1) and 24 / 24 caught, 0 / 6 false flags, 0.10 % worst geometry error (slice 2) — source: `python3 drawing-verifier/run_headline.py` output quoted in REPORT.md §6, §8 and §12.
- [observed] Every error class listed in the slice-3 per-class catch table shows a 100 % catch rate, the table's total row reads 27 / 27 (100 %), and no prior number regressed as the injected set grew from 24 to 27 cases — source: REPORT.md §15 per-error-class catch table.
- [observed] The test suite passes in each slice: 41 tests (slice 1), 58 (slice 2), 74 (slice 3) — source: `python3 -m pytest drawing-verifier/tests/ -q` output quoted in REPORT.md §6, §12 and §18.
- [observed] The new count-consistency check (check 5) is what catches the silently-dropped door: with check 5 removed the model yields 0 findings, with it 2 findings (`schedule_geometry_count_mismatch`, `zone_schedule_count_mismatch`) — source: the inline `python3` snippet and its output quoted in REPORT.md §7.2.
- [observed] Check 6 (`shared_wall_zone_membership`) is the only check that fires on the three new shared-wall injected cases: 0 findings with check 6 removed, exactly the one expected class with it present — source: REPORT.md §15 note and the CLI output quoted in REPORT.md §18.
- [observed] All six clean fixtures still produce 0 findings, and no `*.reference.json` file was edited, so the re-measured geometry error is bit-for-bit the slice-2 measurement (worst 0.10 %, every other deviation ≤ 0.05 %) — source: REPORT.md §14 and §15.
- [observed] The checker CLI exits 1 on a model with findings (e.g. `drawing-verifier/fixtures/injected/classroom_block_shared_door_unlisted.json` → 1 finding, exit 1) and 0 on a clean fixture (`drawing-verifier/fixtures/classroom_block.json` → no findings, exit 0) — source: REPORT.md §18 verification output.
- [observed] The checker compares the model against itself (schedule vs geometry, zone membership vs wall ownership) and never against the drawing — source: REPORT.md §9 and §16.
- [observed] An opening deleted from the geometry, from the zone references and from the schedule at the same time is still invisible to the checker, because every count then agrees with every other count — source: REPORT.md §9 and §16.
- [observed] No VLM was selected, downloaded or called: `checker.SecondReader` is a protocol and `checker.NoVLMSecondReader` always returns `agree=None`, so no VLM agreement number exists — source: REPORT.md §4, §10 and §17.
- [observed] No Matchline extraction run was performed; the checker consumes structured-geometry JSON fixtures only — source: REPORT.md §4, §10 and §17.
- [observed] The geometry-error measurement is a self-consistency measurement: the fixtures are hand-built from the same dimensions the checker reads, so it is not evidence about extraction accuracy from real drawings — source: REPORT.md §2.2.
- [inference] The symbolic-checker half of the POC is demonstrated and measured on this slice's hand-built fixtures: the checker catches every injected error family it is aimed at and stays quiet on clean input, with no prior number regressed — from the headline, per-class catch-table and test observations above.
- [inference] The remaining coverage gaps are structural to a model-only checker (model-vs-model comparison), so they cannot be closed inside the checker and require a drawing-side reader — from the self-comparison and still-not-covered observations above.
- [inference] The label cannot move to Go (no real-drawing evidence) and need not move to No-go (the symbolic checker demonstrably catches every error family it is aimed at and stays quiet on clean input) — from the headline and coverage observations above.
- [inference] The 100 % catch rate on hand-made cases is weak evidence: it demonstrates that the checks fire and are quiet on clean input, not that they generalise — from the headline observations above and the known-limits list in REPORT.md §3.
- [unsupported] The WWR band (0.05–0.55) as a plausibility heuristic rather than a code requirement — carried as an assumption; NOT a premise for any verdict in this artifact.
- [unsupported] The convention that a shared-wall opening is listed in exactly one adjacent zone (listing in both adjacent zones is tolerated, not flagged) — carried as an assumption; NOT a premise for any verdict in this artifact.
- [unsupported] Floor areas as centre-line ("clear internal") areas, with wall thickness carried but not added — carried as an assumption; NOT a premise for any verdict in this artifact.
- [decision] Label this POC Conditional: the symbolic-checker half is demonstrated and measured on the slice's hand-built fixtures, the VLM second-reader half is deferred pending VLM selection, and no Matchline extraction run was performed — operator, 2026-11-06.

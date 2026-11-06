# VLM + Neuro-Symbolic Drawing Verifier

**Status:** Slice 1 in progress — symbolic checker implemented and measured on
hand-built fixtures. The VLM second reader is **not** wired (deferred; see
`REPORT.md`).

Hardens drawing-to-BEM (Matchline) by catching hallucinations and injected
errors before simulation.

This slice is **standalone**: the checker consumes structured-geometry JSON
fixtures.  It is *not* wired into Matchline extraction, into Fluxion, or into
any other POC in this repo, and it makes no model/API calls.

See the repo README for the POC rules: 25–40 hours, standalone, fixed
go/no-go gate, REPORT.md leading with exactly one label (Go, Go (software
only), Conditional, or No-go).

---

## 1. Input format (structured geometry, JSON)

The checker reads one JSON document per building.  The schema is small and
explicit; every file under `fixtures/` validates against it.

```jsonc
{
  "schema_version": 1,
  "project": "small_office",        // optional free-text label
  "units": "m",                     // optional, only "m" is used
  "description": "...",             // optional free-text label

  "walls": [
    {
      "id": "w1",                   // unique wall id
      "start": [0.0, 0.0],          // [x, y] in metres, numbers
      "end":   [6.0, 0.0],          // [x, y] in metres, numbers
      "thickness": 0.2,             // metres, > 0
      "height": 3.0                 // metres, > 0 (default 3.0 if omitted)
    }
  ],

  "openings": [
    {
      "id": "d1",                          // unique opening id
      "kind": "door",                      // "door" | "window"
      "host_wall": "w1",                   // id of the wall it sits in
      "center_offset": 1.0,                // metres from the wall start point
      "width": 0.9,                        // metres, > 0
      "sill_height": 0.0,                  // metres
      "head_height": 2.1,                  // metres, > sill_height
      "schedule_tag": "t_door_01"          // optional tag id into "schedules"
    }
  ],

  "zones": [
    {
      "id": "z_office",                     // unique zone id
      "name": "Office",                     // optional label
      "wall_loop": ["w1", "w2", "w3", "w4"],// ordered wall ids forming the loop
      "openings": ["d1", "win1"],           // opening ids belonging to the zone
      "schedule_tag": "t_zone_office"       // optional tag id into "schedules"
    }
  ],

  "schedules": [
    {
      "tag_id": "t_door_01",                // unique tag id
      "symbol": "D01",                      // drawing symbol
      "value": "Single swing door 900 x 2100"
    }
  ]
}
```

Rules the schema validator enforces (`checker.validate_model`):

* `schema_version` must be `1`; `walls`, `openings`, `zones` and `schedules`
  must all be present lists.
* ids are unique non-empty strings; every coordinate is a number (`bool` is
  rejected); wall `thickness` and `height` are positive; opening `width` is
  positive and `head_height > sill_height`.
* an opening must carry a `host_wall` string (the *existence* of that wall is
  a checker finding, not a schema error — see check 2).
* a zone's `wall_loop` must list at least three wall ids.

Validation failures are reported as findings with the error class
`schema_invalid`, with the offending element id (e.g. `l1`, `winL`).

## 2. The four checks

All checks run in `checker.py` and return structured findings
`{error_class, element_id, reason, severity}`.

### Check 1 — Zone closure (`zone_closure`)

Walks each zone's `wall_loop` in order (a wall may be listed in either
direction) and requires consecutive walls to meet and the last wall to close
back onto the first point.

* **Tolerance:** `TOLERANCE_M = 0.05` m (stated in `checker.py`).
* `zone_not_closed` — the loop has a gap larger than the tolerance.
* `zone_loop_unknown_wall` — the loop cites a wall that does not exist.
* `zone_zero_area` — the loop closes but encloses no area
  (shoelace area <= 1e-6 m2).

### Check 2 — Wall adjacency (`wall_adjacency`)

* `opening_host_missing` — the opening's `host_wall` does not exist.
* `opening_outside_wall` — the opening does not lie within the host wall's
  span (the opening's `[center_offset - width/2, center_offset + width/2]`
  interval must fit inside `[0, wall length]`, tolerance 0.05 m).
* `opening_overlap` — two openings on the same wall overlap by more than the
  tolerance.
* `zone_opening_missing` — a zone references an opening id that does not
  exist (this is how a *deleted* door is caught).

### Check 3 — Window-to-wall ratio sanity (`window_to_wall_ratio`)

Glazed area of a window = `width * (head_height - sill_height)`.
Wall WWR = glazed area on that wall / (`length * height`).
Zone WWR = glazed area of the windows hosted on the zone's loop walls / zone
floor area.

* **Plausible band: `0.05 <= WWR <= 0.55`** (stated in `checker.py` as
  `WWR_BAND`).  A breach is *flagged* (`wwr_out_of_band`, severity
  `warning`) — the ratio is never silently clamped.
* The band is applied only to walls and zones that actually carry glazing; a
  wall or zone with no windows is exempt (zero glazing is legal).
* The WWR of a zone whose loop does not close is not judged (the area is
  undefined); the closure check already reports that.

### Check 4 — Schedule-symbol cross-check (`schedule_cross_check`)

* `schedule_tag_missing` — a zone or opening references a schedule tag that
  is not in the schedule table (dangling reference).
* `schedule_symbol_duplicate` — one schedule symbol maps to more than one tag
  (e.g. a swapped symbol).
* `schedule_duplicate_tag` — the same `tag_id` is defined more than once.

## 3. Running it

```sh
# run the checker on one model (exit code 1 when findings exist)
python3 drawing-verifier/checker.py drawing-verifier/fixtures/small_office.json
python3 drawing-verifier/checker.py drawing-verifier/fixtures/small_office.json --json

# run the test suite
python3 -m pytest drawing-verifier/tests/ -q

# reproduce the headline table (catch rate, false flags, geometry error)
python3 drawing-verifier/run_headline.py
```

Pure Python 3, standard library only (no third-party dependencies, no
network access, no VLM calls).

## 4. Second reader (VLM) — interface only, not wired

`checker.SecondReader` is a `Protocol`: a reader takes the structured
geometry plus a drawing reference and returns `agree` / `reason`.
`checker.NoVLMSecondReader` is the stub implementation; it always returns
`agree=None` with the reason "no VLM configured" and is never used to pass or
fail anything.  The VLM agreement measurement is deferred pending VLM
selection (an Alex decision) — see `REPORT.md`.

## 5. Layout

```
drawing-verifier/
  checker.py            schema validation, the four checks, SecondReader stub
  run_headline.py       one-command headline table
  fixtures/             3 clean fixtures + reference models + injected-error set
  tests/                pytest suite
  REPORT.md             slice-1 report (label: Conditional)
```

# Fixtures

Three hand-built clean buildings plus an injected-error set.  Every clean
fixture has a matching `*.reference.json` holding a **hand-built** reference
model (floor area and WWR per zone/wall) whose arithmetic is written out in
the `arithmetic` field of that file.  The reference numbers were computed by
hand from the dimensions, independently of `checker.py`.

| Fixture | Geometry | Zones | Area (hand) | WWR (hand) |
| --- | --- | --- | --- | --- |
| `small_office.json` | 6.0 x 4.0 m rectangle, 3.0 m high | `z_office` | 6.0 x 4.0 = 24.0 m2 | 3.6 / 24.0 = 0.150 |
| `two_unit_house.json` | 5.0 x 4.0 m + 4.0 x 4.0 m units sharing a wall | `z_unit_a`, `z_unit_b` | 20.0 m2, 16.0 m2 | 2.4 / 20.0 = 0.120, 1.44 / 16.0 = 0.090 |
| `studio_loft.json` | L-shape: 6.0 x 4.0 m minus a 2.0 x 2.0 m notch | `z_studio` | 24.0 - 4.0 = 20.0 m2 | 6.0 / 20.0 = 0.300 |

Glazed areas (hand arithmetic):

* `small_office`: 2 windows x 1.5 m x (2.1 - 0.9) m = 2 x 1.8 = 3.6 m2;
  host wall `w3` gross area 6.0 x 3.0 = 18.0 m2 -> wall WWR 0.200.
* `two_unit_house`: `winA` 2.0 x (2.2 - 1.0) = 2.4 m2, `winB` 1.2 x 1.2 = 1.44 m2;
  host walls `ha3` 5.0 x 3.0 = 15.0 m2 -> 0.160, `hb3` 4.0 x 3.0 = 12.0 m2 -> 0.120.
* `studio_loft`: 1 window 3.0 x (2.5 - 0.5) = 6.0 m2; host wall `l1`
  6.0 x 3.0 = 18.0 m2 -> 0.333.

Floor areas are measured on wall centre lines (shoelace polygon area); wall
thickness is carried in the model but not added to the area.

## Injected-error set (`fixtures/injected/`)

`cases.json` lists every variant, the clean fixture it derives from, the
injected error and the error class the checker must report.

| Variant | Injected error | Expected class |
| --- | --- | --- |
| `small_office_missing_door.json` | door `d1` deleted | `zone_opening_missing` |
| `small_office_scaled_wall.json` | wall `w3` scaled x2 | `zone_not_closed` |
| `small_office_swapped_symbol.json` | schedule symbol swapped | `schedule_symbol_duplicate` |
| `small_office_unclosed_loop.json` | zone loop unclosed | `zone_not_closed` |
| `small_office_orphan_door.json` | door with no host wall | `opening_host_missing` |
| `small_office_duplicate_tag.json` | duplicate schedule tag | `schedule_duplicate_tag` |
| `two_unit_house_dangling_tag.json` | dangling schedule reference | `schedule_tag_missing` |
| `two_unit_house_overlapping_windows.json` | overlapping windows on one wall | `opening_overlap` |
| `studio_loft_window_too_long.json` | window longer than its host wall | `opening_outside_wall` |
| `studio_loft_over_glazed.json` | window-to-wall ratio above the band | `wwr_out_of_band` |
| `studio_loft_bad_coordinate.json` | non-numeric coordinate (malformed) | `schema_invalid` |
| `studio_loft_missing_host_field.json` | opening without host wall (malformed) | `schema_invalid` |

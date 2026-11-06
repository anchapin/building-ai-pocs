# Fixtures

Six hand-built clean buildings plus an injected-error set.  Every clean
fixture has a matching `*.reference.json` holding a **hand-built** reference
model (floor area and WWR per zone/wall) whose arithmetic is written out in
the `arithmetic` field of that file.  The reference numbers were computed by
hand from the dimensions, independently of `checker.py`.

| Fixture | Geometry | Zones | Area (hand) | WWR (hand) |
| --- | --- | --- | --- | --- |
| `small_office.json` | 6.0 x 4.0 m rectangle, 3.0 m high | `z_office` | 6.0 x 4.0 = 24.0 m2 | 3.6 / 24.0 = 0.150 |
| `two_unit_house.json` | 5.0 x 4.0 m + 4.0 x 4.0 m units sharing a wall | `z_unit_a`, `z_unit_b` | 20.0 m2, 16.0 m2 | 2.4 / 20.0 = 0.120, 1.44 / 16.0 = 0.090 |
| `studio_loft.json` | L-shape: 6.0 x 4.0 m minus a 2.0 x 2.0 m notch | `z_studio` | 24.0 - 4.0 = 20.0 m2 | 6.0 / 20.0 = 0.300 |
| `classroom_block.json` | 8.0 x 6.0 m classroom + 8.0 x 2.0 m corridor (shared wall) | `z_classroom`, `z_corridor` | 8.0 x 6.0 = 48.0 m2, 8.0 x 2.0 = 16.0 m2 | 3.6 / 48.0 = 0.075, 2.4 / 16.0 = 0.150 |
| `l_shaped_retail.json` | L-shape: 12.0 x 8.0 m minus a 4.0 x 3.0 m notch | `z_shop` | 96.0 - 12.0 = 84.0 m2 | 19.0 / 84.0 = 0.2262 |
| `three_room_apartment.json` | 12.0 x 9.0 m split into living / kitchen / bathroom | `z_living`, `z_kitchen`, `z_bath` | 7.0 x 9.0 = 63.0 m2, 5.0 x 4.0 = 20.0 m2, 5.0 x 5.0 = 25.0 m2 | 7.8 / 63.0 = 0.1238, 1.56 / 20.0 = 0.0780, 1.8 / 25.0 = 0.0720 |

Glazed areas (hand arithmetic):

* `small_office`: 2 windows x 1.5 m x (2.1 - 0.9) m = 2 x 1.8 = 3.6 m2;
  host wall `w3` gross area 6.0 x 3.0 = 18.0 m2 -> wall WWR 0.200.
* `two_unit_house`: `winA` 2.0 x (2.2 - 1.0) = 2.4 m2, `winB` 1.2 x 1.2 = 1.44 m2;
  host walls `ha3` 5.0 x 3.0 = 15.0 m2 -> 0.160, `hb3` 4.0 x 3.0 = 12.0 m2 -> 0.120.
* `studio_loft`: 1 window 3.0 x (2.5 - 0.5) = 6.0 m2; host wall `l1`
  6.0 x 3.0 = 18.0 m2 -> 0.333.
* `classroom_block`: 2 classroom windows 1.5 x (2.1 - 0.9) = 1.8 m2 each,
  corridor window 2.0 x (2.2 - 1.0) = 2.4 m2; host walls `c2` 6.0 x 3.0 =
  18.0 m2 -> 0.200, `k3` 8.0 x 3.0 = 24.0 m2 -> 0.100.
* `l_shaped_retail`: 3 shopfront windows 2.0 x (2.4 - 0.4) = 4.0 m2 each,
  `win4` 2.0 x 1.4 = 2.8 m2, `win5` / `win6` 1.5 x 1.4 = 2.1 m2 each;
  host walls `r1` 12.0 x 3.0 = 36.0 m2 -> 0.333, `r2` 5.0 x 3.0 = 15.0 m2 ->
  0.140, `r5` 8.0 x 3.0 = 24.0 m2 -> 0.088, `r6` 8.0 x 3.0 = 24.0 m2 -> 0.117.
* `three_room_apartment`: `w1` 2.0 x 1.3 = 2.6 m2, `w2` 2.5 x 1.3 = 3.25 m2,
  `w3` 1.5 x 1.3 = 1.95 m2, `w4` 1.2 x 1.3 = 1.56 m2, `w5` 1.5 x 1.2 = 1.8 m2;
  host walls `p1` 7.0 x 3.0 = 21.0 m2 -> 0.124, `p9` 9.0 x 3.0 = 27.0 m2 ->
  0.120, `p8` 7.0 x 3.0 = 21.0 m2 -> 0.093, `p3` 4.0 x 3.0 = 12.0 m2 -> 0.130,
  `p4` 5.0 x 3.0 = 15.0 m2 -> 0.120.

Floor areas are measured on wall centre lines (shoelace polygon area); wall
thickness is carried in the model but not added to the area.

Every clean fixture also declares the **schedule quantities** (`kind` /
`count` on each schedule entry) that check 5 compares against the geometry.

## Injected-error set (`fixtures/injected/`)

`cases.json` lists every variant, the clean fixture it derives from, the
injected error and the error class the checker must report.  Slice 1 shipped
12 cases; slice 2 adds 12 more (the schedule/geometry consistency family
plus extra variants of the existing families), for 24 in total. Slice 3 adds
3 more (the shared-wall zone-membership family), for 27 in total. Two clean
fixtures now carry a shared-wall internal door: `classroom_block.json`
(`d_internal` on shared wall `c3`, listed in `z_classroom`) and
`three_room_apartment.json` (`d_internal` on shared wall `p7`, listed in
`z_living`).

| Variant | Injected error | Expected class |
| --- | --- | --- |
| `small_office_missing_door.json` | door `d1` deleted (zone ref kept) | `zone_opening_missing` |
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
| `small_office_dropped_door.json` | door deleted from geometry **and** zone list | `schedule_geometry_count_mismatch`, `zone_schedule_count_mismatch` |
| `small_office_dropped_window.json` | window deleted from geometry **and** zone list | `schedule_geometry_count_mismatch`, `zone_schedule_count_mismatch` |
| `small_office_schedule_count_wrong.json` | schedule quantity wrong (3 vs 2 windows) | `schedule_geometry_count_mismatch` |
| `small_office_zone_count_wrong.json` | zone mark quantity wrong (4 vs 3 openings) | `zone_schedule_count_mismatch` |
| `two_unit_house_retagged_window.json` | window re-tagged to another mark | `schedule_geometry_count_mismatch` |
| `two_unit_house_door_kind_swapped.json` | door re-classified as a window | `schedule_geometry_count_mismatch` |
| `two_unit_house_zone_ref_dropped.json` | only the zone reference dropped | `zone_schedule_count_mismatch`, `zone_opening_not_listed` |
| `classroom_block_dropped_window.json` | window deleted from geometry **and** zone list | `schedule_geometry_count_mismatch`, `zone_schedule_count_mismatch` |
| `l_shaped_retail_extra_window.json` | extra window added to geometry and zone list | `schedule_geometry_count_mismatch`, `zone_schedule_count_mismatch` |
| `l_shaped_retail_unclosed_loop.json` | zone loop unclosed in a larger building | `zone_not_closed` |
| `l_shaped_retail_duplicate_symbol.json` | duplicate schedule symbol in a larger building | `schedule_symbol_duplicate` |
| `studio_loft_negative_count.json` | schedule quantity not a positive integer (malformed) | `schema_invalid` |
| `classroom_block_shared_door_unlisted.json` | shared-wall door listed in no zone | `shared_wall_opening_unlisted` |
| `three_room_apartment_shared_door_wrong_zone.json` | shared-wall door also listed in a non-adjacent zone | `shared_wall_opening_wrong_zone` |
| `two_unit_house_door_wrong_zone.json` | single-owner door also listed in a non-adjacent zone | `shared_wall_opening_wrong_zone` |

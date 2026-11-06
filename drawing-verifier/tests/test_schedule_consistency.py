"""Tests for the slice-2 schedule/geometry count-consistency cross-check.

The point of this check is to close the slice-1 gap that "a door deleted
together with its zone reference is invisible".  The tests below therefore
include *discriminating* cases: the same injected model must be silent when
the new check is switched off and must be flagged when it is on.
"""

import json
import os

import checker


NEW_CHECK_NAME = "schedule_geometry_consistency"


def _load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _classes(findings):
    return {f.error_class for f in findings}


def _check_model_without_new_check(model):
    """Run the checker with the slice-2 check disabled."""
    original = checker.CHECKS
    checker.CHECKS = tuple(c for c in original if c[0] != NEW_CHECK_NAME)
    try:
        return checker.check_model(model)
    finally:
        checker.CHECKS = original


# ------------------------------------------------------------------ quiet
def test_consistency_check_quiet_on_every_clean_fixture(fixture_dir):
    names = [
        n
        for n in sorted(os.listdir(fixture_dir))
        if n.endswith(".json") and not n.endswith(".reference.json")
    ]
    assert len(names) >= 6, f"expected at least six clean fixtures, found {names}"
    for name in names:
        model = _load(os.path.join(fixture_dir, name))
        findings = checker.check_schedule_geometry_consistency(model)
        assert findings == [], f"{name}: {[f.reason for f in findings]}"


def test_consistency_check_is_registered_in_the_check_list():
    assert NEW_CHECK_NAME in [name for name, _ in checker.CHECKS]


# ------------------------------------------------- the silently deleted door
def test_dropped_door_with_dropped_zone_ref_is_flagged(injected_dir):
    model = _load(os.path.join(injected_dir, "small_office_dropped_door.json"))
    findings = checker.check_schedule_geometry_consistency(model)
    assert "schedule_geometry_count_mismatch" in _classes(findings)
    assert "zone_schedule_count_mismatch" in _classes(findings)
    assert any(f.element_id == "t_door_01" for f in findings)


def test_dropped_door_with_dropped_zone_ref_is_silent_without_the_check(injected_dir):
    model = _load(os.path.join(injected_dir, "small_office_dropped_door.json"))
    report = _check_model_without_new_check(model)
    assert report["n_findings"] == 0, report["findings"]
    assert "schedule_geometry_count_mismatch" not in report["error_classes"]
    # ... and with the check it is flagged
    report_with = checker.check_model(model)
    assert "schedule_geometry_count_mismatch" in report_with["error_classes"]


def test_dropped_window_with_dropped_zone_ref_is_flagged(injected_dir):
    model = _load(os.path.join(injected_dir, "small_office_dropped_window.json"))
    findings = checker.check_schedule_geometry_consistency(model)
    assert "schedule_geometry_count_mismatch" in _classes(findings)
    assert any(f.element_id == "t_window_01" for f in findings)


def test_dropped_window_is_silent_without_the_check(injected_dir):
    model = _load(os.path.join(injected_dir, "small_office_dropped_window.json"))
    report = _check_model_without_new_check(model)
    assert report["n_findings"] == 0, report["findings"]


# every case of the new family must be silent without the new check and
# flagged with it -- the check is what catches them, not something else
NEW_FAMILY_CASES = (
    "small_office_dropped_door.json",
    "small_office_dropped_window.json",
    "small_office_schedule_count_wrong.json",
    "small_office_zone_count_wrong.json",
    "two_unit_house_retagged_window.json",
    "two_unit_house_door_kind_swapped.json",
    "two_unit_house_zone_ref_dropped.json",
    "classroom_block_dropped_window.json",
    "l_shaped_retail_extra_window.json",
)


def test_new_family_cases_are_silent_without_the_check_and_caught_with_it(
    injected_dir, cases
):
    expected_by_variant = {case["variant"]: case["expected_classes"] for case in cases}
    for variant in NEW_FAMILY_CASES:
        assert variant in expected_by_variant, f"{variant} is not registered in cases.json"
        model = _load(os.path.join(injected_dir, variant))

        without = _check_model_without_new_check(model)
        assert without["n_findings"] == 0, (
            f"{variant}: expected no findings without the new check, got "
            f"{without['findings']}"
        )

        with_check = checker.check_model(model)
        found = set(with_check["error_classes"])
        expected = set(expected_by_variant[variant])
        assert expected.issubset(found), (
            f"{variant}: expected {sorted(expected)}, got {sorted(found)}"
        )


# ------------------------------------------------- other count-consistency
def test_schedule_count_against_geometry_count(clean_model):
    # the schedule claims three windows, the geometry carries two
    for sched in clean_model["schedules"]:
        if sched["tag_id"] == "t_window_01":
            sched["count"] = 3
    findings = checker.check_schedule_geometry_consistency(clean_model)
    assert "schedule_geometry_count_mismatch" in _classes(findings)
    assert any(f.element_id == "t_window_01" for f in findings)


def test_zone_opening_list_against_schedule_mark(clean_model):
    for sched in clean_model["schedules"]:
        if sched["tag_id"] == "t_zone_office":
            sched["count"] = 5
    findings = checker.check_schedule_geometry_consistency(clean_model)
    assert "zone_schedule_count_mismatch" in _classes(findings)
    assert any(f.element_id == "z_office" for f in findings)


def test_zone_opening_not_listed_when_only_the_zone_ref_is_dropped(clean_model):
    # the opening survives in the geometry but the zone forgets it
    clean_model["zones"][0]["openings"] = ["win1", "win2"]
    findings = checker.check_schedule_geometry_consistency(clean_model)
    assert "zone_opening_not_listed" in _classes(findings)
    assert any(f.element_id == "d1" for f in findings)


def test_shared_wall_openings_are_not_reported_as_unlisted(clean_model):
    # a wall shared by two zones has no unambiguous owner: the check must
    # stay quiet rather than guess which zone an opening belongs to
    clean_model["zones"].append(
        {
            "id": "z_other",
            "name": "Other",
            "wall_loop": ["w1", "w2", "w3", "w4"],
            "openings": [],
            "schedule_tag": None,
        }
    )
    findings = checker.check_schedule_geometry_consistency(clean_model)
    assert "zone_opening_not_listed" not in _classes(findings)


def test_schedule_entry_without_a_count_takes_no_part_in_the_check(clean_model):
    for sched in clean_model["schedules"]:
        sched.pop("count", None)
    findings = checker.check_schedule_geometry_consistency(clean_model)
    assert findings == []


def test_kind_narrows_the_count_to_doors_or_windows(clean_model):
    # t_window_01 declares "window" kind, so re-tagging win1 as a door makes
    # the window count wrong (and the door count wrong as well)
    for op in clean_model["openings"]:
        if op["id"] == "win1":
            op["kind"] = "door"
    findings = checker.check_schedule_geometry_consistency(clean_model)
    assert "schedule_geometry_count_mismatch" in _classes(findings)


# --------------------------------------------------------------- schema
def test_schema_rejects_a_non_positive_schedule_count(clean_model):
    clean_model["schedules"][0]["count"] = 0
    findings = checker.validate_model(clean_model)
    assert "schema_invalid" in _classes(findings)


def test_schema_rejects_an_unknown_schedule_kind(clean_model):
    clean_model["schedules"][0]["kind"] = "openingz"
    findings = checker.validate_model(clean_model)
    assert "schema_invalid" in _classes(findings)


def test_schema_accepts_a_valid_schedule_count(clean_model):
    clean_model["schedules"][0]["count"] = 2
    findings = checker.validate_model(clean_model)
    assert findings == []

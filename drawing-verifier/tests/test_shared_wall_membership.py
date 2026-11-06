"""Tests for the slice-3 shared-wall zone-membership check.

Check 6 closes the slice-2 gap named in ``REPORT.md`` §9: an opening hosted on
a wall shared by several zones was not checked for zone membership at all,
because the check had "no unambiguous owner" and stayed quiet.

The convention implemented here:

* an opening on a wall shared by two or more zones must be listed in the
  ``openings`` of **at least one** adjacent zone
  (``shared_wall_opening_unlisted`` otherwise);
* an opening must **not** be listed by a zone that does not border its host
  wall (``shared_wall_opening_wrong_zone``, one finding per offending zone);
* listing the opening in **both** adjacent zones is tolerated.

The tests are *discriminating*: every injected case must be silent when check
6 is removed from ``checker.CHECKS`` and must fire exactly its expected error
class when the check is present.
"""

import json
import os

import checker


NEW_CHECK_NAME = "shared_wall_zone_membership"

#: (variant, expected error class)
NEW_CASES = (
    ("classroom_block_shared_door_unlisted.json", "shared_wall_opening_unlisted"),
    ("three_room_apartment_shared_door_wrong_zone.json", "shared_wall_opening_wrong_zone"),
    ("two_unit_house_door_wrong_zone.json", "shared_wall_opening_wrong_zone"),
)


def _load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _classes(findings):
    return {f.error_class for f in findings}


def _check_model_without_new_check(model):
    """Run the checker with the slice-3 check disabled."""
    original = checker.CHECKS
    checker.CHECKS = tuple(c for c in original if c[0] != NEW_CHECK_NAME)
    try:
        return checker.check_model(model)
    finally:
        checker.CHECKS = original


# ------------------------------------------------------------------ wiring
def test_membership_check_is_registered_in_the_check_list():
    assert NEW_CHECK_NAME in [name for name, _ in checker.CHECKS]


def test_membership_check_runs_after_the_schedule_consistency_check():
    names = [name for name, _ in checker.CHECKS]
    assert names.index(NEW_CHECK_NAME) == names.index("schedule_geometry_consistency") + 1


# ------------------------------------------------------------------- quiet
def test_membership_check_quiet_on_every_clean_fixture(fixture_dir):
    names = [
        n
        for n in sorted(os.listdir(fixture_dir))
        if n.endswith(".json") and not n.endswith(".reference.json")
    ]
    assert len(names) >= 6, f"expected at least six clean fixtures, found {names}"
    for name in names:
        model = _load(os.path.join(fixture_dir, name))
        findings = checker.check_shared_wall_zone_membership(model)
        assert findings == [], f"{name}: {[f.reason for f in findings]}"


def test_listing_a_shared_wall_opening_in_both_adjacent_zones_is_tolerated(
    fixture_dir,
):
    # a door between two spaces may legitimately be listed by both of them
    model = _load(os.path.join(fixture_dir, "classroom_block.json"))
    for zone in model["zones"]:
        if zone["id"] == "z_corridor":
            zone["openings"].append("d_internal")
    findings = checker.check_shared_wall_zone_membership(model)
    assert findings == [], [f.reason for f in findings]


def test_an_opening_with_an_unknown_host_wall_is_not_a_membership_finding(
    injected_dir,
):
    # check 2 reports the missing host wall; membership is undefined here
    model = _load(os.path.join(injected_dir, "small_office_orphan_door.json"))
    findings = checker.check_shared_wall_zone_membership(model)
    assert findings == [], [f.reason for f in findings]


def test_check_5_stays_quiet_on_a_shared_wall_opening(fixture_dir):
    # check 6 is a separate function: check 5's "no unambiguous owner" rule
    # (zone_opening_not_listed) must not start firing on shared walls
    model = _load(os.path.join(fixture_dir, "classroom_block.json"))
    findings = checker.check_schedule_geometry_consistency(model)
    assert "zone_opening_not_listed" not in _classes(findings)


# ------------------------------------------------- the injected new cases
def test_shared_door_unlisted_is_flagged(injected_dir):
    model = _load(os.path.join(injected_dir, "classroom_block_shared_door_unlisted.json"))
    findings = checker.check_shared_wall_zone_membership(model)
    assert _classes(findings) == {"shared_wall_opening_unlisted"}
    assert any(f.element_id == "d_internal" for f in findings)


def test_shared_door_unlisted_is_silent_without_the_check(injected_dir):
    model = _load(os.path.join(injected_dir, "classroom_block_shared_door_unlisted.json"))
    without = _check_model_without_new_check(model)
    assert without["n_findings"] == 0, without["findings"]
    with_check = checker.check_model(model)
    assert with_check["error_classes"] == ["shared_wall_opening_unlisted"], with_check


def test_shared_door_wrong_zone_is_flagged(injected_dir):
    model = _load(
        os.path.join(injected_dir, "three_room_apartment_shared_door_wrong_zone.json")
    )
    findings = checker.check_shared_wall_zone_membership(model)
    assert _classes(findings) == {"shared_wall_opening_wrong_zone"}
    assert any(f.element_id == "d_internal" for f in findings)
    assert "z_bath" in findings[0].reason


def test_shared_door_wrong_zone_is_silent_without_the_check(injected_dir):
    model = _load(
        os.path.join(injected_dir, "three_room_apartment_shared_door_wrong_zone.json")
    )
    without = _check_model_without_new_check(model)
    assert without["n_findings"] == 0, without["findings"]
    with_check = checker.check_model(model)
    assert with_check["error_classes"] == ["shared_wall_opening_wrong_zone"], with_check


def test_single_owner_door_wrong_zone_is_flagged(injected_dir):
    model = _load(os.path.join(injected_dir, "two_unit_house_door_wrong_zone.json"))
    findings = checker.check_shared_wall_zone_membership(model)
    assert _classes(findings) == {"shared_wall_opening_wrong_zone"}
    assert any(f.element_id == "dA" for f in findings)


def test_single_owner_door_wrong_zone_is_silent_without_the_check(injected_dir):
    model = _load(os.path.join(injected_dir, "two_unit_house_door_wrong_zone.json"))
    without = _check_model_without_new_check(model)
    assert without["n_findings"] == 0, without["findings"]
    with_check = checker.check_model(model)
    assert with_check["error_classes"] == ["shared_wall_opening_wrong_zone"], with_check


def test_every_new_case_is_silent_without_the_check_and_caught_with_it(
    injected_dir, cases
):
    expected_by_variant = {case["variant"]: case["expected_classes"] for case in cases}
    for variant, expected_class in NEW_CASES:
        assert variant in expected_by_variant, f"{variant} is not registered in cases.json"
        assert expected_by_variant[variant] == [expected_class]
        model = _load(os.path.join(injected_dir, variant))

        without = _check_model_without_new_check(model)
        assert without["n_findings"] == 0, (
            f"{variant}: expected no findings without the new check, got "
            f"{without['findings']}"
        )

        with_check = checker.check_model(model)
        assert with_check["error_classes"] == [expected_class], (
            f"{variant}: expected exactly [{expected_class}], got "
            f"{with_check['error_classes']}"
        )


# --------------------------------------------------------- unit-level rules
def test_shared_wall_opening_listed_by_no_adjacent_zone_is_unlisted(fixture_dir):
    model = _load(os.path.join(fixture_dir, "classroom_block.json"))
    for zone in model["zones"]:
        zone["openings"] = [o for o in zone["openings"] if o != "d_internal"]
    findings = checker.check_shared_wall_zone_membership(model)
    assert _classes(findings) == {"shared_wall_opening_unlisted"}
    assert any(f.element_id == "d_internal" for f in findings)


def test_a_zone_that_does_not_border_the_host_wall_is_a_wrong_zone(fixture_dir):
    model = _load(os.path.join(fixture_dir, "three_room_apartment.json"))
    for zone in model["zones"]:
        if zone["id"] == "z_bath":
            zone["openings"].append("d_internal")
    findings = checker.check_shared_wall_zone_membership(model)
    assert _classes(findings) == {"shared_wall_opening_wrong_zone"}


def test_one_finding_per_offending_zone(fixture_dir):
    model = _load(os.path.join(fixture_dir, "three_room_apartment.json"))
    for zone in model["zones"]:
        if zone["id"] in ("z_bath", "z_kitchen"):
            zone["openings"].append("d_internal")
    findings = checker.check_shared_wall_zone_membership(model)
    # z_kitchen borders p7 (it is an owner), so only z_bath is reported
    assert len(findings) == 1
    assert findings[0].error_class == "shared_wall_opening_wrong_zone"

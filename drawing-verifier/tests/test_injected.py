"""End-to-end test over the injected-error set and the clean fixtures."""

import json
import os

import checker


def test_at_least_eight_injected_errors(cases):
    assert len(cases) >= 8


def test_injected_set_grew_to_at_least_twenty_cases(cases):
    # slice 1 had 12 cases; slice 2 adds the schedule/geometry consistency
    # family and extra variants of the existing families
    assert len(cases) >= 20, f"only {len(cases)} injected cases registered"


def test_every_injected_error_is_flagged_with_the_right_class(injected_dir, cases):
    for case in cases:
        path = os.path.join(injected_dir, case["variant"])
        with open(path, "r", encoding="utf-8") as handle:
            model = json.load(handle)
        report = checker.check_model(model)
        found = set(report["error_classes"])
        expected = set(case["expected_classes"])
        assert expected.issubset(found), (
            f"{case['variant']}: expected {sorted(expected)}, got {sorted(found)}"
        )
        assert report["n_findings"] >= 1, f"{case['variant']} produced no findings"


def test_injected_findings_carry_element_ids_and_reasons(injected_dir, cases):
    for case in cases:
        path = os.path.join(injected_dir, case["variant"])
        with open(path, "r", encoding="utf-8") as handle:
            model = json.load(handle)
        report = checker.check_model(model)
        for finding in report["findings"]:
            assert finding["element_id"]
            assert finding["reason"]
            assert finding["severity"] in ("error", "warning")


def test_required_error_classes_are_covered(cases):
    covered = {cls for case in cases for cls in case["expected_classes"]}
    required = {
        "zone_opening_missing",       # deleted door
        "zone_not_closed",             # scaled wall / unclosed loop
        "schedule_symbol_duplicate",   # swapped schedule symbol
        "opening_outside_wall",        # window longer than its host wall
        "schedule_duplicate_tag",      # duplicate schedule tag
        "opening_host_missing",        # door with no host wall
        "opening_overlap",             # overlapping windows on one wall
        "schedule_geometry_count_mismatch",   # schedule quantity vs geometry
        "zone_schedule_count_mismatch",       # zone opening list vs schedule mark
        "zone_opening_not_listed",            # zone forgot an opening
    }
    assert required.issubset(covered)


def test_clean_fixtures_produce_no_findings(fixture_dir):
    names = [
        n
        for n in sorted(os.listdir(fixture_dir))
        if n.endswith(".json") and not n.endswith(".reference.json")
    ]
    assert names, "no clean fixtures found"
    assert len(names) >= 6, f"expected at least six clean fixtures, found {names}"
    for name in names:
        with open(os.path.join(fixture_dir, name), "r", encoding="utf-8") as handle:
            model = json.load(handle)
        report = checker.check_model(model)
        assert report["n_findings"] == 0, f"{name}: {report['findings']}"


def test_cli_exit_code_is_non_zero_when_findings_exist(injected_dir, tmp_path):
    import subprocess
    import sys

    poc_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    variant = os.path.join(injected_dir, "small_office_missing_door.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(poc_dir, "checker.py"), variant],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "zone_opening_missing" in proc.stdout


def test_cli_exit_code_is_zero_on_clean_fixture(fixture_dir):
    import subprocess
    import sys

    poc_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    clean = os.path.join(fixture_dir, "small_office.json")
    proc = subprocess.run(
        [sys.executable, os.path.join(poc_dir, "checker.py"), clean],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "no findings" in proc.stdout

"""Schema validation tests: clean fixtures pass, malformed fixtures are rejected."""

import copy
import json
import os

import pytest

from checker import validate_model


def _clean_names(fixture_dir):
    return [
        n
        for n in sorted(os.listdir(fixture_dir))
        if n.endswith(".json") and not n.endswith(".reference.json")
    ]


def test_clean_fixtures_validate(fixture_dir):
    for name in _clean_names(fixture_dir):
        with open(os.path.join(fixture_dir, name), "r", encoding="utf-8") as handle:
            model = json.load(handle)
        findings = validate_model(model)
        assert findings == [], f"{name} should validate: {findings}"


def test_non_numeric_coordinate_is_rejected(clean_model):
    clean_model["walls"][0]["start"] = ["zero", 0.0]
    findings = validate_model(clean_model)
    assert findings
    assert all(f.error_class == "schema_invalid" for f in findings)
    assert any("numbers" in f.reason for f in findings)


def test_missing_host_wall_reference_is_rejected(clean_model):
    del clean_model["openings"][0]["host_wall"]
    findings = validate_model(clean_model)
    assert findings
    assert any(
        f.error_class == "schema_invalid" and "host_wall" in f.reason for f in findings
    )


def test_missing_section_is_rejected(clean_model):
    del clean_model["schedules"]
    findings = validate_model(clean_model)
    assert any("schedules" in f.reason for f in findings)


def test_zero_thickness_wall_is_rejected(clean_model):
    clean_model["walls"][0]["thickness"] = 0
    findings = validate_model(clean_model)
    assert any("thickness" in f.reason for f in findings)


def test_head_height_must_exceed_sill(clean_model):
    clean_model["openings"][1]["head_height"] = clean_model["openings"][1]["sill_height"]
    findings = validate_model(clean_model)
    assert any("head_height" in f.reason for f in findings)


def test_unknown_host_wall_is_not_a_schema_error_but_a_check_finding(clean_model):
    """A syntactically valid but dangling host wall is a checker finding, not a schema error."""
    clean_model["openings"][0]["host_wall"] = "w_nope"
    assert validate_model(clean_model) == []


def test_malformed_injected_fixture_is_rejected(injected_dir):
    path = os.path.join(injected_dir, "studio_loft_bad_coordinate.json")
    with open(path, "r", encoding="utf-8") as handle:
        model = json.load(handle)
    findings = validate_model(model)
    assert findings
    assert any(f.element_id == "l1" for f in findings)

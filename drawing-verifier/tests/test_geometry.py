"""Geometry error: computed areas / WWR must match the hand-built reference models."""

import json
import os

import pytest

import checker


def _clean_names(fixture_dir):
    return [
        n
        for n in sorted(os.listdir(fixture_dir))
        if n.endswith(".json") and not n.endswith(".reference.json")
    ]


@pytest.mark.parametrize("name", ["small_office.json", "two_unit_house.json", "studio_loft.json"])
def test_geometry_matches_hand_reference(fixture_dir, name):
    with open(os.path.join(fixture_dir, name), "r", encoding="utf-8") as handle:
        model = json.load(handle)
    with open(os.path.join(fixture_dir, name[: -len(".json")] + ".reference.json"), "r", encoding="utf-8") as handle:
        reference = json.load(handle)

    metrics = checker.compute_metrics(model)

    for zid, ref in reference["zones"].items():
        computed = metrics["zones"][zid]
        # hand arithmetic, e.g. 6.0 * 4.0 = 24.0
        assert computed["floor_area_m2"] == pytest.approx(ref["floor_area_m2"], abs=1e-6)
        assert computed["wwr"] == pytest.approx(ref["wwr"], abs=1e-3)

    for wid, ref in reference["walls"].items():
        computed = metrics["walls"][wid]
        assert computed["wwr"] == pytest.approx(ref["wwr"], abs=1e-3)


def test_small_office_area_matches_hand_arithmetic():
    """6.0 m x 4.0 m = 24.0 m2, glazing 2 x 1.5 x 1.2 = 3.6 m2 -> WWR 0.15."""
    model = {
        "schema_version": 1,
        "walls": [
            {"id": "w1", "start": [0.0, 0.0], "end": [6.0, 0.0], "thickness": 0.2, "height": 3.0},
            {"id": "w2", "start": [6.0, 0.0], "end": [6.0, 4.0], "thickness": 0.2, "height": 3.0},
            {"id": "w3", "start": [6.0, 4.0], "end": [0.0, 4.0], "thickness": 0.2, "height": 3.0},
            {"id": "w4", "start": [0.0, 4.0], "end": [0.0, 0.0], "thickness": 0.2, "height": 3.0},
        ],
        "openings": [
            {
                "id": "win1", "kind": "window", "host_wall": "w3", "center_offset": 1.5,
                "width": 1.5, "sill_height": 0.9, "head_height": 2.1,
            },
            {
                "id": "win2", "kind": "window", "host_wall": "w3", "center_offset": 4.5,
                "width": 1.5, "sill_height": 0.9, "head_height": 2.1,
            },
        ],
        "zones": [{"id": "z", "wall_loop": ["w1", "w2", "w3", "w4"], "openings": ["win1", "win2"]}],
        "schedules": [],
    }
    metrics = checker.compute_metrics(model)
    assert metrics["zones"]["z"]["floor_area_m2"] == pytest.approx(24.0)
    assert metrics["zones"]["z"]["window_area_m2"] == pytest.approx(3.6)
    assert metrics["zones"]["z"]["wwr"] == pytest.approx(0.15)
    assert metrics["walls"]["w3"]["wwr"] == pytest.approx(3.6 / 18.0)


def test_l_shaped_zone_area_matches_hand_arithmetic(fixture_dir):
    """6 x 4 rectangle (24 m2) minus the 2 x 2 notch (4 m2) = 20 m2."""
    with open(os.path.join(fixture_dir, "studio_loft.json"), "r", encoding="utf-8") as handle:
        model = json.load(handle)
    metrics = checker.compute_metrics(model)
    assert metrics["zones"]["z_studio"]["floor_area_m2"] == pytest.approx(20.0)


def test_geometry_error_against_reference_is_below_five_percent(fixture_dir):
    for name in _clean_names(fixture_dir):
        with open(os.path.join(fixture_dir, name), "r", encoding="utf-8") as handle:
            model = json.load(handle)
        ref_path = os.path.join(fixture_dir, name[: -len(".json")] + ".reference.json")
        with open(ref_path, "r", encoding="utf-8") as handle:
            reference = json.load(handle)
        metrics = checker.compute_metrics(model)
        for zid, ref in reference["zones"].items():
            computed = metrics["zones"][zid]
            area_err = abs(computed["floor_area_m2"] - ref["floor_area_m2"]) / ref["floor_area_m2"]
            wwr_err = abs(computed["wwr"] - ref["wwr"]) / ref["wwr"]
            assert area_err < 0.05
            assert wwr_err < 0.05

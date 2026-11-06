"""Each of the four checks flags its target error and stays quiet on clean input."""

import checker


def _classes(findings):
    return {f.error_class for f in findings}


# ---------------------------------------------------------------- check 1
def test_zone_closure_quiet_on_clean(clean_model):
    assert checker.check_zone_closure(clean_model) == []


def test_zone_closure_flags_unclosed_loop(clean_model):
    clean_model["walls"][3]["start"] = [0.5, 4.0]
    clean_model["walls"][3]["end"] = [0.5, 0.0]
    findings = checker.check_zone_closure(clean_model)
    assert "zone_not_closed" in _classes(findings)
    assert all(f.element_id == "z_office" for f in findings)
    assert all(f.reason for f in findings)


def test_zone_closure_flags_scaled_wall(clean_model):
    clean_model["walls"][2]["end"] = [-6.0, 4.0]
    findings = checker.check_zone_closure(clean_model)
    assert "zone_not_closed" in _classes(findings)


def test_zone_closure_flags_zero_area(clean_model):
    # collapse the loop onto a line
    for wall in clean_model["walls"]:
        wall["end"] = wall["start"]
    findings = checker.check_zone_closure(clean_model)
    assert findings
    assert _classes(findings) & {"zone_zero_area", "zone_not_closed"}


def test_zone_closure_flags_unknown_wall(clean_model):
    clean_model["zones"][0]["wall_loop"][2] = "w_ghost"
    findings = checker.check_zone_closure(clean_model)
    assert "zone_loop_unknown_wall" in _classes(findings)


# ---------------------------------------------------------------- check 2
def test_wall_adjacency_quiet_on_clean(clean_model):
    assert checker.check_wall_adjacency(clean_model) == []


def test_wall_adjacency_flags_missing_host_wall(clean_model):
    clean_model["openings"][0]["host_wall"] = "w_ghost"
    findings = checker.check_wall_adjacency(clean_model)
    assert "opening_host_missing" in _classes(findings)
    assert any(f.element_id == "d1" for f in findings)


def test_wall_adjacency_flags_window_longer_than_host_wall(clean_model):
    clean_model["openings"][2]["width"] = 7.0
    findings = checker.check_wall_adjacency(clean_model)
    assert "opening_outside_wall" in _classes(findings)
    assert any(f.element_id == "win2" for f in findings)


def test_wall_adjacency_flags_overlapping_windows(clean_model):
    clean_model["openings"].append(
        {
            "id": "win3",
            "kind": "window",
            "host_wall": "w3",
            "center_offset": 4.0,
            "width": 2.0,
            "sill_height": 0.9,
            "head_height": 2.1,
        }
    )
    findings = checker.check_wall_adjacency(clean_model)
    assert "opening_overlap" in _classes(findings)


def test_wall_adjacency_flags_deleted_door(clean_model):
    clean_model["openings"] = [o for o in clean_model["openings"] if o["id"] != "d1"]
    findings = checker.check_wall_adjacency(clean_model)
    assert "zone_opening_missing" in _classes(findings)
    assert any(f.element_id == "z_office" for f in findings)


# ---------------------------------------------------------------- check 3
def test_wwr_quiet_on_clean(clean_model):
    assert checker.check_window_to_wall_ratio(clean_model) == []


def test_wwr_flags_over_glazed_zone(clean_model):
    clean_model["openings"][1]["width"] = 6.0
    clean_model["openings"][2]["width"] = 6.0
    findings = checker.check_window_to_wall_ratio(clean_model)
    assert "wwr_out_of_band" in _classes(findings)
    assert any("z_office" == f.element_id for f in findings)


def test_wwr_flags_over_glazed_wall(clean_model):
    clean_model["openings"][1]["width"] = 5.0
    clean_model["openings"][2]["width"] = 5.0
    findings = checker.check_window_to_wall_ratio(clean_model)
    assert any(f.element_id == "w3" for f in findings)


def test_wwr_band_is_not_silently_clamped(clean_model):
    """Out-of-band ratios are reported, never clamped into the band."""
    clean_model["openings"][1]["width"] = 6.0
    clean_model["openings"][2]["width"] = 6.0
    findings = checker.check_window_to_wall_ratio(clean_model)
    for finding in findings:
        assert "outside the plausible band" in finding.reason


# ---------------------------------------------------------------- check 4
def test_schedules_quiet_on_clean(clean_model):
    assert checker.check_schedules(clean_model) == []


def test_schedules_flag_duplicate_symbol(clean_model):
    clean_model["schedules"][1]["symbol"] = "D01"
    findings = checker.check_schedules(clean_model)
    assert "schedule_symbol_duplicate" in _classes(findings)
    assert any(f.element_id == "t_window_01" for f in findings)


def test_schedules_flag_duplicate_tag(clean_model):
    duplicate = dict(clean_model["schedules"][0])
    duplicate["symbol"] = "D02"
    clean_model["schedules"].append(duplicate)
    findings = checker.check_schedules(clean_model)
    assert "schedule_duplicate_tag" in _classes(findings)


def test_schedules_flag_dangling_zone_reference(clean_model):
    clean_model["zones"][0]["schedule_tag"] = "t_zone_ghost"
    findings = checker.check_schedules(clean_model)
    assert "schedule_tag_missing" in _classes(findings)
    assert any(f.element_id == "z_office" for f in findings)


def test_schedules_flag_dangling_opening_reference(clean_model):
    clean_model["openings"][0]["schedule_tag"] = "t_door_ghost"
    findings = checker.check_schedules(clean_model)
    assert "schedule_tag_missing" in _classes(findings)
    assert any(f.element_id == "d1" for f in findings)


# ------------------------------------------------------------- second reader
def test_stub_second_reader_is_never_used_to_pass_or_fail(clean_model):
    stub = checker.NoVLMSecondReader()
    result = stub.review(clean_model, "drawing.png")
    assert result.agree is None
    assert "no VLM configured" in result.reason

    report = checker.check_model(clean_model, second_reader=stub)
    assert report["n_findings"] == 0
    assert report["second_reader"]["agree"] is None

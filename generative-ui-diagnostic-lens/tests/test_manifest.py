"""The field manifest is names + units only: the assembler never sees values."""

import json
import os

import manifest as manifest_mod


def test_manifest_entries_carry_no_values():
    run = manifest_mod.load_run("run_ashrae140_case1")
    man = manifest_mod.manifest_from_run(run)
    for entry in man["entries"]:
        assert set(entry) <= set(manifest_mod.MANIFEST_KEYS)
        assert "values" not in entry
        assert "value" not in entry
    serialised = json.dumps(man)
    assert "21.0" not in serialised
    assert "values" not in serialised


def test_manifest_keeps_names_and_units():
    run = manifest_mod.load_run("run_humid_latent_case3")
    man = manifest_mod.manifest_from_run(run)
    names = manifest_mod.manifest_field_names(man)
    assert "zone1_relative_humidity" in names
    entry = manifest_mod.find_entry(man, "zone1_relative_humidity")
    assert entry["unit"] == "%RH"
    assert entry["kind"] == "series"
    assert manifest_mod.find_entry(man, "nope") is None


def test_manifest_carries_the_runs_own_reference_band():
    run = manifest_mod.load_run("run_ashrae140_case1")
    man = manifest_mod.manifest_from_run(run)
    entry = manifest_mod.find_entry(man, "zone1_air_temperature")
    assert entry["reference_range"] == {"min": 20.0, "max": 24.0}


def test_three_fixture_runs_are_present():
    runs = manifest_mod.list_runs()
    assert runs == [
        "run_ashrae140_case1",
        "run_ground_coupled_case2",
        "run_humid_latent_case3",
    ]


def test_ground_truth_exists_for_every_case():
    for case_id in ("case1_ashrae140", "case2_ground_coupled", "case3_humid_latent"):
        truth = manifest_mod.load_ground_truth(case_id)
        assert truth["case_id"] == case_id
        assert truth["written_before_assembler"] is True
        assert truth["diagnosis"].strip()
        assert truth["key_fields"]


def test_ground_truth_files_are_written_before_the_run_outputs():
    """The generator writes the ground truth first (see gen_fixtures.main)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    source = open(
        os.path.join(here, "fixtures", "gen_fixtures.py"), "r", encoding="utf-8"
    ).read()
    truth_at = source.index("# ground truth FIRST")
    runs_at = source.index("# then the run outputs")
    assert truth_at < runs_at

"""The REAL Fluxion run output: the manifest built from it (slice 2, step 0).

These tests are about the *mapping* only: they check that the lens names
fields the real report actually carries, with the units the report's own
schema declares, and that the manifest still carries no values.
"""

import hashlib
import json
import os
import re

import catalog
import manifest as manifest_mod

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REAL_DIR = os.path.join(HERE, "real_runs")
REPORT = os.path.join(REAL_DIR, manifest_mod.REAL_REPORT_FILE)
PROVENANCE = os.path.join(REAL_DIR, "PROVENANCE.md")


def _report():
    return manifest_mod.load_standard_report()


def test_the_real_report_copy_is_the_one_the_provenance_records():
    """The copy in the folder is byte-identical to the upstream artifact."""
    with open(PROVENANCE, "r", encoding="utf-8") as handle:
        provenance = handle.read()
    match = re.search(r"\b([0-9a-f]{64})\b", provenance)
    assert match, "PROVENANCE.md records no sha256"
    digest = hashlib.sha256()
    with open(REPORT, "rb") as handle:
        digest.update(handle.read())
    assert digest.hexdigest() == match.group(1)


def test_the_real_report_has_the_shape_the_loader_expects():
    report = _report()
    assert report["metadata"]["schema_version"] == "1.0.0"
    assert "annual" in report and "monthly" in report and "hourly" in report
    assert len(report["monthly"]) == 12


def test_the_real_manifest_carries_names_and_units_only():
    man = manifest_mod.manifest_from_standard_report(_report())
    assert man["run_id"] == manifest_mod.REAL_RUN_ID
    assert len(man["entries"]) == len(manifest_mod.STANDARD_REPORT_FIELDS)
    for entry in man["entries"]:
        assert set(entry) <= set(manifest_mod.MANIFEST_KEYS)
        assert "value" not in entry
        assert "values" not in entry
        assert catalog.normalize_unit(entry["unit"]) is not None, entry
    serialised = json.dumps(man)
    assert "7905.46897" not in serialised


def test_every_lens_field_is_a_field_the_real_report_carries():
    """No lens field name is invented: each maps onto a leaf of the report."""
    report = _report()
    hourly_only = set()
    for name, _unit, _kind, path in manifest_mod.STANDARD_REPORT_FIELDS:
        values = manifest_mod.report_field_values(report, name)
        if values is None:
            # the report references the hourly series by checksum only
            hourly_only.add(name)
            assert path[:2] == ("hourly", "columns")
            continue
        assert values, name
    assert hourly_only == {
        "hourly_heating_energy",
        "hourly_cooling_energy",
        "hourly_lighting_energy",
        "hourly_equipment_energy",
    }


def test_the_units_are_the_units_the_report_declares():
    report = _report()
    man = manifest_mod.manifest_from_standard_report(report)
    checks = {
        "heating_energy": ("kWh", report["annual"]["end_use_kwh"]["heating"]),
        "peak_heating": ("kW", report["annual"]["peaks"]["heating"]),
        "floor_area": ("m2", report["annual"]["floor_area_m2"]),
        "zone_count": ("1", report["annual"]["zone_count"]),
        "unmet_heating_hours": ("h", report["unmet_hours"]["all_hours"]["heating"]),
        "setpoint_tolerance": ("°C", report["unmet_hours"]["tolerance_c"]),
    }
    for name, (unit, value) in checks.items():
        entry = manifest_mod.find_entry(man, name)
        assert entry is not None, name
        assert entry["unit"] == unit


def test_the_run_shape_takes_its_values_from_the_report_only():
    report = _report()
    run = manifest_mod.standard_report_to_run(report)
    assert run["run_id"] == manifest_mod.REAL_RUN_ID
    fields = run["fields"]
    assert fields["heating_energy"]["value"] == report["annual"]["end_use_kwh"]["heating"]
    assert fields["monthly_heating_energy"]["values"] == [
        month["end_use_kwh"]["heating"] for month in report["monthly"]
    ]
    # the hourly series is referenced by checksum only - no values may appear
    assert "values" not in fields["hourly_heating_energy"]
    assert "value" not in fields["hourly_heating_energy"]


def test_the_report_declares_the_hourly_series_by_checksum_only():
    report = _report()
    assert report["hourly"]["checksum"].startswith("sha256:")
    assert report["hourly"]["timesteps"] == 8760
    assert "series" not in report["hourly"] or "values" not in report["hourly"]

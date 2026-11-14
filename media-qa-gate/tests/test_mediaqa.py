"""Tests for the mediaqa universal pixel floor (POC #51 Phase 0 slice 1).

The corpus under media-qa-gate/corpus/ holds *real* armored-archer store
artifacts (copied read-only).  The seeded set under media-qa-gate/seeded/
holds derived defect copies.  Both are part of the slice, so the tests can
run offline with no network and no provisioning.
"""

import json
import os
import re

import pytest

import mediaqa

HERE = os.path.dirname(os.path.abspath(__file__))
GATE_DIR = os.path.dirname(HERE)
CORPUS = os.path.join(GATE_DIR, "corpus")
SEEDED = os.path.join(GATE_DIR, "seeded")
MANIFEST = os.path.join(CORPUS, "manifest.json")

LINE_RE = re.compile(r"^(error|warn) ([a-z_]+) (.+); (.+)$")

# Real duplicates that exist in the shipped store assets: the same pixels
# copied into two slots of one submission group.  These are true positives,
# not false positives - see REPORT.md.
KNOWN_CORPUS_DUPLICATES = {
    "ios/screenshots/ipad/screenshot_2.png",
    "ios/screenshots/ipad/screenshot_4.png",
    "ios/screenshots/iphone_5_5/screenshot_3.png",
    "ios/screenshots/iphone_6_7/screenshot_4.png",
}


# The corpus scan is the expensive part (~0.3 s/image); do it once per
# module so the suite stays fast and deterministic.
_MANIFEST_DATA = mediaqa.load_manifest(MANIFEST)
CORPUS_RESULTS = mediaqa.analyze([CORPUS], _MANIFEST_DATA, CORPUS)
SEEDED_RESULTS = mediaqa.analyze([SEEDED], {}, SEEDED)


def corpus_results():
    return CORPUS_RESULTS


def seeded_results():
    return SEEDED_RESULTS


# --------------------------------------------------------------------------
# corpus (real artifacts)
# --------------------------------------------------------------------------


def test_corpus_has_at_least_ten_real_artifacts():
    results = corpus_results()
    assert len(results) >= 10


def test_corpus_manifest_names_every_copied_artifact():
    with open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    assert manifest["count"] == len(manifest["artifacts"])
    for entry in manifest["artifacts"]:
        assert entry["source"].startswith("armored-archer/app_store_assets/")
        assert os.path.isfile(os.path.join(CORPUS, entry["file"]))
        assert entry["sha256"]


def test_no_false_errors_from_pixel_checks_on_real_artifacts():
    """No blank / dimensions / exposure / sharpness error on a real artifact."""
    offenders = []
    for r in corpus_results():
        for check in ("blank", "dimensions", "exposure", "sharpness"):
            cell = r.cells[check]
            if cell.status == "error":
                offenders.append(f"{r.label}:{check}:{cell.measurement}")
    assert offenders == []


def test_corpus_duplicate_errors_are_exactly_the_known_real_duplicates():
    dup_errors = {r.label for r in corpus_results()
                  if r.cells["duplicate"].status == "error"}
    assert dup_errors == KNOWN_CORPUS_DUPLICATES


def test_spec_deviation_is_a_warning_not_an_error():
    """iphone_6_7/screenshot_2.png is 1242x2688, the spec says 1290x2796."""
    target = None
    for r in corpus_results():
        if r.label == "ios/screenshots/iphone_6_7/screenshot_2.png":
            target = r
    assert target is not None
    assert target.cells["dimensions"].status == "warn"
    assert not target.error


def test_shared_cross_store_icon_is_only_a_warning():
    target = None
    for r in corpus_results():
        if r.label == "ios/icon_1024x1024.png":
            target = r
    assert target is not None
    assert target.cells["duplicate"].status == "warn"
    assert not target.error


# --------------------------------------------------------------------------
# seeded defects
# --------------------------------------------------------------------------


def test_every_seed_is_caught_as_an_error_by_its_expected_check():
    with open(os.path.join(SEEDED, "seeds.json"), encoding="utf-8") as fh:
        seeds = json.load(fh)["seeds"]
    results = {r.label: r for r in seeded_results()}
    misses = []
    for seed in seeds:
        r = results.get(seed["file"])
        if r is None:
            misses.append(f"{seed['id']}: artifact missing")
            continue
        cell = r.cells.get(seed["expected_check"])
        if cell is None:
            misses.append(f"{seed['id']}: check {seed['expected_check']} missing")
            continue
        if seed.get("expect_error", True):
            if cell.status != "error":
                misses.append(
                    f"{seed['id']}: expected {seed['expected_check']} error, got "
                    f"{cell.status}")
        elif cell.status == "error":
            misses.append(
                f"{seed['id']}: expected {seed['expected_check']} NOT to error")
    assert misses == []


def test_at_least_five_seed_kinds_are_covered():
    with open(os.path.join(SEEDED, "seeds.json"), encoding="utf-8") as fh:
        seeds = json.load(fh)["seeds"]
    kinds = {s["kind"] for s in seeds}
    assert len(kinds) >= 5
    assert "1x1 placeholder" in kinds
    assert "single-colour frame" in kinds
    assert "wrong dimensions" in kinds
    assert "blurred frame" in kinds
    assert "crushed exposure" in kinds


def test_seeded_run_exits_one():
    assert mediaqa.main([SEEDED, "--root", SEEDED]) == 1


def test_finding_lines_follow_the_required_format():
    for r in seeded_results():
        for f in r.findings:
            assert LINE_RE.match(f.line()), f.line()
            assert f.level in ("error", "warn")
            assert f.check in mediaqa.CHECKS
            assert f.hint.strip()


# --------------------------------------------------------------------------
# behaviour / determinism
# --------------------------------------------------------------------------


def test_measurements_are_deterministic_across_runs():
    first = [(r.label, r.cells["blank"].measurement,
              r.cells["exposure"].measurement,
              r.cells["sharpness"].measurement)
             for r in corpus_results()]
    second = [(r.label, r.cells["blank"].measurement,
               r.cells["exposure"].measurement,
               r.cells["sharpness"].measurement)
              for r in corpus_results()]
    assert first == second


def test_average_runtime_is_under_five_seconds_per_image():
    results = corpus_results()
    avg = sum(r.seconds for r in results) / len(results)
    assert avg < 5.0


def test_clean_directory_exits_zero(tmp_path):
    import shutil
    shutil.copyfile(os.path.join(CORPUS, "android/screenshots/combat.png"),
                    tmp_path / "combat.png")
    assert mediaqa.main([str(tmp_path), "--root", str(tmp_path)]) == 0


def test_unreadable_file_is_an_error(tmp_path):
    bad = tmp_path / "broken.png"
    bad.write_bytes(b"not a png at all")
    results = mediaqa.analyze([str(tmp_path)], {}, str(tmp_path))
    assert len(results) == 1
    assert results[0].error
    assert results[0].cells["blank"].status == "error"


def test_duplicate_detection_is_scoped_to_a_submission_group(tmp_path):
    """Identical pixels in two different groups are a warning, not an error."""
    import shutil
    src = os.path.join(CORPUS, "android/screenshots/combat.png")
    for sub in ("store_a", "store_b"):
        (tmp_path / sub).mkdir()
        shutil.copyfile(src, tmp_path / sub / "combat.png")
    results = mediaqa.analyze([str(tmp_path)], {}, str(tmp_path))
    assert not any(r.error for r in results)
    assert any(r.cells["duplicate"].status == "warn" for r in results)


@pytest.mark.parametrize("check", mediaqa.CHECKS)
def test_every_check_is_represented_in_the_table(check):
    table = mediaqa.format_table(corpus_results())
    assert check in table

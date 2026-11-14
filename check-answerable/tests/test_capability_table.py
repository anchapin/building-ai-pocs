"""Every frozen-set label is pinned against the capability-table function.

The frozen set (Part A) is the contract; this suite pins each of its 24
hand-written labels to the verdict the prototype's table returns, and pins the
gate discipline (zero false-answerable) as its own test.
"""

import json

import pytest

import capability_table as ct
from capability_table import capability, verdict_for_label

from conftest import FROZEN_FILE


@pytest.fixture(scope="module")
def frozen():
    with open(FROZEN_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def questions(frozen):
    return frozen["questions"]


# --------------------------------------------------------------- the frozen set

def test_frozen_set_has_24_questions(questions):
    assert len(questions) == 24


def test_frozen_question_ids_are_unique(questions):
    ids = [q["id"] for q in questions]
    assert len(set(ids)) == len(ids)


def test_every_frozen_question_carries_an_evidence_citation(questions):
    for q in questions:
        assert q.get("evidence"), "question %s has no evidence citation" % q["id"]
        assert "issue #56" in q["evidence"], "question %s does not cite the issue" % q["id"]


def test_every_frozen_question_uses_a_documented_class_and_sheet_type(questions):
    for q in questions:
        assert q["question_class"] in ct.QUESTION_CLASSES, q["id"]
        assert q["sheet_type"] in ct.SHEET_TYPES, q["id"]
        assert q["label"] in ct.VERDICT_FOR_LABEL, q["id"]


def test_frozen_set_spans_covered_partial_and_uncovered_classes(questions):
    labels = {q["label"] for q in questions}
    assert labels == {"answerable", "partial", "unanswerable"}
    classes = {q["question_class"] for q in questions}
    assert classes == set(ct.QUESTION_CLASSES)


# ------------------------------------------- the pinning test (one per question)

@pytest.mark.parametrize(
    "question_id",
    ["Q%02d" % i for i in range(1, 25)],
)
def test_frozen_label_is_pinned_against_the_capability_table(frozen, question_id):
    """Each frozen label must equal the table's verdict for (class, sheet)."""
    by_id = {q["id"]: q for q in frozen["questions"]}
    q = by_id[question_id]
    cap = capability(q["question_class"], q["sheet_type"])
    assert cap.verdict == verdict_for_label(q["label"]), (
        "%s: expected %s, table returned %s (reason %s)"
        % (q["id"], q["label"], cap.verdict, cap.reason_code)
    )
    assert cap.label == q["label"]


def test_every_frozen_question_agrees(questions):
    """Belt-and-braces: no frozen question disagrees with the table."""
    disagreements = []
    for q in questions:
        cap = capability(q["question_class"], q["sheet_type"])
        if cap.verdict != verdict_for_label(q["label"]):
            disagreements.append((q["id"], q["label"], cap.verdict))
    assert disagreements == []


# ------------------------------------------------------------ the reason codes

def test_every_non_covered_row_carries_a_reason_code_from_the_closed_set(questions):
    for q in questions:
        cap = capability(q["question_class"], q["sheet_type"])
        if cap.verdict != "covered":
            assert cap.reason_code in ct.REASON_CODES, (q["id"], cap.reason_code)
        else:
            assert cap.reason_code is None, q["id"]


def test_reason_code_vocabulary_is_the_closed_set():
    assert ct.REASON_CODES == (
        "no_detector",
        "outline_only_not_detected",
        "sheet_not_processed",
        "precision_insufficient",
        "scale_unverified",
        "no_parser",
        "raster_missing",
    )


def test_covered_classes_carry_no_reason_code():
    for cls in (
        "elevation_window_count",
        "elevation_window_band_count",
        "elevation_sill_height",
        "elevation_head_height",
    ):
        cap = capability(cls, "elevation")
        assert cap.verdict == "covered"
        assert cap.reason_code is None


def test_uncovered_classes_carry_their_documented_reason_code():
    assert capability("elevation_door_count", "elevation").reason_code == (
        "outline_only_not_detected"
    )
    assert capability("floor_plan_extraction", "floor_plan").reason_code == "sheet_not_processed"
    assert capability("section_extraction", "section").reason_code == "sheet_not_processed"
    assert capability("schedule_extraction", "schedule").reason_code == "no_parser"
    assert capability("window_width_at_schedule_precision", "schedule").reason_code == (
        "precision_insufficient"
    )


def test_raster_sheets_report_raster_missing():
    for sheet in ("elevation_raster", "floor_plan_raster", "section_raster", "schedule_raster"):
        cap = capability("elevation_window_count", sheet)
        assert cap.reason_code == "raster_missing"
        assert cap.verdict in ("partial", "uncovered")


def test_unscaled_elevation_reports_scale_unverified_for_measured_heights():
    assert capability("elevation_sill_height", "elevation_unscaled").reason_code == (
        "scale_unverified"
    )
    assert capability("elevation_head_height", "elevation_unscaled").verdict == "partial"
    # a count does not depend on the scale and stays covered
    assert capability("elevation_window_count", "elevation_unscaled").verdict == "covered"


def test_off_domain_sheet_types_are_not_processed():
    assert capability("elevation_window_count", "floor_plan").reason_code == "sheet_not_processed"
    assert capability("elevation_window_count", "section").verdict == "uncovered"
    assert capability("schedule_extraction", "elevation").verdict == "uncovered"


def test_window_width_class_is_partial_on_elevation_and_schedule():
    assert capability("window_width_at_schedule_precision", "elevation").verdict == "partial"
    assert capability("window_width_at_schedule_precision", "schedule").verdict == "partial"


# ------------------------------------------------------------------ the gate

def test_zero_false_answerable_on_the_frozen_set(questions):
    false_answerable = [
        q["id"]
        for q in questions
        if q["label"] == "unanswerable"
        and capability(q["question_class"], q["sheet_type"]).verdict == "covered"
    ]
    assert false_answerable == [], "false-answerable questions: %s" % false_answerable


def test_uncovered_class_is_never_fully_answerable_anywhere():
    for cls, spec in ct.QUESTION_CLASSES.items():
        if spec.base_verdict != "covered":
            for sheet in ct.SHEET_TYPES:
                assert capability(cls, sheet).verdict != "covered", (cls, sheet)


# ------------------------------------------------------------- the API guards

def test_unknown_question_class_raises():
    with pytest.raises(ct.UnknownQuestionClass):
        capability("not_a_documented_class", "elevation")


def test_unknown_sheet_type_raises():
    with pytest.raises(ct.UnknownSheetType):
        capability("elevation_window_count", "not_a_sheet_type")


def test_agreement_runner_reports_the_gate():
    import run_agreement

    result = run_agreement.run()
    assert result["n"] == 24
    assert result["false_answerable"] == 0
    assert result["overall_agreement"] >= 0.90
    assert result["proceed"] is True
    assert result["disagreements"] == []

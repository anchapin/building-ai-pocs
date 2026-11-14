#!/usr/bin/env python3
"""check-answerable - standalone, table-only `check_answerable` prototype.

Scope (building-ai-pocs issue #56, Phase 0 slice 1, Part B):

* A *capability table* function that maps
  ``(question class, sheet type) -> (covered | partial | uncovered, reason code)``.
* The caller supplies the question class explicitly.  There is **no LLM
  classification anywhere** in this module, and no model/API call of any kind.
* The table is pure data + pure functions: no I/O, no network, no detector,
  no parser, no server.  Nothing outside ``check-answerable/`` is imported or
  touched.

The capability model is expressed as *primitives* (which sheet types are
processed, which detectors exist, which parsers exist, what precision the
measurements reach) and the table is derived from those primitives by an
explicit, ordered rule list.  See ``README.md`` for the rules and for the
reason-code glossary.

Verdict vocabulary
------------------
``covered``    -> the question is fully answerable from the processed sheet.
``partial``    -> the question is answerable only to a reduced precision.
``uncovered``  -> the question is not answerable from the processed sheet.

Reason codes (closed set, from issue #56)
----------------------------------------
``no_detector``               no detector exists for the asked object class
``outline_only_not_detected`` the object exists only as a drawn outline and is not detected
``sheet_not_processed``       the sheet type is not processed by the pipeline
``precision_insufficient``    the measurement does not reach the asked precision
``scale_unverified``          the sheet's drawing scale is not verified
``no_parser``                 no parser reads the sheet type
``raster_missing``            the sheet is a raster image, so vector geometry is unavailable

A ``covered`` row carries ``reason_code = None``: there is no degradation to
explain.  Every ``partial``/``uncovered`` row carries exactly one code from the
closed set above (asserted by the test suite).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

__all__ = [
    "VERDICTS",
    "REASON_CODES",
    "QUESTION_CLASSES",
    "SHEET_TYPES",
    "Capability",
    "UnknownQuestionClass",
    "UnknownSheetType",
    "capability",
    "check_answerable",
    "load_frozen_questions",
    "verdict_for_label",
    "label_for_verdict",
]

# --- closed vocabularies -----------------------------------------------------

VERDICTS: Tuple[str, ...] = ("covered", "partial", "uncovered")

REASON_CODES: Tuple[str, ...] = (
    "no_detector",
    "outline_only_not_detected",
    "sheet_not_processed",
    "precision_insufficient",
    "scale_unverified",
    "no_parser",
    "raster_missing",
)

#: Frozen-set label vocabulary <-> capability-table verdict vocabulary.
LABEL_FOR_VERDICT = {
    "covered": "answerable",
    "partial": "partial",
    "uncovered": "unanswerable",
}
VERDICT_FOR_LABEL = {v: k for k, v in LABEL_FOR_VERDICT.items()}


class UnknownQuestionClass(KeyError):
    """Raised for a question class outside the documented (closed) set."""


class UnknownSheetType(KeyError):
    """Raised for a sheet type outside the documented (closed) set."""


# --- the capability primitives ----------------------------------------------

@dataclass(frozen=True)
class ClassSpec:
    """What the documented pipeline can do for one question class.

    ``base_verdict`` is the class-level verdict documented in issue #56;
    ``sheet_domain`` is the sheet type the class is asked about;
    ``reason`` is the reason code that explains a non-covered base verdict.
    ``needs_scale`` marks classes whose answer is a measured length and
    therefore depends on a verified drawing scale.
    """

    base_verdict: str
    sheet_domain: str
    reason: Optional[str]
    needs_scale: bool = False


@dataclass(frozen=True)
class SheetSpec:
    """What the documented pipeline can do with one sheet type."""

    domain: str
    processed: bool = True
    raster: bool = False
    scale_verified: bool = True


#: The documented question classes (issue #56, Part A class table).
QUESTION_CLASSES: Dict[str, ClassSpec] = {
    # covered
    "elevation_window_count": ClassSpec("covered", "elevation", None),
    "elevation_window_band_count": ClassSpec("covered", "elevation", None),
    "elevation_sill_height": ClassSpec("covered", "elevation", None, needs_scale=True),
    "elevation_head_height": ClassSpec("covered", "elevation", None, needs_scale=True),
    # uncovered
    "elevation_door_count": ClassSpec("uncovered", "elevation", "outline_only_not_detected"),
    "floor_plan_extraction": ClassSpec("uncovered", "floor_plan", "sheet_not_processed"),
    "section_extraction": ClassSpec("uncovered", "section", "sheet_not_processed"),
    "schedule_extraction": ClassSpec("uncovered", "schedule", "no_parser"),
    # partial
    "window_width_at_schedule_precision": ClassSpec(
        "partial", "schedule", "precision_insufficient"
    ),
}

#: The documented sheet types, plus the quality variants the table must answer
#: for (raster sheets carry no vector geometry; unscaled elevations cannot
#: support a measured height).
SHEET_TYPES: Dict[str, SheetSpec] = {
    "elevation": SheetSpec("elevation"),
    "elevation_raster": SheetSpec("elevation", raster=True),
    "elevation_unscaled": SheetSpec("elevation", scale_verified=False),
    "floor_plan": SheetSpec("floor_plan"),
    "floor_plan_raster": SheetSpec("floor_plan", raster=True),
    "section": SheetSpec("section"),
    "section_raster": SheetSpec("section", raster=True),
    "schedule": SheetSpec("schedule"),
    "schedule_raster": SheetSpec("schedule", raster=True),
}


@dataclass(frozen=True)
class Capability:
    """The verdict for one (question class, sheet type) pair."""

    question_class: str
    sheet_type: str
    verdict: str
    reason_code: Optional[str]

    @property
    def label(self) -> str:
        """The frozen-set label vocabulary equivalent of :attr:`verdict`."""
        return LABEL_FOR_VERDICT[self.verdict]

    def as_dict(self) -> Dict[str, Optional[str]]:
        return {
            "question_class": self.question_class,
            "sheet_type": self.sheet_type,
            "verdict": self.verdict,
            "reason_code": self.reason_code,
            "label": self.label,
        }


# --- the capability table function -------------------------------------------

def capability(question_class: str, sheet_type: str) -> Capability:
    """Return the capability-table verdict for a question class and sheet type.

    The caller states the question class explicitly - this function never
    classifies a question itself (no LLM, no heuristics on question text).

    Rule order (first rule that fires wins):

    R1  unknown class / sheet type -> ``UnknownQuestionClass`` /
        ``UnknownSheetType`` (a closed vocabulary, not a soft verdict).
    R2  raster sheet -> the vector geometry the classes need is unavailable:
        ``uncovered`` with ``raster_missing`` for covered classes, otherwise
        the class's own verdict with ``raster_missing`` as the reason.
    R3  the sheet type is not processed -> ``uncovered`` /
        ``sheet_not_processed``.
    R4  the sheet type is not the class's own domain -> ``uncovered`` /
        ``sheet_not_processed`` (the class is never answered off-domain),
        except for ``window_width_at_schedule_precision`` on an elevation,
        where the elevation gives a width but not at schedule precision:
        ``partial`` / ``precision_insufficient``.
    R5  the sheet's scale is not verified and the class needs a measured
        length -> ``partial`` / ``scale_unverified``.
    R6  otherwise the class's documented base verdict and reason code.
    """
    if question_class not in QUESTION_CLASSES:
        raise UnknownQuestionClass(question_class)
    if sheet_type not in SHEET_TYPES:
        raise UnknownSheetType(sheet_type)

    spec = QUESTION_CLASSES[question_class]
    sheet = SHEET_TYPES[sheet_type]

    if sheet.raster:
        verdict = spec.base_verdict if spec.base_verdict == "partial" else "uncovered"
        return Capability(question_class, sheet_type, verdict, "raster_missing")

    if not sheet.processed:
        return Capability(question_class, sheet_type, "uncovered", "sheet_not_processed")

    if sheet.domain != spec.sheet_domain:
        if question_class == "window_width_at_schedule_precision" and sheet.domain == "elevation":
            return Capability(
                question_class, sheet_type, "partial", "precision_insufficient"
            )
        return Capability(question_class, sheet_type, "uncovered", "sheet_not_processed")

    if not sheet.scale_verified and spec.needs_scale:
        return Capability(question_class, sheet_type, "partial", "scale_unverified")

    return Capability(question_class, sheet_type, spec.base_verdict, spec.reason)


def check_answerable(question_class: str, sheet_type: str) -> Capability:
    """Alias of :func:`capability` (the prototype's public entry point)."""
    return capability(question_class, sheet_type)


# --- frozen-set helpers ------------------------------------------------------

def verdict_for_label(label: str) -> str:
    """Map a frozen-set label (``answerable``/``partial``/``unanswerable``)."""
    try:
        return VERDICT_FOR_LABEL[label]
    except KeyError:
        raise ValueError("unknown label: %r" % (label,))


def label_for_verdict(verdict: str) -> str:
    """Map a capability verdict to the frozen-set label vocabulary."""
    try:
        return LABEL_FOR_VERDICT[verdict]
    except KeyError:
        raise ValueError("unknown verdict: %r" % (verdict,))


FROZEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frozen_questions.json")


def load_frozen_questions(path: Optional[str] = None) -> Dict:
    """Load the frozen question set (Part A).  Read-only."""
    with open(path or FROZEN_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


if __name__ == "__main__":  # tiny manual smoke entry point
    import sys

    if len(sys.argv) != 3:
        sys.stderr.write("usage: capability_table.py <question_class> <sheet_type>\n")
        raise SystemExit(2)
    cap = capability(sys.argv[1], sys.argv[2])
    print(json.dumps(cap.as_dict(), indent=2, sort_keys=True))

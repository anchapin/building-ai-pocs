#!/usr/bin/env python3
"""Run the frozen question set through the capability table and print agreement.

Command:

    python3 check-answerable/run_agreement.py

Output order (as required by issue #56 Phase 0 slice 1 Part B):

1. the raw per-class agreement table,
2. the overall agreement line,
3. the false-answerable count (the headline discipline: a question labelled
   ``unanswerable`` must never come back ``covered``/``answerable``),
4. every disagreement, with expected vs actual verdict and the reason code,
5. the gate verdict (Proceed requires >= 90 % overall agreement AND zero
   false-answerable).

Read-only: it touches nothing outside ``check-answerable/`` and makes no
model/API call.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capability_table import (  # noqa: E402
    capability,
    label_for_verdict,
    load_frozen_questions,
    verdict_for_label,
)

#: Issue #56 Phase 0 slice 1 gate.
MIN_OVERALL_AGREEMENT = 0.90


def run(frozen_path=None):
    """Return the agreement result dict for the frozen set."""
    frozen = load_frozen_questions(frozen_path)
    questions = frozen["questions"]

    rows = []
    for q in questions:
        cap = capability(q["question_class"], q["sheet_type"])
        expected = verdict_for_label(q["label"])
        rows.append(
            {
                "id": q["id"],
                "question": q["question"],
                "question_class": q["question_class"],
                "sheet_type": q["sheet_type"],
                "label": q["label"],
                "expected_verdict": expected,
                "actual_verdict": cap.verdict,
                "reason_code": cap.reason_code,
                "agree": cap.verdict == expected,
                "false_answerable": q["label"] == "unanswerable" and cap.verdict == "covered",
            }
        )

    classes = []
    for q in questions:
        if q["question_class"] not in classes:
            classes.append(q["question_class"])

    per_class = []
    for cls in classes:
        subset = [r for r in rows if r["question_class"] == cls]
        agree = sum(1 for r in subset if r["agree"])
        false_ans = sum(1 for r in subset if r["false_answerable"])
        per_class.append(
            {
                "question_class": cls,
                "n": len(subset),
                "agree": agree,
                "agreement": agree / len(subset),
                "expected_label": subset[0]["label"],
                "actual_label": label_for_verdict(subset[0]["actual_verdict"]),
                "false_answerable": false_ans,
            }
        )

    total_agree = sum(1 for r in rows if r["agree"])
    false_answerable = sum(1 for r in rows if r["false_answerable"])
    disagreements = [r for r in rows if not r["agree"]]

    overall = total_agree / len(rows) if rows else 0.0
    proceed = overall >= MIN_OVERALL_AGREEMENT and false_answerable == 0

    return {
        "rows": rows,
        "per_class": per_class,
        "n": len(rows),
        "total_agree": total_agree,
        "overall_agreement": overall,
        "false_answerable": false_answerable,
        "disagreements": disagreements,
        "proceed": proceed,
        "min_overall_agreement": MIN_OVERALL_AGREEMENT,
    }


def format_result(result):
    out = []
    out.append("check-answerable - capability-table agreement on the frozen set")
    out.append("frozen set: check-answerable/frozen_questions.json (n = %d)" % result["n"])
    out.append("")
    out.append("RAW PER-CLASS AGREEMENT TABLE")
    out.append(
        "%-36s %3s %6s %10s  %-13s %-13s %s"
        % ("question_class", "n", "agree", "agreement", "expected_label", "actual_label", "false_ans")
    )
    for c in result["per_class"]:
        out.append(
            "%-36s %3d %6d %9.1f%%  %-13s %-13s %d"
            % (
                c["question_class"],
                c["n"],
                c["agree"],
                100.0 * c["agreement"],
                c["expected_label"],
                c["actual_label"],
                c["false_answerable"],
            )
        )
    out.append(
        "%-36s %3d %6d %9.1f%%  %-13s %-13s %d"
        % (
            "OVERALL",
            result["n"],
            result["total_agree"],
            100.0 * result["overall_agreement"],
            "-",
            "-",
            result["false_answerable"],
        )
    )
    out.append("")
    out.append(
        "overall agreement: %d/%d = %.1f%%  (gate: >= %.0f%%)"
        % (
            result["total_agree"],
            result["n"],
            100.0 * result["overall_agreement"],
            100.0 * result["min_overall_agreement"],
        )
    )
    out.append(
        "false-answerable (unanswerable question returned as fully answerable): %d"
        % result["false_answerable"]
    )
    if result["false_answerable"]:
        out.append("HEADLINE: a question labelled unanswerable was classified fully answerable.")
        for r in result["rows"]:
            if r["false_answerable"]:
                out.append(
                    "  %s %s | expected=%s actual=%s reason=%s"
                    % (
                        r["id"],
                        r["question_class"],
                        r["expected_verdict"],
                        r["actual_verdict"],
                        r["reason_code"],
                    )
                )
    out.append("")
    if result["disagreements"]:
        out.append("DISAGREEMENTS (%d)" % len(result["disagreements"]))
        for r in result["disagreements"]:
            out.append(
                "  %s  class=%s sheet=%s" % (r["id"], r["question_class"], r["sheet_type"])
            )
            out.append("     question      : %s" % r["question"])
            out.append("     expected      : %s (%s)" % (r["expected_verdict"], r["label"]))
            out.append("     actual        : %s" % r["actual_verdict"])
            out.append("     reason code   : %s" % r["reason_code"])
    else:
        out.append("DISAGREEMENTS (0) - none")
    out.append("")
    out.append(
        "GATE: %s (overall agreement %s; false-answerable %s)"
        % (
            "Proceed" if result["proceed"] else "Do not proceed",
            "meets" if result["overall_agreement"] >= result["min_overall_agreement"] else "below",
            "zero" if result["false_answerable"] == 0 else "non-zero",
        )
    )
    return "\n".join(out)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    frozen_path = argv[0] if argv else None
    result = run(frozen_path)
    print(format_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

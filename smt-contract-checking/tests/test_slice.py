"""Example tests for the SMT-contract-checking slice.

These are the *example tests* of the slice: they mirror the coverage the
upstream POC has for the same code (``drawing-verifier/tests/test_checks.py``,
``drawing-verifier/tests/test_geometry.py``) and they must pass.

They deliberately do **not** cover the nested-span case that the contract
search finds (see ``tools/contract_search.py`` and the xfail test at the
bottom of this file): the point of the POC is that the existing example
tests miss the defect that the contracts expose.
"""

import math

import pytest

import geometry_slice as G
from contracts import ContractViolation, evaluate_contracts

TOL = G.TOLERANCE_M


# --------------------------------------------------------------- dist
def test_dist_matches_hand_arithmetic():
    assert G.dist(0.0, 0.0, 3.0, 4.0) == pytest.approx(5.0)


def test_dist_is_symmetric():
    assert G.dist(1.0, 2.0, -3.0, 0.5) == pytest.approx(G.dist(-3.0, 0.5, 1.0, 2.0))


# -------------------------------------------------------- polygon_area
def test_polygon_area_of_a_rectangle():
    # 6.0 m x 4.0 m, the small_office fixture of the upstream POC
    points = [(0.0, 0.0), (6.0, 0.0), (6.0, 4.0), (0.0, 4.0)]
    assert G.polygon_area(points) == pytest.approx(24.0)


def test_polygon_area_of_a_degenerate_loop_is_zero():
    assert G.polygon_area([(0.0, 0.0), (0.5, 0.0), (1.0, 0.0)]) == pytest.approx(0.0)


def test_polygon_area_of_an_l_shaped_zone():
    # 6 x 4 rectangle (24 m2) minus the 2 x 2 notch (4 m2) = 20 m2
    points = [
        (0.0, 0.0),
        (6.0, 0.0),
        (6.0, 2.0),
        (4.0, 2.0),
        (4.0, 4.0),
        (0.0, 4.0),
    ]
    assert G.polygon_area(points) == pytest.approx(20.0)


# --------------------------------------------------------- glazed_area
def test_glazed_area_of_a_window():
    # 1.5 m wide, sill 0.9 m, head 2.1 m -> 1.5 * 1.2 = 1.8 m2
    assert G.glazed_area(1.5, 0.9, 2.1) == pytest.approx(1.8)


def test_glazed_area_of_a_zero_width_opening_is_zero():
    assert G.glazed_area(0.0, 0.9, 2.1) == pytest.approx(0.0)


# -------------------------------------------------------- opening_span
def test_opening_span_is_centred_on_the_offset():
    assert G.opening_span(3.0, 2.0) == pytest.approx((2.0, 4.0))


def test_opening_span_of_a_door_at_the_wall_start():
    assert G.opening_span(0.5, 1.0) == pytest.approx((0.0, 1.0))


# ------------------------------------------------------- overlap_flag
def test_overlap_flag_detects_a_partial_overlap():
    # the upstream example test: two windows on one wall that overlap
    assert G.overlap_flag(0.0, 2.0, 1.0, 3.0) is True


def test_overlap_flag_is_quiet_on_separated_spans():
    assert G.overlap_flag(0.0, 1.0, 2.0, 3.0) is False


def test_overlap_flag_is_quiet_when_the_overlap_is_below_tolerance():
    assert G.overlap_flag(0.0, 1.0, 0.98, 1.5) is False


# ----------------------------------------------------- overlap_length
def test_overlap_length_matches_the_geometric_overlap():
    assert G.overlap_length(0.0, 2.0, 1.0, 3.0) == pytest.approx(1.0)


def test_overlap_length_is_zero_for_separated_spans():
    assert G.overlap_length(0.0, 1.0, 2.0, 3.0) == pytest.approx(0.0)


# --------------------------------------------------------- true_overlap
def test_true_overlap_of_two_spans():
    assert G.true_overlap(0.0, 2.0, 1.0, 3.0) == pytest.approx(1.0)


def test_true_overlap_is_zero_for_disjoint_spans():
    assert G.true_overlap(0.0, 1.0, 2.0, 3.0) == pytest.approx(0.0)


# ----------------------------------------------------------------- wwr
def test_wwr_matches_hand_arithmetic():
    # 3.6 m2 of glazing on a 24 m2 floor -> 0.15
    assert G.wwr(3.6, 24.0) == pytest.approx(0.15)


def test_wwr_of_a_wall():
    # 3.6 m2 of glazing on a 6.0 m x 3.0 m wall -> 0.2
    assert G.wwr(3.6, 18.0) == pytest.approx(0.2)


# ------------------------------------------------------------------
# The counterexample the example tests miss (kept as a known xfail).
#
# Two openings on the same wall, the second one *contained* in the span of
# the first: the upstream overlap test ignores the end of the second span
# (`hi2`) and therefore reports an overlap of 0.100 m where the geometric
# overlap is 0.050 m -- exactly at the tolerance, so it should not be
# reported at all.  The upstream example test only covers the
# partially-overlapping case, where the upstream formula happens to be right.
# ------------------------------------------------------------------
@pytest.mark.xfail(
    strict=False,
    reason="known counterexample: nested opening spans (see REPORT.md, "
    "'Counterexamples')",
)
def test_overlap_flag_agrees_with_the_geometry_for_a_nested_span():
    lo1, hi1 = 0.0, 1.0
    lo2, hi2 = 0.0, 0.05
    truth = G.true_overlap(lo1, hi1, lo2, hi2) > TOL
    assert G.overlap_flag(lo1, hi1, lo2, hi2) == truth


@pytest.mark.xfail(
    strict=False,
    reason="known counterexample: the reported overlap length is not the "
    "geometric overlap (see REPORT.md, 'Counterexamples')",
)
def test_overlap_length_is_the_geometric_overlap_for_a_nested_span():
    lo1, hi1 = 0.0, 1.0
    lo2, hi2 = 0.0, 0.05
    assert G.overlap_length(lo1, hi1, lo2, hi2) == pytest.approx(
        G.true_overlap(lo1, hi1, lo2, hi2)
    )


# ------------------------------------------------------------------
# Contract plumbing (the contracts themselves are exercised by
# tools/contract_search.py; these two keep the wiring honest).
# ------------------------------------------------------------------
def test_contracts_are_attached_to_the_slice():
    outcome = evaluate_contracts(G.overlap_flag, {"lo1": 0.0, "hi1": 1.0, "lo2": 0.5, "hi2": 1.5})
    assert outcome["pre_ok"]
    assert outcome["post_ok"]


def test_contract_violation_is_raised_at_runtime():
    with pytest.raises(ContractViolation):
        G.glazed_area(1.0, 2.0, 1.0)

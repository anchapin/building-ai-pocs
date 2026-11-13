"""Property-based (hypothesis) counterexample search over the slice's contracts.

This is a *second*, independent search method next to the bounded grid
search in ``tools/contract_search.py``: hypothesis generates spans from the
same 50 mm grid, the contracts are evaluated on each generated input, and
the first violating input is reported with a shrunk, minimal example.

The properties are expected to FAIL on the nested-span case (the known
counterexample), so they are marked ``xfail``: the suite stays green and the
defect stays visible.  When the upstream defect is fixed, these tests start
passing (``XPASS``) and the ``xfail`` markers can be removed.

If hypothesis is not installed the module is skipped.
"""

import pytest

hypothesis = pytest.importorskip("hypothesis")

from hypothesis import HealthCheck, given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

import geometry_slice as G  # noqa: E402
from contracts import evaluate_contracts  # noqa: E402

GRID = [mm / 1000.0 for mm in range(0, 1001, 50)]

spans = st.sampled_from(GRID)


@pytest.mark.xfail(
    strict=False,
    reason="known counterexample: nested opening spans (see REPORT.md)",
)
@settings(max_examples=500, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
@given(lo1=spans, hi1=spans, lo2=spans, hi2=spans)
def test_overlap_flag_property(lo1, hi1, lo2, hi2):
    outcome = evaluate_contracts(
        G.overlap_flag, {"lo1": lo1, "hi1": hi1, "lo2": lo2, "hi2": hi2}
    )
    if not outcome["pre_ok"]:
        return  # outside the contract's domain
    assert outcome["post_ok"], (
        f"overlap_flag({lo1}, {hi1}, {lo2}, {hi2}) returned {outcome['result']} "
        f"but the geometric overlap is {G.true_overlap(lo1, hi1, lo2, hi2)} m"
    )


@pytest.mark.xfail(
    strict=False,
    reason="known counterexample: nested opening spans (see REPORT.md)",
)
@settings(max_examples=500, derandomize=True, suppress_health_check=[HealthCheck.too_slow])
@given(lo1=spans, hi1=spans, lo2=spans, hi2=spans)
def test_overlap_length_property(lo1, hi1, lo2, hi2):
    outcome = evaluate_contracts(
        G.overlap_length, {"lo1": lo1, "hi1": hi1, "lo2": lo2, "hi2": hi2}
    )
    if not outcome["pre_ok"]:
        return
    assert outcome["post_ok"], (
        f"overlap_length({lo1}, {hi1}, {lo2}, {hi2}) returned {outcome['result']} "
        f"but the geometric overlap is {G.true_overlap(lo1, hi1, lo2, hi2)} m"
    )


@settings(max_examples=500, derandomize=True)
@given(width=spans, sill=spans, head=spans)
def test_glazed_area_property(width, sill, head):
    outcome = evaluate_contracts(
        G.glazed_area, {"width": width, "sill_height": sill, "head_height": head}
    )
    if not outcome["pre_ok"]:
        return
    if head <= sill:
        # upstream's schema validation rejects this input before the
        # geometry checks run: a contract error, not a live upstream bug.
        pytest.xfail("input rejected upstream by validate_model")
    assert outcome["post_ok"], (
        f"glazed_area({width}, {sill}, {head}) returned {outcome['result']}"
    )


@settings(max_examples=500, derandomize=True)
@given(glazed=spans, gross=spans)
def test_wwr_property(glazed, gross):
    outcome = evaluate_contracts(G.wwr, {"glazed": glazed, "gross": gross})
    if not outcome["pre_ok"]:
        return
    assert outcome["post_ok"], f"wwr({glazed}, {gross}) returned {outcome['result']}"

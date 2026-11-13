"""Regression tests for the opening-overlap test in ``check_wall_adjacency``.

The overlap of two opening spans is their *common* part,
``min(hi1, hi2) - max(lo1, lo2)``.  The previous implementation compared
``hi1 - lo2`` against the tolerance, which is the complement of the overlap
whenever one span is contained in the other: a 0.020 m overlap inside a 10 m
opening was reported as a 9.960 m overlap (false positive, wrong magnitude).

See ``smt-contract-checking/tools/repro_upstream_bug.py`` for the original
counterexample.
"""

import checker


def _model(openings):
    """A single 10 m wall carrying the given openings."""
    return {
        "schema_version": 1,
        "walls": [
            {
                "id": "w1",
                "start": [0.0, 0.0],
                "end": [10.0, 0.0],
                "thickness": 0.2,
                "height": 3.0,
            }
        ],
        "openings": openings,
        "zones": [],
        "schedules": [],
    }


def _opening(oid, center_offset, width):
    return {
        "id": oid,
        "kind": "window",
        "host_wall": "w1",
        "center_offset": center_offset,
        "width": width,
        "sill_height": 0.9,
        "head_height": 2.1,
    }


def _overlap_findings(model):
    return [
        f
        for f in checker.check_wall_adjacency(model)
        if f.error_class == "opening_overlap"
    ]


def test_contained_overlap_below_tolerance_is_not_reported():
    # A 0.02 m opening whose span lies inside a 10 m opening: the true
    # overlap is 0.020 m, which is below the 0.050 m tolerance.
    model = _model([_opening("A", 5.0, 10.0), _opening("B", 0.05, 0.02)])
    assert checker.check_wall_adjacency(model) == []


def test_contained_overlap_above_tolerance_reports_true_magnitude():
    # A 0.50 m opening inside a 10 m opening: the true overlap is 0.500 m,
    # not the 9.000 m complement.
    model = _model([_opening("A", 5.0, 10.0), _opening("B", 1.25, 0.5)])
    findings = _overlap_findings(model)
    assert len(findings) == 1
    assert findings[0].element_id == "B"
    assert findings[0].severity == checker.FINDING_ERROR
    assert "by 0.500 m" in findings[0].reason


def test_partial_overlap_reports_true_magnitude():
    # Two partially overlapping openings: the true overlap is 0.400 m.
    model = _model([_opening("A", 1.0, 2.0), _opening("B", 2.6, 2.0)])
    findings = _overlap_findings(model)
    assert len(findings) == 1
    assert findings[0].element_id == "B"
    assert "by 0.400 m" in findings[0].reason


def test_overlap_exactly_at_tolerance_is_not_reported():
    # 0.050 m of overlap is at (not above) the tolerance: no finding.
    model = _model([_opening("A", 1.0, 2.0), _opening("B", 2.95, 2.0)])
    assert checker.check_wall_adjacency(model) == []


def test_overlap_of_non_adjacent_openings_is_reported():
    # A narrow opening between two wider ones must not hide the real overlap
    # of the outer two: A = [0, 10], B = [4.00, 4.01], C = [4.50, 6.00], so
    # the true A/C overlap is 1.500 m.
    model = _model(
        [
            _opening("A", 5.0, 10.0),
            _opening("B", 4.005, 0.01),
            _opening("C", 5.25, 1.5),
        ]
    )
    findings = _overlap_findings(model)
    assert len(findings) == 1
    assert findings[0].element_id == "C"
    assert "by 1.500 m" in findings[0].reason


def test_overlap_findings_are_reported_per_pair():
    # Three openings, two overlapping pairs -> two findings, each with the
    # true magnitude of its own pair.
    model = _model(
        [
            _opening("A", 1.0, 2.0),
            _opening("B", 2.6, 2.0),
            _opening("C", 4.2, 2.0),
        ]
    )
    findings = _overlap_findings(model)
    assert [f.element_id for f in findings] == ["B", "C"]
    assert "by 0.400 m" in findings[0].reason
    assert "by 0.400 m" in findings[1].reason

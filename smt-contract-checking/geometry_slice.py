"""Pure-Python geometry slice for the SMT-contract-checking POC (issue #43).

Attribution
-----------
Every function in this module is **copied or mechanically adapted** from
``drawing-verifier/checker.py`` in this repository (POC ``drawing-verifier``,
slices 1-3).  No behaviour was changed; only the *shape* of the arguments
was adapted so that the slice is symbolic-execution friendly (plain floats
instead of JSON dicts, no I/O, no numpy, no dynamic dispatch):

===========================  ==========================================
slice function               upstream origin (drawing-verifier/checker.py)
===========================  ==========================================
``dist``                     ``_dist`` (line 237), adapted to 4 scalars
``polygon_area``             ``polygon_area`` (line 250), verbatim
``glazed_area``              ``opening_glass_area`` (line 263), adapted
                             from a dict to three scalars
``opening_span``             the span arithmetic inside
                             ``check_wall_adjacency`` (lines 411-477)
``overlap_flag``             the overlap test inside
                             ``check_wall_adjacency`` (line ~470)
``overlap_length``           the overlap magnitude reported inside
                             ``check_wall_adjacency`` (line ~472)
``true_overlap``             *new* helper: the geometric ground truth the
                             upstream code is supposed to compute
``wwr``                      the ratio in ``compute_metrics`` (line ~352)
===========================  ==========================================

Premise of this slice (checked in REPORT.md, section "Premise")
----------------------------------------------------------------
* pure Python, standard library only (``math``);
* no file, network, environment or clock access;
* no numpy, no C extensions, no ``eval``/``exec``, no dynamic attribute
  lookups on user data;
* every function is total on floats and short sequences of floats, so a
  symbolic executor can explore them.

Contracts
---------
The invariants are written with the contract decorators of ``contracts.py``,
which resolve to ``deal`` or ``icontract`` when either is installed (those
are the two libraries ``crosshair check`` reads) and to a dependency-free
fallback otherwise.  The contracts below are the *real* invariants of the
upstream code, not invented ones; two of them (``overlap_flag``,
``overlap_length``) are violated by the upstream code as written, which is
the point of the POC.
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

from contracts import ensure, pre

__all__ = [
    "TOLERANCE_M",
    "dist",
    "polygon_area",
    "glazed_area",
    "opening_span",
    "overlap_flag",
    "overlap_length",
    "true_overlap",
    "wwr",
]


#: Endpoint coincidence tolerance used by drawing-verifier, in metres.
#: (drawing-verifier/checker.py, ``TOLERANCE_M = 0.05``)
TOLERANCE_M = 0.05


@ensure(lambda result, ax, ay, bx, by: result >= 0.0)
def dist(ax: float, ay: float, bx: float, by: float) -> float:
    """Euclidean distance between two 2-D points.

    Adapted from ``drawing-verifier/checker.py::_dist`` (which takes two
    ``[x, y]`` sequences); the arithmetic is unchanged.
    """
    return math.hypot(ax - bx, ay - by)


@pre(lambda points: len(points) >= 3)
@ensure(lambda result, points: result >= 0.0)
def polygon_area(points: Sequence[Sequence[float]]) -> float:
    """Absolute shoelace area of a polygon.

    Copied verbatim from ``drawing-verifier/checker.py::polygon_area``
    (line 250).  Upstream invariant: a zone's floor area is never negative,
    and a polygon with fewer than three vertices encloses nothing.
    """
    if len(points) < 3:
        return 0.0
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


@ensure(lambda result, width, sill_height, head_height: result >= 0.0)
def glazed_area(width: float, sill_height: float, head_height: float) -> float:
    """Glazed area of a window opening.

    Adapted from ``drawing-verifier/checker.py::opening_glass_area``
    (line 263), which returns ``0.0`` for doors and
    ``width * (head_height - sill_height)`` for windows.  The door case is
    dropped here (the slice is about windows).

    Contract note: the postcondition "the glazed area is non-negative" is
    the real invariant of the downstream arithmetic (window areas are summed
    and divided), but it is *not* enforced by the upstream function itself:
    upstream rejects ``head_height <= sill_height`` in ``validate_model``
    before any geometry check runs.  A counterexample here is therefore a
    **contract error** (the contract as authored is missing a precondition
    that upstream enforces elsewhere), not a live upstream bug.
    """
    return width * (head_height - sill_height)


@pre(lambda center_offset, width: width >= 0.0)
@ensure(
    lambda result, center_offset, width: result[0] <= result[1]
    and abs((result[1] - result[0]) - width) <= 1e-9
)
def opening_span(center_offset: float, width: float) -> Tuple[float, float]:
    """Span ``(lo, hi)`` of an opening measured along its host wall.

    Adapted from the span arithmetic in ``drawing-verifier/checker.py::
    check_wall_adjacency`` (lines 411-477):

        half = width / 2
        lo = center_offset - half
        hi = center_offset + half
    """
    half = width / 2.0
    return (center_offset - half, center_offset + half)


@pre(lambda lo1, hi1, lo2, hi2: lo1 <= hi1 and lo2 <= hi2 and lo1 <= lo2)
@ensure(
    lambda result, lo1, hi1, lo2, hi2: result
    == (min(hi1, hi2) - max(lo1, lo2) > TOLERANCE_M)
)
def overlap_flag(lo1: float, hi1: float, lo2: float, hi2: float) -> bool:
    """Does the second opening overlap the first one by more than the tolerance?

    Copied verbatim from the overlap test inside ``drawing-verifier/
    checker.py::check_wall_adjacency`` (the spans are sorted by ``lo`` and
    consecutive pairs are compared):

        if lo2 < hi1 - TOLERANCE_M:   -> "opening_overlap"

    The contract states the geometric truth: two spans overlap by more than
    ``TOLERANCE_M`` iff ``min(hi1, hi2) - max(lo1, lo2) > TOLERANCE_M``.
    The upstream test ignores ``hi2`` entirely, so it is wrong whenever the
    second span is *contained* in the first one.
    """
    return lo2 < hi1 - TOLERANCE_M


@pre(lambda lo1, hi1, lo2, hi2: lo1 <= hi1 and lo2 <= hi2 and lo1 <= lo2)
@ensure(
    lambda result, lo1, hi1, lo2, hi2: result == 0.0
    or result == min(hi1, hi2) - max(lo1, lo2)
)
def overlap_length(lo1: float, hi1: float, lo2: float, hi2: float) -> float:
    """Length of the overlap between two opening spans (0.0 when they do not).

    Adapted from the magnitude reported by ``drawing-verifier/checker.py::
    check_wall_adjacency``:

        f"opening {id2!r} overlaps opening {id1!r} on host wall {host!r} "
        f"by {hi1 - lo2:.3f} m"

    i.e. the reported length is ``hi1 - lo2`` whenever the (upstream) test
    fires.  The contract states that the reported length is the true
    geometric overlap (or 0.0 when there is none).
    """
    if lo2 < hi1 - TOLERANCE_M:
        return hi1 - lo2
    return 0.0


@pre(lambda lo1, hi1, lo2, hi2: lo1 <= hi1 and lo2 <= hi2)
@ensure(lambda result, lo1, hi1, lo2, hi2: result >= 0.0)
def true_overlap(lo1: float, hi1: float, lo2: float, hi2: float) -> float:
    """Geometric overlap of two spans -- the ground truth for the two above.

    New helper (not upstream code): it exists so the contracts above can be
    stated against a reference quantity.
    """
    overlap = min(hi1, hi2) - max(lo1, lo2)
    return overlap if overlap > 0.0 else 0.0


@pre(lambda glazed, gross: gross > 0.0 and glazed >= 0.0)
@ensure(lambda result, glazed, gross: result == glazed / gross)
def wwr(glazed: float, gross: float) -> float:
    """Window-to-wall (or window-to-floor) ratio.

    Adapted from the ratio computed in ``drawing-verifier/checker.py::
    compute_metrics`` (line ~352): ``glass / gross`` when ``gross > 0``.
    """
    return glazed / gross

"""Symbolic checker for drawing-to-BEM structured geometry (SLICE 1 + 2).

Pure Python, standard library only.  It reads a structured-geometry JSON file
(see the schema in ``drawing-verifier/README.md``), runs five symbolic checks
over it, and emits structured findings:

  1. zone closure          (loop closes geometrically, encloses non-zero area)
  2. wall adjacency        (openings have a host wall, lie in its span, no overlap)
  3. window-to-wall ratio  (per wall and per zone, flagged outside a stated band)
  4. schedule cross-check  (dangling schedule tags, duplicate symbols / tags)
  5. schedule/geometry consistency (schedule quantities vs geometry counts)

The module also defines the ``SecondReader`` protocol and a stub reader that
records "no VLM configured".  The stub is never used to pass or fail anything:
VLM wiring is deferred (slice 2 / pending VLM selection).

CLI::

    python3 drawing-verifier/checker.py fixtures/small_office.json
    python3 drawing-verifier/checker.py fixtures/small_office.json --json

Exit code is non-zero (1) when findings exist, 0 when the model is clean.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constants (all documented in README.md)
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

#: Endpoint coincidence tolerance for zone loops, in metres.
TOLERANCE_M = 0.05

#: Plausible window-to-wall ratio band (lower, upper).  Applied only to walls
#: and zones that actually carry glazing; a zone/wall without windows is not
#: flagged (zero glazing is legal).
WWR_BAND = (0.05, 0.55)

#: Fallback wall height used when a wall does not declare one, in metres.
DEFAULT_WALL_HEIGHT_M = 3.0

#: Minimum area (m^2) for a zone to count as enclosing a non-zero area.
MIN_ZONE_AREA_M2 = 1e-6

#: Element kinds a schedule entry may declare when it carries a quantity.
#:
#: "opening" -- any opening (door or window) carrying the tag
#: "door"    -- only doors carrying the tag
#: "window"  -- only windows carrying the tag
#: "zone"    -- the zone-level mark: the number of openings listed by a zone
#:              that references the tag
SCHEDULE_COUNT_KINDS = ("opening", "door", "window", "zone")

FINDING_ERROR = "error"
FINDING_WARNING = "warning"


# ---------------------------------------------------------------------------
# Finding type
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """A single structured finding."""

    error_class: str
    element_id: str
    reason: str
    severity: str = FINDING_ERROR

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_str(value: Any) -> bool:
    return isinstance(value, str) and value != ""


def validate_model(model: Any) -> List[Finding]:
    """Validate a structured-geometry model against the slice-1 schema.

    Returns a list of findings with ``error_class == "schema_invalid"``.  An
    empty list means the model is schema-valid.  Semantic reference checks
    (e.g. "host wall does not exist") are *not* done here -- they belong to
    the checker checks.
    """
    out: List[Finding] = []

    def bad(element_id: str, reason: str) -> None:
        out.append(Finding("schema_invalid", element_id, reason))

    if not isinstance(model, dict):
        bad("<model>", "top level value must be a JSON object")
        return out

    version = model.get("schema_version")
    if version != SCHEMA_VERSION:
        bad("<model>", f"schema_version must be {SCHEMA_VERSION}, got {version!r}")

    if "project" in model and not _is_str(model["project"]):
        bad("<model>", "project must be a non-empty string")

    for section in ("walls", "openings", "zones", "schedules"):
        if section not in model:
            bad("<model>", f"missing required section {section!r}")
        elif not isinstance(model[section], list):
            bad("<model>", f"section {section!r} must be a list")

    if out:
        return out

    # --- walls -----------------------------------------------------------
    wall_ids = set()
    for i, wall in enumerate(model["walls"]):
        wid = wall.get("id") if isinstance(wall, dict) else None
        if not _is_str(wid):
            bad(f"<wall #{i}>", "wall id must be a non-empty string")
            continue
        if wid in wall_ids:
            bad(wid, "duplicate wall id")
        wall_ids.add(wid)
        for key in ("start", "end"):
            pt = wall.get(key)
            if not (isinstance(pt, list) and len(pt) == 2 and all(_is_number(c) for c in pt)):
                bad(wid, f"wall {key} must be a list of two numbers, got {pt!r}")
        thickness = wall.get("thickness")
        if not _is_number(thickness) or thickness <= 0:
            bad(wid, f"wall thickness must be a positive number, got {thickness!r}")
        height = wall.get("height", DEFAULT_WALL_HEIGHT_M)
        if not _is_number(height) or height <= 0:
            bad(wid, f"wall height must be a positive number, got {height!r}")

    # --- openings --------------------------------------------------------
    opening_ids = set()
    for i, opening in enumerate(model["openings"]):
        oid = opening.get("id") if isinstance(opening, dict) else None
        if not _is_str(oid):
            bad(f"<opening #{i}>", "opening id must be a non-empty string")
            continue
        if oid in opening_ids:
            bad(oid, "duplicate opening id")
        opening_ids.add(oid)
        kind = opening.get("kind")
        if kind not in ("door", "window"):
            bad(oid, f"opening kind must be 'door' or 'window', got {kind!r}")
        host = opening.get("host_wall")
        if not _is_str(host):
            bad(oid, f"opening host_wall must be a non-empty string, got {host!r}")
        for key in ("center_offset", "width", "sill_height", "head_height"):
            value = opening.get(key)
            if not _is_number(value):
                bad(oid, f"opening {key} must be a number, got {value!r}")
        width = opening.get("width")
        if _is_number(width) and width <= 0:
            bad(oid, f"opening width must be positive, got {width!r}")
        head = opening.get("head_height")
        sill = opening.get("sill_height")
        if _is_number(head) and _is_number(sill) and head <= sill:
            bad(oid, f"opening head_height ({head}) must exceed sill_height ({sill})")
        tag = opening.get("schedule_tag")
        if tag is not None and not _is_str(tag):
            bad(oid, f"opening schedule_tag must be a non-empty string, got {tag!r}")

    # --- zones -----------------------------------------------------------
    zone_ids = set()
    for i, zone in enumerate(model["zones"]):
        zid = zone.get("id") if isinstance(zone, dict) else None
        if not _is_str(zid):
            bad(f"<zone #{i}>", "zone id must be a non-empty string")
            continue
        if zid in zone_ids:
            bad(zid, "duplicate zone id")
        zone_ids.add(zid)
        loop = zone.get("wall_loop")
        if not (isinstance(loop, list) and len(loop) >= 3 and all(_is_str(w) for w in loop)):
            bad(zid, f"zone wall_loop must be a list of at least three wall ids, got {loop!r}")
        zone_openings = zone.get("openings", [])
        if not (isinstance(zone_openings, list) and all(_is_str(o) for o in zone_openings)):
            bad(zid, f"zone openings must be a list of opening ids, got {zone_openings!r}")
        tag = zone.get("schedule_tag")
        if tag is not None and not _is_str(tag):
            bad(zid, f"zone schedule_tag must be a non-empty string, got {tag!r}")

    # --- schedules -------------------------------------------------------
    for i, sched in enumerate(model["schedules"]):
        sid = sched.get("tag_id") if isinstance(sched, dict) else None
        if not _is_str(sid):
            bad(f"<schedule #{i}>", "schedule tag_id must be a non-empty string")
            continue
        if not _is_str(sched.get("symbol")):
            bad(sid, f"schedule symbol must be a non-empty string, got {sched.get('symbol')!r}")
        if "value" not in sched:
            bad(sid, "schedule entry needs a 'value'")
        # Optional quantity fields (slice 2).  A schedule entry may declare
        # what it counts ("kind") and how many ("count"); entries without
        # them take no part in the count cross-check.
        if "kind" in sched and sched["kind"] not in SCHEDULE_COUNT_KINDS:
            bad(
                sid,
                f"schedule kind must be one of {list(SCHEDULE_COUNT_KINDS)}, "
                f"got {sched['kind']!r}",
            )
        if "count" in sched:
            count = sched["count"]
            if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
                bad(sid, f"schedule count must be a positive integer, got {count!r}")

    return out


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _dist(a: Sequence[float], b: Sequence[float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def wall_length(wall: Dict[str, Any]) -> float:
    return _dist(wall["start"], wall["end"])


def wall_height(wall: Dict[str, Any]) -> float:
    height = wall.get("height", DEFAULT_WALL_HEIGHT_M)
    return float(height) if _is_number(height) else DEFAULT_WALL_HEIGHT_M


def polygon_area(points: Sequence[Sequence[float]]) -> float:
    """Signed shoelace area (absolute value returned)."""
    if len(points) < 3:
        return 0.0
    total = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def opening_glass_area(opening: Dict[str, Any]) -> float:
    """Glazed area of an opening (0 for doors)."""
    if opening.get("kind") != "window":
        return 0.0
    height = float(opening["head_height"]) - float(opening["sill_height"])
    return float(opening["width"]) * height


def _walk_loop(pairs: List[Tuple[List[float], List[float]]]) -> Tuple[Optional[List[List[float]]], Optional[str]]:
    """Walk a sequence of (start, end) wall endpoints into a closed polygon."""
    points: List[List[float]] = [list(pairs[0][0])]
    cur = list(pairs[0][0])
    for idx, (a, b) in enumerate(pairs):
        if idx == 0:
            nxt = list(b)
        elif _dist(cur, a) <= TOLERANCE_M:
            nxt = list(b)
        elif _dist(cur, b) <= TOLERANCE_M:
            nxt = list(a)
        else:
            gap = min(_dist(cur, a), _dist(cur, b))
            return None, (
                f"wall {idx} of the loop does not meet the previous wall "
                f"(gap {gap:.3f} m > tolerance {TOLERANCE_M} m)"
            )
        points.append(nxt)
        cur = nxt
    gap = _dist(cur, points[0])
    if gap > TOLERANCE_M:
        return None, (
            f"the loop does not close back onto its first point "
            f"(gap {gap:.3f} m > tolerance {TOLERANCE_M} m)"
        )
    return points, None


def _loop_polygon(model: Dict[str, Any], zone: Dict[str, Any]) -> Tuple[Optional[List[List[float]]], Optional[str]]:
    """Walk a zone wall loop into a polygon.

    Returns ``(points, None)`` on success or ``(None, reason)`` when the loop
    cannot be walked (missing wall or a gap between consecutive walls).  The
    loop may list a wall in either direction; both orientations of the first
    wall are tried.
    """
    walls = {w["id"]: w for w in model["walls"]}
    loop = list(zone["wall_loop"])
    for wid in loop:
        if wid not in walls:
            return None, f"wall {wid!r} referenced by the loop does not exist"

    pairs = [(list(walls[wid]["start"]), list(walls[wid]["end"])) for wid in loop]
    points, err = _walk_loop(pairs)
    if points is None:
        reversed_pairs = [(pairs[0][1], pairs[0][0])] + pairs[1:]
        points2, err2 = _walk_loop(reversed_pairs)
        if points2 is not None:
            return points2, None
        return None, err
    return points, None


def compute_metrics(model: Dict[str, Any]) -> Dict[str, Any]:
    """Compute floor areas and window-to-wall ratios for a model.

    Floor areas are computed from wall centre lines (shoelace).  A wall's WWR
    is glazed area on that wall divided by its gross area (length x height).
    A zone's WWR is the glazed area of the windows hosted on the zone's loop
    walls divided by the zone floor area.
    """
    walls = {w["id"]: w for w in model["walls"]}
    openings = model.get("openings", [])

    wall_metrics: Dict[str, Dict[str, Any]] = {}
    for wid, wall in walls.items():
        length = wall_length(wall)
        height = wall_height(wall)
        glass = 0.0
        windows: List[str] = []
        for op in openings:
            if op.get("host_wall") == wid:
                area = opening_glass_area(op)
                if area > 0:
                    glass += area
                    windows.append(op["id"])
        gross = length * height
        wall_metrics[wid] = {
            "length_m": length,
            "height_m": height,
            "gross_area_m2": gross,
            "window_area_m2": glass,
            "wwr": (glass / gross) if gross > 0 else 0.0,
            "windows": windows,
        }

    zone_metrics: Dict[str, Dict[str, Any]] = {}
    for zone in model.get("zones", []):
        points, err = _loop_polygon(model, zone)
        area = polygon_area(points) if points else 0.0
        glass = 0.0
        window_ids: List[str] = []
        for op in openings:
            if op.get("host_wall") in zone.get("wall_loop", []):
                g = opening_glass_area(op)
                if g > 0:
                    glass += g
                    window_ids.append(op["id"])
        zone_metrics[zone["id"]] = {
            "floor_area_m2": area,
            "window_area_m2": glass,
            "wwr": (glass / area) if area > 0 else 0.0,
            "windows": window_ids,
            "loop_error": err,
        }

    return {"walls": wall_metrics, "zones": zone_metrics}


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------


def check_zone_closure(model: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    for zone in model.get("zones", []):
        zid = zone["id"]
        points, err = _loop_polygon(model, zone)
        if err is not None:
            findings.append(
                Finding(
                    "zone_not_closed" if "does not exist" not in err else "zone_loop_unknown_wall",
                    zid,
                    f"zone {zid!r} wall loop does not close: {err}",
                )
            )
            continue
        area = polygon_area(points)
        if area <= MIN_ZONE_AREA_M2:
            findings.append(
                Finding(
                    "zone_zero_area",
                    zid,
                    f"zone {zid!r} encloses no area (computed {area:.6f} m^2)",
                )
            )
    return findings


def check_wall_adjacency(model: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    walls = {w["id"]: w for w in model["walls"]}
    openings = model.get("openings", [])
    openings_by_id = {o["id"]: o for o in openings}

    spans_by_wall: Dict[str, List[Tuple[float, float, str]]] = {}
    for op in openings:
        oid = op["id"]
        host = op.get("host_wall")
        wall = walls.get(host)
        if wall is None:
            findings.append(
                Finding(
                    "opening_host_missing",
                    oid,
                    f"opening {oid!r} references host wall {host!r} which does not exist",
                )
            )
            continue
        length = wall_length(wall)
        half = float(op["width"]) / 2.0
        lo = float(op["center_offset"]) - half
        hi = float(op["center_offset"]) + half
        if lo < -TOLERANCE_M or hi > length + TOLERANCE_M:
            findings.append(
                Finding(
                    "opening_outside_wall",
                    oid,
                    (
                        f"opening {oid!r} spans [{lo:.3f}, {hi:.3f}] m along host wall "
                        f"{host!r} of length {length:.3f} m -- it does not lie within "
                        "the wall span"
                    ),
                )
            )
        spans_by_wall.setdefault(host, []).append((lo, hi, oid))

    for host, spans in spans_by_wall.items():
        spans.sort()
        for (lo1, hi1, id1), (lo2, hi2, id2) in zip(spans, spans[1:]):
            if lo2 < hi1 - TOLERANCE_M:
                findings.append(
                    Finding(
                        "opening_overlap",
                        id2,
                        (
                            f"opening {id2!r} overlaps opening {id1!r} on host wall "
                            f"{host!r} by {hi1 - lo2:.3f} m"
                        ),
                    )
                )

    for zone in model.get("zones", []):
        zid = zone["id"]
        for oid in zone.get("openings", []):
            if oid not in openings_by_id:
                findings.append(
                    Finding(
                        "zone_opening_missing",
                        zid,
                        f"zone {zid!r} references opening {oid!r} which does not exist "
                        "(deleted or mis-extracted opening)",
                    )
                )
    return findings


def check_window_to_wall_ratio(model: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    low, high = WWR_BAND
    metrics = compute_metrics(model)
    for wid, m in metrics["walls"].items():
        if not m["windows"]:
            continue  # walls without glazing are exempt from the band
        if m["wwr"] < low or m["wwr"] > high:
            findings.append(
                Finding(
                    "wwr_out_of_band",
                    wid,
                    (
                        f"wall {wid!r} window-to-wall ratio {m['wwr']:.3f} is outside the "
                        f"plausible band [{low:.2f}, {high:.2f}] "
                        f"(glazed {m['window_area_m2']:.2f} m^2 of {m['gross_area_m2']:.2f} m^2)"
                    ),
                    FINDING_WARNING,
                )
            )
    for zid, m in metrics["zones"].items():
        if not m["windows"]:
            continue
        if m["loop_error"] or m["floor_area_m2"] <= MIN_ZONE_AREA_M2:
            # The zone loop does not close: its area (and therefore its WWR) is
            # undefined, so the ratio is not judged here.  The closure check
            # already reports the real problem.
            continue
        if m["wwr"] < low or m["wwr"] > high:
            findings.append(
                Finding(
                    "wwr_out_of_band",
                    zid,
                    (
                        f"zone {zid!r} window-to-wall ratio {m['wwr']:.3f} is outside the "
                        f"plausible band [{low:.2f}, {high:.2f}] "
                        f"(glazed {m['window_area_m2']:.2f} m^2 of {m['floor_area_m2']:.2f} m^2 floor)"
                    ),
                    FINDING_WARNING,
                )
            )
    return findings


def check_schedules(model: Dict[str, Any]) -> List[Finding]:
    findings: List[Finding] = []
    tag_ids: Dict[str, int] = {}
    symbol_owner: Dict[str, str] = {}
    for sched in model.get("schedules", []):
        tag = sched["tag_id"]
        symbol = sched["symbol"]
        tag_ids[tag] = tag_ids.get(tag, 0) + 1
        if tag_ids[tag] > 1:
            findings.append(
                Finding(
                    "schedule_duplicate_tag",
                    tag,
                    f"schedule tag {tag!r} is defined {tag_ids[tag]} times",
                )
            )
        if symbol in symbol_owner:
            findings.append(
                Finding(
                    "schedule_symbol_duplicate",
                    tag,
                    (
                        f"schedule symbol {symbol!r} is mapped to more than one tag "
                        f"({symbol_owner[symbol]!r} and {tag!r})"
                    ),
                )
            )
        else:
            symbol_owner[symbol] = tag

    for zone in model.get("zones", []):
        tag = zone.get("schedule_tag")
        if tag is not None and tag not in tag_ids:
            findings.append(
                Finding(
                    "schedule_tag_missing",
                    zone["id"],
                    f"zone {zone['id']!r} references schedule tag {tag!r} which is not "
                    "in the schedule table",
                )
            )
    for op in model.get("openings", []):
        tag = op.get("schedule_tag")
        if tag is not None and tag not in tag_ids:
            findings.append(
                Finding(
                    "schedule_tag_missing",
                    op["id"],
                    f"opening {op['id']!r} references schedule tag {tag!r} which is not "
                    "in the schedule table",
                )
            )
    return findings


def check_schedule_geometry_consistency(model: Dict[str, Any]) -> List[Finding]:
    """Cross-check the schedule quantities against the geometry (slice 2).

    The schedule table is a second source of truth inside the model: it says
    *how many* doors / windows carry a given mark.  The geometry says *which*
    openings exist.  Comparing the two catches an opening that was silently
    deleted from the geometry (together with its zone reference), because the
    schedule still lists it.

    Three sub-checks:

    * ``schedule_geometry_count_mismatch`` -- a schedule entry declares a
      quantity (``count``, and optionally ``kind``) that does not match the
      number of geometry elements carrying that tag.
    * ``zone_schedule_count_mismatch`` -- a zone-level schedule mark declares
      how many openings the zone holds, but the zone's opening list has a
      different number of entries.
    * ``zone_opening_not_listed`` -- an opening hosted on a wall that belongs
      to exactly one zone is not listed in that zone's opening list (the
      opening is there, but the zone forgot it).

    Schedule entries without a ``count`` take no part in the count
    cross-check, so a schedule table that carries no quantities is silent.
    """
    findings: List[Finding] = []
    openings = model.get("openings", [])
    zones = model.get("zones", [])

    # --- (a) schedule quantity vs geometry quantity --------------------
    for sched in model.get("schedules", []):
        if "count" not in sched:
            continue
        tag = sched["tag_id"]
        expected = sched["count"]
        kind = sched.get("kind", "opening")
        if kind == "zone":
            tagged = [z for z in zones if z.get("schedule_tag") == tag]
            if not tagged:
                findings.append(
                    Finding(
                        "schedule_geometry_count_mismatch",
                        tag,
                        (
                            f"schedule tag {tag!r} declares a zone quantity "
                            f"({expected}) but no zone references it"
                        ),
                    )
                )
            for zone in tagged:
                actual = len(zone.get("openings", []))
                if actual != expected:
                    findings.append(
                        Finding(
                            "zone_schedule_count_mismatch",
                            zone["id"],
                            (
                                f"zone {zone['id']!r} lists {actual} opening(s) but its "
                                f"schedule mark {tag!r} declares {expected}"
                            ),
                        )
                    )
            continue

        actual = sum(
            1
            for op in openings
            if op.get("schedule_tag") == tag
            and (kind == "opening" or op.get("kind") == kind)
        )
        if actual != expected:
            findings.append(
                Finding(
                    "schedule_geometry_count_mismatch",
                    tag,
                    (
                        f"schedule tag {tag!r} declares {expected} {kind}(s) but the "
                        f"geometry carries {actual} -- an opening may have been "
                        "silently deleted, duplicated or re-tagged"
                    ),
                )
            )

    # --- (b) zone opening lists vs the geometry -------------------------
    wall_owners: Dict[str, List[str]] = {}
    for zone in zones:
        for wid in zone.get("wall_loop", []):
            wall_owners.setdefault(wid, []).append(zone["id"])
    listed_in: Dict[str, List[str]] = {}
    for zone in zones:
        for oid in zone.get("openings", []):
            listed_in.setdefault(oid, []).append(zone["id"])

    for op in openings:
        owners = wall_owners.get(op.get("host_wall"), [])
        if len(owners) != 1:
            # A wall shared by several zones has no unambiguous owner, so
            # the check stays quiet rather than guessing.
            continue
        zid = owners[0]
        if op["id"] not in listed_in:
            findings.append(
                Finding(
                    "zone_opening_not_listed",
                    op["id"],
                    (
                        f"opening {op['id']!r} is hosted on wall {op.get('host_wall')!r}, "
                        f"which belongs to zone {zid!r}, but it is not listed in that "
                        "zone's opening list"
                    ),
                )
            )

    return findings


CHECKS = (
    ("zone_closure", check_zone_closure),
    ("wall_adjacency", check_wall_adjacency),
    ("window_to_wall_ratio", check_window_to_wall_ratio),
    ("schedule_cross_check", check_schedules),
    ("schedule_geometry_consistency", check_schedule_geometry_consistency),
)


# ---------------------------------------------------------------------------
# Second reader (VLM) -- protocol + stub only, never used to pass/fail
# ---------------------------------------------------------------------------


@dataclass
class SecondReaderResult:
    agree: Optional[bool]
    reason: str
    reader_id: str


class SecondReader(Protocol):
    """A second reader reviews structured geometry against a drawing.

    A real implementation would be a VLM that looks at the drawing image and
    says whether it agrees with the extracted geometry, with a reason.  The
    protocol is defined so the checker can be wired to one later; in slice 1
    no VLM exists and no reader verdict influences pass/fail.
    """

    reader_id: str

    def review(
        self, geometry: Dict[str, Any], drawing_ref: Optional[str]
    ) -> SecondReaderResult:
        ...


class NoVLMSecondReader:
    """Stub reader: records that no VLM is configured.

    Its verdict is always ``agree=None`` (unknown) and it never contributes a
    finding.  It exists only to document the intended interface.
    """

    reader_id = "stub-no-vlm"

    def review(
        self, geometry: Dict[str, Any], drawing_ref: Optional[str]
    ) -> SecondReaderResult:
        return SecondReaderResult(
            agree=None,
            reason="no VLM configured; second-reader agreement not evaluated",
            reader_id=self.reader_id,
        )


# ---------------------------------------------------------------------------
# Top-level API
# ---------------------------------------------------------------------------


def check_model(
    model: Dict[str, Any],
    second_reader: Optional[SecondReader] = None,
    drawing_ref: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all checks over a model.

    Returns a report dict with ``findings`` (list of Finding dicts), the
    per-check breakdown and, when a second reader is supplied, its verdict.
    The second reader never changes the finding list or the exit status.
    """
    schema_findings = validate_model(model)
    findings: List[Finding] = list(schema_findings)
    per_check: Dict[str, List[Dict[str, Any]]] = {}

    if schema_findings:
        per_check["schema"] = [f.to_dict() for f in schema_findings]
    else:
        for name, fn in CHECKS:
            found = fn(model)
            per_check[name] = [f.to_dict() for f in found]
            findings.extend(found)

    report: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "findings": [f.to_dict() for f in findings],
        "checks": per_check,
        "error_classes": sorted({f.error_class for f in findings}),
        "n_findings": len(findings),
    }

    if second_reader is not None:
        result = second_reader.review(model, drawing_ref)
        report["second_reader"] = asdict(result)
    else:
        report["second_reader"] = {
            "agree": None,
            "reason": "no VLM configured; second-reader agreement not evaluated",
            "reader_id": "none",
        }
    return report


def load_model(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def format_findings(report: Dict[str, Any]) -> str:
    lines = []
    for finding in report["findings"]:
        lines.append(
            f"[{finding['severity']}] {finding['error_class']}: "
            f"{finding['element_id']}: {finding['reason']}"
        )
    if not lines:
        lines.append("no findings")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    as_json = "--json" in argv
    argv = [a for a in argv if a != "--json"]
    if len(argv) != 1:
        print("usage: python3 checker.py <model.json> [--json]", file=sys.stderr)
        return 2

    try:
        model = load_model(argv[0])
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot read model {argv[0]!r}: {exc}", file=sys.stderr)
        return 2

    report = check_model(model)
    if as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"model: {argv[0]}")
        print(f"findings: {report['n_findings']}")
        print(format_findings(report))
    return 1 if report["n_findings"] else 0


if __name__ == "__main__":
    sys.exit(main())

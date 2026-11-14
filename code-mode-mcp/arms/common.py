"""Shared helpers for the three measurement arms (issue #50, Phase 0)."""
from __future__ import annotations

import json
import os

#: The read-only spike server (imported / called, never edited).
SERVER_DIR = os.environ.get("MATCHLINE_SERVER_DIR", "/home/hatch/workspace/mka-phase0/route-b/arm-b/server")
SERVER_SCRIPT = os.path.join(SERVER_DIR, "matchline_mcp_server.py")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLDEN_DIR = os.path.join(HERE, "golden")

ELEVATIONS = ["Elevation_01", "Elevation_02", "Elevation_03", "Elevation_04"]
BAND_ORDER = ["Ground", "First", "Second", "Third", "Roof"]


def load_golden(task_id: str) -> dict:
    """Load one frozen golden output."""
    from workload import GOLDEN_FILES
    with open(os.path.join(GOLDEN_DIR, GOLDEN_FILES[task_id]), encoding="utf-8") as fh:
        return json.load(fh)


def nbytes(text: str) -> int:
    """Byte accounting, exactly as defined in the brief: the UTF-8 length of the
    tool-result text as returned."""
    return len(text.encode("utf-8"))


def canonical(obj) -> str:
    """The one serialisation every arm uses for its final answer."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def matches_golden(task_id: str, produced) -> bool:
    """Correctness gate.

    Normalisation (documented in REPORT.md): both sides are JSON-parsed and
    compared as Python objects, so dict key order is irrelevant; crop file
    paths are compared by file name only (the arms store the basename, never
    an absolute path); every number is compared exactly as produced - the
    server rounds its own metric values to 2 decimals and the derived range
    values are rounded to 6 decimals by the reference implementations, so no
    epsilon is applied anywhere.

    Any mismatch is a finding, reported verbatim - it is never waved away as
    a rounding note.
    """
    golden = load_golden(task_id)
    return json.loads(canonical(produced)) == golden


def diff_golden(task_id: str, produced) -> str:
    """Verbatim description of a golden mismatch (empty string when equal)."""
    golden = load_golden(task_id)
    got = json.loads(canonical(produced))
    if got == golden:
        return ""
    lines = []
    for key in sorted(set(golden) | set(got)):
        if golden.get(key) != got.get(key):
            lines.append("  key %r: golden=%s" % (key, json.dumps(golden.get(key), sort_keys=True)[:400]))
            lines.append("  key %r: got   =%s" % (key, json.dumps(got.get(key), sort_keys=True)[:400]))
    return "\n".join(lines)

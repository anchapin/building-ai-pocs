#!/usr/bin/env python3
"""FROZEN canonical workload for the code-mode Phase 0 measurement (issue #50).

This module is the single source of truth for:

  * the five canonical tasks (T1..T5) over the real Route B sheets,
  * the pinned per-task call plans (which server tools each arm must call),
  * the reference ("golden") implementations - plain CPython stdlib, no Monty,
    no LLM, deterministic composition only - that define the expected output of
    every task,
  * the `freeze` mode that computes the golden JSON files ONCE and prints the
    sha256 hashes that evidence the freeze.

FREEZE PROTOCOL (issue #50, Phase 0, done-definition item 1):
  1. write this file,
  2. run `python workload.py freeze` -> writes golden/*.json and prints the
     sha256 of this file and of every golden file,
  3. record those hashes in REPORT.md,
  4. only THEN write any measurement code (arms/, run_measure.py, tests/).
  The reference implementations below are the "hand-checked reference code";
  they contain no judgement calls, only grouping / counting / range arithmetic.

Every arm (sequential MCP client, Monty code-mode program, ad-hoc script) must
produce output that matches the golden JSON exactly after the normalisation
documented in REPORT.md (JSON-parse equality; crop paths compared by file
name).  Any mismatch is a finding, not a rounding note.

Run:  python workload.py freeze
      python workload.py show    (prints the frozen call plans)
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys

# --- frozen constants ------------------------------------------------------

#: Where the read-only spike server lives (never written to).
DEFAULT_SERVER_DIR = "/home/hatch/workspace/mka-phase0/route-b/arm-b/server"

#: The four elevation sheets, in the order the tools are expected to be called.
ELEVATIONS = ["Elevation_01", "Elevation_02", "Elevation_03", "Elevation_04"]

#: Floor bands, in the order the server reports them.
BAND_ORDER = ["Ground", "First", "Second", "Third", "Roof"]

#: Tolerance of the width-consistency check (metres).
TOLERANCE_M = 0.05

#: The FIXED findings list handed to `summarise_findings` in the composite
#: task T5.  Frozen here (not derived from the drawings) so that every arm
#: summarises exactly the same list, and so the finding is reproducible.
FINDINGS = [
    {"floor": "Ground", "classification": "Mismatch"},
    {"floor": "Ground", "classification": "Mismatch"},
    {"floor": "First", "classification": "Mismatch"},
    {"floor": "First", "classification": "Mismatch"},
    {"floor": "First", "classification": "Cannot Determine"},
    {"floor": "Second", "classification": "Mismatch"},
    {"floor": "Second", "classification": "Cannot Determine"},
    {"floor": "Third", "classification": "Mismatch"},
    {"floor": "Third", "classification": "Cannot Determine"},
    {"floor": "Roof", "classification": "Mismatch"},
]

#: The five canonical tasks.
TASKS = [
    {
        "task_id": "T1",
        "name": "elevation_x_band_opening_count_matrix",
        "question": "How many openings does each elevation have per floor band?",
        "elevations": ELEVATIONS,
        "needs_summary": False,
        "needs_crops": False,
    },
    {
        "task_id": "T2",
        "name": "width_consistency_check",
        "question": ("Group openings by rounded width across elevations; flag "
                    "groups whose sill or head values disagree by > 0.05 m."),
        "elevations": ELEVATIONS,
        "needs_summary": False,
        "needs_crops": False,
    },
    {
        "task_id": "T3",
        "name": "band_sill_head_ranges",
        "question": "What is the sill/head range of each floor band across all elevations?",
        "elevations": ELEVATIONS,
        "needs_summary": False,
        "needs_crops": False,
    },
    {
        "task_id": "T4",
        "name": "ground_band_evidence_crops",
        "question": "Generate an evidence crop for every Ground-band opening on all four elevations.",
        "elevations": ELEVATIONS,
        "needs_summary": False,
        "needs_crops": True,
    },
    {
        "task_id": "T5",
        "name": "audit_prep_composite",
        "question": ("Audit prep: the T1 count matrix, the T3 band ranges and a "
                     "summarise_findings() call on the fixed findings list."),
        "elevations": ELEVATIONS,
        "needs_summary": True,
        "needs_crops": False,
    },
]

TASK_IDS = [t["task_id"] for t in TASKS]
TASKS_BY_ID = {t["task_id"]: t for t in TASKS}

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")

GOLDEN_FILES = {
    "T1": "T1_opening_count_matrix.json",
    "T2": "T2_width_consistency.json",
    "T3": "T3_band_sill_head_ranges.json",
    "T4": "T4_ground_band_crops.json",
    "T5": "T5_audit_prep_composite.json",
}


# --- helpers ---------------------------------------------------------------

def canonical_json(obj) -> str:
    """The one serialisation every arm uses for its final answer."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def load_server(server_dir: str = DEFAULT_SERVER_DIR):
    """Import the read-only spike server module (never edited, never written to)."""
    path = os.path.join(server_dir, "matchline_mcp_server.py")
    spec = importlib.util.spec_from_file_location("matchline_mcp_server", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load server module at %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def all_openings(elevation_data: dict) -> list:
    """Every opening of every elevation, in elevation order then server order."""
    out = []
    for sheet in ELEVATIONS:
        for opening in elevation_data[sheet]["openings"]:
            out.append(opening)
    return out


# --- pinned call plans -----------------------------------------------------

def extraction_calls(task_id: str) -> list:
    """The pinned extraction calls of a task: list_sheets once, then one
    extract_elevation_openings() per elevation the task needs."""
    task = TASKS_BY_ID[task_id]
    calls = [("list_sheets", {})]
    for sheet in task["elevations"]:
        calls.append(("extract_elevation_openings", {"sheet": sheet}))
    return calls


def crop_requests(elevation_data: dict) -> list:
    """The pinned get_crop() requests of task T4: one per Ground-band opening,
    in elevation order then server order."""
    requests = []
    for sheet in ELEVATIONS:
        for opening in elevation_data[sheet]["openings"]:
            if opening["floor_band"] != "Ground":
                continue
            x0, y0, x1, y1 = opening["bbox_px"]
            requests.append({
                "id": opening["id"],
                "sheet": sheet,
                "bbox_px": [x0, y0, x1, y1],
                "label": opening["id"].lower() + "_ground",
            })
    return requests


def sequential_call_plan(task_id: str, elevation_data: dict) -> list:
    """The exact Sequential-arm call list of a task, as (tool, args) pairs.

    T4's crop calls depend on the extraction results (the agent has to look at
    them to know which openings are Ground-band and where they are), so the
    plan is completed with the extraction data in hand.
    """
    calls = extraction_calls(task_id)
    if TASKS_BY_ID[task_id]["needs_crops"]:
        for req in crop_requests(elevation_data):
            calls.append(("get_crop", {
                "sheet": req["sheet"],
                "x0": req["bbox_px"][0], "y0": req["bbox_px"][1],
                "x1": req["bbox_px"][2], "y1": req["bbox_px"][3],
                "label": req["label"],
            }))
    if TASKS_BY_ID[task_id]["needs_summary"]:
        calls.append(("summarise_findings", {"findings_json": json.dumps(FINDINGS)}))
    return calls


def aggregate_call_plan(task_id: str) -> list:
    """The sensitivity plan: list_sheets once, then the aggregate
    extract_all_elevations() call, then summarise_findings().  Reported
    separately from the headline Sequential plan and never mixed into it."""
    calls = [("list_sheets", {}), ("extract_all_elevations", {})]
    if TASKS_BY_ID[task_id]["needs_summary"]:
        calls.append(("summarise_findings", {"findings_json": json.dumps(FINDINGS)}))
    return calls


def describe_calls(calls) -> str:
    """Human-readable one-line rendering of a call list for the results table."""
    parts = []
    for tool, args in calls:
        if tool == "extract_elevation_openings":
            parts.append("extract_elevation_openings(%s)" % args["sheet"])
        elif tool == "get_crop":
            parts.append("get_crop(%s,%s)" % (args["sheet"], args["label"]))
        elif tool == "summarise_findings":
            parts.append("summarise_findings(<10 findings>)")
        else:
            parts.append(tool + "()")
    return ", ".join(parts)


# --- reference implementations (the golden definitions) --------------------

def ref_T1(elevation_data: dict) -> dict:
    """Elevation x floor-band opening-count matrix."""
    matrix = {}
    for sheet in ELEVATIONS:
        counts = {band: 0 for band in BAND_ORDER}
        for opening in elevation_data[sheet]["openings"]:
            band = opening["floor_band"]
            counts[band] = counts.get(band, 0) + 1
        matrix[sheet] = {band: counts.get(band, 0) for band in BAND_ORDER}
    return {
        "task_id": "T1",
        "name": "elevation_x_band_opening_count_matrix",
        "band_order": list(BAND_ORDER),
        "matrix": matrix,
    }


def _group_by_width(openings) -> dict:
    groups = {}
    for opening in openings:
        groups.setdefault(opening["width_m"], []).append(opening)
    return groups


def _range_entry(width, members) -> dict:
    sills = [m["sill_m"] for m in members]
    heads = [m["head_m"] for m in members]
    sill_range = round(max(sills) - min(sills), 6)
    head_range = round(max(heads) - min(heads), 6)
    return {
        "width_m": width,
        "n": len(members),
        "sill_min_m": min(sills),
        "sill_max_m": max(sills),
        "head_min_m": min(heads),
        "head_max_m": max(heads),
        "sill_range_m": sill_range,
        "head_range_m": head_range,
        "flagged": bool(sill_range > TOLERANCE_M or head_range > TOLERANCE_M),
    }


def ref_T2(elevation_data: dict) -> dict:
    """Width-consistency check: group openings by rounded width across all
    elevations; flag a group when its sill values or its head values disagree
    by more than TOLERANCE_M.  The same grouping is also reported per floor
    band, where the within-band agreement is the informative part."""
    openings = all_openings(elevation_data)
    groups = []
    for width in sorted(_group_by_width(openings)):
        members = _group_by_width(openings)[width]
        entry = _range_entry(width, members)
        entry["members"] = [
            {"id": m["id"], "sheet": m["id"].split("-")[0],
             "floor_band": m["floor_band"], "sill_m": m["sill_m"], "head_m": m["head_m"]}
            for m in members
        ]
        groups.append(entry)
    by_band = {}
    for band in BAND_ORDER:
        band_openings = [o for o in openings if o["floor_band"] == band]
        entries = []
        for width in sorted(_group_by_width(band_openings)):
            entries.append(_range_entry(width, _group_by_width(band_openings)[width]))
        by_band[band] = entries
    return {
        "task_id": "T2",
        "name": "width_consistency_check",
        "tolerance_m": TOLERANCE_M,
        "groups": groups,
        "by_band": by_band,
    }


def ref_T3(elevation_data: dict) -> dict:
    """Per-band sill/head range table across all elevations."""
    openings = all_openings(elevation_data)
    bands = []
    for band in BAND_ORDER:
        members = [o for o in openings if o["floor_band"] == band]
        if not members:
            bands.append({"band": band, "count": 0, "sill_min_m": None, "sill_max_m": None,
                          "head_min_m": None, "head_max_m": None})
            continue
        sills = [o["sill_m"] for o in members]
        heads = [o["head_m"] for o in members]
        bands.append({"band": band, "count": len(members), "sill_min_m": min(sills),
                      "sill_max_m": max(sills), "head_min_m": min(heads), "head_max_m": max(heads)})
    return {"task_id": "T3", "name": "band_sill_head_ranges", "bands": bands}


def ref_T4(elevation_data: dict, crop_results: list) -> dict:
    """Ground-band evidence crops.  `crop_results` are the parsed get_crop()
    results, in the same order as `crop_requests()`."""
    requests = crop_requests(elevation_data)
    crops = []
    for req, result in zip(requests, crop_results):
        crops.append({
            "id": req["id"],
            "sheet": req["sheet"],
            "bbox_px": req["bbox_px"],
            "label": req["label"],
            "file_name": os.path.basename(result["path"]),
            "size_px": list(result["size_px"]),
            "source_box_px": list(result["source_box_px"]),
        })
    return {"task_id": "T4", "name": "ground_band_evidence_crops", "crops": crops}


def ref_T5(elevation_data: dict, summary: dict) -> dict:
    """Composite audit prep: T1 matrix + T3 band ranges + summarise_findings()."""
    return {
        "task_id": "T5",
        "name": "audit_prep_composite",
        "band_order": list(BAND_ORDER),
        "opening_count_matrix": ref_T1(elevation_data)["matrix"],
        "band_sill_head_ranges": ref_T3(elevation_data)["bands"],
        "findings_summary": summary,
    }


# --- freeze ----------------------------------------------------------------

def compute_golden(server_dir: str = DEFAULT_SERVER_DIR) -> dict:
    """Call the real server once per needed tool and compute every golden."""
    server = load_server(server_dir)
    elevation_data = {}
    for sheet in ELEVATIONS:
        elevation_data[sheet] = json.loads(server.extract_elevation_openings(sheet))
    crop_results = []
    for req in crop_requests(elevation_data):
        crop_results.append(json.loads(server.get_crop(
            req["sheet"], req["bbox_px"][0], req["bbox_px"][1],
            req["bbox_px"][2], req["bbox_px"][3], req["label"])))
    summary = json.loads(server.summarise_findings(json.dumps(FINDINGS)))
    return {
        "T1": ref_T1(elevation_data),
        "T2": ref_T2(elevation_data),
        "T3": ref_T3(elevation_data),
        "T4": ref_T4(elevation_data, crop_results),
        "T5": ref_T5(elevation_data, summary),
    }


def cmd_freeze(args) -> int:
    golden = compute_golden(args.server_dir)
    os.makedirs(args.out, exist_ok=True)
    for task_id in TASK_IDS:
        path = os.path.join(args.out, GOLDEN_FILES[task_id])
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(golden[task_id], indent=1, sort_keys=True) + "\n")
    workload_path = os.path.abspath(__file__)
    print("FROZEN workload sha256: %s  %s" % (sha256_file(workload_path), workload_path))
    for task_id in TASK_IDS:
        path = os.path.join(args.out, GOLDEN_FILES[task_id])
        print("FROZEN golden %s sha256: %s  %s" % (task_id, sha256_file(path), path))
    return 0


def cmd_show(args) -> int:
    server = load_server(args.server_dir)
    elevation_data = {sheet: json.loads(server.extract_elevation_openings(sheet))
                      for sheet in ELEVATIONS}
    for task_id in TASK_IDS:
        plan = sequential_call_plan(task_id, elevation_data)
        print("%s %s: %d calls" % (task_id, TASKS_BY_ID[task_id]["name"], len(plan)))
        print("    %s" % describe_calls(plan))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server-dir", default=os.environ.get("MATCHLINE_SERVER_DIR", DEFAULT_SERVER_DIR))
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_freeze = sub.add_parser("freeze", help="compute and write the golden JSON files")
    p_freeze.add_argument("--out", default=GOLDEN_DIR)
    p_freeze.set_defaults(func=cmd_freeze)
    p_show = sub.add_parser("show", help="print the frozen call plans")
    p_show.set_defaults(func=cmd_show)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

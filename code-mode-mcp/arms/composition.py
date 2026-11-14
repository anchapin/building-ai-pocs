"""Agent-side composition: the deterministic stand-in for the agent's reasoning.

No LLM is called anywhere in this POC (hard requirement of the brief), so the
"agent" that consumes the sequential arm's tool results is this deterministic
composition code.  It reads the tool results exactly as an agent would read
them from its context: the raw JSON text is parsed and grouped/counted.

This is the SECOND independent implementation of the task semantics:

  * the first is the frozen reference implementation in ``workload.py``
    (the golden definition),
  * this one is the agent-side composition used by the Sequential arm,
  * the third is the Monty program (code-mode arm) and the standalone
    ad-hoc script.

The correctness gate compares all of them against the frozen golden, so a
semantic slip in any one implementation is visible.
"""
from __future__ import annotations

from collections import OrderedDict

ELEVATIONS = ["Elevation_01", "Elevation_02", "Elevation_03", "Elevation_04"]
BAND_ORDER = ["Ground", "First", "Second", "Third", "Roof"]
TOLERANCE_M = 0.05


def _rows(elevation_data: dict) -> list:
    rows = []
    for sheet in ELEVATIONS:
        rows.extend(elevation_data[sheet]["openings"])
    return rows


def _entry(width, members) -> dict:
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


def compose_T1(elevation_data: dict) -> dict:
    counts = OrderedDict()
    for sheet in ELEVATIONS:
        per_band = OrderedDict()
        for band in BAND_ORDER:
            per_band[band] = 0
        for opening in elevation_data[sheet]["openings"]:
            per_band[opening["floor_band"]] = per_band.get(opening["floor_band"], 0) + 1
        counts[sheet] = per_band
    return {
        "task_id": "T1",
        "name": "elevation_x_band_opening_count_matrix",
        "band_order": list(BAND_ORDER),
        "matrix": counts,
    }


def compose_T2(elevation_data: dict) -> dict:
    rows = _rows(elevation_data)
    buckets = OrderedDict()
    for opening in rows:
        buckets.setdefault(opening["width_m"], []).append(opening)
    groups = []
    for width in sorted(buckets):
        entry = _entry(width, buckets[width])
        entry["members"] = [
            {
                "id": m["id"],
                "sheet": m["id"].split("-")[0],
                "floor_band": m["floor_band"],
                "sill_m": m["sill_m"],
                "head_m": m["head_m"],
            }
            for m in buckets[width]
        ]
        groups.append(entry)
    by_band = OrderedDict()
    for band in BAND_ORDER:
        band_rows = [o for o in rows if o["floor_band"] == band]
        band_buckets = OrderedDict()
        for opening in band_rows:
            band_buckets.setdefault(opening["width_m"], []).append(opening)
        by_band[band] = [_entry(w, band_buckets[w]) for w in sorted(band_buckets)]
    return {
        "task_id": "T2",
        "name": "width_consistency_check",
        "tolerance_m": TOLERANCE_M,
        "groups": groups,
        "by_band": by_band,
    }


def compose_T3(elevation_data: dict) -> dict:
    rows = _rows(elevation_data)
    bands = []
    for band in BAND_ORDER:
        members = [o for o in rows if o["floor_band"] == band]
        if not members:
            bands.append({
                "band": band, "count": 0, "sill_min_m": None, "sill_max_m": None,
                "head_min_m": None, "head_max_m": None,
            })
            continue
        sills = [o["sill_m"] for o in members]
        heads = [o["head_m"] for o in members]
        bands.append({
            "band": band,
            "count": len(members),
            "sill_min_m": min(sills),
            "sill_max_m": max(sills),
            "head_min_m": min(heads),
            "head_max_m": max(heads),
        })
    return {"task_id": "T3", "name": "band_sill_head_ranges", "bands": bands}


def compose_T4(elevation_data: dict, crop_results: list) -> dict:
    crops = []
    index = 0
    for sheet in ELEVATIONS:
        for opening in elevation_data[sheet]["openings"]:
            if opening["floor_band"] != "Ground":
                continue
            result = crop_results[index]
            index += 1
            crops.append({
                "id": opening["id"],
                "sheet": sheet,
                "bbox_px": list(opening["bbox_px"]),
                "label": opening["id"].lower() + "_ground",
                "file_name": result["path"].split("/")[-1],
                "size_px": list(result["size_px"]),
                "source_box_px": list(result["source_box_px"]),
            })
    return {"task_id": "T4", "name": "ground_band_evidence_crops", "crops": crops}


def compose_T5(elevation_data: dict, summary: dict) -> dict:
    return {
        "task_id": "T5",
        "name": "audit_prep_composite",
        "band_order": list(BAND_ORDER),
        "opening_count_matrix": compose_T1(elevation_data)["matrix"],
        "band_sill_head_ranges": compose_T3(elevation_data)["bands"],
        "findings_summary": summary,
    }

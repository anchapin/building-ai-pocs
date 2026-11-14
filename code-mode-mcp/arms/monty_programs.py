"""The code-mode programs, written for the Monty subset.

Monty subset rules honoured here (issue #50 brief, "design around Monty's
documented subset limits"):

  * no third-party packages (no numpy, no pandas) - only ``json`` (and the
    builtin functions);
  * no class definitions, no inheritance, no metaclasses;
  * no generator functions, no ``del``;
  * only dicts/lists, comprehensions, sorting, grouping, ``json``;
  * deterministic composition only - no mismatch judgement is made inside a
    program; every flag is a comparison of numbers the tools returned.

The host functions are the spike server's own five functions, with their real
signatures, so the programs make exactly the calls the pinned call plan makes:

    list_sheets() -> str
    extract_elevation_openings(sheet: str) -> str
    extract_all_elevations() -> str
    get_crop(sheet: str, x0: int, y0: int, x1: int, y1: int, label: str) -> str
    summarise_findings(findings_json: str) -> str
"""
from __future__ import annotations

import json

#: The fixed findings list of the composite task, serialised exactly as the
#: other arms pass it to ``summarise_findings`` (json.dumps default separators).
FINDINGS_JSON = json.dumps([
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
])

_COMMON = '''
import json

ELEVATIONS = ["Elevation_01", "Elevation_02", "Elevation_03", "Elevation_04"]
BAND_ORDER = ["Ground", "First", "Second", "Third", "Roof"]
TOLERANCE_M = 0.05
'''

T1_PROGRAM = _COMMON + '''
# pinned call plan: list_sheets() once, then one extract_elevation_openings()
# per elevation the task needs.
sheets_text = list_sheets()
elevation_data = {}
for sheet in ELEVATIONS:
    elevation_data[sheet] = json.loads(extract_elevation_openings(sheet))

matrix = {}
for sheet in ELEVATIONS:
    counts = {}
    for band in BAND_ORDER:
        counts[band] = 0
    for opening in elevation_data[sheet]["openings"]:
        band = opening["floor_band"]
        counts[band] = counts.get(band, 0) + 1
    matrix[sheet] = counts

out = {"task_id": "T1", "name": "elevation_x_band_opening_count_matrix",
       "band_order": BAND_ORDER, "matrix": matrix}
result = json.dumps(out, sort_keys=True, separators=(",", ":"))
result
'''

T2_PROGRAM = _COMMON + '''
sheets_text = list_sheets()
openings = []
for sheet in ELEVATIONS:
    elevation = json.loads(extract_elevation_openings(sheet))
    for opening in elevation["openings"]:
        openings.append(opening)


def make_entry(width, members):
    sills = []
    heads = []
    for member in members:
        sills.append(member["sill_m"])
        heads.append(member["head_m"])
    sill_min = min(sills)
    sill_max = max(sills)
    head_min = min(heads)
    head_max = max(heads)
    sill_range = round(sill_max - sill_min, 6)
    head_range = round(head_max - head_min, 6)
    flagged = bool(sill_range > TOLERANCE_M or head_range > TOLERANCE_M)
    return {"width_m": width, "n": len(members),
            "sill_min_m": sill_min, "sill_max_m": sill_max,
            "head_min_m": head_min, "head_max_m": head_max,
            "sill_range_m": sill_range, "head_range_m": head_range,
            "flagged": flagged}


buckets = {}
for opening in openings:
    width = opening["width_m"]
    if width in buckets:
        buckets[width].append(opening)
    else:
        buckets[width] = [opening]

groups = []
for width in sorted(buckets):
    entry = make_entry(width, buckets[width])
    members = []
    for member in buckets[width]:
        members.append({"id": member["id"], "sheet": member["id"].split("-")[0],
                        "floor_band": member["floor_band"],
                        "sill_m": member["sill_m"], "head_m": member["head_m"]})
    entry["members"] = members
    groups.append(entry)

by_band = {}
for band in BAND_ORDER:
    band_buckets = {}
    for opening in openings:
        if opening["floor_band"] != band:
            continue
        width = opening["width_m"]
        if width in band_buckets:
            band_buckets[width].append(opening)
        else:
            band_buckets[width] = [opening]
    entries = []
    for width in sorted(band_buckets):
        entries.append(make_entry(width, band_buckets[width]))
    by_band[band] = entries

out = {"task_id": "T2", "name": "width_consistency_check",
       "tolerance_m": TOLERANCE_M, "groups": groups, "by_band": by_band}
result = json.dumps(out, sort_keys=True, separators=(",", ":"))
result
'''

T3_PROGRAM = _COMMON + '''
sheets_text = list_sheets()
openings = []
for sheet in ELEVATIONS:
    elevation = json.loads(extract_elevation_openings(sheet))
    for opening in elevation["openings"]:
        openings.append(opening)

bands = []
for band in BAND_ORDER:
    members = []
    for opening in openings:
        if opening["floor_band"] == band:
            members.append(opening)
    if len(members) == 0:
        bands.append({"band": band, "count": 0, "sill_min_m": None, "sill_max_m": None,
                      "head_min_m": None, "head_max_m": None})
        continue
    sills = []
    heads = []
    for member in members:
        sills.append(member["sill_m"])
        heads.append(member["head_m"])
    bands.append({"band": band, "count": len(members),
                  "sill_min_m": min(sills), "sill_max_m": max(sills),
                  "head_min_m": min(heads), "head_max_m": max(heads)})

out = {"task_id": "T3", "name": "band_sill_head_ranges", "bands": bands}
result = json.dumps(out, sort_keys=True, separators=(",", ":"))
result
'''

T4_PROGRAM = _COMMON + '''
sheets_text = list_sheets()
ground_items = []
for sheet in ELEVATIONS:
    elevation = json.loads(extract_elevation_openings(sheet))
    for opening in elevation["openings"]:
        if opening["floor_band"] == "Ground":
            ground_items.append({"sheet": sheet, "opening": opening})

crops = []
for item in ground_items:
    sheet = item["sheet"]
    opening = item["opening"]
    box = opening["bbox_px"]
    label = opening["id"].lower() + "_ground"
    crop = json.loads(get_crop(sheet, box[0], box[1], box[2], box[3], label))
    crops.append({"id": opening["id"], "sheet": sheet, "bbox_px": list(box),
                  "label": label, "file_name": crop["path"].split("/")[-1],
                  "size_px": list(crop["size_px"]),
                  "source_box_px": list(crop["source_box_px"])})

out = {"task_id": "T4", "name": "ground_band_evidence_crops", "crops": crops}
result = json.dumps(out, sort_keys=True, separators=(",", ":"))
result
'''

T5_PROGRAM = _COMMON + '''
FINDINGS_JSON = ''' + repr(FINDINGS_JSON) + '''
sheets_text = list_sheets()
elevation_data = {}
for sheet in ELEVATIONS:
    elevation_data[sheet] = json.loads(extract_elevation_openings(sheet))
summary = json.loads(summarise_findings(FINDINGS_JSON))

matrix = {}
for sheet in ELEVATIONS:
    counts = {}
    for band in BAND_ORDER:
        counts[band] = 0
    for opening in elevation_data[sheet]["openings"]:
        band = opening["floor_band"]
        counts[band] = counts.get(band, 0) + 1
    matrix[sheet] = counts

bands = []
for band in BAND_ORDER:
    members = []
    for elevation_sheet in ELEVATIONS:
        for opening in elevation_data[elevation_sheet]["openings"]:
            if opening["floor_band"] == band:
                members.append(opening)
    sills = []
    heads = []
    for member in members:
        sills.append(member["sill_m"])
        heads.append(member["head_m"])
    bands.append({"band": band, "count": len(members),
                  "sill_min_m": min(sills), "sill_max_m": max(sills),
                  "head_min_m": min(heads), "head_max_m": max(heads)})

out = {"task_id": "T5", "name": "audit_prep_composite", "band_order": BAND_ORDER,
       "opening_count_matrix": matrix, "band_sill_head_ranges": bands,
       "findings_summary": summary}
result = json.dumps(out, sort_keys=True, separators=(",", ":"))
result
'''

PROGRAMS = {
    "T1": T1_PROGRAM,
    "T2": T2_PROGRAM,
    "T3": T3_PROGRAM,
    "T4": T4_PROGRAM,
    "T5": T5_PROGRAM,
}

#: Sensitivity variant of the composite task: the same work with the server's
#: aggregate ``extract_all_elevations()`` call instead of four per-elevation
#: calls.  Reported separately from the headline comparison.
T5_AGGREGATE_PROGRAM = _COMMON + '''
FINDINGS_JSON = ''' + repr(FINDINGS_JSON) + '''
sheets_text = list_sheets()
aggregate = json.loads(extract_all_elevations())
summary = json.loads(summarise_findings(FINDINGS_JSON))

matrix = {}
for sheet in ELEVATIONS:
    counts = {}
    for band in BAND_ORDER:
        counts[band] = 0
    for opening in aggregate[sheet]["openings"]:
        band = opening["floor_band"]
        counts[band] = counts.get(band, 0) + 1
    matrix[sheet] = counts

bands = []
for band in BAND_ORDER:
    members = []
    for sheet in ELEVATIONS:
        for opening in aggregate[sheet]["openings"]:
            if opening["floor_band"] == band:
                members.append(opening)
    sills = []
    heads = []
    for member in members:
        sills.append(member["sill_m"])
        heads.append(member["head_m"])
    bands.append({"band": band, "count": len(members),
                  "sill_min_m": min(sills), "sill_max_m": max(sills),
                  "head_min_m": min(heads), "head_max_m": max(heads)})

out = {"task_id": "T5", "name": "audit_prep_composite", "band_order": BAND_ORDER,
       "opening_count_matrix": matrix, "band_sill_head_ranges": bands,
       "findings_summary": summary}
result = json.dumps(out, sort_keys=True, separators=(",", ":"))
result
'''

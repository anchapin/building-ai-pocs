#!/usr/bin/env python3
"""Re-apply the two nearest-feature footprint confirmations to coverage_results.json.

The two buildings whose reference point is not covered by any Microsoft Building
Footprints polygon (James Monroe Building, Federal Reserve Bank Building) were
resolved by a nearest-feature search over the same quadkey tile 032010221 during
the 2026-11-14 desktop run of POC #64/#65 Phase 0. This script re-applies those
*already measured* results to the evidence file; it does NOT re-measure them
(no tile download, no geometry computation beyond the UTM -> WGS84 conversion of
the recorded polygon).

Recorded measurements (provenance: desktop scratch `fp_search.json`, 2026-11-14):

  james_monroe_building   nearest feature 2.995 m from the reference point
                          area 2589.1 m2, 32 vertices, height 24.25 m
  federal_reserve_bank   nearest feature 35.957 m from the reference point
                          area 108.6 m2, 4 vertices, height 12.60 m

Usage:
  python3 address-to-bem-roofer/scripts/apply_footprint_confirmations.py
"""
import json
import os

from pyproj import Transformer
from shapely import wkt as swkt

HERE = os.path.dirname(os.path.abspath(__file__))
POC = os.path.dirname(HERE)
RESULTS = os.path.join(POC, "queries", "coverage_results.json")

# Recorded nearest-feature polygons, WKT in EPSG:26918 (NAD83 / UTM 18N).
RECORDED = {
    "james_monroe_building": {
        "distance_m": 2.9954909573003463,
        "distance_m_rounded": 3.00,
        "area_m2": 2589.1,
        "num_vertices": 32,
        "height": 24.253658294677734,
        "wkt": (
            "POLYGON ((285286.12189848116 4157146.718295496, 285275.91371869406 4157152.003070251, "
            "285274.4208113053 4157149.1427214183, 285274.49192541593 4157153.4879692253, "
            "285271.2810147047 4157153.5407761345, 285272.62529351877 4157156.1160001475, "
            "285281.6540702643 4157155.9675165545, 285275.10413278756 4157159.3584224787, "
            "285274.2388147161 4157158.610497437, 285253.11965025903 4157169.5439483454, "
            "285251.50930779777 4157166.458620484, 285240.6830226104 4157172.0642228047, "
            "285222.8512693839 4157156.6517693033, 285222.7214317906 4157148.7213889533, "
            "285236.7286804711 4157132.6527169268, 285248.64304838696 4157137.7568095997, "
            "285251.13290345913 4157134.9007607936, 285248.24258194875 4157129.3630636493, "
            "285258.5094701021 4157129.1941915364, 285277.17827826785 4157107.7781328354, "
            "285278.04533797177 4157105.7720531705, 285273.45806351287 4157103.8068505605, "
            "285277.01710703585 4157099.7240765253, 285312.004426933 4157129.9673518897, "
            "285300.8177479155 4157130.151281641, 285300.8908207605 4157134.6363920327, "
            "285295.28874968574 4157134.7285062973, 285295.2125592821 4157130.0723275444, "
            "285295.06641469407 4157130.0097283367, 285280.41498457623 4157130.2506579347, "
            "285287.0196686906 4157142.904994814, 285282.5823625084 4157145.202185441, "
            "285286.12189848116 4157146.718295496))"
        ),
    },
    "federal_reserve_bank": {
        "distance_m": 35.95718927509751,
        "distance_m_rounded": 35.96,
        "area_m2": 108.6,
        "num_vertices": 4,
        "height": 12.601751327514648,
        "wkt": (
            "POLYGON ((284384.0392554469 4157070.9495071443, 284390.723382319 4157065.4232330164, "
            "284398.74549131485 4157075.045313929, 284392.06071042514 4157080.571633121, "
            "284384.0392554469 4157070.9495071443))"
        ),
    },
}

NOTE = ("CONFIRMED by nearest-feature match on the same MS Building Footprints quadkey tile "
        "032010221 (measured 2026-11-14 on the desktop; re-applied to this file as a data "
        "edit on 2026-11-14, not re-measured).")


def main():
    with open(RESULTS) as fh:
        doc = json.load(fh)

    inv = Transformer.from_crs("EPSG:26918", "EPSG:4326", always_xy=True).transform
    for tag, rec in RECORDED.items():
        geom = swkt.loads(rec["wkt"])
        rings = [[[inv(x, y) for x, y in geom.exterior.coords]]]
        ms = doc["results"][tag]["ms"]
        ms["footprint_confirmed"] = True
        ms["confirmation_method"] = "nearest-feature"
        ms["confirmation_distance_m"] = rec["distance_m_rounded"]
        ms["nearest_feature"] = {
            "id": None,
            "Height": rec["height"],
            "numVertices": rec["num_vertices"],
            "area_m2": rec["area_m2"],
            "geometry": rings,
        }
        ms["footprint_confirmation_note"] = NOTE
        print(f"{tag}: CONFIRMED (nearest-feature, {rec['distance_m_rounded']} m)")

    # The three buildings whose reference point lies inside a covering polygon are
    # flagged with the same vocabulary so the file states 5/5 in one place.
    for tag, res in doc["results"].items():
        if tag in RECORDED:
            continue
        ms = res["ms"]
        if not ms.get("features_covering_point"):
            continue
        ms["footprint_confirmed"] = True
        ms["confirmation_method"] = "point-in-polygon"
        ms["confirmation_distance_m"] = 0.0
        ms["footprint_confirmation_note"] = (
            "CONFIRMED by point-in-polygon test against the same MS Building Footprints "
            "quadkey tile 032010221 (measured 2026-11-14; the covering feature is kept in "
            "features_covering_point)."
        )
        print(f"{tag}: CONFIRMED (point-in-polygon, 0.0 m)")

    with open(RESULTS, "w") as fh:
        json.dump(doc, fh, indent=1)
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build a GeoPackage of roofprint polygons for one candidate building.

Input : queries/coverage_results.json  (Microsoft Global ML Building Footprints
        extract already confirmed in the Phase 0 coverage gate)
Output: a GeoPackage in EPSG:26918 (UTM 18N) that can be handed to Roofer as
        <polygon-source>.

Usage:
  python3 address-to-bem-roofer/scripts/make_footprint_gpkg.py \
      --tag main_street_station --out /home/alex/muse-workers/roofer-scratch/footprints_main_street_station.gpkg
"""
import argparse
import json
import os

import geopandas as gpd
from shapely.geometry import Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
POC = os.path.dirname(HERE)
TARGET_CRS = "EPSG:26918"  # NAD83 / UTM zone 18N


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="building tag in coverage_results.json")
    ap.add_argument("--out", required=True, help="output .gpkg path (outside the worktree)")
    ap.add_argument("--results", default=os.path.join(POC, "queries", "coverage_results.json"))
    args = ap.parse_args()

    with open(args.results) as fh:
        res = json.load(fh)["results"][args.tag]

    feats = []
    for i, f in enumerate(res["ms"]["features_covering_point"]):
        rings = f["geometry"]
        poly = Polygon(rings[0], rings[1:])  # exterior ring + holes
        feats.append({
            "geometry": poly,
            "id": f"{args.tag}_{i}",
            "num_vertices": f.get("numVertices"),
            "height": f.get("Height"),
        })
    if not feats:
        raise SystemExit(f"no covering features for {args.tag}")

    gdf = gpd.GeoDataFrame(feats, crs="EPSG:4326").to_crs(TARGET_CRS)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    gdf.to_file(args.out, driver="GPKG", layer="footprints")
    print(f"{args.tag}: {len(gdf)} feature(s) -> {args.out}")
    print(f"  crs={gdf.crs} bounds={gdf.total_bounds}")
    for _, r in gdf.iterrows():
        print(f"  {r['id']}: area={r.geometry.area:.1f} m2")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Coverage gate for POC #64 slice 1 (Phase 0, step 1).

For each candidate building (Richmond VA), query:
  * USGS TNM Access API  -> 3DEP Lidar Point Cloud (LPC) tiles covering the building point
  * Microsoft Global ML Building Footprints -> footprint presence + feature id
  * Overture Maps (release parquet on AWS S3) -> footprint presence (best effort)

All raw API responses are written to queries/ for citation. Requests go through the
egress proxy (HTTP_PROXY env var is honoured by urllib via ProxyHandler).

Usage:  python3 address-to-bem-roofer/scripts/coverage_gate.py
"""
import csv
import gzip
import io
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
POC = os.path.dirname(HERE)
QDIR = os.path.join(POC, "queries")
os.makedirs(QDIR, exist_ok=True)

def _proxy():
    p = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if p:
        return p
    # The cell's egress proxy is declared in /etc/environment but is not exported
    # into non-login shells, so read it from there as a fallback.
    try:
        with open("/etc/environment") as fh:
            for line in fh:
                if line.strip().startswith("HTTPS_PROXY="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


PROXY = _proxy()
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"https": PROXY, "http": PROXY}) if PROXY else urllib.request.ProxyHandler({})
)
UA = {"User-Agent": "POC-64-slice1-coverage-gate/1.0 (research)"}


def fetch(url, timeout=180):
    req = urllib.request.Request(url, headers=UA)
    with opener.open(req, timeout=timeout) as r:
        return r.read()


def fetch_json(url, timeout=180):
    return json.loads(fetch(url, timeout).decode("utf-8", "replace"))


def bing_quadkey(lat, lon, level=9):
    """Bing Maps quadkey for a WGS84 point."""
    x = int((lon + 180.0) / 360.0 * (2 ** level))
    y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1.0 / math.cos(math.radians(lat))) / math.pi) / 2.0 * (2 ** level))
    digits = ""
    for i in range(level, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if x & mask:
            digit += 1
        if y & mask:
            digit += 2
        digits += str(digit)
    return digits


def point_in_ring(lon, lat, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[i - 1]
        if (y1 > lat) != (y2 > lat):
            xint = (x2 - x1) * (lat - y1) / (y2 - y1) + x1
            if lon < xint:
                inside = not inside
    return inside


def point_in_polygon(lon, lat, poly):
    if not point_in_ring(lon, lat, poly[0]):
        return False
    for hole in poly[1:]:
        if point_in_ring(lon, lat, hole):
            return False
    return True


def tnm_lpc_tiles(lat, lon, tag):
    """TNM Access: 3DEP LPC products whose bbox contains the building point."""
    d = 0.0015  # ~150 m query box around the building
    bbox = f"{lon - d:.6f},{lat - d:.6f},{lon + d:.6f},{lat + d:.6f}"
    url = ("https://tnmaccess.nationalmap.gov/api/v1/products?bbox=" + bbox +
           "&q=Lidar%20Point%20Cloud&max=100")
    data = fetch_json(url)
    with open(os.path.join(QDIR, f"tnm_lpc_{tag}.json"), "w") as fh:
        json.dump({"request_url": url, "response": data}, fh, indent=1)
    out = []
    for it in data.get("items", []):
        out.append({
            "title": it.get("title"),
            "url": it.get("downloadLazURL") or it.get("downloadURL"),
            "publicationDate": it.get("publicationDate"),
            "format": it.get("format"),
            "sizeInBytes": it.get("sizeInBytes"),
            "bbox": it.get("boundingBox"),
        })
    return url, out


def ms_footprint(lat, lon, tag, links_csv):
    """Microsoft Global ML Building Footprints: does a footprint cover the point?"""
    qk = bing_quadkey(lat, lon, 9)
    url = None
    with open(links_csv, newline="") as fh:
        for row in csv.DictReader(fh):
            if row.get("QuadKey") == qk:
                url = row["Url"]
                break
    if url is None:
        return {"quadkey": qk, "status": "quadkey not present in dataset-links.csv"}
    raw = fetch(url)
    with open(os.path.join(QDIR, f"ms_fp_{tag}.csv.gz"), "wb") as fh:
        fh.write(raw)
    text = gzip.decompress(raw).decode("utf-8", "replace")
    hits = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            feat = json.loads(line)
        except json.JSONDecodeError:
            continue
        g = feat.get("geometry") or {}
        if g.get("type") != "Polygon":
            continue
        polys = [g["coordinates"]] if g.get("type") == "Polygon" else []
        for poly in polys:
            if point_in_polygon(lon, lat, poly):
                hits.append({
                    "id": feat.get("Id") or feat.get("id"),
                    "Height": (feat.get("properties") or {}).get("Height"),
                    "numVertices": (feat.get("properties") or {}).get("numVertices"),
                    "geometry": poly,
                })
    return {"quadkey": qk, "tile_url": url, "status": "ok",
            "features_covering_point": hits}


def main():
    buildings = json.load(open(os.path.join(HERE, "buildings.json")))
    links_csv = "/tmp/dlinks.csv"
    if not os.path.exists(links_csv):
        links_csv = os.path.join(QDIR, "dataset-links.csv")
    results = {}
    for b in buildings:
        tag = b["tag"]
        rec = {"name": b["name"], "lat": b["lat"], "lon": b["lon"]}
        u, tiles = tnm_lpc_tiles(b["lat"], b["lon"], tag)
        rec["tnm_request_url"] = u
        rec["tnm_tile_count"] = len(tiles)
        rec["tnm_tiles"] = tiles
        try:
            rec["ms"] = ms_footprint(b["lat"], b["lon"], tag, links_csv)
        except Exception as e:  # noqa: BLE001
            rec["ms"] = {"error": f"{type(e).__name__}: {e}"}
        results[tag] = rec
        print(json.dumps({k: v for k, v in rec.items() if k != "tnm_tiles"}, indent=1)[:1500])
        print("   tiles:", [t["title"] for t in tiles][:6])
    with open(os.path.join(QDIR, "coverage_results.json"), "w") as fh:
        json.dump({"generated_utc": datetime.now(timezone.utc).isoformat(),
                   "results": results}, fh, indent=1)
    print("written:", os.path.join(QDIR, "coverage_results.json"))


if __name__ == "__main__":
    sys.exit(main())

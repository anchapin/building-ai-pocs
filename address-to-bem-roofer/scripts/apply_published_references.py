#!/usr/bin/env python3
"""Record the published height / footprint-area references for the 5 candidates.

One web search per building (2026-11-14); nothing is estimated. Where no published
figure was found, the building is recorded as NOT SOURCED.

Usage:
  python3 address-to-bem-roofer/scripts/apply_published_references.py
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
POC = os.path.dirname(HERE)
RESULTS = os.path.join(POC, "queries", "coverage_results.json")

REFERENCES = {
    "va_state_capitol": {
        "figure": "Roof height 85 ft (source given as \"Google Earth\" by SkyscraperPage); floor count 3",
        "source_url": "https://skyscraperpage.com/cities/?buildingID=190890",
        "status": "SOURCED",
    },
    "james_monroe_building": {
        "figure": "137 m (449 ft), 29 floors",
        "source_url": "https://en.wikipedia.org/wiki/James_Monroe_Building",
        "status": "SOURCED",
    },
    "600_canal_place": {
        "figure": "127.2 m (417 ft), 20 floors",
        "source_url": ("https://en.wikipedia.org/wiki/600_Canal_Place ; "
                       "https://en.wikipedia.org/wiki/List_of_tallest_buildings_in_Richmond"),
        "status": "SOURCED",
    },
    "main_street_station": {
        "figure": ("NOT SOURCED - the Wikipedia article publishes no height or footprint-area "
                   "figure and the follow-up web search was blocked by a CAPTCHA within the "
                   "search budget"),
        "source_url": "https://en.wikipedia.org/wiki/Richmond_Main_Street_Station",
        "status": "NOT SOURCED",
    },
    "federal_reserve_bank": {
        "figure": "119.8 m (394 ft), 26 floors",
        "source_url": ("https://en.wikipedia.org/wiki/List_of_tallest_buildings_in_Richmond ; "
                       "https://www.skyscrapercenter.com/building/federal-reserve-bank-building/10616"),
        "status": "SOURCED",
    },
}


def main():
    with open(RESULTS) as fh:
        doc = json.load(fh)
    for tag, ref in REFERENCES.items():
        doc["results"][tag]["published_reference"] = ref
        print(f"{tag}: {ref['status']} - {ref['figure']}")
    with open(RESULTS, "w") as fh:
        json.dump(doc, fh, indent=1)
    print(f"wrote {RESULTS}")


if __name__ == "__main__":
    main()

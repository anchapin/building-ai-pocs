"""Make `code-mode-mcp/` importable from the tests (`import workload`) and
provide the live-server fixtures shared by the test modules."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
if os.path.join(HERE, "arms") not in sys.path:
    sys.path.insert(0, os.path.join(HERE, "arms"))

import workload  # noqa: E402


@pytest.fixture(scope="session")
def server():
    """The read-only spike server module (imported, never edited)."""
    return workload.load_server()


@pytest.fixture(scope="session")
def elevation_data(server):
    data = {}
    for sheet in workload.ELEVATIONS:
        data[sheet] = json.loads(server.extract_elevation_openings(sheet))
    return data


@pytest.fixture(scope="session")
def crop_results(server, elevation_data):
    results = []
    for req in workload.crop_requests(elevation_data):
        results.append(json.loads(server.get_crop(
            req["sheet"], req["bbox_px"][0], req["bbox_px"][1],
            req["bbox_px"][2], req["bbox_px"][3], req["label"])))
    return results


@pytest.fixture(scope="session")
def summary(server):
    return json.loads(server.summarise_findings(json.dumps(workload.FINDINGS)))

"""The freeze must hold: the frozen workload and the five golden files are
byte-for-byte the ones that were hashed before any measurement ran."""
import json
import os

import workload

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(HERE, "golden", "golden_manifest.json")


def manifest():
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_manifest_covers_every_task():
    man = manifest()
    assert sorted(man["golden"]) == sorted(workload.TASK_IDS)
    for task_id, entry in man["golden"].items():
        assert entry["file"] == workload.GOLDEN_FILES[task_id]


def test_frozen_workload_hash_unchanged():
    """The freeze evidence: workload.py has not been edited since the freeze."""
    man = manifest()
    assert workload.sha256_file(os.path.join(HERE, "workload.py")) == man["frozen_workload_sha256"]


def test_frozen_golden_hashes_unchanged():
    man = manifest()
    for task_id, entry in man["golden"].items():
        path = os.path.join(HERE, "golden", entry["file"])
        assert workload.sha256_file(path) == entry["sha256"], task_id


def test_golden_files_are_canonical_json():
    """Each golden file parses and carries its task id."""
    for task_id in workload.TASK_IDS:
        data = workload.load_golden(task_id) if hasattr(workload, "load_golden") else None
        path = os.path.join(HERE, "golden", workload.GOLDEN_FILES[task_id])
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["task_id"] == task_id
        assert data["name"] == workload.TASKS_BY_ID[task_id]["name"]


def test_reference_implementations_reproduce_the_golden():
    """The frozen reference code still reproduces the frozen golden from the
    live server, i.e. the golden is the reference implementation's output and
    not a hand-typed artefact."""
    golden = workload.compute_golden()
    for task_id in workload.TASK_IDS:
        with open(os.path.join(HERE, "golden", workload.GOLDEN_FILES[task_id]), encoding="utf-8") as fh:
            frozen = json.load(fh)
        assert golden[task_id] == frozen, task_id

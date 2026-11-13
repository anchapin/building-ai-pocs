"""The assembler: deterministic, manifest-only, explicit about refusals."""

import json
import os

import assembler
import manifest as manifest_mod
import uispec

import pytest


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)["requests"]


@pytest.fixture(scope="module")
def case_requests():
    return _load(os.path.join(HERE, "fixtures", "case_requests.json"))


@pytest.fixture(scope="module")
def adversarial():
    return _load(os.path.join(HERE, "adversarial", "requests.json"))


@pytest.fixture(scope="module")
def out_of_catalog():
    return _load(os.path.join(HERE, "fixtures", "requests_out_of_catalog.json"))


@pytest.fixture(scope="module")
def runs():
    return {run_id: manifest_mod.load_run(run_id) for run_id in manifest_mod.list_runs()}


def _manifest(runs, run_id):
    return manifest_mod.manifest_from_run(runs[run_id])


def test_case_requests_assemble_into_valid_specs(case_requests, runs):
    for request in case_requests:
        man = _manifest(runs, request["run_id"])
        result = assembler.assemble(request["request"], man)
        assert not uispec.is_refusal(result), (request["id"], result)
        assert uispec.validate_spec(result, man) == []
        assert result["run_id"] == request["run_id"]


def test_assembly_is_deterministic(case_requests, runs):
    for request in case_requests:
        man = _manifest(runs, request["run_id"])
        first = assembler.assemble(request["request"], man)
        second = assembler.assemble(request["request"], man)
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_no_binding_is_invented(case_requests, runs):
    """Every field binding of every generated spec exists in the manifest."""
    for request in case_requests:
        man = _manifest(runs, request["run_id"])
        result = assembler.assemble(request["request"], man)
        if uispec.is_refusal(result):
            continue
        for component in result["components"]:
            for key, value in (component.get("bindings") or {}).items():
                if key in ("series", "field", "reference_series", "log_field"):
                    entry = manifest_mod.find_entry(man, value)
                    assert entry is not None, (request["id"], key, value)


def test_adversarial_requests_are_all_refused(adversarial, runs):
    for request in adversarial:
        man = _manifest(runs, request["run_id"])
        result = assembler.assemble(request["request"], man)
        assert uispec.is_refusal(result), (request["id"], result)
        assert result["reason_code"] == request["expect_code"], (request["id"], result)


def test_adversarial_set_has_at_least_ten_requests(adversarial):
    assert len(adversarial) >= 10
    categories = {request["category"] for request in adversarial}
    for expected in ("nonexistent_field", "wrong_unit", "different_run", "mid_run_state"):
        assert expected in categories


def test_out_of_catalog_requests_are_refused(out_of_catalog, runs):
    for request in out_of_catalog:
        man = _manifest(runs, request["run_id"])
        result = assembler.assemble(request["request"], man)
        assert uispec.is_refusal(result), (request["id"], result)
        assert result["reason_code"] == request["expect_code"], (request["id"], result)


def test_unknown_field_is_refused_not_guessed(runs):
    man = _manifest(runs, "run_ashrae140_case1")
    result = assembler.assemble("plot the CO2 generation rate over time", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unknown_field"


def test_wrong_unit_is_refused(runs):
    man = _manifest(runs, "run_ashrae140_case1")
    result = assembler.assemble("show zone1 air temperature in kW", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unit_mismatch"


def test_other_run_is_refused(runs):
    man = _manifest(runs, "run_ashrae140_case1")
    result = assembler.assemble("chart run_humid_latent_case3 zone1 relative humidity", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "run_mismatch"


def test_mid_run_state_is_refused(runs):
    man = _manifest(runs, "run_ashrae140_case1")
    result = assembler.assemble("show the mid-run solver state for zone1", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "mid_run_state_unavailable"


def test_a_mixed_request_refuses_the_whole_thing(runs):
    """One real field plus one invented field: nothing is served."""
    man = _manifest(runs, "run_ashrae140_case1")
    result = assembler.assemble("plot zone1 air temperature and the CO2 generation rate", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unknown_field"


def test_empty_request_is_refused(runs):
    man = _manifest(runs, "run_ashrae140_case1")
    result = assembler.assemble("   ", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "empty_request"


def test_every_primitive_can_be_produced(runs):
    """All six catalog primitives are reachable from a request."""
    produced = set()
    for run_id, run in runs.items():
        man = manifest_mod.manifest_from_run(run)
        for request in (
            "chart zone1 air temperature",
            "add a diff table of zone1 air temperature",
            "a kpi card for total heating energy",
            "highlight zone zone1 air temperature",
            "show the last 20 lines of the run log",
            "show the run inputs",
        ):
            result = assembler.assemble(request, man)
            if not uispec.is_refusal(result):
                produced.update(c["primitive"] for c in result["components"])
    assert produced == {
        "TimeSeriesChart",
        "DiffTable",
        "KPICard",
        "ZoneHighlight",
        "LogTail",
        "ParamInspector",
    }


def test_the_assembler_never_reads_values(runs):
    """The assembler module must not touch series values."""
    source = open(os.path.join(HERE, "assembler.py"), "r", encoding="utf-8").read()
    assert '"values"' not in source
    assert "'values'" not in source

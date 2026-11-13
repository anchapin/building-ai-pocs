"""The unit vocabulary is shared: the assembler knows every catalog unit.

Regression tests for issue #41 (JiT H1): the request
``chart zone1 air temperature in K`` used to fall through the assembler's
shorter, hand-written list of "recognised" units and silently bind the
field's own unit (degC).  A unit the catalog knows must always be checked
against the field, and a unit the catalog cannot check must be refused.
"""

import assembler
import catalog
import manifest as manifest_mod
import uispec

import pytest


RUN_ID = "run_ashrae140_case1"
H1_REQUEST = "chart zone1 air temperature in K"


@pytest.fixture(scope="module")
def man():
    return manifest_mod.manifest_from_run(manifest_mod.load_run(RUN_ID))


def test_h1_kelvin_request_never_binds_a_degc_spec(man):
    """JiT H1 verbatim: 'chart zone1 air temperature in K'.

    Either the request binds K (the field is measured in K) or it is
    refused - a degC-bound spec is never acceptable.
    """
    result = assembler.assemble(H1_REQUEST, man)
    if uispec.is_refusal(result):
        assert result["reason_code"] in ("unit_mismatch", "unknown_unit"), result
        assert "K" in result["message"], result
        return
    for component in result["components"]:
        assert component["bindings"].get("unit") == "K", result


def test_h1_kelvin_request_refuses_against_a_degc_field(man):
    """zone1_air_temperature is measured in degC, so K is a mismatch."""
    result = assembler.assemble(H1_REQUEST, man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unit_mismatch"
    assert result["requested_unit"] == "K"
    assert result["field_unit"] == "°C"


def test_h1_kelvin_request_binds_kelvin_when_the_field_is_in_kelvin():
    """The other half of the H1 case: a kelvin field binds kelvin."""
    kelvin_manifest = {
        "run_id": "run_kelvin_case",
        "run_name": "run_kelvin_case",
        "status": "ok",
        "entries": [
            {
                "name": "zone1_air_temperature",
                "unit": "K",
                "kind": "series",
                "reference_range": None,
            }
        ],
    }
    result = assembler.assemble(H1_REQUEST, kelvin_manifest)
    assert not uispec.is_refusal(result), result
    for component in result["components"]:
        assert component["bindings"]["unit"] == "K", result


def test_kelvin_spelling_is_recognised_as_a_unit_not_as_a_field(man):
    """'kelvin' is a unit, not an unknown field name."""
    result = assembler.assemble("chart zone1 air temperature in kelvin", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unit_mismatch"
    assert result["requested_unit"] == "K"


def test_the_canonical_kelvin_spelling_is_shared_with_the_catalog():
    assert catalog.normalize_unit("K") == "K"
    assert catalog.normalize_unit("k") == "K"
    assert catalog.normalize_unit("kelvin") == "K"
    assert catalog.is_detectable_unit("K")
    assert "k" in assembler.UNIT_WORDS
    assert "kelvin" in assembler.UNIT_WORDS


def test_the_assembler_has_no_private_unit_vocabulary():
    """One source of truth: the assembler borrows the catalog's list."""
    assert not hasattr(assembler, "DETECTABLE_UNITS")
    assert assembler.UNIT_WORDS == frozenset(catalog.unit_spellings())


def test_every_detectable_catalog_unit_is_known_to_the_assembler():
    """No catalog unit can be unknown to the assembler."""
    for unit in catalog.detectable_units():
        assert catalog.is_detectable_unit(unit), unit
        assert unit.lower() in assembler.UNIT_WORDS, unit
        assert unit in catalog.normalize_unit(unit)


def test_every_catalog_unit_spelling_is_detected_in_a_request():
    """Every canonical spelling and every alias names the unit it means."""
    for unit in catalog.detectable_units():
        detected, unknown = assembler._detect_unit(
            "chart zone1 air temperature in %s" % unit
        )
        assert (detected, unknown) == (unit, None), unit
        for alias, target in catalog.UNIT_ALIASES.items():
            if target != unit:
                continue
            detected, unknown = assembler._detect_unit(
                "chart zone1 air temperature in %s" % alias
            )
            assert (detected, unknown) == (unit, None), (unit, alias)


def test_a_unit_the_catalog_cannot_check_is_refused_not_guessed(man):
    """'BTU/h' is not a unit the lens can check: refuse, do not bind degC."""
    result = assembler.assemble("chart zone1 air temperature in BTU/h", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unknown_unit"


def test_the_field_own_unit_is_still_bound_when_no_unit_is_named(man):
    """The plain request keeps working: the field's own unit is bound."""
    result = assembler.assemble("chart zone1 air temperature", man)
    assert not uispec.is_refusal(result), result
    for component in result["components"]:
        assert component["bindings"]["unit"] == "°C"


def test_a_matching_unit_is_bound_and_checked(man):
    """A request naming the field's own unit still assembles."""
    result = assembler.assemble("chart zone1 air temperature in degC", man)
    assert not uispec.is_refusal(result), result
    for component in result["components"]:
        assert component["bindings"]["unit"] == "°C"


def test_a_wrong_but_known_unit_is_refused(man):
    """The pre-existing trap still refuses (kW against a degC field)."""
    result = assembler.assemble("show zone1 air temperature in kW", man)
    assert uispec.is_refusal(result)
    assert result["reason_code"] == "unit_mismatch"


def test_a_time_phrase_is_not_a_unit_mention():
    """'the last 3 hours' is a time window, not a request for hours."""
    detected, unknown = assembler._detect_unit(
        "chart zone1 air temperature over the last 3 hours"
    )
    assert (detected, unknown) == (None, None)


def test_a_manifest_field_name_part_is_not_a_unit_mention():
    """'zone1_heating_kw' is a field name, not a request for kilowatts."""
    entries = [{"name": "zone1_heating_kw"}]
    field_tokens = assembler._field_tokens(entries)
    detected, unknown = assembler._detect_unit(
        "chart zone1 heating kw", field_tokens
    )
    assert (detected, unknown) == (None, None)
    # ... but the same word introduced as a unit is checked
    detected, unknown = assembler._detect_unit(
        "chart zone1 heating in kw", field_tokens
    )
    assert (detected, unknown) == ("kW", None)

"""The adversarial set and the equivalence harness."""

import json

import pytest

import config as config_mod
import panel
import panel_catalog
import panel_spec
import schema

import adversarial_attempts
import handwritten_configs
import panel_requests


def _reject(attempt):
    if attempt["kind"] == "state":
        return list(
            schema.validate_state(attempt["submission"], require_all=False).errors
        )
    if attempt["kind"] == "axis":
        return list(schema.validate_sweep_axis(attempt["axis"]))
    return list(schema.validate_state(attempt["submission"], require_all=False).errors)


def test_the_adversarial_set_has_at_least_twenty_attempts():
    assert len(adversarial_attempts.ADVERSARIAL_ATTEMPTS) >= 20


def test_every_adversarial_attempt_is_rejected_with_a_readable_reason():
    failures = []
    for attempt in adversarial_attempts.ADVERSARIAL_ATTEMPTS:
        errors = _reject(attempt)
        if not errors:
            failures.append("%s: ACCEPTED" % attempt["id"])
            continue
        if errors[0]["code"] != attempt["expected"]:
            failures.append(
                "%s: expected %r, got %r (%s)"
                % (
                    attempt["id"],
                    attempt["expected"],
                    errors[0]["code"],
                    errors[0]["message"],
                )
            )
        if not errors[0]["message"]:
            failures.append("%s: empty reason" % attempt["id"])
    assert not failures, failures


def test_the_adversarial_set_covers_the_issue_examples():
    ids = {attempt["id"] for attempt in adversarial_attempts.ADVERSARIAL_ATTEMPTS}
    for expected in (
        "adv01_negative_cop",
        "adv03_sub_absolute_zero_celsius",
        "adv05_u_value_zero",
        "adv06_u_value_ten_x",
        "adv07_unscoped_parameter",
        "adv09_fahrenheit_value_as_celsius",
        "adv21_geometry_sweep_attempt",
        "adv22_structure_sweep_attempt",
    ):
        assert expected in ids


REQUESTS = {
    "sweep_heating_setpoint_c": (
        "sweep heating setpoint from 18 to 26 in 5 steps",
        {"heating_setpoint_c": {"value": 68.0, "unit": "°F"}},
    ),
    "sweep_cooling_setpoint_c": ("sweep cooling setpoint from 22 to 28 in 4 steps", {}),
    "sweep_infiltration_ach": ("sweep infiltration from 0.1 to 1.0 in 5 steps", {}),
    "sweep_window_u_value_w_m2k": (
        "sweep window u value from 1.0 to 3.0 in 3 steps",
        {},
    ),
    "sweep_cooling_cop": ("sweep cooling cop from 2.0 to 4.0 in 3 steps", {}),
}


def test_the_equivalence_harness_compares_at_least_five_sweeps():
    assert len(handwritten_configs.HANDWRITTEN_CONFIGS) >= 5


def test_panel_generated_and_hand_written_configurations_are_byte_for_byte_equal():
    for case_id, reference in handwritten_configs.HANDWRITTEN_CONFIGS:
        request, submission = REQUESTS[case_id]
        spec = panel.build_panel(request, case_id=case_id)
        assert not panel_catalog.is_refusal(spec)
        state = panel_spec.panel_state(spec)
        if submission:
            merged = dict(state)
            merged.update(submission)
            result = schema.validate_state(merged, require_all=False)
            assert result.ok, result.errors
            state = result.normalized
        else:
            result = schema.validate_state(state, require_all=False)
            assert result.ok, result.errors
            state = result.normalized
        generated = config_mod.build_config(spec, state)
        assert config_mod.canonical_bytes(generated) == config_mod.canonical_bytes(reference)


def test_the_configuration_carries_si_values_only():
    """The imperial sweep must land in the configuration as SI."""
    request, submission = REQUESTS["sweep_heating_setpoint_c"]
    spec = panel.build_panel(request, case_id="sweep_heating_setpoint_c")
    state = panel_spec.panel_state(spec)
    merged = dict(state)
    merged.update(submission)
    result = schema.validate_state(merged, require_all=False)
    assert result.ok
    config = config_mod.build_config(spec, result.normalized)
    assert config["inputs"]["heating_setpoint_c"] == 20.0
    assert "°F" not in json.dumps(config, ensure_ascii=False)

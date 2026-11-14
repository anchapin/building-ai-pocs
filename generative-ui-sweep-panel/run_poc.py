#!/usr/bin/env python3
"""The sweep-panel POC harness (issue #38).

Run with::

    python3 generative-ui-sweep-panel/run_poc.py

It prints, in order:

    [1] the frozen scoped parameter set,
    [2] the generated panels and their binding validity,
    [3] the imperial conversion (explicit, shown),
    [4] the run button while a field is invalid,
    [5] the adversarial set - every rejection, verbatim,
    [6] the equivalence harness - panel-generated vs hand-written config,
    [7] the effort split (strict layer vs assembler),
    [8] the headline table.

The harness never runs a solver: it produces panels, configurations and
refusals only.  Fluxion is not inside this worktree, so **no solver-run
equivalence is claimed anywhere** - the equivalence measured here is
configuration-level (byte-for-byte, both sides through the strict layer).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
FIXTURES = os.path.join(HERE, "fixtures")
if FIXTURES not in sys.path:
    sys.path.insert(0, FIXTURES)

import config as config_mod  # noqa: E402
import panel as panel_mod  # noqa: E402
import panel_catalog  # noqa: E402
import panel_renderer  # noqa: E402
import panel_spec  # noqa: E402
import schema  # noqa: E402

import adversarial_attempts  # noqa: E402
import handwritten_configs  # noqa: E402
import panel_requests  # noqa: E402


def rule(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def section_1_frozen_set() -> None:
    rule("[1] the frozen scoped parameter set (written first, never extended)")
    print(
        "%-34s %-8s %-12s %-14s %-10s %s"
        % ("parameter", "type", "unit", "range", "default", "primitive")
    )
    for spec in schema.FROZEN_SCOPED_PARAMETERS:
        if spec.type == schema.CHOICE:
            rng = "{" + ", ".join(spec.choices) + "}"
        else:
            rng = "%s - %s" % (spec.minimum, spec.maximum)
        print(
            "%-34s %-8s %-12s %-14s %-10s %s"
            % (
                spec.name,
                spec.type,
                spec.unit,
                rng,
                spec.default,
                spec.primitive,
            )
        )
    print()
    print("scoped parameters: %d" % len(schema.FROZEN_SCOPED_PARAMETERS))
    print(
        "evidence kinds: "
        + ", ".join(
            "%s=%d"
            % (kind, sum(1 for s in schema.FROZEN_SCOPED_PARAMETERS if s.evidence_kind == kind))
            for kind in ("in-repo", "physical-bound", "decision")
        )
    )
    print(
        "no Fluxion measure spec exists in this worktree (Fluxion is not in the "
        "tree); the ranges are the cited engineering bounds above."
    )


def section_2_panels() -> Tuple[List[Dict[str, Any]], int, int]:
    rule("[2] panel generation and panel binding validity")
    specs: List[Dict[str, Any]] = []
    valid = 0
    invalid = 0
    for entry in panel_requests.PANEL_REQUESTS:
        spec = panel_mod.build_panel(entry["request"])
        if panel_catalog.is_refusal(spec):
            print("%s  REFUSED  %s: %s" % (entry["id"], spec["reason_code"], spec["message"]))
            invalid += 1
            continue
        errors = panel_spec.validate_panel_spec(spec)
        state = panel_spec.panel_state(spec)
        result = schema.validate_state(state, require_all=False)
        axis = panel_spec.sweep_axis(spec)
        axis_errors = schema.validate_sweep_axis(axis) if axis else ["no axis"]
        button = panel_spec.run_button_enabled(spec)
        components = len(spec["components"])
        controls = sum(
            1
            for c in spec["components"]
            if c["primitive"] in ("ParamSlider", "ParamNumber", "ChoiceSelect")
        )
        if errors or result.errors or axis_errors:
            invalid += 1
            print("%s  INVALID  %s" % (entry["id"], errors or result.errors or axis_errors))
        else:
            valid += 1
        print(
            "%s  ok  axis=%-30s components=%2d (controls=%2d)  "
            "spec-errors=%d state-errors=%d axis-errors=%d run-enabled=%s"
            % (
                entry["id"],
                axis["parameter"],
                components,
                controls,
                len(errors),
                len(result.errors),
                len(axis_errors),
                button,
            )
        )
        specs.append(spec)
    print()
    print("panels generated: %d" % len(specs))
    print("panel binding validity: %d/%d (failures: none)" % (valid, valid + invalid))
    return specs, valid, invalid


def section_3_imperial() -> None:
    rule("[3] explicit imperial conversion (shown, never silent)")
    submission = {"heating_setpoint_c": {"value": 68.0, "unit": "°F"}}
    result = schema.validate_state(submission, require_all=False)
    print("submission: %s" % json.dumps(submission, sort_keys=True))
    print("accepted: %s" % result.ok)
    for conversion in result.conversions:
        print(
            "conversion: %s %s %s -> %s %s   [%s]"
            % (
                conversion["parameter"],
                conversion["submitted_value"],
                conversion["submitted_unit"],
                conversion["converted_value"],
                conversion["si_unit"],
                conversion["formula"],
            )
        )
    print(
        "normalised state: %s"
        % json.dumps(result.normalized, sort_keys=True, ensure_ascii=False)
    )
    print()
    print("the same value submitted as °C (68 °C) is refused:")
    wrong = schema.validate_state(
        {"heating_setpoint_c": {"value": 68.0, "unit": "°C"}}, require_all=False
    )
    for error in wrong.errors:
        print("  %s: %s" % (error["code"], error["message"]))


def section_4_run_button() -> None:
    rule("[4] the run button while a field is invalid")
    spec = panel_mod.build_panel("sweep heating setpoint from 18 to 26 in 5 steps")
    print("panel built, all fields valid -> run enabled: %s" % panel_spec.run_button_enabled(spec))
    broken = json.loads(json.dumps(spec))
    for component in broken["components"]:
        if component["primitive"] == "ParamSlider" and component["bindings"]["parameter"] == "cooling_setpoint_c":
            component["bindings"]["value"] = 15.0
    invalid = panel_spec.invalid_fields(broken)
    print("after setting cooling_setpoint_c = 15.0 °C:")
    print("  invalid fields: %s" % invalid)
    print("  run enabled: %s" % panel_spec.run_button_enabled(broken))
    html = panel_renderer.render_panel(broken)
    print("  rendered button line: %s" % [line for line in html.splitlines() if "<button" in line][0].strip())


def section_5_adversarial() -> Tuple[int, int]:
    rule("[5] the adversarial set - every rejection, verbatim")
    handled = 0
    total = 0
    failures: List[str] = []
    for attempt in adversarial_attempts.ADVERSARIAL_ATTEMPTS:
        total += 1
        if attempt["kind"] == "state":
            result = schema.validate_state(attempt["submission"], require_all=False)
            errors = list(result.errors)
        elif attempt["kind"] == "axis":
            errors = list(schema.validate_sweep_axis(attempt["axis"]))
        else:
            errors = list(
                schema.validate_state(attempt["submission"], require_all=False).errors
            )
        if errors:
            handled += 1
            code = errors[0]["code"]
            ok = code == attempt["expected"]
            if not ok:
                failures.append(
                    "%s: expected code %r, got %r" % (attempt["id"], attempt["expected"], code)
                )
            print(
                "%-38s %-22s %s"
                % (attempt["id"], attempt["description"][:22], "REJECTED" if ok else "REJECTED (code differs)")
            )
            for error in errors:
                print("      %s: %s" % (error["code"], error["message"]))
        else:
            failures.append("%s: ACCEPTED (no rejection)" % attempt["id"])
            print("%-38s %s" % (attempt["id"], "ACCEPTED  <-- FAILURE"))
    print()
    print("adversarial attempts: %d" % total)
    print("rejected at the schema layer: %d/%d" % (handled, total))
    if failures:
        print("FAILURES:")
        for failure in failures:
            print("  " + failure)
    else:
        print("failures: none")
    return handled, total


def section_6_equivalence() -> Tuple[int, int]:
    rule("[6] equivalence harness - panel-generated vs hand-written configuration")
    matched = 0
    total = 0
    requests = {
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
    for case_id, reference in handwritten_configs.HANDWRITTEN_CONFIGS:
        total += 1
        request, submission = requests[case_id]
        spec = panel_mod.build_panel(request, case_id=case_id)
        if panel_catalog.is_refusal(spec):
            print("%s  REFUSED  %s" % (case_id, spec["message"]))
            continue
        state = panel_spec.panel_state(spec)
        if submission:
            merged = dict(state)
            merged.update(submission)
            result = schema.validate_state(merged, require_all=False)
            if not result.ok:
                print("%s  submission refused: %s" % (case_id, result.reason))
                continue
            state = result.normalized
        else:
            result = schema.validate_state(state, require_all=False)
            if not result.ok:
                print("%s  panel state refused: %s" % (case_id, result.reason))
                continue
            state = result.normalized
        generated = config_mod.build_config(spec, state)
        generated_bytes = config_mod.canonical_bytes(generated)
        reference_bytes = config_mod.canonical_bytes(reference)
        same = generated_bytes == reference_bytes
        if same:
            matched += 1
        print("%s" % case_id)
        print(
            "  panel-generated sha256 %s"
            % hashlib.sha256(generated_bytes).hexdigest()
        )
        print(
            "  hand-written   sha256 %s"
            % hashlib.sha256(reference_bytes).hexdigest()
        )
        print("  byte-for-byte identical: %s (%d bytes)" % (same, len(generated_bytes)))
        if not same:
            print("  --- panel-generated ---")
            print(generated_bytes.decode("utf-8"))
            print("  --- hand-written ---")
            print(reference_bytes.decode("utf-8"))
    print()
    print("sweeps compared: %d" % total)
    print("byte-for-byte identical: %d/%d" % (matched, total))
    return matched, total


def section_7_effort() -> None:
    rule("[7] effort split: strict layer vs assembler")
    groups = {
        "strict schema layer (schema.py)": ["schema.py"],
        "strict spec layer (panel_spec.py)": ["panel_spec.py"],
        "catalog extension (panel_catalog.py)": ["panel_catalog.py"],
        "assembler / panel generation (panel.py)": ["panel.py"],
        "configuration writer (config.py)": ["config.py"],
        "renderer (panel_renderer.py)": ["panel_renderer.py"],
        "harness (run_poc.py)": ["run_poc.py"],
        "fixtures": ["fixtures/adversarial_attempts.py", "fixtures/handwritten_configs.py", "fixtures/panel_requests.py"],
    }
    for label, files in groups.items():
        total = 0
        for name in files:
            path = os.path.join(HERE, name)
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.read().splitlines()
            code = [line for line in lines if line.strip() and not line.strip().startswith("#")]
            total += len(code)
        print("%-42s %5d code lines" % (label, total))
    strict = 0
    assembler = 0
    for name in ("schema.py", "panel_spec.py", "panel_catalog.py"):
        with open(os.path.join(HERE, name), "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        strict += len([line for line in lines if line.strip() and not line.strip().startswith("#")])
    for name in ("panel.py", "config.py", "panel_renderer.py"):
        with open(os.path.join(HERE, name), "r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
        assembler += len([line for line in lines if line.strip() and not line.strip().startswith("#")])
    print()
    print("strict layer total (schema + spec + catalog): %d code lines" % strict)
    print("assembler total (panel + config + renderer):   %d code lines" % assembler)


def section_8_headline(
    panels_valid: int,
    panels_total: int,
    adv_handled: int,
    adv_total: int,
    eq_matched: int,
    eq_total: int,
) -> None:
    rule("[8] headline table")
    print("| metric | result |")
    print("|---|---|")
    print("| frozen scoped parameters | %d |" % len(schema.FROZEN_SCOPED_PARAMETERS))
    print("| panels generated | %d |" % panels_total)
    print(
        "| panel binding validity | %d/%d (failures: none) |"
        % (panels_valid, panels_total)
    )
    print("| adversarial attempts rejected | %d/%d |" % (adv_handled, adv_total))
    print("| configuration equivalence (byte-for-byte) | %d/%d |" % (eq_matched, eq_total))
    print(
        "| solver-run equivalence | NOT OBSERVED - Fluxion is not inside this worktree |"
    )
    print("| generated code executed | none (spec + configuration only) |")
    print("| protocol adopted | none (A2UI / AG-UI / MCP Apps not used) |")


def main() -> int:
    section_1_frozen_set()
    specs, valid, invalid = section_2_panels()
    section_3_imperial()
    section_4_run_button()
    adv_handled, adv_total = section_5_adversarial()
    eq_matched, eq_total = section_6_equivalence()
    section_7_effort()
    section_8_headline(valid, valid + invalid, adv_handled, adv_total, eq_matched, eq_total)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

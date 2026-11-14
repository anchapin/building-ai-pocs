"""Configuration generation: a validated panel state -> a Fluxion-style config.

The configuration is **data**: a JSON document describing the scoped
measures of one sweep.  Nothing here runs a solver, and the POC never
claims that a Fluxion run was executed (Fluxion is not inside this
worktree).

The configuration is written from the *normalised* state the strict layer
produced, so an imperial submission is converted once, explicitly, and the
configuration always carries SI values.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Mapping, Optional

import panel_catalog
import panel_spec
import schema

#: the configuration document version (this POC's own, not Fluxion's)
CONFIG_SCHEMA_VERSION = 1


def build_config(
    spec: Mapping[str, Any],
    state: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the configuration for a panel.

    ``state`` is a *validated* submission (as returned by
    ``schema.validate_state(...).normalized``).  When it is omitted the
    panel's own (default) state is used.
    """
    if state is None:
        result = schema.validate_state(panel_spec.panel_state(spec), require_all=False)
        if not result.ok:
            raise ValueError("the panel state is invalid: %s" % result.reason)
        state = result.normalized

    axis = panel_spec.sweep_axis(spec)
    if axis is None:
        raise ValueError("the panel carries no sweep axis")

    inputs: Dict[str, Any] = {}
    for param_spec in schema.FROZEN_SCOPED_PARAMETERS:
        entry = state.get(param_spec.name)
        if entry is None:
            raise ValueError("the state carries no value for %r" % param_spec.name)
        inputs[param_spec.name] = entry["value"]

    return {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "case_id": spec.get("case_id") or spec.get("run_id"),
        "sweep": {
            "parameter": axis["parameter"],
            "min": axis["min"],
            "max": axis["max"],
            "steps": axis["steps"],
            "unit": axis.get("unit") or schema.parameter(axis["parameter"]).unit,
        },
        "inputs": inputs,
    }


def canonical_bytes(config: Mapping[str, Any]) -> bytes:
    """The canonical byte form of a configuration (the comparison basis)."""
    return json.dumps(
        config, sort_keys=True, indent=2, ensure_ascii=False
    ).encode("utf-8")


def config_sha256(config: Mapping[str, Any]) -> str:
    """sha256 of the canonical bytes (a stable fingerprint)."""
    return hashlib.sha256(canonical_bytes(config)).hexdigest()


def write_config(config: Mapping[str, Any], path: str) -> str:
    """Write a configuration to ``path`` (canonical bytes); returns the path."""
    with open(path, "wb") as handle:
        handle.write(canonical_bytes(config))
    return path

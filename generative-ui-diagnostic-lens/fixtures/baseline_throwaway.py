#!/usr/bin/env python3
"""Throwaway baseline: the same view, produced by reading the fixture JSON.

This is the trivial comparison point for the timing table in ``run_poc.py``:
it hard-codes nothing about the request, it just opens the run-output JSON
and prints the named fields.  It is *not* validated, *not* reusable, and it
cannot refuse anything - it is what a person would write once, by hand, for
one question.

    python3 generative-ui-diagnostic-lens/fixtures/baseline_throwaway.py \\
        generative-ui-diagnostic-lens/fixtures/runs/run_ashrae140_case1.json \\
        zone1_air_temperature
"""

import json
import sys


def view(run_path, field_names):
    """Print-ready lines for the named fields of one run output."""
    with open(run_path, "r", encoding="utf-8") as handle:
        run = json.load(handle)
    fields = run.get("fields", {})
    lines = []
    for name in field_names:
        field = fields.get(name, {})
        values = field.get("values")
        value = values[-1] if values else field.get("value")
        lines.append("%s = %s %s" % (name, value, field.get("unit") or ""))
    return lines


if __name__ == "__main__":
    print("\n".join(view(sys.argv[1], sys.argv[2:])))

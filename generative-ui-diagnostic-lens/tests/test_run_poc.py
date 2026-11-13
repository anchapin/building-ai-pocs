"""End-to-end: the reproduce command runs and every binding is valid."""

import io
import json
import os
import sys
from contextlib import redirect_stdout

import pytest


HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import run_poc  # noqa: E402


@pytest.fixture(scope="module")
def headline():
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = run_poc.main()
    return code, buffer.getvalue()


def test_the_reproduce_command_succeeds(headline):
    code, output = headline
    assert code == 0, output
    assert "HEADLINE" in output


def test_the_headline_table_reports_the_three_numbers(headline):
    code, output = headline
    assert "binding validity" in output
    assert "adversarial handled" in output
    assert "catalog coverage" in output


def test_every_binding_of_every_generated_spec_is_valid(headline):
    code, output = headline
    assert "failures: none" in output
    assert "RESULT: every binding valid, every adversarial request handled" in output


def test_the_adversarial_set_is_reported_as_handled(headline):
    code, output = headline
    assert "| adversarial handled (refusal / no-data)  | 14/14 |" in output


def test_the_inexpressible_list_is_a_deliverable(headline):
    code, output = headline
    assert "inexpressible list (deliverable)" in output
    assert "out01_floor_plan_heatmap" in output

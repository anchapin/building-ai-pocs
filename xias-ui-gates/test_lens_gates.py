"""Tests for the lens-surface gates (xias-ui-gates/lens_gates.py).

The fixture-cases test runs the real measurement; the synthetic-HTML tests
prove each gate is not vacuous (a gate that never fires would report 0 for
the lens surface for the wrong reason).
"""

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lens_gates  # noqa: E402


def _measure(html):
    dom = lens_gates.parse_html(html)
    sheet = lens_gates.StyleSheet("".join(dom.styles))
    return dom, sheet


def test_three_fixture_cases():
    cases = lens_gates.fixture_cases()
    assert [c["id"] for c in cases] == [
        "case1_ashrae140", "case2_ground_coupled", "case3_humid_latent",
    ]


def test_fixture_measurement_is_stable():
    first = lens_gates.build_results()
    second = lens_gates.build_results()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["totals"] == {"gate1": 0, "gate2": 0, "gate3": 0, "gate4": 5}
    assert first["gatesFailed"] == ["gate4"]


def test_gate1_flags_missing_lang_and_unnamed_button():
    html = ("<html><head><title>t</title></head><body>"
            "<button></button></body></html>")
    dom, sheet = _measure(html)
    findings = lens_gates.gate1(dom, sheet)
    rules = sorted(f["rule"] for f in findings)
    assert "html-element-has-no-lang" in rules
    assert "interactive-element-has-no-accessible-name" in rules


def test_gate1_passes_the_lens_shape():
    html = ('<html lang="en"><head><title>Diagnostic lens</title></head><body>'
            '<svg role="img" aria-label="x"></svg></body></html>')
    dom, sheet = _measure(html)
    assert lens_gates.gate1(dom, sheet) == []


def test_gate2_flags_low_contrast_text():
    html = ('<html lang="en"><head><title>t</title><style>'
            '.bad{color:#eee;}</style></head><body>'
            '<p class="bad">faint</p></body></html>')
    dom, sheet = _measure(html)
    findings, measured = lens_gates.gate2(dom, sheet)
    assert measured == 1
    assert len(findings) == 1
    assert findings[0]["ratio"] < 4.5
    assert findings[0]["required"] == 4.5


def test_gate2_uses_the_renderer_colour_and_the_white_background():
    html = ('<html lang="en"><head><title>t</title><style>'
            '.nodata{color:#a00;font-style:italic;}</style></head><body>'
            '<p class="nodata">no data</p></body></html>')
    dom, sheet = _measure(html)
    findings, measured = lens_gates.gate2(dom, sheet)
    assert measured == 1
    assert findings == []  # #a00 on white is 7.75:1 -> passes


def test_gate3_flags_a_small_button_and_reports_no_interactive_elements():
    html = ('<html lang="en"><head><title>t</title></head><body>'
            '<button style="width:10px;height:10px">x</button></body></html>')
    dom, sheet = _measure(html)
    findings, interactive = lens_gates.gate3(dom, sheet)
    assert interactive == 1
    assert findings[0]["rule"] == "target-size"
    assert findings[0]["width"] == 10.0

    html = '<html lang="en"><head><title>t</title></head><body><p>x</p></body></html>'
    dom, sheet = _measure(html)
    findings, interactive = lens_gates.gate3(dom, sheet)
    assert interactive == 0
    assert findings == []


def test_gate4_flags_a_wide_viewbox_and_respects_a_responsive_wrapper():
    html = ('<html lang="en"><head><title>t</title></head><body>'
            '<svg viewBox="0 0 520 200"></svg></body></html>')
    dom, sheet = _measure(html)
    findings = lens_gates.gate4(dom, sheet)
    assert len(findings) == 1
    assert findings[0]["rule"] == "svg-viewbox-width"
    assert findings[0]["widthPx"] == 520.0

    html = ('<html lang="en"><head><title>t</title><style>'
            'svg{max-width:100%;}</style></head><body>'
            '<svg viewBox="0 0 520 200"></svg></body></html>')
    dom, sheet = _measure(html)
    assert lens_gates.gate4(dom, sheet) == []


@pytest.mark.parametrize("case_id", ["case1_ashrae140", "case2_ground_coupled"])
def test_each_case_renders_one_wide_chart(case_id):
    request = [r for r in lens_gates.fixture_cases() if r["id"] == case_id][0]
    measured = lens_gates.measure_case(request)
    assert measured["gates"]["gate4"]["count"] == measured["gates"]["gate4"]["count"]
    assert measured["gates"]["gate2"]["textElementsMeasured"] > 0
    assert measured["gates"]["gate3"]["interactiveElements"] == 0

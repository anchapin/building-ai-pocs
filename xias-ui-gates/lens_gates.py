#!/usr/bin/env python3
"""Gates 1-4 measured against the generative-ui-diagnostic-lens renderer.

This is the *lens surface* of the XIAS rendered-UI gates (POC #46).  The
staging-studio surface is measured by ``gates.spec.ts`` in a Playwright
harness; this script measures the same four gates against the static HTML
that ``generative-ui-diagnostic-lens/renderer.py`` produces for the lens'
three fixture cases, using the Python standard library only.

The four gates are adapted from ``gates.spec.ts`` to a surface that is
static HTML (no DOM, no layout, no browser engine available in this
slice):

  gate 1  accessibility (serious/critical): missing/empty accessible names
          on interactive elements, missing ``lang``, missing ``title``,
          duplicate ids, images/SVG without a text alternative.
  gate 2  rendered contrast: WCAG 2.2 contrast ratios computed from the
          colours the renderer's ``<style>`` block and its SVG
          ``fill``/``stroke`` attributes actually specify.
  gate 3  target size: interactive elements smaller than 24x24 CSS px.
  gate 4  horizontal overflow at 280 px: fixed pixel widths / min-widths
          and SVG viewBox widths above 280 px without a responsive wrapper.

Explicit assumptions (also stated in xias-ui-gates/REPORT.md):

  * The renderer's ``<style>`` block sets no page background and no body
    colour, so the UA defaults are assumed: page background ``#fff``
    (white) and body text ``#000`` (black).
  * Where no rule matches, the inherited/default value is used; every
    resolved colour is cited with the ``renderer.py`` line it came from
    (resolved by searching the renderer source for the declaration).

Usage:

    python3 xias-ui-gates/lens_gates.py

Writes ``xias-ui-gates/results/lens-gates-1-4.json`` (sorted keys, no
timestamps - the output is byte-identical across runs).
"""

from __future__ import annotations

import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
LENS_DIR = os.path.join(REPO_ROOT, "generative-ui-diagnostic-lens")
RENDERER_PATH = os.path.join(LENS_DIR, "renderer.py")

# The lens package uses flat imports (see generative-ui-diagnostic-lens/
# tests/conftest.py): the folder itself goes on sys.path.
if LENS_DIR not in sys.path:
    sys.path.insert(0, LENS_DIR)

import assembler  # noqa: E402  (import after the sys.path fix)
import manifest as manifest_mod  # noqa: E402
import renderer  # noqa: E402

CASE_REQUESTS = os.path.join(LENS_DIR, "fixtures", "case_requests.json")
RESULTS_PATH = os.path.join(HERE, "results", "lens-gates-1-4.json")

#: viewport the lens surface is checked against (the brief's 280 px).
OVERFLOW_VIEWPORT_PX = 280

#: WCAG 2.2 target size (2.5.8) minimum.
TARGET_MIN_PX = 24

#: UA defaults assumed for the parts the renderer's <style> block leaves
#: unspecified (see the module docstring).
PAGE_BACKGROUND = "#ffffff"
DEFAULT_TEXT_COLOR = "#000000"
DEFAULT_FONT_SIZE_PX = 16.0
DEFAULT_FONT_WEIGHT = 400

#: citations for the parts of the renderer that are not colour rules.
RENDERER_CITATIONS = {
    "chart viewBox": "generative-ui-diagnostic-lens/renderer.py:93",
    "zone viewBox": "generative-ui-diagnostic-lens/renderer.py:251",
    "chart svg element": "generative-ui-diagnostic-lens/renderer.py:93",
}

VOID_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

INTERACTIVE_TAGS = {"button", "input", "select", "textarea", "a", "summary"}
INTERACTIVE_ROLES = {
    "button", "link", "checkbox", "radio", "tab", "switch",
    "menuitem", "option", "textbox", "combobox",
}


# --------------------------------------------------------------------------
# citation helper: where in renderer.py does a declaration come from?
# --------------------------------------------------------------------------

_LINE_CACHE = {}


def renderer_lines():
    if "lines" not in _LINE_CACHE:
        with open(RENDERER_PATH, "r", encoding="utf-8") as handle:
            _LINE_CACHE["lines"] = handle.read().splitlines()
    return _LINE_CACHE["lines"]


def renderer_citation(selector, prop, value):
    """``generative-ui-diagnostic-lens/renderer.py:<line>`` for a declaration.

    The renderer emits its whole stylesheet as a handful of long string
    literals, one per line, so a declaration can be located by searching
    the renderer source for the selector and the declaration text.
    """
    if not selector or value is None:
        return None
    needle = "%s:%s" % (prop, value)
    for number, line in enumerate(renderer_lines(), start=1):
        compact = line.replace(" ", "")
        if ("%s{" % selector) in compact and needle.replace(" ", "") in compact:
            return "generative-ui-diagnostic-lens/renderer.py:%d" % number
    return None


# --------------------------------------------------------------------------
# a very small DOM (enough for these gates)
# --------------------------------------------------------------------------

class Element:
    """One element of the parsed document, in document order."""

    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []          # child Element objects
        self.text_parts = []         # own (direct) text
        self.index = -1              # document-order index of the start tag

    @property
    def classes(self):
        return (self.attrs.get("class") or "").split()

    def own_text(self):
        return "".join(self.text_parts).strip()

    def text_content(self):
        parts = list(self.text_parts)
        for child in self.children:
            parts.append(child.text_content())
        return "".join(parts).strip()

    def in_svg(self):
        node = self
        while node is not None:
            if node.tag == "svg":
                return True
            node = node.parent
        return False

    def describe(self):
        """Worst-example identifier: tag + classes + document-order index.

        The lens HTML carries no element ids, so elements are identified by
        tag + class + document-order index + a short text/attribute excerpt.
        """
        parts = [self.tag]
        if self.attrs.get("id"):
            parts.append("#" + self.attrs["id"])
        if self.classes:
            parts.append("." + ".".join(self.classes))
        parts.append("[doc#%d]" % self.index)
        ident = "".join(parts)
        excerpt = self.own_text()
        if excerpt:
            ident += ' "%s"' % excerpt[:40]
        for key in ("viewBox", "role", "aria-label"):
            if self.attrs.get(key):
                ident += " %s=%s" % (key, self.attrs[key])
        return ident


class DomParser(HTMLParser):
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.root = Element("#document", [], None)
        self.stack = [self.root]
        self.counter = 0
        self.styles = []

    def _new(self, tag, attrs):
        self.counter += 1
        element = Element(tag, attrs, self.stack[-1])
        element.index = self.counter
        self.stack[-1].children.append(element)
        return element

    def handle_starttag(self, tag, attrs):
        element = self._new(tag, attrs)
        if tag not in VOID_TAGS:
            self.stack.append(element)

    def handle_startendtag(self, tag, attrs):
        self._new(tag, attrs)

    def handle_endtag(self, tag):
        for position in range(len(self.stack) - 1, 0, -1):
            if self.stack[position].tag == tag:
                del self.stack[position:]
                return

    def handle_data(self, data):
        current = self.stack[-1]
        if current.tag == "style":
            self.styles.append(data)
            return
        current.text_parts.append(data)

    def elements(self):
        stack = list(self.root.children)
        while stack:
            element = stack.pop(0)
            yield element
            stack = list(element.children) + stack


def parse_html(html_text):
    parser = DomParser()
    parser.feed(html_text)
    parser.close()
    return parser


# --------------------------------------------------------------------------
# colour helpers (WCAG 2.2 relative luminance / contrast ratio)
# --------------------------------------------------------------------------

NAMED_COLOURS = {
    "black": "#000000", "white": "#ffffff", "red": "#ff0000",
    "green": "#008000", "blue": "#0000ff", "gray": "#808080",
    "grey": "#808080", "silver": "#c0c0c0", "navy": "#000080",
    "transparent": None,
}


def parse_color(value):
    """Return ``(r, g, b)`` for a CSS colour value, or ``None``."""
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text or text in ("none", "inherit", "initial", "unset"):
        return None
    if text in NAMED_COLOURS:
        return parse_color(NAMED_COLOURS[text])
    if text.startswith("#"):
        digits = text[1:]
        if len(digits) == 3:
            digits = "".join(ch * 2 for ch in digits)
        if len(digits) == 6:
            try:
                return (int(digits[0:2], 16), int(digits[2:4], 16), int(digits[4:6], 16))
            except ValueError:
                return None
        return None
    match = re.match(r"^rgba?\(([^)]*)\)$", text)
    if match:
        parts = [p.strip() for p in match.group(1).split(",")]
        try:
            return tuple(int(float(p)) for p in parts[:3])  # type: ignore[return-value]
        except ValueError:
            return None
    return None


def _channel(value):
    value = value / 255.0
    if value <= 0.03928:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb):
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg, bg):
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# --------------------------------------------------------------------------
# the renderer's <style> block
# --------------------------------------------------------------------------

RULE_RE = re.compile(r"([^{}]+)\{([^{}]*)\}", re.DOTALL)


class StyleSheet:
    """The handful of CSS rules the renderer emits (no cascade surprises).

    ``matching()`` maps a property name to ``(value, selector)`` so that
    every resolved colour can be cited with the renderer.py line that
    declares it.
    """

    def __init__(self, css_text):
        self.rules = []  # list of (selector, properties)
        text = re.sub(r"/\*.*?\*/", " ", css_text or "", flags=re.DOTALL)
        for selector_text, body in RULE_RE.findall(text):
            for selector in [s.strip() for s in selector_text.split(",") if s.strip()]:
                properties = {}
                for declaration in body.split(";"):
                    if ":" not in declaration:
                        continue
                    name, value = declaration.split(":", 1)
                    properties[name.strip().lower()] = value.strip()
                self.rules.append((selector, properties))

    def matching(self, element):
        """Properties of every rule whose selector matches ``element``."""
        merged = {}
        for selector, properties in self.rules:
            if self._matches(selector, element):
                for name, value in properties.items():
                    merged[name] = (value, selector)
        return merged

    @staticmethod
    def _matches(selector, element):
        if selector.startswith("."):
            return selector[1:] in element.classes
        if selector == "*":
            return True
        return selector == element.tag


def _inherited(element, sheet, prop):
    """First value of ``prop`` on the element or an ancestor (inheritance).

    Returns ``(value, selector)`` or ``(None, None)``.
    """
    node = element
    while node is not None and node.tag != "#document":
        found = sheet.matching(node).get(prop)
        if found is not None:
            return found
        node = node.parent
    return (None, None)


# --------------------------------------------------------------------------
# gate 1 - accessibility (serious/critical), static adaptation
# --------------------------------------------------------------------------

def is_interactive(element):
    if element.tag in INTERACTIVE_TAGS:
        if element.tag == "a" and not element.attrs.get("href"):
            return False
        if element.tag == "input" and (element.attrs.get("type") or "").lower() == "hidden":
            return False
        return True
    role = (element.attrs.get("role") or "").lower()
    if role in INTERACTIVE_ROLES:
        return True
    tabindex = element.attrs.get("tabindex")
    if tabindex is not None and tabindex != "-1":
        return True
    if element.attrs.get("onclick"):
        return True
    return False


def accessible_name(element):
    for key in ("aria-label", "title"):
        value = (element.attrs.get(key) or "").strip()
        if value:
            return value
    if element.tag == "img":
        value = (element.attrs.get("alt") or "").strip()
        if value:
            return value
    if element.attrs.get("aria-labelledby"):
        return element.attrs["aria-labelledby"]
    return element.text_content()


def gate1(dom, sheet):
    findings = []
    html_element = None
    titles = []
    seen_ids = {}
    for element in dom.elements():
        if element.tag == "html" and html_element is None:
            html_element = element
        if element.tag == "title":
            titles.append(element)

        if element.attrs.get("id"):
            seen_ids.setdefault(element.attrs["id"], []).append(element)

        if is_interactive(element):
            if not accessible_name(element):
                findings.append({
                    "rule": "interactive-element-has-no-accessible-name",
                    "element": element.describe(),
                    "measured": "accessible name is empty",
                })
        if element.tag == "img" and not (element.attrs.get("alt") or "").strip():
            findings.append({
                "rule": "image-has-no-text-alternative",
                "element": element.describe(),
                "measured": "no alt attribute",
            })
        if element.tag == "svg":
            labelled = bool((element.attrs.get("aria-label") or "").strip())
            labelled = labelled or bool((element.attrs.get("aria-labelledby") or "").strip())
            if not labelled and not any(c.tag == "title" for c in element.children):
                findings.append({
                    "rule": "svg-has-no-text-alternative",
                    "element": element.describe(),
                    "measured": "no aria-label and no <title> child",
                })

    if html_element is None:
        findings.append({
            "rule": "document-has-no-html-element",
            "element": "#document",
            "measured": "no <html> element parsed",
        })
    elif not (html_element.attrs.get("lang") or "").strip():
        findings.append({
            "rule": "html-element-has-no-lang",
            "element": html_element.describe(),
            "measured": "lang attribute is missing or empty",
        })

    if not titles or not titles[0].own_text():
        findings.append({
            "rule": "document-has-no-title",
            "element": "head > title",
            "measured": "no non-empty <title>",
        })

    for element_id, elements in sorted(seen_ids.items()):
        if len(elements) > 1:
            findings.append({
                "rule": "duplicate-id",
                "element": elements[1].describe(),
                "measured": "id %r used by %d element(s)" % (element_id, len(elements)),
            })
    return findings


# --------------------------------------------------------------------------
# gate 2 - rendered contrast
# --------------------------------------------------------------------------

def _font_size(element, sheet):
    size, _selector = _inherited(element, sheet, "font-size")
    if size:
        match = re.match(r"^([0-9.]+)px$", size.strip())
        if match:
            return float(match.group(1))
    if element.attrs.get("font-size"):
        try:
            return float(re.sub(r"[^\d.]", "", element.attrs["font-size"]))
        except ValueError:
            pass
    return DEFAULT_FONT_SIZE_PX


def _font_weight(element, sheet):
    weight, _selector = _inherited(element, sheet, "font-weight")
    if weight:
        match = re.search(r"(\d+)", weight)
        if match:
            return int(match.group(1))
    if element.attrs.get("font-weight"):
        try:
            return int(re.sub(r"[^\d]", "", element.attrs["font-weight"]))
        except ValueError:
            pass
    return DEFAULT_FONT_WEIGHT


def _foreground(element, sheet):
    """(rgb, source) of the text colour of ``element``."""
    if element.in_svg():
        properties = sheet.matching(element)
        found = properties.get("fill")
        if found is None and element.attrs.get("fill"):
            found = (element.attrs["fill"], "svg fill attribute")
        if found is None:
            found = _inherited(element, sheet, "fill")
        if found is None:
            # SVG's initial fill is black
            return parse_color(DEFAULT_TEXT_COLOR), (
                "SVG default fill (black); no fill rule in the renderer's <style> block")
        value, selector = found
        rgb = parse_color(value)
        if rgb is None:
            return None, None
        source = renderer_citation(selector, "fill", value) if selector else None
        return rgb, source or ("renderer's <style> rule %r" % selector)

    found = _inherited(element, sheet, "color")
    if found[0] is None:
        return parse_color(DEFAULT_TEXT_COLOR), (
            "UA default body text colour (black); the renderer's <style> block sets no colour")
    value, selector = found
    rgb = parse_color(value)
    if rgb is None:
        return None, None
    source = renderer_citation(selector, "color", value) if selector else None
    return rgb, source or ("renderer's <style> rule %r" % selector)


def _background(element, sheet):
    """(rgb, source) of the background behind ``element``'s text."""
    node = element
    while node is not None and node.tag != "#document":
        properties = sheet.matching(node)
        for key in ("background-color", "background"):
            found = properties.get(key)
            if found is None:
                continue
            value, selector = found
            rgb = parse_color(value)
            if rgb is None:
                continue
            source = renderer_citation(selector, "background", value) if selector else None
            return rgb, source or ("renderer's <style> rule %r" % selector)
        node = node.parent
    return parse_color(PAGE_BACKGROUND), (
        "UA default page background (white); the renderer's <style> block sets none")


def gate2(dom, sheet):
    findings = []
    measured = 0
    for element in dom.elements():
        if element.tag in ("style", "script", "head", "title"):
            continue
        text = element.own_text()
        if not text:
            continue
        fg, fg_source = _foreground(element, sheet)
        bg, bg_source = _background(element, sheet)
        if fg is None or bg is None:
            continue
        measured += 1
        ratio = contrast_ratio(fg, bg)
        size = _font_size(element, sheet)
        weight = _font_weight(element, sheet)
        large = size >= 24 or (size >= 18.66 and weight >= 700)
        required = 3.0 if large else 4.5
        if ratio + 0.005 < required:
            findings.append({
                "rule": "rendered-contrast",
                "element": element.describe(),
                "measured": "%.2f:1 (needs %.1f:1, %gpx/%d)" % (ratio, required, size, weight),
                "ratio": round(ratio, 2),
                "required": required,
                "fontSize": size,
                "fontWeight": weight,
                "foreground": "#%02x%02x%02x" % fg,
                "background": "#%02x%02x%02x" % bg,
                "foregroundSource": fg_source,
                "backgroundSource": bg_source,
            })
    return findings, measured


# --------------------------------------------------------------------------
# gate 3 - target size (WCAG 2.5.8, 24x24)
# --------------------------------------------------------------------------

def _px(value):
    if value is None:
        return None
    match = re.match(r"^\s*([0-9.]+)px\s*$", str(value))
    if match:
        return float(match.group(1))
    return None


def _inline_style(element):
    style = element.attrs.get("style") or ""
    parsed = {}
    for part in style.split(";"):
        if ":" in part:
            name, value = part.split(":", 1)
            parsed[name.strip().lower()] = value.strip()
    return parsed


def _viewbox_size(element):
    box = element.attrs.get("viewBox") or element.attrs.get("viewbox")
    if not box:
        return None
    parts = re.split(r"[ ,]+", box.strip())
    if len(parts) != 4:
        return None
    try:
        return float(parts[2]), float(parts[3])
    except ValueError:
        return None


def gate3(dom, sheet):
    findings = []
    interactive = [e for e in dom.elements() if is_interactive(e)]
    for element in interactive:
        style = _inline_style(element)
        width = _px(style.get("width"))
        height = _px(style.get("height"))
        source = "inline style width/height"
        if width is None or height is None:
            box = _viewbox_size(element)
            if box is not None:
                width, height = box
                source = "viewBox-derived size"
        if width is None or height is None:
            findings.append({
                "rule": "target-size-unmeasurable",
                "element": element.describe(),
                "measured": "no inline size and no viewBox: needs a layout engine (UNMEASURED)",
            })
            continue
        if width < TARGET_MIN_PX or height < TARGET_MIN_PX:
            findings.append({
                "rule": "target-size",
                "element": element.describe(),
                "measured": "%gx%g (needs %dx%d) [%s]" % (
                    width, height, TARGET_MIN_PX, TARGET_MIN_PX, source),
                "width": width,
                "height": height,
            })
    return findings, len(interactive)


# --------------------------------------------------------------------------
# gate 4 - horizontal overflow at 280 px
# --------------------------------------------------------------------------

def _has_responsive_wrapper(element, sheet):
    """True when the element (or an ancestor) can shrink below its width."""
    node = element
    while node is not None and node.tag != "#document":
        properties = sheet.matching(node)
        if (properties.get("max-width") or ("", ""))[0].replace(" ", "").endswith("100%"):
            return True
        if (properties.get("width") or ("", ""))[0].replace(" ", "").endswith("100%"):
            return True
        overflow = (properties.get("overflow-x") or properties.get("overflow") or ("", ""))[0]
        if overflow in ("auto", "scroll", "hidden"):
            return True
        style = _inline_style(node)
        if style.get("max-width", "").replace(" ", "").endswith("100%"):
            return True
        if style.get("overflow-x") in ("auto", "scroll", "hidden"):
            return True
        node = node.parent
    return False


def gate4(dom, sheet):
    findings = []
    for element in dom.elements():
        style = _inline_style(element)
        for prop in ("width", "min-width"):
            value = _px(style.get(prop))
            if value is not None and value > OVERFLOW_VIEWPORT_PX:
                findings.append({
                    "rule": "fixed-pixel-width",
                    "element": element.describe(),
                    "measured": "%s %gpx > %dpx viewport" % (prop, value, OVERFLOW_VIEWPORT_PX),
                    "widthPx": value,
                    "source": "inline style attribute of the rendered HTML",
                })
        properties = sheet.matching(element)
        for prop in ("width", "min-width"):
            found = properties.get(prop)
            if found is None:
                continue
            value, selector = found
            pixels = _px(value)
            if pixels is not None and pixels > OVERFLOW_VIEWPORT_PX:
                findings.append({
                    "rule": "fixed-pixel-width",
                    "element": element.describe(),
                    "measured": "%s %gpx > %dpx viewport" % (prop, pixels, OVERFLOW_VIEWPORT_PX),
                    "widthPx": pixels,
                    "source": renderer_citation(selector, prop, value) or "renderer.py <style> rule",
                })
        box = _viewbox_size(element)
        if box is not None and box[0] > OVERFLOW_VIEWPORT_PX:
            if _has_responsive_wrapper(element, sheet):
                continue
            citation = (RENDERER_CITATIONS["chart viewBox"] if element.classes
                        and "chart" in element.classes else
                        RENDERER_CITATIONS["zone viewBox"])
            findings.append({
                "rule": "svg-viewbox-width",
                "element": element.describe(),
                "measured": "viewBox width %gpx > %dpx viewport, no responsive wrapper"
                            % (box[0], OVERFLOW_VIEWPORT_PX),
                "widthPx": box[0],
                "source": citation,
            })
    return findings


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

def fixture_cases():
    """The three fixture cases the lens' own runner assembles.

    ``fixtures/case_requests.json`` holds the three diagnosis cases (whose
    request id equals their case id) plus four extra exercises against the
    first run; the three diagnosis cases are the fixture cases measured
    here.
    """
    with open(CASE_REQUESTS, "r", encoding="utf-8") as handle:
        requests = json.load(handle)["requests"]
    return [r for r in requests if r.get("id") == r.get("case_id")]


def _worst(findings, key):
    if not findings:
        return None
    return sorted(findings, key=key)[0]


def measure_case(request):
    run = manifest_mod.load_run(request["run_id"])
    manifest = manifest_mod.manifest_from_run(run)
    spec = assembler.assemble(request["request"], manifest)
    if spec.get("status") == "refused":
        raise RuntimeError("fixture case %s was refused: %s" % (request["id"], spec))
    html_text = renderer.render_spec(spec, run)
    dom = parse_html(html_text)
    sheet = StyleSheet("".join(dom.styles))

    gate1_findings = gate1(dom, sheet)
    gate2_findings, gate2_measured = gate2(dom, sheet)
    gate3_findings, interactive_count = gate3(dom, sheet)
    gate4_findings = gate4(dom, sheet)

    return {
        "caseId": request["id"],
        "runId": request["run_id"],
        "request": request["request"],
        "components": [c.get("primitive") for c in spec.get("components", [])],
        "htmlBytes": len(html_text.encode("utf-8")),
        "gates": {
            "gate1": {
                "status": "measured",
                "count": len(gate1_findings),
                "worst": _worst(gate1_findings, lambda f: f["rule"]),
                "findings": gate1_findings,
            },
            "gate2": {
                "status": "measured",
                "count": len(gate2_findings),
                "textElementsMeasured": gate2_measured,
                "worst": _worst(gate2_findings, lambda f: f["ratio"]),
                "findings": gate2_findings,
            },
            "gate3": {
                "status": "measured",
                "count": len(gate3_findings),
                "interactiveElements": interactive_count,
                "worst": _worst(gate3_findings, lambda f: f.get("width", 0) * f.get("height", 0)),
                "findings": gate3_findings,
                "note": ("the lens renderer emits no interactive elements (no a/button/input/"
                         "and no interactive role), so gate 3 has 0 findings and nothing to "
                         "measure" if interactive_count == 0 else ""),
            },
            "gate4": {
                "status": "measured",
                "count": len(gate4_findings),
                "worst": _worst(gate4_findings, lambda f: -f["widthPx"]),
                "findings": gate4_findings,
            },
        },
    }


def build_results():
    cases = [measure_case(request) for request in fixture_cases()]
    totals = {}
    for gate in ("gate1", "gate2", "gate3", "gate4"):
        totals[gate] = sum(case["gates"][gate]["count"] for case in cases)
    failed = sorted(gate for gate in ("gate1", "gate2", "gate3", "gate4") if totals[gate] > 0)
    return {
        "schema": "xias-lens-gates-1",
        "surface": "generative-ui-diagnostic-lens renderer (static HTML)",
        "source": "generative-ui-diagnostic-lens/renderer.py render_spec()",
        "cases": cases,
        "totals": totals,
        "gatesFailed": failed,
        "gatesFailedCount": len(failed),
        "assumptions": [
            "The renderer's <style> block sets no page background and no body colour: "
            "the UA defaults are assumed (page background #ffffff, body text #000000).",
            "Gate 2 resolves the foreground from the class rule in the renderer's <style> "
            "block or from the SVG fill attribute; every colour is cited with the "
            "renderer.py line that declares it.",
            "Gate 4 is the static adaptation of the staging gate (fixed pixel widths / "
            "min-widths / SVG viewBox widths above 280px without a responsive wrapper). "
            "The rendered scrollWidth of the lens HTML was NOT measured: no browser "
            "engine is available in this slice (UNMEASURED).",
            "Gate 3 sizes come from an inline width/height or a viewBox; elements that "
            "would need layout to be sized are reported as unmeasurable, not guessed.",
            "Gate 1 is a static adaptation of the axe serious/critical rule set: axe "
            "itself is not run on this surface (UNMEASURED).",
        ],
    }


def render_table(results):
    lines = []
    lines.append("| Case | G1 a11y | G2 contrast | G3 target | G4 overflow |")
    lines.append("|---|---|---|---|---|")
    for case in results["cases"]:
        gates = case["gates"]
        worst4 = gates["gate4"]["worst"]
        lines.append("| %s | %d | %d | %d | %d%s |" % (
            case["caseId"],
            gates["gate1"]["count"],
            gates["gate2"]["count"],
            gates["gate3"]["count"],
            gates["gate4"]["count"],
            (" (%gpx)" % worst4["widthPx"]) if worst4 else "",
        ))
    return "\n".join(lines)


def main():
    results = build_results()
    directory = os.path.dirname(RESULTS_PATH)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        json.dump(results, handle, sort_keys=True, indent=2)
        handle.write("\n")
    print("XIAS gates 1-4 - generative-ui-diagnostic-lens surface")
    print("results -> %s" % os.path.relpath(RESULTS_PATH, REPO_ROOT))
    print()
    print(render_table(results))
    print()
    for case in results["cases"]:
        print("case %s" % case["caseId"])
        for gate in ("gate1", "gate2", "gate3", "gate4"):
            worst = case["gates"][gate]["worst"]
            detail = worst["measured"] if worst else "no findings"
            print("  %-6s count=%d worst=%s" % (
                gate, case["gates"][gate]["count"], detail))
    print()
    print("gates failed: %s (%d of 4)" % (
        ", ".join(results["gatesFailed"]) or "none", results["gatesFailedCount"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

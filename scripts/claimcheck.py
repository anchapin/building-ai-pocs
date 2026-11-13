#!/usr/bin/env python3
"""claimcheck.py - advisory claims linter for this repository's POC artifacts.

This is a vendored, in-repo implementation of the claim-typing rules that this
repository documents in README.md's "Claim typing in proposals and reports"
section (README.md, "Claim typing in proposals and reports").  The plan-coder
tool (`claimcheck.py` from the plan-coder repo) remains the reference
implementation; this file is a scoped equivalent, written from this repo's own
specification, so that the README's lint command runs from a fresh clone of
this repository with nothing installed and no absolute home path.

Rules enforced (exactly the four that README.md enumerates):

  1. missing-claims       The artifact has no `## Claims` section.
  2. untagged-claim       A bullet inside a `## Claims` section carries none of
                          the four claim tags ([observed], [inference],
                          [unsupported], [decision]).
  3. observed-no-source   An `[observed]` bullet carries no source on the same
                          line.  A source is, per README.md: a command and its
                          output, a file:line, a ledger count with n, a run/PR
                          ID, or a URL - and it is normally introduced by the
                          explicit `source:` marker used by the template.
  4. unsupported-position An `[unsupported]` bullet sits in a verdict/ask
                          position: a verdict/decision/recommendation section,
                          an ask section, or a line that asks the operator for
                          something or states the verdict.

Notes on parsing (documented so the behaviour is not surprising):

  * Headings are read everywhere, including inside fenced code blocks, because
    README.md's copyable template - and therefore its `## Claims` section -
    lives inside a ```markdown fence.
  * Bullets inside fenced code blocks are not treated as claims: a fenced block
    is quoted material, not the artifact's own claim list.
  * "Verdict/ask position" is decided from the artifact's own structure:
    a bullet under a heading whose text names a verdict / decision /
    recommendation / conclusion / label / ask, a bullet whose text opens with
    "Ask", a bullet that opens by declaring a verdict label ("Verdict: ...",
    "Label: ...", "No-go - ..."), and the report's leading label bullet.

Exit status: 0 = clean, 1 = at least one violation was found, 2 = usage error.
Python standard library only.
"""

import argparse
import os
import re
import sys

TAGS = ("observed", "inference", "unsupported", "decision")

# A bullet: "- ", "* ", "+ " or "1. " / "1) ", with optional indentation.
BULLET_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])(\s+)(.*)$")
# A claim tag at the start of a bullet's text, optionally wrapped in emphasis.
TAG_RE = re.compile(r"^\s*(?:\*\*|__|\*|`)?\[(%s)\](?:\*\*|__|\*|`)?\s*(.*)$"
                    % "|".join(TAGS), re.IGNORECASE)
# Any tag anywhere in the bullet (used to count how many tags a bullet carries).
ANY_TAG_RE = re.compile(r"\[(%s)\]" % "|".join(TAGS), re.IGNORECASE)

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")

# --- what counts as a source (README.md: "with its source in the same line") --

EXPLICIT_SOURCE_RE = re.compile(r"\bsources?\s*:\s*\S", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
FILE_LINE_RE = re.compile(
    r"\b[\w./-]*\.(?:py|md|json|ya?ml|txt|csv|tsv|sh|js|ts|jsx|cfg|ini|toml|ipynb)"
    r":\d+")
LEDGER_COUNT_RE = re.compile(r"\bn\s*=\s*\d+", re.IGNORECASE)
RUN_ID_RE = re.compile(
    r"\b(?:run|pr|pull\s+request|issue|commit|sha)\s*(?:id\s*)?[#:]?\s*[0-9a-f]{4,}",
    re.IGNORECASE)

# --- what counts as a verdict / ask position ---------------------------------

VERDICT_HEADING_RE = re.compile(
    r"verdict|decision|recommendation|conclusion|label|^go\b|^no[- ]?go\b|"
    r"why (?:go|no[- ]?go|conditional)", re.IGNORECASE)
ASK_HEADING_RE = re.compile(r"\bask\b|for the operator|operator action", re.IGNORECASE)
ASK_LINE_RE = re.compile(r"^\s*(?:[-*+]\s+)?(?:\*\*|__|\*|`)?\s*ask\b", re.IGNORECASE)
VERDICT_DECL_RE = re.compile(
    r"^\s*(?:\*\*|__|\*|`)?\s*(?:verdict|label|go/no-go|outcome|decision)\s*[:=]",
    re.IGNORECASE)
VERDICT_LABEL_RE = re.compile(
    r"^\s*(?:\*\*|__|\*|`)?\s*(?:go \(software only\)|go|no-go|no go|conditional)\b",
    re.IGNORECASE)


def strip_emphasis(text):
    """Remove leading emphasis/backtick noise from a bullet's text."""
    return text.lstrip("*_` ")


def bullet_text(line):
    """Return the text of a bullet line, or None if the line is not a bullet."""
    m = BULLET_RE.match(line)
    if not m:
        return None
    return m.group(4).strip()


def has_source(line):
    """True if the line carries a source, per README.md's definition."""
    return bool(
        EXPLICIT_SOURCE_RE.search(line)
        or URL_RE.search(line)
        or FILE_LINE_RE.search(line)
        or LEDGER_COUNT_RE.search(line)
        or RUN_ID_RE.search(line)
    )


def fenced_flags(lines):
    """Return a list of booleans: True where the line is inside a code fence."""
    inside = False
    flags = []
    for line in lines:
        m = FENCE_RE.match(line)
        if m:
            flags.append(False)  # the fence marker line itself is not content
            inside = not inside
            continue
        flags.append(inside)
    return flags


def headings(lines):
    """Return [(index, level, text)] for every heading line, fences included."""
    out = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            out.append((i, len(m.group(1)), m.group(2).strip()))
    return out


def section_of(head_list, index):
    """Return (level, text) of the section that line `index` belongs to."""
    current = (0, "")
    for i, level, text in head_list:
        if i > index:
            break
        current = (level, text)
    return current


def is_claims_heading(text):
    return text.strip().strip("*_` ").lower() == "claims"


def verdict_or_ask_section(text):
    return bool(VERDICT_HEADING_RE.search(text) or ASK_HEADING_RE.search(text))


def check_file(path):
    """Return a list of (line_no, rule, message) violations for one artifact."""
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    head_list = headings(lines)
    in_fence = fenced_flags(lines)

    violations = []

    # Rule 1: a missing `## Claims` section.
    claims_headings = [(i, lvl, text) for i, lvl, text in head_list
                       if is_claims_heading(text)]
    if not claims_headings:
        violations.append((0, "missing-claims",
                           "no '## Claims' section found in the artifact"))
        return violations

    # Rule 4: an `[unsupported]` bullet in a verdict/ask position.
    for i, line in enumerate(lines):
        if in_fence[i]:
            continue
        text = bullet_text(line)
        if text is None:
            continue
        m = TAG_RE.match(text)
        if not m or m.group(1).lower() != "unsupported":
            continue
        rest = m.group(2).strip()
        _, heading_text = section_of(head_list, i)
        reasons = []
        if heading_text and verdict_or_ask_section(heading_text):
            reasons.append("it sits under the section %r" % heading_text)
        if ASK_LINE_RE.match(text) or re.match(r"^\s*ask\b", rest, re.IGNORECASE):
            reasons.append("it is an ask line")
        if VERDICT_DECL_RE.match(rest) or VERDICT_LABEL_RE.match(rest):
            reasons.append("it states the verdict")
        if reasons:
            violations.append((i + 1, "unsupported-position",
                               "[unsupported] bullet in a verdict/ask position: "
                               + "; ".join(reasons)))

    # Rules 2 and 3: bullets inside a `## Claims` section.
    for start, level, _text in claims_headings:
        end = len(lines)
        for i, lvl, _t in head_list:
            if i > start and lvl <= level:
                end = i
                break
        for i in range(start + 1, end):
            if in_fence[i]:
                continue  # quoted material is not the artifact's claim list
            text = bullet_text(lines[i])
            if text is None:
                continue
            m = TAG_RE.match(text)
            if not m:
                violations.append((i + 1, "untagged-claim",
                                   "untagged bullet in the '## Claims' section: %r"
                                   % _short(text)))
                continue
            tag = m.group(1).lower()
            if tag == "observed" and not has_source(lines[i]):
                violations.append((i + 1, "observed-no-source",
                                   "[observed] bullet without a source on the "
                                   "same line: %r" % _short(text)))

    violations.sort(key=lambda v: (v[0], v[1]))
    return violations


def _short(text, limit=80):
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit - 3] + "..."
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="claimcheck.py",
        description="Advisory claim-typing linter for this repo's artifacts.")
    parser.add_argument("command", choices=["lint"],
                        help="the only command is 'lint'")
    parser.add_argument("files", nargs="+",
                        help="artifact markdown files to lint")
    args = parser.parse_args(argv)

    total = 0
    for path in args.files:
        if not os.path.isfile(path):
            sys.stderr.write("claimcheck.py: %s: no such file\n" % path)
            return 2
        try:
            violations = check_file(path)
        except OSError as exc:
            sys.stderr.write("claimcheck.py: %s: %s\n" % (path, exc))
            return 2
        for line_no, rule, message in violations:
            where = "%s:%d" % (path, line_no) if line_no else path
            print("%s: [%s] %s" % (where, rule, message))
        total += len(violations)

    if total:
        print("claimcheck.py: %d violation(s) found in %d file(s)"
              % (total, len(args.files)))
        return 1
    print("claimcheck.py: clean - %d file(s), 0 violations" % len(args.files))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""lint_claims.py - run the repo's claims linter over every artifact, in one command.

This is a thin runner around the existing in-repo checker (`scripts/claimcheck.py`).
It does NOT reimplement the lint rules: it discovers the artifact files
(README.md plus every POC's REPORT.md, by glob, so the next POC is picked up
automatically) and delegates every check to `claimcheck.check_file`.

Usage:
    python3 scripts/lint_claims.py                # README.md + every POC REPORT.md
    python3 scripts/lint_claims.py PATH [PATH...] # lint the given files/dirs only

Each PATH may be a markdown file (linted as-is) or a directory (in which case
the directory's README.md and every REPORT.md below it are linted).

Output: one line per artifact - "OK   <path>" or "FAIL <path> (N violation(s))" -
followed by the violations themselves, then a summary line.

Exit status: 0 = every artifact is clean, 1 = at least one artifact has a
violation, 2 = usage error (no artifacts found / unreadable file).

Advisory by design: this linter never blocks a merge; the GitHub Actions
workflow that runs it is configured with `continue-on-error: true`.

Python standard library only.
"""

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import claimcheck  # noqa: E402  (import after sys.path fix)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT_NAME = "REPORT.md"
README_NAME = "README.md"


def artifacts_in_dir(directory):
    """Return the artifact markdown files under `directory`, sorted."""
    found = []
    readme = os.path.join(directory, README_NAME)
    if os.path.isfile(readme):
        found.append(readme)
    pattern = os.path.join(directory, "**", REPORT_NAME)
    for path in sorted(glob.glob(pattern, recursive=True)):
        if os.path.isfile(path) and not _in_git_dir(path):
            found.append(path)
    return found


def _in_git_dir(path):
    parts = os.path.abspath(path).split(os.sep)
    return ".git" in parts


def discover(paths):
    """Expand the CLI arguments into a sorted list of artifact files."""
    if not paths:
        return artifacts_in_dir(REPO_ROOT)

    files = []
    for path in paths:
        if os.path.isdir(path):
            files.extend(artifacts_in_dir(path))
        elif os.path.isfile(path):
            files.append(path)
        else:
            sys.stderr.write("lint_claims.py: %s: no such file or directory\n"
                             % path)
            return None
    # de-duplicate, keep a stable order
    seen = set()
    unique = []
    for path in files:
        key = os.path.normpath(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return sorted(unique)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="lint_claims.py",
        description="Lint README.md and every POC REPORT.md with the "
                    "in-repo claims checker (advisory; blocks nothing).")
    parser.add_argument("paths", nargs="*",
                        help="optional files/directories to lint "
                             "(default: this repository's artifacts)")
    args = parser.parse_args(argv)

    files = discover(args.paths)
    if files is None:
        return 2
    if not files:
        sys.stderr.write("lint_claims.py: no artifacts found to lint\n")
        return 2

    failures = 0
    for path in files:
        try:
            violations = claimcheck.check_file(path)
        except OSError as exc:
            sys.stderr.write("lint_claims.py: %s: %s\n" % (path, exc))
            return 2
        if violations:
            failures += 1
            print("FAIL %s (%d violation(s))" % (path, len(violations)))
            for line_no, rule, message in violations:
                where = "%s:%d" % (path, line_no) if line_no else path
                print("     %s: [%s] %s" % (where, rule, message))
        else:
            print("OK   %s" % path)

    print("lint_claims.py: %d file(s) checked, %d clean, %d with violations"
          % (len(files), len(files) - failures, failures))
    if failures:
        return 1
    print("lint_claims.py: clean - %d file(s), 0 violations" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env bash
# Run `crosshair check` over every function of the slice.
#
# Budget (as stated in the issue): 10 minutes per function, hard cap ~30
# minutes of wall time for the whole crosshair phase.  The script enforces
# both: `timeout 600` per function and a total budget check before each
# function.
#
# Requirements: network access to PyPI (to install crosshair + z3) and, for
# the contract decorators to be the real `deal`/`icontract` ones, one of
# those two packages as well.  In the sandbox this POC was built in, PyPI
# was unreachable (see REPORT.md, "Environment"), so this script has never
# completed a full pass there.
#
# Usage:
#     bash smt-contract-checking/tools/run_crosshair.sh
#     VENV=/tmp/smtcc-venv bash smt-contract-checking/tools/run_crosshair.sh

set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
POC_DIR="$(dirname "$HERE")"
VENV="${VENV:-$POC_DIR/.venv}"

PER_FUNCTION_TIMEOUT="${PER_FUNCTION_TIMEOUT:-600}"   # 10 minutes
TOTAL_BUDGET="${TOTAL_BUDGET:-1800}"                 # 30 minutes

FUNCTIONS=(
  dist
  polygon_area
  glazed_area
  opening_span
  overlap_flag
  overlap_length
  true_overlap
  wwr
)

if [ ! -x "$VENV/bin/python" ]; then
  echo "[setup] creating venv at $VENV"
  python3 -m venv "$VENV"
fi

echo "[setup] installing crosshair, z3 and the contract libraries"
"$VENV/bin/pip" install --upgrade pip || exit 1
"$VENV/bin/pip" install crosshair z3-solver deal icontract || exit 1

START=$(date +%s)
for fn in "${FUNCTIONS[@]}"; do
  NOW=$(date +%s)
  ELAPSED=$(( NOW - START ))
  if [ "$ELAPSED" -ge "$TOTAL_BUDGET" ]; then
    echo "[budget] total budget of ${TOTAL_BUDGET}s exhausted after $ELAPSED s; stopping"
    break
  fi
  echo "[run] crosshair check geometry_slice.py:$fn  (timeout ${PER_FUNCTION_TIMEOUT}s)"
  START_FN=$(date +%s)
  PYTHONPATH="$POC_DIR" timeout "$PER_FUNCTION_TIMEOUT" \
    "$VENV/bin/crosshair" check "$POC_DIR/geometry_slice.py:$fn" \
    --per_condition_timeout=60
  STATUS=$?
  echo "[run] $fn finished with status $STATUS in $(( $(date +%s) - START_FN ))s"
done

echo "[done] total wall time: $(( $(date +%s) - START ))s"

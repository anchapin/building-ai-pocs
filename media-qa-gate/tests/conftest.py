import os
import sys

# media-qa-gate/ is not a valid Python package name (hyphen), so the checker
# is loaded by path rather than imported as a package.
HERE = os.path.dirname(os.path.abspath(__file__))
GATE_DIR = os.path.dirname(HERE)
if GATE_DIR not in sys.path:
    sys.path.insert(0, GATE_DIR)

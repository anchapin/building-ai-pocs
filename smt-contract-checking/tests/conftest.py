"""Make the smt-contract-checking slice importable from the tests."""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
POC_DIR = os.path.dirname(HERE)
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)

"""Pytest configuration: make the diagnostic-lens modules importable.

The POC folder is flat (catalog.py, manifest.py, uispec.py, renderer.py,
assembler.py live next to each other), so the folder itself goes on the
path - the same convention the other POCs in this repo use for their
``src/`` directory.
"""

import os
import sys

POC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if POC_DIR not in sys.path:
    sys.path.insert(0, POC_DIR)

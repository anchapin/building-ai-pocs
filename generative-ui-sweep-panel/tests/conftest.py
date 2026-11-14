"""Pytest configuration: make the sweep-panel modules importable.

The POC folder is flat (``schema.py``, ``panel.py``, ``panel_catalog.py``,
``panel_spec.py``, ``config.py``, ``panel_renderer.py``), so the folder
itself goes on the path - the same convention the Phase 1 POC uses for its
own folder.  The fixtures folder goes on the path too, so the adversarial
set and the hand-written configurations can be imported by name.
"""

import os
import sys

POC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES_DIR = os.path.join(POC_DIR, "fixtures")
for path in (POC_DIR, FIXTURES_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

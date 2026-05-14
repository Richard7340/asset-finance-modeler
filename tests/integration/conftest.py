"""
Integration test fixtures.

Sets PYTHONPATH so that subprocesses spawned by integration tests can import
the package even when the editable-install .pth file is hidden by macOS
(macOS marks files inside .venv/ as hidden, which Python's site.py skips).
"""
import os
from pathlib import Path

_SRC = str(Path(__file__).parent.parent.parent / "src")

# Prepend src/ to PYTHONPATH so subprocess.run(...) inherits it
existing = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = _SRC if not existing else f"{_SRC}:{existing}"

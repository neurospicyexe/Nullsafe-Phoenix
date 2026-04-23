# Re-export Config from the flat config module so that
# `from services.brain.config import Config` works whether the caller
# sees the package (this directory) or the sibling config.py file.
#
# Python resolves the package (directory with __init__.py) before the
# same-named .py file, so callers that do:
#   from services.brain.config import Config
# land here. We forward the import from the actual module.
import importlib
import os
import sys

# Load the sibling config.py (the flat file, not this package) directly.
_spec = importlib.util.spec_from_file_location(
    "services.brain._config_flat",
    os.path.join(os.path.dirname(__file__), "..", "config.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

Config = _mod.Config

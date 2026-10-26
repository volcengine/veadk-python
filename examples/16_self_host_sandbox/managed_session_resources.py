"""Compatibility import for veadk.integrations.mpa.session_resources."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("veadk.integrations.mpa.session_resources")

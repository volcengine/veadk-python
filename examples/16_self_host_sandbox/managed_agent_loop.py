"""Compatibility import for veadk.runtime.managed_agents.loop."""

import sys
from importlib import import_module

sys.modules[__name__] = import_module("veadk.runtime.managed_agents.loop")

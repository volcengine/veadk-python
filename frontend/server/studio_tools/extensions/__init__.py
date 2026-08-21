# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""First-party Studio Tool extensions discovered by the Studio BFF."""

from __future__ import annotations

from importlib import import_module
from pkgutil import iter_modules

from frontend.server.studio_tools.registry import StudioToolRegistry


def register_studio_tool_extensions(registry: StudioToolRegistry) -> None:
    """Register every public extension module in deterministic name order."""

    module_names = sorted(
        module.name
        for module in iter_modules(__path__)
        if not module.ispkg and not module.name.startswith("_")
    )
    for module_name in module_names:
        module = import_module(f"{__name__}.{module_name}")
        register_tools = getattr(module, "register_tools", None)
        if not callable(register_tools):
            raise RuntimeError(
                f"Studio Tool extension {module.__name__} must export "
                "register_tools(registry)"
            )
        register_tools(registry)


__all__ = ["register_studio_tool_extensions"]

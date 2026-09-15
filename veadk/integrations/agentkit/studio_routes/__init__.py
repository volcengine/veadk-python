# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Runtime host for Studio BFF-owned dynamic HTTP routes."""

from __future__ import annotations

import importlib
from typing import Any


_EXPORT_MODULES = {
    "StudioDynamicRouteMiddleware": "host",
    "StudioRouteHost": "host",
    "mount_studio_route_host": "host",
    "ROUTE_PROTOCOL_VERSION": "protocol",
    "RouteCatalogSnapshot": "protocol",
    "StudioRouteManifest": "protocol",
    "match_route_path": "protocol",
    "route_catalog_revision": "protocol",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "ROUTE_PROTOCOL_VERSION",
    "RouteCatalogSnapshot",
    "StudioDynamicRouteMiddleware",
    "StudioRouteHost",
    "StudioRouteManifest",
    "match_route_path",
    "mount_studio_route_host",
    "route_catalog_revision",
]

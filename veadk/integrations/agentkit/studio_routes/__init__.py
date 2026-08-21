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

from veadk.integrations.agentkit.studio_routes.host import (
    StudioDynamicRouteMiddleware,
    StudioRouteHost,
    mount_studio_route_host,
)
from veadk.integrations.agentkit.studio_routes.protocol import (
    ROUTE_PROTOCOL_VERSION,
    RouteCatalogSnapshot,
    StudioRouteManifest,
    match_route_path,
    route_catalog_revision,
)

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

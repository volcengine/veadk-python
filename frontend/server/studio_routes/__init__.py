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

"""Studio BFF-owned dynamic HTTP routes and persistent Runtime connector."""

from frontend.server.studio_routes.connector import (
    StudioRouteChannelError,
    StudioRouteChannelManager,
    runtime_supports_bff_routes,
    serve_studio_route_channel,
)
from frontend.server.studio_routes.registry import (
    StudioRoute,
    StudioRouteRegistry,
    StudioRouteResponse,
    build_studio_route_registry,
)

__all__ = [
    "StudioRoute",
    "StudioRouteChannelError",
    "StudioRouteChannelManager",
    "StudioRouteRegistry",
    "StudioRouteResponse",
    "build_studio_route_registry",
    "runtime_supports_bff_routes",
    "serve_studio_route_channel",
]

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

"""Compatibility exports for Studio's frontend-owned access policy."""

from frontend.server.user_management.policy import (
    StudioAccessPolicy,
    StudioPrincipal,
    StudioRole,
    parse_role_members,
    runtime_attribution,
    runtime_belongs_to,
)

__all__ = [
    "StudioAccessPolicy",
    "StudioPrincipal",
    "StudioRole",
    "parse_role_members",
    "runtime_attribution",
    "runtime_belongs_to",
]

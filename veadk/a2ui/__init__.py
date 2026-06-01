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

"""A2UI (agent-driven UI) integration for VeADK.

Enable it on an agent with ``Agent(enable_a2ui=True)``. Enterprises register
their own components by subclassing :class:`BaseA2UICatalog` (backend) plus a
matching ``frontend/src/a2ui/components/<Name>/`` renderer (frontend).
"""

from veadk.a2ui.catalog import (
    DEFAULT_A2UI_VERSION,
    BaseA2UICatalog,
    get_basic_catalog,
)
from veadk.a2ui.toolset import build_a2ui_toolset

__all__ = [
    "BaseA2UICatalog",
    "get_basic_catalog",
    "build_a2ui_toolset",
    "DEFAULT_A2UI_VERSION",
]

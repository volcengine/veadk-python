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

"""Agent Harness plugin bridge for veADK users."""

from __future__ import annotations

from collections.abc import Iterable

from google.adk.plugins import BasePlugin


def build_harness_plugins(
    *,
    components: Iterable[str] | str | None = None,
    profile: str = "default",
) -> list[BasePlugin]:
    """Build Harness plugins from the bundled veADK extension."""

    from veadk.extensions.harness.adk import build_harness_plugins as _build

    return _build(components=components, profile=profile)


__all__ = ["build_harness_plugins"]

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

from typing import TYPE_CHECKING

from veadk.version import VERSION

if TYPE_CHECKING:
    from veadk.agent import Agent
    from veadk.runner import Runner


# Lazy loading for `Agent` class
def __getattr__(name):
    if name == "Agent":
        from veadk.agent import Agent

        return Agent
    if name == "Runner":
        from veadk.runner import Runner

        return Runner
    raise AttributeError(f"module 'veadk' has no attribute '{name}'")


__all__ = ["Agent", "Runner", "VERSION"]

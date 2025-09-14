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

if TYPE_CHECKING:
    from veadk.memory.long_term_memory import LongTermMemory
    from veadk.memory.short_term_memory import ShortTermMemory


# Lazy loading for classes
def __getattr__(name):
    if name == "ShortTermMemory":
        from veadk.memory.short_term_memory import ShortTermMemory

        return ShortTermMemory
    if name == "LongTeremMemory":
        from veadk.memory.long_term_memory import LongTermMemory

        return LongTermMemory
    raise AttributeError(f"module 'veadk.memory' has no attribute '{name}'")


__all__ = ["ShortTermMemory", "LongTermMemory"]

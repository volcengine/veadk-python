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

from abc import ABC, abstractmethod

from pydantic import BaseModel


class BaseLongTermMemoryBackend(ABC, BaseModel):
    index: str

    @abstractmethod
    def save_memory(self, event_strings: list[str], **kwargs) -> bool:
        """Save memory to long term memory backend"""

    @abstractmethod
    def search_memory(self, query: str, **kwargs) -> list[str]:
        """Retrieve memory from long term memory backend"""

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

from pydantic import BaseModel


class MemoryProfile(BaseModel):
    name: str
    describe: str
    event_ids: list[str]


class MemoryProfileList(BaseModel):
    profiles: list[MemoryProfile]  # 核心：list[MemoryProfile]类型字段


class MemoryProfileV2(BaseModel):
    name: str
    tags: list[str]
    event_ids: list[str]


class MemoryProfileListV2(BaseModel):
    profiles: list[MemoryProfileV2]  # 核心：list[MemoryProfile]类型字段

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

from pydantic import BaseModel, Field


class KnowledgebaseProfile(BaseModel):
    name: str = Field(description="The name of the knowledgebase.")

    description: str = Field(description="The description of the knowledgebase.")

    tags: list[str] = Field(
        description="Some tags of the knowledgebase. It represents the category of the knowledgebase. About 3-5 tags should be provided."
    )

    keywords: list[str] = Field(
        description="Recommanded query keywords of the knowledgebase. About 3-5 keywords should be provided."
    )

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

from veadk.agent import Agent
from veadk.memory.short_term_memory import ShortTermMemory


class MediaMessage(BaseModel):
    text: str
    """Text-based prompt"""

    media: str
    """Media file (e.g., `.pdf`, `.docx`, `.png`, `.jpg`, `.jpeg`, `.mp4`, `.mp3`, `.wav`, `.txt`) path"""


class AgentRunConfig(BaseModel):
    """Configuration for running an agent on VeFaaS platform."""

    model_config = {"arbitrary_types_allowed": True}

    app_name: str = Field(
        default="veadk_vefaas_app", description="The name of the application"
    )

    agent: Agent = Field(..., description="The root agent instance")

    short_term_memory: ShortTermMemory = Field(
        default_factory=ShortTermMemory, description="The short-term memory instance"
    )

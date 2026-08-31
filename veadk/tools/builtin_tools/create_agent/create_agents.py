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

"""Google ADK tool wrapper with a runtime-dependent Pydantic schema."""

from __future__ import annotations

from google.adk.tools import FunctionTool
from google.genai import types
from pydantic import BaseModel
from typing_extensions import override


class CreateAgentsTool(FunctionTool):
    """FunctionTool whose visible input excludes unsupported workflow nodes."""

    def __init__(self, function, *, input_model: type[BaseModel]) -> None:
        self._input_model = input_model
        super().__init__(function)

    @override
    def _get_declaration(self) -> types.FunctionDeclaration | None:
        return types.FunctionDeclaration(
            name=self.name,
            description=(
                "Create one or more sub-agents and transfer the current task to "
                "the agent named by handoff_to. Normally call collect_resources "
                "first, use its collection_id, and select only resource refs "
                "returned by that call. If the user explicitly prohibits network, "
                "knowledge-base, and external-resource access, skip collection, "
                "pass an empty collection_id, and leave every node's resources "
                "empty. Collected resources are candidates only "
                "and are not mounted automatically. For every LLM node, explicitly "
                "include each relevant Skill, knowledge base, and built-in tool in "
                "resources; when relevant Skills were returned, bind at least one. "
                "Call create_agents exactly once for each collect_resources result "
                "and include every required sub-agent in that single agents list. "
                "Once it completes or sets handoff_to, never call it again. "
                "The selected sub-agent, not the main agent, produces the final "
                "answer."
            ),
            parameters_json_schema=self._input_model.model_json_schema(by_alias=True),
        )

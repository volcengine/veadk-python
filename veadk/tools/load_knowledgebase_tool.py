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

from __future__ import annotations

from typing import TYPE_CHECKING

import wrapt
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.knowledgebase import KnowledgeBase
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from google.adk.models.llm_request import LlmRequest


knowledgebase: KnowledgeBase | None = None


class LoadKnowledgebaseResponse(BaseModel):
    knowledges: list[KnowledgebaseEntry] = Field(default_factory=list)


class SearchKnowledgebaseResponse(BaseModel):
    """Represents the response from a knowledgebase search.

    Attributes:
        knowledges: A list of knowledgebase entries that relate to the search query.
    """

    knowledges: list[KnowledgebaseEntry] = Field(default_factory=list)


async def search_knowledgebase(
    self, query: str, app_name: str
) -> SearchKnowledgebaseResponse:
    """Searches the knowledgebase of the current user."""
    if isinstance(knowledgebase, KnowledgeBase):
        entry_list = knowledgebase.search(query)
        return SearchKnowledgebaseResponse(knowledges=entry_list)
    else:
        return SearchKnowledgebaseResponse(knowledges=[])


@wrapt.when_imported("google.adk.tools.tool_context")
def on_tool_context_imported(module):
    class_ = getattr(module, "ToolContext", None)
    if not class_:
        raise ImportError("Could not find ToolContext in module")

    if not hasattr(class_, "search_knowledgebase"):
        class_.search_knowledgebase = search_knowledgebase


async def load_knowledgebase(
    query: str, tool_context: ToolContext
) -> LoadKnowledgebaseResponse:
    """Loads the knowledgebase for the user.

    Args:
      query: The query to load the knowledgebase for.

    Returns:
      A list of knowledgebase results.
    """

    search_knowledgebase_response = await tool_context.search_knowledgebase(  # type: ignore[attr-defined]
        query, tool_context._invocation_context.app_name
    )
    return LoadKnowledgebaseResponse(
        knowledges=search_knowledgebase_response.knowledges
    )


class LoadKnowledgebaseTool(FunctionTool):
    """A tool that loads the common knowledgebase.

    In the future, we will support multiple knowledgebase based on different user.
    """

    def __init__(self):
        super().__init__(load_knowledgebase)
        global knowledgebase
        if knowledgebase is None:
            logger.info(
                "Get global knowledgebase instance failed, failed to set knowledgebase tool backend."
            )
        else:
            if not self.custom_metadata:
                self.custom_metadata = {}
            self.custom_metadata["backend"] = knowledgebase.backend

    @override
    def _get_declaration(self) -> types.FunctionDeclaration | None:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(
                        type=types.Type.STRING,
                    )
                },
                required=["query"],
            ),
        )

    @override
    async def process_llm_request(
        self,
        *,
        tool_context: ToolContext,
        llm_request: LlmRequest,
    ) -> None:
        await super().process_llm_request(
            tool_context=tool_context, llm_request=llm_request
        )
        # Tell the model about the knowledgebase.
        llm_request.append_instructions(
            [
                """
You have a knowledgebase. You can use it to answer questions. If any questions need
you to look up the knowledgebase, you should call load_knowledgebase function with a query.
"""
            ]
        )


load_knowledgebase_tool = LoadKnowledgebaseTool()

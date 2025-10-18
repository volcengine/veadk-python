from __future__ import annotations

from google.adk.models.llm_request import LlmRequest
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.knowledgebase import KnowledgeBase
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class LoadKnowledgebaseResponse(BaseModel):
    knowledges: list[KnowledgebaseEntry] = Field(default_factory=list)


class LoadKnowledgebaseTool(FunctionTool):
    """A tool that loads the common knowledgebase"""

    def __init__(self, knowledgebase: KnowledgeBase):
        super().__init__(self.load_knowledgebase)

        self.knowledgebase = knowledgebase

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
                f"""
You have a knowledgebase (knowledegebase name is `{self.knowledgebase.name}`, knowledgebase description is `{self.knowledgebase.description}`). You can use it to answer questions. If any questions need
you to look up the knowledgebase, you should call load_knowledgebase function with a query.
"""
            ]
        )

    async def load_knowledgebase(
        self, query: str, tool_context: ToolContext
    ) -> LoadKnowledgebaseResponse:
        """Loads the knowledgebase for the user.

        Args:
        query: The query to load the knowledgebase for.

        Returns:
        A list of knowledgebase results.
        """
        logger.info(f"Search knowledgebase: {self.knowledgebase.name}")
        response = self.knowledgebase.search(query)
        logger.info(f"Loaded {len(response)} knowledgebase entries for query: {query}")
        return LoadKnowledgebaseResponse(knowledges=response)

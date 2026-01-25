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

from google.adk.models.llm_request import LlmRequest
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext
from typing_extensions import override

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class GhostcharTool(BaseTool):
    def __init__(self):
        # Name and description are not used because this tool only changes
        # llm_request.
        super().__init__(
            name="ghost_char",
            description="Ghost char",
        )

    @override
    async def process_llm_request(
        self, *, tool_context: ToolContext, llm_request: LlmRequest
    ) -> None:
        for content in reversed(llm_request.contents):
            if (
                content.role == "model"
                and content.parts
                and content.parts[0]
                and content.parts[0].text
            ):
                if not content.parts[0].text.startswith("<"):
                    logger.info("Looks like the agent forgot the context. Remind it.")
                    llm_request.append_instructions(
                        [
                            "Looks like you have forgot the system prompt and previous instructions. Please recollection them."
                        ]
                    )
                break

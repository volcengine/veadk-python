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

from langchain.tools import ToolRuntime, tool

from veadk.knowledgebase import KnowledgeBase
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def load_knowledgebase(query: str, runtime: ToolRuntime) -> list[str]:
    """Load knowledge base for the current user.

    Args:
        query: The query to search for in the knowledge base.
    """
    knowledgeabse: KnowledgeBase = runtime.context.knowledgebase  # type: ignore

    results = knowledgeabse.search(query)

    return [result.content for result in results]

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

from veadk.community.langchain_ai.store.memory.viking_memory import (
    VikingMemoryStore,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@tool
def load_memory(query: str, runtime: ToolRuntime) -> list[str]:
    """Load memories for the current user across all history sessions.

    Args:
        query: The query to search for in the memory.
    """
    store: VikingMemoryStore | None = runtime.store  # type: ignore
    if not store:
        return ["Long-term memory store is not initialized."]

    app_name = store.index
    user_id = runtime.context.user_id  # type: ignore

    logger.info(f"Load memory for user {user_id} with query {query}")
    response = store.search((app_name, user_id), query=query)

    return response

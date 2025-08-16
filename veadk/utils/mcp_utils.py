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

from typing import Any

from google.adk.tools.mcp_tool.mcp_session_manager import (
    SseConnectionParams,
    StreamableHTTPConnectionParams,
)

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def get_mcp_params(url: str) -> Any:
    """Automatically set MCP connection params according to url.

    Only support http and sse protocol.

    Args:
        url (str): MCP server url
    """
    if "/mcp" in url:
        logger.info("MCP url detected, use StreamableHTTPConnectionParams.")
        return StreamableHTTPConnectionParams(url=url)
    elif "/sse" in url:
        logger.info("SSE url detected, use SseConnectionParams.")
        return SseConnectionParams(url=url)
    else:
        raise ValueError(
            "Unsupported MCP url, because it has no `/mcp` or `/sse` field in your url. Please specify your connection params manually."
        )

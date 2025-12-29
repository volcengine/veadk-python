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

import os

from google.adk.tools.mcp_tool import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import StdioServerParameters, McpToolset

from veadk.config import getenv
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _get_vod_envs() -> dict[str, str]:
    """
    note, available `TOOL_VOD_GROUPS`:
        "edit",  # Tools related to video editing
        "intelligent_slicing",  # Tools related to intelligent slicing
        "intelligent_matting",  # Tools related to intelligent matting
        "subtitle_processing",  # Tools related to subtitle processing
        "audio_processing",  # Tools related to audio processing
        "video_enhancement",  # Tools related to video enhancement
        'upload',  # Related to upload
        "video_play"  # Related to video playback
    https://github.com/volcengine/mcp-server/blob/main/server/mcp_server_vod/src/vod/mcp_server.py#L14
    """

    ak = getenv("VOLCENGINE_ACCESS_KEY", None)
    sk = getenv("VOLCENGINE_SECRET_KEY", None)

    if os.getenv("TOOL_VOD_GROUPS", None):
        return {
            "VOLCENGINE_ACCESS_KEY": ak,
            "VOLCENGINE_SECRET_KEY": sk,
            "MCP_TOOL_GROUPS": getenv("TOOL_VOD_GROUPS"),
        }
    else:
        return {
            "VOLCENGINE_ACCESS_KEY": ak,
            "VOLCENGINE_SECRET_KEY": sk,
        }


_vod_envs = _get_vod_envs()

vod_tools = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uvx",
            args=[
                "--from",
                "git+https://github.com/volcengine/mcp-server#subdirectory=server/mcp_server_vod",
                "mcp-server-vod",
            ],
            env=_vod_envs,
        ),
        timeout=float(os.getenv("TOOL_VOD_TIMEOUT", 10.0)),
    )
)

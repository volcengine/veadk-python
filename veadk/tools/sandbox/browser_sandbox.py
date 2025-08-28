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

from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

from veadk.config import getenv
from veadk.utils.mcp_utils import get_mcp_params

url = getenv("TOOL_BROWSER_SANDBOX_URL")


browser_sandbox = MCPToolset(connection_params=get_mcp_params(url=url))

# browser_sandbox = ...


# def browser_use(prompt: str) -> str:
#     """Using the remote browser sandbox to according to the prompt.

#     Args:
#         prompt (str): The prompt to be used.

#     Returns:
#         str: The response from the sandbox.
#     """
#     ...

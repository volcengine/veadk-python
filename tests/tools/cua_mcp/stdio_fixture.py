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

"""Cloud-free subprocess used only by integration tests; no production fake mode."""

import asyncio
import base64
import sys
from fakes import Platform, Desktop
from agentkit_cua_mcp.service import SandboxService
from agentkit_cua_mcp.server import run


class ImageDesktop(Desktop):
    async def call(self, name, arguments):
        if name == "cua_screenshot":
            return b"\x89PNG\r\n\x1a\nTEST"
        if name == "cua_click" and arguments.get("include_screenshot"):
            return {
                "success": True,
                "data": {"action_performed": "CLICK"},
                "screenshot": base64.b64encode(b"\x89PNG\r\n\x1a\nTEST").decode(),
            }
        if name == "cua_actions_batch":
            return {
                "success": True,
                "data": {
                    "performed": [a["action_type"] for a in arguments["actions"]],
                    "failed_index": None,
                    "error": None,
                },
            }
        return await super().call(name, arguments)


async def main():
    platform = Platform()
    if "--disabled" in sys.argv:
        platform.envs = []
        ImageDesktop.enabled = False
        ImageDesktop.ready = False
    if "--existing" in sys.argv:
        await platform.request("CreateSession", {"UserSessionId": "agent_user_one"})
    await run(SandboxService(platform, "t-example", desktop_factory=ImageDesktop))


asyncio.run(main())

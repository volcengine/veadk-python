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

import asyncio
from pathlib import Path

from a2a.types import TextPart
from fastmcp.client import Client

from veadk.cloud.cloud_agent_engine import CloudAgentEngine
from veadk.cloud.cloud_app import CloudApp, get_message_id

SESSION_ID = "cloud_app_test_session"
USER_ID = "cloud_app_test_user"


async def _send_msg_with_a2a(cloud_app: CloudApp, message: str) -> None:
    print("===== A2A example =====")

    response_message = await cloud_app.message_send(message, SESSION_ID, USER_ID)

    if not response_message or not response_message.parts:
        print(
            "No response from VeFaaS application. Something wrong with cloud application."
        )
        return

    print(f"Message ID: {get_message_id(response_message)}")

    if isinstance(response_message.parts[0].root, TextPart):
        print(
            f"Response from {cloud_app.vefaas_endpoint}: {response_message.parts[0].root.text}"
        )
    else:
        print(
            f"Response from {cloud_app.vefaas_endpoint}: {response_message.parts[0].root}"
        )


async def _send_msg_with_mcp(cloud_app: CloudApp, message: str) -> None:
    print("===== MCP example =====")

    endpoint = cloud_app._get_vefaas_endpoint()
    print(f"MCP server endpoint: {endpoint}/mcp")

    # Connect to MCP server
    client = Client(f"{endpoint}/mcp")

    async with client:
        # List available tools
        tools = await client.list_tools()
        print(f"Available tools: {tools}")

        # Call run_agent tool, pass user input and session information
        res = await client.call_tool(
            "run_agent",
            {
                "user_input": message,
                "session_id": SESSION_ID,
                "user_id": USER_ID,
            },
        )
        print(f"Response from {cloud_app.vefaas_endpoint}: {res}")


async def main():
    engine = CloudAgentEngine()

    cloud_app = engine.deploy(
        path=str(Path(__file__).parent / "src"),
        application_name="{{cookiecutter.vefaas_application_name}}",
        gateway_name="{{cookiecutter.veapig_instance_name}}",
        gateway_service_name="{{cookiecutter.veapig_service_name}}",
        gateway_upstream_name="{{cookiecutter.veapig_upstream_name}}",
        use_adk_web={{cookiecutter.use_adk_web}},
        auth_method="{{cookiecutter.auth_method}}",
        local_test=False,  # Set to True for local testing before deploy to VeFaaS
    )
    print(f"VeFaaS application ID: {cloud_app.vefaas_application_id}")

    if {{cookiecutter.use_adk_web}}:
        print(f"Web is running at: {cloud_app.vefaas_endpoint}")
    else:
        # Test with deployed cloud application
        message = "How is the weather like in Beijing?"
        print(f"Test message: {message}")

        # await _send_msg_with_a2a(cloud_app=cloud_app, message=message)
        # await _send_msg_with_mcp(cloud_app=cloud_app, message=message)


if __name__ == "__main__":
    asyncio.run(main())

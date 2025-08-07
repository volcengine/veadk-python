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

from veadk.cloud.cloud_agent_engine import CloudAgentEngine

SESSION_ID = "cloud_app_test_session"
USER_ID = "cloud_app_test_user"

VEFAAS_APPLICATION_NAME = "weather-reporter"
GATEWAY_NAME = ""
GATEWAY_SERVICE_NAME = ""
GATEWAY_UPSTREAMNAME = ""
USE_STUDIO = False
USE_ADK_WEB = False


async def main():
    engine = CloudAgentEngine()

    cloud_app = engine.deploy(
        path=str(Path(__file__).parent / "src"),
        application_name=VEFAAS_APPLICATION_NAME,
        gateway_name=GATEWAY_NAME,
        gateway_service_name=GATEWAY_SERVICE_NAME,
        gateway_upstream_name=GATEWAY_UPSTREAMNAME,
        use_studio=USE_STUDIO,
        use_adk_web=USE_ADK_WEB,
    )

    if not USE_STUDIO and not USE_ADK_WEB:
        response_message = await cloud_app.message_send(
            "How is the weather like in Beijing?", SESSION_ID, USER_ID
        )
        print(f"VeFaaS application ID: {cloud_app.vefaas_application_id}")
        print(f"Message ID: {response_message.messageId}")
        print(
            f"Response from {cloud_app.vefaas_endpoint}: {response_message.parts[0].root.text}"
        )
    else:
        print(f"Web is running at: {cloud_app.vefaas_endpoint}")


if __name__ == "__main__":
    asyncio.run(main())

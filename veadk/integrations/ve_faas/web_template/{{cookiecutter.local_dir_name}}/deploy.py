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

async def main():
    engine = CloudAgentEngine()

    cloud_app = engine.deploy(
        path=str(Path(__file__).parent / "src"),
        application_name="{{cookiecutter.vefaas_application_name}}",
        gateway_name="{{cookiecutter.veapig_instance_name}}",
        gateway_service_name="{{cookiecutter.veapig_service_name}}",
        gateway_upstream_name="{{cookiecutter.veapig_upstream_name}}",
        use_adk_web={{cookiecutter.use_adk_web}},
        local_test=False,  # Set to True for local testing before deploy to VeFaaS
    )
    print(f"VeFaaS application ID: {cloud_app.vefaas_application_id}")

    if {{cookiecutter.use_adk_web}}:
        print(f"Web is running at: {cloud_app.vefaas_endpoint}")
    else:
        print(f"Web template does not support use_adk_web=False")


if __name__ == "__main__":
    asyncio.run(main())

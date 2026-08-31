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

"""Run the VeADK agent with remotely dispatched sandbox tools."""

import argparse
import asyncio
import uuid

from agents.self_host_sandbox_agent.agent import agent
from veadk import Runner


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default=(
            "Use the bash tool to run: printf 'veadk-self-host-ok'. "
            "Then reply with the exact output."
        ),
    )
    parser.add_argument("--session-id", default=None)
    args = parser.parse_args()

    session_id = args.session_id or f"veadk-{uuid.uuid4()}"
    runner = Runner(agent=agent, app_name="self_host_sandbox_demo")
    output = await runner.run(messages=args.prompt, session_id=session_id)
    print(output)


if __name__ == "__main__":
    asyncio.run(main())

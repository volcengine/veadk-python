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

"""Run the piagent runtime example locally.

Set PIAGENT_BINARY to a platform-matching local Pi executable before running.
On macOS arm64, for example:

    export PIAGENT_BINARY=/private/tmp/veadk-piagent-binary/v0.80.6-darwin/extracted/pi/pi
    export PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-example-home

Then run:

    .venv/bin/python examples/piagent_runtime_basic/main.py "hello"
"""

import asyncio
import sys

from veadk import Runner

from examples.piagent_runtime_basic.agent import agent


async def main() -> None:
    message = " ".join(sys.argv[1:]).strip() or "用一句话介绍火山引擎。"

    runner = Runner(agent=agent, app_name="piagent_runtime_basic")
    answer = await runner.run(
        messages=message,
        user_id="local-user",
        session_id="local-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())

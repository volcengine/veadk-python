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

import click


@click.command()
@click.option("--path", default=".", help="Path to the agent directory")
def studio(path: str) -> None:
    """Run VeADK Studio with the specified agent. The VeADK Studio will be deprecated soon."""
    import os
    from pathlib import Path

    import uvicorn

    from veadk.cli.studio.fast_api import get_fast_api_app
    from veadk.utils.misc import load_module_from_file

    path = str(Path(path).resolve())

    agent_py_path = os.path.join(path, "agent.py")

    module = load_module_from_file(
        module_name="local_agent", file_path=str(agent_py_path)
    )

    agent = None
    short_term_memory = None
    try:
        agent = module.agent
        short_term_memory = module.short_term_memory
    except AttributeError as e:
        missing = str(e).split("'")[1] if "'" in str(e) else "unknown"
        raise AttributeError(f"agent.py is missing required variable: {missing}")

    app = get_fast_api_app(agent, short_term_memory)

    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        loop="asyncio",  # for deepeval
    )

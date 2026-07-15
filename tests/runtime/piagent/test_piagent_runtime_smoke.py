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

"""Manual smoke test for a real local Pi binary.

This file is intentionally skipped by default because it calls a real model. Run
it explicitly after setting model credentials. Set PIAGENT_BINARY to use an
existing Pi executable inside a fully extracted Pi release directory; otherwise
the runtime uses PIAGENT_INSTALL_DIR/pi/pi and downloads Pi there when it is
missing:

    PIAGENT_BINARY=/path/to/pi \
    PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-test-home \
    MODEL_AGENT_API_KEY=<key> \
    PIAGENT_SMOKE_MODEL=<model> \
    PIAGENT_RUN_SMOKE=1 \
    .venv/bin/python -m pytest tests/runtime/piagent/test_piagent_runtime_smoke.py -s
"""

from __future__ import annotations

import os

import pytest

from veadk import Agent, Runner


def pytest_configure(config):
    config.addinivalue_line("markers", "piagent_smoke: real Pi binary/model smoke test")


@pytest.mark.piagent_smoke
@pytest.mark.asyncio
async def test_real_piagent_runtime_smoke():
    if os.getenv("PIAGENT_RUN_SMOKE") != "1":
        pytest.skip("set PIAGENT_RUN_SMOKE=1 to call a real Pi binary and model")

    api_key = os.getenv("PIAGENT_SMOKE_API_KEY") or os.getenv("MODEL_AGENT_API_KEY")
    if not api_key:
        pytest.skip("set PIAGENT_SMOKE_API_KEY or MODEL_AGENT_API_KEY")

    model_name = os.getenv("PIAGENT_SMOKE_MODEL")
    if not model_name:
        pytest.skip("PIAGENT_SMOKE_MODEL is required")

    agent = Agent(
        name="assistant",
        instruction="Answer briefly.",
        runtime="piagent",
        model_name=model_name,
        model_api_base=os.getenv(
            "PIAGENT_SMOKE_API_BASE",
            "https://ark.cn-beijing.volces.com/api/v3/",
        ),
        model_api_key=api_key,
        model_api_key_name="",
    )
    runner = Runner(agent=agent, app_name="piagent_smoke")

    result = await runner.run("hello", user_id="u1", session_id="s1")

    assert isinstance(result, str)
    assert result.strip()

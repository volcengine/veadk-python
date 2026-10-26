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

"""AgentKit HTTP listener; business execution stays in the existing Agent Loop."""

from __future__ import annotations

import os

from agentkit.apps import AgentkitSimpleApp


def _first_env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default


app = AgentkitSimpleApp()


@app.ping
def ping() -> dict[str, str]:
    return {"status": "ok"}


@app.entrypoint
async def invoke(payload: dict, headers: dict) -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(
        host=_first_env("AGENTKIT_RUNTIME_HOST", "MA_RUNTIME_HOST", default="0.0.0.0"),
        port=int(
            _first_env(
                "AGENTKIT_RUNTIME_PORT", "MA_RUNTIME_PORT", "PORT", default="8080"
            )
        ),
    )

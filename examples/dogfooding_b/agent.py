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

"""Agent builder — slot B for the web UI's A/B compare mode.

Identical to ``dogfooding`` (same config-JSON instruction) but a SEPARATE ADK app
so the web UI can run two builders in parallel and diff their designs. Pin its
model with the env var ``AGENT_BUILDER_MODEL_B`` (otherwise it uses the VeADK
default model). The shared instruction is imported from the ``dogfooding`` app so
the two stay in sync.
"""

import os

from veadk import Agent

# The two builder apps share one instruction. ADK puts the agents dir on
# sys.path, so the sibling app package is importable; fall back to the
# fully-qualified path when imported as part of the `examples` package.
try:
    from dogfooding.agent import INSTRUCTION
except ImportError:  # pragma: no cover - depends on how the loader sets sys.path
    from examples.dogfooding.agent import INSTRUCTION

_MODEL_B = os.getenv("AGENT_BUILDER_MODEL_B", "").strip()

agent = Agent(
    name="agent_builder_b",
    description="VeADK Agent Builder (B)：A/B 对比中的第二个构建器。",
    instruction=lambda _ctx: INSTRUCTION,
    **({"model_name": _MODEL_B} if _MODEL_B else {}),
)

# Required by the Google ADK agent loader.
root_agent = agent

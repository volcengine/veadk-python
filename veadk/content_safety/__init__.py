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
"""Opt-in content safety for VeADK agents.

The simplest setup is a ``tool.content_safety`` block in ``config.yaml``::

    agent = Agent(...)
    runner = Runner(agent=agent)   # plugin mounted automatically

``Agent(content_safety=...)`` supplies the configuration in code, and
``agent.content_safety_plugins`` covers a manually constructed ADK ``App``.
Nothing is mounted when the block is absent or ``provider`` is ``none``.

The explicit API remains available::

    from veadk.content_safety import (
        ContentSafetyConfig, build_content_safety,
    )

    config = ContentSafetyConfig.from_dict({...})
    plugin = build_content_safety(config)
    app = App(name="my_app", root_agent=agent, plugins=[plugin] if plugin else [])
"""

from .config import (
    DEFAULT_BLOCK_MESSAGE,
    DEFAULT_DECISION_MODEL,
    DEFAULT_QUESTION_INSTRUCTIONS,
    DEFAULT_QUESTION_THRESHOLD,
    ContentSafetyConfig,
    ContentSafetyConfigError,
    DecisionConfig,
    QuestionConfig,
    default_questions,
    load_content_safety_config,
    load_content_safety_config_if_present,
)
from .decider import ThresholdDecider
from .factory import build_content_safety
from .integration import (
    resolve_content_safety_plugin,
    resolve_content_safety_plugins,
)
from .plugin import DecisionPlugin
from .state import STATE_POLICY_PREFIX, StateBuilder
from .types import (
    AuditAction,
    AuditResult,
    AuditStatus,
    Checkpoint,
    Provider,
    QuestionResult,
)

__all__ = [
    "AuditAction",
    "AuditResult",
    "AuditStatus",
    "Checkpoint",
    "ContentSafetyConfig",
    "ContentSafetyConfigError",
    "DecisionPlugin",
    "DecisionConfig",
    "Provider",
    "QuestionConfig",
    "QuestionResult",
    "StateBuilder",
    "STATE_POLICY_PREFIX",
    "DEFAULT_BLOCK_MESSAGE",
    "DEFAULT_DECISION_MODEL",
    "DEFAULT_QUESTION_INSTRUCTIONS",
    "DEFAULT_QUESTION_THRESHOLD",
    "default_questions",
    "ThresholdDecider",
    "build_content_safety",
    "load_content_safety_config",
    "load_content_safety_config_if_present",
    "resolve_content_safety_plugin",
    "resolve_content_safety_plugins",
]

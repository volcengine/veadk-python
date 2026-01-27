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

import json
from pathlib import Path

from google.adk.tools.tool_context import ToolContext

from veadk import Agent
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def load_profile(profile_path: Path) -> dict:
    # read file content
    with open(profile_path, "r") as f:
        content = f.read()
    return json.loads(content)


def load_kb_queries(profile_names: list[str], tool_context: ToolContext) -> list[str]:
    """Load recommanded knowledgebase queries based on the knowledgebase profiles.

    Args:
        profile_names: The list of knowledgebase profile names to load the profile for.

    Returns:
    A list of knowledgebase profile results.
    """
    logger.info(f"Loading knowledgebase profiles: {profile_names}")

    if not isinstance(tool_context._invocation_context.agent, Agent):
        logger.warning("Agent is not VeADK Agent, cannot load knowledgebase profile")
        return ["Error: Agent is not VeADK Agent, cannot load knowledgebase profile"]

    if not tool_context._invocation_context.agent.knowledgebase:
        logger.warning("Agent has no knowledgebase, cannot load knowledgebase profile")
        return ["Error: Agent has no knowledgebase, cannot load knowledgebase profile"]

    index = tool_context._invocation_context.agent.knowledgebase.index

    all_profile_names = []

    with open(
            f"./profiles/knowledgebase/profiles_{index}/all_profile_list.json",
            "r",
    ) as f:
        all_profile_names = json.load(f)

    recommanded_queries = []
    for profile_name in profile_names:
        if profile_name not in all_profile_names:
            logger.info(f"{profile_name} Invalid")
            continue
        profile_path = Path(
            f"./profiles/knowledgebase/profiles_{index}/profile_{profile_name}.json"
        )
        profile = load_profile(profile_path)
        recommanded_queries.extend(profile.get("keywords", []))
        logger.debug(
            f"Loaded keywords from profile {profile_name}: {profile.get('keywords', [])}"
        )
    logger.debug(
        f"Loaded total keywords for knowledgebase {index}: {recommanded_queries}"
    )
    return recommanded_queries

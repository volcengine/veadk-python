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


def load_profile(profile_path: Path) -> dict:
    # read file content
    with open(profile_path, "r") as f:
        content = f.read()
    return json.loads(content)


def load_history_events(group_names: list[str], tool_context: ToolContext) -> dict:
    """Load necessary history events by group names.

    Args:
        group_names (list[str]): The list of group names to load events for.
    """
    app_name = tool_context._invocation_context.app_name
    user_id = tool_context._invocation_context.user_id
    session_id = tool_context._invocation_context.session.id

    events = {}
    for group_name in group_names:
        profile_path = Path(
            f"./profiles/memory/{app_name}/{user_id}/{session_id}/{group_name}.json"
        )
        profile = load_profile(profile_path)
        events[group_name] = profile.get("event_list", [])
    return events

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

"""Create or select an AgentKit Skill Space for mpa-agent (FR-14).

Mirrors the reference chain's ``CreateSkillSpace/GetSkillSpace`` step: select an
existing space by name when present, otherwise create one, and return its id so
the caller can inject ``SKILL_SPACE_ID`` into the runtime env.
"""

from __future__ import annotations

from typing import Any


class MpaSkillSpaceError(RuntimeError):
    """Raised when a Skill Space cannot be resolved or created."""


def _find_space_by_name(client: Any, name: str) -> str:
    from agentkit.sdk.skills import types as st

    request = st.ListSkillSpacesRequest(
        filter=st.SkillSpaceFilter(name=name),
        page_number=1,
        page_size=50,
    )
    resp = client.list_skill_spaces(request)
    for space in getattr(resp, "items", None) or []:
        if getattr(space, "name", None) == name:
            return str(getattr(space, "id", "") or "")
    return ""


def ensure_skill_space(
    client: Any,
    *,
    name: str,
    description: str = "Created by VeADK mpa provisioning",
    project_name: str = "default",
) -> str:
    """Return the id of a Skill Space named ``name``, creating it if absent.

    An empty ``name`` returns an empty string so callers omit ``SKILL_SPACE_ID``.
    """
    name = (name or "").strip()
    if not name:
        return ""

    existing = _find_space_by_name(client, name)
    if existing:
        return existing

    from agentkit.sdk.skills import types as st

    resp = client.create_skill_space(
        st.CreateSkillSpaceRequest(
            name=name,
            description=description,
            project_name=project_name,
        )
    )
    space_id = str(getattr(resp, "id", "") or "")
    if not space_id:
        raise MpaSkillSpaceError("CreateSkillSpace returned no id")
    return space_id

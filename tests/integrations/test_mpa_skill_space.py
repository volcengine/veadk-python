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

"""Tests for Skill Space create/select orchestration (FR-14, AC-12)."""

from types import SimpleNamespace

from veadk.integrations.mpa.mpa_skill_space import ensure_skill_space


class _FakeSkillsClient:
    def __init__(self, *, existing=None):
        self._existing = existing or []
        self.created = None
        self.create_calls = 0

    def list_skill_spaces(self, request):
        wanted = getattr(getattr(request, "filter", None), "name", None)
        items = [s for s in self._existing if wanted is None or s.name == wanted]
        return SimpleNamespace(items=items, total_count=len(items))

    def create_skill_space(self, request):
        self.create_calls += 1
        self.created = request
        return SimpleNamespace(id="ss-new")


def test_select_existing_space_by_name() -> None:
    """AC-12: an existing space with the target name is selected, not created."""
    client = _FakeSkillsClient(
        existing=[SimpleNamespace(id="ss-old", name="mpa-space", status="Ready")]
    )
    space_id = ensure_skill_space(client, name="mpa-space")
    assert space_id == "ss-old"
    assert client.create_calls == 0


def test_create_space_when_absent() -> None:
    """AC-12: when no space matches the name, one is created."""
    client = _FakeSkillsClient(existing=[])
    space_id = ensure_skill_space(client, name="mpa-space")
    assert space_id == "ss-new"
    assert client.create_calls == 1
    assert client.created.name == "mpa-space"


def test_blank_name_returns_empty() -> None:
    """No name -> no space id (SKILL_SPACE_ID omitted upstream)."""
    client = _FakeSkillsClient(existing=[])
    assert ensure_skill_space(client, name="") == ""
    assert client.create_calls == 0

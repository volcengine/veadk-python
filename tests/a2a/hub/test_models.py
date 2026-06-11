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

"""Contract tests for the A2A hub pydantic models.

These pin field names, defaults, and inheritance so that a silent change to the
hub wire schema is caught here rather than by a broken client.
"""

import pytest
from pydantic import ValidationError

from veadk.a2a.hub.models import (
    AgentInformation,
    BaseResponse,
    GetAgentResponse,
    GetAgentsResponse,
    GetGroupsResponse,
    RegisterAgentRequest,
    RegisterAgentResponse,
    RegisterGroupResponse,
)


def test_base_response_defaults():
    resp = BaseResponse()
    assert resp.err_code == 0
    assert resp.msg == ""


def test_base_response_explicit_values():
    resp = BaseResponse(err_code=1, msg="boom")
    assert resp.err_code == 1
    assert resp.msg == "boom"


def test_register_group_response_inherits_base():
    assert issubclass(RegisterGroupResponse, BaseResponse)
    resp = RegisterGroupResponse(group_id="g1")
    assert resp.group_id == "g1"
    # inherited defaults
    assert resp.err_code == 0
    assert resp.msg == ""


def test_register_group_response_default_group_id():
    assert RegisterGroupResponse().group_id == ""


def test_register_agent_request_requires_fields():
    # group_id, agent_id, agent_card have no defaults -> required.
    with pytest.raises(ValidationError) as exc_info:
        RegisterAgentRequest()  # type: ignore[call-arg]
    missing = {e["loc"][0] for e in exc_info.value.errors()}
    assert {"group_id", "agent_id", "agent_card"} <= missing


def test_register_agent_request_roundtrip():
    card = {"name": "demo", "url": "http://x"}
    req = RegisterAgentRequest(group_id="g1", agent_id="a1", agent_card=card)
    assert req.group_id == "g1"
    assert req.agent_id == "a1"
    assert req.agent_card == card
    # RegisterAgentRequest extends BaseResponse, so it carries err_code/msg too.
    assert req.err_code == 0


def test_register_agent_response_defaults():
    resp = RegisterAgentResponse()
    assert resp.group_id == ""
    assert resp.agent_id == ""
    # agent_card uses default_factory=dict -> a fresh dict each time.
    assert resp.agent_card == {}
    other = RegisterAgentResponse()
    assert resp.agent_card is not other.agent_card


def test_agent_information_defaults_and_factory():
    info = AgentInformation()
    assert info.agent_id == ""
    assert info.agent_card == {}
    # mutating one instance's factory dict must not leak to another.
    info.agent_card["k"] = "v"
    assert AgentInformation().agent_card == {}


def test_get_agents_response_holds_agent_information_list():
    info = AgentInformation(agent_id="a1", agent_card={"x": 1})
    resp = GetAgentsResponse(group_id="g1", agent_infos=[info])
    assert resp.group_id == "g1"
    assert len(resp.agent_infos) == 1
    assert isinstance(resp.agent_infos[0], AgentInformation)
    assert resp.agent_infos[0].agent_id == "a1"


def test_get_agents_response_coerces_dict_to_model():
    # pydantic should validate a plain dict into an AgentInformation.
    resp = GetAgentsResponse(agent_infos=[{"agent_id": "a2", "agent_card": {}}])  # type: ignore[list-item]
    assert isinstance(resp.agent_infos[0], AgentInformation)
    assert resp.agent_infos[0].agent_id == "a2"


def test_get_agents_response_default_empty_list():
    resp = GetAgentsResponse()
    assert resp.agent_infos == []
    assert GetAgentsResponse().agent_infos is not resp.agent_infos


def test_get_agent_response_defaults():
    resp = GetAgentResponse()
    assert resp.agent_id == ""
    assert resp.agent_card == {}


def test_get_groups_response_defaults_and_assignment():
    assert GetGroupsResponse().group_ids == []
    resp = GetGroupsResponse(group_ids=["g1", "g2"])
    assert resp.group_ids == ["g1", "g2"]
